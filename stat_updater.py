"""Standalone production update loop -- the app's one live updater.

Originally split off from legacy/gdoc/GDoc_updater.py (2026-08-10) to
decouple stat refreshing from Google Sheets output. As of 2026-10-07,
GDoc_updater.py's remaining non-Sheets responsibilities (draft refresh,
player-stats/roster-rank/NBA-schedule exports, roster/team rank history,
Discord milestone notifications) were ported in here too, and the
gdoc-updater container/service was removed -- this is now the only
production update loop. See legacy/gdoc/README.md for the retired
Sheets-writing half.

Two-tier cadence, same shape as the old GDoc_updater.py loop:
- 6PM-2AM Eastern (game hours): refresh the stat CSV every ~2 minutes, so
  the web app/bots reflect near-live stats while games are happening.
- Otherwise: one full refresh (stat CSV + every precomputed export for
  dashboard_site + Discord bots, draft scores, roster/rank history
  snapshots, Discord milestones), then sleep until 6PM.
"""

from __future__ import annotations

import csv
import datetime
import os
import sys
import threading
import time
from datetime import timedelta
from zoneinfo import ZoneInfo

REPO_ROOT = os.path.abspath(os.path.dirname(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from flask import Flask, jsonify  # noqa: E402

from constants import (  # noqa: E402
    RS_weekCountDict,
    bs_calList,
    currentYear,
    playoffRounds,
    playoffTeamCount,
)
from StatGenerator import updateStatCSV  # noqa: E402
from shared.runtime_config import calendar_csv_path  # noqa: E402
from scripts.export_real_matchup_flags import main as export_real_matchup_flags  # noqa: E402
from scripts.export_team_summary import main as export_team_summary  # noqa: E402
from scripts.export_playoff_brackets import main as export_playoff_brackets  # noqa: E402
from scripts.export_player_stats import main as export_player_stats  # noqa: E402
from scripts.export_roster_ranks import (  # noqa: E402
    append_roster_rank_history,
    append_team_roster_history,
    main as export_roster_ranks,
)
from scripts.export_nba_schedule import main as export_nba_schedule  # noqa: E402
from Models.Draft import Draft  # noqa: E402
from Models.League import fantasyLeague  # noqa: E402
from discord.discord_messages import notify_milestones  # noqa: E402

app = Flask(__name__)
EASTERN_TZ = ZoneInfo("America/New_York")

job_lock = threading.Lock()
job_thread = None


def ensure_updater_running():
    global job_thread
    with job_lock:
        if job_thread is None or not job_thread.is_alive():
            job_thread = threading.Thread(target=run_updater, daemon=True)
            job_thread.start()
            return True
        return False


def _load_cal_list(year: int) -> list[list]:
    calPath = calendar_csv_path(year)
    with open(calPath, "r") as csvfile:
        reader = csv.reader(csvfile)
        next(reader)
        return [
            [
                int(row[0]),
                datetime.date(int(row[1]), int(row[2]), int(row[3])),
                datetime.date(int(row[4]), int(row[5]), int(row[6])),
            ]
            for row in reader
        ]


def _playoff_window_active(year: int, today: datetime.date, calList: list[list]) -> bool:
    # Real first/last playoff week numbers, not calList's raw last row --
    # that calendar file has trailing rows well past the actual final
    # playoff week (e.g. week 24 vs. the real final of 21 for a 6-team,
    # 3-round bracket), so calList[-1] alone would be wrong here.
    first_po_week = RS_weekCountDict.get(year, 0) + 1
    last_po_week = RS_weekCountDict.get(year, 0) + playoffRounds.get(year, 0)
    first_po_week_start = next((s for wk, s, e in calList if wk == first_po_week), None)
    last_po_week_start = next((s for wk, s, e in calList if wk == last_po_week), None)
    return bool(
        playoffTeamCount.get(year, 0) > 0
        and first_po_week_start is not None
        and last_po_week_start is not None
        and first_po_week_start <= today <= last_po_week_start + timedelta(days=10)
    )


def run_updater() -> None:
    year = currentYear
    calList = _load_cal_list(year)

    while True:
        now = datetime.datetime.now(EASTERN_TZ)
        today = now.date()
        current_time = now.replace(tzinfo=None).time()

        # if the time is still before or equal to 2AM count it as yesterday
        # -- makes sure Sunday games that go past midnight EST are accounted for
        lookup_date = today - timedelta(days=1) if current_time <= datetime.time(2, 0) else today
        currentWeek = bs_calList(lookup_date, calList)
        print(f"Current Week: {currentWeek}")

        if current_time >= datetime.time(18, 0) or current_time <= datetime.time(2, 0):
            try:
                updateStatCSV(year)
            except Exception as e:
                print(f"Stat refresh (game-hours) error: {e}")
            time.sleep(120)
        else:
            try:
                # Refresh draft results/scores once per daytime update cycle.
                try:
                    print(f"Refreshing draft scores for {year}...")
                    Draft(year).updateDraft()
                    print("Draft scores refreshed.")
                except Exception as draft_exc:
                    print(f"Draft refresh warning: {draft_exc}")

                updateStatCSV(year)

                try:
                    export_real_matchup_flags()
                except Exception as flags_exc:
                    print(f"real_matchup_flags export warning: {flags_exc}")

                try:
                    export_team_summary()
                except Exception as summary_exc:
                    print(f"team_summary export warning: {summary_exc}")

                # Trade Hub's real NBA player stats.
                try:
                    export_player_stats()
                except Exception as player_stats_exc:
                    print(f"player_stats export warning: {player_stats_exc}")

                # Team page's Roster sub-view: current-season roster/rank
                # snapshot.
                try:
                    export_roster_ranks([year])
                except Exception as roster_ranks_exc:
                    print(f"roster_ranks export warning: {roster_ranks_exc}")

                # Once-per-week player/team rank history snapshots -- both
                # no-op if this (year, currentWeek) is already recorded, so
                # calling them every daily cycle is cheap and correctly
                # fires exactly once per week.
                try:
                    added = append_roster_rank_history(year, currentWeek)
                    if added:
                        print(f"roster_rank_history: snapshotted {added} player rows for week {currentWeek}")
                except Exception as roster_history_exc:
                    print(f"roster_rank_history export warning: {roster_history_exc}")

                try:
                    added_teams = append_team_roster_history(year, currentWeek)
                    if added_teams:
                        print(f"team_roster_history: snapshotted {added_teams} team rows for week {currentWeek}")
                except Exception as team_roster_history_exc:
                    print(f"team_roster_history export warning: {team_roster_history_exc}")

                try:
                    export_nba_schedule()
                except Exception as schedule_exc:
                    print(f"nba_schedule export warning: {schedule_exc}")

                if _playoff_window_active(year, today, calList):
                    try:
                        export_playoff_brackets()
                    except Exception as bracket_exc:
                        print(f"playoff_brackets export warning: {bracket_exc}")

                # Discord milestone notifications -- gated by
                # DISCORD_ENABLE_MILESTONES inside notify_milestones itself.
                try:
                    print("Checking milestones")
                    league = fantasyLeague()
                    stat_cols = ["PTS", "3PTM", "REB", "AST", "STL", "BLK"]
                    rank_cols = [cat + "_rank" for cat in stat_cols]
                    cols = ["Team"] + stat_cols + rank_cols
                    dfs = {
                        "Career": league.get_totals_df()[cols],
                        "RS": league.get_totals_df(PO=False)[cols],
                        "PO": league.get_totals_df(RS=False)[cols],
                    }
                    notify_milestones(dfs)
                except Exception as milestones_exc:
                    print(f"milestones warning: {milestones_exc}")

                target_dt = now.replace(hour=18, minute=0, second=0, microsecond=0)
                delta = target_dt - now
                seconds_until_target = max(0, delta.total_seconds())
                sleep_seconds = min(60 * 60, seconds_until_target)
                print(f"waiting {int(sleep_seconds)}s before next check (toward 6PM EST)...")
                time.sleep(sleep_seconds)
            except Exception as e:
                print(f"Encountered error: {e}")
                time.sleep(60 * 5)


@app.route("/")
def index():
    return "OK — stat updater server is running"


@app.route("/status")
def status():
    alive = bool(job_thread and job_thread.is_alive())
    return jsonify({"updater_thread_alive": alive})


@app.route("/run-script")
def run_script():
    started = ensure_updater_running()
    return jsonify({"status": "running", "started_now": started})


if __name__ == "__main__":
    started = ensure_updater_running()
    print(f"Stat updater thread started on boot: {started}")
    app.run(host="0.0.0.0", debug=False, use_reloader=False)
