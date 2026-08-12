"""Exports the real NBA schedule (today onward, through the following NBA
season's rough end) into Ref/nba_schedule.csv, for the Team page's Roster
sub-view "games this week" feature.

Uses ESPN's PUBLIC scoreboard API (site.api.espn.com) -- distinct from the
espn_fr FANTASY library used elsewhere in this codebase, and unauthenticated
(no espn_s2/swid needed). Verified live from both a local residential
machine and the droplet before this was written: reachable from both with
correct data, unlike NBA.com's own schedule CDN, which is Akamai-blocked
from both.

Real-world schedule, not tied to any fantasy-platform year -- one file,
always "from today forward," refreshed daily via the same pipeline slot as
the other Ref/ exports. Pulling "the full season" literally isn't possible
before the NBA actually publishes it: as of writing (deep 2026 offseason),
ESPN's scoreboard only has ~2 weeks of preseason games listed even when
queried for a 9-month window -- the rest of the season's games simply
don't exist in ESPN's system yet. Re-running this daily is what lets the
stored data grow to the real full season as the NBA publishes more of it,
not a one-time snapshot.

Team abbreviations are normalized to match espn_fr's PRO_TEAM_MAP
convention (already used in Ref/roster_ranks.csv's NBATeam column), since
ESPN's public scoreboard API uses a handful of different abbreviations for
the same teams -- confirmed live, 8 of 30 teams differ (GS/NOP, NO/NOP,
NY/NYK, PHI/PHL, PHX/PHO, SA/SAS, UTAH/UTA, WSH/WAS -- scoreboard-API/
PRO_TEAM_MAP). Without this, joining schedule data to roster data by team
abbreviation would silently drop games for a quarter of the league.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.atomic_write import atomic_write  # noqa: E402
from shared.runtime_config import REF_DIR  # noqa: E402

OUTPUT_PATH = REF_DIR / "nba_schedule.csv"
COLUMNS = ["Date", "HomeTeam", "AwayTeam"]

SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"

# ESPN public-scoreboard abbreviation -> espn_fr's PRO_TEAM_MAP abbreviation,
# for every team where the two disagree (see module docstring). Identity for
# every other team, so this only needs the exceptions.
TEAM_ABBR_NORMALIZE = {
    "GS": "GSW",
    "NO": "NOP",
    "NY": "NYK",
    "PHI": "PHL",
    "PHX": "PHO",
    "SA": "SAS",
    "UTAH": "UTA",
    "WSH": "WAS",
}

# How far ahead to pull, in ~1-month chunks (defensive against the API
# capping a single huge date-range request -- not yet observed to happen,
# but a full ~1230-game season hasn't existed to test against yet either).
MONTHS_AHEAD = 9


def _normalize(abbr: str) -> str:
    return TEAM_ABBR_NORMALIZE.get(abbr, abbr)


def _month_ranges(start: date, months: int) -> list[tuple[date, date]]:
    ranges = []
    cursor = start
    for _ in range(months):
        chunk_end = cursor + timedelta(days=29)
        ranges.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return ranges


def _fetch_range(start: date, end: date) -> list[dict]:
    params = {
        "dates": f"{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}",
        "limit": 1000,
    }
    resp = requests.get(SCOREBOARD_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    rows = []
    for event in data.get("events", []):
        competitors = event["competitions"][0]["competitors"]
        home = next(c for c in competitors if c["homeAway"] == "home")
        away = next(c for c in competitors if c["homeAway"] == "away")
        rows.append(
            {
                "Date": event["date"],
                "HomeTeam": _normalize(home["team"]["abbreviation"]),
                "AwayTeam": _normalize(away["team"]["abbreviation"]),
            }
        )
    return rows


def main() -> None:
    today = date.today()
    rows: list[dict] = []
    seen_dates: set[str] = set()
    for start, end in _month_ranges(today, MONTHS_AHEAD):
        chunk_rows = _fetch_range(start, end)
        # ESPN's date-range chunking can overlap at boundaries -- dedupe by
        # the (Date, HomeTeam, AwayTeam) triple rather than trust the chunks
        # are cleanly disjoint.
        for row in chunk_rows:
            key = f"{row['Date']}|{row['HomeTeam']}|{row['AwayTeam']}"
            if key in seen_dates:
                continue
            seen_dates.add(key)
            rows.append(row)
        print(f"{start} - {end}: {len(chunk_rows)} games")

    df = pd.DataFrame(rows, columns=COLUMNS).sort_values("Date").reset_index(drop=True)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(OUTPUT_PATH, lambda f: df.to_csv(f, index=False))
    print(f"Wrote {len(df)} games to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
