import json

from src.history import save_monthly, load_recent


def test_save_and_load_roundtrip(tmp_path):
    root = str(tmp_path)
    save_monthly({"multiplier": 1.5, "amount": 1500}, "2026-06", root=root)
    save_monthly({"multiplier": 1.0, "amount": 1000}, "2026-07", root=root)
    recent = load_recent(12, root=root)
    assert [r["month"] for r in recent] == ["2026-07", "2026-06"]
    assert recent[1]["amount"] == 1500


def test_save_is_valid_json(tmp_path):
    p = save_monthly({"multiplier": 2.0}, "2026-05", root=str(tmp_path))
    assert json.loads(p.read_text(encoding="utf-8"))["multiplier"] == 2.0
