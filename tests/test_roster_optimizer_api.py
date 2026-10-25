"""Endpoint + LeagueStore tests for the Roster Optimizer (POST /league/roster_optimizer)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import dashboard_site.api.app as app_module
from dashboard_site.api.league_store import LeagueStore

client = TestClient(app_module.app)
URL = "/league/roster_optimizer"


def test_feature_off_without_password_env(monkeypatch):
    monkeypatch.delenv("ROSTER_OPTIMIZER_PASSWORD", raising=False)
    r = client.post(URL, json={"team": "Fano", "password": "anything"})
    assert r.status_code == 503


def test_wrong_password_rejected(monkeypatch):
    monkeypatch.setenv("ROSTER_OPTIMIZER_PASSWORD", "secret")
    called = []
    monkeypatch.setattr(app_module.league_store, "roster_optimizer", lambda *a: called.append(a) or {})
    r = client.post(URL, json={"team": "Fano", "password": "wrong"})
    assert r.status_code == 401 and not called


def test_correct_password_runs(monkeypatch):
    monkeypatch.setenv("ROSTER_OPTIMIZER_PASSWORD", "secret")
    monkeypatch.setattr(app_module.league_store, "roster_optimizer", lambda team, n: {"team": team, "max_swaps": n})
    r = client.post(URL, json={"team": "Fano", "password": "secret", "max_swaps": 4})
    assert r.status_code == 200 and r.json() == {"team": "Fano", "max_swaps": 4}


def test_unknown_team_is_404(monkeypatch):
    monkeypatch.setenv("ROSTER_OPTIMIZER_PASSWORD", "secret")

    def boom(team, n):
        raise KeyError(f"no 2027 roster found for team {team!r}")

    monkeypatch.setattr(app_module.league_store, "roster_optimizer", boom)
    assert client.post(URL, json={"team": "Nobody", "password": "secret"}).status_code == 404


def test_max_swaps_validated():
    assert client.post(URL, json={"team": "Fano", "password": "x", "max_swaps": 0}).status_code == 422


# --- LeagueStore.roster_optimizer on a tiny synthetic ref dir -------------

def _write_ref(tmp_path, rng):
    stats, proj, roster = [], [], []
    pid = 1
    for team in ["A", "B", "C", "T"]:
        for _ in range(4):
            stats.append(_stat_row(pid, f"P{pid}", rng))
            proj.append({"PlayerId": pid, **{f"proj_{c}": v for c, v in _line(rng).items()}, "proj_GP": 70,
                         "InjuryStatus": "ACTIVE"})
            roster.append({"Year": 2027, "FantasyTeam": team, "Player": f"P{pid}", "NBATeam": "BOS", "Rank": pid})
            pid += 1
    for _ in range(10):  # free agents
        stats.append(_stat_row(pid, f"P{pid}", rng))
        proj.append({"PlayerId": pid, **{f"proj_{c}": v for c, v in _line(rng).items()}, "proj_GP": 70,
                     "InjuryStatus": "ACTIVE"})
        roster.append({"Year": 2027, "FantasyTeam": None, "Player": f"P{pid}", "NBATeam": "BOS", "Rank": pid})
        pid += 1
    pd.DataFrame(stats).to_csv(tmp_path / "player_stats.csv", index=False)
    pd.DataFrame(proj).to_csv(tmp_path / "player_projections.csv", index=False)
    pd.DataFrame(roster).to_csv(tmp_path / "roster_ranks.csv", index=False)
    pd.DataFrame([{"Year": 2027, "Week": 1, "StartDate": "2026-10-20", "EndDate": "2026-10-25"}]).to_csv(
        tmp_path / "week_calendar.csv", index=False)


def _line(rng):
    fga, fta = rng.uniform(5, 18), rng.uniform(1, 7)
    return {"FGM": fga * rng.uniform(0.4, 0.55), "FGA": fga, "FTM": fta * rng.uniform(0.65, 0.9), "FTA": fta,
            "3PTM": rng.uniform(0, 3), "REB": rng.uniform(2, 11), "AST": rng.uniform(1, 8), "STL": rng.uniform(0.3, 2),
            "BLK": rng.uniform(0.1, 2), "TO": rng.uniform(0.5, 3), "PTS": rng.uniform(5, 28)}


def _stat_row(pid, name, rng, gp=5):
    ln = _line(rng)
    row = {"PlayerId": pid, "Player": name, "Team": "BOS", "season_GP": gp, "d30_GP": gp,
           "season_FG%_made": ln["FGM"] * gp, "season_FG%_att": ln["FGA"] * gp,
           "season_FT%_made": ln["FTM"] * gp, "season_FT%_att": ln["FTA"] * gp}
    for c in ["3PTM", "REB", "AST", "STL", "BLK", "TO", "PTS"]:
        row[f"season_{c}_avg"] = ln[c]
    return row


@pytest.fixture
def store(tmp_path, monkeypatch):
    _write_ref(tmp_path, np.random.default_rng(5))

    class FakeStats:
        ref_dir = str(tmp_path)

    s = LeagueStore.__new__(LeagueStore)
    s.store = FakeStats()
    s._player_stats_df = s._roster_ranks_df = s._player_projections_df = s._week_calendar_df = None
    monkeypatch.setattr(s, "meta", lambda: {"current_year": 2027})
    return s


def test_store_response_shape(store):
    out = store.roster_optimizer("T", max_swaps=3)
    assert out["team"] == "T" and out["roster_size"] == 4 and out["max_swaps"] == 3
    assert "TO" not in out["categories"] and len(out["categories"]) == 8
    assert set(out["start"]) == set(out["categories"]) == set(out["end"])
    assert 0 <= out["start_matchup_win"] <= 1 and 0 <= out["end_matchup_win"] <= 1
    assert len(out["swaps"]) <= 3
    for sw in out["swaps"]:
        assert sw["score_gain"] >= 0.01
        assert set(sw["category_change"]) == set(out["categories"])
        assert sw["drop"]["name"].startswith("P") and sw["add"]["name"].startswith("P")
    assert out["data_as_of"]["projections"] is not None


def test_store_clamps_max_swaps_to_roster_size(store):
    assert store.roster_optimizer("T", max_swaps=20)["max_swaps"] == 4


def test_store_unknown_team(store):
    with pytest.raises(KeyError):
        store.roster_optimizer("Nobody")
