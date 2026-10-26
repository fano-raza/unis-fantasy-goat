"""/refresh_status: what open pages poll to decide when to re-fetch."""
from __future__ import annotations

from fastapi.testclient import TestClient

import dashboard_site.api.app as app_module

client = TestClient(app_module.app)


def test_refresh_status_shape_and_not_cached():
    r = client.get("/refresh_status")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    body = r.json()
    assert set(body["loaded"]) == set(body["sources"]) == {"live", "draft", "player_stats", "team_summary"}


def test_loaded_follows_reloads_not_file_writes(monkeypatch):
    from datetime import datetime, timezone

    stamp = {"t": datetime(2026, 10, 26, 1, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr(app_module, "_scan_source_mtimes", lambda *a: {"live": stamp["t"], "draft": None,
                                                                       "player_stats": None, "team_summary": None})
    monkeypatch.setattr(app_module, "loaded_sources", {"live": "old", "draft": None, "player_stats": None,
                                                       "team_summary": None})
    # The file changed but the API hasn't reloaded yet: `sources` moves, `loaded` doesn't.
    body = client.get("/refresh_status").json()
    assert body["sources"]["live"] == stamp["t"].isoformat() and body["loaded"]["live"] == "old"
    # After a reload, `loaded` catches up (StatsStore/league store builds stubbed out).
    monkeypatch.setattr(app_module, "StatsStore", lambda: app_module.store)
    monkeypatch.setattr(app_module, "get_league_store", lambda s: app_module.league_store)
    monkeypatch.setattr(app_module, "reset_league_store", lambda: None)
    app_module._refresh_data()
    assert client.get("/refresh_status").json()["loaded"]["live"] == stamp["t"].isoformat()
