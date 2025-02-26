from constants import *
import csv
from espn_fr.basketball import League
from constants import *
from constants import seasonInfoDict as si
from yfpy_fr import YahooFantasySportsQuery
import pandas as pd
import time

def genWeekStatDict(year, week):
    stats = mainCats
    statDict = {teamName: {} for teamName in si[year]['teams']}

    ## If the year is on ESPN
    if si[year]['is_espn']:
        espnLeague = League(espn_leagueID, year, espn_s2, espn_swid)
        league_data = espnLeague._fetch_league()
        sched = league_data.get("schedule")
        weekSched = sched[(week - 1) * -(-teamCount[year] // 2) : week * -(-teamCount[year] // 2)]
        ## double negative floor division to ceiling divide

        for matchup in weekSched:
            try:
                team1 = espnTeamIDs.get(year).get(matchup.get('home').get('teamId'))
                team2 = espnTeamIDs.get(year).get(matchup.get('away').get('teamId'))
                for stat in stats:
                    statDict[team1][stat] = (matchup.get('home').get('cumulativeScore').get('scoreByStat').
                        get(espnStatMap.get(stat)).get('score'))

                    statDict[team2][stat] = (matchup.get('away').get('cumulativeScore').get('scoreByStat').
                                             get(espnStatMap.get(stat)).get('score'))

                statDict[team1]['Opp'], statDict[team2]['Opp'] = team2, team1
            except:
                pass
            # if team2 != 'BYE':

    ## If season is Yahoo
    else:
        yQuery = YahooFantasySportsQuery('', yLeagueIDs[year], 'nba', yGameIDs[year], False, False, yKey, ySec)

        matchupListCopy = yQuery.get_league_matchups_by_week(week)
        team_stats = yQuery.get_all_team_stats_by_week(week)

        for matchup in matchupListCopy:
            matchup_teams = matchup.teams

            team1_id = matchup_teams[0].team_id
            team2_id = matchup_teams[1].team_id

            team1 = yTeamIDs[year].get(team1_id)
            team2 = yTeamIDs[year].get(team2_id)

            teamStat1 = team_stats[team1_id]
            teamStat2 = team_stats[team2_id]

            statDict[team1] = {stat: teamStat1.get(yStatMap.get(stat)) for stat in stats}
            statDict[team2] = {stat: teamStat2.get(yStatMap.get(stat)) for stat in stats}
            statDict[team1]['Opp'], statDict[team2]['Opp'] = team2, team1

    return statDict
def genStatDict(year):
    if year not in si:
        return None
    stats = ['FG%', 'FT%', '3PTM', 'REB', 'AST', 'STL', 'BLK', 'TO', 'PTS', 'FGM', 'FGA', 'FTM', 'FTA', '3PTA', '3PT%']

    ## If the year was on ESPN
    if si[year]["is_espn"]:
        espnLeague = League(espn_leagueID, year, espn_s2, espn_swid)
        league_data = espnLeague._fetch_league()
        sched = league_data.get("schedule")

        statDict = {week:{} for week in range(1,weekCountDict[year] + playoffWeeks[year] + 1)}
        # if year == 2020:
        #     statDict = {week: {} for week in range(1, 21)}
        for matchup in sched:
            try:
                team1 = espnTeamIDs.get(year).get(matchup.get('home').get('teamId'))
                team2 = espnTeamIDs.get(year).get(matchup.get('away').get('teamId'))

            except:
                team1 = espnTeamIDs.get(year).get(matchup.get('home').get('teamId'))
                team2 = "BYE"

            week = matchup.get('matchupPeriodId')
            if week > weekCountDict[year] + playoffWeeks[year]:
                break
            statDict[week][team1] = {'Opp':team2}
            statDict[week][team2] = {'Opp':team1}

            for stat in stats:
                try:
                    statDict[week][team1][stat] = matchup.get('home').get('cumulativeScore').get('scoreByStat').get(espnStatMap.get(stat)).get('score')
                except AttributeError:
                    pass
                try:
                    statDict[week][team2][stat] = matchup.get('away').get('cumulativeScore').get('scoreByStat').get(espnStatMap.get(stat)).get('score')
                except:
                    # print(f"team2: {team2}, stat: {stat}")
                    pass

    ## If the year was on Yahoo
    else:
        yQuery = YahooFantasySportsQuery('',str(yLeagueIDs[year]),'nba',yGameIDs[year],False,False,yKey,ySec)
        mWeeks = yQuery.get_league_info().current_week
        statDict = {}

        for week in range(1,mWeeks+1):

            statDict[week] = {}

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

                statDict[week][team1] = statDict1
                statDict[week][team2] = statDict2

    return statDict

def genStatList(year, extStatDict = None):
    if year not in si:
        return None
    csvList = []
    stats = ['FG%', 'FT%', '3PTM', 'REB', 'AST', 'STL', 'BLK', 'TO', 'PTS', 'FGM', 'FGA', 'FTM', 'FTA', '3PTA', '3PT%']
    statDict = extStatDict if extStatDict else genStatDict(year)

    for week in statDict:
        try:
            weekName = f"M{week}" if week <= weekCountDict[year] else f"P{week % weekCountDict[year]}"
            reg = 'RS' if week <= weekCountDict[year] else 'PO'
            for team in statDict[week]:
                count = False if statDict[week][team]['Opp'] == 'BYE' or team == 'BYE' else True
                statLine = [statDict[week][team].get(stat,"") for stat in stats]
                infoLine = [year, week, weekName, reg, count, team, statDict[week][team]['Opp']]
                csvList.append(infoLine+statLine)
        except KeyError: #current week is not up to end of season
            break

    return csvList

def genStatCSV(year, extStatList=[]):
    stats = statCats
    print(f"\nGenerating stats for all teams from the {year - 1}/{year} season")

    pathname = f"/Users/fano/Documents/Fantasy/Fantasy GOAT/ref/{year}_CompStats.csv"

    statList = extStatList if len(extStatList)>0 else genStatList(year)

    with open(pathname, 'w') as csvfile:
        header = ['Year', 'Week', 'Week Name', 'Season', 'Count', 'Team', 'Opp'] + stats
        # header.extend(stats)
        writer = csv.writer(csvfile)
        writer.writerow(header)
        writer.writerows(statList)

def genStatDF(year, extStatList=None):
    if year not in si:
        return None

    if extStatList:
        print(f"making df out of existing list")
        # startTime = time.time()
        data = extStatList
        cols = ['Year', 'Week', 'Week Name', 'Season', 'Count', 'Team', 'Opp'] + statCats
        stat_df = pd.DataFrame(data, columns=cols)
        # print(f"finished df out of list: took {time.time() - startTime}s")

    else:
        try:
            csv_path = f"/Users/fano/Documents/Fantasy/Fantasy GOAT/ref/{year}_CompStats.csv"
            stat_df = pd.read_csv(csv_path)
        except FileNotFoundError:
            print(f"Generating {year} DF from scratch...may take some time")
            statList = genStatList(year, year)
            data = statList
            cols = ['Year', 'Week', 'Week Name', 'Season', 'Count', 'Team', 'Opp']+statCats
            stat_df = pd.DataFrame(data, columns=cols)

    stat_df = stat_df[~((stat_df['Team'] == 'BYE') | (stat_df['Opp'] == 'BYE'))]
    return stat_df

if __name__ == '__main__':
    year = 2019

    genStatCSV(year)




