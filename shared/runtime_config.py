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


def top6_role_state_path() -> Path:
    """Last-run date for FeatureBot's weekly Top 6 role update (see
    discord/feature_bot.py) -- a container restart shouldn't cause a
    duplicate same-day run, and a missed hourly tick should still catch up
    later the same day."""
    return DATA_ROOT / "top6_role_last_run.txt"
