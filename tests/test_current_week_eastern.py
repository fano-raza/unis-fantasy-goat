"""The current week follows the US Eastern date, not the server's UTC date
(the droplet runs on UTC, which used to flip weeks at 8 PM ET on Sundays)."""
from __future__ import annotations

from datetime import date

import pandas as pd

import dashboard_site.api.league_store as ls


def _store(monkeypatch, eastern_today: date) -> ls.LeagueStore:
    store = ls.LeagueStore.__new__(ls.LeagueStore)
    cal = pd.DataFrame(
        [
            {"Year": 2027, "Week": 1, "StartDate": "2026-10-20", "EndDate": "2026-10-25"},
            {"Year": 2027, "Week": 2, "StartDate": "2026-10-26", "EndDate": "2026-11-01"},
        ]
    )
    monkeypatch.setattr(store, "_ensure_week_calendar_df", lambda: cal, raising=False)
    monkeypatch.setattr(ls, "_eastern_today", lambda: eastern_today)
    return store


def test_sunday_night_eastern_is_still_week_1(monkeypatch):
    # 8:21 PM ET Sunday Oct 25 == 00:21 UTC Monday Oct 26.
    assert _store(monkeypatch, date(2026, 10, 25))._current_week_from_calendar(2027) == 1


def test_monday_eastern_is_week_2(monkeypatch):
    assert _store(monkeypatch, date(2026, 10, 26))._current_week_from_calendar(2027) == 2
