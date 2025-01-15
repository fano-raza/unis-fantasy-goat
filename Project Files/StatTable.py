import pandas as pd
from IPython.display import display
from tkinter import *
import time
import csv
from flask import Flask
from gdoc_writer import *
import datetime
import pandas as pd
from TeamManager import *
from League import *


app = Flask(__name__)
@app.route('/')
def runner():
    # Here, you can place the code you want to run
    # For example, a simple return message
    start = 2019
    end = 2024

    while True:
        for year in range(start, end + 1):
            pass
            x = leagueSeason(year)

            pdDict = {f"{team} W{week}": [stat for stat in x.statDict[week][team].values()] for week in x.statDict for team
                      in x.statDict[week]}
            # print(pdDict)
            index = [statName for statName in x.statDict[1]['Fano'].keys()]

            df = pd.DataFrame(pdDict, index)
            df = df.transpose()

        return df.to_html(notebook=True)




if __name__ == '__main__':
    app.run(debug=True, port=8080)