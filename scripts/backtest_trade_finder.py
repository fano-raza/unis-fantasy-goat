"""Backtests the Trade Finder (shared/trade_finder.py, Phase 7) on past ESPN
seasons with the Roster Optimizer's replay (scripts/backtest_roster_optimizer):

At checkpoints (weeks 4, 6, ..., 14), for every team, using only what was
known that day:
  - search trades for every one of its active players (1-for-1 and 2-for-1);
  - take the best Fair trade and the best Fleece trade (highest gain for
    the team) -- the top card the tool would have shown -- and, separately,
    the best 1-for-1 of each mode;
  - apply it on top of reality: from the checkpoint on, both teams' REAL
    daily rosters with the traded players moved (plus the partner's drop
    and the free agent you add in a 2-for-1); every other team unchanged;
  - replay the rest of the regular season and compare both teams' matchup
    wins and category wins with the no-trade replay.

Controls (same team, same checkpoint):
  pickup_only   2-for-1s only: skip the trade, just swap the less valuable of
                the two players you'd have given for the same free agent --
                how much of a 2-for-1's gain is the pickup you could make anyway
  random_fair   a random trade (any shape) the partner wouldn't see as
                lopsided, with no win-% rule -- what a value-fair trade does
                without the model choosing it

Caveat (as in the optimizer's backtest): a free agent you add can still show
up on another team's real roster later (no exclusivity across hypotheticals).

  python -m scripts.backtest_trade_finder --data <dir> --ref <ref dir> --out trades.csv \\
      [--years 2019 2020 2021 2022 2023]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import backtest_roster_optimizer as bt  # noqa: E402
from shared import roster_optimizer as ro  # noqa: E402
from shared import trade_finder as tf  # noqa: E402

CHECKPOINTS = (4, 6, 8, 10, 12, 14)
IR_SLOT = 13


def active_rosters(s: bt.Season, sp: int) -> dict[str, list]:
    day = s.rosters[(s.rosters["ScoringPeriod"] == sp) & (s.rosters["LineupSlotId"] != IR_SLOT)]
    return {t: day.loc[day["Team"] == t, "PlayerId"].astype(int).tolist() for t in s.teams}


def moved(daily: dict[int, list], pairs: list[tuple]) -> dict[int, list]:
    """Apply (leaving, arriving) substitutions to each day's real roster. A
    substitution only happens on days the leaving player is really there --
    if the manager had already let him go, the arriving player doesn't come
    either, so roster sizes never change (adding him anyway inflated both
    sides: a 2-for-1's partner usually releases its drop in reality too)."""
    out = {}
    for sp, ids in daily.items():
        ids = list(ids)
        for leaving, arriving in pairs:
            if leaving in ids and arriving not in ids:
                ids[ids.index(leaving)] = arriving
        out[sp] = ids
    return out


def replay(s, cp, sp0, base, base_table, priority, changes: dict[str, list[tuple]]) -> dict[str, tuple[float, float]]:
    """changes: team -> [(leaving, arriving), ...] substitutions from sp0 on.
    Returns team -> (delta matchup wins, delta category wins) vs no trade."""
    sim = dict(base)
    for team, pairs in changes.items():
        sim[team] = bt.weekly_totals(s, cp, moved(bt.real_daily(s, team, sp0), pairs), priority)
    table = bt.standings(s, cp, sim)
    res = {}
    for team in changes:
        r, b = table.loc[team], base_table.loc[team]
        res[team] = (float((r["W"] + 0.5 * r["T"]) - (b["W"] + 0.5 * b["T"])),
                     float((r["cW"] + 0.5 * r["cT"]) - (b["cW"] + 0.5 * b["cT"])))
    return res


def trade_changes(team: str, t: tf.Trade) -> dict[str, list[tuple]]:
    """1-for-1: you x->y, partner y->x. 2-for-1: you x1->y, x2->free agent;
    partner y->x1, its drop->x2."""
    if t.shape == "1-for-1":
        return {team: [(t.give[0], t.get[0])], t.partner: [(t.get[0], t.give[0])]}
    return {team: [(t.give[0], t.get[0]), (t.give[1], t.fa_add)],
            t.partner: [(t.get[0], t.give[0]), (t.partner_drop, t.give[1])]}


def run_season(s: bt.Season, rng: np.random.Generator) -> list[dict]:
    rows = []
    for cp in CHECKPOINTS:
        if cp not in s.week_start or cp >= max(s.rs_weeks):
            continue
        t0 = time.time()
        sp0 = int(s.week_start[cp])
        stats, projections = bt.checkpoint_inputs(s, sp0)
        rosters = active_rosters(s, sp0)
        rostered_all = set(s.rosters.loc[s.rosters["ScoringPeriod"] == sp0, "PlayerId"].astype(int))
        fas = [p for p in stats["PlayerId"] if p not in rostered_all]
        players = ro.blend_players(stats, projections, ro.OptimizerConfig(), replacement_pool=pd.Index(fas),
                                   days_elapsed=sp0 - 1)
        priority = (players["PTS"] + 1.2 * players["REB"] + 1.5 * players["AST"]).to_dict()
        base = {t: bt.weekly_totals(s, cp, bt.real_daily(s, t, sp0), priority) for t in s.teams}
        base_table = bt.standings(s, cp, base)
        weeks_left = len([w for w in s.rs_weeks if w >= cp])
        rostered = pd.Index([p for ids in rosters.values() for p in ids])
        values = tf.player_value(tf.League(players, rosters, ro.recommended_config()).comps, rostered)

        for team in s.teams:
            fleece, anyfair = [], []
            for x in rosters[team]:
                fleece += tf.find_trades(team, [x], players, rosters, fas,
                                         tf.TradeConfig(mode="fleece", max_results=None)).trades
                anyfair += tf.find_trades(team, [x], players, rosters, fas,
                                          tf.TradeConfig(mode="fleece", max_results=None, min_gain=-1.0,
                                                         partner_min_gain=-1.0)).trades
            fair = [t for t in fleece if t.partner_gain >= tf.MODES["fair"][1]]
            picks = {}
            if fair:
                picks["fair"] = max(fair, key=lambda t: t.gain)
            if fleece:
                picks["fleece"] = max(fleece, key=lambda t: t.gain)
            # Best 1-for-1s on their own (the overall best is almost always a
            # 2-for-1, whose pickup adds to its gain).
            for label, pool in (("fair_1for1", fair), ("fleece_1for1", fleece)):
                ones = [t for t in pool if t.shape == "1-for-1"]
                if ones:
                    picks[label] = max(ones, key=lambda t: t.gain)
            if anyfair:
                picks["random_fair"] = anyfair[rng.integers(len(anyfair))]
            for label, t in picks.items():
                d = replay(s, cp, sp0, base, base_table, priority, trade_changes(team, t))
                row = {
                    "year": s.year, "checkpoint": cp, "weeks_left": weeks_left, "team": team, "scenario": label,
                    "shape": t.shape, "partner": t.partner,
                    "give": " + ".join(s.names.get(p, str(p)) for p in t.give),
                    "get": s.names.get(t.get[0], str(t.get[0])),
                    "partner_drop": s.names.get(t.partner_drop, "") if t.partner_drop is not None else "",
                    "fa_add": s.names.get(t.fa_add, "") if t.fa_add is not None else "",
                    "pred_gain": t.gain, "pred_partner_gain": t.partner_gain, "partner_value_net": t.partner_value_net,
                    "wins": d[team][0], "cats": d[team][1],
                    "partner_wins": d[t.partner][0], "partner_cats": d[t.partner][1],
                }
                rows.append(row)
                if label in ("fair", "fleece") and t.shape == "2-for-1":
                    lesser = min(t.give, key=lambda p: values.get(p, -np.inf))
                    d2 = replay(s, cp, sp0, base, base_table, priority, {team: [(lesser, t.fa_add)]})
                    rows.append({**row, "scenario": f"{label}_pickup_only", "partner": "", "get": "",
                                 "give": s.names.get(lesser, str(lesser)), "partner_drop": "",
                                 "wins": d2[team][0], "cats": d2[team][1], "partner_wins": np.nan, "partner_cats": np.nan})
        print(f"  {s.year} week {cp}: {time.time() - t0:.0f}s", flush=True)
    return rows


def bootstrap_ci(v: np.ndarray, n: int = 4000, seed: int = 0) -> tuple[float, float]:
    v = np.asarray(v, dtype=float)
    v = v[~np.isnan(v)]
    if len(v) == 0:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    means = rng.choice(v, (n, len(v))).mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def summarize(df: pd.DataFrame) -> str:
    out = []

    def line(label, d):
        if d.empty:
            return
        lo, hi = bootstrap_ci(d["wins"].to_numpy())
        plo, phi = bootstrap_ci(d["partner_wins"].to_numpy())
        pw = d["partner_wins"].dropna()
        out.append(
            f"  {label:34s} n={len(d):3d}  you {d.wins.mean():+.2f} [{lo:+.2f},{hi:+.2f}] wins, {d.cats.mean():+.1f} cats, "
            f"better {np.mean(d.wins > 0):.0%} / worse {np.mean(d.wins < 0):.0%}"
            + (f" | partner {pw.mean():+.2f} [{plo:+.2f},{phi:+.2f}], {d.partner_cats.mean():+.1f} cats, "
               f"better {np.mean(pw > 0):.0%} / worse {np.mean(pw < 0):.0%}" if len(pw) else "")
            + f" | predicted you {d.pred_gain.mean() * 100:+.1f} pts, partner {d.pred_partner_gain.mean() * 100:+.1f}"
        )

    for split, years in [("ALL", None), ("dev 2019-21", [2019, 2020, 2021]), ("hold-out 2022-23", [2022, 2023])]:
        d0 = df if years is None else df[df.year.isin(years)]
        out.append(f"\n{split} (rest-of-season change vs no trade, per trade):")
        for sc in ["fair", "fair_pickup_only", "fleece", "fleece_pickup_only", "fair_1for1", "fleece_1for1", "random_fair"]:
            line(sc, d0[d0.scenario == sc])
        for sc in ["fair", "fleece"]:
            for shape in ["1-for-1", "2-for-1"]:
                line(f"{sc} {shape}", d0[(d0.scenario == sc) & (d0["shape"] == shape)])
    out.append("\nBy checkpoint (fair / fleece, your wins):")
    for cp, g in df.groupby("checkpoint"):
        f, fl = g[g.scenario == "fair"], g[g.scenario == "fleece"]
        out.append(f"  week {cp:2d}: fair {f.wins.mean():+.2f} (partner {f.partner_wins.mean():+.2f}, n={len(f)})   "
                   f"fleece {fl.wins.mean():+.2f} (partner {fl.partner_wins.mean():+.2f}, n={len(fl)})")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--ref", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--years", type=int, nargs="+", default=[2019, 2020, 2021, 2022, 2023])
    ap.add_argument("--summary-only", action="store_true", help="summarize an existing --out CSV")
    args = ap.parse_args()
    if not args.summary_only:
        rng = np.random.default_rng(0)
        rows = []
        for y in args.years:
            print(f"{y}", flush=True)
            rows += run_season(bt.Season(y, args.data, args.ref), rng)
            pd.DataFrame(rows).to_csv(args.out, index=False)
    print(summarize(pd.read_csv(args.out)))


if __name__ == "__main__":
    main()
