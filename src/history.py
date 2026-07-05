import json
from pathlib import Path


def save_monthly(record: dict, month: str, root: str = "history") -> Path:
    d = Path(root)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{month}.json"
    p.write_text(json.dumps({**record, "month": month}, ensure_ascii=False, indent=2),
                 encoding="utf-8")
    return p


def load_recent(n: int = 12, root: str = "history") -> list[dict]:
    d = Path(root)
    if not d.exists():
        return []
    files = sorted(d.glob("????-??.json"), reverse=True)[:n]
    return [json.loads(p.read_text(encoding="utf-8")) for p in files]
