"""Exports a small (Year, Week, Season, Team) -> real_matchup, is_winner
lookup from Models/League.py's fully-computed standings/seeding logic, so
dashboard_site (which stays on the lightweight venv and never imports
Models) can tell real playoff-bracket matchups apart from consolation-
bracket games that the raw CompStats CSVs mark Count=True for equally, and
can know the tiebreak-resolved winner of a real matchup that ended in an
exact category tie.

Regular-season rows don't need either column (Count==True is already a
reliable "real matchup" proxy there, and a RS category tie is reported as a
real draw, not resolved to a winner) -- this only matters for playoff weeks,
where bracket membership is seeding-derived business logic, and a tied game
gets walked through the league's tiebreak order (H2H record -> H2H category
record -> seeding, Models/seasons.py's _resolve_playoff_tie), neither of
which is recoverable from the raw CompStats category counts alone.

Run this whenever Ref/*_CompStats.csv changes (same cadence as the GDoc/stat
refresh pipeline) so dashboard_site's cache doesn't go stale. Requires the
full repo venv (Models/constants dependency chain), unlike dashboard_site
itself.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Models.League import fantasyLeague  # noqa: E402
from shared.atomic_write import atomic_write  # noqa: E402
from shared.runtime_config import REF_DIR  # noqa: E402

OUTPUT_PATH = REF_DIR / "real_matchup_flags.csv"


def _official_winners(lg: fantasyLeague) -> pd.DataFrame:
    """One row per team per real playoff-bracket matchup (BYEs and
    consolation-bracket games excluded -- same games real_matchup already
    flags as real), carrying whether that team was the matchup's official
    (tiebreak-resolved) winner. Walks poSeason.PO_matchups_by_week directly
    rather than statDF, since the tiebreak resolution lives only on the
    matchup objects (matchup_obj.official_winner), not as a statDF column."""
    rows: list[dict] = []
    for season in lg.seasons.values():
        po_season = season.playoffs
        if not getattr(po_season, "PO_time", False):
            continue
        for week in range(po_season.RSweekCount + 1, po_season.PO_currentWeek + 1):
            for m in po_season.PO_matchups_by_week.get(week, []):
                if m.is_BYE:
                    continue
                for team in (m.team1, m.team2):
                    rows.append(
                        {
                            "Year": season.year,
                            "Week": week,
                            "Season": "PO",
                            "Team": team,
                            "is_winner": int(team == m.official_winner),
                        }
                    )
    return pd.DataFrame(rows, columns=["Year", "Week", "Season", "Team", "is_winner"])


def main() -> None:
    lg = fantasyLeague()
    df = lg.get_filtered_df(real=False)
    # real=False returns every hypothetical all-play row too (one team can
    # have several rows for a given week, only one of them real) -- take the
    # max of real_matchup per (Year, Week, Season, Team) rather than
    # drop_duplicates, which would keep an arbitrary row and could easily
    # grab a hypothetical (real_matchup=0) row over the real one.
    po = (
        df[df["Season"] == "PO"]
        .groupby(["Year", "Week", "Season", "Team"], as_index=False)["real_matchup"]
        .max()
    )
    po = po.merge(_official_winners(lg), on=["Year", "Week", "Season", "Team"], how="left")

    sorted_po = po.sort_values(["Year", "Week", "Team"])

    def _write(f) -> None:
        writer = csv.writer(f)
        writer.writerow(["Year", "Week", "Season", "Team", "real_matchup", "is_winner"])
        for _, row in sorted_po.iterrows():
            is_winner = row["is_winner"]
            is_winner_val = "" if pd.isna(is_winner) else int(is_winner)
            writer.writerow(
                [int(row["Year"]), int(row["Week"]), row["Season"], row["Team"], int(row["real_matchup"]), is_winner_val]
            )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(OUTPUT_PATH, _write, newline="")

    print(f"Wrote {len(po)} playoff-week real_matchup rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
