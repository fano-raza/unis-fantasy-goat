"""Every fantasy team's lineup slot for every day of the current season, so
the Roster page's full-week grid can tell which games actually counted:
a player sitting in an IR or bench (BE) slot that day doesn't score.

Source: ESPN's day-by-day roster history (view=mRoster with a
scoringPeriodId -- the same call scripts/export_backtest_data.py uses for
past seasons; ESPN NBA scoring periods are single days). Each scoring
period's calendar date comes from ESPN's own pro-team schedule
(proGamesByScoringPeriod), so dates are exact rather than "today minus N",
which would be off by one if this runs before ESPN rolls over to the new
day.

Writes Ref/lineup_history.csv:
  Year, ScoringPeriod, Date (ET, YYYY-MM-DD), FantasyTeam, PlayerId, Player,
  LineupSlot (ESPN slot name: PG ... UT, "BE" = bench, "IR" = injured reserve)

Incremental and cheap: past days are fetched once (the first run backfills
the season so far, one request per day); every run re-fetches yesterday and
today, since a day's lineup can still change until its games lock. ESPN
leagues only (2027 is ESPN); a Yahoo season is skipped.

Runs daily in the stat-updater loop, after export_roster_ranks.
  python3 -m scripts.export_lineup_history [--year 2027]
"""
from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from constants import currentYear, espnLeagueIDs, espn_s2, espn_swid, espnTeamIDs, seasonInfo  # noqa: E402
from shared.atomic_write import atomic_write  # noqa: E402
from shared.runtime_config import REF_DIR  # noqa: E402

LINEUP_HISTORY_PATH = REF_DIR / "lineup_history.csv"
COLUMNS = ["Year", "ScoringPeriod", "Date", "FantasyTeam", "PlayerId", "Player", "LineupSlot"]
EASTERN = ZoneInfo("America/New_York")
# Days re-fetched every run even if already stored: yesterday and today.
REFRESH_TRAILING_DAYS = 2


def scoring_period_dates(league) -> dict[int, str]:
    """Scoring period -> ET date, from the NBA games ESPN files under each
    period. A period with no NBA games (rare off days) takes its date from
    the nearest period that has one, since periods are consecutive days."""
    known: dict[int, datetime.date] = {}
    for games in league._get_all_pro_schedule().values():
        for sp, game_list in games.items():
            for g in game_list:
                known.setdefault(int(sp), datetime.datetime.fromtimestamp(g["date"] / 1000, EASTERN).date())
    if not known:
        return {}
    anchors = sorted(known)
    out = {}
    for sp in range(league.firstScoringPeriod, league.finalScoringPeriod + 1):
        anchor = sp if sp in known else min(anchors, key=lambda a: abs(a - sp))
        out[sp] = (known[anchor] + datetime.timedelta(days=sp - anchor)).isoformat()
    return out


def fetch_day(league, year: int, sp: int, date: str) -> list[dict]:
    from espn_fr.basketball.constant import POSITION_MAP

    team_names = espnTeamIDs.get(year, {})
    data = league.espn_request.league_get(params={"view": "mRoster", "scoringPeriodId": sp})
    rows = []
    for team in data["teams"]:
        name = team_names.get(team["id"])
        if not name:
            continue
        for entry in team["roster"]["entries"]:
            player = entry["playerPoolEntry"]["player"]
            slot_id = entry.get("lineupSlotId")
            rows.append({
                "Year": year,
                "ScoringPeriod": sp,
                "Date": date,
                "FantasyTeam": name,
                "PlayerId": int(player["id"]),
                "Player": player.get("fullName", ""),
                "LineupSlot": POSITION_MAP.get(slot_id, str(slot_id)),
            })
    return rows


def main(year: int | None = None) -> int:
    year = year or currentYear
    if not seasonInfo[year][1]:
        print(f"lineup_history: {year} isn't an ESPN season, skipping")
        return 0

    from espn_fr.basketball.league import League

    league = League(espnLeagueIDs[year], year, espn_s2=espn_s2, swid=espn_swid)
    dates = scoring_period_dates(league)
    current = min(league.scoringPeriodId, league.finalScoringPeriod)

    existing = pd.DataFrame(columns=COLUMNS)
    if LINEUP_HISTORY_PATH.exists():
        existing = pd.read_csv(LINEUP_HISTORY_PATH)
    have = set(existing.loc[existing["Year"] == year, "ScoringPeriod"].astype(int))
    to_fetch = [
        sp for sp in range(league.firstScoringPeriod, current + 1)
        if sp not in have or sp > current - REFRESH_TRAILING_DAYS
    ]
    if not to_fetch:
        return 0

    fresh = [row for sp in to_fetch if sp in dates for row in fetch_day(league, year, sp, dates[sp])]
    keep = existing[~((existing["Year"] == year) & existing["ScoringPeriod"].isin(to_fetch))]
    out = pd.concat([keep, pd.DataFrame(fresh, columns=COLUMNS)], ignore_index=True)
    out = out.sort_values(["Year", "ScoringPeriod", "FantasyTeam", "Player"]).reset_index(drop=True)
    atomic_write(LINEUP_HISTORY_PATH, lambda f: out.to_csv(f, index=False))
    print(f"lineup_history: {len(to_fetch)} day(s) fetched ({len(fresh)} rows), {len(out)} rows total")
    return len(to_fetch)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--year", type=int, default=None)
    main(parser.parse_args().year)
