"""Trade Log: LeagueStore.trades and GET /league/trades."""
from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import dashboard_site.api.app as app_module
from dashboard_site.api.league_store import LeagueStore


@pytest.fixture
def store(tmp_path):
    pd.DataFrame([
        {"Year": 2027, "Platform": "ESPN", "TradeId": "x", "ProposedDate": "2026-11-01", "ResolvedDate": "2026-11-03",
         "Status": "Declined", "Proposer": "Rohil", "Partner": "Fano", "ProposerGives": "A; B", "PartnerGives": "C",
         "VetoVotes": 0, "DetailsAvailable": True, "HasRejectedData": True},
        {"Year": 2027, "Platform": "ESPN", "TradeId": "y", "ProposedDate": "", "ResolvedDate": "2026-11-02",
         "Status": "Declined", "Proposer": "", "Partner": "Juan", "ProposerGives": "", "PartnerGives": "",
         "VetoVotes": 0, "DetailsAvailable": False, "HasRejectedData": True},
        {"Year": 2025, "Platform": "Yahoo", "TradeId": "z", "ProposedDate": "", "ResolvedDate": "2024-11-23",
         "Status": "Completed", "Proposer": "Fano", "Partner": "Ange", "ProposerGives": "D", "PartnerGives": "E; F",
         "VetoVotes": 0, "DetailsAvailable": True, "HasRejectedData": False},
    ]).to_csv(tmp_path / "trades.csv", index=False)

    class FakeStats:
        ref_dir = str(tmp_path)

    s = LeagueStore.__new__(LeagueStore)
    s.store = FakeStats()
    s._trades = None
    return s


def test_store_trades(store):
    out = store.trades()
    assert out["no_rejected_data_years"] == [2025]
    x, y, z = out["trades"]
    assert x["proposer_gives"] == ["A", "B"] and x["partner_gives"] == ["C"] and x["details_available"] is True
    assert y["proposer"] is None and y["proposed_date"] is None and y["proposer_gives"] == [] and y["details_available"] is False
    assert z["platform"] == "Yahoo" and z["partner_gives"] == ["E", "F"]


def test_endpoint(monkeypatch):
    monkeypatch.setattr(app_module.league_store, "trades", lambda: {"trades": [], "no_rejected_data_years": [2024]})
    r = TestClient(app_module.app).get("/league/trades")
    assert r.status_code == 200 and r.json()["no_rejected_data_years"] == [2024]


def test_endpoint_missing_file(monkeypatch):
    def boom():
        raise ValueError("trades.csv not found")
    monkeypatch.setattr(app_module.league_store, "trades", boom)
    assert TestClient(app_module.app).get("/league/trades").status_code == 404
