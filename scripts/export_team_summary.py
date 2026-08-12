"""Exports per-team career profile stats (chips, finals, playoffs, streaks,
draft scores, ...) from Models/team_profile.py::build_team_summary_df, so
dashboard_site (lightweight venv, never imports Models) can serve the Career
Comparison page. That function needs TeamManager -> Models.seasons/Draft ->
espn_fr/yfpy_fr, unlike the rest of dashboard_site's data path.

Run this whenever Ref/*_CompStats.csv changes (same cadence as the GDoc/stat
refresh pipeline, same as scripts/export_real_matchup_flags.py) so
dashboard_site's cache doesn't go stale. Requires the full repo venv.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Models.League import fantasyLeague  # noqa: E402
from Models.team_profile import build_team_summary_df  # noqa: E402
from shared.atomic_write import atomic_write  # noqa: E402
from shared.runtime_config import REF_DIR  # noqa: E402

OUTPUT_PATH = REF_DIR / "team_summary.csv"


def main() -> None:
    lg = fantasyLeague()
    df = build_team_summary_df(reuse_managers={tm.name: tm for tm in lg.historicalMembers})

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(OUTPUT_PATH, lambda f: df.to_csv(f, index=False))

    print(f"Wrote {len(df)} team summary rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
