"""Tuning harness for the Trade Finder (Phase 7, _planning/trade-recommender.md).

Step 1 (`build`): at every checkpoint, for every team and every one of its
active players, collect a BROAD set of candidate trades (loose thresholds,
no lopsided filter) with the model's predictions, and score each one a
second time with an "oracle": the same standings scoring, but using what
every player actually produced over the rest of that regular season instead
of projections (rosters frozen at the checkpoint + the trade). The oracle
removes week-to-week matchup luck and lineup effects, so it's a low-noise
yardstick for "did this trade really make the team better" -- the full
replay (scripts/backtest_trade_finder.py) stays the final check.

Step 2 (`evaluate`, in a notebook/script): selection policies are filters and
rankings over that table; projection changes need a rebuild with another
blend config (`--variant`).

  python -m scripts.trade_finder_tuning --data <dir> --ref <ref> --out cands_<variant>.parquet \\
      [--years 2019 2020 2021] [--variant base]
"""
from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import backtest_roster_optimizer as bt  # noqa: E402
from scripts.backtest_trade_finder import CHECKPOINTS, active_rosters  # noqa: E402
from shared import roster_optimizer as ro  # noqa: E402
from shared import trade_finder as tf  # noqa: E402

COMP = ro.COMPONENTS

# Projection variants (blend configs) -- each needs its own build.
VARIANTS: dict[str, dict] = {
    "base": {},
}

BROAD = dict(mode="fleece", max_results=None, min_gain=0.0, partner_min_gain=-0.05, value_tolerance=1e9)


def oracle_lines(s: bt.Season, sp0: int, universe: pd.Index) -> pd.DataFrame:
    """Each player's real component totals from sp0 to the end of the RS."""
    last = int(s.weeks.loc[s.weeks["Week"] == max(s.rs_weeks), "EndSP"].iloc[0])
    g = s.games[(s.games["ScoringPeriod"] >= sp0) & (s.games["ScoringPeriod"] <= last)]
    tot = g.groupby("PlayerId")[COMP].sum().reindex(universe).fillna(0.0)
    tot.insert(0, "Player", "")
    return tot


def oracle_scores(league: tf.League, team: str, trades: list[tf.Trade]) -> np.ndarray:
    """(T, 2) score after each trade for (team, partner) under `league`'s
    player lines (the oracle's real totals, or an alternative projection)."""
    a = league.idx[team]
    comps = league.comps
    out = np.empty((len(trades), 2))
    # group by partner for vectorization
    by_partner: dict[str, list[int]] = {}
    for i, t in enumerate(trades):
        by_partner.setdefault(t.partner, []).append(i)
    for B, idx in by_partner.items():
        b = league.idx[B]
        sa, sb = league.scale[a], league.scale[b]
        S = np.repeat(league.sums[None], len(idx), axis=0)
        for r, i in enumerate(idx):
            t = trades[i]
            give = comps.loc[t.give].to_numpy().sum(0)
            get = comps.loc[t.get].to_numpy().sum(0)
            S[r, a] += sa * (get - give)
            S[r, b] += sb * (give - get)
            if t.fa_add is not None:
                S[r, a] += sa * comps.loc[t.fa_add].to_numpy()
            if t.partner_drop is not None:
                S[r, b] -= sb * comps.loc[t.partner_drop].to_numpy()
        sc, _ = league.score(S, [a, b])
        out[idx] = sc
    return out


def build_year(args: tuple) -> pd.DataFrame:
    year, data, ref, variant = args
    s = bt.Season(year, Path(data), Path(ref))
    blend_cfg = ro.OptimizerConfig(**VARIANTS[variant])
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
        players = ro.blend_players(stats, projections, blend_cfg, replacement_pool=pd.Index(fas), days_elapsed=sp0 - 1)
        score_cfg = ro.recommended_config(**VARIANTS[variant])
        league = tf.League(players, rosters, score_cfg)
        rostered = pd.Index([p for ids in rosters.values() for p in ids])
        v_proj = tf.player_value(league.comps, rostered)
        olines = oracle_lines(s, sp0, players.index)
        oleague = tf.League(olines, rosters, ro.recommended_config(use_availability=False))
        v_orc = tf.player_value(oleague.comps, rostered)
        obase, _ = oleague.score(oleague.sums, list(range(len(oleague.teams))))
        # Alternative views of the same players, for robustness checks:
        #   real   season-to-date per-game for players with >= 8 games (blend otherwise)
        #   prior  the preseason prior only (projection + a little last season)
        #   fah    the blend with every free agent's line cut 15%
        real, gp = ro._real_per_game(stats.set_index("PlayerId"), "season")
        alt_real = players.copy()
        ok = (gp >= 8) & real.notna().all(axis=1)
        ok = ok.reindex(alt_real.index).fillna(False).astype(bool)
        alt_real.loc[ok, COMP] = real.loc[ok[ok].index, COMP].to_numpy()
        alt_prior = ro.blend_players(stats, projections, ro.OptimizerConfig(**{**VARIANTS[variant], "k_games": 1e12}),
                                     replacement_pool=pd.Index(fas), days_elapsed=sp0 - 1)
        alt_fah = players.copy()
        fa_idx = alt_fah.index.intersection(pd.Index(fas))
        alt_fah.loc[fa_idx, COMP] = alt_fah.loc[fa_idx, COMP] * 0.85
        alts = {}
        for name, frame in (("real", alt_real), ("prior", alt_prior), ("fah", alt_fah)):
            lg = tf.League(frame, rosters, score_cfg)
            alts[name] = (lg, lg.score(lg.sums, list(range(len(lg.teams))))[0])
        weeks_left = len([w for w in s.rs_weeks if w >= cp])

        for team in s.teams:
            seen = {}
            for x in rosters[team]:
                res = tf.find_trades(team, [x], players, rosters, fas, tf.TradeConfig(optimizer=score_cfg, **BROAD))
                for t in res.trades:
                    key = (t.shape, t.partner, tuple(sorted(t.give)), t.get[0])
                    if key not in seen:
                        seen[key] = t
            trades = list(seen.values())
            if not trades:
                continue
            orc = oracle_scores(oleague, team, trades)
            alt_sc = {name: oracle_scores(lg, team, trades) for name, (lg, _) in alts.items()}
            a = oleague.idx[team]
            for i, (t, (oa, ob)) in enumerate(zip(trades, orc)):
                b = oleague.idx[t.partner]
                g2 = t.give[1] if len(t.give) > 1 else None
                rec = {
                    "year": year, "checkpoint": cp, "weeks_left": weeks_left, "team": team, "partner": t.partner,
                    "shape": t.shape, "give1": t.give[0], "give2": g2, "get": t.get[0],
                    "drop": t.partner_drop, "fa": t.fa_add,
                    "pred_gain": t.gain, "pred_partner_gain": t.partner_gain,
                    "partner_value_net": t.partner_value_net,
                    "orc_gain": float(oa - obase[a]), "orc_partner_gain": float(ob - obase[b]),
                }
                for name, (lg, base_sc) in alts.items():
                    rec[f"{name}_gain"] = float(alt_sc[name][i, 0] - base_sc[a])
                    rec[f"{name}_partner_gain"] = float(alt_sc[name][i, 1] - base_sc[b])
                for role in ["give1", "give2", "get", "drop", "fa"]:
                    pid = rec[role]
                    ok = pid is not None and pid == pid
                    rec[f"{role}_gp"] = float(players.at[pid, "GP"]) if ok else np.nan
                    rec[f"{role}_avail"] = float(players.at[pid, "availability"]) if ok else np.nan
                    rec[f"{role}_vproj"] = float(v_proj.get(pid, np.nan)) if ok else np.nan
                    rec[f"{role}_vorc"] = float(v_orc.get(pid, np.nan)) if ok else np.nan
                rows.append(rec)
        print(f"  [{variant}] {year} week {cp}: {time.time() - t0:.0f}s, {len(rows)} rows", flush=True)
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--years", type=int, nargs="+", default=[2019, 2020, 2021])
    ap.add_argument("--variant", default="base", choices=list(VARIANTS))
    args = ap.parse_args()
    with ProcessPoolExecutor(max_workers=len(args.years)) as ex:
        frames = list(ex.map(build_year, [(y, args.data, args.ref, args.variant) for y in args.years]))
    df = pd.concat(frames, ignore_index=True)
    df.to_parquet(args.out) if args.out.suffix == ".parquet" else df.to_csv(args.out, index=False)
    print(f"wrote {len(df)} candidate trades -> {args.out}")


if __name__ == "__main__":
    main()
