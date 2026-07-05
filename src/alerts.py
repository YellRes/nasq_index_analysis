from datetime import date, timedelta


def _stale(last_iso: str | None, days: int, today: date) -> bool:
    if not last_iso:
        return True
    return (today - date.fromisoformat(last_iso)) >= timedelta(days=days)


def check(metrics: dict, state: dict, cfg: dict, today: date) -> tuple[list[str], dict]:
    a = cfg["alerts"]
    msgs: list[str] = []
    new_state = {"levels": dict(state.get("levels", {})),
                 "daily_drop": state.get("daily_drop")}

    dd = metrics["drawdown_pct"]
    for level in sorted(a["drawdown_levels"], reverse=True):
        if dd >= level:
            key = str(level)
            if _stale(new_state["levels"].get(key), a["level_dedup_days"], today):
                msgs.append(f"纳指回撤达 -{level}% 档（当前 -{dd:.1f}%），进入对应加仓区")
            # 覆盖式记录：更深档位触发时同时刷新浅档位，避免回撤缓慢加深时重复提醒
            for shallower in a["drawdown_levels"]:
                if shallower <= level:
                    new_state["levels"][str(shallower)] = today.isoformat()
            break

    if metrics["daily_change_pct"] <= -a["daily_drop_pct"]:
        if _stale(new_state["daily_drop"], a["daily_drop_dedup_days"], today):
            msgs.append(f"纳指单日 {metrics['daily_change_pct']:.1f}%，大幅波动")
            new_state["daily_drop"] = today.isoformat()

    return msgs, new_state
