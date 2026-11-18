import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from gateway.core import Gateway
from gateway.server import make_server


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, n):
        self.now += n


@pytest.fixture
def setup(tmp_path):
    config = json.loads(Path("gateway/config.example.json").read_text())
    config["database"] = str(tmp_path / "test.sqlite3")
    clock = Clock()
    gateway = Gateway(config, clock=clock)
    yield gateway, clock
    gateway.close()


def packet(seq=1, boot=1, **kwargs):
    return dict(
        device="room-node-01", boot=boot, seq=seq, temperature=27.0, humidity=60.0, fan=False, **kwargs
    )


def test_replay_duplicate_and_reboot(setup):
    gateway, _ = setup
    assert gateway.ingest(packet(2))
    assert not gateway.ingest(packet(2))
    assert not gateway.ingest(packet(1))
    assert gateway.ingest(packet(1, boot=2))
    assert gateway.snapshot()["outbox_count"] == 2


@pytest.mark.parametrize(
    "key,value",
    [
        ("temperature", float("nan")),
        ("humidity", float("inf")),
        ("humidity", 101),
        ("temperature", True),
        ("seq", -1),
        ("seq", 1.5),
        ("boot", True),
        ("fan", "false"),
        ("device", "intruder"),
    ],
)
def test_invalid_telemetry_has_no_side_effect(setup, key, value):
    gateway, _ = setup
    p = packet()
    p[key] = value
    with pytest.raises(ValueError):
        gateway.ingest(p)
    assert gateway.snapshot()["outbox_count"] == 0
    assert gateway.snapshot()["latest"] is None


def test_hysteresis_prevents_chatter(setup):
    gateway, _ = setup
    for seq, temp in enumerate([27, 32, 31, 30.1, 30, 29], 1):
        p = packet(seq)
        p["temperature"] = temp
        gateway.ingest(p)
    assert [e["kind"] for e in reversed(gateway.snapshot()["events"])] == [
        "threshold_raised",
        "threshold_cleared",
    ]


def test_humidity_alarm(setup):
    gateway, _ = setup
    for seq, rh in enumerate([60, 81, 78, 75], 1):
        p = packet(seq)
        p["humidity"] = rh
        gateway.ingest(p)
    assert len(gateway.snapshot()["events"]) == 2


def test_command_not_successful_until_matching_device_ack(setup):
    gateway, clock = setup
    sent = []
    gateway.send_command = sent.append
    command = gateway.command("room-node-01", True, rpc_id=31)
    gateway.tick()
    assert sent == [{"type": "command", "id": command["id"], "value": True}]
    assert gateway.snapshot()["commands"][0]["status"] == "pending"
    assert not gateway.ack(command["id"], False)
    assert not gateway.ack(command["id"] + 1, True)
    assert gateway.ack(command["id"], True)
    assert not gateway.ack(command["id"], True)
    replies = []
    gateway.flush(lambda topic, body: replies.append((topic, body)) or True)
    assert replies[0][1] == {
        "device": "room-node-01",
        "id": 31,
        "data": {"success": True, "fan": True, "detail": "Device ACK"},
    }


def test_timeout_never_fabricates_success(setup):
    gateway, clock = setup
    command = gateway.command("room-node-01", False, rpc_id=2)
    gateway.tick()
    clock.advance(0.6)
    gateway.tick()
    clock.advance(5)
    gateway.tick()
    assert gateway.snapshot()["commands"][0]["status"] == "failed"
    assert not gateway.ack(command["id"], False)
    bodies = []
    gateway.flush(lambda _, body: bodies.append(body) or True)
    assert bodies[0]["data"]["success"] is False


def test_duplicate_rpc_does_not_reapply_command(setup):
    gateway, _ = setup
    first = gateway.command("room-node-01", True, rpc_id=12)
    assert gateway.command("room-node-01", True, rpc_id=12)["id"] == first["id"]
    with pytest.raises(ValueError):
        gateway.command("room-node-01", False, rpc_id=12)
    with pytest.raises(ValueError):
        gateway.command("room-node-01", False)
    gateway.ack(first["id"], True)
    gateway.command("room-node-01", True, rpc_id=12)
    assert len(gateway.snapshot()["commands"]) == 1


def test_outbox_survives_restart_and_failed_publish(setup):
    gateway, clock = setup
    gateway.ingest(packet())
    assert gateway.flush(lambda *_: False) == 0
    restored = Gateway(gateway.config, clock=clock)
    try:
        assert restored.snapshot()["outbox_count"] == 1
        assert restored.flush(lambda *_: True) == 1
        assert restored.snapshot()["outbox_count"] == 0
    finally:
        restored.close()


def test_backpressure_does_not_partially_store_packet(setup):
    gateway, _ = setup
    gateway.config["max_outbox"] = 1
    gateway.ingest(packet())
    with pytest.raises(ValueError):
        gateway.ingest(packet(2))
    assert gateway.snapshot()["latest"]["seq"] == 1


def test_stale_data_after_disconnect(setup):
    gateway, clock = setup
    assert gateway.snapshot()["stale"]
    gateway.ingest(packet())
    assert not gateway.snapshot()["stale"]
    clock.advance(16)
    assert gateway.snapshot()["stale"]
    assert gateway.snapshot()["latest"]["values"]["temperature"] == 27


def test_ai_event_path(setup):
    gateway, _ = setup
    gateway.predictor = lambda t, h: (-0.2, True) if t > 30 else (0.1, False)
    p = packet()
    p["temperature"] = 31
    gateway.ingest(p)
    assert gateway.snapshot()["latest"]["values"]["anomaly"]
    assert gateway.snapshot()["events"][0]["kind"] == "ai_anomaly_raised"


def test_http_control_journal_and_cross_origin(setup):
    gateway, _ = setup
    gateway.ingest(packet())
    server = make_server(gateway, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        assert b"SmartRoom" in urllib.request.urlopen(base).read()
        state = json.load(urllib.request.urlopen(base + "/api/state"))
        assert not state["stale"]
        request = urllib.request.Request(
            base + "/api/command", data=b'{"value":true}', headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request) as response:
            assert response.status == 202
        request.add_header("Origin", "https://untrusted.invalid")
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request)
        assert error.value.code == 403
        assert b"command_pending" in urllib.request.urlopen(base + "/api/events.csv").read()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
