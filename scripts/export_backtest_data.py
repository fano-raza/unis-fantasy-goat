"""Exports one past ESPN season's raw data for the Roster Optimizer backtest
(scripts/backtest_roster_optimizer.py, Phase 6 in _planning/web-app-build-plan.md):

  <out>/<year>_games.csv        every player's real game rows (PlayerId, ScoringPeriod,
                                FGM..PTS) for the whole season, keyed by ESPN's day
                                index (its dates are UTC, so late games roll over)
  <out>/<year>_weeks.csv        exact week -> day ranges, probed from ESPN
  <out>/<year>_projections.csv  ESPN's stored season projection per player (+ proj_GP)
  <out>/<year>_rosters.csv      every fantasy team's roster on EVERY scoring period (day)
                                of the season, with lineup slot (Team, ScoringPeriod,
                                PlayerId, LineupSlotId)

Weeks are probed from ESPN (probe_weeks) rather than read from
Ref/week_calendar.csv, whose rule-derived ESPN-season dates miss irregular
weeks. Daily rosters + game rows + weeks let the backtest rebuild each team's
real weekly totals and check them against Ref/<year>_CompStats.csv.

Rosters come from ESPN's day-by-day roster history (view=mRoster with a
scoringPeriodId) -- verified live 2026-10-24 that past seasons keep it
(2019 rosters differ between day 1, day 35, day 80 and the final day).

Needs ESPN credentials, so it runs in the stat-updater container:
  python -m scripts.export_backtest_data --year 2019 --out /tmp/backtest
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

from constants import espnLeagueIDs, espnTeamIDs, espn_s2, espn_swid  # noqa: E402

# ESPN Player.stats per-game totals keys -> our component names.
GAME_STATS = {"FGM": "FGM", "FGA": "FGA", "FTM": "FTM", "FTA": "FTA", "3PTM": "3PTM",
              "REB": "REB", "AST": "AST", "STL": "STL", "BLK": "BLK", "TO": "TO", "PTS": "PTS"}
PROJ_STATS = {"0": "PTS", "6": "REB", "3": "AST", "2": "STL", "1": "BLK", "11": "TO",
              "17": "3PTM", "13": "FGM", "14": "FGA", "15": "FTM", "16": "FTA"}
CHUNK_SIZE = 400


def export(year: int, out: Path, reuse_rosters: bool = False) -> None:
    from espn_fr.basketball.league import League

    out.mkdir(parents=True, exist_ok=True)
    league = League(espnLeagueIDs[year], year, espn_s2=espn_s2, swid=espn_swid)
    team_names = {k: v for k, v in espnTeamIDs[year].items() if isinstance(k, int)}

    # Projections (whole player pool).
    filters = {"players": {"filterStatus": {"value": ["FREEAGENT", "WAIVERS", "ONTEAM"]}, "limit": 3000,
                           "sortPercOwned": {"sortPriority": 1, "sortAsc": False}}}
    pool = league.espn_request.league_get(params={"view": "kona_player_info"},
                                          headers={"x-fantasy-filter": json.dumps(filters)})["players"]
    proj_rows = []
    for entry in pool:
        p = entry["player"]
        row = {"PlayerId": p["id"], "Player": p.get("fullName")}
        split = next((s for s in p.get("stats") or [] if s.get("statSourceId") == 1
                      and s.get("seasonId") == year and s.get("statSplitTypeId") == 0), None)
        avg = (split or {}).get("averageStats") or {}
        for sid, name in PROJ_STATS.items():
            row[f"proj_{name}"] = avg.get(sid)
        row["proj_GP"] = ((split or {}).get("stats") or {}).get("42")
        proj_rows.append(row)
    pd.DataFrame(proj_rows).to_csv(out / f"{year}_projections.csv", index=False)

    # Every team's roster + lineup slot on every day of the season (slow:
    # one request per day -- reuse_rosters skips it when a previous run's
    # file is already there).
    roster_path = out / f"{year}_rosters.csv"
    if reuse_rosters and roster_path.exists():
        rosters = pd.read_csv(roster_path)
    else:
        roster_rows = []
        for sp in range(1, league.finalScoringPeriod + 1):
            data = league.espn_request.league_get(params={"view": "mRoster", "scoringPeriodId": sp})
            for team in data["teams"]:
                name = team_names.get(team["id"], str(team["id"]))
                for e in team["roster"]["entries"]:
                    roster_rows.append({"Team": name, "ScoringPeriod": sp,
                                        "PlayerId": e["playerPoolEntry"]["player"]["id"],
                                        "LineupSlotId": e.get("lineupSlotId")})
        rosters = pd.DataFrame(roster_rows)
        rosters.to_csv(roster_path, index=False)

    # Game rows: player_map ∪ projection pool ∪ every player who was ever
    # rostered (some, e.g. players retired since, are missing from
    # player_map -- the first 2019 run lost ~5% of real production that way).
    ids = sorted({v for k, v in league.player_map.items() if isinstance(k, str)}
                 | {r["PlayerId"] for r in proj_rows} | set(rosters["PlayerId"].astype(int)))
    game_rows = []
    for i in range(0, len(ids), CHUNK_SIZE):
        chunk = ids[i:i + CHUNK_SIZE]
        try:
            result = league.player_info(playerId=chunk)
        except Exception as exc:  # one bad chunk shouldn't sink the export
            print(f"skipping chunk {i}: {exc}", file=sys.stderr)
            continue
        for player in result if isinstance(result, list) else [result]:
            for key, entry in (player.stats or {}).items():
                totals = entry.get("total") or {}
                if not key.isdigit() or totals.get("GP", 0) != 1:
                    continue
                row = {"PlayerId": player.playerId, "ScoringPeriod": int(key)}
                for src, name in GAME_STATS.items():
                    row[name] = totals.get(src, 0) or 0
                game_rows.append(row)
    pd.DataFrame(game_rows).to_csv(out / f"{year}_games.csv", index=False)

    weeks = probe_weeks(league)
    pd.DataFrame(weeks, columns=["Week", "StartSP", "EndSP"]).to_csv(out / f"{year}_weeks.csv", index=False)

    missing = set(rosters["PlayerId"].astype(int)) - {r["PlayerId"] for r in game_rows}
    print(f"{year}: {len(proj_rows)} projections, {len(game_rows)} game rows, {len(rosters)} roster rows, "
          f"{len(weeks)} weeks, {len(missing)} rostered players with no game rows")


def probe_weeks(league) -> list[tuple[int, int, int]]:
    """Exact matchup period (week) -> scoring period (day) ranges. A matchup's
    lineup only comes back when the requested day falls inside that week, so
    each week's last day is found by galloping + binary search -- catches
    ESPN's irregular weeks (e.g. 2019 week 18 = days 119-132, the All-Star
    break merged in), which the date-rule Ref/week_calendar.csv gets wrong."""

    def in_week(week: int, sp: int) -> bool:
        if sp > league.finalScoringPeriod:
            return False
        data = league.espn_request.league_get(
            params={"view": ["mMatchupScore", "mScoreboard"], "scoringPeriodId": sp},
            headers={"x-fantasy-filter": json.dumps({"schedule": {"filterMatchupPeriodIds": {"value": [week]}}})},
        )
        return any((m.get(side) or {}).get("rosterForCurrentScoringPeriod", {}).get("entries")
                   for m in data.get("schedule", []) for side in ("home", "away"))

    weeks, week, start = [], 1, 1
    while start <= league.finalScoringPeriod and in_week(week, start):
        end, step = start, 7
        while in_week(week, end + step):
            end += step
        lo, hi = end, end + step  # last True in [lo, hi)
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if in_week(week, mid):
                lo = mid
            else:
                hi = mid
        weeks.append((week, start, lo))
        week, start = week + 1, lo + 1
    return weeks


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--out", type=Path, default=Path("/tmp/backtest"))
    parser.add_argument("--reuse-rosters", action="store_true")
    args = parser.parse_args()
    export(args.year, args.out, args.reuse_rosters)
