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
         "Partner": "Ange", "ProposerGives": "D", "PartnerGives": "E; F"},
    ]).to_csv(tmp_path / "trades.csv", index=False)

    class FakeStats:
        ref_dir = str(tmp_path)

    s = LeagueStore.__new__(LeagueStore)
    s.store = FakeStats()
    s._trades = None
    return s


def test_store_trades(store):
    x, z = store.trades()
    assert x == {"id": "x", "year": 2027, "platform": "ESPN", "date": "2026-11-03", "proposer": "Rohil",
                 "partner": "Fano", "proposer_gives": ["A", "B"], "partner_gives": ["C"]}
    assert z["platform"] == "Yahoo" and z["partner_gives"] == ["E", "F"]


def test_endpoint(monkeypatch):
    monkeypatch.setattr(app_module.league_store, "trades", lambda: [{"id": "x"}])
    r = TestClient(app_module.app).get("/league/trades")
    assert r.status_code == 200 and r.json() == [{"id": "x"}]


def test_endpoint_missing_file(monkeypatch):
    def boom():
        raise ValueError("trades.csv not found")
    monkeypatch.setattr(app_module.league_store, "trades", boom)
    assert TestClient(app_module.app).get("/league/trades").status_code == 404
