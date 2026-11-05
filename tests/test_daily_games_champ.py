"""discord/daily_games.champion_counts's `since` look-back (/champ-<game> days=)."""
from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "discord" / "daily_games.py"
_spec = importlib.util.spec_from_file_location("daily_games_under_test", _PATH)
dg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dg)


def test_since_limits_days(monkeypatch):
    rows = [  # (date, uid, score)
        ("2026-10-01", 1, 900), ("2026-10-01", 2, 800),
        ("2026-11-03", 1, 700), ("2026-11-03", 2, 950),
        ("2026-11-04", 2, 990), ("2026-11-04", 1, 990),  # tie: both get the day
    ]
    monkeypatch.setattr(dg, "load_history_rows", lambda game: [
        {"date": d, "discord_user_id": str(u), "score": str(s)} for d, u, s in rows])
    game = next(iter(dg.TOP_SCORE_GAMES))
    all_time = {r["uid"]: r["count"] for r in dg.champion_counts(game, 1)}
    assert all_time == {1: 2, 2: 2}
    recent = {r["uid"]: r["count"] for r in dg.champion_counts(game, 1, since=date(2026, 11, 3))}
    assert recent == {2: 2, 1: 1}
    assert dg.champion_counts(game, 1, since=date(2026, 12, 1)) == []
