import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler

from constants import *
from constants import seasonInfoDict as si

start = True
for year in si:
    statCSV = f"/Users/fano/Documents/Fantasy/Fantasy GOAT/Ref/{year}_CompStats.csv"
    if start:
        stats = pd.read_csv(statCSV)
        start = False
    else:
        dfToAdd = pd.read_csv(statCSV)
        stats = pd.concat([stats, dfToAdd], axis=0)

print(stats)

print(pd.isna(stats).value_counts())
# print(stats.groupby(['Team','Year'])[mainCats].mean())


