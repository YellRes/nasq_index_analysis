import pandas as pd

from src.datasources.market import compute_market_metrics


def make_series(values):
    idx = pd.date_range("2024-01-01", periods=len(values), freq="B")
    return pd.Series(values, index=idx, dtype=float)


def test_drawdown_and_ath():
    closes = make_series([100, 200, 150])
    m = compute_market_metrics(closes)
    assert m["ath"] == 200
    assert m["price"] == 150
    assert abs(m["drawdown_pct"] - 25.0) < 1e-9


def test_ma200_none_when_short():
    m = compute_market_metrics(make_series([100] * 50))
    assert m["ma200"] is None


def test_ma200_and_above_flag():
    closes = make_series([100] * 200 + [150])
    m = compute_market_metrics(closes)
    assert m["ma200"] is not None
    assert m["above_ma200"] is True


def test_daily_change():
    m = compute_market_metrics(make_series([100, 96]))
    assert abs(m["daily_change_pct"] - (-4.0)) < 1e-9
