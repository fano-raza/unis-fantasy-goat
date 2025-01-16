import gspread as gs
import math
from espn_api.basketball.constant import STATS_MAP


## ESPN league/login info
espn_leagueID = 82864377
espn_s2 = 'AEB10E76tw6SHjpKpDqw7nBJndJfFekcJaC%2FiUC0JrJ2wj1Nb5YcBVZ04ary1%2F%2FEiiqzXaA1UPb0CcRBu%2FMpigZ%2BX6Hr%2FqD0nan6hZfQok4YHbHuVkIAVHzfUnJ%2FLDPNMqtIcS8ZmhAFVwW62RM6HlhFSk1DZz6z29J0TZjioAkFhYwVDaf6ILm%2FrtaSTeBSPwdSOqxxyd%2F%2FzlZwt1avKDdP0fLxEytLrCGjtUpd8LANz6kvqXLgUBjRCz0YBrKbYlfzkc6zhmt2Fx%2Fncfcoi5eEOZbTPlFJRG%2B2k6Qw079Z7g%3D%3D'
espn_swid = '{F1B30D95-9F03-4CA9-BE62-D89858BE885E}'

## Yahoo league/login info
yKey = "dj0yJmk9S0hLcFVjVVZtd2ZMJmQ9WVdrOWVqUk9XazV4YW1zbWNHbzlNQT09JnM9Y29uc3VtZXJzZWNyZXQmc3Y9MCZ4PTQ3"
ySec = "f98bfdf3286771e0b58de7b4062a59b0f867f467"
yTok = ".GdtU2GZ51hrVk80XOBbis0afJ1bdDKBFA.SFatClK5dwQ4u1rDoCCDN61MfyRmgEoyeiijZt3GDzFECBXBysVJGvFJIthzQZDJqnnB0ispBSBUlDfOc2pGuz7oVmIzfB2h_zWkPa5V0lg76dt5nTGrJYftvKw55rHHEaIdss2fXGC178S1ES9zgn6cwWkRV0vjSRFZQzQ0qCvRkCUpsS.Kn5HgY3shM9SwGWCyLRnwIMxcQv2ySwc_tuBXmsJBToVVjlZuADDo2Lj7WeQxXWSQLnBHJQAwt60fklT.TOnZyBdkMfQKWv1jEKUoyqfHeZ.FnkjrSQfDVo24rxusvpgN0mBsq8CHr1rq8raHJn7dMoVu1MoB5VYo2g.Qz94qqaNv1h.tpnGC0ews8ABLJxND0nf8l02M4HQ31JsLO6wOyBgm9yXLZzFL8oCM5ajWA8cPd0C_cLlCxqC4DPG7lGhhG87BZvRVwzPv7Xl5E4EKiknjV_VcQysrQj39.hoqFznYmkpAdcMA.M1eKgqoFwjMP17SJwt5j2OZfckN7NxGvRuWAv0029Vz9a_wUCcU3.XdoiLNp3ol83Bs.2KGlTePODW4eFIxIdIaX.hF29Rg8wu87Tw2PoTp4njwenB__zROg8X2lrqV1R4leXoiKj1.qOX3Ubc6w2h6yArkF4D0zkeP0PQXGgzC78yyyPRvJkecU48t7JybdCoYzPtQt1i8HDUQV2db3JRpCO4XHB8AOuj3a_dgvmLXM_rc3D.6MbD8wCkhSOVF7v.kNj4jIxRH1q3NB_K2eUbZsf.tuSUOHYffHu7yMypHNMc21.PYCZKRZZESrLVBEGafL8O0xW3AMmXGC5s7lpIoEj8TuRRRRrkuI6bSr3Pl0PK1Vs4rXK4vWjnzi5Doow7FA1zHkhs9SKTZ2XISScyfHgXFqjj6VDJh0FwgCebEFUSXbgOosBu_QUiYUeuFAK_JadqP4DCeWIpMkPtVxAmMYjdf_r8UgGZNc38vR.fDK"


yLeagueIDs = {
    2024:138772,
    2025:29987
}

currentYear = 2025

## ALL MEMBERS EVER
allMembers = sorted(['Jesse', 'Ange', 'Juan', 'Saamrit', 'Rohil', 'Chirayu', 'Fano', 'Zahir', 'Amil', 'Sama', 'Sai'])

## season info dict has tuple as value for each key
## each tuple will contain ((team1, team2, ...), is ESPN (T/F), is W/L scoring (T/F))
statCats = ['FG%', 'FT%', '3PTM', 'REB', 'AST', 'STL', 'BLK', 'TO', 'PTS', 'FGM', 'FGA', 'FTM', 'FTA', '3PTA', '3PT%']

seasonInfo = {
    2019: (('Jesse', 'Ange', 'Juan', 'Saamrit', 'Rohil', 'Chirayu', 'Fano', 'Zahir'),True,True),
    2020: (('Jesse', 'Ange', 'Juan', 'Sama', 'Saamrit', 'Rohil', 'Chirayu', 'Fano', 'Zahir'),True,True),
    2021: (('Amil', 'Ange', 'Juan', 'Sama', 'Saamrit', 'Rohil', 'Chirayu', 'Fano', 'Zahir'),True,True),
    2022: (('Amil', 'Ange', 'Juan', 'Sama', 'Saamrit', 'Rohil', 'Chirayu', 'Fano', 'Zahir', 'Sai'),True,True),
    2023: (('Amil', 'Ange', 'Juan', 'Sama', 'Saamrit', 'Rohil', 'Chirayu', 'Fano', 'Zahir', 'Sai'),True,True),
    2024: (('Amil', 'Ange', 'Juan', 'Sama', 'Saamrit', 'Rohil', 'Chirayu', 'Fano', 'Zahir', 'Sai'),False,False),
    2025: (('Amil', 'Ange', 'Juan', 'Sama', 'Saamrit', 'Rohil', 'Chirayu', 'Fano', 'Zahir', 'Sai'),False,True)
}

seasonInfo2 = {
    year: {'teams': seasonInfo[year][0], 'is_espn': seasonInfo[year][1], 'W/L': seasonInfo[year][1]} for year in seasonInfo
}

teamCount = {year : len(seasonInfo[year][0]) for year in seasonInfo}

## Calendars
calendars = {year:f"/Users/fano/Documents/Fantasy/Fantasy GOAT/{year}/{year}_matchup_cal.csv" for year in seasonInfo}

# Draft order for each season
draftOrder = {
    2019: ('Jesse', 'Zahir', 'Ange', 'Saamrit', 'Juan', 'Rohil', 'Fano', 'Chirayu'),
    2020: ('Saamrit', 'Chirayu', 'Jesse', 'Ange', 'Sama', 'Juan', 'Zahir', 'Rohil', 'Fano'),
    2021: ('Amil', 'Juan', 'Ange', 'Chirayu', 'Fano', 'Sama', 'Zahir', 'Saamrit', 'Rohil'),
    2022: ('Sama', 'Juan', 'Saamrit', 'Zahir', 'Ange', 'Rohil', 'Chirayu', 'Amil', 'Fano', 'Sai'),
    2023: ('Sama', 'Amil', 'Ange', 'Zahir', 'Saamrit', 'Chirayu', 'Fano', 'Juan', 'Rohil', 'Sai'),
    2024: ('Ange', 'Zahir', 'Saamrit', 'Sama', 'Amil', 'Juan', 'Rohil', 'Fano', 'Sai', 'Chirayu'),
    2025: ('Juan', 'Amil', 'Sai', 'Sama', 'Rohil', 'Ange', 'Fano', 'Saamrit', 'Chirayu', 'Zahir')
}

weekCountDict = {
    2019:20,
    2020:18,
    2021:18,
    2022:18,
    2023:18,
    2024:18,
    2025:18
}

playoffTeamCount = {
    2019:4,
    2020:0,
    2021:4,
    2022:6,
    2023:6,
    2024:6,
    2025:6
}

playoffWeeks = {year:math.ceil(playoffTeamCount[year]/2) for year in playoffTeamCount}
# print(playoffWeeks)

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
    2025: {1:'Fano', 2:"Saamrit", 3:"Zahir", 4:"Chirayu", 5:"Amil", 6:"Juan", 7:"Sai", 8:"Sama", 9:"Ange", 10:"Rohil"}
    }
for year in yTeamIDs:
    for num in range(1,len(yTeamIDs[year])):
        yTeamIDs[year][yTeamIDs[year].get(num)] = num

yGameIDs = {
    2024:428,
    2025:454
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
gc = gs.service_account("/Users/fano/Library/Caches/JetBrains/PyCharmCE2024.1/demo/PyCharmLearningProject/venv/lib/python3.12/site-packages/gspread/fantasy-goat-306ebfffe1c2.json")

## Spreadsheet Names ##
gDocNames = {
    2019:"ULTRA 18/19 Rankings",
    2020:"19/20 Rankings (The Numbers)",
    2021:"20/21 Rankings (The Numbers)",
    2022:"21/22 Rankings (The Numbers)",
    2023:"ULTRA 22/23 Rankings",
    2024:"23/24 Rankings (The Numbers)",
    2025:"24/25 Rankings (The Numbers)"
}

## are the actual stats the top rows? ##
stat24 = True
stat23 = False
stat22 = False
stat21 = False
stat20 = False
stat19 = True
stat25 = True




