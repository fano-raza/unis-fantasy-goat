import threading, time, csv, datetime
import os
import sys
import gspread.exceptions
from zoneinfo import ZoneInfo

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from flask import Flask, jsonify
from GDoc.GDoc_Week import *
from GDoc.GDoc_AllTime import *
from Models.Draft import Draft
from datetime import timedelta
from discord.discord_messages import notify_milestones
from shared.runtime_config import calendar_csv_path
from scripts.export_real_matchup_flags import main as export_real_matchup_flags
from scripts.export_team_summary import main as export_team_summary
from scripts.export_playoff_brackets import main as export_playoff_brackets
from scripts.export_player_stats import main as export_player_stats

app = Flask(__name__)
EASTERN_TZ = ZoneInfo("America/New_York")

# prevent double-starts
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

def run_updater():
    year = currentYear
    calPath = calendar_csv_path(year)
    with open(calPath, 'r') as csvfile:
        reader = csv.reader(csvfile, delimiter=',')
        next(reader)
        calList = [[int(week[0]), datetime.date(int(week[1]),int(week[2]),int(week[3])),
                    datetime.date(int(week[4]),int(week[5]),int(week[6]))]
                   for week in reader]

    while True:
        now = datetime.datetime.now(EASTERN_TZ)
        today = now.date()
        current_time = now.replace(tzinfo=None).time()
        displayTime = f"{now.month}/{now.day}/{now.year - 2000} {now.hour}:{now.minute:02}"

        # if the time is still before or equal to 2AM count it as yesterday
        # makes sure Sunday games that go past midnight EST are accounted for
        if current_time <= datetime.time(2, 0):
            currentWeek = bs_calList(today-timedelta(days=1), calList)

        else:
            currentWeek = bs_calList(today, calList)

        print(f"Current Week: {currentWeek}")
        # between 18:00 and 02:00
        if (current_time >= datetime.time(18, 0) or current_time <= datetime.time(2, 0)):
            try:
                updateCurrentSheet()

            except gspread.exceptions.APIError:
                print("Encountered API Error")
            except Exception as e:
                print("Encountered Other Error:", e)
                time.sleep(60*5)

            time.sleep(120)

        else:
            try:
                # Refresh draft results/scores once per daytime update cycle so sheets stay current.
                try:
                    print(f"Refreshing draft scores for {year}...")
                    d = Draft(year)
                    d.updateDraft()
                    print("Draft scores refreshed.")
                except Exception as draft_exc:
                    # Keep updater alive even if draft provider/auth has a transient issue.
                    print(f"Draft refresh warning: {draft_exc}")

                updateStatCSV(year)
                updateStandings(year)

                # dashboard_site's lightweight venv can't derive playoff-bracket
                # membership itself (no Models import) -- refresh its precomputed
                # lookup whenever the raw stat CSVs change, same cadence as above.
                try:
                    export_real_matchup_flags()
                except Exception as flags_exc:
                    print(f"real_matchup_flags export warning: {flags_exc}")

                # Same idea for the Career Comparison page's precomputed profile
                # stats (chips/finals/streaks/draft scores) -- also needs Models.
                try:
                    export_team_summary()
                except Exception as summary_exc:
                    print(f"team_summary export warning: {summary_exc}")

                # Real NBA player stats (season + 7/14/30/90-day rolling
                # windows) for the Players page's Trade Hub -- pure network
                # call to stats.nba.com via nba_api, no Models dependency,
                # but wrapped the same way since stats.nba.com is unofficial
                # and known to occasionally block/rate-limit.
                try:
                    export_player_stats()
                except Exception as player_stats_exc:
                    print(f"player_stats export warning: {player_stats_exc}")

                # Playoff bracket data (Standings page's playoff tree toggle) only
                # changes during the actual playoff window: from the first day of
                # the first playoff week through 10 days after the last playoff
                # week starts (buffer for late corrections). currentWeek can't
                # gate this: bs_calList() pins it at the calendar's last row
                # forever once today is past the season's final date, so months
                # after the season ends this would otherwise look identical to
                # being mid-playoffs.
                # Look up the real first/last playoff week numbers rather than
                # assuming calList's last row is the season's last real week --
                # this calendar file has trailing rows (week 24) well past the
                # actual final playoff week (21 for a standard 6-team, 3-round
                # bracket), so calList[-1] alone would be wrong here.
                first_po_week = RS_weekCountDict.get(year, 0) + 1
                last_po_week = RS_weekCountDict.get(year, 0) + playoffRounds.get(year, 0)
                first_po_week_start = next(
                    (start for wk, start, end in calList if wk == first_po_week), None
                )
                last_po_week_start = next(
                    (start for wk, start, end in calList if wk == last_po_week), None
                )
                po_window_active = (
                    playoffTeamCount.get(year, 0) > 0
                    and first_po_week_start is not None
                    and last_po_week_start is not None
                    and first_po_week_start <= today <= last_po_week_start + timedelta(days=10)
                )
                if po_window_active:
                    try:
                        export_playoff_brackets()
                    except Exception as bracket_exc:
                        print(f"playoff_brackets export warning: {bracket_exc}")

                league = fantasyLeague()

                updateCarTotals(league)
                updateRSTotals(league)
                updatePOTotals(league)
                updateCarAVGs(league)
                updateRSAVGs(league)
                updatePOAVGs(league)
                updateSummarySheet(league)

                # send discord messages
                print('Checking Milestons')
                stat_cols = ["PTS", "3PTM", "REB", "AST", "STL", "BLK"]
                rank_cols = [cat + "_rank" for cat in stat_cols]
                cols = ["Team"] + stat_cols + rank_cols
                dfs = {
                    "Career": league.get_totals_df()[cols],
                    "RS": league.get_totals_df(PO=False)[cols],
                    "PO": league.get_totals_df(RS=False)[cols]
                }

                notify = notify_milestones(dfs)

                target_dt = now.replace(hour=18, minute=0, second=0, microsecond=0)
                delta = target_dt - now
                seconds_until_target = max(0, delta.total_seconds())
                sleep_seconds = min(60 * 601, seconds_until_target)
                print(f"waiting {int(sleep_seconds)}s before next time check (toward 6PM EST)...")
                time.sleep(sleep_seconds)
            except gspread.exceptions.APIError:
                print("Encountered API Error")
                time.sleep(120)
            except Exception as e:
                print(f"Encountered Other Error: {e} at {displayTime}")
                time.sleep(60*5)

@app.route('/')
def index():
    return 'OK — updater server is running'

@app.route('/status')
def status():
    alive = bool(job_thread and job_thread.is_alive())
    return jsonify({"updater_thread_alive": alive})

@app.route('/run-script')
def run_script():
    started = ensure_updater_running()
    return jsonify({"status": "running", "started_now": started})

if __name__ == '__main__':
    started = ensure_updater_running()
    print(f"Updater thread started on boot: {started}")
    # If you’re accessing from another device on your LAN, use host='0.0.0.0'
    app.run(debug=True, use_reloader=False)  # disable reloader to avoid starting the thread twice

## INSTRUCTIONS TO RUN
'''
1. RUN THE FOLLOWING LINE IN THE TERMINAL
python3 GDoc/GDoc_updater.py

OR

PYTHONPATH="$PWD" python3 GDoc/GDoc_updater.py

THE INSTRUCTIONS BELOW ARE DEPRECATED.
SIMPLY RUNNING THIS SCRIPT WILL START THE UPDATER SERVER AND SCHEDULE THE UPDATES TO RUN AUTOMATICALLY.

2. THEN RUN THE FOLLOWING LINE
curl -i http://127.0.0.1:5000/run-script
'''
