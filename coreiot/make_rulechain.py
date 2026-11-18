"""Generate portable rule-chain import; verify on the class CoreIOT version."""

import json
from pathlib import Path

root = Path(__file__).resolve().parent
nodes = []


def node(kind, name, config, x, y):
    nodes.append(
        {
            "type": "org.thingsboard.rule.engine." + kind,
            "name": name,
            "debugMode": False,
            "configuration": config,
            "additionalInfo": {"layoutX": x, "layoutY": y},
        }
    )


node("filter.TbMsgTypeSwitchNode", "Telemetry only", {"version": 0}, 100, 150)
node("telemetry.TbMsgTimeseriesNode", "Save timeseries", {"defaultTTL": 0}, 350, 150)
node(
    "filter.TbJsFilterNode",
    "High or anomaly",
    {"scriptLang": "JS", "jsScript": (root / "rulechain/smartroom_filter.js").read_text()},
    600,
    150,
)
details = {
    "alarmType": "SmartRoom Environment",
    "scriptLang": "JS",
    "alarmDetailsBuildJs": "return {temperature: msg.temperature, humidity: msg.humidity, anomaly: msg.anomaly, data_source: msg.data_source};",
}
node(
    "action.TbCreateAlarmNode",
    "Create SmartRoom alarm",
    dict(
        details,
        severity="MAJOR",
        propagate=False,
        propagateToOwner=False,
        propagateToOwnerHierarchy=False,
        propagateToTenant=False,
        useMessageAlarmData=False,
        overwriteAlarmDetails=True,
        dynamicSeverity=False,
        relationTypes=[],
    ),
    900,
    70,
)
node(
    "filter.TbJsFilterNode",
    "Recovered below clear limits",
    {"scriptLang": "JS", "jsScript": (root / "rulechain/smartroom_clear.js").read_text()},
    900,
    240,
)
node("action.TbClearAlarmNode", "Clear SmartRoom alarm", details, 1200, 240)
edges = [(0, 1, "Post telemetry"), (1, 2, "Success"), (2, 3, "True"), (2, 4, "False"), (4, 5, "True")]
result = {
    "ruleChain": {
        "name": "SmartRoom alarms",
        "root": False,
        "debugMode": False,
        "firstRuleNodeId": None,
        "configuration": None,
        "additionalInfo": {
            "description": "SmartRoom threshold/AI alarm with recovery hysteresis. Configure notifications separately."
        },
    },
    "metadata": {
        "firstNodeIndex": 0,
        "nodes": nodes,
        "connections": [{"fromIndex": a, "toIndex": b, "type": label} for a, b, label in edges],
        "ruleChainConnections": None,
    },
}
(root / "smartroom_rulechain.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(root / "smartroom_rulechain.json")
