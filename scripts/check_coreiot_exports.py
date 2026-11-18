"""Read-only checks of the user's real CoreIOT exports and screenshots."""

import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evidence/coreiot"


def main():
    checks = []

    def check(name, condition):
        checks.append({"check": name, "pass": bool(condition)})

    dashboard = json.loads((SOURCE / "smartroom_co3037.json").read_text(encoding="utf-8-sig"))
    root = json.loads((SOURCE / "root_rule_chain.json").read_text(encoding="utf-8-sig"))
    child = json.loads((SOURCE / "smartroom_alarms.json").read_text(encoding="utf-8-sig"))
    cfg = dashboard["configuration"]
    widgets = cfg["widgets"]
    aliases = cfg["entityAliases"]
    switches = [w for w in widgets.values() if w.get("typeFullFqn") == "system.single_switch"]
    check("One Single Switch and four widgets", len(switches) == 1 and len(widgets) == 4)
    settings = switches[0]["config"]["settings"]
    check(
        "Switch reads fan telemetry",
        settings["initialState"]["action"] == "GET_TIME_SERIES"
        and settings["initialState"]["getTimeSeries"]["key"] == "fan",
    )
    for action, value in [("onUpdateState", True), ("offUpdateState", False)]:
        action_config = settings[action]
        parameter = action_config["valueToData"].get("constantValue")
        check(
            action + " sends setFan with a boolean",
            action_config["action"] == "EXECUTE_RPC"
            and action_config["executeRpc"]["method"] == "setFan"
            and type(parameter) is bool
            and parameter == value,
        )
    charts = [w for w in widgets.values() if w["type"] == "timeseries"]
    for chart in charts:
        config = chart["config"]
        key = config["datasources"][0]["dataKeys"][0]
        axis_id = key["settings"].get("yAxisId", "default")
        expected_unit = "%" if key["name"] == "humidity" else "°C"
        check(
            key["name"] + " axis matches data unit",
            key["units"] == expected_unit and config["settings"]["yAxes"][axis_id]["units"] == expected_unit,
        )
        check(
            key["name"] + " alias resolves to room-node-01",
            aliases[config["datasources"][0]["entityAliasId"]]["filter"].get("entityNameFilter")
            == "room-node-01",
        )
    for state in cfg["states"].values():
        for layout in state["layouts"].values():
            check("Layout references existing widgets", set(layout["widgets"]).issubset(widgets))

    def index_of(chain, suffix):
        return next(i for i, n in enumerate(chain["metadata"]["nodes"]) if n["type"].endswith(suffix))

    def linked(chain, source, target, relation):
        return {"fromIndex": source, "toIndex": target, "type": relation} in chain["metadata"]["connections"]

    for label, chain in [("root", root), ("alarms", child)]:
        nodes = chain["metadata"]["nodes"]
        check(
            label + " graph indices are valid",
            0 <= chain["metadata"]["firstNodeIndex"] < len(nodes)
            and all(
                0 <= c["fromIndex"] < len(nodes) and 0 <= c["toIndex"] < len(nodes)
                for c in chain["metadata"]["connections"]
            ),
        )
    root_switch = index_of(root, "TbMsgTypeSwitchNode")
    device_filter = index_of(root, "TbJsFilterNode")
    save = index_of(root, "TbMsgTimeseriesNode")
    child_call = index_of(root, "TbRuleChainInputNode")
    rpc = index_of(root, "TbSendRPCRequestNode")
    check(
        "Root Post telemetry enters SmartRoom filter",
        linked(root, root_switch, device_filter, "Post telemetry"),
    )
    check("True routes to alarm chain", linked(root, device_filter, child_call, "True"))
    check("False keeps other devices saving telemetry", linked(root, device_filter, save, "False"))
    check("RPC Request to Device route is preserved", linked(root, root_switch, rpc, "RPC Request to Device"))
    check("No duplicate direct telemetry save route", not linked(root, root_switch, save, "Post telemetry"))
    check(
        "Child chain links save, high filter, create and clear",
        all(
            linked(child, a, b, kind)
            for a, b, kind in [
                (0, 1, "Post telemetry"),
                (1, 2, "Success"),
                (2, 3, "True"),
                (2, 4, "False"),
                (4, 5, "True"),
            ]
        ),
    )
    nodes = child["metadata"]["nodes"]
    create = nodes[index_of(child, "TbCreateAlarmNode")]["configuration"]
    clear = nodes[index_of(child, "TbClearAlarmNode")]["configuration"]
    check(
        "Create and clear use same alarm type",
        create["alarmType"] == clear["alarmType"] == "SmartRoom Environment",
    )
    check("Alarm severity is Major", create["severity"] == "MAJOR")

    high_script = nodes[2]["configuration"]["jsScript"]
    clear_script = nodes[4]["configuration"]["jsScript"]
    filter_script = root["metadata"]["nodes"][device_filter]["configuration"]["jsScript"]
    cases = []
    for name, msg, high, recovered in [
        ("normal", {"temperature": 27, "humidity": 60, "anomaly": False}, False, True),
        ("hot", {"temperature": 35, "humidity": 60, "anomaly": False}, True, False),
        ("humid", {"temperature": 27, "humidity": 85, "anomaly": False}, True, False),
        ("AI anomaly", {"temperature": 27, "humidity": 60, "anomaly": True}, True, False),
        ("hysteresis band", {"temperature": 31, "humidity": 78, "anomaly": False}, False, False),
        ("high boundary", {"temperature": 32, "humidity": 60, "anomaly": False}, True, False),
        ("clear boundary", {"temperature": 30, "humidity": 75, "anomaly": False}, False, True),
    ]:
        cases.append({"name": name + " high", "script": high_script, "msg": msg, "expected": high})
        cases.append({"name": name + " clear", "script": clear_script, "msg": msg, "expected": recovered})
    for name in ("room-node-01", "another-device"):
        cases.append(
            {
                "name": "device filter " + name,
                "script": filter_script,
                "metadata": {"deviceName": name},
                "expected": name == "room-node-01",
            }
        )
    # The checked exports contain the group's short JavaScript filters; run them
    # with representative telemetry in isolated contexts and a bounded timeout.
    runner = """const fs=require('fs'),vm=require('vm');
const cases=JSON.parse(fs.readFileSync(0,'utf8'));
const result=cases.map(c=>({name:c.name,expected:c.expected,
 actual:vm.runInNewContext('(function(){'+c.script+'})()',
 {msg:c.msg||{},metadata:c.metadata||{}},{timeout:1000})}));
process.stdout.write(JSON.stringify(result));"""
    run = subprocess.run(
        ["node", "-e", runner],
        input=json.dumps(cases),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=True,
    )
    scenarios = json.loads(run.stdout)
    for scenario in scenarios:
        check(scenario["name"], scenario["actual"] is scenario["expected"])
    findings = []
    for chart in charts:
        config = chart["config"]
        timewindow = cfg["timewindow"] if config.get("useDashboardTimewindow") else config["timewindow"]
        if timewindow["aggregation"]["type"] == "AVG":
            findings.append(
                {
                    "severity": "display_issue",
                    "chart": config["title"],
                    "aggregation": "AVG",
                    "interval_ms": timewindow["realtime"]["interval"],
                    "window_ms": timewindow["realtime"]["timewindowMs"],
                    "recommendation": "Use None aggregation to show raw transient peaks; optionally share dashboard time window",
                }
            )
    import pymupdf

    files = []
    for path in sorted(SOURCE.iterdir()):
        if path.suffix.lower() not in (".png", ".json"):
            continue
        record = {
            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        if path.suffix.lower() == ".png":
            image = pymupdf.Pixmap(str(path))
            record["pixels"] = [image.width, image.height]
        files.append(record)
    result = {
        "scope": "User-provided cloud exports/screenshots; sensor data is simulated; no account mutation",
        "passed": sum(c["pass"] for c in checks),
        "failed": sum(not c["pass"] for c in checks),
        "checks": checks,
        "script_scenarios": scenarios,
        "findings": findings,
        "source_files": files,
        "notes": [
            "Dashboard export omits its runtime ID; current dashboard URL is not derived from its title.",
            "Root export has root=false; this flag alone does not establish which runtime chain is active.",
            "The root child-chain reference contains a server-specific ID; preserve original exports.",
        ],
    }
    (ROOT / "evidence/coreiot_export_check.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"CoreIOT export checks: {result['passed']} PASS, {result['failed']} FAIL; {len(findings)} display findings"
    )
    return bool(result["failed"])


if __name__ == "__main__":
    raise SystemExit(main())
