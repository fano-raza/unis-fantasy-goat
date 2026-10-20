"""Exports the real NBA schedule (today onward, through the following NBA
season's rough end -- or, with --backfill, every past fantasy season's
real date range too) into Ref/nba_schedule.csv, for the Team page's
Roster sub-view "games this week" feature and its per-season week
selector.

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

import argparse
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

# Earliest date any fantasy season's week_calendar.csv can reference
# (2019's ESPN-heuristic week 1) -- the --backfill starting point.
EARLIEST_SEASON_DATE = date(2018, 10, 16)

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

# How far ahead to pull.
MONTHS_AHEAD = 9


def _normalize(abbr: str) -> str:
    return TEAM_ABBR_NORMALIZE.get(abbr, abbr)


def _day_list(start: date, months: int) -> list[date]:
    end = start + timedelta(days=30 * months)
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def _fetch_day(day: date) -> list[dict]:
    # ESPN's scoreboard endpoint used to accept a "YYYYMMDD-YYYYMMDD" date
    # range (this script originally pulled ~1-month chunks that way) but no
    # longer does -- confirmed live, every range query now 400s with
    # "Failed to get events endpoint." regardless of span (even 2 days) or
    # period (past or future), while a single "YYYYMMDD" date still works
    # fine. One request per day instead of per month -- slower, but it's
    # the only query shape ESPN's public API currently accepts.
    params = {"dates": day.strftime("%Y%m%d"), "limit": 1000}
    resp = requests.get(SCOREBOARD_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    rows = []
    skipped = 0
    for event in data.get("events", []):
        competitors = event["competitions"][0]["competitors"]
        home = next(c for c in competitors if c["homeAway"] == "home")
        away = next(c for c in competitors if c["homeAway"] == "away")
        # Preseason exhibitions against non-NBA clubs (e.g. EuroLeague teams
        # during October preseason tours) show up in this scoreboard but
        # have no "abbreviation" field -- confirmed live (e.g. "Ulm at
        # Portland Trail Blazers", Oct 2024). Not a real fantasy-relevant
        # NBA-vs-NBA game, so skip rather than crash the whole backfill.
        if "abbreviation" not in home["team"] or "abbreviation" not in away["team"]:
            skipped += 1
            continue
        rows.append(
            {
                "Date": event["date"],
                "HomeTeam": _normalize(home["team"]["abbreviation"]),
                "AwayTeam": _normalize(away["team"]["abbreviation"]),
            }
        )
    if skipped:
        print(f"  (skipped {skipped} non-NBA exhibition game(s))")
    return rows


def main(backfill: bool = False) -> None:
    today = date.today()
    start_date = EARLIEST_SEASON_DATE if backfill else today
    months = ((today + timedelta(days=30 * MONTHS_AHEAD)) - start_date).days // 30 + 1

    rows: list[dict] = []
    seen_keys: set[str] = set()
    days = _day_list(start_date, months)
    for i, day in enumerate(days):
        day_rows = _fetch_day(day)
        for row in day_rows:
            key = f"{row['Date']}|{row['HomeTeam']}|{row['AwayTeam']}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            rows.append(row)
        # One request per day now (see _fetch_day) -- a print per request
        # would be too noisy over an 8-year backfill, so mark progress
        # roughly monthly instead.
        if (i + 1) % 30 == 0 or day == days[-1]:
            print(f"...through {day}: {len(rows)} games so far")

    new_df = pd.DataFrame(rows, columns=COLUMNS)

    # Merge into any existing export rather than replacing it wholesale --
    # a plain daily run (start_date=today) must not wipe out games from a
    # past --backfill run that are now before "today," and a --backfill
    # run must not lose whatever future games a previous daily run already
    # pulled in. Dedupe on the same (Date, HomeTeam, AwayTeam) key.
    if OUTPUT_PATH.exists():
        existing_df = pd.read_csv(OUTPUT_PATH)
        existing_df = existing_df[
            ~existing_df.apply(lambda r: f"{r.Date}|{r.HomeTeam}|{r.AwayTeam}" in seen_keys, axis=1)
        ]
        combined = pd.concat([existing_df, new_df], ignore_index=True)
    else:
        combined = new_df

    combined = combined.sort_values("Date").reset_index(drop=True)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(OUTPUT_PATH, lambda f: combined.to_csv(f, index=False))
    print(f"Wrote {len(combined)} total games to {OUTPUT_PATH} ({len(new_df)} fetched this run)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Pull every past fantasy season's real date range too (one-time setup), "
        "not just today onward.",
    )
    args = parser.parse_args()
    main(backfill=args.backfill)
