# from yfpy_fr import YahooFantasySportsQuery
from Models.Draft import *
from Models.TeamManager import *
import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler

class fantasyLeague():
    def __init__(self, startYear: int = 0, endYear: int = 0, include: list = [], exclude: list = []):
        # if startYear is less than the earliest year played OR greater than the latest year played,
        # set it to the earliest year played
        startYear = max(min(si.keys()), min(max(si.keys()),startYear))

        # if endYear is less than the earliest year played OR greater than the latest year played,
        # set it to the latest year played
        endYear = max(si.keys()) if endYear > max(si.keys()) or endYear < min(si.keys()) else endYear

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
        self.seasonList = [self.seasons[year] for year in self.include]

        # create dictionary of draftResults for every year so that they don't have to be recreated
        # when new instances of teamSeasons are initialized
        self.drafts = {season.year: season.draft.draftResults for season in self.seasons.values()}
        self.draftList = [self.drafts[year] for year in self.include]

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

        self.currentYear = currentYear

        print("Fantasy League Initialized")

    def __repr__(self):
        return f"fantasyLeague({self.include})"

    def get_filtered_df(self, years=[], weeks=[], teams=[], opps=[], RS=True, PO=True, real=True) -> pd.DataFrame:
        if len(years) == 0:
            years = self.include
        if len(weeks)==0:
            weeks = list(range(1, max(RS_weekCountDict.values()) + max(playoffRounds.values())))
        if len(teams)==0:
            teams = [team.name for team in self.historicalMembers]
        if len(opps)==0:
            opps = [team.name for team in self.historicalMembers]

        season_include = ("M", "P") if RS and PO else ("M") if RS and not PO else ("P") if PO and not RS else ()

        real_include = 1 if real else 0

        filtered_df = self.compStatDF.loc[
                            (self.compStatDF["Year"].isin(years)) &
                            (self.compStatDF["Opp"].isin(opps)) &
                            (self.compStatDF["Week"].isin(weeks)) &
                            (self.compStatDF["Week Name"].str.startswith(season_include)) &
                            (self.compStatDF["real_matchup"] >= real_include) &
                            (self.compStatDF["Team"].isin(teams))
        ]
        return filtered_df

    def get_totals_df(self, groupby_col: str | list[str] = 'Team', years=[], weeks=[], teams=[], opps=[], RS=True, PO=True, real=True):
        if isinstance(groupby_col, str):
            groupby_col = [groupby_col]

        df = self.get_filtered_df(years=years, weeks=weeks, teams=teams, opps=opps, RS=RS, PO=PO, real=real)[['Team', 'Year', 'Week']+mainCats]
        # Create a dictionary of aggregations
        agg_dict = {col: 'mean' for col in mainCatsPCT}
        agg_dict.update({col: 'sum' for col in mainCatsSum})

        # Perform the groupby + aggregation
        df = df.groupby(groupby_col, as_index=False).agg(agg_dict)

        scaler = MinMaxScaler()
        # WEIGHTED RANKING scale; scales values from 1 to 0 (lowest to highest)
        def minmax_rating_scale(df, columns):
            return df[columns].transform(
                lambda x: pd.Series(scaler.fit_transform(x.values.reshape(-1, 1)).flatten(), index=x.index))

        for col in posCats:
            df[col + '_rank'] = df[col].rank(method='min', ascending=False)
            df[col + '_rating'] = minmax_rating_scale(df, [col])

        stat_df_copy = df.copy()
        stat_df_copy[negCats] = -stat_df_copy[negCats]
        for col in negCats:
            df[col + '_rank'] = df[col].rank(method='min', ascending=True)
            df[col + '_rating'] = minmax_rating_scale(stat_df_copy, [col])

        df['avg_rating'] = df[mainCats_ratings].mean(axis=1)
        df['Rank'] = df['avg_rating'].rank(ascending=False)

        return df

    def get_avg_df(self, groupby_col: str | list[str] = 'Team', years=[], weeks=[], teams=[], opps=[], RS=True, PO=True, real=True):
        if isinstance(groupby_col, str):
            groupby_col = [groupby_col]

        df = self.get_filtered_df(years=years, weeks=weeks, teams=teams, opps=opps, RS=RS, PO=PO, real=real)[['Team', 'Year', 'Week']+mainCats]
        df = df.groupby(groupby_col, as_index=False).mean()

        scaler = MinMaxScaler()
        # WEIGHTED RANKING scale; scales values from 1 to 0 (lowest to highest)
        def minmax_rating_scale(df, columns):
            return df[columns].transform(
                lambda x: pd.Series(scaler.fit_transform(x.values.reshape(-1, 1)).flatten(), index=x.index))

        for col in posCats:
            df[col + '_rank'] = df[col].rank(method='min', ascending=False)
            df[col + '_rating'] = minmax_rating_scale(df, [col])

        stat_df_copy = df.copy()
        stat_df_copy[negCats] = -stat_df_copy[negCats]
        for col in negCats:
            df[col + '_rank'] = df[col].rank(method='min', ascending=True)
            df[col + '_rating'] = minmax_rating_scale(stat_df_copy, [col])

        df['avg_rating'] = df[mainCats_ratings].mean(axis=1)
        df['Rank'] = df['avg_rating'].rank(ascending=False)

        return df

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

        try:
            self.currentWeek = self.playoffs.PO_currentWeek
        except:
            self.currentWeek = self.regSsn.currentWeek

    def __repr__(self):
        return f"leagueSeason({self.year})"

    def get_draft_scores(self, sortedReturn=True):
        scoreDict = {name.team : name.teamScore for name in self.teamDrafts}

        if sortedReturn:
            sortedTeams = sorted(scoreDict, key=lambda k: scoreDict[k])
            sortedTeams.reverse()
            rankedScoreDict = {num: (sortedTeams[num-1], scoreDict[sortedTeams[num-1]]) for num in range(1,len(scoreDict)+1)}

            rankedScoreDict['Total'] = sum(scoreDict.values())

            return rankedScoreDict

        else:
            scoreDict['Total'] = sum(scoreDict.values())
            return scoreDict

## TESTING
if __name__ == '__main__':
    # y = leagueSeason(2022)
    # print(y.currentWeek)
    # print(y.get_draft_scores())
    # df = y.regSsn.get_filtered_df(PO=False)
    # df2 = y.regSsn.get_filtered_df()
    # for cat in mainCats:
    #     print(df.groupby('Team')[cat].mean().sort_values())
    #     print(df2.groupby('Team')[cat].mean().sort_values())
    # print(df.loc[df['Week']>y.regSsn.RSweekCount][['Week','Team','Opp']])
    # print(df.loc[df['Week']==1][['PTS','PTS_scaled']].sort_values(['PTS']),"\n")
    # print(df.loc[df['Week']==1][['TO', 'TO_scaled']].sort_values(['TO']),"\n")
    # print(df.loc[df['Week'] == 1][['Team','week_rating', 'week_rank']].sort_values(['week_rating']), "\n")
    # teamInclude = ['Fano', 'Juan']
    # result = df.loc[(df['Week'] <= y.regSsn.RSweekCount) & (df['Opp'].isin(teamInclude))].groupby('Team')[['matchup_win', 'matchup_loss', 'matchup_tie', 'cat_wins', 'cat_losses', 'cat_ties']].sum()
    # print(result)

    # print("total: ", y.draft.draftScore)
    # for team in y.teamDrafts:
    #     print(team.team, team.teamScore)

    x = fantasyLeague()
    print(x.get_totals_df() [["Team"]+mainCats])
    print(x.get_totals_df(PO = False) [["Team"]+mainCats])
    print(x.get_totals_df(RS=False) [["Team"]+mainCats])
    # df_tot = x.get_totals_df(["Team", "Year"])
    # df_avg = x.get_avg_df(["Team", "Year"])

    # df = df_tot.sort_values(by='PTS', ascending=False)
    # print(df_avg.sort_values(by='PTS', ascending=False))
    # print(x.get_filtered_df(real=True)[['Team', 'week_wt_rank', 'week_rank']])

    # df13 = x.get_filtered_df(weeks=list(range(13,25)))
    # df15 = x.get_filtered_df(weeks=list(range(15,25)))

    # print(df13.groupby(['Team'])['matchup_win'].sum().sort_values())
    # print(df15.groupby(['Team'])['matchup_win'].sum().sort_values())

    # print(df13.groupby(['Team'])['week_rank'].mean())

    # df1 = df1.loc[(df1['Team'].isin(['Fano'])) & (df1['Year']==2025)][['Team', 'Year']]
    # print(df1)
    # df2 = x.get_filtered_df(teams=["Fano"], years=[2025])[['Team', 'Week', 'real_matchup']]
    # print(df2)
    # print(x.compStatDF.groupby(['Team'])['matchup_win'].sum().sort_values())
    # # print(x.compStatDF.groupby(['Team'])['matchup_loss'].sum().sort_values())
    # # print(x.compStatDF.groupby(['Team'])['cat_wins'].sum().sort_values())
    # # print(x.compStatDF.groupby(['Team'])['cat_losses'].sum().sort_values())
    # # print(x.compStatDF.shape)
    #
    # for season in x.seasonList:
    #     print(season.get_draft_scores())

    pass


