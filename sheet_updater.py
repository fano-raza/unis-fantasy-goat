import gspread.exceptions
from flask import Flask
from gdoc_writer import *
from AllTimeGDoc import *

app = Flask(__name__)

@app.route('/run-script')
def run_script():
    # Here, you can place the code you want to run
    # For example, a simple return message
    year = 2025
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

        # Check if the current time is between 6 PM and 2 AM
        if (current_time >= datetime.datetime.strptime("18:00", "%H:%M").time() or
                current_time <= datetime.datetime.strptime("02:00", "%H:%M").time()):

            now = datetime.datetime.now()
            displayTime = f"{now.month}/{now.day}/{now.year - 2000} {now.hour}:{now.minute:02}"
            currentWeek = bs_calList(today, calList)

            try:
                write_gDoc(year, currentWeek, "UPDATING", "L2", italic=True)
                write_gDoc_stats(year, currentWeek)
                write_gDoc(year, currentWeek, f"UPDATED {displayTime}", "L2", bold=True)
            except gspread.exceptions.APIError:
                print("Encountered API Error")
                pass
            except:
                print("Encountered Other Error")
                time.sleep(60*5)

            time.sleep(120)

        else:
            league = fantasyLeague()

            try:
                updateCarTotals(league)
                updateRSTotals(league)
                updatePOTotals(league)
                updateCarAVGs(league)
                updateRSAVGs(league)
                updatePOAVGs(league)

                target_time = datetime.time(18, 00)
                delta = datetime.datetime.combine(today, target_time) - datetime.datetime.combine(today, current_time)
                time.sleep(delta.total_seconds())

            except gspread.exceptions.APIError:
                print("Encountered API Error")
                time.sleep(120)

            except:
                print("Encountered Other Error")
                time.sleep(60*5)

    # return "Hello, your Python script has run!"
    return "Updated"

# Run the server
if __name__ == '__main__':
    app.run(debug=True)