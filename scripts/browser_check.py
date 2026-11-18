"""Optional: browser integration check with installed Chrome (pip install playwright)."""

import json
from pathlib import Path
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parents[1]
errors = []
with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1160}, device_scale_factor=1)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("http://127.0.0.1:8080", wait_until="networkidle")
    page.wait_for_function("document.querySelector('#temperature').textContent.includes('°C')")
    with page.expect_response(lambda r: r.url.endswith("/api/command")) as created:
        page.get_by_role("button", name="Bật quạt").click()
    command_id = created.value.json()["id"]
    page.wait_for_function(
        "id => {const text=document.querySelector('#commandStatus').textContent; return text.startsWith('Lệnh #'+id+':') && text.includes('node đã xác nhận')}",
        arg=command_id,
        timeout=8000,
    )
    response = page.request.get("http://127.0.0.1:8080/api/state")
    state = response.json()
    assert state["commands"][0]["status"] == "applied"
    assert state["commands"][0]["value"] == 1
    page.screenshot(path=str(root / "evidence/dashboard_desktop.png"), full_page=False)
    page.set_viewport_size({"width": 390, "height": 844})
    page.screenshot(path=str(root / "evidence/dashboard_mobile.png"), full_page=False)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    with page.expect_response(lambda r: r.url.endswith("/api/command")) as created:
        page.get_by_role("button", name="Tắt quạt").click()
    command_id = created.value.json()["id"]
    page.wait_for_function(
        "id => {const text=document.querySelector('#commandStatus').textContent; return text.startsWith('Lệnh #'+id+':') && text.includes('node đã xác nhận')}",
        arg=command_id,
        timeout=8000,
    )
    assert not errors, errors
    (root / "evidence/browser_check.json").write_text(
        json.dumps(
            {
                "scope": "real Chrome + simulated device; no real ESP32/cloud",
                "desktop": "1440x1160",
                "mobile": "390x844",
                "control_on_off": "PASS",
                "console_errors": errors,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (root / "evidence/demo_state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
    browser.close()
print("Browser checks PASS; screenshots saved to evidence/")
