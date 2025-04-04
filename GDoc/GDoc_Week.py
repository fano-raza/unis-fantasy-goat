# import csv
# from espn_fr.basketball import League
# from yfpy_fr import YahooFantasySportsQuery
# from constants import *
# import datetime
# import time
import sys
import os
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(parent_dir)

from Models.seasons import *

def genWeekStats(year, week):
    stats = gDocStatCats
    statList = []

    ## If the year is on ESPN
    if seasonInfo[year][1]:
        espnLeague = League(espn_leagueID, year, espn_s2, espn_swid)
        league_data = espnLeague._fetch_league()
        sched = league_data.get("schedule")

        for matchup in sched[(week-1)*(teamCount[year]-teamCount[year]%2)//2:week*(teamCount[year]-teamCount[year]%2)//2]:
            try:
                line1 = [espnTeamIDs.get(year).get(matchup.get('home').get('teamId'))]
                line2 = [espnTeamIDs.get(year).get(matchup.get('away').get('teamId'))]

                for stat in stats:
                    line1.append(
                        matchup.get('home').get('cumulativeScore').get('scoreByStat').get(espnStatMap.get(stat)).get(
                            'score'))
                    line2.append(
                        matchup.get('away').get('cumulativeScore').get('scoreByStat').get(espnStatMap.get(stat)).get(
                            'score'))
                statList.append(line1)
                statList.append(line2)
            except:
                pass
            # if team2 != 'BYE':

    ## If season is Yahoo
    else:
        yQuery = YahooFantasySportsQuery('',yLeagueIDs[year],'nba',yGameIDs[year],False,False,yKey,ySec)

        matchupListCopy = yQuery.get_league_matchups_by_week(week)
        team_stats = yQuery.get_all_team_stats_by_week(week)

        for team_id in team_stats:
            team = yTeamIDs[year].get(team_id)
            teamStat = team_stats[team_id]
            statDict = {stat: teamStat.get(yStatMap.get(stat)) for stat in statCats}
            line = [team]+[statDict.get(stat) for stat in stats]
            statList.append(line)

    return statList

def nthLetter(n):
    if 1 <= n <= 26:
        return chr(ord('A') + n - 1)
    else:
        print("Invalid input. Please enter a number between 1 and 26.")


def write_gDoc_stats(year, week):
    worksheet = gc.open(gDocNames[year]).worksheet(f"M{week}")

    statUpdate = genWeekStats(year, week)
    firstRow = 7
    worksheet.update(statUpdate,f"A{firstRow}:J{firstRow+(teamCount[year]-teamCount[year]%2)-1}")

    writeUpdateTime(year, week, "L2")

def writeUpdateTime(year, week, cell):
    now = datetime.datetime.now()
    displayTime = f"{now.month}/{now.day}/{now.year - 2000} {now.hour}:{now.minute:02}"

    write_gDoc(year, week, f"UPDATED {displayTime}", cell, bold=True)

def genSched(year):
    teams = sorted(seasonInfo[year][0])
    schedule = []
    ## if is_espn is true
    if seasonInfo[year][1]:
        espnLeague = League(espn_leagueID, year, espn_s2, espn_swid)
        league_data = espnLeague._fetch_league()
        sched = league_data.get("schedule")

        for week in range(weekCountDict[year]):
            Opps = {}
            for matchup in sched[(week - 1)*len(seasonInfo[year][0])//2:week*len(seasonInfo[year][0])//2]:
                try:
                    team1 = espnTeamIDs.get(year).get(matchup.get('home').get('teamId'))
                    team2 = espnTeamIDs.get(year).get(matchup.get('away').get('teamId'))

                    Opps[team1] = team2
                    Opps[team2] = team1
                except:
                    pass
            line = [Opps[team] for team in teams]
            schedule.append(line)
    else:
        yQuery = YahooFantasySportsQuery('',yLeagueIDs[year],'nba',yGameIDs[year],False,False,yKey,ySec)
        for week in range(1,weekCountDict[year]+1):
            matchupListCopy = yQuery.get_league_matchups_by_week(week).copy()
            Opps={}
            for matchup in matchupListCopy:

                matchup_teams = matchup.teams.copy()

                team1_id = matchup_teams[0].team_id
                team2_id = matchup_teams[1].team_id

                team1 = yTeamIDs[year].get(team1_id)
                team2 = yTeamIDs[year].get(team2_id)

                Opps[team1]=team2
                Opps[team2]=team1

            line = [Opps[team] for team in teams]
            schedule.append(line)

    worksheet = gc.open(gDocNames[year]).worksheet(f"Matchups")

    worksheet.update(teams, f"B1:K1")
    worksheet.update(schedule, f"B{2+weekCountDict[year]+3}:K{2+2*weekCountDict[year]+2}")

def createWeekSheet(year, week, copy = 1):
    sheet = gc.open(gDocNames[year])
    worksheet_to_copy = gc.open(gDocNames[year]).worksheet(f"M{copy}")
    worksheet_to_copy.duplicate(insert_sheet_index = week+1, new_sheet_name=f"M{week}")

def write_gDoc(year, week, text, cell, bold = False, italic = False, underline = False):
    worksheet = gc.open(gDocNames[year]).worksheet(f"M{week}")

    worksheet.update([[text],[""]], f"{cell}:{cell[0]}{int(cell[1])+1}")
    worksheet.format(cell, {"textFormat":{
        'bold':bold,
        'italic':italic,
        'underline':underline
    },
    "horizontalAlignment": "CENTER"
    })

def makeRestOfSheets(year, startWeek = 1):
    endWeek = weekCountDict[year] + playoffRounds[year]
    week = startWeek

    while week <= endWeek:
        try:
            createWeekSheet(year, week)
            write_gDoc_stats(year, week)
            week += 1
        except: ## Most errors will be that the API read request/min limit has been reached.
            print("Waiting on Google Docs")
            time.sleep(5)

def updateCurrentSheet(year):
    calPath = f"/Users/fano/Documents/Fantasy/Fantasy GOAT/{year}/{year}_matchup_cal.csv"
    with open(calPath, 'r') as csvfile:
        reader = csv.reader(csvfile, delimiter=',')
        next(reader)
        calList = [[int(week[0]), datetime.date(int(week[1]), int(week[2]), int(week[3])),
                    datetime.date(int(week[4]), int(week[5]), int(week[6]))]
                   for week in reader]
    today = datetime.date.today()
    currentWeek = bs_calList(today, calList)

    write_gDoc_stats(year, currentWeek)

def updateStandings(year, extSeason = None):
    worksheet = gc.open(gDocNames[year]).worksheet(f"Overall Rank")

    season = regSeason(year) if not extSeason else extSeason
    WL_standings = season.get_WL_standings()
    cat_standings = season.get_Cats_standings()

    replacements = str.maketrans({"W":"",
                                  "L":"",
                                  "D":""})

    WL_standings_list = [[place, WL_standings[place][0], WL_standings[place][1].translate(replacements)] for place in WL_standings]
    cat_standings_list = [[place, cat_standings[place][0], cat_standings[place][1].translate(replacements)] for place in cat_standings]

    worksheet.update(WL_standings_list, f"A32:C41")
    worksheet.update(cat_standings_list, f"F32:H41")

if __name__ == '__main__':
    year = 2025
    week = 21

    # createWeekSheet(year, week)

    write_gDoc_stats(year,week)

    # write_gDoc_sched(year)

    # makeRestOfSheets(year, startWeek=19)

    # updateCurrentSheet(year)

    # genSched(2024)

    # updateStandings(year)



