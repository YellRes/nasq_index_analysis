"""采集全部信号，辅助信号失败降级，主信号失败抛错。"""
import os

from src.models import Signals
from src.datasources import market, rates


def collect_signals(cfg: dict) -> tuple[Signals, list[str]]:
    warnings: list[str] = []

    closes = market.fetch_ndx_closes()          # 失败自然抛 RuntimeError
    m = market.compute_market_metrics(closes)

    vix = market.fetch_vix()
    if vix is None:
        warnings.append("VIX 数据缺失")

    tnx_yield = tnx_change = None
    try:
        r = rates.compute_rate_metrics(rates.fetch_10y(os.environ.get("FRED_API_KEY")))
        tnx_yield, tnx_change = r["tnx_yield"], r["tnx_change_3m"]
    except RuntimeError:
        warnings.append("10Y 利率数据缺失（利率修正未生效）")

    from src.datasources.valuation import fetch_qqq_pe
    pe = fetch_qqq_pe()
    if pe is None:
        warnings.append("QQQ PE 数据缺失（估值为辅助信号，不影响倍数）")

    signals = Signals(price=m["price"], ath=m["ath"], ma200=m["ma200"],
                      vix=vix, tnx_yield=tnx_yield, tnx_change_3m=tnx_change, pe=pe)
    return signals, warnings
