"""Exports every NBA player's ESPN season projection and last season's actual
per-game averages into Ref/player_projections.csv -- the prior that the
Roster Optimizer (shared/roster_optimizer.py) blends with real season-to-date
stats (Ref/player_stats.csv) while there are still few games played.

One kona_player_info call returns both, per player:
  - statSourceId=1, seasonId=<year>, statSplitTypeId=0  -> ESPN's season projection
  - statSourceId=0, seasonId=<year-1>, statSplitTypeId=0 -> last season's actuals
(verified live 2026-10-24). Values are ESPN's own per-game `averageStats`.
Yahoo was investigated as a second projection source and has none for NBA via
its API -- see _planning/web-app-build-plan.md Phase 6.

Joins to player_stats.csv on PlayerId (both are ESPN player ids).

Not yet wired into the daily stat-updater loop -- Phase 6 is still being
tested standalone. Usage:
  python -m scripts.export_player_projections            # currentYear
  python -m scripts.export_player_projections --year 2027
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

from constants import currentYear, espnLeagueIDs, espn_s2, espn_swid  # noqa: E402
from shared.atomic_write import atomic_write  # noqa: E402
from shared.runtime_config import REF_DIR  # noqa: E402

OUTPUT_PATH = REF_DIR / "player_projections.csv"

# Same full-pool limit as export_roster_ranks.py -- comfortably above the real
# pool size, no paging needed.
ESPN_PLAYER_POOL_LIMIT = 2000

# ESPN stat id -> our column suffix (espn_fr/basketball/constant.py STATS_MAP).
# Makes/attempts rather than FG%/FT% so percentages can be re-aggregated
# correctly across players.
ESPN_STATS = {
    "0": "PTS",
    "6": "REB",
    "3": "AST",
    "2": "STL",
    "1": "BLK",
    "11": "TO",
    "17": "3PTM",
    "13": "FGM",
    "14": "FGA",
    "15": "FTM",
    "16": "FTA",
}
ESPN_GP_STAT = "42"


def _find_split(stats: list[dict], source: int, season: int) -> dict | None:
    for s in stats:
        if s.get("statSourceId") == source and s.get("seasonId") == season and s.get("statSplitTypeId") == 0:
            return s
    return None


def rows_for_year(year: int) -> list[dict]:
    from espn_fr.basketball.constant import PRO_TEAM_MAP
    from espn_fr.basketball.league import League

    league = League(espnLeagueIDs.get(year) or espnLeagueIDs[2019], year, espn_s2=espn_s2, swid=espn_swid)
    filters = {
        "players": {
            "filterStatus": {"value": ["FREEAGENT", "WAIVERS", "ONTEAM"]},
            "limit": ESPN_PLAYER_POOL_LIMIT,
            "sortPercOwned": {"sortPriority": 1, "sortAsc": False},
        }
    }
    data = league.espn_request.league_get(
        params={"view": "kona_player_info"},
        headers={"x-fantasy-filter": json.dumps(filters)},
    )

    rows: list[dict] = []
    for entry in data["players"]:
        player = entry["player"]
        stats = player.get("stats") or []
        row: dict = {
            "PlayerId": player["id"],
            "Player": player.get("fullName"),
            "Team": PRO_TEAM_MAP.get(player.get("proTeamId"), ""),
            # ACTIVE / DAY_TO_DAY / OUT / ... (missing for many deep-bench
            # players). The optimizer keeps OUT players out of the free-agent
            # pool -- a projection says nothing about whether they can play.
            "InjuryStatus": player.get("injuryStatus") or "",
        }
        proj = _find_split(stats, source=1, season=year)
        last = _find_split(stats, source=0, season=year - 1)
        for prefix, split in (("proj", proj), ("last", last)):
            avg = (split or {}).get("averageStats") or {}
            for stat_id, name in ESPN_STATS.items():
                value = avg.get(stat_id)
                row[f"{prefix}_{name}"] = float(value) if value is not None else None
        # Games played: projected games (ESPN projects a GP total) and last
        # season's real GP -- the optimizer uses last_GP to discount a tiny
        # last-season sample.
        row["proj_GP"] = ((proj or {}).get("stats") or {}).get(ESPN_GP_STAT)
        row["last_GP"] = ((last or {}).get("stats") or {}).get(ESPN_GP_STAT)
        rows.append(row)
    return rows


def main(year: int) -> None:
    df = pd.DataFrame(rows_for_year(year))
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(OUTPUT_PATH, lambda f: df.to_csv(f, index=False))
    print(
        f"Wrote {len(df)} players to {OUTPUT_PATH} "
        f"({df['proj_PTS'].notna().sum()} with a projection, {df['last_PTS'].notna().sum()} with last-season stats)"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--year", type=int, default=currentYear)
    main(parser.parse_args().year)
