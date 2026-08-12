"""Exports a (Year, Week) -> real calendar date range table into
Ref/week_calendar.csv, so the Team page's Roster/Schedule sub-view can
offer a week selector for every season, not just the current one.

Yahoo seasons (2024+) already have exact real dates in
{DATA_ROOT}/{year}/{year}_matchup_cal.csv (see shared/runtime_config.py
::calendar_csv_path), fetched from Yahoo's own game_weeks API by
ScheduleGenerator.py when that season was current -- this script just
reads them.

ESPN seasons (2019-2023, is_espn=True) have NO real dates stored anywhere
in this codebase: espn_fr only exposes integer scoringPeriodId/
matchupPeriodId, no real date boundaries. Real dates are DERIVED here via
a heuristic, confirmed by the user as an acceptable approximation (not
exact, unlike the Yahoo years):
  - week 1 runs from that season's real, publicly-known opening night
    (a Tuesday, hardcoded in ESPN_SEASON_OPEN below) through the
    following Sunday.
  - each subsequent week is a clean Monday-Sunday block, and how many
    calendar weeks long a given fantasy week is comes from REAL,
    live-fetched league structure (League(...).settings.matchup_periods
    -- e.g. a 2-calendar-week playoff round shows up as a 2-element list
    for that matchupPeriodId), not guessed.
This exact "opening night -> next Sunday, then clean Mon-Sun" pattern is
independently confirmed by the real Yahoo-year files (e.g. 2024's week 1
is Tue Oct 22 - Sun Oct 27), which is why it was chosen as the ESPN-year
heuristic.

Data-integrity note (found while building this, not a guess): DATA_ROOT's
2024_matchup_cal.csv and 2025_matchup_cal.csv were discovered to be
byte-identical (both holding the 2024-25 season's real dates, mislabeled
as if for two different seasons). User confirmed fantasy year 2024 =
the 2023-24 season (started Oct 24, 2023) -- consistent with the
"year = season's ending year" convention used everywhere else in this
app (matches the ESPN years and year 2026's already-correct file).
Fixed at the source: 2025_matchup_cal.csv now holds what was
2024_matchup_cal.csv's real (and correctly-labeled-for-2025) content,
and 2024_matchup_cal.csv was regenerated via this same heuristic (real
Oct 24, 2023 opening night; 21 weeks of 1 calendar week each, matching
the real week-length structure confirmed in the neighboring, exact 2025
season) since Yahoo's API is currently blocked and can't be re-queried
to regenerate it exactly.

Usage:
  python -m scripts.export_week_calendar
"""

from __future__ import annotations

import csv
import datetime
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from constants import calendar_csv_path, espn_leagueID, espn_s2, espn_swid, seasonInfo  # noqa: E402
from shared.atomic_write import atomic_write  # noqa: E402
from shared.runtime_config import REF_DIR  # noqa: E402

OUTPUT_PATH = REF_DIR / "week_calendar.csv"
COLUMNS = ["Year", "Week", "StartDate", "EndDate"]

# Real, publicly-confirmed NBA season opening nights for the ESPN-era
# fantasy years (year = the season's ending year, e.g. 2022 -> the
# 2021-22 season). Also covers fantasy year 2024 (2023-24 season),
# needed to regenerate its calendar since Yahoo's API is blocked -- see
# module docstring.
SEASON_OPEN: dict[int, datetime.date] = {
    2019: datetime.date(2018, 10, 16),
    2020: datetime.date(2019, 10, 22),
    2021: datetime.date(2020, 12, 22),
    2022: datetime.date(2021, 10, 19),
    2023: datetime.date(2022, 10, 18),
    2024: datetime.date(2023, 10, 24),
}
# Fantasy year 2024's real per-week structure can't be fetched live
# (Yahoo blocked), so it borrows the confirmed-real structure of the
# immediately-adjacent 2025 season (21 weeks, 1 calendar week each) --
# see module docstring.
YAHOO_2024_WEEK_LENGTHS = [1] * 21


def _week_bounds_from_lengths(open_date: datetime.date, lengths: list[int]) -> list[tuple[int, datetime.date, datetime.date]]:
    week1_end = open_date + datetime.timedelta(days=6 - open_date.weekday())
    rows = [(1, open_date, week1_end)]
    cur_start = week1_end + datetime.timedelta(days=1)
    for i, length in enumerate(lengths[1:], start=2):
        cur_end = cur_start + datetime.timedelta(days=length * 7 - 1)
        rows.append((i, cur_start, cur_end))
        cur_start = cur_end + datetime.timedelta(days=1)
    return rows


def _espn_week_calendar(year: int) -> list[dict]:
    from espn_fr.basketball.league import League

    league = League(espn_leagueID, year, espn_s2=espn_s2, swid=espn_swid)
    matchup_periods = league.settings.matchup_periods
    lengths = [len(v) for _, v in sorted(matchup_periods.items(), key=lambda kv: int(kv[0]))]
    bounds = _week_bounds_from_lengths(SEASON_OPEN[year], lengths)
    return [{"Year": year, "Week": wk, "StartDate": s.isoformat(), "EndDate": e.isoformat()} for wk, s, e in bounds]


def _yahoo_2024_week_calendar() -> list[dict]:
    bounds = _week_bounds_from_lengths(SEASON_OPEN[2024], YAHOO_2024_WEEK_LENGTHS)
    return [{"Year": 2024, "Week": wk, "StartDate": s.isoformat(), "EndDate": e.isoformat()} for wk, s, e in bounds]


def _yahoo_week_calendar_from_file(year: int) -> list[dict]:
    path = calendar_csv_path(year)
    rows: list[dict] = []
    with open(path, "r") as f:
        reader = csv.reader(f)
        next(reader)
        for week, sy, sm, sd, ey, em, ed in reader:
            start = datetime.date(int(sy), int(sm), int(sd))
            end = datetime.date(int(ey), int(em), int(ed))
            rows.append({"Year": year, "Week": int(week), "StartDate": start.isoformat(), "EndDate": end.isoformat()})
    return rows


def rows_for_year(year: int) -> list[dict]:
    is_espn = seasonInfo[year][1]
    if is_espn:
        return _espn_week_calendar(year)
    if year == 2024:
        return _yahoo_2024_week_calendar()
    return _yahoo_week_calendar_from_file(year)


def main() -> None:
    all_rows: list[dict] = []
    for year in seasonInfo:
        try:
            year_rows = rows_for_year(year)
        except Exception as exc:
            print(f"{year}: FAILED ({exc}) -- skipped")
            continue
        print(f"{year}: {len(year_rows)} weeks")
        all_rows.extend(year_rows)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(all_rows, columns=COLUMNS)
    atomic_write(OUTPUT_PATH, lambda f: df.to_csv(f, index=False))
    print(f"Wrote {len(df)} total week rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
