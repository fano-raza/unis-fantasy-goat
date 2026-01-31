import threading, time, csv, datetime
import gspread.exceptions
from flask import Flask, jsonify
from GDoc_Week import *
from GDoc_AllTime import *
from datetime import timedelta
from discord_messages import notify_milestones

app = Flask(__name__)

# prevent double-starts
job_lock = threading.Lock()
job_thread = None

def run_updater():
    year = currentYear
    calPath = f"/Users/fano/Documents/Fantasy/Fantasy GOAT/{year}/{year}_matchup_cal.csv"
    with open(calPath, 'r') as csvfile:
        reader = csv.reader(csvfile, delimiter=',')
        next(reader)
        calList = [[int(week[0]), datetime.date(int(week[1]),int(week[2]),int(week[3])),
                    datetime.date(int(week[4]),int(week[5]),int(week[6]))]
                   for week in reader]

    while True:
        today = datetime.date.today()
        current_time = datetime.datetime.now().time()

        now = datetime.datetime.now()
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

                target_time = datetime.time(18, 0)
                delta = datetime.datetime.combine(today, target_time) - datetime.datetime.combine(today, current_time)
                print("waiting until 6PM...")
                time.sleep(max(0, delta.total_seconds()))
            except gspread.exceptions.APIError:
                print("Encountered API Error")
                time.sleep(120)
            except Exception as e:
                print("Encountered Other Error:", e)
                time.sleep(60*5)

@app.route('/')
def index():
    return 'OK — go to /run-script to kick off the updater'

@app.route('/run-script')
def run_script():
    global job_thread
    with job_lock:
        if job_thread is None or not job_thread.is_alive():
            job_thread = threading.Thread(target=run_updater, daemon=True)
            job_thread.start()
            started = True
        else:
            started = False
    return jsonify({"status": "running", "started_now": started})

if __name__ == '__main__':
    # If you’re accessing from another device on your LAN, use host='0.0.0.0'
    app.run(debug=True, use_reloader=False)  # disable reloader to avoid starting the thread twice

## INSTRUCTIONS TO RUN
'''
1. RUN THE FOLLOWING LINE IN THE TERMINAL
python3 /Users/fano/Documents/Fantasy/Fantasy\ GOAT/unisFantasyGOAT/GDoc/GDoc_updater.py

OR

PYTHONPATH="/Users/fano/Documents/Fantasy/Fantasy GOAT/unisFantasyGOAT" \
python3 "/Users/fano/Documents/Fantasy/Fantasy GOAT/unisFantasyGOAT/GDoc/GDoc_updater.py"

2. THEN RUN THE FOLLOWING LINE
curl -i http://127.0.0.1:5000/run-script

OR

CLICK ON/OPEN THIS LINK
http://127.0.0.1:5000/run-script

3. CLICK ON THE SERVER LINK
'''

