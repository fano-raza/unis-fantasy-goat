"""Roster Optimizer weekly backtest: current projections (blend_players) vs
the corrected projections (shared/projection_adjust) -- the check agreed
with the user before the optimizer adopts the Trade Finder's projection
change (_planning/trade-recommender.md, "Next steps").

Same setup as scripts/backtest_weekly_strategies.py: every team-season
2019-2023 starts from its post-draft roster; each week the optimizer
(recommended_config, up to --cap swaps) re-runs on that week's information;
opponents keep their real daily rosters; every week is scored against the
real opponent. Out of sample: seasons the correction was fitted on (2019,
2021, 2022) use coefficients fitted WITHOUT that season (--params-by-year);
2020 and 2023 were never used in fitting.

  python -m scripts.backtest_optimizer_projections --data <backtest dir> --ref <ref dir> \\
      --pub <public ESPN dir with MIN/GS> --params-by-year adjust_params.json --out out.csv
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
from shared import projection_adjust as pa  # noqa: E402
from shared import roster_optimizer as ro  # noqa: E402

VARIANTS = ("blend", "corrected")


def weekly_players(s: bt.Season, pub: Path, coefs: dict) -> dict[int, dict[str, pd.DataFrame]]:
    """Week -> {variant: players} using each week's first-day information.
    The replacement-level pool is that day's real free agents (shared by
    every team -- a negligible simplification, identical for both variants)."""
    games = pd.read_csv(pub / f"{s.year}_games.csv")
    pproj = pd.read_csv(pub / f"{s.year}_projections.csv").set_index("PlayerId")
    prev_path = pub / f"{s.year - 1}_games.csv"
    last_mpg = None
    if prev_path.exists():
        prev = pd.read_csv(prev_path)
        last_mpg = prev.groupby("PlayerId")["MIN"].sum() / prev.groupby("PlayerId").size()
    out = {}
    for w in s.rs_weeks:
        sp = int(s.week_start[w])
        stats, projections = bt.checkpoint_inputs(s, sp)
        rostered = {p for ids in s.roster_on(sp).values() for p in ids}
        fas = [p for p in stats["PlayerId"] if p not in rostered]
        blend = ro.blend_players(stats, projections, ro.OptimizerConfig(), replacement_pool=pd.Index(fas),
                                 days_elapsed=sp - 1)
        prior = pproj["proj_MIN"].reindex(blend.index) if "proj_MIN" in pproj else pd.Series(np.nan, index=blend.index)
        if last_mpg is not None:
            prior = prior.fillna(last_mpg.reindex(blend.index))
        corrected = pa.adjusted_players(blend, games, sp, prior, {"coefs": coefs})
        out[w] = {"blend": blend, "corrected": corrected}
    return out


def rolling(s: bt.Season, team: str, players_by_week, variant: str, cap: int) -> tuple[dict[int, list], int]:
    roster = list(s.roster_on(int(s.week_start[1]))[team])
    daily, n = {}, 0
    cfg = ro.recommended_config(max_swaps=cap)
    for w in s.rs_weeks:
        sp = int(s.week_start[w])
        rosters = s.roster_on(sp)
        rosters[team] = list(roster)
        rostered = {p for ids in rosters.values() for p in ids}
        players = players_by_week[w][variant]
        fas = [p for p in players.index if p not in rostered]
        res = ro.optimize(team, players, rosters, fas, cfg)
        for sw in res.swaps:
            roster[roster.index(sw.drop)] = sw.add
        n += len(res.swaps)
        end = int(s.weeks.loc[s.weeks["Week"] == w, "EndSP"].iloc[0])
        for day in range(sp, end + 1):
            daily[day] = list(roster)
    return daily, n


def run_year(args) -> pd.DataFrame:
    year, data, ref, pub, params, cap = args
    s = bt.Season(year, Path(data), Path(ref))
    key = str(year) if str(year) in params["coefs"] else "all"
    coefs = {c: np.array(v) for c, v in params["coefs"][key].items()}
    pbw = weekly_players(s, Path(pub), coefs)
    sp0 = int(s.week_start[1])
    first = pbw[s.rs_weeks[0]]["blend"]
    priority = (first["PTS"] + 1.2 * first["REB"] + 1.5 * first["AST"]).to_dict()
    base = {t: bt.weekly_totals(s, 1, bt.real_daily(s, t, sp0), priority) for t in s.teams}
    rows = []
    for team in s.teams:
        sims, swaps = {"actual": base[team],
                       "stand_pat": bt.weekly_totals(s, 1, bt.frozen_daily(s, s.roster_on(sp0)[team], sp0), priority)}, {}
        for v in VARIANTS:
            daily, n = rolling(s, team, pbw, v, cap)
            sims[v] = bt.weekly_totals(s, 1, daily, priority)
            swaps[v] = n
        for row in s.comp[s.comp["Team"] == team].itertuples():
            wk = row.Week
            if wk not in base[row.Opp].index:
                continue
            opp = bt.cat_values(base[row.Opp].loc[wk])
            rec = {"year": year, "team": team, "week": wk, **{f"swaps_{v}": swaps[v] for v in VARIANTS}}
            for k, sim in sims.items():
                if wk not in sim.index:
                    rec[k] = rec[f"{k}_cats"] = np.nan
                    continue
                W, L, T = bt.matchup(bt.cat_values(sim.loc[wk]), opp)
                rec[k] = 1.0 if W > L else 0.0 if L > W else 0.5
                rec[f"{k}_cats"] = W + 0.5 * T
            rows.append(rec)
        print(f"  {year} {team}: swaps blend {swaps['blend']}, corrected {swaps['corrected']}", flush=True)
    return pd.DataFrame(rows)


def ci(v, n=4000, seed=0):
    v = np.asarray(v, float)
    b = np.random.default_rng(seed).choice(v, (n, len(v))).mean(1)
    return np.percentile(b, 2.5), np.percentile(b, 97.5)


def summarize(d: pd.DataFrame) -> str:
    d = d[d.week <= 18]
    t = d.groupby(["year", "team"]).agg(
        **{k: (k, "sum") for k in ("blend", "corrected", "stand_pat", "actual")},
        **{f"{k}_c": (f"{k}_cats", "sum") for k in ("blend", "corrected", "stand_pat")},
        sb=("swaps_blend", "first"), sc=("swaps_corrected", "first"))
    out = [f"{len(t)} team-seasons; wins over 18 weeks vs never changing the drafted roster:"]
    for k in ("blend", "corrected", "actual"):
        x = t[k] - t.stand_pat
        lo, hi = ci(x)
        out.append(f"  {k:10s} {x.mean():+.2f} [{lo:+.2f}, {hi:+.2f}]")
    x = t.corrected - t.blend
    lo, hi = ci(x)
    xc = t.corrected_c - t.blend_c
    clo, chi = ci(xc)
    out.append(f"corrected - blend: {x.mean():+.2f} wins [{lo:+.2f}, {hi:+.2f}], better in {np.mean(x > 0):.0%} / worse in "
               f"{np.mean(x < 0):.0%}; category wins {xc.mean():+.1f} [{clo:+.1f}, {chi:+.1f}]")
    out.append("by season (corrected - blend wins): " + ", ".join(
        f"{y} {v:+.2f}" for y, v in (t.corrected - t.blend).groupby(level=0).mean().items()))
    out.append(f"swaps per season: blend {t.sb.mean():.1f}, corrected {t.sc.mean():.1f}")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--pub", required=True)
    ap.add_argument("--params-by-year", required=True, help="JSON with coefs keyed by held-out year (+ 'all')")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--years", type=int, nargs="+", default=[2019, 2020, 2021, 2022, 2023])
    ap.add_argument("--cap", type=int, default=3, help="swaps per week (live default 3)")
    ap.add_argument("--summary-only", action="store_true")
    args = ap.parse_args()
    if not args.summary_only:
        params = json.loads(Path(args.params_by_year).read_text())
        with ProcessPoolExecutor(max_workers=len(args.years)) as ex:
            df = pd.concat(ex.map(run_year, [(y, args.data, args.ref, args.pub, params, args.cap) for y in args.years]))
        df.to_csv(args.out, index=False)
    print(summarize(pd.read_csv(args.out)))


if __name__ == "__main__":
    main()
