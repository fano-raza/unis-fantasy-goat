"""scripts/export_trades.py's ESPN chain logic (offer outcome, teams, players).
Needs the stat-updater deps (constants imports espn_fr -> requests); skipped
in a venv without them."""
from __future__ import annotations

import datetime

import pytest

pytest.importorskip("requests")
from scripts import export_trades as et  # noqa: E402

DAY = 86_400_000


def _item(frm, to, pid):
    return {"type": "TRADE", "fromTeamId": frm, "toTeamId": to, "playerId": pid}


@pytest.fixture
def espn(monkeypatch):
    """Fake 2019 ESPN records: one chain per outcome."""
    t0 = 1_540_000_000_000
    records = [
        # Completed: proposal + executed accept (team 1 Fano proposes to 8 Rohil)
        {"id": "p1", "type": "TRADE_PROPOSAL", "status": "PENDING", "teamId": 1, "proposedDate": t0,
         "items": [_item(1, 8, 10), _item(8, 1, 11)]},
        {"id": "a1", "type": "TRADE_ACCEPT", "status": "EXECUTED", "relatedTransactionId": "p1",
         "processDate": t0 + DAY, "items": [_item(1, 8, 10), _item(8, 1, 11)]},
        # Vetoed: accepted, never executed, a veto vote; proposal gone
        {"id": "a2", "type": "TRADE_ACCEPT", "status": None, "relatedTransactionId": "p2", "proposedDate": t0, "items": []},
        {"id": "v2", "type": "TRADE_VETO", "status": "EXECUTED", "relatedTransactionId": "p2", "teamId": 6},
        # Declined, details gone: only the decline record (team 7 Juan declined)
        {"id": "d3", "type": "TRADE_DECLINE", "status": "EXECUTED", "relatedTransactionId": "p3", "teamId": 7,
         "proposedDate": t0 + 2 * DAY},
        # Canceled: only the cancelled copy survives; includes a drop to FA (team 0)
        {"id": "c4", "type": "TRADE_PROPOSAL", "status": "CANCELED", "relatedTransactionId": "p4", "teamId": 4,
         "proposedDate": t0, "items": [_item(4, 5, 12), _item(5, 4, 13), {"type": "DROP", "fromTeamId": 4, "toTeamId": 0, "playerId": 14}]},
    ]
    monkeypatch.setattr(et, "_session", lambda: None)
    monkeypatch.setattr(et, "_espn_trade_records", lambda s, y, recent_days=None: records)
    monkeypatch.setattr(et, "_espn_player_names", lambda s, y, ids: {i: f"P{i}" for i in ids})


def test_espn_outcomes(espn):
    rows = {r["TradeId"]: r for r in et.espn_trades(2019, today=datetime.date(2026, 11, 4))}
    assert set(rows) == {"p1", "p2", "p3", "p4"}
    p1 = rows["p1"]
    assert p1["Status"] == "Completed" and p1["Proposer"] == "Fano" and p1["Partner"] == "Rohil"
    assert p1["ProposerGives"] == "P10" and p1["PartnerGives"] == "P11" and p1["DetailsAvailable"] is True
    assert rows["p2"]["Status"] == "Vetoed" and rows["p2"]["VetoVotes"] == 1
    p3 = rows["p3"]
    assert p3["Status"] == "Declined" and p3["DetailsAvailable"] is False
    assert p3["Partner"] == "Juan" and p3["Proposer"] == "" and p3["ProposerGives"] == ""
    p4 = rows["p4"]
    assert p4["Status"] == "Canceled" and (p4["Proposer"], p4["Partner"]) == ("Saamrit", "Ange")
    assert p4["ProposerGives"] == "P12"  # the drop to free agency isn't part of the deal
    assert all(r["HasRejectedData"] for r in rows.values())
