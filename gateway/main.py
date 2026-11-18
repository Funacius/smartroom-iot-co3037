"""Run: python -m gateway.main --simulate (no hardware or cloud required)."""

import argparse
import json
import logging
import signal
import threading
from pathlib import Path

from gateway.core import Gateway
from gateway.server import make_server
from gateway.transports import CoreIOT, SerialBridge, Simulator

ROOT = Path(__file__).resolve().parents[1]


def load_predictor(path):
    if not Path(path).exists():
        return None
    import joblib

    model = joblib.load(path)  # Only load locally trained/trusted files.

    def predict(temperature, humidity):
        score = float(model.decision_function([[temperature, humidity]])[0])
        return score, score < 0

    return predict


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(ROOT / "gateway/config.example.json"))
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--cloud", action="store_true", help="Enable real CoreIOT connection explicitly")
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    if args.port:
        config["http_port"] = args.port
    if args.simulate:
        # Keep synthetic evidence out of the real hardware database.
        config["database"] = "runtime/simulation.sqlite3"
    gateway = Gateway(config, load_predictor(config.get("model", "ai/model.joblib")))
    adapter = Simulator(gateway) if args.simulate else SerialBridge(gateway)
    gateway.send_command = adapter.send
    cloud = CoreIOT(gateway) if args.cloud else None
    server = make_server(gateway, config.get("http_host", "127.0.0.1"), config.get("http_port", 8080))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    logging.info(
        "SmartRoom %s at http://%s:%s; cloud=%s",
        "SIMULATION" if args.simulate else "HARDWARE",
        *server.server_address,
        bool(cloud),
    )
    try:
        while not stop.is_set():
            adapter.poll()
            gateway.tick()
            if cloud:
                cloud.poll()
            stop.wait(0.02)
    finally:
        server.shutdown()
        server.server_close()
        if cloud:
            cloud.close()
        adapter.close()
        gateway.close()


if __name__ == "__main__":
    main()
