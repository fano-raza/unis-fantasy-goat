"""Standalone stat-refresh loop, decoupled from Google Sheets output.

GDoc/GDoc_updater.py historically did both: pull fresh stats AND push them
to Google Sheets. Now that the web app (dashboard_site + Next.js frontend)
is the live presentation layer, the Sheets-writing half is no longer
needed for day-to-day operation -- this module keeps only the
stat-fetching half. GDoc_updater.py is left as-is (not touched here, may
be retired later) rather than edited in place, so nothing here risks
breaking its still-independent Sheets-writing path.

Two-tier cadence, same shape as GDoc_updater.py's own loop:
- 6PM-2AM Eastern (game hours): refresh the stat CSV every ~2 minutes, so
  the web app/bots reflect near-live stats while games are happening.
- Otherwise: one full refresh (stat CSV + all 3 precomputed exports for
  dashboard_site), then sleep until 6PM.

Deliberately does NOT build the full fantasyLeague() object or send
Discord milestone notifications -- both added real cost (a full
historical league rebuild) for the stat-CSV refresh itself, and the user
chose to drop them here rather than pay that cost every cycle. Revisit
if milestones are wanted again later.
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
                updateStatCSV(year)

                try:
                    export_real_matchup_flags()
                except Exception as flags_exc:
                    print(f"real_matchup_flags export warning: {flags_exc}")

                try:
                    export_team_summary()
                except Exception as summary_exc:
                    print(f"team_summary export warning: {summary_exc}")

                if _playoff_window_active(year, today, calList):
                    try:
                        export_playoff_brackets()
                    except Exception as bracket_exc:
                        print(f"playoff_brackets export warning: {bracket_exc}")

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
