# from yfpy_fr import YahooFantasySportsQuery
from Models.Draft import *
from Models.TeamManager import *
import pandas as pd
import numpy as np


class fantasyLeague():
    def __init__(self, startYear: int = 0, endYear: int = 0, include: list = [], exclude: list = []):
        # if startYear is less than the earliest year played OR greater than the latest year played,
        # set it to the earliest year played
        if startYear < min(si.keys()) or startYear > max(si.keys()):
            startYear = min(si.keys())

        # if endYear is less than the earliest year played OR greater than the latest year played,
        # set it to the latest year played
        if endYear < min(si.keys()) or endYear > max(si.keys()):
            endYear = max(si.keys())

        self.include = include
        # if there is no specific include year list provided, include all years within startYear and endYear
        if len(self.include) == 0:
            self.include = list(range(startYear, endYear+1))
        # remove from include list all years in the exclude list
        if len(exclude) > 0:
            for year in exclude:
                self.include.remove(year)

        # initialize every leagueSeason for year in include list
        self.seasons = {year: leagueSeason(year) for year in self.include}

        # create dictionary of draftResults for every year so that they don't have to be recreated
        # when new instances of teamSeasons are initialized
        self.drafts = {season.year: season.draft.draftResults for season in self.seasons.values()}

        # create dictionary of statDicts for every year so that they don't have to be recreated
        # when new instances of seasons are initialized
        self.statDicts = {season.year : season.statDict for season in self.seasons.values()}

        self.statDFs = {season.year : season.statDF for season in self.seasons.values()}
        self.compStatDF = pd.concat([self.statDFs[year] for year in self.statDFs])

        # Initialize teamManager for every member of the league
        # use existing league statDicts and draft results, so they don't have to be initialized again
        self.historicalMembers = [teamManager(team,
                                              extStatDicts=self.statDicts,
                                              extDraft=self.drafts,
                                              extStatDFs=self.statDFs) for team in allMembers]

        self.statCats = ['FG%', 'FT%', '3PTM', 'REB', 'AST', 'STL', 'BLK', 'TO', 'PTS']

        print("Fantasy League Initialized")

    def __repr__(self):
        return f"fantasyLeague({self.include})"

class leagueSeason:
    def __init__(self, year):
        print(f"initializing League Season: {year}")

        ## Basic Variables
        self.year = year
        self.teams = si[year]['teams']
        self.teamCount = len(self.teams)
        self.is_espn = si[year]['is_espn']
        self.is_WL = si[year]['is_WL']
        self.rosterSize = 13
        self.statCats = mainCats

        self.draft = Draft(self.year)

        #initialize playoffs before reg season in order to get updated statDF
        self.playoffs = poSeason(self.year)
        self.statDict = self.playoffs.statDict
        self.statDF = self.playoffs.statDF
        self.regSsn = regSeason(self.year, extStatDict=self.statDict, extStatDF=self.statDF)

        self.teamDrafts = [teamDraft(team, self.year, self.draft.draftResults) for team in self.teams]
        self.teamRegSeasons = [team_reg_season(team, self.year,
                                               extStatDict=self.statDict,
                                               extStatDF=self.statDF) for team in self.teams]

        if self.playoffs.PO_time:
            self.teamPlayoffs = [team_PO_season(team, self.year,
                                                extStatDict=self.statDict,
                                                extStatDF=self.statDF) for team in self.playoffs.PO_teams]
        else:
            self.teamPlayoffs = []

    def __repr__(self):
        return f"leagueSeason({self.year})"

## TESTING
if __name__ == '__main__':
    y = leagueSeason(2020)
    df = y.statDF
    print(df.loc[df['Week']>y.regSsn.RSweekCount][['Week','Team','Opp']])
    # print(df.loc[df['Week']==1][['PTS','PTS_scaled']].sort_values(['PTS']),"\n")
    # print(df.loc[df['Week']==1][['TO', 'TO_scaled']].sort_values(['TO']),"\n")
    # print(df.loc[df['Week'] == 1][['Team','week_rating', 'week_rank']].sort_values(['week_rating']), "\n")
    # teamInclude = ['Fano', 'Juan']
    # result = df.loc[(df['Week'] <= y.regSsn.RSweekCount) & (df['Opp'].isin(teamInclude))].groupby('Team')[['matchup_win', 'matchup_loss', 'matchup_tie', 'cat_wins', 'cat_losses', 'cat_ties']].sum()
    # print(result)
    # x = fantasyLeague()
    # print(x.compStatDF.groupby(['Team','Year'])['PTS'].sum())
    # print(x.compStatDF.shape)

    # for year in x.seasons:
    #     print(x.seasons[year].regSsn.get_WL_standings())

    # print(x.seasons[2019].statDF)
    # print(x.seasons)
    # for team in x.historicalMembers:
    #     print(team.name, team.get_avg_rating())

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


