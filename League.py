from constants import *
from constants import seasonInfo as si
from espn_fr.basketball import *
# from yfpy_fr import YahooFantasySportsQuery
from Draft import *
from seasons import regSeason, poSeason
from TeamManager import *
import pandas as pd

class fantasyLeague():
    def __init__(self):
        self.seasons = [leagueSeason(year) for year in si]

        # create dictionary of statDicts for every year so that they don't have to be recreated
        # when new instances of seasons are initialized
        self.statDicts = {season.year : season.regSsn.statDict for season in self.seasons}

        self.historicalMembers = [teamManager(team, self.statDicts) for team in allMembers]

        self.statCats = ['FG%', 'FT%', '3PTM', 'REB', 'AST', 'STL', 'BLK', 'TO', 'PTS']

class leagueSeason:
    def __init__(self, year):
        print(year)

        ## Basic Variables
        self.year = year
        self.teams = si[year][0]
        self.teamCount = len(self.teams)
        self.is_espn = si[year][1]
        self.is_WL = si[year][2]
        self.rosterSize = 13
        self.statCats = ['FG%','FT%','3PTM','REB','AST','STL','BLK','TO','PTS']

        self.draft = Draft(self.year)

        self.regSsn = regSeason(self.year)
        self.statDict = self.regSsn.statDict
        self.playoffs = poSeason(self.year, self.statDict)
        self.teamRegSeasons = [team_reg_season(name, self.year, self.statDict) for name in self.teams]
        if self.playoffs.PO_time:
            self.teamPlayoffs = [team_PO_season(name, self.year, self.statDict) for name in self.playoffs.PO_teams]
        else:
            self.teamPlayoffs = []

## TESTING REGULAR SEASON
if __name__ == '__main__':
    x = fantasyLeague()

    start = 2019
    end = 2024
    for year in range (start,end+1):
        pass
        # x = leagueSeason(year)
        #
        # pdDict = {f"{team} W{week}": [stat for stat in x.statDict[week][team].values()] for week in x.statDict for team in x.statDict[week]}
        # # print(pdDict)
        # index = [statName for statName in x.statDict[1]['Fano'].keys()]
        #
        # df = pd.DataFrame(pdDict, index)
        # df = df.transpose()
        # print(df)

    #     print(f"\nSeason: {year}")
    #     print(x.playoffs.getFinalResults('Zahir'))
        # print(x.playoffs.get_PO_totals())
    # #     print(x.draft.draftScore)
    # #     print(x.regSsn.getCatStandings())
    # #     print(x.regSsn.get_WL_standings())
    # #     print(x.regSsn.getSeasonRankings())
    #     print(x.regSsn.getWeekRankings(2))

        # y = poSeason(year)
        # y.make_PO_Matchups()
        # # print(f"teams: {y.PO_teams}")
        #
        # print(y.runPlayoffs())
        # print(f"Champ: {y.getWinner()}")
        # print(y.getFinalStandings())


