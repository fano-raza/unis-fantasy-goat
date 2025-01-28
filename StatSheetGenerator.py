from constants import *
import csv
from espn_fr.basketball import League
from constants import *
from yfpy_fr import YahooFantasySportsQuery

def genStatDict(startYear, endYear=0):
    if endYear==0:
        endYear = startYear
    allStatDict = {year:{} for year in range(startYear, endYear+1)}
    stats = ['FG%', 'FT%', '3PTM', 'REB', 'AST', 'STL', 'BLK', 'TO', 'PTS', 'FGM', 'FGA', 'FTM', 'FTA', '3PTA', '3PT%']

    for year in range(startYear,endYear+1):

        ## If the year was on ESPN
        if seasonInfo[year][1]:
            espnLeague = League(espn_leagueID, year, espn_s2, espn_swid)
            league_data = espnLeague._fetch_league()
            sched = league_data.get("schedule")

            allStatDict[year] = {week:{} for week in range(1,weekCountDict[year] + playoffWeeks[year] + 1)}
            if year == 2020:
                allStatDict[year] = {week: {} for week in range(1, 21)}
            for matchup in sched:
                try:
                    team1 = espnTeamIDs.get(year).get(matchup.get('home').get('teamId'))
                    team2 = espnTeamIDs.get(year).get(matchup.get('away').get('teamId'))

                except:
                    team1 = espnTeamIDs.get(year).get(matchup.get('home').get('teamId'))
                    team2 = "BYE"

                week = matchup.get('matchupPeriodId')
                allStatDict[year][week][team1] = {'Opp':team2}
                allStatDict[year][week][team2] = {'Opp':team1}

                for stat in stats:
                    try:
                        allStatDict[year][week][team1][stat] = matchup.get('home').get('cumulativeScore').get('scoreByStat').get(espnStatMap.get(stat)).get('score')
                        # line1.append(matchup.get('home').get('cumulativeScore').get('scoreByStat').get(espnStatMap.get(stat)).get('score'))
                    except:
                        # print(f"team1: {team1}, stat: {stat}")
                        pass
                    try:
                        allStatDict[year][week][team2][stat] = matchup.get('away').get('cumulativeScore').get('scoreByStat').get(espnStatMap.get(stat)).get('score')
                    except:
                        # print(f"team2: {team2}, stat: {stat}")
                        pass

        ## If the year was on Yahoo
        else:
            yQuery = YahooFantasySportsQuery('',str(yLeagueIDs[year]),'nba',yGameIDs[year],False,False,yKey,ySec)
            mWeeks = yQuery.get_league_info().current_week

            for week in range(1,mWeeks+1):

                allStatDict[year][week] = {}

                matchupList = yQuery.get_league_matchups_by_week(week)
                team_stats = yQuery.get_all_team_stats_by_week(week)

                for matchup in matchupList:

                    matchup_teams = matchup.teams

                    team1_id = matchup_teams[0].team_id
                    team2_id = matchup_teams[1].team_id

                    team1 = yTeamIDs[year].get(team1_id)
                    team2 = yTeamIDs[year].get(team2_id)

                    statDict1 = {'Opp':team2}
                    statDict2 = {'Opp':team1}

                    teamStat1 = team_stats[team1_id]
                    teamStat2 = team_stats[team2_id]

                    for stat in statCats:
                        statDict1[stat] = teamStat1.get(yStatMap.get(stat))
                        statDict2[stat] = teamStat2.get(yStatMap.get(stat))

                    allStatDict[year][week][team1] = statDict1
                    allStatDict[year][week][team2] = statDict2

    return allStatDict

def genStatList(startYear, endYear):
    if endYear==0:
        endYear = startYear
    csvList = []
    stats = ['FG%', 'FT%', '3PTM', 'REB', 'AST', 'STL', 'BLK', 'TO', 'PTS', 'FGM', 'FGA', 'FTM', 'FTA', '3PTA', '3PT%']
    statDict = genStatDict(startYear, endYear)

    for year in statDict:
        for week in statDict[year]:
            weekName = f"M{week}" if week <= weekCountDict[year] else f"P{week % weekCountDict[year]}"
            reg = 'RS' if week <= weekCountDict[year] else 'PO'
            for team in statDict[year][week]:
                count = False if statDict[year][week][team]['Opp'] == 'BYE' or team == 'BYE' else True
                statLine = [statDict[year][week][team].get(stat,"") for stat in stats]
                infoLine = [year, week, weekName, reg, count, team, statDict[year][week][team]['Opp']]
                csvList.append(infoLine+statLine)

    return csvList

if __name__ == '__main__':
    startYear = 2025
    endYear = 2025
    stats = ['FG%', 'FT%', '3PTM', 'REB', 'AST', 'STL', 'BLK', 'TO', 'PTS', 'FGM', 'FGA', 'FTM', 'FTA', '3PTA', '3PT%']

    print(f"\nGenerating stats for all players from the {startYear - 1}/{startYear} season\n"
          f"to the {endYear - 1}/{endYear} season...")

    pathname = f"/Users/fano/Documents/Fantasy/Fantasy GOAT/ref/{startYear}_to_{endYear}_CompStats.csv" if startYear != endYear \
        else f"/Users/fano/Documents/Fantasy/Fantasy GOAT/ref/{startYear}_CompStats.csv"

    statList = genStatList(startYear, endYear)

    with open(pathname, 'w') as csvfile:
        header = ['Year', 'Week', 'Week Name', 'Season', 'Count', 'Team', 'Opp']+stats
        # header.extend(stats)
        writer = csv.writer(csvfile)
        writer.writerow(header)
        writer.writerows(statList)




