"""Capture real gateway snapshots; never manufacture hardware measurements."""

import argparse
import json
import time
import urllib.request
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--url", default="http://127.0.0.1:8080")
parser.add_argument("--seconds", type=int, default=300)
parser.add_argument("--output", default="evidence/hardware/session.jsonl")
args = parser.parse_args()
path = Path(args.output)
path.parent.mkdir(parents=True, exist_ok=True)
last_key = None
with path.open("w", encoding="utf-8") as f:
    deadline = time.monotonic() + args.seconds
    while time.monotonic() < deadline:
        state = json.load(urllib.request.urlopen(args.url + "/api/state", timeout=3))
        reading = state["latest"]
        if reading:
            if reading["values"]["data_source"] != "hardware":
                raise SystemExit("Refusing to label simulation as hardware evidence")
            key = (reading["boot"], reading["seq"])
            if key != last_key:
                f.write(
                    json.dumps({"captured_at": time.time(), "reading": reading}, ensure_ascii=False) + "\n"
                )
                f.flush()
                last_key = key
        time.sleep(0.25)
print(path)
