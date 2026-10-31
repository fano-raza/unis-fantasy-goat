"""LeagueStore.roster_week_status + POST /league/roster_week_status (the
Roster page's full-week grid: lineup slots, games played, injury status)."""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import dashboard_site.api.app as app_module
from dashboard_site.api.league_store import LeagueStore


@pytest.fixture
def store(tmp_path, monkeypatch):
    days = {10: "2026-10-29", 11: "2026-10-30", 12: "2026-10-31"}
    history = []
    for sp, d in days.items():
        history += [
            {"Year": 2027, "ScoringPeriod": sp, "Date": d, "FantasyTeam": "Fano", "PlayerId": 1, "Player": "Ja Morant",
             "LineupSlot": {10: "PG", 11: "BE", 12: "IR"}[sp]},
            {"Year": 2027, "ScoringPeriod": sp, "Date": d, "FantasyTeam": "Fano", "PlayerId": 2, "Player": "Jayson Tatum",
             "LineupSlot": "PF"},
            {"Year": 2027, "ScoringPeriod": sp, "Date": d, "FantasyTeam": "Amil", "PlayerId": 3, "Player": "Other Guy",
             "LineupSlot": "C"},
        ]
    pd.DataFrame(history).to_csv(tmp_path / "lineup_history.csv", index=False)
    pd.DataFrame([
        {"PlayerId": 1, "ScoringPeriod": 10, "MIN": 31},
        {"PlayerId": 2, "ScoringPeriod": 10, "MIN": 36},
        {"PlayerId": 2, "ScoringPeriod": 11, "MIN": 0},   # dressed, didn't play
        {"PlayerId": 2, "ScoringPeriod": 12, "MIN": 30},
    ]).to_csv(tmp_path / "player_game_logs.csv", index=False)
    pd.DataFrame([{"PlayerId": 1, "InjuryStatus": "OUT"}, {"PlayerId": 2, "InjuryStatus": "ACTIVE"}]).to_csv(
        tmp_path / "player_projections.csv", index=False)

    class FakeStats:
        ref_dir = str(tmp_path)

    s = LeagueStore.__new__(LeagueStore)
    s.store = FakeStats()
    monkeypatch.setattr(s, "meta", lambda: {"current_year": 2027})
    return s


def test_slots_played_and_injury(store):
    out = store.roster_week_status(2027, "Fano", date(2026, 10, 27), date(2026, 11, 2))
    assert set(out["players"]) == {"Ja Morant", "Jayson Tatum"}
    ja, jt = out["players"]["Ja Morant"], out["players"]["Jayson Tatum"]
    assert ja["slots"] == {"2026-10-29": "PG", "2026-10-30": "BE", "2026-10-31": "IR"}
    assert ja["played"] == ["2026-10-29"] and ja["injury_status"] == "OUT" and ja["out"] is True
    # A 0-minute game isn't a game played.
    assert jt["played"] == ["2026-10-29", "2026-10-31"] and jt["out"] is False
    assert out["game_logs_through"] == "2026-10-31"


def test_week_window_and_missing_history(store, tmp_path):
    out = store.roster_week_status(2027, "Fano", date(2026, 10, 30), date(2026, 10, 30))
    assert out["players"]["Ja Morant"]["slots"] == {"2026-10-30": "BE"}
    assert out["players"]["Jayson Tatum"]["played"] == []
    (tmp_path / "lineup_history.csv").unlink()
    store._ref_csv_cache = {}
    assert store.roster_week_status(2027, "Fano", date(2026, 10, 27), date(2026, 11, 2))["players"] == {}


def test_endpoint(monkeypatch):
    seen = []
    monkeypatch.setattr(app_module.league_store, "roster_week_status",
                        lambda y, t, a, b: seen.append((y, t, a, b)) or {"players": {}})
    r = TestClient(app_module.app).post("/league/roster_week_status",
                                        json={"year": 2027, "team": "Fano", "start_date": "2026-10-27", "end_date": "2026-11-02"})
    assert r.status_code == 200 and seen == [(2027, "Fano", date(2026, 10, 27), date(2026, 11, 2))]


def test_league_week_status_all_teams(store):
    out = store.league_week_status(2027, date(2026, 10, 27), date(2026, 11, 2))
    assert set(out["teams"]) == {"Fano", "Amil"}
    # Same per-player data as the single-team call.
    single = store.roster_week_status(2027, "Fano", date(2026, 10, 27), date(2026, 11, 2))
    assert out["teams"]["Fano"] == single["players"]
    assert out["game_logs_through"] == single["game_logs_through"] == "2026-10-31"


def test_league_week_status_endpoint(monkeypatch):
    seen = []
    monkeypatch.setattr(app_module.league_store, "league_week_status",
                        lambda y, a, b: seen.append((y, a, b)) or {"teams": {}})
    r = TestClient(app_module.app).post("/league/week_status",
                                        json={"year": 2027, "start_date": "2026-10-26", "end_date": "2026-11-01"})
    assert r.status_code == 200 and seen == [(2027, date(2026, 10, 26), date(2026, 11, 1))]
