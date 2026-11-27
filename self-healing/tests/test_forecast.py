import numpy as np
import pandas as pd

from selfheal.forecast.train_lstm import (INPUTS, P99_CAP, TARGETS, alert_scores, inverse_targets, transform,
                                          transform_window)


def test_p99_log_roundtrip_and_cap():
    raw = np.array([[10.0, 0.1, 25.0, 0.0], [10.0, 0.1, 10000.0, 0.0]], np.float32)
    w = transform_window(raw)
    assert np.isclose(w[0, INPUTS.index("p99")], np.log1p(25.0))
    assert np.isclose(w[1, INPUTS.index("p99")], np.log1p(P99_CAP))      
    y = np.zeros((1, len(TARGETS)), np.float32)
    y[0, TARGETS.index("p99")] = np.log1p(25.0)
    assert np.isclose(inverse_targets(y)[0, TARGETS.index("p99")], 25.0, atol=1e-3)


def test_dataframe_and_window_transform_agree():
    df = pd.DataFrame([[10.0, 0.1, 300.0, 0.01]], columns=INPUTS)
    assert np.allclose(transform(df).to_numpy(np.float32), transform_window(df.to_numpy(np.float32)))


def test_alert_scores_flags_always_on_predictor():
    true = np.zeros((10, len(TARGETS)))
    true[:3, TARGETS.index("p99")] = 500.0                             
    always = np.full_like(true, 500.0)
    s = alert_scores(always, true, 200.0)
    assert s["alert_rate"] == 1.0 and s["precision"] == 0.3 and s["recall"] == 1.0
