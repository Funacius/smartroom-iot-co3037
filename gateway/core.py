"""Keep processing independent of Serial, MQTT and HTTP so it can be measured.

Telemetry -> validation -> duplicate filter -> AI -> durable outbox.
Command -> pending -> physical ACK -> applied (or timeout -> failed).
"""

from __future__ import annotations

import json
import math
import sqlite3
import threading
import time
from pathlib import Path


class Gateway:
    def __init__(self, config, predictor=None, clock=time.time):
        self.config, self.predictor, self.clock = config, predictor, clock
        path = config.get("database", ":memory:")
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.send_command = lambda command: None
        self.db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS readings(
          id INTEGER PRIMARY KEY, device TEXT, boot INTEGER, seq INTEGER,
          received REAL, payload TEXT, UNIQUE(device,boot,seq));
        CREATE TABLE IF NOT EXISTS events(
          id INTEGER PRIMARY KEY, ts REAL, device TEXT, kind TEXT, detail TEXT);
        CREATE TABLE IF NOT EXISTS outbox(
          id INTEGER PRIMARY KEY, topic TEXT, payload TEXT);
        CREATE TABLE IF NOT EXISTS commands(
          id INTEGER PRIMARY KEY AUTOINCREMENT, created REAL, expires REAL,
          device TEXT, value INTEGER, status TEXT, rpc_key TEXT UNIQUE,
          rpc_id TEXT, sent REAL DEFAULT 0, detail TEXT DEFAULT '');
        """)

    def _event(self, kind, detail, device=None):
        self.db.execute(
            "INSERT INTO events(ts,device,kind,detail) VALUES(?,?,?,?)",
            (self.clock(), device or self.config["device"], kind, detail),
        )

    def _queue(self, topic, payload):
        self.db.execute(
            "INSERT INTO outbox(topic,payload) VALUES(?,?)", (topic, json.dumps(payload, allow_nan=False))
        )

    def ingest(self, packet):
        """Reject malformed, stale-sequence and duplicated packets without side effects."""
        device = packet.get("device")
        if device != self.config["device"]:
            raise ValueError("Unknown device")
        for key in ("boot", "seq"):
            if type(packet.get(key)) is not int or not 0 <= packet[key] <= 0xFFFFFFFF:
                raise ValueError(f"Invalid {key}")
        for key, low, high in (("temperature", -40, 85), ("humidity", 0, 100)):
            value = packet.get(key)
            if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"Invalid {key}")
        if type(packet.get("fan")) is not bool:
            raise ValueError("fan must be a boolean")
        with self.lock, self.db:
            last = self.db.execute(
                "SELECT seq FROM readings WHERE device=? AND boot=? ORDER BY id DESC LIMIT 1",
                (device, packet["boot"]),
            ).fetchone()
            if last and packet["seq"] <= last["seq"]:
                return False
            if self.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] >= self.config.get(
                "max_outbox", 100000
            ):
                raise ValueError("Outbox full: restore cloud connection or archive data")
            now = self.clock()
            values = {k: packet[k] for k in ("temperature", "humidity", "fan", "boot", "seq")}
            values["data_source"] = packet.get("data_source", "hardware")
            values["ai_available"] = self.predictor is not None
            if self.predictor:
                started = time.perf_counter()
                score, abnormal = self.predictor(values["temperature"], values["humidity"])
                values.update(
                    anomaly_score=float(score),
                    anomaly=bool(abnormal),
                    inference_ms=(time.perf_counter() - started) * 1000,
                )
            previous = self.db.execute("SELECT payload FROM readings ORDER BY id DESC LIMIT 1").fetchone()
            old = json.loads(previous[0]) if previous else {}
            # Hysteresis: 32/30 C and 80/75 %RH avoid alert chatter.
            high = self.config.get("temperature_high", 32)
            clear = self.config.get("temperature_clear", 30)
            rh_high = self.config.get("humidity_high", 80)
            rh_clear = self.config.get("humidity_clear", 75)
            alarm = values["temperature"] >= high or values["humidity"] >= rh_high
            if old.get("threshold_alarm"):
                alarm = not (values["temperature"] <= clear and values["humidity"] <= rh_clear)
            values["threshold_alarm"] = alarm
            for key, kind in (("threshold_alarm", "threshold"), ("anomaly", "ai_anomaly")):
                if bool(values.get(key)) != bool(old.get(key)):
                    self._event(
                        kind + ("_raised" if values.get(key) else "_cleared"), json.dumps(values), device
                    )
            self.db.execute(
                "INSERT INTO readings(device,boot,seq,received,payload) VALUES(?,?,?,?,?)",
                (device, packet["boot"], packet["seq"], now, json.dumps(values)),
            )
            self._queue("v1/gateway/telemetry", {device: [{"ts": int(now * 1000), "values": values}]})
            return True

    def command(self, device, value, rpc_id=None, rpc_scope=None):
        if device != self.config["device"] or type(value) is not bool:
            raise ValueError("Expected known device and boolean value")
        # Cloud request IDs can be reused by a new transport session. Keep local
        # command IDs persistent, but deduplicate RPCs only within their session.
        identity = [device, rpc_id] if rpc_scope is None else [device, rpc_scope, rpc_id]
        rpc_key = None if rpc_id is None else json.dumps(identity)
        with self.lock, self.db:
            if rpc_key is not None:
                found = self.db.execute("SELECT * FROM commands WHERE rpc_key=?", (rpc_key,)).fetchone()
                if found:
                    if bool(found["value"]) != value:
                        raise ValueError("RPC id reused with different parameters")
                    if found["status"] != "pending":
                        self._rpc_reply(found, found["status"] == "applied", found["detail"])
                    return dict(found)
            # One outstanding command avoids reordered on/off retries.
            if self.db.execute("SELECT 1 FROM commands WHERE status='pending'").fetchone():
                raise ValueError("A command is pending; wait for ACK or timeout")
            now = self.clock()
            cur = self.db.execute(
                """INSERT INTO commands(created,expires,device,value,status,rpc_key,rpc_id)
                VALUES(?,?,?,?,'pending',?,?)""",
                (
                    now,
                    now + self.config.get("command_ttl_seconds", 5),
                    device,
                    int(value),
                    rpc_key,
                    None if rpc_id is None else json.dumps(rpc_id),
                ),
            )
            self._event("command_pending", str(cur.lastrowid), device)
            return dict(self.db.execute("SELECT * FROM commands WHERE id=?", (cur.lastrowid,)).fetchone())

    def _rpc_reply(self, command, success, detail):
        if command["rpc_id"] is not None:
            self._queue(
                "v1/gateway/rpc",
                {
                    "device": command["device"],
                    "id": json.loads(command["rpc_id"]),
                    "data": {"success": success, "fan": bool(command["value"]), "detail": detail},
                },
            )

    def ack(self, command_id, value):
        if type(command_id) is not int or type(value) is not bool:
            return False
        with self.lock, self.db:
            row = self.db.execute("SELECT * FROM commands WHERE id=?", (command_id,)).fetchone()
            if not row or row["status"] != "pending" or bool(row["value"]) != value:
                return False
            if self.clock() >= row["expires"]:
                return False
            self.db.execute(
                "UPDATE commands SET status='applied',detail='Device ACK' WHERE id=?", (command_id,)
            )
            self._event("command_applied", str(command_id))
            self._rpc_reply(row, True, "Device ACK")
            return True

    def tick(self):
        """Retry bounded commands; success is never inferred from merely sending."""
        with self.lock, self.db:
            now = self.clock()
            for row in self.db.execute("SELECT * FROM commands WHERE status='pending'").fetchall():
                if now >= row["expires"]:
                    self.db.execute(
                        "UPDATE commands SET status='failed',detail='ACK timeout' WHERE id=?", (row["id"],)
                    )
                    self._event("command_failed", str(row["id"]))
                    self._rpc_reply(row, False, "ACK timeout; physical state unknown")
                elif now - row["sent"] >= self.config.get("command_retry_seconds", 0.5):
                    self.db.execute("UPDATE commands SET sent=? WHERE id=?", (now, row["id"]))
                    try:
                        self.send_command({"type": "command", "id": row["id"], "value": bool(row["value"])})
                    except (OSError, ValueError) as exc:
                        self._event("serial_write_error", str(exc))

    def snapshot(self):
        with self.lock:
            row = self.db.execute("SELECT * FROM readings ORDER BY id DESC LIMIT 1").fetchone()
            latest = dict(row) if row else None
            if latest:
                latest["values"] = json.loads(latest.pop("payload"))
                latest["age_seconds"] = max(0, self.clock() - latest["received"])
            history = [
                dict(r)
                for r in self.db.execute("SELECT received,payload FROM readings ORDER BY id DESC LIMIT 120")
            ]
            for r in history:
                r["values"] = json.loads(r.pop("payload"))
            return {
                "device": self.config["device"],
                "latest": latest,
                "stale": latest is None or latest["age_seconds"] > self.config.get("stale_seconds", 15),
                "history": list(reversed(history)),
                "events": [
                    dict(r) for r in self.db.execute("SELECT * FROM events ORDER BY id DESC LIMIT 60")
                ],
                "commands": [
                    dict(r) for r in self.db.execute("SELECT * FROM commands ORDER BY id DESC LIMIT 20")
                ],
                "outbox_count": self.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0],
            }

    def flush(self, publish, limit=20):
        """Remove only after transport confirms QoS1 PUBACK. Replay can duplicate."""
        count = 0
        for _ in range(limit):
            with self.lock:
                row = self.db.execute(
                    "SELECT * FROM outbox ORDER BY CASE WHEN topic='v1/gateway/rpc' THEN 0 ELSE 1 END,id LIMIT 1"
                ).fetchone()
            if not row or not publish(row["topic"], json.loads(row["payload"])):
                break
            with self.lock, self.db:
                self.db.execute("DELETE FROM outbox WHERE id=?", (row["id"],))
            count += 1
        return count

    def close(self):
        self.db.close()
