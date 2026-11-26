"""Evaluate the frozen model against a threshold baseline on synthetic data.

Run: python -m ai.evaluate. Does not retrain or overwrite the deployed model.
Scenario labels describe the generator, not measured comfort or health limits.
"""

import argparse
import csv
import hashlib
import json
import platform
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import matplotlib
import numpy as np
import sklearn
from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from gateway.core import Gateway
from gateway.main import load_predictor

ROOT = Path(__file__).resolve().parents[1]


def threshold_predict(x):
    """Stateless baseline; gateway hysteresis is checked separately as a sequence."""
    return ((x[:, 0] >= 32) | (x[:, 1] >= 80)).astype(int)


def summarize(y, prediction):
    tn, fp, fn, tp = confusion_matrix(y, prediction, labels=[0, 1]).ravel()
    precision, recall, f1, _ = precision_recall_fscore_support(
        y, prediction, average="binary", zero_division=0
    )
    return {"samples": len(y), "normal": int(tn + fp), "anomalous": int(fn + tp),
            "confusion_matrix": [[int(tn), int(fp)], [int(fn), int(tp)]],
            "accuracy": float(accuracy_score(y, prediction)),
            "precision": float(precision), "recall": float(recall), "f1": float(f1),
            "false_positive_rate": float(fp / (tn + fp)) if tn + fp else None,
            "false_negative_rate": float(fn / (fn + tp)) if fn + tp else None}


def generated_test(seed, normal=800, hot=200, humid=200):
    rng = np.random.default_rng(seed)
    return (np.vstack([rng.normal([27, 60], [1.3, 5], (normal, 2)),
                       rng.normal([35, 66], [1.2, 5], (hot, 2)),
                       rng.normal([28, 88], [1.2, 3], (humid, 2))]),
            np.array([0] * normal + [1] * (hot + humid)))


def evaluate(output=None):
    output = Path(output or ROOT / "evidence")
    output.mkdir(parents=True, exist_ok=True)
    model_path = ROOT / "ai/model.joblib"
    source_path = ROOT / "evidence/ai_test_predictions.csv"
    model_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
    model = joblib.load(model_path)
    with source_path.open(encoding="utf-8") as source_file:
        rows = list(csv.DictReader(source_file))
    if not rows or any(not r.get("source", "").startswith("synthetic_") for r in rows):
        raise ValueError("This experiment requires the archived synthetic reference; do not relabel field data")
    reference_x = np.array([[float(r["temperature"]), float(r["humidity"])] for r in rows])
    reference_y = np.array([int(r["label"]) for r in rows])
    expected = np.array([int(r["prediction"]) for r in rows])
    seeds = [26101, 26102, 26103, 26104, 26105]
    batches = [generated_test(seed) for seed in seeds]
    rng = np.random.default_rng(26106)
    datasets = {
        "reference": (reference_x, reference_y),
        "fresh_same_distribution": (np.vstack([x for x, _ in batches]), np.concatenate([y for _, y in batches])),
        "shifted_normal": (rng.normal([29, 65], [1.3, 5], (1000, 2)), np.zeros(1000, dtype=int)),
        "unseen_cold": (rng.normal([18, 40], [1.5, 4], (300, 2)), np.ones(300, dtype=int)),
        "rare_anomaly": generated_test(26107, normal=2000, hot=20, humid=20),
    }
    results, trials, errors = {}, [], []
    for name, (x, y) in datasets.items():
        scores = model.decision_function(x)
        predicted = (scores < 0).astype(int)
        baseline = threshold_predict(x)
        results[name] = {"isolation_forest": summarize(y, predicted), "threshold": summarize(y, baseline)}
        for i, (point, label, score, ai, rule) in enumerate(zip(x, y, scores, predicted, baseline)):
            row = [name, i, float(point[0]), float(point[1]), int(label), float(score), int(ai), int(rule)]
            trials.append(row)
            if ai != label or rule != label:
                errors.append(row)
    if not np.array_equal((model.predict(reference_x) == -1).astype(int), expected):
        raise ValueError("Deployed model predictions do not match the archived reference CSV")
    repeats = []
    for seed, (x, y) in zip(seeds, batches):
        repeats.append({"seed": seed, "isolation_forest": summarize(y, (model.predict(x) == -1).astype(int)),
                        "threshold": summarize(y, threshold_predict(x))})

    # Each point starts with a new gateway so prior hysteresis cannot hide the
    # difference between an AI anomaly and the independently configured rule.
    point_checks = []
    for name, t, h in [("normal", 27, 60), ("temperature_high_boundary", 32, 60),
                       ("humidity_high_boundary", 27, 80), ("below_both_thresholds", 27, 78),
                       ("unusual_cold", 20, 40), ("temperature_clear_boundary", 30, 60),
                       ("humidity_clear_boundary", 27, 75)]:
        gateway = Gateway({"database": ":memory:", "device": "ai-evaluation"},
                          predictor=load_predictor(model_path))
        try:
            gateway.ingest({"device": "ai-evaluation", "boot": 1, "seq": 1,
                            "temperature": t, "humidity": h, "fan": False, "data_source": "simulation"})
            values = gateway.snapshot()["latest"]["values"]
            payloads = []
            gateway.flush(lambda topic, payload: payloads.append(payload) or True)
            assert all(k in payloads[0]["ai-evaluation"][0]["values"]
                       for k in ("anomaly", "anomaly_score", "inference_ms", "ai_available"))
            point_checks.append({"name": name, **values})
        finally:
            gateway.close()

    # Real CPU timings with a fixed order, warm-up and no concurrent cloud call.
    times = []
    timing_x = reference_x[np.random.default_rng(26108).choice(len(reference_x), 200, replace=False)]
    for point in timing_x[:10]:
        model.decision_function([point])
    for point in timing_x:
        start = time.perf_counter()
        model.decision_function([point])
        times.append((time.perf_counter() - start) * 1000)
    assert hashlib.sha256(model_path.read_bytes()).hexdigest() == model_hash
    result = {
        "checked_at": datetime.now(timezone(timedelta(hours=7))).isoformat(),
        "scope": "Frozen model; all evaluation data is synthetic; local gateway integration, no live cloud or board",
        "model_sha256": model_hash,
        "reference_csv_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "model_unchanged": True, "reference_predictions_match": True,
        "protocol": {"baseline": "Stateless temperature>=32 OR humidity>=80; no hysteresis in classification metrics",
                     "fresh_seeds": seeds, "stress_seed": 26106, "rare_seed": 26107,
                     "shifted_normal_assumption": "All 1000 shifted samples are assumed valid normal conditions, not field labels",
                     "unseen_cold_assumption": "All 300 cold samples are generator-defined anomalies, not health limits",
                     "no_tuning": "Model, contamination and threshold fixed before evaluation; no retraining or threshold search"},
        "datasets": results, "fresh_repeats": repeats, "point_checks": point_checks,
        "inference_ms": {"n": len(times), "warmup": 10, "mean": float(np.mean(times)),
                         "min": min(times), "max": max(times), "p95": float(np.percentile(times, 95))},
        "versions": {"python": platform.python_version(), "sklearn": sklearn.__version__, "numpy": np.__version__},
        "limitations": ["Synthetic separation is easy; no field accuracy claim",
                        "Normal distribution drift may cause many false alarms",
                        "Anomaly score is not a probability or confidence percentage",
                        "Single-class stress sets have undefined class-specific metrics; interpret counts/FPR only",
                        "Snapshot model uses two instantaneous variables; does not infer trends or room occupancy"],
    }
    header = ["dataset", "sample", "temperature", "humidity", "label", "anomaly_score", "ai_prediction", "threshold_prediction"]
    for name, data in [("ai_evaluation_trials.csv", trials), ("ai_error_samples.csv", errors)]:
        with (output / name).open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(data)
    (output / "ai_evaluation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    names = ["reference", "fresh_same_distribution", "rare_anomaly"]
    indices = np.arange(len(names))
    for method, label, offset, color in [("isolation_forest", "Isolation Forest", -0.18, "#176550"),
                                         ("threshold", "Threshold rule", 0.18, "#bc7138")]:
        axes[0].bar(indices + offset, [results[n][method]["f1"] for n in names], 0.36, label=label, color=color)
        axes[1].bar(indices + offset, [100 * results[n][method]["false_positive_rate"] for n in names],
                    0.36, label=label, color=color)
    for ax in axes:
        ax.set_xticks(indices, ["Reference", "Fresh seeds", "Rare anomaly"])
        ax.legend(fontsize=8)
        ax.grid(axis="y", alpha=0.2)
        ax.set_axisbelow(True)
    axes[0].set(ylabel="F1 (anomaly class)", ylim=(0, 1.08))
    axes[1].set(ylabel="False positive rate (%)")
    fig.suptitle("Frozen-model comparison — synthetic data only")
    fig.tight_layout()
    fig.savefig(output / "ai_comparison.png", dpi=180)
    plt.close(fig)

    ts, hs = np.meshgrid(np.linspace(18, 38, 140), np.linspace(35, 95, 140))
    score_grid = model.decision_function(np.column_stack([ts.ravel(), hs.ravel()])).reshape(ts.shape)
    fig, ax = plt.subplots(figsize=(8, 5))
    contour = ax.contourf(ts, hs, score_grid, levels=24, cmap="RdYlGn")
    ax.contour(ts, hs, score_grid, levels=[0], colors="#163433", linewidths=1.5)
    ax.axvline(32, color="#ab451f", linestyle="--", label="Threshold T >= 32 C")
    ax.axhline(80, color="#2b5887", linestyle="--", label="Threshold RH >= 80%")
    ax.set(xlabel="Temperature (C)", ylabel="Humidity (%)", title="Decision score (not probability) — fixed synthetic model")
    ax.legend(loc="lower right", fontsize=8)
    fig.colorbar(contour, ax=ax, label="decision_function; anomaly if < 0")
    fig.tight_layout()
    fig.savefig(output / "ai_decision_regions.png", dpi=180)
    plt.close(fig)
    print(json.dumps({"datasets": results, "inference_ms": result["inference_ms"]}, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    evaluate(parser.parse_args().output)
