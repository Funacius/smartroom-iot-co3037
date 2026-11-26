from pathlib import Path

import numpy as np
import pytest

from ai.train import load_csv_data
from gateway.core import Gateway
from gateway.main import load_predictor

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def predictor():
    return load_predictor(ROOT / "ai/model.joblib")


def test_real_model_detects_and_clears_events_and_exports_ai(predictor):
    g = Gateway({"database": ":memory:", "device": "ai-test"}, predictor=predictor)
    try:
        for seq, (t, h, expected) in enumerate([(27, 60, False), (35, 60, True),
                                                (28, 88, True), (27, 60, False)], 1):
            g.ingest({"device": "ai-test", "boot": 1, "seq": seq, "temperature": t,
                      "humidity": h, "fan": False, "data_source": "simulation"})
            values = g.snapshot()["latest"]["values"]
            assert values["ai_available"] is True
            assert values["anomaly"] is expected
            assert np.isfinite(values["anomaly_score"])
        kinds = [e["kind"] for e in reversed(g.snapshot()["events"])]
        assert kinds.count("ai_anomaly_raised") == kinds.count("ai_anomaly_cleared") == 1
        sent = []
        g.flush(lambda _, payload: sent.append(payload) or True)
        assert len(sent) == 4
        assert all("anomaly_score" in p["ai-test"][0]["values"] for p in sent)
    finally:
        g.close()


def test_real_ai_can_flag_anomaly_without_high_threshold(predictor):
    g = Gateway({"database": ":memory:", "device": "ai-test"}, predictor=predictor)
    try:
        g.ingest({"device": "ai-test", "boot": 1, "seq": 1, "temperature": 20,
                  "humidity": 40, "fan": False})
        values = g.snapshot()["latest"]["values"]
        assert values["anomaly"] is True
        assert values["threshold_alarm"] is False
    finally:
        g.close()


@pytest.mark.parametrize("line", ["27,60,0.5", "27,60,2", "27,60,nan", "nan,60,0",
                                  "27,inf,0", "86,60,0", "27,-1,0", "27,101,0"])
def test_csv_rejects_invalid_samples_before_training(tmp_path, line):
    path = tmp_path / "samples.csv"
    path.write_text("temperature,humidity,label\n" + line + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_csv_data(path)


def test_csv_requires_named_columns(tmp_path):
    path = tmp_path / "samples.csv"
    path.write_text("temperature,humidity\n27,60\n", encoding="utf-8")
    with pytest.raises(ValueError, match="columns"):
        load_csv_data(path)


def test_csv_preserves_order_and_exact_labels(tmp_path):
    path = tmp_path / "samples.csv"
    path.write_text("temperature,humidity,label\n27,60,0\n35,65,1\n26,58,0\n", encoding="utf-8")
    x, y = load_csv_data(path)
    assert x.tolist() == [[27, 60], [35, 65], [26, 58]]
    assert y.tolist() == [0, 1, 0]
