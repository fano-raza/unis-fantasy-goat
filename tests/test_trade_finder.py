"""Tests for shared/trade_finder.py (Phase 7). Run from the repo root:
    .venv-dashboard/bin/python -m pytest tests/ -q

The reference for every score is ro.optimize itself (max_swaps=0 just scores
the given rosters), recomputing the whole league from scratch per trade.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from shared import roster_optimizer as ro
from shared import trade_finder as tf
from tests.test_roster_optimizer import random_league

SCORE_CFG = ro.recommended_config(max_swaps=0)


def ref_score(team, players, rosters):
    return ro.optimize(team, players, rosters, [], SCORE_CFG).start_objective


def apply(rosters, team, partner, give, get, drop=None, fa=None):
    out = {t: list(ids) for t, ids in rosters.items()}
    out[team] = [p for p in out[team] if p not in give] + list(get) + ([fa] if fa is not None else [])
    out[partner] = [p for p in out[partner] if p not in get] + list(give)
    if drop is not None:
        out[partner].remove(drop)
    return out


def with_availability(players):
    p = players.copy()
    p["availability"] = 1.0
    return p


@pytest.fixture(scope="module")
def small_league():
    players, rosters, fas = random_league(np.random.default_rng(3), teams=4, per_team=6, free_agents=8)
    return players, rosters, fas


def all_trades(team, give, players, rosters, fas, mode, fa_weight=1.0):
    # fa_weight=1.0: scores must equal ro.optimize's exactly (the brute-force reference)
    return tf.find_trades(team, give, players, rosters, fas,
                          tf.TradeConfig(mode=mode, max_results=None, fa_shortlist=50, fa_weight=fa_weight))


def test_base_scores_match_the_optimizer(small_league):
    players, rosters, fas = small_league
    res = all_trades("t0", [rosters["t0"][0]], players, rosters, fas, "fleece")
    for t in rosters:
        assert res.score[t] == pytest.approx(ref_score(t, players, rosters), abs=1e-9)


@pytest.mark.parametrize("mode", ["fair", "fleece"])
def test_every_trade_is_scored_like_the_optimizer_for_both_teams(small_league, mode):
    players, rosters, fas = small_league
    seen = 0
    for team in rosters:
        for x in rosters[team][:3]:
            for t in all_trades(team, [x], players, rosters, fas, mode).trades:
                after = apply(rosters, team, t.partner, t.give, t.get, t.partner_drop, t.fa_add)
                assert t.score_after == pytest.approx(ref_score(team, players, after), abs=1e-9)
                assert t.partner_score_after == pytest.approx(ref_score(t.partner, players, after), abs=1e-9)
                seen += 1
    assert seen > 0


def brute_force(team, give, players, rosters, fas, mode, tolerance=0.0):
    """Every 1-for-1 / 2-for-1 the finder should return, by recomputing the
    league with ro.optimize for every candidate, partner drop and free agent.
    While the partner picks its drop, your open spot holds a zero-line
    placeholder (the finder keeps each team's roster scale fixed)."""
    min_you, min_partner = tf.MODES[mode]
    rostered = pd.Index([p for ids in rosters.values() for p in ids])
    values = tf.player_value(players[ro.COMPONENTS], rostered)
    shortlist = sorted(fas, key=lambda q: -values[q])[:50]
    p0 = pd.concat([players, pd.DataFrame({c: [0.0] for c in ro.COMPONENTS}, index=["EMPTY"]).assign(Player="EMPTY")])
    base = {t: ref_score(t, players, rosters) for t in rosters}
    out = set()
    shapes = [("1-for-1", [give])] if len(give) == 1 else []
    pairs = [give] if len(give) == 2 else [[give[0], o] for o in rosters[team] if o != give[0]]
    shapes.append(("2-for-1", pairs))
    for shape, gives in shapes:
        for gv in gives:
            for B in rosters:
                if B == team:
                    continue
                for y in rosters[B]:
                    drop = fa = None
                    if shape == "2-for-1":
                        tmp = apply(rosters, team, B, gv, [y], fa="EMPTY")
                        drops = [d for d in tmp[B] if d not in gv]
                        drop = max(drops, key=lambda d: ref_score(B, p0, {**tmp, B: [p for p in tmp[B] if p != d]}))
                        fa = max(shortlist, key=lambda f: ref_score(team, players, apply(rosters, team, B, gv, [y], drop, f)))
                    after = apply(rosters, team, B, gv, [y], drop, fa)
                    g, pg = ref_score(team, players, after) - base[team], ref_score(B, players, after) - base[B]
                    net = sum(values[p] for p in gv) - (values[drop] if drop is not None else 0.0) - values[y]
                    if g >= min_you and pg >= min_partner and net >= -tolerance:
                        out.add((shape, B, tuple(gv), y, drop, fa))
    return out


@pytest.mark.parametrize("mode", ["fair", "fleece"])
@pytest.mark.parametrize("seed", [3, 11])
def test_finder_matches_brute_force(mode, seed):
    players, rosters, fas = random_league(np.random.default_rng(seed), teams=4, per_team=6, free_agents=8)
    for team in ["t0", "t2"]:
        for give in ([rosters[team][1]], rosters[team][2:4]):
            got = {(t.shape, t.partner, tuple(t.give), t.get[0], t.partner_drop, t.fa_add)
                   for t in all_trades(team, give, players, rosters, fas, mode).trades}
            assert got == brute_force(team, give, players, rosters, fas, mode)


def test_modes_apply_their_thresholds(small_league):
    players, rosters, fas = small_league
    for team in rosters:
        for x in rosters[team]:
            for t in all_trades(team, [x], players, rosters, fas, "fair").trades:
                assert t.gain >= 0.01 and t.partner_gain >= 0.01
            for t in all_trades(team, [x], players, rosters, fas, "fleece").trades:
                assert t.gain >= 0.01 and t.partner_gain >= -0.01


def test_fair_trades_are_a_subset_of_fleece(small_league):
    players, rosters, fas = small_league
    key = lambda t: (t.shape, t.partner, tuple(t.give), tuple(t.get))  # noqa: E731
    for x in rosters["t1"]:
        fair = {key(t) for t in all_trades("t1", [x], players, rosters, fas, "fair").trades}
        fleece = {key(t) for t in all_trades("t1", [x], players, rosters, fas, "fleece").trades}
        assert fair <= fleece


def test_lopsided_trades_are_never_returned(small_league):
    players, rosters, fas = small_league
    for team in rosters:
        for x in rosters[team]:
            res = all_trades(team, [x], players, rosters, fas, "fleece")
            for t in res.trades:
                assert t.partner_value_net >= 0


def test_lopsided_filter_removes_the_star_for_scrub_trade():
    """The model alone would take a star for a scrub when the star's team
    doesn't need him in its categories; the value check must stop it."""
    players, rosters, fas = random_league(np.random.default_rng(5), teams=4, per_team=6, free_agents=8)
    players = players.copy()
    star, scrub = rosters["t1"][0], rosters["t0"][0]
    players.loc[star, ro.COMPONENTS] = players.loc[star, ro.COMPONENTS] * 2.5
    players.loc[scrub, ro.COMPONENTS] = players.loc[scrub, ro.COMPONENTS] * 0.3
    loose = tf.find_trades("t0", [scrub], players, rosters, fas,
                           tf.TradeConfig(mode="fleece", max_results=None, value_tolerance=1e9, shapes=("1-for-1",)))
    strict = tf.find_trades("t0", [scrub], players, rosters, fas,
                            tf.TradeConfig(mode="fleece", max_results=None, shapes=("1-for-1",)))
    assert all(t.get != [star] for t in strict.trades)
    assert all(t.partner_value_net >= 0 for t in strict.trades)
    assert len(strict.trades) <= len(loose.trades)


def test_sorted_by_your_gain(small_league):
    players, rosters, fas = small_league
    res = all_trades("t0", [rosters["t0"][2]], players, rosters, fas, "fleece")
    gains = [t.gain for t in res.trades]
    assert gains == sorted(gains, reverse=True)


def test_two_picked_players_only_search_that_pair(small_league):
    players, rosters, fas = small_league
    pair = rosters["t0"][:2]
    res = all_trades("t0", pair, players, rosters, fas, "fleece")
    assert all(t.shape == "2-for-1" and sorted(t.give) == sorted(pair) for t in res.trades)


def test_injured_and_unsigned_free_agents_never_fill_the_open_spot(small_league):
    players, rosters, fas = small_league
    players = players.copy()
    players["InjuryStatus"] = "ACTIVE"
    players["NBATeam"] = "XXX"
    players.loc[fas[:3], "InjuryStatus"] = "OUT"
    players.loc[fas[3:5], "NBATeam"] = "FA"
    for x in rosters["t0"]:
        for t in all_trades("t0", [x], players, rosters, fas, "fleece").trades:
            assert t.fa_add is None or t.fa_add in fas[5:]


def test_bad_give_is_rejected(small_league):
    players, rosters, fas = small_league
    with pytest.raises(ValueError):
        tf.find_trades("t0", [rosters["t1"][0]], players, rosters, fas)
    with pytest.raises(ValueError):
        tf.find_trades("t0", rosters["t0"][:3], players, rosters, fas)
    with pytest.raises(KeyError):
        tf.find_trades("nobody", [rosters["t0"][0]], players, rosters, fas)


def test_availability_is_applied(small_league):
    players, rosters, fas = small_league
    a = tf.find_trades("t0", [rosters["t0"][0]], players, rosters, fas, tf.TradeConfig(mode="fleece", max_results=None))
    b = tf.find_trades("t0", [rosters["t0"][0]], with_availability(players), rosters, fas,
                       tf.TradeConfig(mode="fleece", max_results=None))
    assert a.score == pytest.approx(b.score)


# ---------------------------------------------------------------------------
# Backtest helpers (scripts/backtest_trade_finder.py)
# ---------------------------------------------------------------------------

def test_backtest_moves_players_on_every_later_day():
    from scripts.backtest_trade_finder import moved
    daily = {10: [1, 2, 3], 11: [1, 3, 4]}  # player 2 already gone on day 11
    assert moved(daily, [(2, 9), (3, 8)]) == {10: [1, 9, 8], 11: [1, 8, 4]}
    # roster sizes never change, even when the leaving player is already gone
    assert all(len(v) == len(daily[k]) for k, v in moved(daily, [(2, 9)]).items())


def test_backtest_trade_changes_cover_both_sides_of_a_two_for_one():
    from scripts.backtest_trade_finder import trade_changes
    t = tf.Trade("2-for-1", "B", [1, 2], [7], 8, 50, 0.02, 0.01, 0.6, 0.5, 0.5, 0.4, 1.0, 0.5, 0.2)
    assert trade_changes("A", t) == {"A": [(1, 7), (2, 50)], "B": [(7, 1), (8, 2)]}


def test_free_agent_weight_discounts_only_your_pickup(small_league):
    players, rosters, fas = small_league
    x = rosters["t0"][0]
    full = {(tuple(t.give), t.get[0], t.partner): t for t in all_trades("t0", [x], players, rosters, fas, "fleece")
            .trades if t.shape == "2-for-1"}
    cut = {(tuple(t.give), t.get[0], t.partner): t for t in tf.find_trades(
        "t0", [x], players, rosters, fas, tf.TradeConfig(mode="fleece", max_results=None, fa_shortlist=50,
                                                        min_gain=-1, partner_min_gain=-1, fa_weight=0.7)).trades
        if t.shape == "2-for-1"}
    common = set(full) & set(cut)
    assert common
    for k in common:
        assert cut[k].gain < full[k].gain            # your pickup counts for less
        if cut[k].fa_add == full[k].fa_add:          # same pickup -> partner scored identically
            assert cut[k].partner_gain == pytest.approx(full[k].partner_gain, abs=1e-12)


def test_default_config_is_the_backtested_one():
    assert tf.TradeConfig().fa_weight == 0.7


# ---------------------------------------------------------------------------
# shared/projection_adjust.py
# ---------------------------------------------------------------------------

def test_projection_adjust_params_load_and_zero_coefs_are_identity():
    from shared import projection_adjust as pa
    params = pa.load_params()
    assert set(params["coefs"]) == set(pa.COMP)
    blend = pd.DataFrame({c: [1.0, 2.0] for c in pa.COMP}, index=[1, 2])
    blend["FGA"], blend["FTA"] = 3.0, 3.0
    games = pd.DataFrame({"PlayerId": [1, 1, 2], "ScoringPeriod": [1, 2, 2],
                          **{c: [1.0, 2.0, 3.0] for c in pa.COMP}, "MIN": [20.0, 30.0, 25.0], "GS": [0.0, 1.0, 1.0]})
    feats = pa.features(blend, pa.windows(games, 10, blend.index), pd.Series([22.0, 25.0], index=[1, 2]))
    zero = {c: np.zeros(len(pa.FEATURES)) for c in pa.COMP}
    pd.testing.assert_frame_equal(pa.correct(blend, feats, zero)[pa.COMP], blend[pa.COMP])
    adj = pa.adjusted_players(blend, games, 10, pd.Series([22.0, 25.0], index=[1, 2]), params)
    assert (adj[pa.COMP] >= 0).all().all()
    assert (adj["FGM"] <= adj["FGA"]).all() and (adj["FTM"] <= adj["FTA"]).all()


def test_uncertainty_shrinks_with_games_played():
    from shared import projection_adjust as pa
    params = pa.load_params()
    blend = pd.DataFrame({c: [10.0, 10.0] for c in pa.COMP}, index=[1, 2])
    sd = pa.uncertainty(blend, pd.Series([0, 40], index=[1, 2]), params["uncertainty"])
    assert (sd.loc[1, ["PTS", "REB", "AST"]] > sd.loc[2, ["PTS", "REB", "AST"]]).all()


def test_game_log_export_keeps_this_season_and_picks_the_minutes_prior():
    from scripts.export_player_game_logs import parse
    game = lambda season, sp, gp=1: {"seasonId": season, "statSourceId": 0, "statSplitTypeId": 5, "scoringPeriodId": sp,
                                     "stats": {"42": gp, "0": 20.0, "40": 30.0, "41": 1.0}}
    players = [
        {"id": 1, "stats": [game(2027, 3), game(2026, 150), game(2027, 4, gp=None),
                            {"seasonId": 2027, "statSourceId": 1, "statSplitTypeId": 0, "stats": {"40": 2400.0, "42": 80.0}},
                            {"seasonId": 2026, "statSourceId": 0, "statSplitTypeId": 0, "stats": {"40": 1000.0, "42": 50.0}}]},
        {"id": 2, "stats": [{"seasonId": 2026, "statSourceId": 0, "statSplitTypeId": 0, "stats": {"40": 1000.0, "42": 50.0}}]},
    ]
    games, prior = parse(players, 2027)
    assert games[["PlayerId", "ScoringPeriod"]].values.tolist() == [[1, 3]]   # last season + DNP days dropped
    assert games.loc[0, "MIN"] == 30.0 and games.loc[0, "GS"] == 1.0
    p = prior.set_index("PlayerId")
    assert p.loc[1, "prior_MPG"] == 30.0 and p.loc[1, "prior_source"] == "projection"
    assert p.loc[2, "prior_MPG"] == 20.0 and p.loc[2, "prior_source"] == "last_season"
