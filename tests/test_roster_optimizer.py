"""Tests for shared/roster_optimizer.py (Phase 6). Run from the repo root:
    .venv-dashboard/bin/python -m pytest tests/ -q
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
import pytest

from shared import roster_optimizer as ro
from shared.weighted_rank import aggregate_rating

C = ro.COMPONENTS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def stats_row(pid, name, gp, line=None, window="season"):
    """One Ref/player_stats.csv-shaped row from a per-game component line."""
    line = line or {c: 0.0 for c in C}
    row = {"PlayerId": pid, "Player": name, f"{window}_GP": gp}
    row[f"{window}_FG%_made"] = line["FGM"] * gp
    row[f"{window}_FG%_att"] = line["FGA"] * gp
    row[f"{window}_FT%_made"] = line["FTM"] * gp
    row[f"{window}_FT%_att"] = line["FTA"] * gp
    for cat in ["3PTM", "REB", "AST", "STL", "BLK", "TO", "PTS"]:
        row[f"{window}_{cat}_avg"] = line[cat] if gp else None
    return row


def proj_row(pid, proj=None, last=None, last_gp=0):
    row = {"PlayerId": pid, "last_GP": last_gp}
    for c in C:
        row[f"proj_{c}"] = proj[c] if proj else None
        row[f"last_{c}"] = last[c] if last else None
    return row


def line(**kw):
    base = {c: 0.0 for c in C}
    base.update(kw)
    return base


def players_frame(lines: dict) -> pd.DataFrame:
    """Blended-players-shaped frame straight from per-game lines."""
    df = pd.DataFrame.from_dict(lines, orient="index")[C]
    df.insert(0, "Player", [str(i) for i in df.index])
    return df


# ---------------------------------------------------------------------------
# 1. Blending
# ---------------------------------------------------------------------------

REAL = line(FGM=10, FGA=20, FTM=4, FTA=5, **{"3PTM": 3}, REB=8, AST=6, STL=2, BLK=1, TO=3, PTS=30)
PROJ = line(FGM=6, FGA=12, FTM=2, FTA=3, **{"3PTM": 1}, REB=4, AST=2, STL=1, BLK=0.5, TO=2, PTS=16)
LAST = line(FGM=8, FGA=16, FTM=3, FTA=4, **{"3PTM": 2}, REB=6, AST=4, STL=1.5, BLK=1, TO=2.5, PTS=22)


def test_real_weight_is_gp_over_gp_plus_k():
    stats = pd.DataFrame([stats_row(1, "a", 15, REAL)])
    proj = pd.DataFrame([proj_row(1, PROJ)])
    out = ro.blend_players(stats, proj, ro.OptimizerConfig(k_games=15)).loc[1]
    assert out["w_real"] == pytest.approx(0.5)
    for c in C:
        assert out[c] == pytest.approx(0.5 * REAL[c] + 0.5 * PROJ[c])


def test_two_games_is_mostly_projection():
    stats = pd.DataFrame([stats_row(1, "a", 2, REAL)])
    proj = pd.DataFrame([proj_row(1, PROJ)])
    out = ro.blend_players(stats, proj).loc[1]
    assert out["w_real"] == pytest.approx(2 / 17)
    assert out["PTS"] == pytest.approx(2 / 17 * 30 + 15 / 17 * 16)


def test_no_games_is_pure_prior():
    stats = pd.DataFrame([stats_row(1, "a", 0)])
    proj = pd.DataFrame([proj_row(1, PROJ)])
    out = ro.blend_players(stats, proj).loc[1]
    assert out["w_real"] == 0
    for c in C:
        assert out[c] == pytest.approx(PROJ[c])


def test_last_season_small_weight_scaled_by_sample():
    cfg = ro.OptimizerConfig(last_season_weight=0.2, last_season_full_gp=20)
    stats = pd.DataFrame([stats_row(1, "full", 0), stats_row(2, "half", 0)])
    proj = pd.DataFrame([proj_row(1, PROJ, LAST, last_gp=60), proj_row(2, PROJ, LAST, last_gp=10)])
    out = ro.blend_players(stats, proj, cfg)
    assert out.loc[1, "PTS"] == pytest.approx(0.8 * 16 + 0.2 * 22)
    assert out.loc[2, "PTS"] == pytest.approx(0.9 * 16 + 0.1 * 22)
    assert out.loc[1, "prior"] == "proj+last"


def test_last_season_only_when_no_projection():
    stats = pd.DataFrame([stats_row(1, "a", 0)])
    proj = pd.DataFrame([proj_row(1, None, LAST, last_gp=50)])
    out = ro.blend_players(stats, proj).loc[1]
    assert out["prior"] == "last"
    assert out["PTS"] == pytest.approx(22)


def test_small_last_season_sample_shrinks_toward_replacement():
    # 6 games last season -> trust 6/20 = 0.3; replacement = pool median (8 PTS).
    stats = pd.DataFrame([stats_row(i, str(i), 0) for i in (1, 2, 3, 9)])
    proj = pd.DataFrame(
        [proj_row(1, line(PTS=6, FGA=5, FGM=2)), proj_row(2, line(PTS=8, FGA=6, FGM=3)),
         proj_row(3, line(PTS=20, FGA=15, FGM=7)), proj_row(9, None, line(PTS=16, FGA=12, FGM=6), last_gp=6)]
    )
    out = ro.blend_players(stats, proj).loc[9]
    assert out["prior"] == "last"
    assert out["PTS"] == pytest.approx(0.3 * 16 + 0.7 * 8)


def test_no_prior_one_big_game_shrinks_to_replacement_level():
    # Player 9: no projection, no last season, one 50-point game. Replacement
    # level = median projection of the pool (players 1-3).
    stats = pd.DataFrame(
        [stats_row(i, str(i), 0) for i in (1, 2, 3)] + [stats_row(9, "flash", 1, line(PTS=50, FGM=20, FGA=25))]
    )
    proj = pd.DataFrame(
        [proj_row(1, line(PTS=6, FGA=5, FGM=2)), proj_row(2, line(PTS=8, FGA=6, FGM=3)),
         proj_row(3, line(PTS=20, FGA=15, FGM=7)), proj_row(9)]
    )
    out = ro.blend_players(stats, proj).loc[9]
    assert out["prior"] == "replacement"
    assert out["w_real"] == pytest.approx(1 / 16)
    assert out["PTS"] == pytest.approx(1 / 16 * 50 + 15 / 16 * 8)


def test_blend_uses_the_requested_window():
    stats = pd.DataFrame([{**stats_row(1, "a", 15, REAL, window="d14"), **stats_row(1, "a", 0, window="season")}])
    proj = pd.DataFrame([proj_row(1, PROJ)])
    assert ro.blend_players(stats, proj, window="d14").loc[1, "PTS"] == pytest.approx(23)
    assert ro.blend_players(stats, proj, window="season").loc[1, "PTS"] == pytest.approx(16)


# ---------------------------------------------------------------------------
# 2-3. Team values and ratings
# ---------------------------------------------------------------------------

def test_percentages_aggregate_from_makes_and_attempts():
    # 1/1 and 0/9 is 10%, not the 50% an average of percentages would give.
    sums = np.array([line(FGM=1, FGA=10, FTM=3, FTA=4)[c] for c in C])
    v = dict(zip(ro.MAIN_CATS, ro.category_values(sums)))
    assert v["FG%"] == pytest.approx(0.1)
    assert v["FT%"] == pytest.approx(0.75)


def test_league_ratings_match_the_apps_formula():
    rng = np.random.default_rng(7)
    values = pd.DataFrame(rng.uniform(0, 100, size=(10, 9)), columns=ro.MAIN_CATS, index=[f"t{i}" for i in range(10)])
    values["BLK"] = 5.0  # zero-variance category -> all 0, like the app
    ours = ro.league_ratings(values)
    app = aggregate_rating(values.reset_index(names="Team"), ro.MAIN_CATS, ["TO"]).set_index("Team")
    for c in ro.MAIN_CATS:
        np.testing.assert_allclose(ours[c].to_numpy(), app[f"{c}_rating"].to_numpy(), atol=1e-12)
    assert ours["TO"].idxmax() == values["TO"].idxmin()  # fewest turnovers rates best


# ---------------------------------------------------------------------------
# 4. Targets
# ---------------------------------------------------------------------------

def test_targets_are_top_five_and_never_turnovers():
    ratings = pd.Series({"FG%": 0.2, "FT%": 0.9, "3PTM": 0.5, "REB": 0.7, "AST": 0.1, "STL": 0.6, "BLK": 0.3, "TO": 1.0, "PTS": 0.8})
    targets = ro.pick_targets(ratings, 5, ro.considered_cats(ro.OptimizerConfig()))
    assert targets == ["FT%", "PTS", "REB", "STL", "3PTM"]
    assert "TO" not in targets


def test_target_ties_keep_category_order():
    ratings = pd.Series({c: 0.5 for c in ro.MAIN_CATS})
    assert ro.pick_targets(ratings, 5, ro.considered_cats(ro.OptimizerConfig())) == ["FG%", "FT%", "3PTM", "REB", "AST"]


# ---------------------------------------------------------------------------
# 5. Search: hand-built scenarios with known answers
# ---------------------------------------------------------------------------

SHOOT = dict(FGM=5, FGA=10, FTM=5, FTA=10)


def punt_league():
    """Target T vs A and B. Two free agents: 'tank' adds a bit more PTS/REB
    than 'safe' but shoots 0-for-10. Worked by hand:
      T + safe: PTS 20, REB 20, FG 50%  -> targets 0.5+0.5 = 1.00, FG% rating 0.5
      T + tank: PTS 21, REB 21, FG 25%  -> targets 0.55+0.55 = 1.10, FG% rating 0
    Full punt -> tank (1.10 > 1.00). Balanced 0.25 -> safe (1.00 + 0.125 > 1.10)."""
    lines = {
        "a1": line(PTS=10, REB=10, FGM=4, FGA=10, FTM=5, FTA=10),
        "b1": line(PTS=30, REB=30, FGM=6, FGA=10, FTM=5, FTA=10),
        "t1": line(PTS=10, REB=10, **SHOOT),
        "t2": line(),
        "safe": line(PTS=10, REB=10, **SHOOT),
        "tank": line(PTS=11, REB=11, FGM=0, FGA=10, FTM=5, FTA=10),
    }
    rosters = {"A": ["a1"], "B": ["b1"], "T": ["t1", "t2"]}
    return players_frame(lines), rosters, ["safe", "tank"]


TARGETS = ["PTS", "REB", "AST", "STL", "BLK"]


def test_full_punt_takes_the_tanker():
    players, rosters, fas = punt_league()
    res = ro.optimize("T", players, rosters, fas, ro.OptimizerConfig(other_weight=0.0), targets=TARGETS)
    assert (res.swaps[0].drop, res.swaps[0].add) == ("t2", "tank")
    assert res.swaps[0].objective == pytest.approx(1.10)


def test_balanced_protects_the_other_categories():
    players, rosters, fas = punt_league()
    res = ro.optimize("T", players, rosters, fas, ro.OptimizerConfig(other_weight=0.25), targets=TARGETS)
    assert (res.swaps[0].drop, res.swaps[0].add) == ("t2", "safe")
    assert res.swaps[0].objective == pytest.approx(1.125)


def test_turnover_only_improvement_is_ignored():
    # 'clean' is t2 with zero turnovers: the only thing it changes is TO.
    lines = {
        "a1": line(PTS=10, TO=5, **SHOOT), "b1": line(PTS=30, TO=1, **SHOOT),
        "t1": line(PTS=20, TO=2, **SHOOT), "t2": line(TO=8), "clean": line(TO=0),
    }
    rosters = {"A": ["a1"], "B": ["b1"], "T": ["t1", "t2"]}
    players = players_frame(lines)
    ignored = ro.optimize("T", players, rosters, ["clean"], ro.OptimizerConfig(other_weight=0.25))
    assert ignored.swaps == []
    assert "TO" not in ignored.targets and "TO" not in ignored.start_ratings
    # Sanity: the same swap IS taken once TO counts -- so the line above is the
    # ignore rule at work, not a scenario where the swap never helped.
    counted = ro.optimize(
        "T", players, rosters, ["clean"], ro.OptimizerConfig(ignored_cats=(), other_weight=0.25), targets=["TO", "PTS"]
    )
    assert [(s.drop, s.add) for s in counted.swaps] == [("t2", "clean")]


def test_targets_rejected_if_they_include_an_ignored_category():
    players, rosters, fas = punt_league()
    with pytest.raises(ValueError):
        ro.optimize("T", players, rosters, fas, targets=["TO", "PTS"])


def test_no_improving_swap_means_no_swaps():
    players, rosters, _ = punt_league()
    useless = players_frame({**{i: players.loc[i, C].to_dict() for i in players.index}, "dud": line()})
    res = ro.optimize("T", useless, rosters, ["dud"], targets=TARGETS)
    assert res.swaps == [] and res.end_objective == res.start_objective


def test_max_swaps_is_respected():
    rng = np.random.default_rng(3)
    players, rosters, fas = random_league(rng)
    res = ro.optimize("t0", players, rosters, fas, ro.OptimizerConfig(max_swaps=2))
    assert len(res.swaps) <= 2


# ---------------------------------------------------------------------------
# 5. Search: invariants + brute force against the app's own rating function
# ---------------------------------------------------------------------------

def random_league(rng, teams=10, per_team=13, free_agents=60):
    lines = {}
    rosters = {}
    pid = 0

    def rand_line(scale):
        fga = rng.uniform(5, 20) * scale
        fta = rng.uniform(1, 8) * scale
        return line(
            FGA=fga, FGM=fga * rng.uniform(0.38, 0.58), FTA=fta, FTM=fta * rng.uniform(0.6, 0.92),
            **{"3PTM": rng.uniform(0, 4) * scale}, REB=rng.uniform(2, 12) * scale, AST=rng.uniform(1, 9) * scale,
            STL=rng.uniform(0.3, 2) * scale, BLK=rng.uniform(0.1, 2.5) * scale, TO=rng.uniform(0.5, 3.5) * scale,
            PTS=rng.uniform(6, 30) * scale,
        )

    for t in range(teams):
        rosters[f"t{t}"] = []
        for _ in range(per_team):
            lines[f"p{pid}"] = rand_line(1.0)
            rosters[f"t{t}"].append(f"p{pid}")
            pid += 1
    fas = []
    for _ in range(free_agents):
        lines[f"p{pid}"] = rand_line(rng.uniform(0.5, 1.1))
        fas.append(f"p{pid}")
        pid += 1
    return players_frame(lines), rosters, fas


def brute_force_first_swap(team, players, rosters, fas, targets, config):
    """Slow reference: try every drop/add, recompute the WHOLE league with the
    app's aggregate_rating, score the target team. Shares no search code with
    the optimizer."""
    weights = {c: (1.0 if c in targets else 0.0 if c in config.ignored_cats else config.other_weight) for c in ro.MAIN_CATS}

    def league_value_frame(rs):
        rows = []
        for t, ids in rs.items():
            s = players.loc[ids, C].sum()
            rows.append({
                "Team": t, "FG%": s["FGM"] / s["FGA"], "FT%": s["FTM"] / s["FTA"],
                **{c: s[c] for c in ["3PTM", "REB", "AST", "STL", "BLK", "TO", "PTS"]},
            })
        return pd.DataFrame(rows)

    def score(rs):
        rated = aggregate_rating(league_value_frame(rs), ro.MAIN_CATS, ["TO"]).set_index("Team").loc[team]
        return sum(weights[c] * rated[f"{c}_rating"] for c in ro.MAIN_CATS)

    best = (score(rosters), None, None)
    for drop, add in itertools.product(rosters[team], fas):
        trial = {t: list(ids) for t, ids in rosters.items()}
        trial[team] = [add if p == drop else p for p in trial[team]]
        s = score(trial)
        if s > best[0] + 1e-12:
            best = (s, drop, add)
    return best


@pytest.mark.parametrize("seed,other_weight", [(1, 0.0), (2, 0.25), (5, 0.0), (11, 0.25)])
def test_first_swap_matches_brute_force(seed, other_weight):
    rng = np.random.default_rng(seed)
    players, rosters, fas = random_league(rng)
    cfg = ro.OptimizerConfig(other_weight=other_weight)
    res = ro.optimize("t0", players, rosters, fas, cfg)
    best_score, drop, add = brute_force_first_swap("t0", players, rosters, fas, res.targets, cfg)
    assert res.swaps, "a random league always has some improving swap"
    assert (res.swaps[0].drop, res.swaps[0].add) == (drop, add)
    assert res.swaps[0].objective == pytest.approx(best_score, abs=1e-9)


@pytest.mark.parametrize("seed", range(6))
def test_greedy_invariants(seed):
    rng = np.random.default_rng(100 + seed)
    players, rosters, fas = random_league(rng)
    for w in (0.0, 0.25):
        res = ro.optimize("t3", players, rosters, fas, ro.OptimizerConfig(other_weight=w))
        added = [s.add for s in res.swaps]
        dropped = [s.drop for s in res.swaps]
        assert len(set(added)) == len(added)                  # no FA added twice
        assert set(added) <= set(fas)                         # only free agents are added
        assert set(dropped) <= set(rosters["t3"])            # only original players are dropped
        assert not set(added) & set(dropped)                  # so nothing is added then dropped
        assert all(s.gain > 0 for s in res.swaps)              # every step strictly helps
        objs = [res.start_objective] + [s.objective for s in res.swaps]
        assert objs == sorted(objs)
        for s in res.swaps:
            assert "TO" not in s.ratings
            assert all(0.0 <= v <= 1.0 for v in s.ratings.values())
        # Targets come from the 8 considered categories, and the reported
        # start ratings match a from-scratch league rating.
        sums = ro.team_component_sums(players, rosters)
        vals = pd.DataFrame(ro.category_values(sums.to_numpy()), index=sums.index, columns=ro.MAIN_CATS)
        start = ro.league_ratings(vals).loc["t3"]
        assert res.targets == ro.pick_targets(start, 5, ro.considered_cats(ro.OptimizerConfig()))


def brute_force_greedy(team, players, rosters, fas, targets, config):
    """Full reference greedy sequence, every candidate scored from scratch with
    the app's aggregate_rating -- same rules (only original players dropped,
    each FA added at most once), none of the optimizer's vectorized code."""

    def score(rs):
        return brute_force_first_swap(team, players, rs, [], targets, config)[0]

    original = set(rosters[team])
    current = {t: list(ids) for t, ids in rosters.items()}
    pool = list(fas)
    best_score = score(current)
    sequence = []
    for _ in range(config.max_swaps):
        drop = add = None
        for d in [p for p in current[team] if p in original]:
            for a in pool:
                trial = {t: list(ids) for t, ids in current.items()}
                trial[team] = [a if p == d else p for p in trial[team]]
                s = score(trial)
                if s > best_score + 1e-12:
                    best_score, drop, add = s, d, a
        if drop is None:
            break
        current[team] = [add if p == drop else p for p in current[team]]
        pool.remove(add)
        sequence.append((drop, add, best_score))
    return sequence


@pytest.mark.parametrize("seed,other_weight", [(21, 0.0), (22, 0.25)])
def test_whole_greedy_sequence_matches_brute_force(seed, other_weight):
    rng = np.random.default_rng(seed)
    players, rosters, fas = random_league(rng, teams=6, per_team=8, free_agents=25)
    cfg = ro.OptimizerConfig(other_weight=other_weight)
    res = ro.optimize("t0", players, rosters, fas, cfg)
    ref = brute_force_greedy("t0", players, rosters, fas, res.targets, cfg)
    assert [(s.drop, s.add) for s in res.swaps] == [(d, a) for d, a, _ in ref]
    for s, (_, _, score) in zip(res.swaps, ref):
        assert s.objective == pytest.approx(score, abs=1e-9)
    assert len(res.swaps) >= 2, "scenario should exercise multiple steps"


def test_injured_free_agents_are_never_suggested():
    players, rosters, fas = punt_league()
    players["InjuryStatus"] = ""
    players.loc["tank", "InjuryStatus"] = "OUT"
    res = ro.optimize("T", players, rosters, fas, ro.OptimizerConfig(other_weight=0.0), targets=TARGETS)
    assert "tank" not in [s.add for s in res.swaps]
    assert (res.swaps[0].drop, res.swaps[0].add) == ("t2", "safe")
    # Day-to-day is still fine to suggest.
    players.loc["tank", "InjuryStatus"] = "DAY_TO_DAY"
    res = ro.optimize("T", players, rosters, fas, ro.OptimizerConfig(other_weight=0.0), targets=TARGETS)
    assert res.swaps[0].add == "tank"


def test_blend_carries_injury_status():
    stats = pd.DataFrame([stats_row(1, "a", 0), stats_row(2, "b", 0)])
    proj = pd.DataFrame([{**proj_row(1, PROJ), "InjuryStatus": "OUT"}, {**proj_row(2, PROJ), "InjuryStatus": None}])
    out = ro.blend_players(stats, proj)
    assert out.loc[1, "InjuryStatus"] == "OUT" and out.loc[2, "InjuryStatus"] == ""


def test_unsigned_free_agents_are_never_suggested():
    players, rosters, fas = punt_league()
    players["NBATeam"] = "BOS"
    players.loc["tank", "NBATeam"] = "FA"
    res = ro.optimize("T", players, rosters, fas, ro.OptimizerConfig(other_weight=0.0), targets=TARGETS)
    assert "tank" not in [s.add for s in res.swaps]
    res = ro.optimize("T", players, rosters, fas, ro.OptimizerConfig(other_weight=0.0, exclude_unsigned=False), targets=TARGETS)
    assert res.swaps[0].add == "tank"


def test_injured_rostered_player_counts_at_small_weight_and_becomes_the_drop():
    # t1 is the team's best player but OUT: at 10% weight T's PTS/REB fall
    # from 20 to 11, so swapping him for 'safe' is now the best move.
    lines = {
        "a1": line(PTS=10, REB=10, FGM=4, FGA=10, FTM=5, FTA=10),
        "b1": line(PTS=30, REB=30, FGM=6, FGA=10, FTM=5, FTA=10),
        "t1": line(PTS=10, REB=10, **SHOOT),
        "t2": line(PTS=10, REB=10, **SHOOT),
        "safe": line(PTS=9, REB=9, **SHOOT),
    }
    players = players_frame(lines)
    players["InjuryStatus"] = ""
    players.loc["t1", "InjuryStatus"] = "OUT"
    rosters = {"A": ["a1"], "B": ["b1"], "T": ["t1", "t2"]}
    res = ro.optimize("T", players, rosters, ["safe"], ro.OptimizerConfig(injured_roster_weight=0.1), targets=TARGETS)
    assert [(s.drop, s.add) for s in res.swaps] == [("t1", "safe")]
    # Start: PTS = 1 + 10 = 11 -> (11-10)/20 = 0.05 for PTS and REB.
    assert res.start_ratings["PTS"] == pytest.approx(0.05)
    # Ignoring injuries (weight 1.0), 'safe' is worse than either starter.
    res = ro.optimize("T", players, rosters, ["safe"], ro.OptimizerConfig(injured_roster_weight=1.0), targets=TARGETS)
    assert res.swaps == []


def test_injured_weight_applies_to_other_teams_too():
    lines = {
        "a1": line(PTS=40, **SHOOT), "b1": line(PTS=20, **SHOOT),
        "t1": line(PTS=30, **SHOOT),
    }
    players = players_frame(lines)
    players["InjuryStatus"] = ["OUT", "", ""]
    rosters = {"A": ["a1"], "B": ["b1"], "T": ["t1"]}
    # A's star is OUT: A projects 4 PTS, so T (30) is the league's best.
    res = ro.optimize("T", players, rosters, [], ro.OptimizerConfig(), targets=TARGETS)
    assert res.start_ratings["PTS"] == pytest.approx(1.0)
