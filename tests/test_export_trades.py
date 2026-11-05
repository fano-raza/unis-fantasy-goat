"""scripts/export_trades.py's ESPN logic: only executed trades, with the
offering team, partner and players. Needs the stat-updater deps (constants
imports espn_fr -> requests); skipped in a venv without them."""
from __future__ import annotations

import pytest

pytest.importorskip("requests")
from scripts import export_trades as et  # noqa: E402

DAY = 86_400_000


def _item(frm, to, pid):
    return {"type": "TRADE", "fromTeamId": frm, "toTeamId": to, "playerId": pid}


@pytest.fixture
def espn(monkeypatch):
    """Fake 2019 ESPN records: one completed trade plus offers that weren't."""
    t0 = 1_540_000_000_000
    records = [
        # Completed: Saamrit (4) offered; the executed accept includes a drop to FA (team 0).
        {"id": "p1", "type": "TRADE_PROPOSAL", "status": "PENDING", "teamId": 4, "proposedDate": t0,
         "items": [_item(4, 5, 10), _item(5, 4, 11)]},
        {"id": "a1", "type": "TRADE_ACCEPT", "status": None, "relatedTransactionId": "p1", "items": [_item(4, 5, 10)]},
        {"id": "a1x", "type": "TRADE_ACCEPT", "status": "EXECUTED", "relatedTransactionId": "p1", "processDate": t0 + DAY,
         "items": [_item(4, 5, 10), _item(5, 4, 11), {"type": "DROP", "fromTeamId": 4, "toTeamId": 0, "playerId": 12}]},
        # Completed, but the executed accept has no player list (common in
        # 2020-21): players come from the sibling accept / proposal.
        {"id": "p5", "type": "TRADE_PROPOSAL", "status": "PENDING", "teamId": 1, "items": [_item(1, 8, 40), _item(8, 1, 41)]},
        {"id": "a5", "type": "TRADE_ACCEPT", "status": "EXECUTED", "relatedTransactionId": "p5", "processDate": t0, "items": []},
        # Accepted but vetoed (never executed)
        {"id": "a2", "type": "TRADE_ACCEPT", "status": None, "relatedTransactionId": "p2", "items": [_item(1, 8, 20), _item(8, 1, 21)]},
        {"id": "v2", "type": "TRADE_VETO", "status": "EXECUTED", "relatedTransactionId": "p2"},
        # Declined / cancelled
        {"id": "d3", "type": "TRADE_DECLINE", "status": "EXECUTED", "relatedTransactionId": "p3", "teamId": 7},
        {"id": "c4", "type": "TRADE_PROPOSAL", "status": "CANCELED", "relatedTransactionId": "p4", "teamId": 4,
         "items": [_item(4, 5, 30), _item(5, 4, 31)]},
    ]
    monkeypatch.setattr(et, "_session", lambda: None)
    monkeypatch.setattr(et, "_espn_trade_records", lambda s, y: records)
    monkeypatch.setattr(et, "_espn_player_names", lambda s, y, ids: {i: f"P{i}" for i in ids})


def test_only_completed_trades(espn):
    rows = {r["TradeId"]: r for r in et.espn_trades(2019)}
    assert set(rows) == {"p1", "p5"}
    assert (rows["p5"]["Proposer"], rows["p5"]["ProposerGives"], rows["p5"]["PartnerGives"]) == ("Fano", "P40", "P41")
    r = rows["p1"]
    assert r["TradeId"] == "p1" and r["Date"]
    assert (r["Proposer"], r["Partner"]) == ("Saamrit", "Ange")
    assert r["ProposerGives"] == "P10" and r["PartnerGives"] == "P11"  # the drop isn't part of the deal
