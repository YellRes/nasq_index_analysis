import pandas as pd

from src.report import render_monthly, sparkline_b64

RECORD = {
    "month": "2026-07",
    "signals": {"price": 20000.0, "ath": 23000.0, "drawdown_pct": 13.04,
                "ma200": 19500.0, "vix": 18.5, "tnx_yield": 4.1, "tnx_change_3m": -0.2,
                "pe": None},
    "decision": {"multiplier": 1.25, "amount": 1250, "base_multiplier": 1.25,
                 "tier_hit": "回撤 ≥ 10%", "adjustments": []},
    "warnings": ["PE 数据缺失"],
}


def test_render_contains_conclusion_and_warning():
    html = render_monthly(RECORD, recent=[], charts={}, commentary=None)
    assert "1.25x" in html and "1250" in html
    assert "回撤 ≥ 10%" in html
    assert "PE 数据缺失" in html


def test_render_with_commentary_and_history():
    html = render_monthly(RECORD, recent=[{"month": "2026-06",
                          "decision": {"multiplier": 1.0, "amount": 1000}}],
                          charts={}, commentary="宏观点评正文")
    assert "宏观点评正文" in html and "2026-06" in html


def test_sparkline_is_data_uri():
    s = pd.Series(range(50), index=pd.date_range("2026-01-01", periods=50))
    assert sparkline_b64(s, "NDX").startswith("data:image/png;base64,")
