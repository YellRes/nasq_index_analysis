from src.models import Signals, Decision


def _base_tier(dd: float, cfg: dict) -> tuple[float, str]:
    for tier in cfg["tiers"]:
        if dd >= tier["min_drawdown"]:
            return tier["multiplier"], f"回撤 ≥ {tier['min_drawdown']}%"
    return cfg["default_multiplier"], "回撤 < 10%（默认档）"


def _round_step(x: float, step: float) -> float:
    return round(x / step) * step


def compute_decision(signals: Signals, cfg: dict) -> Decision:
    base, tier_hit = _base_tier(signals.drawdown_pct, cfg)
    multiplier = base
    adjustments: list[str] = []

    ra = cfg["rate_adjust"]
    if ra["enabled"] and signals.tnx_yield is not None and signals.tnx_change_3m is not None:
        if signals.tnx_yield > ra["high_yield"] and signals.tnx_change_3m > 0:
            multiplier *= ra["tighten_factor"]
            adjustments.append(f"高利率且上行（10Y={signals.tnx_yield:.2f}%）×{ra['tighten_factor']}")
        elif signals.tnx_change_3m < -ra["easing_drop"]:
            multiplier *= ra["easing_factor"]
            adjustments.append(f"利率快速下行（3个月 {signals.tnx_change_3m:+.2f}pp）×{ra['easing_factor']}")

    multiplier = min(_round_step(multiplier, cfg["round_step"]), cfg["cap"])
    amount = int(round(multiplier * cfg["base_amount"]))
    return Decision(multiplier=multiplier, amount=amount,
                    base_multiplier=base, tier_hit=tier_hit,
                    adjustments=adjustments)
