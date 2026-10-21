import os
import sys

REPO_ROOT = os.path.abspath(os.path.dirname(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from constants import *
import csv
from espn_fr.basketball import League
from constants import *
from constants import seasonInfoDict as si
from yfpy_fr import YahooFantasySportsQuery
import pandas as pd
import time
from shared.runtime_config import comp_stats_csv_path

def _apply_replacement_stats_for_week(stat_dict, year, week, stat_keys):
    if not replacement_stats:
        return
    for entry in replacement_stats:
        if entry.get("year") != year or entry.get("week") != week:
            continue
        team = entry.get("team")
        if not team or team not in stat_dict:
            continue
        for stat in stat_keys:
            if stat in entry:
                stat_dict[team][stat] = entry[stat]


def _apply_replacement_stats_all(stat_dict, year, stat_keys):
    if not replacement_stats:
        return
    for entry in replacement_stats:
        if entry.get("year") != year:
            continue
        week = entry.get("week")
        team = entry.get("team")
        if week is None or not team:
            continue
        week_dict = stat_dict.get(week)
        if not week_dict or team not in week_dict:
            continue
        for stat in stat_keys:
            if stat in entry:
                week_dict[team][stat] = entry[stat]

def genWeekStatDict(year, week):
    if year not in si:
        print("Invalid Year")
        return None
    statDict = {teamName: {} for teamName in si[year]['teams']}

    ## If the year is on ESPN
    if si[year]['is_espn']:
        espnLeague = League(espnLeagueIDs[year], year, espn_s2, espn_swid)
        league_data = espnLeague._fetch_league()
        sched = league_data.get("schedule")
        weekSched = sched[(week - 1) * -(-teamCount[year] // 2) : week * -(-teamCount[year] // 2)]
        ## double negative floor division to ceiling divide

        for matchup in weekSched:
            try:
                team1 = espnTeamIDs.get(year).get(matchup.get('home').get('teamId'))
                team2 = espnTeamIDs.get(year).get(matchup.get('away').get('teamId'))
                for stat in mainCats:
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

            statDict[team1] = {stat: teamStat1.get(yStatMap.get(stat)) for stat in mainCats}
            statDict[team2] = {stat: teamStat2.get(yStatMap.get(stat)) for stat in mainCats}
            statDict[team1]['Opp'], statDict[team2]['Opp'] = team2, team1

    _apply_replacement_stats_for_week(statDict, year, week, mainCats)
    return statDict
def genStatDict(year):
    if year not in si:
        print("Invalid Year")
        return None

    ## If the year was on ESPN
    if si[year]["is_espn"]:
        espnLeague = League(espnLeagueIDs[year], year, espn_s2, espn_swid)
        league_data = espnLeague._fetch_league()
        sched = league_data.get("schedule")

        statDict = {week:{} for week in range(1, RS_weekCountDict[year] + playoffRounds[year] + 1)}
        for matchup in sched:
            try:
                team1 = espnTeamIDs.get(year).get(matchup.get('home').get('teamId'))
                team2 = espnTeamIDs.get(year).get(matchup.get('away').get('teamId'))

            except:
                team1 = espnTeamIDs.get(year).get(matchup.get('home').get('teamId'))
                team2 = "BYE"

            week = matchup.get('matchupPeriodId')
            if week > RS_weekCountDict[year] + playoffRounds[year]:
                break
            statDict[week][team1] = {'Opp':team2}
            statDict[week][team2] = {'Opp':team1}

            for stat in statCats:
                try:
                    statDict[week][team1][stat] = (matchup.get('home').get('cumulativeScore')
                                                   .get('scoreByStat').get(espnStatMap.get(stat)).get('score'))
                except AttributeError:
                    pass
                try:
                    statDict[week][team2][stat] = (matchup.get('away').get('cumulativeScore')
                                                   .get('scoreByStat').get(espnStatMap.get(stat)).get('score'))
                except:
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

    _apply_replacement_stats_all(statDict, year, statCats)
    return statDict

def genStatList(year, extStatDict = None):
    if year not in si:
        print("Invalid Year")
        return None
    csvList = []
    statDict = extStatDict if extStatDict else genStatDict(year)

    for week in statDict:
        try:
            weekName = f"M{week}" if week <= RS_weekCountDict[year] else f"P{week % RS_weekCountDict[year]}"
            reg = 'RS' if week <= RS_weekCountDict[year] else 'PO'
            for team in statDict[week]:
                count = False if statDict[week][team]['Opp'] == 'BYE' or team == 'BYE' else True
                statLine = [statDict[week][team].get(stat,"") for stat in statCats]
                infoLine = [year, week, weekName, reg, count, team, statDict[week][team]['Opp']]
                csvList.append(infoLine+statLine)
        except KeyError: #current week is not up to end of season
            break

    return csvList

def genStatCSV(year, extStatList=[]):
    print(f"\nGenerating stats for all teams from the {year - 1}/{year} season")

    pathname = comp_stats_csv_path(year)

    statList = extStatList if len(extStatList)>0 else genStatList(year)

    with open(pathname, 'w') as csvfile:
        header = ['Year', 'Week', 'Week Name', 'Season', 'Count', 'Team', 'Opp'] + statCats
        writer = csv.writer(csvfile)
        writer.writerow(header)
        writer.writerows(statList)

def updateStatCSV(year, startWeek = 0, endWeek = 0, extStatList = []):
    if year not in si:
        print("Invalid Year")
        return None

    pathname = comp_stats_csv_path(year)
    try:
        with (open(pathname, 'r') as csvfile):
            csvList = list(csv.reader(csvfile))
            if not csvList:
                # Empty file (a prior run crashed mid-write, or got
                # truncated by something external) -- same recovery path
                # as a missing file below. Without this, every retry hits
                # csvList[-1] on an empty list, which raises IndexError
                # forever: the file never gets rewritten because nothing
                # ever reaches the write below it. Confirmed this exact
                # loop in production (2026 CompStats went empty 2026-10-14,
                # stayed empty until manually rebuilt two days later).
                raise FileNotFoundError(f"{pathname} exists but is empty")
            if startWeek <= 0:
                # NOT simply the last row's week -- a season onboarded with
                # its full future schedule pre-seeded (e.g. 2027: every RS
                # week's matchups were written up front as blank-stat
                # placeholder rows, not built up incrementally the way
                # 2019-2026 were) has a last row week far beyond anything
                # actually played yet. Trusting it outright set startWeek
                # past maxWeek every single run, so this returned None
                # before ever fetching -- confirmed live: 2027_CompStats.csv
                # sat untouched since onboarding while the game-hours loop
                # "succeeded" every 2 minutes doing nothing. Use the last
                # week that actually has a recorded PTS value instead
                # (column 15); none yet (brand new season) -> week 1.
                real_weeks = [int(row[1]) for row in csvList[1:] if len(row) > 15 and row[15] != ""]
                startWeek = max(real_weeks) if real_weeks else 1
            # Default behavior: refresh through current detected week.
            # If caller provides endWeek explicitly, honor it (used by manual forced refresh).
            maxWeek = getLastWeek(year) if endWeek <= 0 else endWeek

        # Avoid destructive truncation when caller asks for a past week and file already
        # has newer rows (e.g., startWeek > maxWeek). In that case there is nothing to fetch.
        if startWeek > maxWeek:
            return None

        if si[year]['is_espn']:
            espnLeague = League(espnLeagueIDs[year], year, espn_s2, espn_swid)
            league_data = espnLeague._fetch_league()
            sched = league_data.get("schedule")
            weekSched = sched[(startWeek - 1) * -(-teamCount[year] // 2):] ## double negative floor division to ceiling divide

            statDict = {week: {} for week in range(startWeek, maxWeek + 1)}
            for matchup in weekSched:
                try:
                    team1 = espnTeamIDs.get(year).get(matchup.get('home').get('teamId'))
                    team2 = espnTeamIDs.get(year).get(matchup.get('away').get('teamId'))

                except:
                    team1 = espnTeamIDs.get(year).get(matchup.get('home').get('teamId'))
                    team2 = "BYE"

                week = matchup.get('matchupPeriodId')
                if week > RS_weekCountDict[year] + playoffRounds[year]:
                    break
                statDict[week][team1] = {'Opp': team2}
                statDict[week][team2] = {'Opp': team1}

                for stat in statCats:
                    try:
                        statDict[week][team1][stat] = (matchup.get('home').get('cumulativeScore')
                                                       .get('scoreByStat').get(espnStatMap.get(stat)).get('score'))
                    except AttributeError:
                        pass
                    try:
                        statDict[week][team2][stat] = (matchup.get('away').get('cumulativeScore')
                                                       .get('scoreByStat').get(espnStatMap.get(stat)).get('score'))
                    except:
                        pass

        else: ## If season is Yahoo
            yQuery = YahooFantasySportsQuery('', str(yLeagueIDs[year]), 'nba', yGameIDs[year], False, False, yKey, ySec)
            statDict = {}

            for week in range(startWeek, maxWeek+1):
                statDict[week] = {}
                matchupList = yQuery.get_league_matchups_by_week(week)
                team_stats = yQuery.get_all_team_stats_by_week(week)

                for matchup in matchupList:

                    matchup_teams = matchup.teams

                    team1_id = matchup_teams[0].team_id
                    team2_id = matchup_teams[1].team_id

                    team1 = yTeamIDs[year].get(team1_id)
                    team2 = yTeamIDs[year].get(team2_id)

                    statDict1 = {'Opp': team2}
                    statDict2 = {'Opp': team1}

                    teamStat1 = team_stats[team1_id]
                    teamStat2 = team_stats[team2_id]

                    for stat in statCats:
                        statDict1[stat] = teamStat1.get(yStatMap.get(stat))
                        statDict2[stat] = teamStat2.get(yStatMap.get(stat))

                    statDict[week][team1] = statDict1
                    statDict[week][team2] = statDict2

        _apply_replacement_stats_all(statDict, year, statCats)
        rowsPerWeek = 2*-(-teamCount[year] // 2)
        lastRow = 0 + rowsPerWeek * (startWeek-1)
        # Preserve any pre-seeded rows for weeks AFTER maxWeek (e.g. 2027's
        # full-season placeholder rows written at onboarding -- see the
        # startWeek-detection comment above) instead of silently dropping
        # them. Only the startWeek..maxWeek range being refetched below
        # should actually be replaced.
        futureRows = csvList[1 + rowsPerWeek*maxWeek:]
        row = lastRow
        csvList = csvList[:lastRow+1]
        for week in statDict:
            weekName = f"M{week}" if week <= RS_weekCountDict[year] else f"P{week % RS_weekCountDict[year]}"
            reg = 'RS' if week <= RS_weekCountDict[year] else 'PO'
            for team in statDict[week]:
                count = False if statDict[week][team]['Opp'] == 'BYE' or team == 'BYE' else True
                statLine = [statDict[week][team].get(stat, "") for stat in statCats]
                infoLine = [year, week, weekName, reg, count, team, statDict[week][team]['Opp']]
                csvList.append(infoLine + statLine)
        csvList.extend(futureRows)

        with open(pathname, 'w') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerows(csvList)

    except FileNotFoundError:
        genStatCSV(year, extStatList)
        return None

def genStatDF(year, extStatList=None):
    if year not in si:
        return None

    if extStatList:
        # print(f"making df out of existing list")
        # startTime = time.time()
        data = extStatList
        cols = ['Year', 'Week', 'Week Name', 'Season', 'Count', 'Team', 'Opp'] + statCats
        stat_df = pd.DataFrame(data, columns=cols)
        # print(f"finished df out of list: took {time.time() - startTime}s")

    else:
        try:
            csv_path = comp_stats_csv_path(year)
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
    year = currentYear

    genStatCSV(year)

    updateStatCSV(year)
