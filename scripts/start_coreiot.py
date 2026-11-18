"""Start the class CoreIOT profile; enter the gateway token privately in a terminal."""

import argparse
import getpass
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hardware", action="store_true", help="Use the USB bridge instead of simulation")
    parser.add_argument("--port", type=int, default=8081, help="Local dashboard port (default: 8081)")
    args = parser.parse_args()
    config_path = ROOT / "runtime/coreiot_config.json"
    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config = json.loads((ROOT / "gateway/config.coreiot.example.json").read_text(encoding="utf-8"))
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print("CoreIOT profile: runtime/coreiot_config.json")
    print("The supplied app.coreiot.io profile uses MQTT port 1883 without TLS, per CoreIOT docs.")
    if args.hardware:
        print("Hardware mode: check serial_port in that config before starting.")
    else:
        print("Simulation mode: synthetic telemetry will be sent to your CoreIOT child device.")
    token = getpass.getpass("Access token of smartroom-pc-gateway (hidden): ").strip()
    if not token:
        raise SystemExit("No token entered; nothing was sent.")
    env = dict(os.environ, COREIOT_TOKEN=token)
    command = [
        sys.executable,
        "-m",
        "gateway.main",
        "--config",
        str(config_path),
        "--cloud",
        "--port",
        str(args.port),
    ]
    if not args.hardware:
        command.append("--simulate")
    # Keep the token out of arguments, config files, logs and parent environment.
    try:
        return subprocess.call(command, cwd=ROOT, env=env)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
