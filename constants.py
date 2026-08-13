import os
import json
import gspread as gs
import math
from pathlib import Path
from espn_fr.basketball.constant import STATS_MAP
import datetime
import csv
from shared.runtime_config import (
    GOOGLE_SERVICE_ACCOUNT_JSON_PATH,
    calendar_csv_path,
)


## ESPN league/login info
espn_leagueID = 82864377
# `os.getenv(key, default)` only falls back to `default` when the var is
# entirely UNSET -- an env var explicitly set to "" (as ESPN_S2/ESPN_SWID
# are on the droplet, likely a leftover from the Yahoo migration cleanup)
# still counts as "set" and silently wins with an empty string, which
# breaks any espn_fr auth attempt. `or` treats blank the same as unset.
espn_s2 = os.getenv("ESPN_S2") or (
    'AEB10E76tw6SHjpKpDqw7nBJndJfFekcJaC%2FiUC0JrJ2wj1Nb5YcBVZ04ary1%2F%2FEiiqzXaA1UPb0CcRBu%2FMpigZ%2BX6Hr%2FqD0nan6hZfQok4YHbHuVkIAVHzfUnJ%2FLDPNMqtIcS8ZmhAFVwW62RM6HlhFSk1DZz6z29J0TZjioAkFhYwVDaf6ILm%2FrtaSTeBSPwdSOqxxyd%2F%2FzlZwt1avKDdP0fLxEytLrCGjtUpd8LANz6kvqXLgUBjRCz0YBrKbYlfzkc6zhmt2Fx%2Fncfcoi5eEOZbTPlFJRG%2B2k6Qw079Z7g%3D%3D'
)
espn_swid = os.getenv("ESPN_SWID") or '{F1B30D95-9F03-4CA9-BE62-D89858BE885E}'

## Yahoo league/login info
# The Yahoo consumer key/secret/refresh token live in private.json (repo
# root, gitignored) instead of hardcoded here -- keeps the actual secret
# values out of source/version control and in one discoverable file,
# matching yfpy's own private.json convention (yfpy_fr/query.py's
# YahooFantasySportsQuery reads the same two field names as its own
# fallback when no consumer_key/consumer_secret is passed directly).
# Missing file falls back to None rather than crashing this import --
# surfaces as the same "client id cannot be empty"/"not authorized" errors
# yfpy_fr already raises downstream, instead of breaking every module that
# imports constants.py.
_private_json_path = Path(__file__).resolve().parent / "private.json"
try:
    with open(_private_json_path) as _f:
        _yahoo_private = json.load(_f)
except FileNotFoundError:
    _yahoo_private = {}

# Same blank-env-var-shadows-default gotcha as espn_s2/espn_swid above --
# the droplet's YAHOO_KEY/YAHOO_SECRET are set to "" (not unset), which
# os.getenv(key, default) doesn't fall back on. Found while verifying Yahoo
# rank data live on the droplet for the Team-page roster/rank feature --
# every yfpy_fr call there was silently failing with "client id cannot be
# empty" / "not authorized" because of this.
yKey = os.getenv("YAHOO_KEY") or _yahoo_private.get("consumer_key")
ySec = os.getenv("YAHOO_SECRET") or _yahoo_private.get("consumer_secret")
yRefTok = _yahoo_private.get("refresh_token")

yLeagueIDs = {
    2024:138772,
    2025:29987,
    2026:79557,
}

currentYear = 2026

## ALL MEMBERS EVER
allMembers = sorted(['Jesse', 'Ange', 'Juan', 'Saamrit', 'Rohil', 'Chirayu', 'Fano', 'Zahir', 'Amil', 'Sama', 'Sai'])
abbMembers = {'Jesse':'JS', 'Ange':'AB', 'Juan':'JA', 'Rohil':'RB',
              'Saamrit':'SR', 'Fano':'FR', 'Chirayu':'CP', 'Zahir':'ZZ',
              'Amil':'AO', 'Sama':'SKa', 'Sai':'SKo'}

mainCats = ['FG%', 'FT%', '3PTM', 'REB', 'AST', 'STL', 'BLK', 'TO', 'PTS']
statCats = ['FG%', 'FT%', '3PTM', 'REB', 'AST', 'STL', 'BLK', 'TO', 'PTS', 'FGM', 'FGA', 'FTM', 'FTA', '3PTA', '3PT%']
mainCats_ratings = [cat+"_rating" for cat in mainCats]
mainCats_rankings = [cat+"_rank" for cat in mainCats]
mainCats_wt_rankings = [cat+"_wt_rank" for cat in mainCats]
posCats = ['FG%', 'FT%', '3PTM', 'REB', 'AST', 'STL', 'BLK', 'PTS']
negCats = ['TO']
mainCatsSum = ['3PTM', 'REB', 'AST', 'STL', 'BLK', 'TO', 'PTS']
mainCatsPCT = ['FG%', 'FT%']

# Manual stat overrides (applied after pulling from ESPN/Yahoo)
# Each dict should include: year, week, team, and any of the 9 main stats
# Example:
# {"year": 2026, "week": 1, "team": "Fano", "FG%": 0.45, "FT%": 0.78, "3PTM": 120, "PTS": 950, "REB": 420, "AST": 260, "STL": 65, "BLK": 40, "TO": 90}
replacement_stats = [{"year":2026, "week":14, "team":"Zahir", "FG%":0.4859, "FT%":0.783, "3PTM":75, "PTS":676, "REB":250, "AST":177, "STL":42, "BLK":19, "TO":94}]

## season info dict has tuple as value for each key
## each tuple will contain ((team1, team2, ...), is ESPN (T/F), is W/L scoring (T/F))
seasonInfo = {
    2019: (sorted(('Jesse', 'Ange', 'Juan', 'Saamrit', 'Rohil', 'Chirayu', 'Fano', 'Zahir')),True,True),
    2020: (sorted(('Jesse', 'Ange', 'Juan', 'Sama', 'Saamrit', 'Rohil', 'Chirayu', 'Fano', 'Zahir')),True,True),
    2021: (sorted(('Amil', 'Ange', 'Juan', 'Sama', 'Saamrit', 'Rohil', 'Chirayu', 'Fano', 'Zahir')),True,True),
    2022: (sorted(('Amil', 'Ange', 'Juan', 'Sama', 'Saamrit', 'Rohil', 'Chirayu', 'Fano', 'Zahir', 'Sai')),True,True),
    2023: (sorted(('Amil', 'Ange', 'Juan', 'Sama', 'Saamrit', 'Rohil', 'Chirayu', 'Fano', 'Zahir', 'Sai')),True,True),
    2024: (sorted(('Amil', 'Ange', 'Juan', 'Sama', 'Saamrit', 'Rohil', 'Chirayu', 'Fano', 'Zahir', 'Sai')),False,False),
    2025: (sorted(('Amil', 'Ange', 'Juan', 'Sama', 'Saamrit', 'Rohil', 'Chirayu', 'Fano', 'Zahir', 'Sai')),False,True),
    2026: (sorted(('Amil', 'Ange', 'Juan', 'Sama', 'Saamrit', 'Rohil', 'Chirayu', 'Fano', 'Zahir', 'Sai')),False,False)
}

# was too lazy to rewrite seasonInfo as a dict, but everything should be using this Dict as reference
seasonInfoDict = {
    year: {'teams': seasonInfo[year][0], 'is_espn': seasonInfo[year][1], 'is_WL': seasonInfo[year][2]} for year in seasonInfo
}

# number of participating teams per year
teamCount = {year : len(seasonInfo[year][0]) for year in seasonInfo}

## Calendars
calendars = {year: calendar_csv_path(year) for year in seasonInfo}

# Draft order for each season
draftOrder = {
    2019: ('Jesse', 'Zahir', 'Ange', 'Saamrit', 'Juan', 'Rohil', 'Fano', 'Chirayu'),
    2020: ('Saamrit', 'Chirayu', 'Jesse', 'Ange', 'Sama', 'Juan', 'Zahir', 'Rohil', 'Fano'),
    2021: ('Amil', 'Juan', 'Ange', 'Chirayu', 'Fano', 'Sama', 'Zahir', 'Saamrit', 'Rohil'),
    2022: ('Sama', 'Juan', 'Saamrit', 'Zahir', 'Ange', 'Rohil', 'Chirayu', 'Amil', 'Fano', 'Sai'),
    2023: ('Sama', 'Amil', 'Ange', 'Zahir', 'Saamrit', 'Chirayu', 'Fano', 'Juan', 'Rohil', 'Sai'),
    2024: ('Ange', 'Zahir', 'Saamrit', 'Sama', 'Amil', 'Juan', 'Rohil', 'Fano', 'Sai', 'Chirayu'),
    2025: ('Juan', 'Amil', 'Sai', 'Sama', 'Rohil', 'Ange', 'Fano', 'Saamrit', 'Chirayu', 'Zahir'),
    2026: ('Rohil', 'Chirayu', 'Ange', 'Fano', 'Sai', 'Amil', 'Sama', 'Juan', 'Zahir', 'Saamrit')
}

# number of REGULAR SEASON weeks per year
RS_weekCountDict = {
    2019:20,
    2020:18,
    2021:18,
    2022:18,
    2023:18,
    2024:18,
    2025:18,
    2026:18,
}

# number of playoff teams per year
playoffTeamCount = {
    2019:4,
    2020:0,
    2021:4,
    2022:6,
    2023:6,
    2024:6,
    2025:6,
    2026:6,
}

# number of rounds in playoffs per year
playoffRounds = {year:math.ceil(playoffTeamCount[year] / 2) for year in playoffTeamCount}

# number of weeks per round of playoffs per year
playoffRoundLength = {
    2019:2,
    2020:2,
    2021:2,
    2022:2,
    2023:2,
    2024:1,
    2025:1,
    2026:1,
}

totalMatchupCount = {year: RS_weekCountDict[year] + playoffRounds[year] for year in RS_weekCountDict}

# if the official standings in the league are calculated differently for some reason
# (e.g. tiebreakers that haven't been accounted for here)
standingsOverwrite = {
    2025: {1: "Fano",
           2: "Sama",
           3: "Amil",
           4: "Zahir",
           5: "Saamrit",
           6: "Ange",
           7: "Juan",
           8: "Sai",
           9: "Rohil",
           10: "Chirayu"}
}

## ESPN-SPECIFIC INFO
espnTeamIDs = {
    2019: {1: 'Fano', 2: 'Jesse', 3: 'Chirayu', 4: 'Saamrit', 5: 'Ange', 6: 'Zahir', 7: 'Juan', 8: 'Rohil'},
    2020: {1: 'Fano', 2: 'Jesse', 3: 'Chirayu', 4: 'Saamrit', 5: 'Ange', 6: 'Zahir', 7: 'Juan', 8: 'Rohil', 9: 'Sama'},
    2021: {1: 'Fano', 2: 'Amil', 3: 'Chirayu', 4: 'Saamrit', 5: 'Ange', 6: 'Zahir', 7: 'Juan', 8: 'Rohil', 9: 'Sama'},
    2022: {1: 'Fano', 2: 'Jesse', 3: 'Chirayu', 4: 'Saamrit', 5: 'Ange', 6: 'Zahir', 7: 'Juan', 8: 'Rohil', 9: 'Sama', 10: 'Sai', 11: 'Amil'},
    2023: {1: 'Fano', 2: 'Jesse', 3: 'Chirayu', 4: 'Saamrit', 5: 'Ange', 6: 'Zahir', 7: 'Juan', 8: 'Rohil', 9: 'Sama', 10: 'Sai', 11: 'Amil'},
}
# Add flipped keys to dict
for year in espnTeamIDs:
    for num in range(1,len(espnTeamIDs[year])):
        espnTeamIDs[year][espnTeamIDs[year].get(num)] = num

espnStatMap = STATS_MAP
for key in range(len(espnStatMap)):
    espnStatMap[espnStatMap[str(key)]] = str(key)

## YAHOO-SPECIFIC INFO ##
yTeamIDs = {
    2024: {1:'Fano', 2:"Saamrit", 3:"Ange", 4:"Juan", 5:"Chirayu", 6:"Sai", 7:"Amil", 8:"Sama", 9:"Zahir", 10:"Rohil"},
    2025: {1:'Fano', 2:"Saamrit", 3:"Zahir", 4:"Chirayu", 5:"Amil", 6:"Juan", 7:"Sai", 8:"Sama", 9:"Ange", 10:"Rohil"},
    2026: {1:'Fano', 2:"Saamrit", 3:"Zahir", 4:"Chirayu", 5:"Amil", 6:"Juan", 7:"Sai", 8:"Sama", 9:"Ange", 10:"Rohil"},
    }
for year in yTeamIDs:
    for num in range(1,len(yTeamIDs[year])):
        yTeamIDs[year][yTeamIDs[year].get(num)] = num

yGameIDs = {
    2024:428,
    2025:454,
    2026:466,
}

yStatMap = {
    0: 'GP', 'GP': 0, 1: 'GS', 'GS': 1, 2: 'MIN', 'MIN': 2, 3: 'FGA', 'FGA': 3, 4: 'FGM', 'FGM': 4,
    5: 'FG%', 'FG%': 5, 6: 'FTA', 'FTA': 6, 7: 'FTM', 'FTM': 7, 8: 'FT%', 'FT%': 8, 9: '3PTA', '3PTA': 9,
    10: '3PTM', '3PTM': 10, 11: '3PT%', '3PT%': 11, 12: 'PTS', 'PTS': 12, 13: 'OREB', 'OREB': 13,
    14: 'DREB', 'DREB': 14, 15: 'REB', 'REB': 15, 16: 'AST', 'AST': 16, 17: 'STL', 'STL': 17, 18: 'BLK',
    'BLK': 18, 19: 'TO', 'TO': 19, 20: 'A/T', 'A/T': 20, 21: 'PF', 'PF': 21, 22: 'DISQ', 'DISQ': 22,
    23: 'TECH', 'TECH': 23, 24: 'EJCT', 'EJCT': 24, 25: 'FF', 'FF': 25, 26: 'MPG', 'MPG': 26, 27: 'DD',
    'DD': 27, 28: 'TD', 'TD': 28
            }

## GOOGLE DOC SPECIFIC INFO ##
gc = gs.service_account(
        GOOGLE_SERVICE_ACCOUNT_JSON_PATH
    )

## Spreadsheet Names ##
gDocNames = {
    2019:"ULTRA 18/19 Rankings",
    2020:"19/20 Rankings (The Numbers)",
    2021:"20/21 Rankings (The Numbers)",
    2022:"21/22 Rankings (The Numbers)",
    2023:"ULTRA 22/23 Rankings",
    2024:"23/24 Rankings (The Numbers)",
    2025:"24/25 Rankings (The Numbers)",
    2026:"25/26 Rankings (The Numbers)",
}

# the categories and order they appear on the gdocs
gDocStatCats = ['FG%', 'FT%', '3PTM', 'PTS', 'REB', 'AST', 'STL', 'BLK', 'TO']

## are the actual stats the top rows? ##
stat24 = True
stat23 = False
stat22 = False
stat21 = False
stat20 = False
stat19 = True
stat25 = True
stat26 = True

## Functions
def bs_calList(day, calList): #binary search to find what week/matchup "day" is in
    if day < calList[0][1]: # if day is before start date of first week
        return calList[0][0]

    if day > calList[-1][2]: # if day is after end date of last week
        return calList[-1][0]

    if len(calList) == 1:
        return calList[0][0]

    midInd = len(calList)//2

    if day < calList[midInd][1]: ## if today is before the start date of the middle week
        return bs_calList(day, calList[:midInd])

    elif day > calList[midInd][2]: ## if today is after the end date of the middle week
        return bs_calList(day, calList[midInd+1:])

    else:
        return calList[midInd][0]

def getLastWeek(year):
    if year == currentYear:
        today = datetime.date.today()
        calPath = calendar_csv_path(year)
        with open(calPath, 'r') as csvfile:
            reader = csv.reader(csvfile, delimiter=',')
            next(reader)
            calList = [[int(week[0]), datetime.date(int(week[1]), int(week[2]), int(week[3])),
                        datetime.date(int(week[4]), int(week[5]), int(week[6]))]
                       for week in reader]
        lastWeek = min(bs_calList(today, calList), RS_weekCountDict[year] + playoffRounds[year])
    elif year < currentYear:
        lastWeek = RS_weekCountDict[year] + playoffRounds[year]
    elif year > currentYear:
        print("Invalid Year")
        return None

    return lastWeek

if __name__ == '__main__':
    day = datetime.datetime.today()
    x = bs_calList(day, calendars[2025])
