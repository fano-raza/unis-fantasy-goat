from constants import *
from constants import seasonInfoDict as si
from espn_fr.basketball import *
from yfpy_fr import YahooFantasySportsQuery
import math
import datetime
import time
from Models.Matchup import matchup
import csv
from StatGenerator import *
import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler


def bs_calList(day, calList): #binary search to find what week/matchup "day" is in
    if len(calList) == 1:
        return calList[0][0]

    midInd = len(calList)//2
    if day < calList[midInd][1]: ## if today is before the start date of the middle week
        return bs_calList(day, calList[:midInd])
    elif day > calList[midInd][2]:
        return bs_calList(day, calList[midInd+1:])
    else:
        return calList[midInd][0]

class regSeason:
    def __init__(self, year, extStatDict = None, extStatDF = None):
        ## Basic Variables
        self.year = year

        self.teams = si[year]['teams']
        self.teamCount = len(self.teams)
        self.is_espn = si[year]['is_espn']
        self.is_WL = si[year]['is_WL']

        self.statCats = ['FG%', 'FT%', '3PTM', 'REB', 'AST', 'STL', 'BLK', 'TO', 'PTS']
        self.RSweekCount = weekCountDict[self.year] # from constants

        if self.year == currentYear:
            today = datetime.date.today()
            calPath = f"/Users/fano/Documents/Fantasy/Fantasy GOAT/{self.year}/{self.year}_matchup_cal.csv"
            with open(calPath, 'r') as csvfile:
                reader = csv.reader(csvfile, delimiter=',')
                next(reader)
                calList = [[int(week[0]), datetime.date(int(week[1]), int(week[2]), int(week[3])),
                            datetime.date(int(week[4]), int(week[5]), int(week[6]))]
                           for week in reader]
            self.currentWeek = min(bs_calList(today, calList), self.RSweekCount)
        else:
            self.currentWeek = self.RSweekCount

        # Stat Data Structures
        self.statCSV = f"/Users/fano/Documents/Fantasy/Fantasy GOAT/ref/{self.year}_CompStats.csv"
        self.statDict = {} if not extStatDict else extStatDict
        self.statDF = extStatDF if isinstance(extStatDF, pd.DataFrame) else pd.DataFrame()
        if len(self.statDict)==0 or self.statDF.size==0:
            self.make_stats()

        self.matchups = []
        self.make_matchups()

        if 'PTS_opp' not in self.statDF.columns:
            self.df_build_out()

        if self.is_WL:
            self.RS_champ = self.get_RSwinner_WL()
        else:
            self.RS_champ = self.get_RSwinner_Cats()

        self.status = "Active" if self.currentWeek<self.RSweekCount else "Complete"

    def __repr__(self):
        # return f"Regular Season({self.year}, Status: {self.status})"
        return f"Regular Season({self.year})"
    def get_week_range(self, startWeek, endWeek):
        if endWeek <= 0 or endWeek > self.currentWeek:
            endWeek = self.currentWeek
        if startWeek <=0 or startWeek > self.currentWeek:
            startWeek = 1
        return startWeek, endWeek

    def make_stats(self):
        # Try to find CompStat csv for that year
        try:
            statCats = ['Opp', 'FG%', 'FT%', '3PTM', 'REB', 'AST', 'STL', 'BLK',
                        'TO', 'PTS', 'FGM', 'FGA', 'FTM', 'FTA', '3PTA', '3PT%']

            with open(self.statCSV, 'r') as file:
                csvFile = csv.reader(file)
                for line in csvFile:
                    if line[1] != 'Week' and line[1]:
                        if int(line[1]) not in self.statDict:
                            # print(f"not yet: {line[1]}")
                            self.statDict[int(line[1])] = {}
                        self.statDict[int(line[1])][line[5]] = {}
                        ind = 6
                        for stat in statCats:
                            try:
                                self.statDict[int(line[1])][line[5]][stat] = float(line[ind])
                            except ValueError:
                                self.statDict[int(line[1])][line[5]][stat] = line[ind]
                            except IndexError:
                                self.statDict[int(line[1])][line[5]][stat] = None
                            # print(line, stat, ind)
                            ind += 1

        # If CompStat csv doesn't exist (takes longer, esp w Yahoo)
        except FileNotFoundError:
            print(f"Creating stat database for {self.year} season...make take some time")
            self.statDict = genStatDict(self.year)

        statList = genStatList(self.year, extStatDict=self.statDict)
        self.statDF = genStatDF(self.year, extStatList=statList)

    def make_matchups(self):

        for week in range(1, self.currentWeek+1):
            # print(week, self.year)
            teams = []
            if week not in self.statDict:
                break
            for team in self.statDict[week]:
                teams.append(team)
                opp = self.statDict[week].get(team)['Opp']
                if opp not in teams:
                    self.matchups.append(matchup(self.year, week, team, opp))
                    # print(f"matchup {team} vs {opp}: {time.time()-start}s")

        for matchupObj in self.matchups:
            matchupObj.getStats(self.statDict)
            matchupObj.getResults(self.statCats)

    def get_WL_standings(self, week = 0, sortedReturn = True):
        recDict = {}
        if week <= 0 or week > self.currentWeek:
            week = self.currentWeek

        for team in self.teams:
            recDict[team] = {'wins':0, 'losses':0, 'ties':0, 'score':0}
        # print(recDict)

        for matchup in self.matchups[:math.ceil(self.teamCount/2)*week]:
            if matchup.is_reg and matchup.count:
                # print(matchup)
                try:
                    recDict[matchup.winner]['wins'] += 1
                    recDict[matchup.loser]['losses'] += 1
                    recDict[matchup.winner]['score'] += 1
                except KeyError: #if matchup was a tie
                    recDict[matchup.team1]['ties'] += 1
                    recDict[matchup.team2]['ties'] += 1
                    recDict[matchup.team1]['score'] += 0.49
                    recDict[matchup.team2]['score'] += 0.49


        sortedTeams = sorted(recDict, key=lambda k: recDict[k]['score'])
        sortedTeams.reverse()

        standingsDict = {}
        place = 1
        for team in sortedTeams:
            standingsDict[place] = (team,f"{recDict[team]['wins']}W-{recDict[team]['losses']}L-{recDict[team]['ties']}D")
            recDict[team]['position'] = place
            place += 1

        if sortedReturn:
            return standingsDict
        else:
            return recDict

    def get_WL_standings_DF(self, week = 0, sortedReturn = True):
        if week <= 0 or week > self.currentWeek:
            week = self.currentWeek

        recDF = self.statDF.loc[(self.statDF['Week'] <= self.RSweekCount)] \
            .groupby('Team')[['matchup_win', 'matchup_loss', 'matchup_tie']].sum()

        recDict = {team: {'wins':recDF.loc[team, 'matchup_win'],
                          'ties': recDF.loc[team, 'matchup_tie'],
                          'losses': recDF.loc[team, 'matchup_loss'],
                          'score': recDF.loc[team, 'matchup_win']+0.49*recDF.loc[team, 'matchup_tie']
                          } for team in self.teams}

        sortedTeams = sorted(recDict, key=lambda k: recDict[k]['score'])
        sortedTeams.reverse()

        standingsDict = {}
        place = 1
        for team in sortedTeams:
            standingsDict[place] = (
            team, f"{recDict[team]['wins']}W-{recDict[team]['losses']}L-{recDict[team]['ties']}D")
            recDict[team]['position'] = place
            place += 1

        if sortedReturn:
            return standingsDict
        else:
            return recDict

    def get_Cats_standings(self, week = 0, sortedReturn = True):
        recDict = {}
        if week <= 0 or week > self.currentWeek:
            week = self.currentWeek

        for team in self.teams:
            recDict[team] = {'wins': 0, 'losses': 0, 'ties': 0, 'score': 0}

        for matchup_obj in self.matchups[:math.ceil(self.teamCount / 2) * week]:
            if matchup_obj.is_reg and matchup_obj.count:

                recDict[matchup_obj.team1]['wins'] += matchup_obj.wins
                recDict[matchup_obj.team1]['losses'] += matchup_obj.losses
                recDict[matchup_obj.team1]['ties'] += matchup_obj.ties
                recDict[matchup_obj.team1]['score'] += matchup_obj.wins + 0.49*matchup_obj.ties

                ## for team2 wins and losses are reversed since a matchup object considers team1 to be the "main" or "home" team
                recDict[matchup_obj.team2]['wins'] += matchup_obj.losses
                recDict[matchup_obj.team2]['losses'] += matchup_obj.wins
                recDict[matchup_obj.team2]['ties'] += matchup_obj.ties
                recDict[matchup_obj.team2]['score'] += matchup_obj.losses + 0.49 * matchup_obj.ties

        sortedTeams = sorted(recDict, key=lambda k: recDict[k]['score'])
        sortedTeams.reverse()

        standingsDict = {}
        place = 1
        for team in sortedTeams:
            standingsDict[place] = (team,f"{recDict[team]['wins']}W-{recDict[team]['losses']}L-{recDict[team]['ties']}D")
            recDict[team]['position'] = place
            place += 1

        if sortedReturn:
            return standingsDict
        else:
            return recDict

    def get_RSwinner_WL(self):
        return self.get_WL_standings()[1][0]

    def get_RSwinner_Cats(self):
        return self.get_Cats_standings()[1][0]

    def get_week_cat_rankings(self, week):
        if week <= 0 or week > self.currentWeek:
            print("Invalid Week Input")
            return None

        teamStats = {}
        teams = []
        for team in self.statDict[week]:
            if team == 'BYE' or self.statDict[week][team]["Opp"] == 'BYE':
                pass
            else:
                stats = []
                teams.append(team)
                for cat in self.statCats:
                    stats.append(self.statDict[week][team][cat])
                teamStats[team] = stats

        statsByCat = list(zip(*teamStats.values()))
        # print(statsByCat)

        weightedCatRanks = {}
        for team in teams:
            weightedCatRanks[team] = {}
            for cat in self.statCats:
                if cat != 'TO':
                    weightedCatRanks[team][cat] = ((max(statsByCat[self.statCats.index(cat)]) -
                                                    statsByCat[self.statCats.index(cat)][teams.index(team)]) /
                                                   (max(statsByCat[self.statCats.index(cat)]) - min(
                                                       statsByCat[self.statCats.index(cat)]))) * (
                                                              self.teamCount - 1) + 1
                ##
                else:  ## if cat IS TO
                    weightedCatRanks[team][cat] = ((min(statsByCat[self.statCats.index(cat)]) -
                                                    statsByCat[self.statCats.index(cat)][teams.index(team)]) /
                                                   (min(statsByCat[self.statCats.index(cat)]) - max(
                                                       statsByCat[self.statCats.index(cat)]))) * (
                                                              self.teamCount - 1) + 1
        return weightedCatRanks

    def get_week_rankings(self, week, sortedRetrun = True) -> dict[str, dict]:
        if week <= 0 or week > self.currentWeek:
            print("Invalid Week Input")
            return None

        weightedCatRanks = self.get_week_cat_rankings(week)

        weightedCatsAVG = {}
        for team in weightedCatRanks:
            weightedCatsAVG[team] = sum(weightedCatRanks[team].values())/len(weightedCatRanks[team].values())

        weightedRanks = {}
        for team in weightedCatsAVG:
            weightedRanks[team] = ((min(weightedCatsAVG.values())-weightedCatsAVG[team])/
                                    (min(weightedCatsAVG.values())-max(weightedCatsAVG.values()))) * (self.teamCount-1)+1

        sortedWeightedRank = sorted(weightedRanks, key=lambda k: weightedRanks[k])

        sortedDict = {}
        rank = 1
        for team in sortedWeightedRank:
            sortedDict[rank] = (team, round(weightedRanks[team],2))
            rank += 1

        if sortedRetrun:
            return sortedDict
        else:
            return weightedRanks

    def get_season_rankings(self, startWeek = 0, endWeek = 0, sortedReturn = True):
        rankingsDict = {}
        averageRankDict = {}
        rankedDict = {}

        startWeek, endWeek = self.get_week_range(startWeek, endWeek)

        for team in self.teams:
            rankingsDict[team] = []
            for week in range(startWeek, endWeek+1):
                try:
                    rankingsDict[team].append(self.get_week_rankings(week, False)[team])
                except KeyError:
                    pass

            averageRankDict[team] = sum(rankingsDict[team])/len(rankingsDict[team])

        sortedRanks = sorted(averageRankDict, key=lambda k: averageRankDict[k])

        rank = 1
        for team in sortedRanks:
            rankedDict[rank] = (team, round(averageRankDict[team],2))
            rank += 1

        if sortedReturn:
            return rankedDict
        else:
            return averageRankDict

    def get_avg_cat_rankings(self, startWeek = 0, endWeek = 0):
        startWeek, endWeek = self.get_week_range(startWeek, endWeek)

        avgCatRankDict = {team: {cat: 0 for cat in mainCats} for team in self.teams}

        # have to build this separately to accomodate exception for when team has a BYE week
        # and doesn't appear in avgCatRankDict
        for team in avgCatRankDict:
            weeksPlayed = 0
            for week in range(startWeek, endWeek + 1):
                try:
                    for cat in mainCats:
                        avgCatRankDict[team][cat] += self.get_week_cat_rankings(week)[team][cat]
                    weeksPlayed += 1
                except KeyError:
                    pass

            for cat in mainCats:
                avgCatRankDict[team][cat] /= weeksPlayed

        return avgCatRankDict

    def get_opp_week_rankings(self, week = 0, sortedReturn = True):
        if week <= 0 or week > self.currentWeek:
            print("Invalid Week Input")
            return None

        weekRankings = self.get_week_rankings(week, False)
        oppWeekRankings = {team: weekRankings[self.statDict[week][team]["Opp"]] for team in weekRankings}

        sortedOppWeightedRank = sorted(oppWeekRankings, key=lambda k: oppWeekRankings[k])

        sortedDict = {i+1: (sortedOppWeightedRank[i], oppWeekRankings[sortedOppWeightedRank[i]])
                      for i in range(len(sortedOppWeightedRank))}

        if sortedReturn:
            return sortedDict
        else:
            return oppWeekRankings

    def get_opp_season_rankings(self, startWeek = 0, endWeek = 0, sortedReturn = True):
        startWeek, endWeek = self.get_week_range(startWeek, endWeek)

        OppRankings = {}

        for team in self.teams:
            OppRankings[team] = []
            for week in range(startWeek, endWeek+1):
                try:
                    OppRankings[team].append(self.get_opp_week_rankings(week, False)[team])
                except KeyError:
                    pass

        OppAvgRankings = {team: sum(OppRankings[team])/len(OppRankings[team])
                          for team in OppRankings}

        sortedOppDifficulty = sorted(OppAvgRankings, key=lambda k: OppAvgRankings[k])
        rankedDict = {i+1: (sortedOppDifficulty[i],round(OppAvgRankings[sortedOppDifficulty[i]],2))
                      for i in range(len(OppAvgRankings))}

        if sortedReturn:
            return rankedDict
        else:
            return OppAvgRankings

    def get_league_totals(self, startWeek = 0, endWeek = 0):
        startWeek, endWeek = self.get_week_range(startWeek, endWeek)

        catTotals = {cat: 0 for cat in self.statCats}
        if self.is_espn:
            catTotals['FGM'] = 0
            catTotals['FGA'] = 0
            catTotals['FTM'] = 0
            catTotals['FTA'] = 0
        for week in range(startWeek,endWeek+1):
            weekDict = self.statDict[week]
            for team in weekDict:
                if weekDict[team]['Opp'] != 'BYE' and team != 'BYE':
                    for cat in catTotals:
                        if cat == 'FG%':
                            try:
                                catTotals['FGM'] += weekDict[team]['FGM']
                                catTotals['FGA'] += weekDict[team]['FGA']
                            except KeyError:
                                catTotals[cat] += weekDict[team][cat]/(self.currentWeek*math.floor(len(self.teams)/2)*2)
                        elif cat == 'FT%':
                            try:
                                catTotals['FTM'] += weekDict[team]['FTM']
                                catTotals['FTA'] += weekDict[team]['FTA']
                            except KeyError:
                                catTotals[cat] += weekDict[team][cat]/(self.currentWeek*math.floor(len(self.teams)/2)*2)
                        else:
                            catTotals[cat]+=weekDict[team][cat]

        if catTotals['FG%']==0:
            catTotals['FG%'] = catTotals['FGM']/catTotals['FGA']
            catTotals['FT%'] = catTotals['FTM']/catTotals['FTA']

        return catTotals

    def get_league_avgs(self, startWeek = 0, endWeek = 0):
        startWeek, endWeek = self.get_week_range(startWeek, endWeek)

        catTotals = self.get_league_totals(startWeek, endWeek)
        catAvgs = {cat: catTotals[cat]/(self.currentWeek * math.floor(len(self.teams)/2)*2) for cat in catTotals}
        catAvgs['FG%'] = catTotals['FG%']
        catAvgs['FT%'] = catTotals['FT%']

        return catAvgs

    def get_league_cat_totals(self, startWeek = 0, endWeek = 0):
        startWeek, endWeek = self.get_week_range(startWeek, endWeek)

        catTotals = {cat: 0 for cat in self.statCats}
        if self.is_espn:
            catTotals['FGM'] = 0
            catTotals['FGA'] = 0
            catTotals['FTM'] = 0
            catTotals['FTA'] = 0
        for week in range(startWeek, endWeek + 1):
            weekDict = self.statDict[week]
            for team in weekDict:
                if weekDict[team]['Opp'] != 'BYE' and team != 'BYE':
                    for cat in catTotals:
                        if cat == 'FG%':
                            try:
                                catTotals['FGM'] += weekDict[team]['FGM']
                                catTotals['FGA'] += weekDict[team]['FGA']
                            except KeyError:
                                catTotals[cat] += weekDict[team][cat] / (
                                            self.currentWeek * math.floor(len(self.teams) / 2) * 2)
                        elif cat == 'FT%':
                            try:
                                catTotals['FTM'] += weekDict[team]['FTM']
                                catTotals['FTA'] += weekDict[team]['FTA']
                            except KeyError:
                                catTotals[cat] += weekDict[team][cat] / (
                                            self.currentWeek * math.floor(len(self.teams) / 2) * 2)
                        else:
                            catTotals[cat] += weekDict[team][cat]

        if catTotals['FG%'] == 0:
            catTotals['FG%'] = catTotals['FGM'] / catTotals['FGA']
            catTotals['FT%'] = catTotals['FTM'] / catTotals['FTA']

        return catTotals

    #TODO: write league Win standings for WL and Cats
    def get_league_wins_standings_WL(self, startWeek = 0, endWeek = 0):
        startWeek, endWeek = self.get_week_range(startWeek, endWeek)

    # DATAFRAME PREP FUNCTIONS
    def df_build_out(self):
        posCats = [cat for cat in mainCats if cat != 'TO']
        posCats_opp = [cat + "_opp" for cat in posCats]
        negCats, negCats_opp = ['TO'], ['TO_opp']


        scaler = MinMaxScaler()

        # RANKING scale; scales values from 1 to 0 (lowest to highest)
        def minmax_rank_scale(df, columns):
            return df.groupby('Week')[columns].transform(
                lambda x: 1-pd.Series(scaler.fit_transform(x.values.reshape(-1, 1)).flatten(), index=x.index))
        # RATING scale; scales values from 0 to 1 (lowest to highest)
        def minmax_rating_scale(df, columns):
            return df.groupby('Week')[columns].transform(
                lambda x: pd.Series(scaler.fit_transform(x.values.reshape(-1, 1)).flatten(), index=x.index))

        # add columns for cat ranks + overall week rank
        for col in posCats:
            self.statDF[col + '_rank'] = minmax_rank_scale(self.statDF, [col])
            self.statDF[col + '_rating'] = minmax_rating_scale(self.statDF, [col])

        stat_df_copy = self.statDF.copy()
        stat_df_copy['TO'] = -stat_df_copy['TO']
        for col in negCats:
            self.statDF[col + '_rank'] = minmax_rank_scale(stat_df_copy, [col])
            self.statDF[col + '_rating'] = minmax_rank_scale(stat_df_copy, [col])

        rank_cols = [col + '_rank' for col in mainCats]
        rating_cols = [col + '_rating' for col in mainCats]

        self.statDF['week_rank'] = self.statDF[rank_cols].mean(axis=1)
        self.statDF['week_rank'] = 1-minmax_rank_scale(self.statDF, ['week_rank'])

        self.statDF['week_rating'] = self.statDF[rating_cols].mean(axis=1)
        self.statDF['week_rating'] = minmax_rating_scale(self.statDF, ['week_rating'])

        # re-scale all RANK values so that they from 1 to teamCount
        self.statDF[rank_cols+['week_rank']] = self.statDF[rank_cols+['week_rank']].apply(
            lambda x: (self.teamCount-1) * x+1)

        # add columns for opponent stats
        self.statDF = self.statDF.merge(self.statDF[['Week', 'Team']+mainCats+['week_rank']],
                                        left_on=['Week', 'Opp'], right_on=['Week', 'Team'],
                                        suffixes=('', '_opp'))
        self.statDF.drop(columns=['Team_opp'], inplace=True)


        # add columns for category WLD and matchup WLD
        self.statDF['cat_wins'] = (self.statDF[posCats].values > self.statDF[posCats_opp].values).sum(axis=1) + \
                                  (self.statDF[negCats].values < self.statDF[negCats_opp].values).sum(axis=1)
        self.statDF['cat_losses'] = (self.statDF[posCats].values < self.statDF[posCats_opp].values).sum(axis=1) + \
                                  (self.statDF[negCats].values > self.statDF[negCats_opp].values).sum(axis=1)
        self.statDF['cat_ties'] = len(mainCats)-(self.statDF[['cat_wins', 'cat_losses']]).sum(axis=1)

        self.statDF['matchup_win'] = (self.statDF['cat_wins'] > self.statDF['cat_losses']).astype(int)
        self.statDF['matchup_loss'] = (self.statDF['cat_wins'] < self.statDF['cat_losses']).astype(int)
        self.statDF['matchup_tie'] = (self.statDF['cat_wins'] == self.statDF['cat_losses']).astype(int)

        return None
class poSeason(regSeason):
    def __init__(self, year, extStatDict = None, extStatDF = None):
        super(poSeason, self).__init__(year, extStatDict=extStatDict, extStatDF=extStatDF)
        try:
            self.rounds = int(playoffTeamCount[self.year]/2) # from constants
        except TypeError:
            self.rounds = 0
        # print(f"{self.year}: {self.rounds}")

        self.PO_weeks = self.RSweekCount+self.rounds

        today = datetime.date.today()
        if self.year == currentYear:
            calPath = f"/Users/fano/Documents/Fantasy/Fantasy GOAT/{self.year}/{self.year}_matchup_cal.csv"

            with open(calPath, 'r') as csvfile:
                reader = csv.reader(csvfile, delimiter=',')
                next(reader)
                calList = [[int(week[0]), datetime.date(int(week[1]), int(week[2]), int(week[3])),
                            datetime.date(int(week[4]), int(week[5]), int(week[6]))]
                           for week in reader]
            self.PO_currentWeek = min(bs_calList(today, calList), self.PO_weeks)
        else:
            self.PO_currentWeek = self.PO_weeks

        self.PO_time = False if self.PO_currentWeek <= self.RSweekCount else True
        self.PO_teams = []
        self.POseeding = {}
        self.POmatchupsByWeek = {"Final":None,"3rd Place":None}
        self.PO_champ = None
        self.PO_results = {}
        self.PO_standings = {}

        if self.PO_time and self.rounds > 0:
            for i in range(1,playoffTeamCount[self.year]+1):
                if self.is_WL:
                    self.PO_teams.append(self.get_WL_standings()[i][0])
                    self.POseeding[i] = self.get_WL_standings()[i][0]
                else:
                    self.PO_teams.append(self.get_Cats_standings()[i][0])
                    self.POseeding[i] = self.get_Cats_standings()[i][0]

            self.make_PO_matchups()
            self.run_playoffs()
            self.PO_champ = self.get_PO_winner()
        else:
            self.statDF = self.statDF.loc[self.statDF['Week'] <= self.RSweekCount]

        self.status = \
            "Not Active" if not self.PO_time else \
            "Active" if self.PO_time and not self.PO_champ else \
            "Complete"

    def __repr__(self):
        # return f"Playoff({self.year}, Status: {self.status})"
        return f"Playoff({self.year})"

    def make_PO_matchups(self):
        if playoffTeamCount[self.year] == 'N/A':
            pass

        else:
            for week in range(self.RSweekCount+1, self.RSweekCount+1 + self.rounds):
                self.POmatchupsByWeek[week] = []

                teams = []
                for team in self.PO_teams:
                    teams.append(team)

                    ## Yahoo doesn't include matchups/stats for BYE weeks, so there is no line in master stat sheet with BYE weeks (need try/except)
                    try:
                        opp = self.statDict.get(week).get(team).get('Opp')
                        if opp not in teams:
                            newMatchup = matchup(self.year, week, team, opp)
                            newMatchup.getStats(self.statDict)
                            newMatchup.getResults(self.statCats)
                            self.POmatchupsByWeek[week].append(newMatchup)
                    except AttributeError:
                        pass

    def run_playoffs(self):
        ## if year didn't have playoffs (e.g. 2020 season)
        if playoffTeamCount[self.year] == 0:
            print("Playoffs Skipped")
            return None

        # print(self.statDF.loc[self.statDF['Week']>self.RSweekCount][['Week','Team','Opp']])

        # initial pass of removing non-playoff teams' matchups from statDF
        self.statDF = self.statDF.loc[~((self.statDF['Week'] >= self.RSweekCount + 1) &
                                      (~self.statDF['Team'].isin(self.PO_teams)))]

        # print(self.statDF.loc[self.statDF['Week']>self.RSweekCount][['Week','Team','Opp']])

        elimTeams = []
        thirdPlace = []
        for week in range(self.RSweekCount + 1, self.RSweekCount + self.rounds + 1):
            # print(f"eliminated teams: {elimTeams}")
            remover = []

            for matchup_obj in self.POmatchupsByWeek[week]:
                ## remove BYE week matchups (during first round)
                if matchup_obj.is_BYE:
                    remover.append(matchup_obj)

            for matchup_obj in self.POmatchupsByWeek[week]:
                ## if past the first week, remove any matchups that include eliminated teams
                if week > self.RSweekCount + 1:
                    if matchup_obj.team1 in elimTeams or matchup_obj.team2 in elimTeams:
                        remover.append(matchup_obj)
                    # print(f"past first week remover: {remover}")

                ## teams that lost in quarterfinals or earlier are added to eliminated teams
                if week < self.RSweekCount + self.rounds-1:
                    elimTeams.append(matchup_obj.loser)
                    self.PO_results[matchup_obj.loser] = 'Below Top 4'
                    # print(f"loser: {matchup_obj.loser}")

                ## teams that lost in the semi-final are added to third place game
                elif week == self.RSweekCount + self.rounds-1:
                    thirdPlace.append(matchup_obj.loser)

                ## in final week, teams in 3rd place list are part of 3rd place game
                ## teams not in 3rd place list are part of final
                elif week == self.RSweekCount + self.rounds:
                    if matchup_obj.team1 in thirdPlace or matchup_obj.team2 in thirdPlace:
                        self.POmatchupsByWeek['3rd Place'] = matchup_obj
                    else:
                        self.POmatchupsByWeek['Final'] = matchup_obj

                for matchup_obj in remover:
                    try:
                        self.POmatchupsByWeek[week].remove(matchup_obj)
                        self.statDF = self.statDF.loc[~((self.statDF['Week'] == week) & \
                                                      (self.statDF['Team'].isin(matchup_obj.teams)))]
                    except:
                        pass
                    # print(self.statDF.loc[self.statDF['Week']>self.RSweekCount][['Week','Team','Opp']])

        # if self.POmatchupsByWeek['Final']:
        self.PO_champ = self.get_PO_winner()
        self.PO_standings = {
            1: self.PO_champ,
            2: self.POmatchupsByWeek['Final'].loser,
            3: self.POmatchupsByWeek['3rd Place'].winner,
            4: self.POmatchupsByWeek['3rd Place'].loser
        }

        for standing in self.PO_standings:
            self.PO_results[self.PO_standings[standing]] = standing


    def get_PO_winner(self):
        if playoffTeamCount[self.year] == 0 or self.POmatchupsByWeek['Final']==None:
            # print(f"the {year - 1}/{year} season did not have any Playoffs\nThe Regular Season Champ was {self.get_rsWinnerWL()}")
            return None
        else:
            return self.POmatchupsByWeek['Final'].winner

    def get_final_PO_standings(self):
        if playoffTeamCount[self.year] == 'N/A':
            print(f"the {year - 1}/{year} season did not have any Playoffs\nThe Regular Season Standings were: {self.get_WL_standings()}")
            return None
        else:
            return self.PO_standings

    def get_final_PO_results(self, team = None):
        if playoffTeamCount[self.year] == 'N/A':
            print(f"the {year - 1}/{year} season did not have any Playoffs\nThe Regular Season Standings were: {self.get_WL_standings()}")
            return None
        else:
            if team == None:
                return self.PO_results
            else:
                return self.PO_results.get(team, "DNQ")

## TESTING ##
if __name__ == '__main__':
    # x = regSeason(2022)
    y = poSeason(2024)
    print(y.statDF.loc[y.statDF['Week']>18][['Week','Team','Opp']])
    # print(y.POmatchupsByWeek)
    # print(x.statDict)
    # print(x.matchups)
    # print(x.getCatStandings())
    # print(x.getCatStandings(x.currentWeek-1))
    # print(x.get_league_totals())
    # print(x.getLeagueAvgs())
    # print(x.get_week_cat_rankings(3))
    # print(x.get_league_cat_totals())
    # print(x.get_week_cat_rankings(3))
    # print(x.get_avg_cat_rankings())
    # print(x.teams)