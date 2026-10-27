"""Projection research (Phase 7 follow-up, _planning/trade-recommender.md):
can we predict a player's rest-of-season production better than the Roster
Optimizer's blend (shared/roster_optimizer.blend_players) -- in particular,
spot the players who will beat their preseason projection?

Data: scripts/export_espn_public_season.py output (games with MIN/GS,
projections with proj_MIN) for 2018-2026. Clean preseason projections:
2018, 2019, 2021, 2022 (dev); 2020 has almost none, 2023's are a mid-season
snapshot; 2024-2026 are the untouched hold-out -- never evaluated here until
the final check.

`build` writes one row per (season, checkpoint day, player): what was known
at the checkpoint, the current blend's per-game line, and what actually
happened over the rest of the season.

  python -m scripts.projection_research build --data <pub dir> --years 2018 2019 2021 2022 --out rows.pkl
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import backtest_roster_optimizer as bt  # noqa: E402
from shared import roster_optimizer as ro  # noqa: E402

COMP = ro.COMPONENTS
CHECKPOINT_DAYS = tuple(range(14, 147, 7))  # weekly, ~week 3 to ~week 21


def load(data: Path, year: int) -> SimpleNamespace:
    games = pd.read_csv(data / f"{year}_games.csv")
    proj = pd.read_csv(data / f"{year}_projections.csv")
    prev = data / f"{year - 1}_games.csv"
    s = SimpleNamespace(
        year=year, games=games, proj=proj,
        prev_games=pd.read_csv(prev) if prev.exists() else None,
        rosters=pd.DataFrame({"PlayerId": pd.Series(dtype=int)}),
        names=dict(zip(proj["PlayerId"], proj["Player"])),
    )
    return s


def window(g: pd.DataFrame, prefix: str, universe) -> pd.DataFrame:
    agg = g.groupby("PlayerId")[COMP + ["MIN", "GS"]].sum().reindex(universe)
    gp = g.groupby("PlayerId").size().reindex(universe).fillna(0)
    out = pd.DataFrame(index=universe)
    out[f"{prefix}_GP"] = gp
    for c in COMP + ["MIN", "GS"]:
        out[f"{prefix}_{c}"] = agg[c].fillna(0)   # totals
    return out


def build_year(args) -> pd.DataFrame:
    data, year = args
    s = load(Path(data), year)
    last_day = int(s.games["ScoringPeriod"].max())
    prev = None
    if s.prev_games is not None:
        pg = s.prev_games
        prev = window(pg, "last", pd.Index(sorted(pg["PlayerId"].unique())))
    rows = []
    for cp in CHECKPOINT_DAYS:
        if cp >= last_day - 20:
            break
        stats, projections = bt.checkpoint_inputs(s, cp)
        blend = ro.blend_players(stats, projections, ro.OptimizerConfig(), days_elapsed=cp - 1)
        universe = blend.index
        g = s.games
        before, after = g[g["ScoringPeriod"] < cp], g[g["ScoringPeriod"] >= cp]
        f = pd.concat([
            window(before, "szn", universe),
            window(before[before["ScoringPeriod"] >= cp - 14], "r14", universe),
            window(before[before["ScoringPeriod"] >= cp - 30], "r30", universe),
            window(after, "act", universe),
        ], axis=1)
        pr = s.proj.set_index("PlayerId").reindex(universe)
        for c in COMP + ["MIN", "GP"]:
            f[f"proj_{c}"] = pr[f"proj_{c}"] if f"proj_{c}" in pr else np.nan
        if prev is not None:
            lp = prev.reindex(universe)
            for c in ["GP"] + COMP + ["MIN"]:
                f[f"last_{c}"] = lp[f"last_{c}"]
        for c in COMP:
            f[f"blend_{c}"] = blend[c]
        f["blend_avail"] = blend["availability"]
        f["prior_kind"] = blend["prior"]
        f["year"], f["cp"] = year, cp
        f["days_left"] = last_day - cp + 1
        f["Player"] = blend["Player"]
        rows.append(f.reset_index().rename(columns={"index": "PlayerId"}))
        print(f"  {year} day {cp}: {len(f)} players", flush=True)
    return pd.concat(rows, ignore_index=True)


def main() -> None:
    from concurrent.futures import ProcessPoolExecutor

    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build"])
    ap.add_argument("--data", required=True)
    ap.add_argument("--years", type=int, nargs="+", required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    with ProcessPoolExecutor(max_workers=min(8, len(args.years))) as ex:
        df = pd.concat(ex.map(build_year, [(args.data, y) for y in args.years]), ignore_index=True)
    df.to_pickle(args.out)
    print(f"wrote {len(df)} rows -> {args.out}")


if __name__ == "__main__":
    main()
