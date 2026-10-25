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
    out = ro.blend_players(stats, proj, ro.OptimizerConfig(k_games=15)).loc[1]
    assert out["w_real"] == pytest.approx(2 / 17)
    assert out["PTS"] == pytest.approx(2 / 17 * 30 + 15 / 17 * 16)


def test_no_games_is_pure_prior():
    stats = pd.DataFrame([stats_row(1, "a", 0)])
    proj = pd.DataFrame([proj_row(1, PROJ)])
    out = ro.blend_players(stats, proj).loc[1]
    assert out["w_real"] == 0
    for c in C:
        assert out[c] == pytest.approx(PROJ[c])


def test_per_component_k():
    # Default k: PTS stabilizes after 3 games, STL only after 15.
    stats = pd.DataFrame([stats_row(1, "a", 6, REAL)])
    proj = pd.DataFrame([proj_row(1, PROJ)])
    out = ro.blend_players(stats, proj).loc[1]
    assert out["PTS"] == pytest.approx(6 / 9 * 30 + 3 / 9 * 16)
    assert out["STL"] == pytest.approx(6 / 21 * 2 + 15 / 21 * 1)
    assert out["w_real"] == pytest.approx(6 / 9)


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
    out = ro.blend_players(stats, proj, ro.OptimizerConfig(k_games=15)).loc[9]
    assert out["prior"] == "replacement"
    assert out["w_real"] == pytest.approx(1 / 16)
    assert out["PTS"] == pytest.approx(1 / 16 * 50 + 15 / 16 * 8)


def test_blend_uses_the_requested_window():
    stats = pd.DataFrame([{**stats_row(1, "a", 15, REAL, window="d14"), **stats_row(1, "a", 0, window="season")}])
    proj = pd.DataFrame([proj_row(1, PROJ)])
    cfg = ro.OptimizerConfig(k_games=15)
    assert ro.blend_players(stats, proj, cfg, window="d14").loc[1, "PTS"] == pytest.approx(23)
    assert ro.blend_players(stats, proj, cfg, window="season").loc[1, "PTS"] == pytest.approx(16)


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
        "a0": line(), "b0": line(),  # empty padding: equal roster sizes, sums unchanged
    }
    rosters = {"A": ["a1", "a0"], "B": ["b1", "b0"], "T": ["t1", "t2"]}
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
        "a0": line(), "b0": line(),
    }
    rosters = {"A": ["a1", "a0"], "B": ["b1", "b0"], "T": ["t1", "t2"]}
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

    base = score(rosters)
    best = (base, None, None)
    for drop, add in itertools.product(rosters[team], fas):
        trial = {t: list(ids) for t, ids in rosters.items()}
        trial[team] = [add if p == drop else p for p in trial[team]]
        s = score(trial)
        if s > best[0] + 1e-12:
            best = (s, drop, add)
    if best[1] is not None and best[0] - base <= config.min_gain:
        return (base, None, None)
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
        step_base = best_score
        for d in [p for p in current[team] if p in original]:
            for a in pool:
                trial = {t: list(ids) for t, ids in current.items()}
                trial[team] = [a if p == d else p for p in trial[team]]
                s = score(trial)
                if s > best_score + 1e-12:
                    best_score, drop, add = s, d, a
        if drop is None or best_score - step_base <= config.min_gain:
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


def test_availability_is_projected_games_over_season():
    stats = pd.DataFrame([stats_row(1, "a", 0), stats_row(2, "b", 0), stats_row(3, "c", 0)])
    proj = pd.DataFrame([
        {**proj_row(1, PROJ), "proj_GP": 59}, {**proj_row(2, PROJ), "proj_GP": 90}, {**proj_row(3), "proj_GP": None},
    ])
    out = ro.blend_players(stats, proj, ro.OptimizerConfig(availability_calibration=(0.0, 1.0)), replacement_pool=pd.Index([1]))
    assert out.loc[1, "availability"] == pytest.approx(59 / 82)
    assert out.loc[2, "availability"] == 1.0                       # capped
    assert out.loc[3, "availability"] == pytest.approx(0.60)      # no projection -> measured 0.60


def test_injured_star_with_good_availability_is_not_cut():
    # t1 is OUT right now but ESPN projects 74 GP (90%): he still outvalues a
    # healthy but weaker free agent, so no swap -- the old flat 10% injury
    # weight would have cut him.
    lines = {
        "a1": line(PTS=10, REB=10, FGM=4, FGA=10, FTM=5, FTA=10),
        "b1": line(PTS=30, REB=30, FGM=6, FGA=10, FTM=5, FTA=10),
        "t1": line(PTS=10, REB=10, **SHOOT), "t2": line(PTS=10, REB=10, **SHOOT),
        "healthy": line(PTS=8, REB=8, **SHOOT),
        "a0": line(), "b0": line(),
    }
    players = players_frame(lines)
    players["InjuryStatus"] = ""
    players.loc["t1", "InjuryStatus"] = "OUT"
    players["availability"] = 1.0
    players.loc["t1", "availability"] = 0.9
    rosters = {"A": ["a1", "a0"], "B": ["b1", "b0"], "T": ["t1", "t2"]}
    res = ro.optimize("T", players, rosters, ["healthy"], ro.OptimizerConfig(), targets=TARGETS)
    assert res.swaps == []
    # A long-term absence (ESPN projects 20 GP, ~24%) does make him the drop.
    players.loc["t1", "availability"] = 0.24
    res = ro.optimize("T", players, rosters, ["healthy"], ro.OptimizerConfig(), targets=TARGETS)
    assert [(s.drop, s.add) for s in res.swaps] == [("t1", "healthy")]


def test_availability_scales_free_agents_too():
    players, rosters, fas = punt_league()
    players["availability"] = 1.0
    players.loc["tank", "availability"] = 0.5   # tank now adds ~5.5 PTS/REB, worse than safe
    res = ro.optimize("T", players, rosters, fas, ro.OptimizerConfig(other_weight=0.0), targets=TARGETS)
    assert res.swaps[0].add == "safe"


def test_rosters_are_scaled_to_a_common_size():
    # B carries a third, empty-ish player: without scaling it would sum the
    # same as with two; scaled to 2 players, B's 30 PTS over 3 -> 20.
    lines = {
        "a1": line(PTS=5, **SHOOT), "a2": line(PTS=5, **SHOOT),
        "b1": line(PTS=15, **SHOOT), "b2": line(PTS=15, **SHOOT), "b3": line(**SHOOT),
        "t1": line(PTS=10, **SHOOT), "t2": line(PTS=5, **SHOOT),
    }
    rosters = {"A": ["a1", "a2"], "B": ["b1", "b2", "b3"], "T": ["t1", "t2"]}
    players = players_frame(lines)
    assert ro.roster_scale(rosters) == {"A": 1.0, "B": pytest.approx(2 / 3), "T": 1.0}
    sums = ro.team_component_sums(players, rosters)
    assert sums.loc["B", "PTS"] == pytest.approx(20)
    res = ro.optimize("T", players, rosters, [], ro.OptimizerConfig(), targets=TARGETS)
    # T 15 PTS between A 10 and B 20 (scaled) -> 0.5; unscaled B (30) gives 0.25.
    assert res.start_ratings["PTS"] == pytest.approx(0.5)


def test_tiny_swaps_are_not_suggested():
    # 'nudge' adds 0.1 PTS: worth (0.1/20) = 0.005 in the PTS rating.
    players, rosters, _ = punt_league()
    players = players_frame({**{i: players.loc[i, C].to_dict() for i in players.index},
                             "nudge": line(PTS=0.1, REB=0, FGA=0, FGM=0)})
    assert ro.optimize("T", players, rosters, ["nudge"], targets=TARGETS).swaps == []
    tiny = ro.optimize("T", players, rosters, ["nudge"], ro.OptimizerConfig(min_gain=0.0), targets=TARGETS)
    assert [(s.drop, s.add) for s in tiny.swaps] == [("t2", "nudge")]
    assert tiny.swaps[0].gain == pytest.approx(0.005)


# ---------------------------------------------------------------------------
# Probabilistic objectives (category_wins / matchup_wins / standings)
# ---------------------------------------------------------------------------

import math


def test_normal_cdf_matches_math_erf():
    zs = np.linspace(-6, 6, 241)
    ours = ro.normal_cdf(zs)
    ref = np.array([0.5 * (1 + math.erf(z / math.sqrt(2))) for z in zs])
    np.testing.assert_allclose(ours, ref, atol=2e-7)


def test_at_least_k_matches_enumeration():
    rng = np.random.default_rng(0)
    p = rng.uniform(0, 1, size=9)
    for k in range(10):
        brute = 0.0
        for outcome in itertools.product([0, 1], repeat=9):
            if sum(outcome) >= k:
                brute += np.prod([p[i] if o else 1 - p[i] for i, o in enumerate(outcome)])
        assert ro.at_least_k(p[None, :], k)[0] == pytest.approx(brute, abs=1e-12)


def test_win_probabilities_orientation_and_symmetry():
    sigma = np.ones(9)
    own = np.zeros(9)
    others = np.zeros((1, 9))
    np.testing.assert_allclose(ro.win_probabilities(own, others, sigma), 0.5)
    own = np.full(9, 1.0)  # more of everything: wins every cat except TO
    p = ro.win_probabilities(own, others, sigma)[0]
    to = ro.MAIN_CATS.index("TO")
    assert p[to] < 0.5 and all(p[i] > 0.5 for i in range(9) if i != to)


def slow_objective(team, players, rosters, sigma, targets, config):
    """Independent pure-Python scorer for the probabilistic objectives."""
    vals = {}
    for t, ids in rosters.items():
        s = players.loc[ids, C].sum()
        vals[t] = {"FG%": s["FGM"] / s["FGA"], "FT%": s["FTM"] / s["FTA"],
                   **{c: s[c] for c in ["3PTM", "REB", "AST", "STL", "BLK", "TO", "PTS"]}}
    opps = [t for t in rosters if t != team]
    p = {}
    for o in opps:
        for i, c in enumerate(ro.MAIN_CATS):
            if c in config.ignored_cats:
                p[(o, c)] = 0.5
                continue
            d = vals[team][c] - vals[o][c]
            if c == "TO":
                d = -d
            p[(o, c)] = 0.5 * (1 + math.erf(d / (sigma[i] * math.sqrt(2)) / math.sqrt(2)))
    share = {c: sum(p[(o, c)] for o in opps) / len(opps) for c in ro.MAIN_CATS}
    if config.objective == "category_wins":
        w = {c: 1.0 if c in targets else 0.0 if c in config.ignored_cats else config.other_weight for c in ro.MAIN_CATS}
        return sum(w[c] * share[c] for c in ro.MAIN_CATS)
    mw = 0.0
    for o in opps:
        pr = [p[(o, c)] for c in ro.MAIN_CATS]
        mw += sum(np.prod([pr[i] if b else 1 - pr[i] for i, b in enumerate(bits)])
                  for bits in itertools.product([0, 1], repeat=9) if sum(bits) >= config.cats_to_win)
    mw /= len(opps)
    if config.objective == "matchup_wins":
        return mw
    return 0.5 * mw + 0.5 * sum(share.values()) / 9


def slow_greedy(team, players, rosters, fas, targets, config):
    sums = ro.team_component_sums(players, rosters)
    vals = pd.DataFrame(ro.category_values(sums.to_numpy()), index=sums.index, columns=ro.MAIN_CATS)
    sigma = ro.category_sigma(vals, config)  # fixed at the start, like the optimizer
    gain_floor = config.min_gain_share if config.objective in ("matchup_wins", "standings") else config.min_gain
    original, current, pool, seq = set(rosters[team]), {t: list(v) for t, v in rosters.items()}, list(fas), []
    best = slow_objective(team, players, current, sigma, targets, config)
    for _ in range(config.max_swaps):
        step_base, choice = best, None
        for d in [p for p in current[team] if p in original]:
            for a in pool:
                trial = {t: list(v) for t, v in current.items()}
                trial[team] = [a if p == d else p for p in trial[team]]
                sc = slow_objective(team, players, trial, sigma, targets, config)
                if sc > best + 1e-12:
                    best, choice = sc, (d, a)
        if choice is None or best - step_base <= gain_floor:
            break
        d, a = choice
        current[team] = [a if p == d else p for p in current[team]]
        pool.remove(a)
        seq.append((d, a, best))
    return seq


@pytest.mark.parametrize("objective,other_weight,seed", [
    ("category_wins", 0.0, 31), ("category_wins", 0.25, 32), ("matchup_wins", 0.0, 33), ("standings", 0.0, 34),
])
def test_probabilistic_greedy_matches_brute_force(objective, other_weight, seed):
    rng = np.random.default_rng(seed)
    players, rosters, fas = random_league(rng, teams=5, per_team=6, free_agents=14)
    cfg = ro.OptimizerConfig(objective=objective, other_weight=other_weight, min_gain_share=0.001)
    res = ro.optimize("t0", players, rosters, fas, cfg)
    ref = slow_greedy("t0", players, rosters, fas, res.targets, cfg)
    assert [(s.drop, s.add) for s in res.swaps] == [(d, a) for d, a, _ in ref]
    for s, (_, _, sc) in zip(res.swaps, ref):
        assert s.objective == pytest.approx(sc, abs=1e-6)
    assert res.swaps, "scenario should produce at least one swap"


def test_category_wins_rewards_margin_where_ratings_does_not():
    # T already leads PTS. 'bigger' adds more PTS margin; 'same' adds none.
    # Ratings (capped at 1.0) sees no difference; category_wins prefers bigger.
    lines = {
        "a1": line(PTS=20, REB=10, **SHOOT), "b1": line(PTS=22, REB=10, **SHOOT),
        "t1": line(PTS=20, REB=10, **SHOOT), "t2": line(PTS=5, REB=10, **SHOOT),
        "same": line(PTS=5, REB=10, **SHOOT), "bigger": line(PTS=12, REB=10, **SHOOT),
        "a0": line(), "b0": line(),
    }
    players = players_frame(lines)
    rosters = {"A": ["a1", "a0"], "B": ["b1", "b0"], "T": ["t1", "t2"]}
    rat = ro.optimize("T", players, rosters, ["same", "bigger"], ro.OptimizerConfig(min_gain=0.0), targets=["PTS"])
    assert rat.swaps == []  # T at 25 PTS already rates 1.0
    cw = ro.optimize("T", players, rosters, ["same", "bigger"],
                     ro.OptimizerConfig(objective="category_wins", min_gain=0.0), targets=["PTS"])
    assert [s.add for s in cw.swaps] == ["bigger"]


def test_availability_blends_projection_with_recent_playing_rate():
    cfg = ro.OptimizerConfig(availability_calibration=(0.0, 1.0))
    stats = pd.DataFrame([{**stats_row(1, "proj", 10), "d30_GP": 7}, {**stats_row(2, "noproj", 10), "d30_GP": 14}])
    proj = pd.DataFrame([{**proj_row(1, PROJ), "proj_GP": 82}, {**proj_row(2), "proj_GP": None}])
    # Without days_elapsed: projection-only (unprojected -> 0.60).
    out = ro.blend_players(stats, proj, cfg)
    assert out.loc[1, "availability"] == 1.0 and out.loc[2, "availability"] == pytest.approx(0.60)
    # 60 days in: 30-day window, ~13.9 NBA games; rate weight 0.5.
    games = 30 * cfg.nba_games_per_day
    out = ro.blend_players(stats, proj, cfg, days_elapsed=60)
    assert out.loc[1, "availability"] == pytest.approx(0.5 * 1.0 + 0.5 * (7 / games))
    assert out.loc[2, "availability"] == pytest.approx(0.5 * 0.60 + 0.5 * min(1, 14 / games))
    # 7 days in: the rate only gets 0.5 * 7/28 weight, over a 7-day window.
    out = ro.blend_players(stats, proj, cfg, days_elapsed=7)
    w = 0.5 * 7 / 28
    assert out.loc[1, "availability"] == pytest.approx((1 - w) * 1.0 + w * min(1, 7 / (7 * cfg.nba_games_per_day)))


def test_availability_calibration_is_applied_last():
    stats = pd.DataFrame([stats_row(1, "a", 0)])
    proj = pd.DataFrame([{**proj_row(1, PROJ), "proj_GP": 82}])
    out = ro.blend_players(stats, proj, ro.OptimizerConfig(availability_calibration=(0.065, 0.816)))
    assert out.loc[1, "availability"] == pytest.approx(0.065 + 0.816 * 1.0)


def test_matchup_win_reported_for_probabilistic_objectives():
    rng = np.random.default_rng(41)
    players, rosters, fas = random_league(rng, teams=5, per_team=6, free_agents=14)
    res = ro.optimize("t0", players, rosters, fas, ro.recommended_config())
    assert 0 <= res.start_matchup_win <= 1
    assert all(0 <= s.matchup_win <= 1 for s in res.swaps)
    # Independent check with the slow scorer: matchup_wins objective == reported matchup_win.
    cfg = ro.OptimizerConfig(objective="matchup_wins")
    sums = ro.team_component_sums(players, rosters)
    vals = pd.DataFrame(ro.category_values(sums.to_numpy()), index=sums.index, columns=ro.MAIN_CATS)
    sigma = ro.category_sigma(vals, cfg)
    assert res.start_matchup_win == pytest.approx(slow_objective("t0", players, rosters, sigma, [], cfg), abs=1e-6)
    assert ro.optimize("t0", players, rosters, fas, ro.OptimizerConfig()).start_matchup_win is None


def test_recent_form_blend():
    # 10 season games at 20 PTS, last-14-day average 30 PTS over 4 games.
    row = {**stats_row(1, "a", 10, line(PTS=20, FGM=8, FGA=16)), **stats_row(1, "a", 4, line(PTS=30, FGM=12, FGA=20), window="d14")}
    stats = pd.DataFrame([row])
    proj = pd.DataFrame([proj_row(1, line(PTS=20, FGM=8, FGA=16))])
    off = ro.blend_players(stats, proj, ro.OptimizerConfig(k_games=15)).loc[1]
    on = ro.blend_players(stats, proj, ro.OptimizerConfig(k_games=15, recent_form_window="d14")).loc[1]
    w = 10 / 25
    assert off["PTS"] == pytest.approx(w * 20 + (1 - w) * 20)
    assert on["PTS"] == pytest.approx(w * (0.7 * 20 + 0.3 * 30) + (1 - w) * 20)
    # No games in the window -> season average unchanged.
    row0 = {**stats_row(1, "a", 10, line(PTS=20, FGM=8, FGA=16)), **stats_row(1, "a", 0, window="d14")}
    zero = ro.blend_players(pd.DataFrame([row0]), proj, ro.OptimizerConfig(k_games=15, recent_form_window="d14")).loc[1]
    assert zero["PTS"] == pytest.approx(off["PTS"])
