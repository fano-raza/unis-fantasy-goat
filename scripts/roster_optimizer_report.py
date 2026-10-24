"""Runs the Roster Optimizer (shared/roster_optimizer.py) on real league data
and prints both variants -- Full punt and Balanced -- side by side for one
team or every team. Standalone testing tool for Phase 6; not used by the app.

Inputs (CSV, or JSON as returned by the API):
  --stats        Ref/player_stats.csv          (GET /league/player_stats)
  --rosters      Ref/roster_ranks.csv          (POST /league/roster_ranks)
  --projections  Ref/player_projections.csv    (scripts/export_player_projections.py)

  python -m scripts.roster_optimizer_report --team Fano
  python -m scripts.roster_optimizer_report --all --balanced-weight 0.25
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared import roster_optimizer as ro  # noqa: E402


def _load(path: str) -> pd.DataFrame:
    if path.endswith(".json"):
        return pd.DataFrame(json.load(open(path)))
    return pd.read_csv(path)


def load_league(stats_path: str, rosters_path: str, projections_path: str, year: int, config: ro.OptimizerConfig, window: str):
    stats = _load(stats_path)
    roster_rows = _load(rosters_path)
    roster_rows = roster_rows[roster_rows["Year"] == year]
    projections = _load(projections_path)

    name_to_id = dict(zip(stats["Player"], stats["PlayerId"]))
    rosters: dict[str, list] = {}
    unmatched = []
    for _, row in roster_rows.iterrows():
        team = row["FantasyTeam"]
        if not isinstance(team, str) or not team:
            continue
        pid = name_to_id.get(row["Player"])
        if pid is None:
            unmatched.append(row["Player"])
            continue
        rosters.setdefault(team, []).append(pid)
    if unmatched:
        print(f"WARNING: {len(unmatched)} rostered players have no stats row: {unmatched}")

    rostered = {pid for ids in rosters.values() for pid in ids}
    free_agents = [pid for pid in stats["PlayerId"] if pid not in rostered]
    players = ro.blend_players(stats, projections, config, window=window, replacement_pool=pd.Index(free_agents))
    return players, rosters, free_agents


def fmt_ratings(ratings: dict, targets: list[str]) -> str:
    return "  ".join(f"{c}{'*' if c in targets else ''} {ratings[c]:.2f}" for c in ratings)


def report(team: str, players, rosters, free_agents, base: ro.OptimizerConfig, balanced_weight: float) -> None:
    variants = [("Full punt", 0.0), (f"Balanced (other x{balanced_weight:g})", balanced_weight)]
    results = []
    for label, w in variants:
        cfg = ro.OptimizerConfig(**{**base.__dict__, "other_weight": w})
        results.append((label, ro.optimize(team, players, rosters, free_agents, cfg)))

    first = results[0][1]
    print(f"\n{'=' * 78}\n{team}  -- targets: {', '.join(first.targets)}   (* = target, TO ignored)")
    print(f"  start   {fmt_ratings(first.start_ratings, first.targets)}")
    for label, res in results:
        print(f"\n  {label}: objective {res.start_objective:.3f} -> {res.end_objective:.3f} in {len(res.swaps)} swaps")
        for k, s in enumerate(res.swaps, 1):
            d, a = players.loc[s.drop], players.loc[s.add]
            print(
                f"    {k:2}. drop {s.drop_name:<24} add {s.add_name:<24} +{s.gain:.3f}"
                f"   (add: {a['GP']:.0f} GP, real wt {a['w_real']:.0%}, prior {a['prior']})"
            )
        print(f"    end   {fmt_ratings(res.end_ratings, res.targets)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stats", required=True)
    parser.add_argument("--rosters", required=True)
    parser.add_argument("--projections", required=True)
    parser.add_argument("--year", type=int, default=2027)
    parser.add_argument("--window", default="season")
    parser.add_argument("--team")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--balanced-weight", type=float, default=0.25)
    parser.add_argument("--max-swaps", type=int, default=14)
    args = parser.parse_args()

    base = ro.OptimizerConfig(max_swaps=args.max_swaps)
    players, rosters, free_agents = load_league(args.stats, args.rosters, args.projections, args.year, base, args.window)
    print(f"{len(players)} players ({players['prior'].value_counts().to_dict()}), "
          f"{len(rosters)} teams, {len(free_agents)} free agents")
    teams = sorted(rosters) if args.all else [args.team]
    for team in teams:
        report(team, players, rosters, free_agents, base, args.balanced_weight)


if __name__ == "__main__":
    main()
