"""Train an Isolation Forest without test leakage.

Default samples are SYNTHETIC. --csv requires temperature,humidity,label columns,
label=0 normal, label=1 anomalous; rows must be chronologically ordered.
The first 60% are training; the last 40% are a held-out test set.
"""

import argparse
import csv
import json
import platform
import time
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import sklearn
from sklearn.ensemble import IsolationForest
from sklearn.metrics import classification_report, confusion_matrix


def train(csv_path=None):
    rng = np.random.default_rng(2353007)
    if csv_path:
        rows = np.genfromtxt(csv_path, delimiter=",", names=True)
        x = np.column_stack([rows["temperature"], rows["humidity"]])
        y = rows["label"].astype(int)
        cut = int(len(x) * 0.6)
        train_x, test_x, test_y = x[:cut][y[:cut] == 0], x[cut:], y[cut:]
        source = "user_csv:" + str(csv_path)
    else:
        train_x = rng.normal([27, 60], [1.3, 5.0], (1500, 2))
        normal = rng.normal([27, 60], [1.3, 5.0], (800, 2))
        hot = rng.normal([35, 66], [1.2, 5.0], (200, 2))
        humid = rng.normal([28, 88], [1.2, 3.0], (200, 2))
        test_x = np.vstack([normal, hot, humid])
        test_y = np.array([0] * 800 + [1] * 400)
        source = "synthetic_seed_2353007_NOT_field_measurements"
    if (
        len(train_x) < 100
        or len(test_x) < 50
        or not np.isfinite(train_x).all()
        or not np.isfinite(test_x).all()
    ):
        raise ValueError("Need >=100 finite normal training samples and >=50 finite test samples")
    if set(test_y) != {0, 1}:
        raise ValueError("Test set must contain normal and anomalous samples")
    model = IsolationForest(n_estimators=100, contamination=0.02, random_state=2353007, n_jobs=1)
    model.fit(train_x)
    pred = (model.predict(test_x) == -1).astype(int)
    timings = []
    for row in test_x[:100]:
        start = time.perf_counter()
        model.decision_function([row])
        timings.append((time.perf_counter() - start) * 1000)
    report = classification_report(test_y, pred, output_dict=True, zero_division=0)
    metrics = {
        "data_source": source,
        "training_normal_samples": len(train_x),
        "test_samples": len(test_x),
        "confusion_matrix_labels": ["normal", "anomaly"],
        "confusion_matrix": confusion_matrix(test_y, pred).tolist(),
        "classification": report,
        "inference_ms": {
            "n": len(timings),
            "mean": float(np.mean(timings)),
            "min": min(timings),
            "max": max(timings),
            "p95": float(np.percentile(timings, 95)),
        },
        "versions": {
            "python": platform.python_version(),
            "sklearn": sklearn.__version__,
            "numpy": np.__version__,
        },
    }
    Path("ai").mkdir(exist_ok=True)
    Path("evidence").mkdir(exist_ok=True)
    joblib.dump(model, "ai/model.joblib")
    Path("evidence/ai_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    with open("evidence/ai_test_predictions.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["temperature", "humidity", "label", "prediction", "source"])
        writer.writerows((*x, int(y), int(p), source) for x, y, p in zip(test_x, test_y, pred))
    fig, ax = plt.subplots(figsize=(7, 4.4))
    image = ax.imshow(confusion_matrix(test_y, pred), cmap="Greens")
    for (r, c), count in np.ndenumerate(confusion_matrix(test_y, pred)):
        ax.text(c, r, str(count), ha="center", va="center", fontsize=20, color="#102f20")
    ax.set(
        xticks=[0, 1],
        yticks=[0, 1],
        xticklabels=["Normal", "Anomaly"],
        yticklabels=["Normal", "Anomaly"],
        xlabel="Prediction",
        ylabel="Ground truth",
        title="Isolation Forest — synthetic held-out data",
    )
    fig.colorbar(image, ax=ax)
    fig.tight_layout()
    fig.savefig("evidence/confusion_matrix.png", dpi=180)
    plt.close(fig)
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv")
    train(parser.parse_args().csv)
