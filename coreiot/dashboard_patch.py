"""Change the fan control on an existing dashboard without changing its identity."""

import copy

DEFAULT_DASHBOARD_ID = "0ca724e0-e352-11f1-8cd8-29dc599bec29"
DEFAULT_DASHBOARD_URL = "https://app.coreiot.io/dashboards/all/" + DEFAULT_DASHBOARD_ID
SWITCH_FQN = "system.control_widgets.switch_control"
FAN_TYPES = {
    "system.control_widgets.rpcbutton",
    SWITCH_FQN,
    "system.control_widgets.slide_toggle_control",
}


def entity_id(value):
    return value.get("id") if isinstance(value, dict) else value


def is_fan_control(widget):
    settings = widget.get("config", {}).get("settings", {})
    return widget.get("typeFullFqn") in FAN_TYPES and (
        settings.get("methodName") == "setFan" or settings.get("setValueMethod") == "setFan"
    )


def patch_fan_switch(dashboard, expected_id):
    if entity_id(dashboard.get("id")) != expected_id:
        raise ValueError("Dashboard ID does not match the requested dashboard; refusing to save")
    patched = copy.deepcopy(dashboard)
    config = patched["configuration"]
    widgets = config["widgets"]
    candidates = [(wid, widget) for wid, widget in widgets.items() if is_fan_control(widget)]
    if not candidates:
        raise ValueError("No existing setFan control found; open the dashboard with the working fan buttons")
    # Reuse a switch if present so repeated updates keep the same widget ID.
    primary_id, primary = next(
        ((wid, w) for wid, w in candidates if w["typeFullFqn"] == SWITCH_FQN), candidates[0]
    )
    target = primary["config"].get("targetDevice")
    if not target or not (target.get("deviceId") or target.get("entityAliasId")):
        raise ValueError("The existing fan control has no target device; configure its target first")
    # Other devices' controls must remain intact even if they use setFan too.
    related = {wid for wid, w in candidates if w["config"].get("targetDevice") == target}
    removed = related - {primary_id}
    switch = copy.deepcopy(primary)
    for key in ("typeId", "bundleAlias", "typeAlias", "isSystemType"):
        switch.pop(key, None)
    switch.update(typeFullFqn=SWITCH_FQN, type="rpc")
    switch["config"] = {
        "title": "Quạt phòng học",
        "showTitle": False,
        "backgroundColor": "#ffffff",
        "color": "#163433",
        "padding": "8px",
        "dropShadow": True,
        "targetDevice": copy.deepcopy(target),
        "settings": {
            "title": "Quạt phòng học",
            "initialValue": False,
            "showOnOffLabels": True,
            "retrieveValueMethod": "timeseries",
            "valueKey": "fan",
            "getValueMethod": "getFan",
            "setValueMethod": "setFan",
            "parseValueFunction": 'return data === true || data === "true" || data === 1;',
            "convertValueFunction": "return value === true;",
            "requestTimeout": 10000,
            "requestPersistent": False,
        },
        "actions": {},
    }
    widgets[primary_id] = switch
    for wid in removed:
        del widgets[wid]
    layout_found = False
    for state in config.get("states", {}).values():
        for layout in state.get("layouts", {}).values():
            placements = layout.get("widgets", {})
            old = [copy.deepcopy(placements[wid]) for wid in related if wid in placements]
            for wid in removed:
                placements.pop(wid, None)
            if primary_id not in placements:
                # Preserve a state which displayed only the second old button.
                if old:
                    placements[primary_id] = old[0]
                else:
                    continue
            layout_found = True
            if len(old) > 1 and len({p.get("row", 0) for p in old}) == 1:
                left = min(p.get("col", 0) for p in old)
                right = max(p.get("col", 0) + p["sizeX"] for p in old)
                row = old[0].get("row", 0)
                height = max(p["sizeY"] for p in old)
                overlaps = any(
                    wid != primary_id
                    and p.get("col", 0) < right
                    and p.get("col", 0) + p["sizeX"] > left
                    and p.get("row", 0) < row + height
                    and p.get("row", 0) + p["sizeY"] > row
                    for wid, p in placements.items()
                )
                if not overlaps:
                    placements[primary_id].update(col=left, sizeX=right - left, row=row, sizeY=height)
    if not layout_found:
        raise ValueError("The fan control is not present in a dashboard layout")
    # Correct the inherited axis unit without resetting chart styling or time windows.
    for widget in widgets.values():
        if widget.get("type") != "timeseries":
            continue
        cfg = widget["config"]
        keys = [key for ds in cfg.get("datasources", []) for key in ds.get("dataKeys", [])]
        if keys and all(key.get("name") == "humidity" for key in keys):
            cfg["units"] = "%"
            for key in keys:
                key["units"] = "%"
            cfg["settings"].setdefault("yAxis", {})["units"] = "%"
            for axis in cfg["settings"].get("yAxes", {}).values():
                axis["units"] = "%"
    plan = {
        "dashboard_id": expected_id,
        "title": dashboard.get("title"),
        "switch_widget_id": primary_id,
        "removed_button_ids": sorted(removed),
        "state_source": "fan telemetry",
        "changed": patched != dashboard,
    }
    return patched, plan
