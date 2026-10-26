"""The current week follows the league's day -- the US Eastern date with a
2 AM cutoff -- not the server's UTC date (the droplet runs on UTC, which used
to flip weeks at 8 PM ET on Sundays)."""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

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
    monkeypatch.setattr(ls, "_league_today", lambda: eastern_today)
    return store


def test_sunday_night_eastern_is_still_week_1(monkeypatch):
    # 8:21 PM ET Sunday Oct 25 == 00:21 UTC Monday Oct 26.
    assert _store(monkeypatch, date(2026, 10, 25))._current_week_from_calendar(2027) == 1


def test_monday_eastern_is_week_2(monkeypatch):
    assert _store(monkeypatch, date(2026, 10, 26))._current_week_from_calendar(2027) == 2


class _FrozenDatetime(datetime):
    now_value: datetime

    @classmethod
    def now(cls, tz=None):
        return cls.now_value


def _league_today_at(monkeypatch, y, m, d, hh, mm):
    import datetime as dt_module

    _FrozenDatetime.now_value = datetime(y, m, d, hh, mm, tzinfo=ZoneInfo("America/New_York"))
    monkeypatch.setattr(dt_module, "datetime", _FrozenDatetime)
    return ls._league_today()


def test_league_day_cutoff_is_2am_eastern(monkeypatch):
    # Monday Oct 26 before/at 2 AM ET is still Sunday Oct 25 (week 1).
    assert _league_today_at(monkeypatch, 2026, 10, 26, 0, 59) == date(2026, 10, 25)
    assert _league_today_at(monkeypatch, 2026, 10, 26, 2, 0) == date(2026, 10, 25)
    assert _league_today_at(monkeypatch, 2026, 10, 26, 2, 1) == date(2026, 10, 26)
