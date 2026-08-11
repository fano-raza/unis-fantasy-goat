"""Exports real NBA player stats (season totals/averages + 7/14/30/90-day
rolling windows) for the Players page's Trade Hub, via `espn_fr` (already
vendored in this repo) rather than stats.nba.com.

nba_api's LeagueDashPlayerStats was the first approach (see git history) but
got dropped: stats.nba.com is behind an Akamai WAF that returns a hard 403 to
the droplet's datacenter IP (confirmed live -- a raw `requests.get` with
browser-like headers got "Access Denied" from failover-waf.nba.com), while it
works fine from a residential IP. ESPN's endpoint was investigated as a
replacement and verified live, not assumed: reachable from the droplet, gives
real per-game granularity (not just pre-aggregated windows) via the
`kona_playercard` endpoint's `filterStatsForTopScoringPeriodIds` filter --
a player's *entire season* of individual game-level stat splits in one call,
batchable across the whole ~1,100-player universe in a single request (~3s).
Since every game is its own row, all 5 windows below are derived from one
pull per player instead of nba_api's 5 separate window-scoped calls.

`league.player_map` (built from ESPN's sport-wide `/players` endpoint, not
scoped to any one fantasy roster) already gives the full active-player
name<->id universe, so no separate player-identity source is needed.

Despite not needing `Models`, this is no longer a "lightweight" export: it
needs `espn_leagueID`/`espn_s2`/`espn_swid` from `constants.py`, which builds
a live `gspread` service-account client at import time. That's a non-issue in
practice since this already runs inside the `gdoc-updater` container, which
has the full heavy dependency chain (valid Google credentials included)
regardless -- just noting it's no longer avoiding that chain the way the
nba_api version's docstring used to claim.

Uses the same `espn_leagueID` this league used before migrating to Yahoo in
2024 -- verified live that ESPN's player-card data isn't gated by whether
this specific fantasy league is still active there; both the 2025 and 2026
seasons resolved fine through the old league ID.

Run this whenever the other precomputed exports run (same cadence).
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from constants import currentYear, espn_leagueID, espn_s2, espn_swid  # noqa: E402
from espn_fr.basketball.league import League  # noqa: E402
from shared.runtime_config import REF_DIR  # noqa: E402

OUTPUT_PATH = REF_DIR / "player_stats.csv"

# ESPN's raw stat labels (see espn_fr/basketball/constant.py::STATS_MAP) ->
# this app's existing category naming convention (matches
# web/src/lib/api.ts's MAIN_CATS exactly, so the frontend needs no
# translation layer). ESPN already uses "TO"/"3PTM", unlike nba_api's
# "TOV"/"FG3M", so this mapping is mostly identity.
COUNTING_CATS = {"3PTM": "3PTM", "REB": "REB", "AST": "AST", "STL": "STL", "BLK": "BLK", "TO": "TO", "PTS": "PTS"}
# Raw makes/attempts per percentage category, carried through so a *group*
# of players (Trade Hub's up-to-5-a-side) gets a real weighted FG%/FT%
# (sum(makes)/sum(attempts)) instead of a naive average of individual
# players' ratios -- same reasoning as the nba_api version had.
PCT_COMPONENTS = {"FG%": ("FGM", "FGA"), "FT%": ("FTM", "FTA")}

# ESPN batches the whole ~1,100-player universe in one call fine (verified:
# 3.1s for all of them), but chunking keeps one bad/oversized request from
# losing the whole export -- a failed chunk is skipped, not fatal.
CHUNK_SIZE = 400


def _player_game_rows(stats: dict) -> list[dict]:
    """Filters a Player.stats dict down to real single-game entries (numeric
    scoring-period keys with GP=1 in that entry's totals) -- excludes the
    '{year}_total'/'{year}_projected' season-summary entries and any
    scoring period the player didn't actually play in."""
    rows = []
    for key, entry in stats.items():
        if not key.isdigit():
            continue
        totals = entry.get("total") or {}
        if totals.get("GP", 0) != 1 or entry.get("date") is None:
            continue
        rows.append({"date": entry["date"], "totals": totals})
    return rows


def _aggregate_window(game_rows: list[dict]) -> dict:
    """One window's worth of derived stats from a list of that player's real
    game rows -- same makes/attempts-weighted percentage math as the
    nba_api version, just computed from real per-game data instead of an
    API-side date-range aggregate."""
    gp = len(game_rows)
    out: dict[str, float | None] = {"GP": gp}
    for raw_cat, cat in COUNTING_CATS.items():
        total = sum(r["totals"].get(raw_cat, 0) or 0 for r in game_rows)
        out[f"{cat}_total"] = total
        out[f"{cat}_avg"] = round(total / gp, 3) if gp else None
    for cat, (made_key, att_key) in PCT_COMPONENTS.items():
        made = sum(r["totals"].get(made_key, 0) or 0 for r in game_rows)
        att = sum(r["totals"].get(att_key, 0) or 0 for r in game_rows)
        out[f"{cat}"] = round(made / att, 3) if att else None
        out[f"{cat}_made"] = made
        out[f"{cat}_att"] = att
    return out


def main() -> None:
    year = currentYear
    today = datetime.date.today()
    windows = {
        "d7": today - datetime.timedelta(days=7),
        "d14": today - datetime.timedelta(days=14),
        "d30": today - datetime.timedelta(days=30),
        "d90": today - datetime.timedelta(days=90),
    }

    league = League(espn_leagueID, year, espn_s2, espn_swid)
    name_to_id = {k: v for k, v in league.player_map.items() if isinstance(k, str)}
    all_ids = list(name_to_id.values())
    id_to_name = {v: k for k, v in name_to_id.items()}

    rows: list[dict] = []
    for i in range(0, len(all_ids), CHUNK_SIZE):
        chunk = all_ids[i : i + CHUNK_SIZE]
        try:
            result = league.player_info(playerId=chunk)
        except Exception as exc:
            print(f"Skipping player chunk {i}-{i + len(chunk)}: {exc}")
            continue
        players = result if isinstance(result, list) else ([result] if result else [])

        for player in players:
            game_rows = _player_game_rows(player.stats)
            row: dict = {
                "PlayerId": player.playerId,
                "Player": player.name or id_to_name.get(player.playerId, ""),
                "Team": player.proTeam,
            }
            season_agg = _aggregate_window(game_rows)
            for key, value in season_agg.items():
                row[f"season_{key}"] = value
            for window, cutoff in windows.items():
                window_rows = [r for r in game_rows if r["date"].date() >= cutoff]
                window_agg = _aggregate_window(window_rows)
                for key, value in window_agg.items():
                    row[f"{window}_{key}"] = value
            rows.append(row)

    df = pd.DataFrame(rows)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)

    print(f"Wrote {len(df)} player stat rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
