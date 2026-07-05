from datetime import date

import yaml

from src.alerts import check

CFG = yaml.safe_load(open("config.yaml", encoding="utf-8"))
TODAY = date(2026, 7, 5)


def metrics(dd, daily=0.0):
    return {"drawdown_pct": dd, "daily_change_pct": daily}


def test_crossing_level_alerts():
    msgs, state = check(metrics(21.0), {}, CFG, TODAY)
    assert any("20%" in m for m in msgs)
    assert state["levels"]["20"] == "2026-07-05"
    assert "10" in state["levels"]          # 一次跌穿两档都记录


def test_dedup_within_30_days():
    state = {"levels": {"20": "2026-06-20", "10": "2026-06-20"}}
    msgs, _ = check(metrics(22.0), state, CFG, TODAY)
    assert msgs == []


def test_realert_after_30_days():
    state = {"levels": {"20": "2026-05-01", "10": "2026-05-01"}}
    msgs, _ = check(metrics(22.0), state, CFG, TODAY)
    assert len(msgs) == 1


def test_daily_big_drop():
    msgs, state = check(metrics(5.0, daily=-4.5), {}, CFG, TODAY)
    assert any("单日" in m for m in msgs)
    assert state["daily_drop"] == "2026-07-05"


def test_daily_drop_dedup_7_days():
    state = {"daily_drop": "2026-07-01"}
    msgs, _ = check(metrics(5.0, daily=-4.5), state, CFG, TODAY)
    assert msgs == []


def test_no_alert_quiet_market():
    msgs, _ = check(metrics(5.0, daily=-0.5), {}, CFG, TODAY)
    assert msgs == []
