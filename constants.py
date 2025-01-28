import gspread as gs
import math
from espn_fr.basketball.constant import STATS_MAP


## ESPN league/login info
espn_leagueID = 82864377
espn_s2 = 'AEB10E76tw6SHjpKpDqw7nBJndJfFekcJaC%2FiUC0JrJ2wj1Nb5YcBVZ04ary1%2F%2FEiiqzXaA1UPb0CcRBu%2FMpigZ%2BX6Hr%2FqD0nan6hZfQok4YHbHuVkIAVHzfUnJ%2FLDPNMqtIcS8ZmhAFVwW62RM6HlhFSk1DZz6z29J0TZjioAkFhYwVDaf6ILm%2FrtaSTeBSPwdSOqxxyd%2F%2FzlZwt1avKDdP0fLxEytLrCGjtUpd8LANz6kvqXLgUBjRCz0YBrKbYlfzkc6zhmt2Fx%2Fncfcoi5eEOZbTPlFJRG%2B2k6Qw079Z7g%3D%3D'
espn_swid = '{F1B30D95-9F03-4CA9-BE62-D89858BE885E}'

## Yahoo league/login info
yKey = "dj0yJmk9S0hLcFVjVVZtd2ZMJmQ9WVdrOWVqUk9XazV4YW1zbWNHbzlNQT09JnM9Y29uc3VtZXJzZWNyZXQmc3Y9MCZ4PTQ3"
ySec = "f98bfdf3286771e0b58de7b4062a59b0f867f467"
yTok = "uB0jRRyZ51jlQNiz47T97fln1VPV73fMQHr6EiZOLHq31g20X4pPKGU8dS4vAuDfRV1L1jWSvtuI57mrYF5Gvj1C75qjhbv4yjtrICnLapQ7IqnpjS1cdqXzhK2PG.EeRBAHBt0qE29gg6lUqX5HPFD0IddWjj6PEmbB8tZkJRfEefC1R8uvcyu97E545TbBaR8Aox1FGxReq6IVe_q4knZJ1vJVSxMY2xPgZNT6YrD.DK1vNakcsWys8FSPjOpGt0CdxSntrBXCOmENcjjPjbX7x47MHU1zckZoxmulP312SlcyrOYGZm3Ut5TZVL9dQM9BdAyFXzRkxnVPH0qdt6N1GuuSJ.RdNoTtku7Y5sL_ow..JtrwcXCm05zxsjx9wnyx9Cy_GGUc5EQqfY87a8GwBQN4I3zG2OkYAk7DsA9DFHq5mOTHxazAaTHem2YRaECRr9yxlRckzkcanjXl4Jwb_dvJxaPlXiq2ULhEJj0PGFulmgrpcIkemZL5cjDOYbjL99cSrtsIElNlUDihAgo7jvNflaYoQDSVqYdusIOn1eCjknFv_B72xGyjH9mwjr.mFKSN1GmG7lpBTJjLzAWt9DW6EhoPWI.4Im4Z5dllgTBTrpvy3Bw8CEff0pwhYIMJcx8VoX2m4P8GtR9bDHyMay6ltiurCdOi4C4TkKyCXmb_Svt3p4kpIxjABYK.LIUKC3mktTWMs2dhRUYdfENiZyVI.8SJZlkHp2B9rmgv3e2BLHILKqeZt4bh7cuggPMOpLKUcmwhqGotsBXD1gknm2prbQ5jcTPvT5HE2YKkk4gM3xZPpxs4q8gz3U98ugiH5B1swIyCB4hBHDmPGJ05RtntSYs4Z_FKoumR4j7jKmlLpd4kjuAumHz5LPFx.XEqILuabedRdTBvYA2BNteGtIMCDzfZxszEJMDTm2KaBYclZLLSCXZrl0JNPCGmT889BOK6W7Wu0BaVsALsM8aNSQBZyLeKV3uCa0K7REczBKZ1nRUacU8-"
yRefTok = 'AFRlfGYz42hqZri9tJIlY6d1og_S~000~bkow8_Z7ijMknqCgEQhHIinloToXvkYm'

yLeagueIDs = {
    2024:138772,
    2025:29987
}

currentYear = 2025

## ALL MEMBERS EVER
allMembers = sorted(['Jesse', 'Ange', 'Juan', 'Saamrit', 'Rohil', 'Chirayu', 'Fano', 'Zahir', 'Amil', 'Sama', 'Sai'])
abbMembers = {member:
    member[:2] if member.startswith('A') else
    member[:3] if member.startswith('S') else
    member[0] for member in allMembers
}

mainCats = ['FG%', 'FT%', '3PTM', 'REB', 'AST', 'STL', 'BLK', 'TO', 'PTS']
statCats = ['FG%', 'FT%', '3PTM', 'REB', 'AST', 'STL', 'BLK', 'TO', 'PTS', 'FGM', 'FGA', 'FTM', 'FTA', '3PTA', '3PT%']

## season info dict has tuple as value for each key
## each tuple will contain ((team1, team2, ...), is ESPN (T/F), is W/L scoring (T/F))
seasonInfo = {
    2019: (sorted(('Jesse', 'Ange', 'Juan', 'Saamrit', 'Rohil', 'Chirayu', 'Fano', 'Zahir')),True,True),
    2020: (sorted(('Jesse', 'Ange', 'Juan', 'Sama', 'Saamrit', 'Rohil', 'Chirayu', 'Fano', 'Zahir')),True,True),
    2021: (sorted(('Amil', 'Ange', 'Juan', 'Sama', 'Saamrit', 'Rohil', 'Chirayu', 'Fano', 'Zahir')),True,True),
    2022: (sorted(('Amil', 'Ange', 'Juan', 'Sama', 'Saamrit', 'Rohil', 'Chirayu', 'Fano', 'Zahir', 'Sai')),True,True),
    2023: (sorted(('Amil', 'Ange', 'Juan', 'Sama', 'Saamrit', 'Rohil', 'Chirayu', 'Fano', 'Zahir', 'Sai')),True,True),
    2024: (sorted(('Amil', 'Ange', 'Juan', 'Sama', 'Saamrit', 'Rohil', 'Chirayu', 'Fano', 'Zahir', 'Sai')),False,False),
    2025: (sorted(('Amil', 'Ange', 'Juan', 'Sama', 'Saamrit', 'Rohil', 'Chirayu', 'Fano', 'Zahir', 'Sai')),False,True)
}

# was too lazy to rewrite seasonInfo as a dict
seasonInfoDict = {
    year: {'teams': seasonInfo[year][0], 'is_espn': seasonInfo[year][1], 'is_WL': seasonInfo[year][1]} for year in seasonInfo
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
gc = gs.service_account(
        "/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/site-packages/gspread/fantasy-goat-306ebfffe1c2.json"
    )

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




