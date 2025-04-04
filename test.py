# from espn_fr.basketball.box_score import H2HCategoryBoxScore
from Models.TeamManager import *
from StatGenerator import *
import time


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
    print(sched)
    # print(len(sched))
    # print(sched[0].get('matchupPeriodId'))
    # print(sched[0].get('away').get('cumulativeScore').get('scoreByStat').get)
    # for key in league_data["teams"]:
        # print(key)
    # print(league_data['members'][0])
    # print(league_data['teams'][0])

    # FIGURE OUT ESPN TEAM IDS
    # csvList = []
    # for year in range(2019,2024):
    #     espnLeague = League(espn_leagueID, year, espn_s2, espn_swid)
    #     league_data = espnLeague._fetch_league()
    #     memberDict = {}
    #     for member in league_data.get('members'):
    #         memberDict[member.get('id')] = member.get('firstName')
    #     print (memberDict)
    #
    #     for team in league_data['teams']:
    #         name = team['name']
    #         abbrev = team['abbrev']
    #         teamID = team.get('id')
    #         # ownerCode = str(team.get('owners')[0]) if type(team.get('owners')[0]) is list else team.get('owners')
    #         print(team.get('owners'))
    #         try:
    #             ownerCode = team.get('owners')[0]
    #         except:
    #             ownerCode = 'N/A'
    #         owner = memberDict.get(ownerCode)
    #
    #         csvList.append([owner, ownerCode, teamID, abbrev, name, year])
    #
    # pathname = f"/Users/fano/Documents/Fantasy/Fantasy GOAT/espn team codes.csv"
    # with open(pathname, 'w') as csvfile:
    #     header = ['owner', 'ownerCode', 'teamID', 'abb', 'teamName', 'year']
    #     writer = csv.writer(csvfile)
    #     writer.writerow(header)
    #     writer.writerows(csvList)



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
    year = 2025
    yQuery = YahooFantasySportsQuery('',str(yLeagueIDs[year]),'nba',yGameIDs[year],False,False,yKey,ySec)
    # print(yQuery.get_all_yahoo_fantasy_game_keys())
    # leagueKey = yQuery.get_league_key()

    team_stats = yQuery.get_all_team_stats_by_week(19)
    print(team_stats)




if __name__ == '__main__':
    # gdoc()
    # espn()
    # yahoo()

    x = teamManager('Fano')
    # print(x.compStatDF.columns)
    # print(x.compStatDF["matchup_length"])
    # print(x.compStatDF.loc[x.compStatDF["real_matchup"]==1][mainCats])
    # print(x.get_filtered_df(years=[2025],RS=False)[mainCats])
    print("df: ", x.get_career_matchups_played_df(RS=True, PO=False))
    print("dict: ", x.get_career_matchups_played(RS=True, PO=False))

    start = time.time()
    # print(x.get_avg_opp_rating(rating='rank'))
    res = x.get_car_opp_records_df(record='record', sortedReturn=False, RS=True, PO=False)
    print(res)
    matches = [sum(team.values()) for team in res.values()]
    print(sum(matches))
    print("df time: ", time.time()-start)

    start = time.time()
    res = x.get_car_opp_records()
    print(res)
    matches = [sum(team.values()) for team in res.values()]
    print(sum(matches))
    print("dict time: ", time.time() - start)

    # a = fantasyLeague()
    # for season in a.seasons:
    #     print(season.regSsn)
    #     print(season.playoffs)
    #     print(season.playoffs.getWinner())

    # x = teamManager('Juan')
    # x.get_career_PO_totals()
    # print(x.career_PO_totals)
    #
    # for playoff in x.playOffs.values():
    #     print(playoff.year, playoff.get_team_PO_totals())

    # y = teamManager('Fano')
    # y.get_career_PO_totals()
    # print(y.career_PO_totals)
    #
    # for playoff in y.playOffs.values():
    #     print(playoff.year, playoff.get_PO_totals())

    # df_19 = genStatDF(2019,2025)
    # for year in range(2019,2026):
    #     print(year)
    #     dict = genStatDict(year)
    # df_25 = genStatDF(2025,2026)
    # # print(df_25)
    #
    # print(df_19[mainCats])
    # print(df_25[mainCats])
    # print("DF ALL", df_all)
    # print(df_all[['Team','Year']+mainCats])

    pass