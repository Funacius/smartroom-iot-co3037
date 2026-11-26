"""Check local switch and incoming CoreIOT RPC in Chrome, with simulated I/O.

Uses an isolated in-memory gateway; does not connect to or alter cloud devices.
Run from the repository root: python scripts/check_fan_sync.py
"""

import json
import queue
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gateway.core import Gateway  # noqa: E402
from gateway.server import make_server  # noqa: E402
from gateway.transports import CoreIOT, Simulator  # noqa: E402


def main():
    gateway = Gateway({"database": ":memory:", "device": "room-node-01",
                       "sample_seconds": 0.2, "stale_seconds": 1})
    simulator = Simulator(gateway)
    gateway.send_command = simulator.send
    cloud = CoreIOT.__new__(CoreIOT)
    cloud.gateway = gateway
    cloud.ready = threading.Event()
    cloud.ready.set()
    cloud.connect_needed = threading.Event()
    cloud.incoming = queue.Queue()
    cloud.rpc_scope = "browser-integration"
    cloud.publish = Mock(return_value=True)
    stop, paused = threading.Event(), threading.Event()
    errors, local_posts = [], []

    def poll():
        while not stop.is_set():
            if not paused.is_set():
                simulator.poll()
            gateway.tick()
            cloud.poll()
            stop.wait(0.01)

    server = make_server(gateway, port=0)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    worker = threading.Thread(target=poll, daemon=True)
    server_thread.start()
    worker.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 1100})
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.on("request", lambda r: local_posts.append(r.post_data)
                        if r.method == "POST" and r.url.endswith("/api/command") else None)
                page.goto(f"http://127.0.0.1:{server.server_port}", wait_until="networkidle")
                switch = page.get_by_role("switch", name="Bật/tắt quạt")
                expect(switch).to_be_enabled()
                expect(switch).not_to_be_checked()
                switch.check()
                expect(page.locator("#fan")).to_have_text("Đang bật")
                expect(page.locator("#commandStatus")).to_contain_text("node đã xác nhận")
                assert len(local_posts) == 1

                # Exercise the MQTT callback and normal command/ACK path, then
                # verify polling updates the switch without sending a local POST.
                for rpc_id, value in ((1, False), (2, True)):
                    body = {"device": "room-node-01",
                            "data": {"id": rpc_id, "method": "setFan", "params": value}}
                    cloud._on_message(None, None, SimpleNamespace(payload=json.dumps(body).encode()))
                    expect(page.locator("#fan")).to_have_text("Đang bật" if value else "Đang tắt")
                    if value:
                        expect(switch).to_be_checked()
                    else:
                        expect(switch).not_to_be_checked()
                    assert len(local_posts) == 1, "External updates must not echo back as new commands"
                    with gateway.lock:
                        current = gateway.snapshot()["commands"][0]
                    assert current["status"] == "applied"
                    assert current["rpc_id"] == str(rpc_id)

                # The control remains keyboard accessible.
                expect(switch).to_be_enabled()
                switch.focus()
                page.keyboard.press("Space")
                expect(page.locator("#fan")).to_have_text("Đang tắt")
                assert len(local_posts) == 2
                output = ROOT / "evidence"
                output.mkdir(exist_ok=True)
                page.screenshot(path=str(output / "fan_switch_desktop.png"))
                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=str(output / "fan_switch_mobile.png"), full_page=True)
                paused.set()
                expect(switch).to_be_disabled()
                expect(page.locator("#fanSwitchLabel")).to_have_text("Chưa có dữ liệu mới")
                assert not errors, errors
                result = {"scope": "Chrome + isolated in-memory gateway; simulated sensor/MQTT, no live cloud",
                          "local_switch_on_off": "PASS", "incoming_rpc_updates_switch": "PASS",
                          "no_command_echo": "PASS", "keyboard_control": "PASS",
                          "stale_disables_switch": "PASS", "mobile_overflow": False,
                          "console_errors": errors}
                (output / "fan_sync_check.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
                print(json.dumps(result))
            finally:
                browser.close()
    finally:
        stop.set()
        worker.join(timeout=3)
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=3)
        gateway.close()


if __name__ == "__main__":
    main()
