"""Exports every fantasy-relevant NBA player's rank (+ real NBA team, +
which fantasy team owns them, if any) per season into Ref/roster_ranks.csv,
so dashboard_site can serve the Team page's Roster sub-view without
importing Models/espn_fr/yfpy_fr directly.

Covers the FULL player pool, not just rostered players -- a player who
was never on any fantasy roster that season (a free agent, or someone
dropped/waived before the season ended) still gets a row, with an empty
FantasyTeam. This matters for the Roster sub-view's swap simulator,
which needs a real "any player, not just someone else's roster" pool to
search -- confirmed live (2022) that the roster-only version of this
script was missing real, fantasy-relevant players like Ja Morant (a free
agent all of 2022) entirely.

ESPN seasons (is_espn=True, 2019-2023) are fully supported: one
kona_player_info query per season (view used by espn_fr's own
League.free_agents(), reused directly here rather than added as a new
vendored-library method, with its filterStatus widened to
FREEAGENT+WAIVERS+ONTEAM instead of just the first two) returns every
player's rank/proTeam/onTeamId in one call -- verified live against a
real closed season (2022): 938 players returned (vs. ~137 from the old
roster-only approach), Ja Morant correctly present (rank 71, MEM,
onTeamId=0 -> free agent), LeBron James correctly owned (onTeamId=10 ->
mapped through the existing constants.espnTeamIDs). onTeamId=0 (or any
id with no entry in espnTeamIDs, e.g. a team that left the league) maps
to an empty FantasyTeam.

Yahoo seasons (is_espn=False, 2024+): now VERIFIED end-to-end live (see
_planning/web-app-build-plan.md's 2026-09-29 session log) -- ran
_yahoo_roster_ranks_for_year(2026) for real: 719 players, 135 correctly
owned (real names/teams, e.g. Nikola Jokić -> Rohil, SGA -> Fano). This
was blocked for a long stretch by a Yahoo app-verification issue on this
app's developer account (not a code bug), since resolved. The rank+NBA-
team scan (_yahoo_player_ranks) is the same already-proven live call in
Models/Draft.py::makeRankDict (sort=AR, NOT the misleading static
preseason "OR" sort yfpy_fr.query.YahooFantasySportsQuery.get_player_rank()
uses), extended to also read editorial_team_abbr out of the same response
(no extra call needed) -- this scan has no status filter, so it already
covers the full player pool the same way ESPN's does. A year that fails
is logged and skipped by main()'s per-year loop below, not silently
dropped and not allowed to crash a multi-year run.

Historical (closed) seasons are frozen snapshots -- only need to run once
per season, not daily. The CURRENT season is what the daily pipeline
re-runs. Merges new rows into any existing CSV rather than overwriting it
wholesale, so refreshing one year's rows never clobbers another year's
already-exported data.

Usage:
  python -m scripts.export_roster_ranks                    # current year only
  python -m scripts.export_roster_ranks --backfill          # every ESPN year (2019-2023), one-time setup
  python -m scripts.export_roster_ranks --years 2021 2022   # specific years
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from constants import currentYear, espn_leagueID, espn_s2, espn_swid, espnTeamIDs, seasonInfo, yTeamIDs  # noqa: E402
from shared.atomic_write import atomic_write  # noqa: E402
from shared.runtime_config import REF_DIR  # noqa: E402

OUTPUT_PATH = REF_DIR / "roster_ranks.csv"
COLUMNS = ["Year", "FantasyTeam", "Player", "NBATeam", "Rank"]

# Comfortably above the real full-pool size (938 players, confirmed live
# for 2022) without needing pagination -- ESPN's kona_player_info view
# accepts this as a single "limit" value, no offset/paging required.
ESPN_PLAYER_POOL_LIMIT = 2000


def _espn_roster_ranks_for_year(year: int) -> list[dict]:
    import json

    from espn_fr.basketball.league import League
    from espn_fr.basketball.player import Player

    league = League(espn_leagueID, year, espn_s2=espn_s2, swid=espn_swid)
    team_map = espnTeamIDs.get(year, {})

    params = {"view": "kona_player_info", "scoringPeriodId": league.finalScoringPeriod}
    filters = {
        "players": {
            "filterStatus": {"value": ["FREEAGENT", "WAIVERS", "ONTEAM"]},
            "limit": ESPN_PLAYER_POOL_LIMIT,
            "sortPercOwned": {"sortPriority": 1, "sortAsc": False},
        }
    }
    headers = {"x-fantasy-filter": json.dumps(filters)}
    data = league.espn_request.league_get(params=params, headers=headers)

    rows: list[dict] = []
    for entry in data["players"]:
        player = Player(entry, year)
        fantasy_team = team_map.get(entry.get("onTeamId"), "")
        rows.append(
            {
                "Year": year,
                "FantasyTeam": fantasy_team,
                "Player": player.name,
                "NBATeam": player.proTeam,
                "Rank": player.rank,
            }
        )
    return rows


def _yahoo_player_ranks(league_key: str) -> dict[str, dict]:
    """Every fantasy-relevant player that season -- real Actual Rank
    (sort=AR, NOT the misleading static preseason "OR" sort
    yfpy_fr.query.YahooFantasySportsQuery.get_player_rank() uses) plus NBA
    team, both read out of the same response. This exact call is copied
    from the already-proven live Models/Draft.py::makeRankDict Yahoo
    branch (rank half); the NBA-team read is new but pulls from a field
    already present in that same response, no extra request. No status
    filter is applied, so this covers free agents alongside rostered
    players already -- ownership is looked up separately in
    _yahoo_roster_ranks_for_year below."""
    from yfpy_fr.YahooQuery import construct_endpoint, make_yahoo_api_request

    players: dict[str, dict] = {}
    limit = 1000
    for start_point in range(0, limit, 25):
        endpoint = construct_endpoint(league_key, resource="players", params={"sort": "AR", "start": start_point})
        data = make_yahoo_api_request(endpoint)
        page = list(data["fantasy_content"]["league"][1]["players"].values())
        # The trailing "count" entry in this dict isn't a player -- only
        # keep entries that actually have a "player" key.
        entries = [p for p in page if isinstance(p, dict) and "player" in p]
        if not entries:
            break
        for i, entry in enumerate(entries):
            name = None
            nba_team = None
            for field in entry["player"][0]:
                if isinstance(field, dict):
                    if "name" in field:
                        name = field["name"]["full"]
                    if "editorial_team_abbr" in field:
                        nba_team = field["editorial_team_abbr"]
            if name is None:
                continue
            players[name] = {"NBATeam": nba_team, "Rank": start_point + i + 1}
        if len(entries) < 25:
            break
    return players


def _yahoo_roster_ranks_for_year(year: int) -> list[dict]:
    """VERIFIED end-to-end live (2026-09-29, against the real 2026 season
    once the Yahoo app-verification block cleared): 719 players, 135
    correctly owned (real names/teams, e.g. Nikola Jokić -> Rohil, SGA ->
    Fano). Two pieces:

    - Rank + NBA team (_yahoo_player_ranks above): the rank half is the
      exact call already proven live in Models/Draft.py::makeRankDict;
      the NBA-team read is new but pulls from a field already present in
      that same proven response.
    - Ownership (which player is on which fantasy team, if any): built on
      the SAME already-proven auth mechanism (yfpy_fr.YahooQuery's raw
      construct_endpoint/make_yahoo_api_request) rather than the separate
      yfpy_fr.query.YahooFantasySportsQuery class, which needs a
      private.json file (see constants.py's Yahoo credentials section) --
      via Yahoo's documented `league/{league_key}/teams;out=roster`
      endpoint (returns every team + its current roster in one call). A
      player found in the rank scan but NOT in this ownership map is
      written with an empty FantasyTeam (free agent) -- confirmed live,
      e.g. Tyrese Maxey correctly unowned in the 2026 test run.

    Deliberately does NOT catch KeyError/IndexError here -- if Yahoo ever
    changes this response shape, this must fail loudly, not silently
    write wrong rosters.
    """
    from yfpy_fr.YahooQuery import construct_endpoint, make_yahoo_api_request, league_keys

    league_key = league_keys[year]
    team_map = yTeamIDs.get(year, {})
    players = _yahoo_player_ranks(league_key)

    roster_endpoint = construct_endpoint(league_key, resource="teams", params={"out": "roster"})
    roster_data = make_yahoo_api_request(roster_endpoint)
    teams_blob = roster_data["fantasy_content"]["league"][1]["teams"]

    owner_by_name: dict[str, str] = {}
    for key, team_entry in teams_blob.items():
        if key == "count" or not isinstance(team_entry, dict):
            continue

        team_id = None
        for field in team_entry["team"][0]:
            if isinstance(field, dict) and "team_id" in field:
                team_id = int(field["team_id"])
        fantasy_team = team_map.get(team_id)
        if fantasy_team is None:
            continue

        roster_players = team_entry["team"][1]["roster"]["0"]["players"]
        for pkey, player_entry in roster_players.items():
            if pkey == "count" or not isinstance(player_entry, dict):
                continue
            for field in player_entry["player"][0]:
                if isinstance(field, dict) and "name" in field:
                    owner_by_name[field["name"]["full"]] = fantasy_team

    return [
        {
            "Year": year,
            "FantasyTeam": owner_by_name.get(name, ""),
            "Player": name,
            "NBATeam": info["NBATeam"],
            "Rank": info["Rank"],
        }
        for name, info in players.items()
    ]


def rows_for_year(year: int) -> list[dict]:
    is_espn = seasonInfo[year][1]
    if is_espn:
        return _espn_roster_ranks_for_year(year)
    return _yahoo_roster_ranks_for_year(year)


HISTORY_COLUMNS = ["Year", "Week", "SnapshotDate", "Player", "NBATeam", "FantasyTeam", "Rank"]


def append_roster_rank_history(year: int, week: int) -> int:
    """Snapshots the CURRENT season's live player ranks, dated, into
    Ref/roster_rank_history.csv -- append-only (never overwrites a prior
    week's rows, matching discord/daily_games.py's convention), kept
    entirely separate from roster_ranks.csv above (which stays a single
    current-season snapshot for the Roster page's swap simulator -- an
    unrelated purpose). Feature request (2026-09-29): "at least once a
    week... note all player rankings and the date... eventually... track
    player rankings over the course of the season." A no-op (returns 0)
    if this exact (year, week) was already snapshotted, so a retried run
    can't write duplicate rows. Reuses rows_for_year()'s already-proven
    fetch functions as-is -- no new Yahoo/ESPN call logic.
    """
    from datetime import date

    from shared.runtime_config import roster_rank_history_csv_path

    path = roster_rank_history_csv_path()
    if path.exists():
        existing = pd.read_csv(path)
        if ((existing["Year"] == year) & (existing["Week"] == week)).any():
            return 0
    else:
        existing = pd.DataFrame(columns=HISTORY_COLUMNS)

    year_rows = rows_for_year(year)
    snapshot_date = date.today().isoformat()
    new_rows = [
        {
            "Year": year,
            "Week": week,
            "SnapshotDate": snapshot_date,
            "Player": r["Player"],
            "NBATeam": r["NBATeam"],
            "FantasyTeam": r["FantasyTeam"],
            "Rank": r["Rank"],
        }
        for r in year_rows
    ]

    path.parent.mkdir(parents=True, exist_ok=True)
    combined = pd.concat([existing, pd.DataFrame(new_rows, columns=HISTORY_COLUMNS)], ignore_index=True)
    atomic_write(path, lambda f: combined.to_csv(f, index=False))
    return len(new_rows)


TEAM_ROSTER_HISTORY_COLUMNS = ["Year", "Week", "SnapshotDate", "FantasyTeam", "RosterSize", "Players"]


def append_team_roster_history(year: int, week: int) -> int:
    """Snapshots each fantasy team's full roster, dated, into
    Ref/team_roster_history.csv -- one row per (year, week, team), append-
    only, same convention as append_roster_rank_history() above. Complements
    it rather than duplicates it: that one is player-level (one row per
    player per week) for rank-over-time correlation; this one is team-
    level (one row per team per week, with its players joined into a
    single cell) for "what did this team's roster look like in week N"
    queries, which the player-level file can only answer via a filter +
    groupby. Feature request, 2026-10-06 -- same cadence/trigger as
    append_roster_rank_history() (called alongside it every daily cycle;
    no-ops once this exact (year, week) is already recorded, so it still
    only ever actually writes once per week), and reuses the same
    rows_for_year() fetch -- no new Yahoo/ESPN call logic.
    """
    from datetime import date

    from shared.runtime_config import team_roster_history_csv_path

    path = team_roster_history_csv_path()
    if path.exists():
        existing = pd.read_csv(path)
        if ((existing["Year"] == year) & (existing["Week"] == week)).any():
            return 0
    else:
        existing = pd.DataFrame(columns=TEAM_ROSTER_HISTORY_COLUMNS)

    year_rows = rows_for_year(year)
    by_team: dict[str, list[str]] = {}
    for r in year_rows:
        # rows_for_year() returns every league player, rostered or not --
        # free agents carry an empty FantasyTeam (confirmed live: 584 of
        # 719 2026 rows). A *roster* tracker should only ever include
        # players actually on a team, unlike the player-level rank
        # history above (which deliberately tracks everyone).
        if not r["FantasyTeam"]:
            continue
        by_team.setdefault(r["FantasyTeam"], []).append(r["Player"])

    snapshot_date = date.today().isoformat()
    new_rows = [
        {
            "Year": year,
            "Week": week,
            "SnapshotDate": snapshot_date,
            "FantasyTeam": team,
            "RosterSize": len(players),
            "Players": "; ".join(sorted(players)),
        }
        for team, players in sorted(by_team.items())
    ]

    path.parent.mkdir(parents=True, exist_ok=True)
    combined = pd.concat([existing, pd.DataFrame(new_rows, columns=TEAM_ROSTER_HISTORY_COLUMNS)], ignore_index=True)
    atomic_write(path, lambda f: combined.to_csv(f, index=False))
    return len(new_rows)


def main(years: list[int]) -> None:
    new_rows: list[dict] = []
    failed_years: list[int] = []
    for year in years:
        try:
            year_rows = rows_for_year(year)
        except Exception as exc:
            # One year's failure (most likely Yahoo's pending API access
            # block right now) must not lose the other years in this same
            # run -- log clearly and keep going, don't touch that year's
            # existing rows in the CSV (see the merge logic below).
            print(f"{year}: FAILED ({exc}) -- leaving any existing rows for this year untouched")
            failed_years.append(year)
            continue
        print(f"{year}: {len(year_rows)} player rows")
        new_rows.extend(year_rows)

    succeeded_years = [y for y in years if y not in failed_years]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Merge into any existing export -- refreshing one year's rows (e.g. the
    # daily current-season update) must not clobber other years' data, and
    # a year that FAILED this run must not wipe whatever it had from a
    # previous successful run either (only succeeded_years are replaced).
    if OUTPUT_PATH.exists():
        existing = pd.read_csv(OUTPUT_PATH)
        existing = existing[~existing["Year"].isin(succeeded_years)]
    else:
        existing = pd.DataFrame(columns=COLUMNS)

    combined = pd.concat([existing, pd.DataFrame(new_rows, columns=COLUMNS)], ignore_index=True)
    atomic_write(OUTPUT_PATH, lambda f: combined.to_csv(f, index=False))
    print(f"Wrote {len(combined)} total player rows to {OUTPUT_PATH} ({len(new_rows)} refreshed this run)")
    if failed_years:
        print(f"Years that failed this run (left untouched in the CSV): {failed_years}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Every historical (non-current) year, both platforms -- one-time setup. "
        "Yahoo years will fail/skip individually until Yahoo API access is approved.",
    )
    parser.add_argument("--years", type=int, nargs="+", help="Specific years to (re)export")
    args = parser.parse_args()

    if args.backfill:
        target_years = [y for y in seasonInfo if y != currentYear]
    elif args.years:
        target_years = args.years
    else:
        # Daily-pipeline default: just the current year.
        target_years = [currentYear]

    main(target_years)
