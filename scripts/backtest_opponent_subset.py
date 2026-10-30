"""Roster Optimizer: does leaving some opponents out of the score change
anything? (_planning/roster-optimizer.md, 2026-10-30.) The user asked about
optimizing to beat "everyone except" a few teams they expect to beat anyway;
this tests leaving Chirayu and Saamrit (in every season) out of the opponent
average (ro.optimize's ignore_opponents) against the live whole-league score.

Same weekly replay as scripts/backtest_cats_objective.py: every team-season
2019-2023 from its post-draft roster, re-optimized weekly with up to --cap
swaps, live corrected projections with out-of-sample coefficients, opponents
on their real daily rosters. Records, per replayed week, the matchup result
for each variant, so wins can be split into games against the ignored teams
and games against everyone else. Also records, on the whole-league path,
whether the subset variant would have recommended different moves from the
same roster (the "do the recommendations differ at all" question).

  python -m scripts.backtest_opponent_subset --data <backtest dir> --ref <ref dir> \\
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

VARIANTS = ("league", "subset")


def rolling(s: bt.Season, team: str, players_by_week, ignore: frozenset, cap: int, shadow: frozenset | None = None):
    """Weekly re-optimization along one variant's own path. With `shadow`,
    also asks the shadow variant what it would do from the same roster each
    week and records whether its moves differ."""
    roster = list(s.roster_on(int(s.week_start[1]))[team])
    daily, n, diffs = {}, 0, []
    cfg = ro.recommended_config(max_swaps=cap)
    for w in s.rs_weeks:
        sp = int(s.week_start[w])
        rosters = s.roster_on(sp)
        rosters[team] = list(roster)
        rostered = {p for ids in rosters.values() for p in ids}
        players = players_by_week[w]["corrected"]
        fas = [p for p in players.index if p not in rostered]
        res = ro.optimize(team, players, rosters, fas, cfg, ignore_opponents=ignore)
        if shadow is not None:
            alt = ro.optimize(team, players, rosters, fas, cfg, ignore_opponents=shadow)
            mine = [(sw.drop, sw.add) for sw in res.swaps]
            theirs = [(sw.drop, sw.add) for sw in alt.swaps]
            diffs.append({"week": w, "n_league": len(mine), "n_subset": len(theirs),
                          "same": set(mine) == set(theirs),
                          "same_adds": {a for _, a in mine} == {a for _, a in theirs}})
        for sw in res.swaps:
            roster[roster.index(sw.drop)] = sw.add
        n += len(res.swaps)
        end = int(s.weeks.loc[s.weeks["Week"] == w, "EndSP"].iloc[0])
        for day in range(sp, end + 1):
            daily[day] = list(roster)
    return daily, n, diffs


def run_year(args) -> tuple[pd.DataFrame, pd.DataFrame]:
    year, data, ref, pub, params, cap, ignored = args
    s = bt.Season(year, Path(data), Path(ref))
    key = str(year) if str(year) in params["coefs"] else "all"
    pbw = weekly_players(s, Path(pub), {c: np.array(v) for c, v in params["coefs"][key].items()})
    sp0 = int(s.week_start[1])
    first = pbw[s.rs_weeks[0]]["blend"]
    priority = (first["PTS"] + 1.2 * first["REB"] + 1.5 * first["AST"]).to_dict()
    base = {t: bt.weekly_totals(s, 1, bt.real_daily(s, t, sp0), priority) for t in s.teams}
    rows, diff_rows = [], []
    for team in s.teams:
        ignore = frozenset(ignored) - {team}
        sims = {"stand_pat": bt.weekly_totals(s, 1, bt.frozen_daily(s, s.roster_on(sp0)[team], sp0), priority)}
        swaps = {}
        daily, swaps["league"], diffs = rolling(s, team, pbw, frozenset(), cap, shadow=ignore)
        sims["league"] = bt.weekly_totals(s, 1, daily, priority)
        daily, swaps["subset"], _ = rolling(s, team, pbw, ignore, cap)
        sims["subset"] = bt.weekly_totals(s, 1, daily, priority)
        diff_rows += [{"year": year, "team": team, **d} for d in diffs]
        for row in s.comp[s.comp["Team"] == team].itertuples():
            wk = row.Week
            if wk not in base[row.Opp].index:
                continue
            opp = bt.cat_values(base[row.Opp].loc[wk])
            rec = {"year": year, "team": team, "week": wk, "opp": row.Opp, "vs_ignored": row.Opp in ignore,
                   **{f"swaps_{v}": swaps[v] for v in VARIANTS}}
            for k, sim in sims.items():
                if wk not in sim.index:
                    rec[k] = rec[f"{k}_cats"] = np.nan
                    continue
                W, L, T = bt.matchup(bt.cat_values(sim.loc[wk]), opp)
                rec[k] = 1.0 if W > L else 0.0 if L > W else 0.5
                rec[f"{k}_cats"] = W + 0.5 * T
            rows.append(rec)
        same = np.mean([d["same"] for d in diffs]) if diffs else float("nan")
        print(f"  {year} {team}: swaps {swaps}, same moves {same:.0%} of weeks", flush=True)
    return pd.DataFrame(rows), pd.DataFrame(diff_rows)


def summarize(d: pd.DataFrame, diffs: pd.DataFrame, ignored: list[str]) -> str:
    d = d[d.week <= 18]
    out = []
    diffs = diffs[diffs.week <= 18]
    out.append(f"Same roster, same week (whole-league path): subset recommends the same moves in {diffs.same.mean():.0%} of "
               f"{len(diffs)} team-weeks, the same pickups in {diffs.same_adds.mean():.0%}; it moves in "
               f"{(diffs.n_subset > 0).mean():.0%} of weeks vs {(diffs.n_league > 0).mean():.0%}.")
    seasons_same = diffs.groupby(["year", "team"]).same.all()
    out.append(f"  identical recommendations all season: {seasons_same.mean():.0%} of {len(seasons_same)} team-seasons")

    for label, mask in [("all games", slice(None)), (f"vs {'/'.join(ignored)}", d.vs_ignored), ("vs everyone else", ~d.vs_ignored)]:
        sub = d[mask] if not isinstance(mask, slice) else d
        t = sub.groupby(["year", "team"])[[*VARIANTS, "stand_pat", *[f"{v}_cats" for v in VARIANTS], "stand_pat_cats"]].sum()
        out.append(f"\n{label} ({len(sub)} games, {len(t)} team-seasons), season totals:")
        for v in VARIANTS:
            wlo, whi = ci(t[v] - t.stand_pat)
            clo, chi = ci(t[f"{v}_cats"] - t.stand_pat_cats)
            out.append(f"  {v:7s} vs stand pat: matchup wins {(t[v] - t.stand_pat).mean():+.2f} [{wlo:+.2f}, {whi:+.2f}]   "
                       f"category wins {(t[f'{v}_cats'] - t.stand_pat_cats).mean():+.1f} [{clo:+.1f}, {chi:+.1f}]")
        dw = t.subset - t.league
        dc = t.subset_cats - t.league_cats
        wlo, whi = ci(dw)
        clo, chi = ci(dc)
        out.append(f"  subset - league: matchup wins {dw.mean():+.2f} [{wlo:+.2f}, {whi:+.2f}] (better in {np.mean(dw > 0):.0%}, "
                   f"worse in {np.mean(dw < 0):.0%})   category wins {dc.mean():+.1f} [{clo:+.1f}, {chi:+.1f}]")
    t = d.groupby(["year", "team"])[[*VARIANTS, "swaps_league", "swaps_subset"]].agg(
        {"league": "sum", "subset": "sum", "swaps_league": "first", "swaps_subset": "first"})
    out.append(f"\nswaps / season: league {t.swaps_league.mean():.1f}, subset {t.swaps_subset.mean():.1f}")
    out.append("by season (matchup wins, subset - league): " + ", ".join(
        f"{y} {v:+.2f}" for y, v in (t.subset - t.league).groupby(level=0).mean().items()))
    excl = d[~d.team.isin(ignored)]
    te = excl.groupby(["year", "team"])[list(VARIANTS)].sum()
    lo, hi = ci(te.subset - te.league)
    out.append(f"teams other than {'/'.join(ignored)} only ({len(te)} team-seasons): subset - league "
               f"{(te.subset - te.league).mean():+.2f} [{lo:+.2f}, {hi:+.2f}]")
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
    ap.add_argument("--ignore", nargs="+", default=["Chirayu", "Saamrit"])
    ap.add_argument("--summary-only", action="store_true")
    args = ap.parse_args()
    diffs_path = args.out.with_name(args.out.stem + "_diffs.csv")
    if not args.summary_only:
        params = json.loads(Path(args.params_by_year).read_text())
        with ProcessPoolExecutor(max_workers=len(args.years)) as ex:
            parts = list(ex.map(run_year, [(y, args.data, args.ref, args.pub, params, args.cap, args.ignore) for y in args.years]))
        pd.concat([p[0] for p in parts]).to_csv(args.out, index=False)
        pd.concat([p[1] for p in parts]).to_csv(diffs_path, index=False)
    print(summarize(pd.read_csv(args.out), pd.read_csv(diffs_path), args.ignore))


if __name__ == "__main__":
    main()
