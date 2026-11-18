"""Adapt official ThingsBoard Thermostats widgets (Apache-2.0) for SmartRoom.

Imports still need verification on the user's CoreIOT version. Never claim that
generating a JSON file deploys or tests a dashboard on CoreIOT.
"""

import copy
import json
from pathlib import Path

root = Path(__file__).resolve().parent
source = json.loads((root / "templates/thermostats.upstream.json").read_text(encoding="utf-8"))
config = source["configuration"]
alias = "12ae98c7-1ea2-52cf-64d5-763e9d993547"
config["entityAliases"] = {
    alias: {
        "id": alias,
        "alias": "SmartRoom sensor",
        # ThingsBoard EntityNameFilter; deviceName is not a valid filter type.
        "filter": {
            "type": "entityName",
            "entityType": "DEVICE",
            "resolveMultiple": False,
            "entityNameFilter": "room-node-01",
        },
    }
}
keep = [
    "eda8a397-0959-690c-405c-11e2c9b2bc7e",
    "ac90f089-197f-b767-82c3-2668844265a2",
    "7943196b-eedb-d422-f9c3-b32d379ad172",
]
widgets = {k: copy.deepcopy(config["widgets"][k]) for k in keep}
for wid in keep:
    widget = widgets[wid]
    widget["config"]["actions"] = {}
    for ds in widget["config"].get("datasources", []):
        ds["entityAliasId"] = alias
        ds["latestDataKeys"] = []
    if widget["type"] == "timeseries":
        cfg = widget["config"]
        cfg["useDashboardTimewindow"] = True
        cfg["settings"]["thresholds"] = []
        key = cfg["datasources"][0]["dataKeys"][0]
        units = "%" if key["name"] == "humidity" else "°C"
        # The upstream humidity axis incorrectly inherits Celsius independently
        # of the data key's percent unit. Set both axis and data-key units.
        cfg["units"] = units
        key["units"] = units
        cfg["settings"]["yAxis"]["units"] = units
        for axis in cfg["settings"].get("yAxes", {}).values():
            axis["units"] = units
    if widget["type"] == "alarm":
        widget["config"]["title"] = "SmartRoom alarms"
        if "alarmSource" in widget["config"]:
            widget["config"]["alarmSource"]["entityAliasId"] = alias
config["widgets"] = widgets
config["timewindow"]["realtime"].update(realtimeType=0, timewindowMs=600000, interval=1000)
config["timewindow"]["aggregation"] = {"type": "NONE", "limit": 1000}
layout = copy.deepcopy(config["states"]["default"]["layouts"]["main"])
layout["widgets"] = {
    keep[0]: {"sizeX": 12, "sizeY": 6, "row": 0, "col": 0},
    keep[1]: {"sizeX": 12, "sizeY": 6, "row": 0, "col": 12},
    keep[2]: {"sizeX": 24, "sizeY": 7, "row": 6, "col": 0},
}
config["states"] = {"default": {"name": "SmartRoom", "root": True, "layouts": {"main": layout}}}
dashboard = {"title": "SmartRoom CO3037", "configuration": config, "image": None, "resources": []}
(root / "smartroom_dashboard.json").write_text(
    json.dumps(dashboard, indent=2, ensure_ascii=False), encoding="utf-8"
)
print(root / "smartroom_dashboard.json")

# An additional dashboard leaves an already imported dashboard intact. These
# widgets reference the built-in RPC Button; no widget controller is copied.
# Schema: ThingsBoard widget.models.ts and system/widget_types/rpc_button.json.
rpc_dashboard = copy.deepcopy(dashboard)
rpc_dashboard["title"] = "SmartRoom CO3037 RPC"
rpc_config = rpc_dashboard["configuration"]
rpc_layout = rpc_config["states"]["default"]["layouts"]["main"]["widgets"]
rpc_layout[keep[2]]["row"] = 8
for suffix, value, column in [("01", True, 0), ("02", False, 12)]:
    wid = "9abff001-2353-4300-b001-0000000000" + suffix
    label = "Bật quạt" if value else "Tắt quạt"
    rpc_config["widgets"][wid] = {
        "typeFullFqn": "system.control_widgets.rpcbutton",
        "type": "rpc",
        "sizeX": 12,
        "sizeY": 2,
        "row": 6,
        "col": column,
        "config": {
            "title": label,
            "showTitle": False,
            "backgroundColor": "#ffffff",
            "color": "#163433",
            "padding": "8px",
            "dropShadow": True,
            "targetDevice": {"type": "entity", "entityAliasId": alias},
            "settings": {
                "methodName": "setFan",
                "methodParams": json.dumps(value),
                "requestTimeout": 10000,
                "oneWayElseTwoWay": False,
                "requestPersistent": False,
                "showError": True,
                "buttonText": label,
                "styleButton": {"isRaised": True, "isPrimary": True},
            },
            "actions": {},
        },
    }
    rpc_layout[wid] = {"sizeX": 12, "sizeY": 2, "row": 6, "col": column}
(root / "smartroom_dashboard_rpc.json").write_text(
    json.dumps(rpc_dashboard, indent=2, ensure_ascii=False), encoding="utf-8"
)
print(root / "smartroom_dashboard_rpc.json")
