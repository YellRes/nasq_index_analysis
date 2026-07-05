import yaml

from src.models import Signals
from src.rules import compute_decision

CFG = yaml.safe_load(open("config.yaml", encoding="utf-8"))


def sig(drawdown_pct: float, **kw) -> Signals:
    ath = 10000.0
    defaults = dict(ath=ath, price=ath * (1 - drawdown_pct / 100),
                    ma200=None, vix=None, tnx_yield=None, tnx_change_3m=None, pe=None)
    defaults.update(kw)
    return Signals(**defaults)


def test_default_tier_below_10():
    d = compute_decision(sig(9.9), CFG)
    assert d.multiplier == 1.0
    assert d.amount == 1000


def test_tier_boundary_exactly_10():
    d = compute_decision(sig(10.0), CFG)
    assert d.multiplier == 1.25
    assert d.amount == 1250


def test_tier_20():
    assert compute_decision(sig(23.0), CFG).multiplier == 1.5


def test_tier_30_is_cap():
    d = compute_decision(sig(36.0), CFG)
    assert d.multiplier == 2.0
    assert d.amount == 2000


def test_decision_records_tier_hit():
    d = compute_decision(sig(23.0), CFG)
    assert "20" in d.tier_hit


def test_high_rate_tightens():
    # 回撤 23% 基础 1.5x；10Y=4.8 且 3 个月上行 → ×0.8 = 1.2 → 取整 0.25 档 → 1.25
    d = compute_decision(sig(23.0, tnx_yield=4.8, tnx_change_3m=0.3), CFG)
    assert d.multiplier == 1.25
    assert any("×0.8" in a for a in d.adjustments)


def test_easing_boosts_but_capped():
    # 回撤 36% 基础 2.0x；3 个月下行 0.8pp → ×1.2 = 2.4 → 上限 2.0
    d = compute_decision(sig(36.0, tnx_yield=3.0, tnx_change_3m=-0.8), CFG)
    assert d.multiplier == 2.0


def test_easing_boost_applies():
    # 基础 1.0x；宽松 → 1.2 → 取整 → 1.25
    d = compute_decision(sig(5.0, tnx_yield=3.0, tnx_change_3m=-0.8), CFG)
    assert d.multiplier == 1.25


def test_missing_rate_data_no_adjust():
    d = compute_decision(sig(23.0, tnx_yield=None, tnx_change_3m=None), CFG)
    assert d.multiplier == 1.5
    assert d.adjustments == []


def test_rate_adjust_can_be_disabled():
    cfg = {**CFG, "rate_adjust": {**CFG["rate_adjust"], "enabled": False}}
    d = compute_decision(sig(23.0, tnx_yield=4.8, tnx_change_3m=0.3), cfg)
    assert d.multiplier == 1.5
