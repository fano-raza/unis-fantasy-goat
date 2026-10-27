"""Every fantasy team's Yahoo roster on given dates, for the Yahoo seasons
(2024-2026) -- the rosters half of the Trade Finder's fresh 2024-26 hold-out
(_planning/trade-recommender.md). Read-only: Yahoo's documented
`team/{team_key}/roster;date=YYYY-MM-DD` resource, same auth as
scripts/export_roster_ranks.py.

Default dates: the first day of weeks 1 and 4-14 (Ref/week_calendar.csv) --
the backtest's checkpoints, plus week 1 (post-draft).

Run where the Yahoo credentials live (stat-updater container):
  python3 -m scripts.export_yahoo_checkpoint_rosters --years 2024 2025 2026 --out /tmp/yahoo_rosters.csv
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from constants import yTeamIDs  # noqa: E402
from shared.runtime_config import REF_DIR  # noqa: E402

WEEKS = (1, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14)


def roster_on(league_key: str, team_id: int, date: str) -> list[dict]:
    from yfpy_fr.YahooQuery import make_yahoo_api_request

    data = make_yahoo_api_request(f"team/{league_key}.t.{team_id}/roster;date={date}?format=json")
    players = data["fantasy_content"]["team"][1]["roster"]["0"]["players"]
    out = []
    for key, entry in players.items():
        if key == "count" or not isinstance(entry, dict):
            continue
        info = {}
        for field in entry["player"][0]:
            if isinstance(field, dict):
                info.update(field)
        sel = entry["player"][1].get("selected_position") or [] if len(entry["player"]) > 1 else []
        pos = next((x["position"] for x in sel if isinstance(x, dict) and "position" in x), "")
        out.append({
            "Player": info["name"]["full"],
            "YahooPlayerId": int(info["player_id"]),
            "NBATeam": info.get("editorial_team_abbr", ""),
            "Slot": "IR" if pos in ("IL", "IL+") else pos,
        })
    return out


def main() -> None:
    from yfpy_fr.YahooQuery import league_keys

    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, nargs="+", default=[2024, 2025, 2026])
    ap.add_argument("--weeks", type=int, nargs="+", default=list(WEEKS))
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    cal = pd.read_csv(REF_DIR / "week_calendar.csv")
    rows = []
    for year in args.years:
        teams = {k: v for k, v in yTeamIDs[year].items() if isinstance(k, int)}
        for week in args.weeks:
            hit = cal[(cal["Year"] == year) & (cal["Week"] == week)]
            if hit.empty:
                print(f"{year} week {week}: not in week_calendar.csv, skipped")
                continue
            date = str(hit["StartDate"].iloc[0])
            for team_id, team in teams.items():
                for p in roster_on(league_keys[year], team_id, date):
                    rows.append({"Year": year, "Week": week, "Date": date, "FantasyTeam": team, **p})
                time.sleep(0.2)
            print(f"{year} week {week} ({date}): {sum(1 for r in rows if r['Year'] == year and r['Week'] == week)} rostered", flush=True)
    pd.DataFrame(rows).to_csv(args.out, index=False)
    print(f"wrote {len(rows)} rows -> {args.out}")


if __name__ == "__main__":
    main()
