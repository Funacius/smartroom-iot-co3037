"""Reproducible SOFTWARE measurements; these are NOT radio/physical latencies."""

import csv
import json
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gateway.core import Gateway


def summarize(samples):
    samples = sorted(samples)
    return {
        "n": len(samples),
        "mean": statistics.mean(samples),
        "min": samples[0],
        "max": samples[-1],
        "p95": samples[min(len(samples) - 1, int(0.95 * len(samples)))],
    }


def run():
    config = json.loads(Path("gateway/config.example.json").read_text())
    raw = []
    with tempfile.TemporaryDirectory() as tmp:
        config["database"] = str(Path(tmp) / "measure.sqlite3")
        gateway = Gateway(config)
        for seq in range(1, 1001):
            p = dict(
                device=config["device"],
                boot=123,
                seq=seq,
                temperature=27.0,
                humidity=60.0,
                fan=False,
                data_source="software_benchmark",
            )
            start = time.perf_counter()
            gateway.ingest(p)
            raw.append(
                {"metric": "ingest_sqlite_ms", "trial": seq, "value": (time.perf_counter() - start) * 1000}
            )
        for trial in range(1, 101):
            start = time.perf_counter()
            gateway.snapshot()
            raw.append(
                {"metric": "snapshot_ms", "trial": trial, "value": (time.perf_counter() - start) * 1000}
            )
        before = gateway.snapshot()["outbox_count"]
        gateway.flush(lambda *_: False)
        failed_left = gateway.snapshot()["outbox_count"]
        gateway.close()
        gateway = Gateway(config)
        after_restart = gateway.snapshot()["outbox_count"]
        flushed = gateway.flush(lambda *_: True, limit=2000)
        after_flush = gateway.snapshot()["outbox_count"]
        gateway.close()
    metrics = {
        name: summarize([r["value"] for r in raw if r["metric"] == name])
        for name in ("ingest_sqlite_ms", "snapshot_ms")
    }
    result = {
        "scope": "SOFTWARE ONLY; SQLite durability and local processing; no ESP32/radio/cloud measurements",
        "platform": platform.platform(),
        "python": platform.python_version(),
        "metrics": metrics,
        "recovery": {
            "before": before,
            "after_failed_publish": failed_left,
            "after_restart": after_restart,
            "flushed_mock_puback": flushed,
            "remaining": after_flush,
        },
    }
    Path("evidence").mkdir(exist_ok=True)
    Path("evidence/software_metrics.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    with open("evidence/software_trials.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["metric", "trial", "value"])
        writer.writeheader()
        writer.writerows(raw)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(9, 4))
    for ax, name in zip(axes, metrics):
        values = [r["value"] for r in raw if r["metric"] == name]
        ax.hist(values, bins=35, color="#26765b", edgecolor="white")
        ax.set(title=name.replace("_", " "), xlabel="Milliseconds (local PC)", ylabel="Trials")
    fig.suptitle("Measured software processing — NOT end-to-end IoT latency")
    fig.tight_layout()
    fig.savefig("evidence/software_latency.png", dpi=180)
    plt.close(fig)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    run()
