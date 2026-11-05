"""Trade Log (completed trades): LeagueStore.trades and GET /league/trades."""
from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import dashboard_site.api.app as app_module
from dashboard_site.api.league_store import LeagueStore


@pytest.fixture
def store(tmp_path):
    pd.DataFrame([
        {"Year": 2027, "Platform": "ESPN", "TradeId": "x", "Date": "2026-11-03", "Proposer": "Rohil",
         "Partner": "Fano", "ProposerGives": "A; B", "PartnerGives": "C"},
        {"Year": 2025, "Platform": "Yahoo", "TradeId": "z", "Date": "2024-11-23", "Proposer": "Fano",
         "Partner": "Ange", "ProposerGives": "D", "PartnerGives": "E; F", "ProposerValue": 120.5,
         "PartnerValue": 80.0, "Winner": "Fano",
         "ValueDetail": '[{"player": "E", "team": "Fano", "games": 30, "value": 120.5}]'},
    ]).to_csv(tmp_path / "trades.csv", index=False)

    class FakeStats:
        ref_dir = str(tmp_path)

    s = LeagueStore.__new__(LeagueStore)
    s.store = FakeStats()
    s._trades = None
    s.meta = lambda: {"current_year": 2027}
    return s


def test_store_trades(store):
    x, z = store.trades()
    assert x == {"id": "x", "year": 2027, "platform": "ESPN", "date": "2026-11-03", "proposer": "Rohil",
                 "partner": "Fano", "proposer_gives": ["A", "B"], "partner_gives": ["C"],
                 "proposer_value": None, "partner_value": None, "winner": None,
                 "proposer_wins_added": None, "partner_wins_added": None, "top_player": None,
                 "top_player_team": None, "top_player_wins_added": None, "players": [], "final": False}
    assert z["platform"] == "Yahoo" and z["partner_gives"] == ["E", "F"]
    assert (z["proposer_value"], z["partner_value"], z["winner"]) == (120.5, 80.0, "Fano")
    assert z["players"] == [{"player": "E", "team": "Fano", "games": 30, "value": 120.5}]


def test_endpoint(monkeypatch):
    monkeypatch.setattr(app_module.league_store, "trades", lambda: [{"id": "x"}])
    r = TestClient(app_module.app).get("/league/trades")
    assert r.status_code == 200 and r.json() == [{"id": "x"}]


def test_endpoint_missing_file(monkeypatch):
    def boom():
        raise ValueError("trades.csv not found")
    monkeypatch.setattr(app_module.league_store, "trades", boom)
    assert TestClient(app_module.app).get("/league/trades").status_code == 404


def test_team_trade_stats(tmp_path):
    rows = [  # (year, proposer, partner)
        (2019, "Fano", "Juan"), (2020, "Juan", "Amil"), (2020, "Juan", "Fano"),
        (2021, "Ange", "Juan"), (2023, "Juan", "Amil; Ange"),
    ]
    pd.DataFrame([
        {"Year": y, "Platform": "ESPN", "TradeId": str(i), "Date": f"{y}-01-01", "Proposer": a, "Partner": b,
         "ProposerGives": "X", "PartnerGives": "Y"}
        for i, (y, a, b) in enumerate(rows)
    ]).to_csv(tmp_path / "trades.csv", index=False)
    pd.DataFrame([{"Team": "Juan"}, {"Team": "Sai"}]).to_csv(tmp_path / "team_summary.csv", index=False)

    class FakeStats:
        ref_dir = str(tmp_path)

    s = LeagueStore.__new__(LeagueStore)
    s.store = FakeStats()
    s._trades = None
    s._team_summary_df = None
    s.meta = lambda: {"current_year": 2027}
    stats = s.team_trade_stats()
    assert stats["Juan"] == {
        "Trades": 5, "Trades Won": 0, "Most Trades in a Season": 2, "Most Trades in a Season Years": "2020",
        "Consecutive Seasons with a Trade": 3, "Consecutive Seasons with a Trade Years": "2019–2021",
    }
    # Each team in a multi-team trade counts it; ties list every run.
    assert stats["Ange"]["Trades"] == 2 and stats["Ange"]["Consecutive Seasons with a Trade Years"] == "2021, 2023"
    juan, sai = s.team_summary()
    assert juan["Trades"] == 5 and sai["Trades"] == 0 and sai["Most Trades in a Season Years"] is None
