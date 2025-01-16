import gspread as gs
import numpy as np
import pandas as pd
import csv
from espn_api.basketball.league import League
# from espn_api.basketball.box_score import H2HCategoryBoxScore
from yfpy_fr.query import YahooFantasySportsQuery
from yfpy.models import YahooFantasyObject
from constants import *

# from espn_api.basketball.constant import

## GOOGLE DOCS GOOGLE DOCS GOOGLE DOCS
def gdoc():
    ## gspread account info
    gc = gs.service_account(
        "/Users/fano/Library/Caches/JetBrains/PyCharmCE2024.1/demo/PyCharmLearningProject/venv/lib/python3.12/site-packages/gspread/fantasy-goat-306ebfffe1c2.json")
    test = gc.open("ULTRA 18/19 Rankings")

    ## Fetching data
    # print(test.sheet1.get('A1'))
    # print(test.sheet1.spreadsheet_id)
    # print(test.worksheet("M3").get('F6')[0][0])
    # print(test.worksheet("M3").get('A1:A10'))
    # print(test.worksheet("M3").row_values(8))
    # print(test.worksheet("M3").get_all_values())
    # for week in range(1,19):
    #     print(f"M{week}: {test.worksheet(f"M{week}").get_all_values()}")
    # print(test.worksheet("M3").cell(1,1))
    # print(test.title)
    # print(test.worksheet("M3").batch_get(["A1:J10","A12:J13"]))
    # numpyTest = np.array(test.worksheet("M2").get_all_values())
    # print(numpyTest[0])

    ## Writing data
    test.worksheet("test").update([["hi emilia"] for i in range(10)],"C1:C10")
    # test.worksheet("test").duplicate(insert_sheet_index=1,new_sheet_name="test 2")
    # for i in range(1,21):
    #     test.del_worksheet(test.worksheet(f"M{i}"))

# ## ESPN ESPN ESPN ESPN ESPN
def espn():
    pass
    year = 2021
    espnLeague = League(espn_leagueID, year, espn_s2, espn_swid)

    league_data = espnLeague._fetch_league()
    # for key in league_data:
    #     print(key)

    sched = league_data.get("schedule")
    # print(type(sched))
    # print(len(sched))
    # print(sched[0].get('matchupPeriodId'))
    print(sched[0].get('away').get('cumulativeScore').get('scoreByStat').get)
    # for key in league_data["teams"]:
        # print(key)
    # print(league_data['members'][0])
    # print(league_data['teams'][0])

    # FIGURE OUT ESPN TEAM IDS
    csvList = []
    for year in range(2019,2024):
        espnLeague = League(espn_leagueID, year, espn_s2, espn_swid)
        league_data = espnLeague._fetch_league()
        memberDict = {}
        for member in league_data.get('members'):
            memberDict[member.get('id')] = member.get('firstName')
        print (memberDict)

        for team in league_data['teams']:
            name = team['name']
            abbrev = team['abbrev']
            teamID = team.get('id')
            # ownerCode = str(team.get('owners')[0]) if type(team.get('owners')[0]) is list else team.get('owners')
            print(team.get('owners'))
            try:
                ownerCode = team.get('owners')[0]
            except:
                ownerCode = 'N/A'
            owner = memberDict.get(ownerCode)

            csvList.append([owner, ownerCode, teamID, abbrev, name, year])

    pathname = f"/Users/fano/Documents/Fantasy/Fantasy GOAT/espn team codes.csv"
    with open(pathname, 'w') as csvfile:
        header = ['owner', 'ownerCode', 'teamID', 'abb', 'teamName', 'year']
        writer = csv.writer(csvfile)
        writer.writerow(header)
        writer.writerows(csvList)



    player_map = espnLeague._fetch_players()
    # print(player_map)

    myTeam = espnLeague.teams[0]
    myRoster = myTeam.roster

    player_data = espnLeague.espn_request.get_pro_players()[:400] ## basic player info
    # print(player_data)

    player_test = espnLeague.player_info(player_data[0]['fullName'])

    # print(player_test)
    # print(player_test.rank)

    # player_card_dict = {}
    # for player in player_data:
    #     player_card_dict[player['fullName']] = player
    # print(player_card_dict.get('Zach Randolph'))
    #
    # print(espnLeague.player_map.get('Zach Randolph'))

## YAHOO YAHOO YAHOO
def yahoo():
    year = 2024
    yQuery = YahooFantasySportsQuery('',str(yLeagueIDs[year]),'nba',yGameIDs[year],False,False,yKey,ySec)
    # leagueKey = yQuery.get_league_key()

    # print(yQuery.get_team_stats_by_week(1, 2))

    print(yQuery.get_all_team_stats_by_week(2))

    # LEAGUE_KEY = "428.l.138772"
    # BASE_URL = "https://fantasysports.yahooapis.com/fantasy/v2"
    # TEAM_KEYS = [f"{LEAGUE_KEY}.t.{i}" for i in range(1,4)]
    # WEEK = 1
    # TOKEN = yTok
    #
    # headers = {"Authorization": f"Bearer {TOKEN}"}
    # team_keys = ",".join(TEAM_KEYS)
    # url = f"{BASE_URL}/teams;team_keys={team_keys}/stats;type=week;week={WEEK}?format=json"
    # # url = f"{BASE_URL}/teams;team_keys={TEAM_KEYS[0]}/stats;type=week;week=1,2,3?format=json"
    #
    # response = requests.get(url, headers=headers)
    # if response.status_code == 200:
    #     data = response.json()
    #     # print(response.text)  # Process the response manually
    #     # print(data['fantasy_content']['teams']['0'].keys())
    # else:
    #     print(f"Error: {response.status_code}, {response.text}")

    # print(yQuery.get_league_matchups_by_week(2))
    # print(yQuery.get_league_scoreboard_by_week(1))


    # print(yQuery.get_league_players())
    # print(yQuery.get_league_scoreboard_by_week(2).matchups[1].teams[1])
    # print(yQuery.get_all_yahoo_fantasy_game_keys())
    # for week in range(1,19):
    #     print(yQuery.get_league_matchups_by_week(week))
    # yInfo = yQuery.get_league_info()
    # gameInfo = yQuery.get_current_game_info()

    # csvList = []
    # for week in gameInfo.game_weeks:
    #     startDate = [int(i) for i in week.start.split("-")]
    #     endDate = [int(i) for i in week.end.split("-")]
    #     line = [week.week]+startDate+endDate
    #     csvList.append(line)
    #
    # pathname = f"/Users/fano/Documents/Fantasy/Fantasy GOAT/{year}/{year}_matchup_cal.csv"
    # with open(pathname, 'w') as csvfile:
    #     header = ["week","start year","start mon", "start day", "end year", "end mon", "end day"]
    #     writer = csv.writer(csvfile)
    #     writer.writerow(header)
    #     writer.writerows(csvList)

    # print(type(yInfo))
    # for key in yInfo:
    #     print(key)
    # print(yInfo)
    # print(yQuery.get_league_players())
    # print(yQuery.get_league_matchups_by_week(1))
    # print(yQuery.get_league_draft_results()[55].player_key)
    # print(yQuery.get_player_draft_analysis("428.p.5958"))
    # print(yQuery.get_league_info())

    # yStatMapList = yQuery.get_game_stat_categories_by_game_id('nba').stats
    # yStatMap = {}
    # for stat in yStatMapList:
    #     yStatMap[stat.stat_id] = stat.display_name
    #     yStatMap[stat.display_name] = stat.stat_id
    # print(yStatMap)

    # print(type(yQuery.get_game_stat_categories_by_game_id('nba')))
    # print(yQuery.get_league_scoreboard_by_week(1))
    # print(yQuery.get_team_stats(2))
    # print(yQuery.get_team_matchups(1))
    # yObj = YahooFantasyObject(yQuery.get_team_matchups(1))
    # print(yObj)
    # print(yQuery.get_all_yahoo_fantasy_game_keys())
    # print(yQuery.get_game_stat_categories_by_game_id(428))
    # yQuery.get_league_scoreboard_by_week(1)
    # print(yQuery.get_team_stats(4))

    # team_stat = yQuery.get_team_stats_by_week(4, 20)
    # print(team_stat)
    # for statDict in team_stat:
    #     # print(statDict['stat'].stat_id)
    #     print(statDict['stat'])

    # print(yQuery.get_league_matchups_by_week(3))
    # print(yInfo.current_week)
    # for team in yInfo.teams:
    #     print(f"id: {team.team_id}")
    #     print(f"email: {team.managers[0].email}")
    #     print(f"nickname: {team.managers[0].nickname}")

    # print(yQuery.get_league_matchups_by_week(1))
    # for matchup in yQuery.get_league_matchups_by_week(1):
    #     team1 = matchup.teams[0].team_id

    # print("\nBREAK\nBREAK\nBREAK\n\n")
    # print(yQuery.get_team_stats(1))

    # print(yQuery.test_func(1))



if __name__ == '__main__':
    # gdoc()
    # espn()
    yahoo()