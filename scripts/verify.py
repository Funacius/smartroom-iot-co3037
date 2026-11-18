"""Record actual verification, with optional firmware compilation."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--firmware", action="store_true")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
os.chdir(root)
evidence = root / "evidence"
evidence.mkdir(exist_ok=True)
env = dict(os.environ, PYTHONIOENCODING="utf-8", PLATFORMIO_SETTING_ENABLE_TELEMETRY="no")
commands = {"pytest": [sys.executable, "-m", "pytest", "-q", "--junitxml=evidence/pytest.xml"]}
if args.firmware:
    pio = shutil.which("pio") or shutil.which("platformio")
    if not pio:
        candidate = Path.home() / ".platformio/penv/Scripts/platformio.exe"
        pio = str(candidate) if candidate.exists() else None
    if not pio:
        raise SystemExit("PlatformIO not found; install platformio==6.2.0")
    commands["firmware_build"] = [pio, "run", "-d", "firmware"]
results = {}
for name, command in commands.items():
    run = subprocess.run(command, env=env, capture_output=True, encoding="utf-8", errors="replace")
    (evidence / f"{name}.log").write_text(run.stdout + run.stderr, encoding="utf-8")
    results[name] = {
        "exit_code": run.returncode,
        "command": command,
        "scope": "software/build; no physical board or live cloud",
    }
    print(name, "PASS" if run.returncode == 0 else "FAIL")
    if run.returncode:
        print(run.stdout[-4000:], run.stderr[-2000:])
(evidence / "verification.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
raise SystemExit(any(r["exit_code"] for r in results.values()))
