import pandas as pd

from src.datasources.rates import compute_rate_metrics


def test_change_3m():
    idx = pd.date_range("2026-01-01", periods=70, freq="B")
    vals = [4.0] * 63 + [4.5] * 7          # 63 个交易日前 4.0，现在 4.5
    m = compute_rate_metrics(pd.Series(vals, index=idx, dtype=float))
    assert abs(m["tnx_yield"] - 4.5) < 1e-9
    assert abs(m["tnx_change_3m"] - 0.5) < 1e-9


def test_short_series_change_none():
    idx = pd.date_range("2026-01-01", periods=10, freq="B")
    m = compute_rate_metrics(pd.Series([4.0] * 10, index=idx, dtype=float))
    assert m["tnx_yield"] == 4.0
    assert m["tnx_change_3m"] is None
