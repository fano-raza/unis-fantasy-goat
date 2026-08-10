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
from datetime import timedelta
from discord.discord_messages import notify_milestones
from shared.runtime_config import calendar_csv_path
from scripts.export_playoff_brackets import main as export_playoff_brackets

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
                updateStatCSV(year)
                updateStandings(year)

                # Playoff bracket data (Standings page's playoff tree toggle) only
                # changes when there's a new playoff result. currentWeek can't
                # gate this: bs_calList() pins it at the calendar's last row
                # forever once today is past the season's final date, so months
                # after the season ends this would otherwise look identical to
                # being mid-playoffs. Check real calendar proximity to the
                # season's actual final week (calList's last row) instead.
                last_week_start = calList[-1][1]
                if playoffTeamCount.get(year, 0) > 0 and abs((today - last_week_start).days) <= 10:
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
                sleep_seconds = min(60 * 60, seconds_until_target)
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
