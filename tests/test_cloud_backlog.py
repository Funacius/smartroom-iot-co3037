from gateway.core import Gateway


def test_rpc_reply_is_not_delayed_by_telemetry_backlog():
    g = Gateway({"database": ":memory:", "device": "room-node-01"})
    try:
        for seq in range(1, 20):
            g.ingest(dict(device="room-node-01", boot=1, seq=seq, temperature=27, humidity=60, fan=False))
        command = g.command("room-node-01", True, rpc_id=99)
        assert g.ack(command["id"], True)
        sent = []
        g.flush(lambda topic, body: sent.append((topic, body)) or True, limit=1)
        assert sent[0][0] == "v1/gateway/rpc"
        assert sent[0][1]["id"] == 99
        assert g.snapshot()["outbox_count"] == 19
    finally:
        g.close()
