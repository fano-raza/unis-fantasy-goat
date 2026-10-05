import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Defaults preserve current local behavior, but can be overridden for server deploy.
DEFAULT_DATA_ROOT = "/Users/fano/Documents/Fantasy/Fantasy GOAT"
DEFAULT_GSPREAD_SERVICE_ACCOUNT = (
    "/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/site-packages/"
    "gspread/fantasy-goat-306ebfffe1c2.json"
)

DATA_ROOT = Path(os.getenv("FANTASY_DATA_ROOT", DEFAULT_DATA_ROOT))
REF_DIR = Path(os.getenv("FANTASY_REF_DIR", str(DATA_ROOT / "ref")))
GOOGLE_SERVICE_ACCOUNT_JSON_PATH = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_JSON",
    DEFAULT_GSPREAD_SERVICE_ACCOUNT,
)


def calendar_csv_path(year: int) -> str:
    return str(DATA_ROOT / str(year) / f"{year}_matchup_cal.csv")


def comp_stats_csv_path(year: int) -> str:
    return str(REF_DIR / f"{year}_CompStats.csv")


def draft_results_csv_path(year: int) -> str:
    return str(DATA_ROOT / str(year) / f"{year} Draft Results.csv")


def feature_requests_path() -> Path:
    return DATA_ROOT / "feature_requests.md"


def msg_claude_path() -> Path:
    """Same Open/Done/Ignored checklist shape as feature_requests_path(),
    populated by the /discord-mode-claude Discord command (discord/feature_bot.py)
    -- a separate inbox for general chat messages to Claude, distinct
    from feature requests."""
    return DATA_ROOT / "msg_claude.md"


def weekly_role_sync_state_path() -> Path:
    """Last-run date for FeatureBot's weekly Discord role sync (Top 6 /
    Champs / Current Champ -- see discord/feature_bot.py) -- a container
    restart shouldn't cause a duplicate same-day run, and a missed hourly
    tick should still catch up later the same day."""
    return DATA_ROOT / "weekly_role_sync_last_run.txt"


def daily_games_history_path() -> Path:
    """One row per #daily-games score post (MapTap/Worldle/Flagle/WhenTaken/
    Travle) -- see discord/daily_games.py."""
    return DATA_ROOT / "daily_games_history.csv"


def daily_games_cursor_path() -> Path:
    """Last processed Discord message id for the #daily-games scan, so the
    daily refresh only walks new messages instead of the whole channel
    history each time."""
    return DATA_ROOT / "daily_games_cursor.txt"


def daily_games_last_run_path() -> Path:
    """Last-run date for StatBot's daily #daily-games sync -- same
    restart/missed-tick reasoning as weekly_role_sync_state_path()."""
    return DATA_ROOT / "daily_games_last_run.txt"


def weekly_rankings_last_run_path() -> Path:
    """Last-run (year, week) for StatBot's Monday weekly-rankings post --
    same restart/missed-tick reasoning as weekly_role_sync_state_path(),
    but keyed on the fantasy week rather than a calendar date since this
    only needs to fire once per (year, week), not once per Monday."""
    return DATA_ROOT / "weekly_rankings_last_run.txt"


def weekly_recaps_csv_path() -> Path:
    """One row per (year, week) StatBot has posted a rankings recap for --
    see discord/weekly_rankings.py. Surfaced on the web app's Weekly Stats
    page via LeagueStore.weekly_recap()."""
    return REF_DIR / "weekly_recaps.csv"


def roster_rank_history_csv_path() -> Path:
    """One row per (year, week, player) snapshot of that player's live
    fantasy rank, dated -- see scripts/export_roster_ranks.py's
    append_roster_rank_history(). Distinct from roster_ranks.csv, which
    stays a single current-season snapshot for the Roster page's swap
    simulator. No separate "last run" cursor needed -- the function
    itself no-ops once a (year, week) pair is already in the file."""
    return REF_DIR / "roster_rank_history.csv"


def daily_games_last_synced_at_path() -> Path:
    """Last-synced-at UTC timestamp (ISO 8601), written on every successful
    scan_and_record() call regardless of caller. Distinct from
    daily_games_last_run_path(), which only tracks a once-per-day date for
    gating the 4am scheduled sync -- this one has real precision, so it can
    back a "stale after N minutes" freshness check and a "Last updated"
    display line on leaderboard commands."""
    return DATA_ROOT / "daily_games_last_synced_at.txt"
