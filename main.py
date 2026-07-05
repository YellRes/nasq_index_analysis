import argparse
import dataclasses
import json
import sys
from datetime import date

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # Windows 控制台默认 cp1252 打不出中文

import yaml
from dotenv import load_dotenv

from src import history
from src.pipeline import collect_signals
from src.rules import compute_decision


def load_config() -> dict:
    with open("config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_monthly(cfg: dict, dry_run: bool) -> dict:
    signals, warnings = collect_signals(cfg)
    decision = compute_decision(signals, cfg)
    month = date.today().strftime("%Y-%m")
    record = {
        "signals": {**dataclasses.asdict(signals), "drawdown_pct": signals.drawdown_pct},
        "decision": dataclasses.asdict(decision),
        "warnings": warnings,
    }
    print(json.dumps(record, ensure_ascii=False, indent=2))

    from pathlib import Path
    from src.report import render_monthly, sparkline_b64
    from src.datasources.market import fetch_ndx_closes
    from src.commentary import generate

    charts = {}
    try:
        charts["ndx"] = sparkline_b64(fetch_ndx_closes(period="1y").tail(252), "NDX - 1Y")
    except Exception:
        pass
    commentary = generate(record, cfg)
    html = render_monthly({**record, "month": month},
                          history.load_recent(12), charts, commentary=commentary)

    if dry_run:
        Path("out").mkdir(exist_ok=True)
        Path("out/report-preview.html").write_text(html, encoding="utf-8")
        print("预览已写入 out/report-preview.html")
    else:
        from src.notify import send_html
        subject = cfg["mail"]["subject_monthly"].format(
            month=month, multiplier=record["decision"]["multiplier"],
            amount=record["decision"]["amount"])
        send_html(subject, html, cfg)
        history.save_monthly(record, month)
        print(f"报告已发送：{subject}")
    return record


def run_daily(cfg: dict, dry_run: bool) -> None:
    from datetime import date as _date
    from pathlib import Path
    from src.alerts import check
    from src.datasources.market import fetch_ndx_closes, compute_market_metrics

    metrics = compute_market_metrics(fetch_ndx_closes())
    state_path = Path("history/alerts_state.json")
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    msgs, new_state = check(metrics, state, cfg, _date.today())

    if not msgs:
        print("无触发，静默退出")
        return
    body = "<br>".join(msgs) + f"<p>当前回撤 -{metrics['drawdown_pct']:.1f}%，收盘 {metrics['price']:.0f}</p>"
    print("\n".join(msgs))
    if not dry_run:
        from src.notify import send_html
        send_html(cfg["mail"]["subject_alert"].format(title=msgs[0]), body, cfg)
        state_path.parent.mkdir(exist_ok=True)
        state_path.write_text(json.dumps(new_state, ensure_ascii=False, indent=2),
                              encoding="utf-8")


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="纳指定投监控系统")
    parser.add_argument("--mode", choices=["monthly", "daily"], required=True)
    parser.add_argument("--dry-run", action="store_true", help="不发邮件不写历史")
    args = parser.parse_args()
    cfg = load_config()
    if args.mode == "monthly":
        run_monthly(cfg, args.dry_run)
    else:
        run_daily(cfg, args.dry_run)


if __name__ == "__main__":
    main()
