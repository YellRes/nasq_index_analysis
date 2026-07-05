"""用三个真实历史时点验证规则合理性（数值为当时快照，冻结不变）。"""
import yaml

from src.models import Signals
from src.rules import compute_decision

CFG = yaml.safe_load(open("config.yaml", encoding="utf-8"))


def test_2020_03_covid_crash():
    # 2020-03-23 疫情底：NDX≈6994，ATH≈9736（回撤≈28%），10Y=0.76 且 3 个月暴跌
    s = Signals(price=6994.0, ath=9736.0, tnx_yield=0.76, tnx_change_3m=-1.05)
    d = compute_decision(s, CFG)
    assert d.base_multiplier == 1.5          # 回撤 20-30% 档
    assert d.multiplier == 1.75              # 1.5 × 1.2 = 1.8 → 取整 1.75
    assert d.amount == 1750


def test_2022_12_rate_hike_bear_bottom():
    # 2022-12-28 加息熊底：NDX≈10679，ATH≈16765（回撤≈36%），10Y=3.88 高位盘整
    s = Signals(price=10679.0, ath=16765.0, tnx_yield=3.88, tnx_change_3m=0.1)
    d = compute_decision(s, CFG)
    assert d.base_multiplier == 2.0
    assert d.multiplier == 2.0               # 3.88 < 4.5 不触发收紧，维持上限
    assert d.amount == 2000


def test_2024_07_at_high():
    # 2024-07-10 历史高位附近：回撤≈0，10Y=4.28 温和回落
    s = Signals(price=20675.0, ath=20675.0, tnx_yield=4.28, tnx_change_3m=-0.1)
    d = compute_decision(s, CFG)
    assert d.multiplier == 1.0
    assert d.amount == 1000
