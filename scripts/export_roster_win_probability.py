"""Exports every current-season fantasy team's weekly matchup win
probability (real roster, no what-ifs) into Ref/roster_win_probability.csv
-- the Roster Rankings page's premium "Win probability" sub-tab reads this
cached snapshot instead of rerunning the optimizer's scoring on every
request. The inputs (rosters, projections) only change once a day anyway,
same reasoning as every other Ref/*.csv export.

Reuses dashboard_site.api.league_store.LeagueStore.compute_roster_win_probabilities()
directly -- the exact same computation the app would run live -- rather
than reimplementing the optimizer glue here, so the cached numbers can
never drift from what a live call would return.

Usage: python -m scripts.export_roster_win_probability
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dashboard_site.api.league_store import LeagueStore  # noqa: E402
from shared.atomic_write import atomic_write  # noqa: E402
from shared.runtime_config import REF_DIR  # noqa: E402

OUTPUT_PATH = REF_DIR / "roster_win_probability.csv"


def main() -> None:
    data = LeagueStore().compute_roster_win_probabilities()
    rows = [
        {"Year": data["year"], "Team": row["team"], "MatchupWin": row["matchup_win"], **row["categories"]}
        for row in data["teams"]
    ]
    df = pd.DataFrame(rows, columns=["Year", "Team", "MatchupWin", *data["categories"]])
    atomic_write(OUTPUT_PATH, lambda f: df.to_csv(f, index=False))
    print(f"Wrote {len(df)} team rows for {data['year']} to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
