"""Roster Optimizer: should a Cats-format season optimize categories only?
(_planning/roster-optimizer.md, 2026-10-28.) Compares the live objective
("standings": half weekly matchup-win probability, half expected category
share) with "categories" (expected category share only) on the weekly
replay -- same setup as scripts/backtest_optimizer_projections.py (every
team-season 2019-2023 from its post-draft roster, re-optimized weekly with
up to --cap swaps, live corrected projections with out-of-sample
coefficients, opponents on their real daily rosters). Every replayed week
records both matchup wins and category wins, so the Cats question (more
category wins?) is answerable on these W/L seasons too.

  python -m scripts.backtest_cats_objective --data <backtest dir> --ref <ref dir> \\
      --pub <public ESPN dir> --params-by-year adjust_params.json --out out.csv
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import backtest_roster_optimizer as bt  # noqa: E402
from scripts.backtest_optimizer_projections import ci, weekly_players  # noqa: E402
from shared import roster_optimizer as ro  # noqa: E402

OBJECTIVES = ("standings", "categories")


# The categories-only score moves less per swap than the 50/50 mix, so the
# same +0.01 minimum gain is effectively stricter for it; --cat-min-gain
# runs it at a different bar for a like-for-like comparison.
CAT_MIN_GAIN = 0.01


def rolling(s: bt.Season, team: str, players_by_week, objective: str, cap: int) -> tuple[dict[int, list], int]:
    roster = list(s.roster_on(int(s.week_start[1]))[team])
    daily, n = {}, 0
    cfg = ro.recommended_config(max_swaps=cap, objective=objective,
                                **({"min_gain_share": CAT_MIN_GAIN} if objective == "categories" else {}))
    for w in s.rs_weeks:
        sp = int(s.week_start[w])
        rosters = s.roster_on(sp)
        rosters[team] = list(roster)
        rostered = {p for ids in rosters.values() for p in ids}
        players = players_by_week[w]["corrected"]
        res = ro.optimize(team, players, rosters, [p for p in players.index if p not in rostered], cfg)
        for sw in res.swaps:
            roster[roster.index(sw.drop)] = sw.add
        n += len(res.swaps)
        end = int(s.weeks.loc[s.weeks["Week"] == w, "EndSP"].iloc[0])
        for day in range(sp, end + 1):
            daily[day] = list(roster)
    return daily, n


def run_year(args) -> pd.DataFrame:
    year, data, ref, pub, params, cap, cat_min_gain = args
    global CAT_MIN_GAIN
    CAT_MIN_GAIN = cat_min_gain
    s = bt.Season(year, Path(data), Path(ref))
    key = str(year) if str(year) in params["coefs"] else "all"
    pbw = weekly_players(s, Path(pub), {c: np.array(v) for c, v in params["coefs"][key].items()})
    sp0 = int(s.week_start[1])
    first = pbw[s.rs_weeks[0]]["blend"]
    priority = (first["PTS"] + 1.2 * first["REB"] + 1.5 * first["AST"]).to_dict()
    base = {t: bt.weekly_totals(s, 1, bt.real_daily(s, t, sp0), priority) for t in s.teams}
    rows = []
    for team in s.teams:
        sims = {"stand_pat": bt.weekly_totals(s, 1, bt.frozen_daily(s, s.roster_on(sp0)[team], sp0), priority)}
        swaps = {}
        for obj in OBJECTIVES:
            daily, swaps[obj] = rolling(s, team, pbw, obj, cap)
            sims[obj] = bt.weekly_totals(s, 1, daily, priority)
        for row in s.comp[s.comp["Team"] == team].itertuples():
            wk = row.Week
            if wk not in base[row.Opp].index:
                continue
            opp = bt.cat_values(base[row.Opp].loc[wk])
            rec = {"year": year, "team": team, "week": wk, **{f"swaps_{o}": swaps[o] for o in OBJECTIVES}}
            for k, sim in sims.items():
                if wk not in sim.index:
                    rec[k] = rec[f"{k}_cats"] = np.nan
                    continue
                W, L, T = bt.matchup(bt.cat_values(sim.loc[wk]), opp)
                rec[k] = 1.0 if W > L else 0.0 if L > W else 0.5
                rec[f"{k}_cats"] = W + 0.5 * T
            rows.append(rec)
        print(f"  {year} {team}: swaps {swaps}", flush=True)
    return pd.DataFrame(rows)


def summarize(d: pd.DataFrame) -> str:
    d = d[d.week <= 18]
    t = d.groupby(["year", "team"])[[*OBJECTIVES, "stand_pat", *[f"{o}_cats" for o in OBJECTIVES], "stand_pat_cats",
                                     *[f"swaps_{o}" for o in OBJECTIVES]]].agg(
        {**{c: "sum" for c in [*OBJECTIVES, "stand_pat", *[f"{o}_cats" for o in OBJECTIVES], "stand_pat_cats"]},
         **{f"swaps_{o}": "first" for o in OBJECTIVES}})
    out = [f"{len(t)} team-seasons, 18 weeks, vs never changing the drafted roster:"]
    for o in OBJECTIVES:
        lo, hi = ci(t[f"{o}_cats"] - t.stand_pat_cats)
        wlo, whi = ci(t[o] - t.stand_pat)
        out.append(f"  {o:10s} category wins {(t[f'{o}_cats'] - t.stand_pat_cats).mean():+.1f} [{lo:+.1f}, {hi:+.1f}]   "
                   f"matchup wins {(t[o] - t.stand_pat).mean():+.2f} [{wlo:+.2f}, {whi:+.2f}]   swaps {t[f'swaps_{o}'].mean():.1f}")
    dc = t.categories_cats - t.standings_cats
    dw = t.categories - t.standings
    lo, hi = ci(dc)
    wlo, whi = ci(dw)
    out.append(f"categories - standings: category wins {dc.mean():+.1f} [{lo:+.1f}, {hi:+.1f}] (better in {np.mean(dc > 0):.0%}, "
               f"worse in {np.mean(dc < 0):.0%}); matchup wins {dw.mean():+.2f} [{wlo:+.2f}, {whi:+.2f}]")
    out.append("by season (category wins, categories - standings): " + ", ".join(
        f"{y} {v:+.1f}" for y, v in dc.groupby(level=0).mean().items()))
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--pub", required=True)
    ap.add_argument("--params-by-year", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--years", type=int, nargs="+", default=[2019, 2020, 2021, 2022, 2023])
    ap.add_argument("--cap", type=int, default=3)
    ap.add_argument("--cat-min-gain", type=float, default=0.01)
    ap.add_argument("--summary-only", action="store_true")
    args = ap.parse_args()
    if not args.summary_only:
        params = json.loads(Path(args.params_by_year).read_text())
        with ProcessPoolExecutor(max_workers=len(args.years)) as ex:
            df = pd.concat(ex.map(run_year, [(y, args.data, args.ref, args.pub, params, args.cap, args.cat_min_gain) for y in args.years]))
        df.to_csv(args.out, index=False)
    print(summarize(pd.read_csv(args.out)))


if __name__ == "__main__":
    main()
