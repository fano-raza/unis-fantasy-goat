"""Trade Hub premium endpoints: LeagueStore.trade_odds / trade_recommend and
their /league/trade_odds, /league/trade_recommend routes. Run from the repo
root:  .venv-dashboard/bin/python -m pytest tests/ -q
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from dashboard_site.api import app as app_module
from shared import roster_optimizer as ro
from shared import trade_finder as tf
from tests.test_roster_optimizer_api import store  # noqa: F401  (fixture: teams A, B, C, T; P1-P16 + 10 FAs)

client = TestClient(app_module.app)
CFG = ro.recommended_config(max_swaps=0)


def reference_matchup_win(s, team, sends_a, sends_b, team_a, team_b, drops=()):
    """Independent check: rebuild the post-trade rosters by hand and let
    ro.optimize score them from scratch."""
    _, rosters, _, players, n2i = s._optimizer_inputs()
    new = {t: list(ids) for t, ids in rosters.items()}
    for n in sends_a:
        pid = n2i[n]
        for ids in new.values():
            if pid in ids:
                ids.remove(pid)
        new[team_b].append(pid)
    for n in sends_b:
        pid = n2i[n]
        for ids in new.values():
            if pid in ids:
                ids.remove(pid)
        new[team_a].append(pid)
    for t, n in drops:
        new[t].remove(n2i[n])
    # A team left short (the open spot in a 2-for-1) loses that player's
    # stats -- it isn't scaled back up to a full roster. (Every fixture team
    # starts at the common size, so its original scale is 1.0.)
    short = {t for t in new if len(new[t]) != len(rosters[t])}
    return ro.optimize(team, players, new, [], CFG, unscaled_teams=short).start_matchup_win


def test_no_trade_changes_nothing(store):  # noqa: F811
    o = store.trade_odds("A", "B", [], [])
    for side in o["teams"]:
        assert side["matchup_win"] == side["start_matchup_win"]
        assert side["after"] == side["start"]


def test_one_for_one_matches_the_optimizer_for_both_teams(store):  # noqa: F811
    o = store.trade_odds("A", "B", ["P1"], ["P5"])
    a, b = o["teams"]
    assert (a["sends"], a["receives"], b["sends"], b["receives"]) == (["P1"], ["P5"], ["P5"], ["P1"])
    assert a["matchup_win"] == pytest.approx(reference_matchup_win(store, "A", ["P1"], ["P5"], "A", "B"), abs=1e-4)
    assert b["matchup_win"] == pytest.approx(reference_matchup_win(store, "B", ["P1"], ["P5"], "A", "B"), abs=1e-4)
    assert a["start_matchup_win"] == pytest.approx(ro.optimize("A", *store._optimizer_inputs()[3:4],
                                                               store._optimizer_inputs()[1], [], CFG).start_matchup_win, abs=1e-4)
    assert set(a["start"]) == {c for c in ro.MAIN_CATS if c != "TO"}


def test_two_for_one_receiver_releases_one_of_its_own(store):  # noqa: F811
    o = store.trade_odds("A", "B", ["P1", "P2"], ["P5"])
    a, b = o["teams"]
    assert a["active_after"] == 3 and b["active_after"] == b["active_before"] == 4
    assert b["auto_drop"] and len(b["drops"]) == 1 and b["drops"][0] in {"P6", "P7", "P8"}
    assert b["matchup_win"] == pytest.approx(
        reference_matchup_win(store, "B", ["P1", "P2"], ["P5"], "A", "B", drops=[("B", b["drops"][0])]), abs=1e-4)
    # The auto drop is the one B misses least (by its score).
    _, rosters, _, players, n2i = store._optimizer_inputs()
    def b_score(d):
        new = {t: list(ids) for t, ids in rosters.items()}
        new["A"] = [p for p in new["A"] if p not in (n2i["P1"], n2i["P2"])] + [n2i["P5"]]
        new["B"] = [p for p in new["B"] if p not in (n2i["P5"], n2i[d])] + [n2i["P1"], n2i["P2"]]
        return ro.optimize("B", players, new, [], CFG, unscaled_teams={"A"}).start_objective
    assert b["drops"][0] == max(["P6", "P7", "P8"], key=b_score)


def test_explicit_drop_is_respected(store):  # noqa: F811
    o = store.trade_odds("A", "B", ["P1", "P2"], ["P5"], drops={"B": ["P8"]})
    assert o["teams"][1]["drops"] == ["P8"] and not o["teams"][1]["auto_drop"]


def test_free_agent_pickup_fills_the_open_spot(store):  # noqa: F811
    o = store.trade_odds("A", "B", ["P1", "P2"], ["P5", "P17"])  # P17 is a free agent -> joins A
    a, b = o["teams"]
    assert a["receives"] == ["P5", "P17"] and a["active_after"] == 4
    assert b["active_after"] == 4


def test_errors_and_unknown_names(store):  # noqa: F811
    with pytest.raises(ValueError):
        store.trade_odds("A", "A", [], [])
    with pytest.raises(KeyError):
        store.trade_odds("A", "Nobody", [], [])
    with pytest.raises(ValueError):
        store.trade_odds("A", "B", ["P1"], ["P1"])
    assert store.trade_odds("A", "B", ["Not A Player"], [])["unknown"] == ["Not A Player"]


def test_recommendation_follows_the_pick_rules(store):  # noqa: F811
    _, rosters, fas, players, n2i = store._optimizer_inputs()
    for team_b in ["B", None]:
        r = store.trade_recommend("A", team_b)
        assert r["kind"] in {"fair", "least_lopsided", "none"}
        if r["kind"] == "none":
            continue
        t = r["trade"]
        if team_b:
            assert t["partner"] == team_b
        # Re-derive the finder's view of the same trade.
        cands = tf.find_trades("A", [n2i[n] for n in t["give"]][:2], players, rosters, fas,
                               tf.TradeConfig(mode="fleece", partner_min_gain=-1.0, max_results=None,
                                              partners=(t["partner"],))).trades
        match = [c for c in cands if [players.at[g, "Player"] for g in c.get] == t["get"]
                 and sorted(players.at[g, "Player"] for g in c.give) == sorted(t["give"])]
        assert match and match[0].gain >= 0.01
        if r["kind"] == "fair":
            assert match[0].partner_gain >= 0.01
        assert [s["team"] for s in r["odds"]["teams"]] == ["A", t["partner"]]


def test_recommendation_respects_picked_players(store):  # noqa: F811
    r = store.trade_recommend("A", None, ["P1"])
    if r["trade"]:
        assert "P1" in r["trade"]["give"]
    with pytest.raises(ValueError):
        store.trade_recommend("A", None, ["P5"])  # not A's player


# --- routes -------------------------------------------------------------------

def test_routes_require_the_password(monkeypatch):
    monkeypatch.delenv("ROSTER_OPTIMIZER_PASSWORD", raising=False)
    assert client.post("/league/trade_odds", json={"password": "x", "team_a": "A", "team_b": "B"}).status_code == 503
    monkeypatch.setenv("ROSTER_OPTIMIZER_PASSWORD", "secret")
    assert client.post("/league/trade_odds", json={"password": "x", "team_a": "A", "team_b": "B"}).status_code == 401
    assert client.post("/league/trade_recommend", json={"password": "x", "team_a": "A"}).status_code == 401


def test_routes_pass_requests_through(monkeypatch):
    monkeypatch.setenv("ROSTER_OPTIMIZER_PASSWORD", "secret")
    seen = []
    monkeypatch.setattr(app_module.league_store, "trade_odds", lambda *a: seen.append(a) or {"ok": 1})
    monkeypatch.setattr(app_module.league_store, "trade_recommend", lambda *a: seen.append(a) or {"ok": 2})
    r = client.post("/league/trade_odds", json={"password": "secret", "team_a": "A", "team_b": "B",
                                                 "a_sends": ["P1"], "b_sends": ["P5"]})
    assert r.json() == {"ok": 1} and seen[-1] == ("A", "B", ["P1"], ["P5"], None)
    r = client.post("/league/trade_recommend", json={"password": "secret", "team_a": "A", "give": ["P1"]})
    assert r.json() == {"ok": 2} and seen[-1] == ("A", None, ["P1"])
    assert client.post("/league/trade_recommend", json={"password": "secret", "team_a": "A",
                                                        "give": ["P1", "P2", "P3"]}).status_code == 422


def test_route_errors_map_to_status_codes(monkeypatch):
    monkeypatch.setenv("ROSTER_OPTIMIZER_PASSWORD", "secret")

    def missing(*a):
        raise KeyError("no roster")

    def bad(*a):
        raise ValueError("bad")

    monkeypatch.setattr(app_module.league_store, "trade_odds", missing)
    assert client.post("/league/trade_odds", json={"password": "secret", "team_a": "A", "team_b": "Z"}).status_code == 404
    monkeypatch.setattr(app_module.league_store, "trade_recommend", bad)
    assert client.post("/league/trade_recommend", json={"password": "secret", "team_a": "A"}).status_code == 422


# --- recommendation cache + warm-up ----------------------------------------

def test_recommendations_are_cached_until_the_data_changes(store, monkeypatch):  # noqa: F811
    from dashboard_site.api import league_store as ls_module
    ls_module._TRADE_REC_CACHE.clear()
    calls = []
    real = tf.find_trades
    monkeypatch.setattr(tf, "find_trades", lambda *a, **k: calls.append(1) or real(*a, **k))
    first = store.trade_recommend("A")
    again = store.trade_recommend("A")
    assert again == first and len(calls) == 1          # served from the cache
    again["kind"] = "tampered"                          # callers get copies
    assert store.trade_recommend("A")["kind"] == first["kind"]
    # A roster move changes the key -> searched again.
    _, rosters, *_ = store._optimizer_inputs()
    rosters_moved = {t: list(ids) for t, ids in rosters.items()}
    rosters_moved["A"] = rosters_moved["A"][::-1][:3]
    assert store._trade_data_key(rosters_moved) != store._trade_data_key(rosters)


def test_warm_up_fills_every_team_once(store):  # noqa: F811
    from dashboard_site.api import league_store as ls_module
    ls_module._TRADE_REC_CACHE.clear()
    assert store.warm_trade_recommendations(pause_seconds=0) == 4
    assert store.warm_trade_recommendations(pause_seconds=0) == 0   # nothing left to do
