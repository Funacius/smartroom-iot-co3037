"""Adapters: the simulator uses exactly the gateway's normal ingest/ACK path."""

import json
import logging
import math
import os
import queue
import random
import threading
import time

LOG = logging.getLogger(__name__)


class Simulator:
    def __init__(self, gateway):
        self.gateway = gateway
        self.fan = False
        self.seq = 0
        self.boot = random.Random(time.time_ns()).randint(1, 0xFFFFFFFF)
        self.started = time.monotonic()
        self.next_sample = 0
        self.pending = None
        self.random = random.Random(2353086)

    def send(self, command):
        self.pending = (time.monotonic() + 0.04, command)

    def poll(self):
        now = time.monotonic()
        if self.pending and now >= self.pending[0]:
            command = self.pending[1]
            self.fan = command["value"]
            self.gateway.ack(command["id"], self.fan)
            self.pending = None
        if now < self.next_sample:
            return
        self.next_sample = now + self.gateway.config.get("sample_seconds", 2)
        elapsed = now - self.started
        # A deliberate hot spell and recovery exercise the event journal.
        hot = 20 <= elapsed % 60 < 40
        self.seq += 1
        self.gateway.ingest(
            {
                "device": self.gateway.config["device"],
                "boot": self.boot,
                "seq": self.seq,
                "temperature": 27
                + 0.6 * math.sin(elapsed / 7)
                + (8 if hot else 0)
                + self.random.gauss(0, 0.12),
                "humidity": 60 + self.random.gauss(0, 1.2),
                "fan": self.fan,
                "data_source": "simulation",
            }
        )

    def close(self):
        pass


class SerialBridge:
    def __init__(self, gateway):
        import serial

        self.serial_module = serial
        self.gateway = gateway
        self.port = None
        self.buffer = bytearray()
        self.retry_at = 0

    def _connect(self):
        if self.port is None and time.monotonic() >= self.retry_at:
            try:
                self.port = self.serial_module.Serial(
                    self.gateway.config["serial_port"],
                    self.gateway.config.get("serial_baud", 115200),
                    timeout=0,
                    write_timeout=0.5,
                )
                LOG.info("USB bridge connected")
            except self.serial_module.SerialException:
                self.retry_at = time.monotonic() + 2

    def send(self, command):
        if self.port is None:
            raise OSError("USB bridge disconnected")
        self.port.write((json.dumps(command) + "\n").encode())

    def poll(self):
        self._connect()
        if self.port is None:
            return
        try:
            self.buffer.extend(self.port.read(4096))
            if len(self.buffer) > 16384:
                self.buffer.clear()
                LOG.warning("Serial buffer overflow; discarded corrupt line")
            while b"\n" in self.buffer:
                line, _, self.buffer = self.buffer.partition(b"\n")
                try:
                    packet = json.loads(line)
                    if not isinstance(packet, dict):
                        raise ValueError("Serial JSON must be an object")
                    if packet.get("type") == "telemetry":
                        self.gateway.ingest(packet)
                    elif packet.get("type") == "ack":
                        self.gateway.ack(packet["id"], packet["value"])
                    elif packet.get("type") == "local_command":
                        self.gateway.command(self.gateway.config["device"], packet["value"])
                except (ValueError, KeyError, TypeError):
                    LOG.warning("Ignored malformed serial record")
        except self.serial_module.SerialException:
            self.close()
            self.retry_at = time.monotonic() + 2

    def close(self):
        if self.port:
            self.port.close()
        self.port = None
        self.buffer.clear()


class CoreIOT:
    def __init__(self, gateway):
        import paho.mqtt.client as mqtt

        self.gateway = gateway
        self.ready = threading.Event()
        self.incoming = queue.Queue(maxsize=100)
        self.connect_needed = threading.Event()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        token = os.getenv("COREIOT_TOKEN", "")
        if not token:
            raise ValueError("Set COREIOT_TOKEN to the gateway device access token")
        self.client.username_pw_set(token)
        if gateway.config.get("mqtt_tls", True):
            self.client.tls_set()  # system CA validation; never tls_insecure_set(True)
        self.client.reconnect_delay_set(1, 30)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = lambda *args: self.ready.clear()
        self.client.on_message = self._on_message
        self.client.connect_async(gateway.config["mqtt_host"], gateway.config.get("mqtt_port", 8883), 60)
        self.client.loop_start()

    def _on_connect(self, client, userdata, flags, reason, properties):
        if reason == 0:
            client.subscribe("v1/gateway/rpc", qos=1)
            self.connect_needed.set()

    def _on_message(self, client, userdata, message):
        try:
            self.incoming.put_nowait(json.loads(message.payload))
        except (ValueError, queue.Full):
            LOG.warning("Malformed RPC or queue full")

    def publish(self, topic, payload):
        try:
            info = self.client.publish(topic, json.dumps(payload), qos=1)
            info.wait_for_publish(timeout=1)
            return info.is_published()
        except (ValueError, RuntimeError, OSError):
            return False

    def poll(self):
        if self.connect_needed.is_set():
            if self.publish(
                "v1/gateway/connect", {"device": self.gateway.config["device"], "type": "SmartRoom"}
            ):
                self.connect_needed.clear()
                self.ready.set()
        for _ in range(20):
            try:
                body = self.incoming.get_nowait()
            except queue.Empty:
                break
            try:
                data = body["data"]
                if data["method"] != "setFan":
                    raise ValueError("Supported method: setFan")
                self.gateway.command(body["device"], data["params"], rpc_id=data["id"])
            except (KeyError, TypeError, ValueError) as exc:
                if isinstance(body, dict) and isinstance(body.get("data"), dict) and "id" in body["data"]:
                    with self.gateway.lock, self.gateway.db:
                        self.gateway._queue(
                            "v1/gateway/rpc",
                            {
                                "device": body.get("device", ""),
                                "id": body["data"]["id"],
                                "data": {"success": False, "detail": str(exc)},
                            },
                        )
        # Only one message per poll bounds the cloud delay on device processing.
        if self.ready.is_set():
            self.gateway.flush(self.publish, limit=1)

    def close(self):
        if self.ready.is_set():
            self.publish("v1/gateway/disconnect", {"device": self.gateway.config["device"]})
        self.client.disconnect()
        self.client.loop_stop()
