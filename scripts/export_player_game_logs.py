"""This season's per-game logs (with minutes and starts) and each player's
preseason minutes expectation -- the inputs of the projection correction
(shared/projection_adjust.py) that the Roster Optimizer and Trade Finder
share (_planning/trade-recommender.md; user decision 2026-10-27: one set of
player projections for both tools).

Source: ESPN's public player endpoint (no league or login needed), the same
one scripts/export_espn_public_season.py uses for the backtest seasons.

Writes:
  Ref/player_game_logs.csv     PlayerId, ScoringPeriod, FGM ... PTS, MIN, GS
                               (one row per game played this season)
  Ref/player_minutes_prior.csv PlayerId, prior_MPG, prior_source
                               (ESPN's projected minutes per game, else last
                               season's actual)

Runs daily in the stat-updater loop, after export_player_projections.
  python3 -m scripts.export_player_game_logs [--year 2027]
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

from scripts.export_espn_public_season import COMP, EXTRA, STATS, URL  # noqa: E402
from shared.atomic_write import atomic_write  # noqa: E402
from shared.runtime_config import REF_DIR  # noqa: E402

GAME_LOGS_PATH = REF_DIR / "player_game_logs.csv"
MINUTES_PRIOR_PATH = REF_DIR / "player_minutes_prior.csv"


def fetch(year: int) -> list[dict]:
    import requests

    r = requests.get(URL.format(year=year), params={"scoringPeriodId": 0, "view": "kona_player_info"},
                     headers={"X-Fantasy-Filter": json.dumps({"players": {"limit": 5000}})}, timeout=120)
    r.raise_for_status()
    return r.json()


def parse(players: list[dict], year: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    games, prior = [], []
    for p in players:
        pid = p["id"]
        proj_mpg = last_mpg = None
        for s in p.get("stats") or []:
            st = s.get("stats") or {}
            season, source, split = s.get("seasonId"), s.get("statSourceId"), s.get("statSplitTypeId")
            # The response also carries last season's games -- keep this season's only.
            if season == year and source == 0 and split == 5 and st.get("42") == 1:
                games.append({"PlayerId": pid, "ScoringPeriod": int(s["scoringPeriodId"]),
                              **{c: float(st.get(k, 0.0)) for k, c in STATS.items()},
                              **{c: float(st.get(k, 0.0)) for k, c in EXTRA.items()}})
            elif season == year and source == 1 and split == 0 and st.get("42"):
                proj_mpg = float(st.get("40", 0.0)) / float(st["42"])
            elif season == year - 1 and source == 0 and split == 0 and st.get("42"):
                last_mpg = float(st.get("40", 0.0)) / float(st["42"])
        if proj_mpg:
            prior.append({"PlayerId": pid, "prior_MPG": proj_mpg, "prior_source": "projection"})
        elif last_mpg:
            prior.append({"PlayerId": pid, "prior_MPG": last_mpg, "prior_source": "last_season"})
    cols = ["PlayerId", "ScoringPeriod"] + COMP + list(EXTRA.values())
    return pd.DataFrame(games, columns=cols), pd.DataFrame(prior, columns=["PlayerId", "prior_MPG", "prior_source"])


def main(year: int | None = None) -> None:
    if year is None:
        from constants import currentYear
        year = currentYear
    games, prior = parse(fetch(year), year)
    if prior.empty:
        # A response with no projections or last season at all means the
        # endpoint changed -- fail loudly rather than write an empty prior.
        raise RuntimeError(f"ESPN public endpoint returned no minutes prior for {year}")
    REF_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write(GAME_LOGS_PATH, lambda f: games.to_csv(f, index=False))
    atomic_write(MINUTES_PRIOR_PATH, lambda f: prior.to_csv(f, index=False))
    print(f"Wrote {len(games)} games ({games['PlayerId'].nunique() if len(games) else 0} players) to {GAME_LOGS_PATH}, "
          f"{len(prior)} minutes priors to {MINUTES_PRIOR_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--year", type=int, default=None)
    main(parser.parse_args().year)
