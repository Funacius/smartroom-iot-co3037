import copy
import io
import json
import os
from pathlib import Path
import urllib.error
from unittest.mock import Mock

import pytest

from coreiot.dashboard_patch import DEFAULT_DASHBOARD_ID, SWITCH_FQN, patch_fan_switch
from scripts import update_coreiot_dashboard as updater


@pytest.fixture
def dashboard():
    value = json.loads(Path("coreiot/smartroom_dashboard_rpc.json").read_text(encoding="utf-8"))
    value["id"] = {"entityType": "DASHBOARD", "id": DEFAULT_DASHBOARD_ID}
    value["tenantId"] = {"entityType": "TENANT", "id": "test-tenant"}
    value["title"] = "User's existing dashboard"
    value["configuration"]["settings"]["customUserSetting"] = "preserve me"
    return value


def test_update_preserves_identity_charts_alarm_and_user_settings(dashboard):
    before = copy.deepcopy(dashboard)
    updated, plan = patch_fan_switch(dashboard, DEFAULT_DASHBOARD_ID)
    assert dashboard == before
    assert updated["id"] == before["id"]
    assert updated["title"] == before["title"]
    assert updated["tenantId"] == before["tenantId"]
    assert updated["configuration"]["settings"] == before["configuration"]["settings"]
    widgets = updated["configuration"]["widgets"]
    assert len(widgets) == 4
    for wid, widget in before["configuration"]["widgets"].items():
        if widget["type"] in ("timeseries", "alarm"):
            assert widgets[wid] == widget
    switch = widgets[plan["switch_widget_id"]]
    assert switch["typeFullFqn"] == SWITCH_FQN
    assert switch["config"]["settings"]["retrieveValueMethod"] == "timeseries"
    assert switch["config"]["settings"]["valueKey"] == "fan"


def test_repeated_update_does_not_add_widgets_or_change_ids(dashboard):
    first, _ = patch_fan_switch(dashboard, DEFAULT_DASHBOARD_ID)
    second, plan = patch_fan_switch(first, DEFAULT_DASHBOARD_ID)
    assert first == second
    assert plan["changed"] is False
    assert plan["removed_button_ids"] == []


def test_all_states_keep_valid_widget_references(dashboard):
    state = copy.deepcopy(dashboard["configuration"]["states"]["default"])
    ids = [wid for wid, w in dashboard["configuration"]["widgets"].items() if w["type"] == "rpc"]
    state["layouts"]["main"]["widgets"].pop(ids[0])
    dashboard["configuration"]["states"]["secondary"] = state
    updated, _ = patch_fan_switch(dashboard, DEFAULT_DASHBOARD_ID)
    for state in updated["configuration"]["states"].values():
        for layout in state["layouts"].values():
            assert set(layout["widgets"]).issubset(updated["configuration"]["widgets"])


def test_other_devices_fan_control_is_untouched(dashboard):
    widgets = dashboard["configuration"]["widgets"]
    foreign = copy.deepcopy(next(w for w in widgets.values() if w["type"] == "rpc"))
    foreign["config"]["targetDevice"] = {"type": "device", "deviceId": "another-device"}
    widgets["foreign-widget"] = foreign
    updated, _ = patch_fan_switch(dashboard, DEFAULT_DASHBOARD_ID)
    assert updated["configuration"]["widgets"]["foreign-widget"] == foreign


def test_humidity_axis_fix_does_not_change_temperature(dashboard):
    original_temperature = None
    for widget in dashboard["configuration"]["widgets"].values():
        if widget["type"] == "timeseries":
            key = widget["config"]["datasources"][0]["dataKeys"][0]["name"]
            if key == "humidity":
                widget["config"]["settings"]["yAxes"]["default"]["units"] = "°C"
            else:
                original_temperature = copy.deepcopy(widget)
    updated, _ = patch_fan_switch(dashboard, DEFAULT_DASHBOARD_ID)
    for widget in updated["configuration"]["widgets"].values():
        if widget["type"] == "timeseries":
            key = widget["config"]["datasources"][0]["dataKeys"][0]["name"]
            if key == "humidity":
                assert widget["config"]["settings"]["yAxes"]["default"]["units"] == "%"
            else:
                assert widget == original_temperature


def test_wrong_dashboard_is_rejected_before_mutation(dashboard):
    with pytest.raises(ValueError, match="ID does not match"):
        patch_fan_switch(dashboard, "wrong-id")


def test_no_existing_fan_control_does_not_create_a_new_one(dashboard):
    dashboard["configuration"]["widgets"] = {
        wid: w for wid, w in dashboard["configuration"]["widgets"].items() if w["type"] != "rpc"
    }
    with pytest.raises(ValueError, match="No existing setFan"):
        patch_fan_switch(dashboard, DEFAULT_DASHBOARD_ID)


def test_api_update_saves_same_id_backups_and_is_idempotent(dashboard, monkeypatch, tmp_path):
    state = copy.deepcopy(dashboard)
    writes = []

    def api(path, token=None, data=None):
        nonlocal state
        if data is not None:
            assert path == "/api/dashboard"
            assert data["id"] == dashboard["id"]
            writes.append(copy.deepcopy(data))
            state = copy.deepcopy(data)
        else:
            assert path == "/api/dashboard/" + DEFAULT_DASHBOARD_ID
        return copy.deepcopy(state)

    monkeypatch.setattr(updater, "ROOT", tmp_path)
    monkeypatch.setattr(updater, "request", api)
    result = updater.update_dashboard("synthetic-token-only", DEFAULT_DASHBOARD_ID, apply=True)
    assert result["verified"]
    backup = tmp_path / result["backup"]
    assert json.loads(backup.read_text(encoding="utf-8")) == dashboard
    assert "synthetic-token-only" not in backup.read_text(encoding="utf-8")
    updater.update_dashboard("synthetic-token-only", DEFAULT_DASHBOARD_ID, apply=True)
    assert len(writes) == 1


def test_preview_never_sends_post(dashboard, monkeypatch, tmp_path):
    api = Mock(return_value=copy.deepcopy(dashboard))
    monkeypatch.setattr(updater, "ROOT", tmp_path)
    monkeypatch.setattr(updater, "request", api)
    updater.update_dashboard("synthetic-token-only", DEFAULT_DASHBOARD_ID, apply=False)
    assert api.call_count == 1
    assert list((tmp_path / "runtime/coreiot-backups").glob("*.preview.json"))


def test_concurrent_change_stops_save(dashboard, monkeypatch, tmp_path):
    changed = copy.deepcopy(dashboard)
    changed["title"] = "Someone else saved this"
    api = Mock(side_effect=[copy.deepcopy(dashboard), changed])
    monkeypatch.setattr(updater, "ROOT", tmp_path)
    monkeypatch.setattr(updater, "request", api)
    with pytest.raises(RuntimeError, match="changed during preparation"):
        updater.update_dashboard("synthetic-token-only", DEFAULT_DASHBOARD_ID, apply=True)
    assert api.call_count == 2


def test_noninteractive_without_session_does_not_request_credentials(monkeypatch, tmp_path):
    monkeypatch.setattr(updater, "CACHE", tmp_path / "missing.dpapi")
    prompt = Mock(side_effect=AssertionError("Must not prompt"))
    monkeypatch.setattr(updater.getpass, "getpass", prompt)
    with pytest.raises(RuntimeError, match="No usable saved session"):
        updater.authenticate(non_interactive=True)
    assert not prompt.called


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI")
def test_remembered_session_is_encrypted_and_roundtrips():
    value = b"synthetic-test-token-not-a-real-credential"
    encrypted = updater.dpapi(value)
    assert value not in encrypted
    assert updater.dpapi(encrypted, decrypt=True) == value


def test_http_auth_error_does_not_expose_credentials(monkeypatch):
    opener = Mock()
    opener.open.side_effect = urllib.error.HTTPError(
        updater.HOST + "/api/auth/login", 401, "denied", {}, io.BytesIO(b"synthetic-sensitive-response")
    )
    monkeypatch.setattr(updater.urllib.request, "build_opener", lambda *args: opener)
    with pytest.raises(updater.APIError) as error:
        updater.request("/api/auth/login", data={"username": "test@example.invalid", "password": "synthetic"})
    assert "synthetic" not in str(error.value)
    assert error.value.status == 401
