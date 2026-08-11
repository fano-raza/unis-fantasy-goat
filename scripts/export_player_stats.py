"""Exports real NBA player stats (season totals/averages + 7/14/30/90-day
rolling windows) for the Players page's Trade Hub, via nba_api's
LeagueDashPlayerStats endpoint (stats.nba.com, unofficial but free/no key).

Unlike scripts/export_team_summary.py and export_real_matchup_flags.py, this
does NOT need Models/gspread/yahoo_oauth -- it's a standalone network call +
pandas reshape. It still runs from the gdoc-updater container (nba_api added
to infra/docker/requirements-deploy.txt) purely to share that container's
refresh cadence, not because it needs the heavy dependency chain.

Yahoo's API (yfpy_fr, used elsewhere in this repo) was investigated first and
ruled out: it only supports week/single-day/season stat coverage, no
date-range query, and live testing hit a sustained rate limit. nba_api's
LeagueDashPlayerStats, by contrast, returns every player's aggregated stats
for an arbitrary date range in one call (~1-2s), with correctly-weighted
FG%/FT% (real makes/attempts ratios, not naive per-game averaging) and GP
included -- verified against known real player stat lines before building
this script.

Run this whenever the other precomputed exports run (same cadence). Requires
network access to stats.nba.com -- known to sometimes block/rate-limit
datacenter IPs, unlike the residential IP this was prototyped from. If this
starts failing specifically in the droplet's environment, that's the
suspect, not the code.
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.runtime_config import REF_DIR  # noqa: E402

OUTPUT_PATH = REF_DIR / "player_stats.csv"

# nba_api's raw stat column -> this app's existing category naming
# convention (matches web/src/lib/api.ts's MAIN_CATS exactly, so the
# frontend needs no translation layer).
COUNTING_CATS = {
    "FG3M": "3PTM",
    "REB": "REB",
    "AST": "AST",
    "STL": "STL",
    "BLK": "BLK",
    "TOV": "TO",
    "PTS": "PTS",
}
PCT_CATS = {"FG_PCT": "FG%", "FT_PCT": "FT%"}
# Raw makes/attempts per percentage category, carried through alongside the
# ratio itself -- lets a consumer combining multiple players (Trade Hub's
# up-to-5-a-side groups) compute a real weighted group FG%/FT%
# (sum(makes)/sum(attempts)) instead of a naive average of individual
# players' ratios, which misweights players with very different attempt
# volumes.
PCT_COMPONENTS = {"FG%": ("FGM", "FGA"), "FT%": ("FTM", "FTA")}


def _current_nba_season() -> str:
    """NBA season string nba_api expects (e.g. "2025-26") -- season flips
    over in October, not January 1st."""
    today = datetime.date.today()
    start_year = today.year if today.month >= 10 else today.year - 1
    return f"{start_year}-{str(start_year + 1)[2:]}"


def _fetch_window(season: str, date_from: str | None, date_to: str | None) -> pd.DataFrame:
    from nba_api.stats.endpoints import leaguedashplayerstats

    kwargs = {"season": season, "per_mode_detailed": "Totals", "timeout": 30}
    if date_from and date_to:
        kwargs["date_from_nullable"] = date_from
        kwargs["date_to_nullable"] = date_to
    resp = leaguedashplayerstats.LeagueDashPlayerStats(**kwargs)
    return resp.get_data_frames()[0]


def _windowed_columns(df: pd.DataFrame, window: str) -> pd.DataFrame:
    """Reshapes one window's raw Totals-mode response into this app's
    {window}_{cat}_total / {window}_{cat}_avg columns, deriving per-game
    averages by dividing by GP -- valid for counting stats; FG%/FT% are
    already the correct weighted ratio regardless of Totals vs PerGame mode,
    so they're carried through unchanged (no _total/_avg split needed)."""
    out = pd.DataFrame({"PLAYER_ID": df["PLAYER_ID"], f"{window}_GP": df["GP"]})
    gp_safe = df["GP"].replace(0, pd.NA)
    for raw_col, cat in COUNTING_CATS.items():
        out[f"{window}_{cat}_total"] = df[raw_col]
        out[f"{window}_{cat}_avg"] = (df[raw_col] / gp_safe).round(3)
    for raw_col, cat in PCT_CATS.items():
        out[f"{window}_{cat}"] = df[raw_col]
    for cat, (made_col, att_col) in PCT_COMPONENTS.items():
        out[f"{window}_{cat}_made"] = df[made_col]
        out[f"{window}_{cat}_att"] = df[att_col]
    return out


def main() -> None:
    season = _current_nba_season()
    today = datetime.date.today()

    windows = [
        ("season", None, None),
        ("d7", today - datetime.timedelta(days=7), today),
        ("d14", today - datetime.timedelta(days=14), today),
        ("d30", today - datetime.timedelta(days=30), today),
        ("d90", today - datetime.timedelta(days=90), today),
    ]

    identity_df: pd.DataFrame | None = None
    windowed_frames: list[pd.DataFrame] = []

    for window, date_from, date_to in windows:
        raw = _fetch_window(
            season,
            date_from.strftime("%m/%d/%Y") if date_from else None,
            date_to.strftime("%m/%d/%Y") if date_to else None,
        )
        if identity_df is None:
            identity_df = raw[["PLAYER_ID", "PLAYER_NAME", "TEAM_ABBREVIATION"]].rename(
                columns={"PLAYER_NAME": "Player", "TEAM_ABBREVIATION": "Team"}
            )
        windowed_frames.append(_windowed_columns(raw, window))

    assert identity_df is not None
    merged = identity_df
    for frame in windowed_frames:
        merged = merged.merge(frame, on="PLAYER_ID", how="outer")

    merged = merged.rename(columns={"PLAYER_ID": "PlayerId"})
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(OUTPUT_PATH, index=False)

    print(f"Wrote {len(merged)} player stat rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
