"""Backtest data for the Yahoo seasons (2024-2026) in the same file format as
scripts/export_backtest_data.py (<year>_games/projections/rosters/weeks.csv),
so the Trade Finder's tuning/backtest tools run on them unchanged -- the fresh
2024-26 hold-out (_planning/trade-recommender.md).

Sources:
  - ESPN's public player endpoint (no league needed):
    /apis/v3/games/fba/seasons/<year>/players?view=kona_player_info
      statSourceId=0, statSplitTypeId=5  one row per player per scoring period
                                          (games: stat 42 == 1)
      statSourceId=1, statSplitTypeId=0  ESPN's season projection (totals;
                                          checked 2026-10-27 to be preseason --
                                          error vs actual matches the clean
                                          2019/2021/2022 projections, unlike
                                          the 2023 mid-season snapshot)
  - our league's Yahoo rosters on checkpoint dates
    (scripts/export_yahoo_checkpoint_rosters.py), matched to ESPN players by
    normalized name;
  - Ref/week_calendar.csv for week boundaries. ESPN scoring period 1 = week
    1's start date (opening night; checked: Wembanyama's 2023-10-25 debut is
    period 2).

Without --yahoo-rosters it writes only games (with MIN/GS columns) and
projections (with proj_MIN) -- used for the projection research on any season
2018+.

Only checkpoint-day rosters exist (no day-by-day history), so these seasons
support the oracle evaluation and frozen-roster replays, not the
real-roster replay.

  python -m scripts.export_espn_public_season --years 2024 2025 2026 \\
      --yahoo-rosters yahoo_rosters.csv --calendar Ref/week_calendar.csv --out <dir>
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

import pandas as pd

URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/{year}/players"
STATS = {"13": "FGM", "14": "FGA", "15": "FTM", "16": "FTA", "17": "3PTM", "6": "REB", "3": "AST",
         "2": "STL", "1": "BLK", "11": "TO", "0": "PTS"}
COMP = ["FGM", "FGA", "FTM", "FTA", "3PTM", "REB", "AST", "STL", "BLK", "TO", "PTS"]
# Extra per-game columns for projection research (ignored by the backtest).
EXTRA = {"40": "MIN", "41": "GS"}
IR_SLOT = 13
ACTIVE_SLOT = 0


def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[.'\-]", "", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s)
    return re.sub(r"\s+", " ", s).strip()


def fetch(year: int, cache: Path) -> list[dict]:
    path = cache / f"espn_{year}.json"
    if path.exists():
        return json.loads(path.read_text())
    import requests  # only needed when not cached (not in the light venv)

    r = requests.get(URL.format(year=year), params={"scoringPeriodId": 0, "view": "kona_player_info"},
                     headers={"X-Fantasy-Filter": json.dumps({"players": {"limit": 5000}})}, timeout=120)
    r.raise_for_status()
    path.write_text(r.text)
    return r.json()


def season_files(year: int, players: list[dict], rosters: pd.DataFrame, cal: pd.DataFrame, out: Path) -> dict:
    games, proj = [], []
    for p in players:
        pid, name = p["id"], p.get("fullName")
        for s in p.get("stats") or []:
            st = s.get("stats") or {}
            if s.get("seasonId") != year:
                continue
            if s.get("statSourceId") == 0 and s.get("statSplitTypeId") == 5 and st.get("42") == 1:
                games.append({"PlayerId": pid, "ScoringPeriod": int(s["scoringPeriodId"]),
                              **{c: float(st.get(k, 0.0)) for k, c in STATS.items()},
                              **{c: float(st.get(k, 0.0)) for k, c in EXTRA.items()}})
            elif s.get("statSourceId") == 1 and s.get("statSplitTypeId") == 0 and st.get("42"):
                gp = float(st["42"])
                proj.append({"PlayerId": pid, "Player": name,
                             **{f"proj_{c}": float(st.get(k, 0.0)) / gp for k, c in STATS.items()},
                             "proj_MIN": float(st.get("40", 0.0)) / gp, "proj_GP": gp})
    games = pd.DataFrame(games)[["PlayerId", "ScoringPeriod"] + COMP + list(EXTRA.values())]
    proj = pd.DataFrame(proj)
    # Every player ESPN lists gets a name (projection or not) -- the backtest
    # names players from this file.
    names = pd.DataFrame([{"PlayerId": p["id"], "Player": p.get("fullName")} for p in players])
    proj = names.merge(proj.drop(columns="Player"), on="PlayerId", how="left")

    games.to_csv(out / f"{year}_games.csv", index=False)
    proj.to_csv(out / f"{year}_projections.csv", index=False)
    if rosters is None or cal is None or year not in set(cal["Year"]):
        return {"games": len(games), "projected": int(proj["proj_GP"].notna().sum())}

    yc = cal[cal["Year"] == year].sort_values("Week")
    opening = pd.Timestamp(yc["StartDate"].iloc[0])
    weeks = pd.DataFrame({
        "Week": yc["Week"].to_numpy(),
        "StartSP": [(pd.Timestamp(d) - opening).days + 1 for d in yc["StartDate"]],
        "EndSP": [(pd.Timestamp(d) - opening).days + 1 for d in yc["EndDate"]],
    })

    by_name: dict[str, list] = {}
    for p in players:
        by_name.setdefault(norm(p.get("fullName", "")), []).append(p["id"])
    played = set(games["PlayerId"])
    r = rosters[rosters["Year"] == year].copy()
    ids, misses = [], []
    for row in r.itertuples():
        cands = by_name.get(norm(row.Player), [])
        # Same name twice (rare): prefer the one who actually played this season.
        cands = sorted(cands, key=lambda i: i not in played)
        ids.append(cands[0] if cands else None)
        if not cands:
            misses.append(row.Player)
    r["PlayerId"] = ids
    r = r.dropna(subset=["PlayerId"])
    r["ScoringPeriod"] = [(pd.Timestamp(d) - opening).days + 1 for d in r["Date"]]
    r["LineupSlotId"] = [IR_SLOT if s == "IR" else ACTIVE_SLOT for s in r["Slot"]]
    r = r.rename(columns={"FantasyTeam": "Team"})[["Team", "ScoringPeriod", "PlayerId", "LineupSlotId"]]
    r["PlayerId"] = r["PlayerId"].astype(int)

    r.to_csv(out / f"{year}_rosters.csv", index=False)
    weeks.to_csv(out / f"{year}_weeks.csv", index=False)
    return {"games": len(games), "projected": int(proj["proj_GP"].notna().sum()), "roster_rows": len(r),
            "unmatched": sorted(set(misses))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, nargs="+", default=[2024, 2025, 2026])
    ap.add_argument("--yahoo-rosters", type=Path, help="omit for games + projections only")
    ap.add_argument("--calendar", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    rosters = pd.read_csv(args.yahoo_rosters) if args.yahoo_rosters else None
    cal = pd.read_csv(args.calendar) if args.calendar else None
    for year in args.years:
        print(year, season_files(year, fetch(year, args.out), rosters, cal, args.out), flush=True)


if __name__ == "__main__":
    main()
