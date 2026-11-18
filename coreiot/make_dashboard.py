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
        widget["config"]["settings"]["thresholds"] = []
    if widget["type"] == "alarm":
        widget["config"]["title"] = "SmartRoom alarms"
        if "alarmSource" in widget["config"]:
            widget["config"]["alarmSource"]["entityAliasId"] = alias
config["widgets"] = widgets
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
