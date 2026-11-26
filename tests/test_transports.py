"""Exercise wire formats and retry behavior without pretending to test real radio."""

import queue
import threading
from unittest.mock import Mock

import pytest

from gateway.core import Gateway
from gateway.transports import CoreIOT, SerialBridge, Simulator


@pytest.fixture
def gateway():
    g = Gateway({"database": ":memory:", "device": "room-node-01", "sample_seconds": 0})
    yield g
    g.close()


def cloud_stub(gateway):
    c = CoreIOT.__new__(CoreIOT)
    c.gateway = gateway
    c.ready = threading.Event()
    c.ready.set()
    c.connect_needed = threading.Event()
    c.rpc_scope = "test-session"
    c.incoming = queue.Queue()
    c.publish = Mock(return_value=True)
    return c


def test_coreiot_rpc_wire_format_and_physical_ack(gateway):
    cloud = cloud_stub(gateway)
    cloud.incoming.put({"device": "room-node-01", "data": {"id": 14, "method": "setFan", "params": True}})
    cloud.poll()
    command = gateway.snapshot()["commands"][0]
    assert command["status"] == "pending"
    assert not cloud.publish.called  # No success before physical ACK.
    gateway.ack(command["id"], True)
    cloud.poll()
    topic, payload = cloud.publish.call_args.args
    assert topic == "v1/gateway/rpc" and payload["id"] == 14 and payload["data"]["success"] is True


def test_cloud_reconnect_registers_child_before_telemetry(gateway):
    cloud = cloud_stub(gateway)
    cloud.ready.clear()
    cloud.connect_needed.set()
    gateway.ingest(dict(device="room-node-01", boot=1, seq=1, temperature=27, humidity=60, fan=False))
    cloud.poll()
    assert cloud.publish.call_args_list[0].args == (
        "v1/gateway/connect",
        {"device": "room-node-01", "type": "SmartRoom"},
    )
    assert cloud.publish.call_args_list[1].args[0] == "v1/gateway/telemetry"


@pytest.mark.parametrize("value", [False, True])
def test_rpc_id_reused_after_reconnect_is_a_new_command(gateway, value):
    # Reproduce the persisted RPCs from an earlier run, including a matching
    # value which used to return old success without applying the new request.
    old = gateway.command("room-node-01", True, rpc_id=0)
    assert gateway.ack(old["id"], True)
    gateway.flush(lambda *_: True)
    cloud = cloud_stub(gateway)
    client = Mock()
    cloud._on_connect(client, None, None, 0, None)
    first_scope = cloud.rpc_scope
    body = {"device": "room-node-01", "data": {"id": 0, "method": "setFan", "params": value}}
    cloud.incoming.put(body)
    cloud.poll()
    current = gateway.snapshot()["commands"][0]
    assert current["id"] > old["id"]
    assert current["status"] == "pending"
    assert bool(current["value"]) is value
    cloud.incoming.put(body)
    cloud.poll()
    assert gateway.snapshot()["commands"][0]["id"] == current["id"]
    assert gateway.ack(current["id"], value)
    cloud.poll()
    assert cloud.publish.call_args.args[1]["id"] == 0
    assert cloud.publish.call_args.args[1]["data"]["fan"] is value
    cloud._on_connect(client, None, None, 0, None)
    assert cloud.rpc_scope != first_scope
    cloud.incoming.put(body)
    cloud.poll()
    assert gateway.snapshot()["commands"][0]["id"] > current["id"]


@pytest.mark.parametrize("params", ["true", 1, {}, None])
def test_invalid_rpc_replies_failure(gateway, params):
    cloud = cloud_stub(gateway)
    cloud.incoming.put({"device": "room-node-01", "data": {"id": 3, "method": "setFan", "params": params}})
    cloud.poll()
    assert cloud.publish.call_args.args[1]["data"]["success"] is False
    assert not gateway.snapshot()["commands"]


def test_serial_fragmentation_bad_records_and_local_command(gateway):
    bridge = SerialBridge(gateway)
    chunks = iter(
        [
            b'# boot\n[]\n{"type":"tele',
            b'metry","device":"room-node-01","boot":1,"seq":1,"temperature":27,"humidity":60,"fan":false}\n',
            b'{"type":"local_command","value":true}\n',
        ]
    )
    port = Mock()
    port.read.side_effect = lambda _: next(chunks)
    bridge.port = port
    bridge.poll()
    assert gateway.snapshot()["latest"] is None
    bridge.poll()
    assert gateway.snapshot()["latest"]["seq"] == 1
    bridge.poll()
    assert gateway.snapshot()["commands"][0]["value"] == 1


def test_simulation_uses_normal_telemetry_path(gateway):
    sim = Simulator(gateway)
    sim.poll()
    assert gateway.snapshot()["latest"]["values"]["data_source"] == "simulation"
