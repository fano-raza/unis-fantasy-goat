"""Exports a small (Year, Week, Season, Team) -> real_matchup lookup from
Models/League.py's fully-computed standings/seeding logic, so dashboard_site
(which stays on the lightweight venv and never imports Models) can tell real
playoff-bracket matchups apart from consolation-bracket games that the raw
CompStats CSVs mark Count=True for equally.

Regular-season rows don't need this (Count==True is already a reliable proxy
there); this only matters for playoff weeks, where bracket membership is
seeding-derived business logic, not something stored in the CSV.

Run this whenever Ref/*_CompStats.csv changes (same cadence as the GDoc/stat
refresh pipeline) so dashboard_site's cache doesn't go stale. Requires the
full repo venv (Models/constants dependency chain), unlike dashboard_site
itself.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Models.League import fantasyLeague  # noqa: E402
from shared.runtime_config import REF_DIR  # noqa: E402

OUTPUT_PATH = REF_DIR / "real_matchup_flags.csv"


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

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Year", "Week", "Season", "Team", "real_matchup"])
        for _, row in po.sort_values(["Year", "Week", "Team"]).iterrows():
            writer.writerow([int(row["Year"]), int(row["Week"]), row["Season"], row["Team"], int(row["real_matchup"])])

    print(f"Wrote {len(po)} playoff-week real_matchup rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
