import pandas as pd

from Models.Draft import teamDraft
from Models.seasons import *
from Models.Matchup import matchup


class teamManager():
    # TODO figure out include and exclude
    def __init__(self, name, extStatDicts = None, extStatDFs = None, extDraft = {1996: None}, includeYear = [], excludeYear = []):
        self.name = name
        self.yearsPlayed = []
        for year in si:
            if self.name in si[year]['teams']:
                self.yearsPlayed.append(year)
        self.regSeasons = {}
        self.playoffs = {}
        self.draftInfo = {}
        statDFs = []
        for year in self.yearsPlayed:
            # can use existing statDict if it is called out
            extStatDict = None if not extStatDicts else extStatDicts[year]
            extStatDF = None if not extStatDFs else extStatDFs[year]

            self.playoffs[year] = team_PO_season(self.name, year, extStatDict=extStatDict, extStatDF=extStatDF)
            self.regSeasons[year] = team_reg_season(self.name, year,
                                                    extStatDict=self.playoffs[year].statDict,
                                                    extStatDF=self.playoffs[year].statDF)
            self.draftInfo[year] = teamDraft(self.name, year, extDraft.get(year))
            statDFs.append(self.regSeasons[year].statDF)
        self.compStatDF = pd.concat(statDFs)

        self.get_career_draft_score()
        self.total_career_matchups = self.get_career_matchups_played()
        self.total_RS_matchups = self.get_career_matchups_played(0,0,'RS')
        self.total_PO_matchups = self.get_career_matchups_played(0,0,'PO')

        self.career_RS_totals = self.get_career_RS_totals()
        self.career_PO_totals = self.get_career_PO_totals()

        self.PO_chips = sum(self.get_PO_chips().values())
        self.PO_years_won = [year for year in self.get_PO_chips().keys() if self.get_PO_chips()[year] == 1]
        self.RS_finals = 0

        self.RS_chips = sum(self.get_RS_chips().values())
        self.RS_years_won = [year for year in self.get_RS_chips().keys() if self.get_RS_chips()[year] == 1]

    def __repr__(self):
        return f"TeamManager({self.name})"

    def get_career_matchups_played2(self, years = [], weeks = [], RS=True, PO=True):
        if len(years) == 0:
            years = self.yearsPlayed
        if len(weeks)==0:
            weeks = list(range(1,22)) # most possible weeks played

        season_include = ("M", "P") if RS and PO else ("M") if RS and not PO else ("P") if PO and not RS else ()

        return self.compStatDF.loc[self.compStatDF["Year"].isin(years) &
                                   (self.compStatDF["Team"] == self.name) &
                                   self.compStatDF["Week"].isin(weeks) &
                                   self.compStatDF["Week Name"].str.startswith(season_include)].shape[0]

    def get_career_matchups_played(self, startYear = 0, endYear = 0, season = 0):
        if endYear == 0 or endYear > self.yearsPlayed[-1]:
            endYear = self.yearsPlayed[-1]

        if startYear == 0 or startYear < self.yearsPlayed[0]:
            startYear = self.yearsPlayed[0]

        RS_matchups_played, PO_matchups_played = 0, 0

        for year in range(startYear, endYear+1):
            RS_matchups_played += self.regSeasons[year].get_team_weeks_played()
            PO_matchups_played += self.playoffs[year].get_team_rounds_played()

        total_matchups_played = RS_matchups_played + PO_matchups_played

        if season == 'RS':
            return RS_matchups_played
        elif season == 'PO':
            return PO_matchups_played
        else:
            return total_matchups_played

    def get_career_RS_totals(self, startYear = 0, endYear = 0):
        if endYear == 0 or endYear>max(self.yearsPlayed):
            endYear = max(self.yearsPlayed)

        if startYear == 0 or startYear<min(self.yearsPlayed):
            startYear = min(self.yearsPlayed)

        yearTotals = {}
        weeks_played_in_year = []
        for year in range(startYear, endYear+1):
            # print(f"year: {year}")
            yearTotals[year] = list(self.regSeasons[year].get_team_totals().values())
            weeks_played_in_year.append(self.regSeasons[year].get_team_weeks_played())

        # print(f"yearTotals: {yearTotals}")

        statCats = ['FG%', 'FT%', '3PTM', 'REB', 'AST', 'STL', 'BLK',
                    'TO', 'PTS', 'FGM', 'FGA', 'FTM', 'FTA', '3PTA', '3PT%']

        statsByCat = list(zip(*yearTotals.values()))
        self.career_RS_totals = {}
        self.career_RS_averages = {}

        for category in statCats:
            if category == 'FG%':
                try:
                    self.career_RS_totals[category] = sum(statsByCat[statCats.index('FGM')]) / sum(statsByCat[statCats.index('FGA')])
                except TypeError:
                    FG_sumproduct = sum(x * y for x, y in zip(weeks_played_in_year, statsByCat[statCats.index('FG%')]))
                    self.career_RS_totals[category] = FG_sumproduct/sum(weeks_played_in_year)
                self.career_RS_averages[category] = self.career_RS_totals[category]
            elif category == 'FT%':
                try:
                    self.career_RS_totals[category] = (sum(statsByCat[statCats.index('FTM')]) /
                                                       sum(statsByCat[statCats.index('FTA')]))
                except TypeError:
                    FT_sumproduct = sum(x * y for x, y in zip(weeks_played_in_year, statsByCat[statCats.index('FT%')]))
                    self.career_RS_totals[category] = FT_sumproduct / sum(weeks_played_in_year)
                self.career_RS_averages[category] = self.career_RS_totals[category]
            else:
                try:
                    self.career_RS_totals[category] = sum(statsByCat[statCats.index(category)])
                    self.career_RS_averages[category] = self.career_RS_totals[category]/sum(weeks_played_in_year)
                except TypeError:
                    # print(f"cat: {category}")
                    # print(f"rs total: {statsByCat[statCats.index(category)]}")
                    self.career_RS_totals[category] = "N/A"
                    self.career_RS_averages[category] = self.career_RS_totals[category]
        return self.career_RS_totals

    def get_career_RS_averages(self, startYear = 0, endYear = 0):
        self.get_career_RS_totals(startYear, endYear)
        return self.career_RS_averages

    def get_career_PO_totals(self, startYear = 0, endYear = 0):
        if endYear == 0 or endYear > max(self.yearsPlayed):
            endYear = max(self.yearsPlayed)

        if startYear == 0 or startYear < min(self.yearsPlayed):
            startYear = min(self.yearsPlayed)

        statCats = ['FG%', 'FT%', '3PTM', 'REB', 'AST', 'STL', 'BLK',
                    'TO', 'PTS', 'FGM', 'FGA', 'FTM', 'FTA', '3PTA', '3PT%']

        yearTotals = {}
        for year in range(startYear, endYear + 1):
            # print(f"year: {year}")
            try:
                yearTotals[year] = list(self.playoffs[year].get_team_PO_totals().values())
            except AttributeError:
                pass

        statsByCat = list(zip(*yearTotals.values()))
        # print(statsByCat)

        self.career_PO_totals = {}
        self.career_PO_averages = {}
        rounds_played_in_year = [self.playoffs.get(year).get_team_rounds_played() for year in range(startYear, endYear + 1)]

        for category in statCats:
            if len(statsByCat) == 0:
                self.career_PO_totals[category] = 0
                self.career_PO_averages[category] = 0
            elif category == 'FG%':
                try:
                    self.career_PO_totals[category] = sum(statsByCat[statCats.index('FGM')]) / sum(statsByCat[statCats.index('FGA')])
                except (TypeError, IndexError, ZeroDivisionError):
                    if sum(rounds_played_in_year) == 0:
                        self.career_PO_totals[category] = 0
                    else:
                        FG_sumproduct = sum(x * y for x, y in zip(rounds_played_in_year, statsByCat[statCats.index('FG%')]))
                        self.career_PO_totals[category] = FG_sumproduct / sum(rounds_played_in_year)
                self.career_PO_averages[category] = self.career_PO_totals[category]
            elif category == 'FT%':
                try:
                    self.career_PO_totals[category] = sum(statsByCat[statCats.index('FTM')]) / sum(statsByCat[statCats.index('FTA')])
                except (TypeError, IndexError, ZeroDivisionError):
                    if sum(rounds_played_in_year) == 0:
                        self.career_PO_totals[category] = 0
                    else:
                        FT_sumproduct = sum(x * y for x, y in zip(rounds_played_in_year, statsByCat[statCats.index('FT%')]))
                        self.career_PO_totals[category] = FT_sumproduct / sum(rounds_played_in_year)
                self.career_PO_averages[category] = self.career_PO_totals[category]
            else:
                try:
                    self.career_PO_totals[category] = sum(statsByCat[statCats.index(category)])
                    try:
                        self.career_PO_averages[category] = self.career_PO_totals[category]/sum(rounds_played_in_year)
                    except ZeroDivisionError:
                        self.career_PO_averages[category] = 0
                except TypeError:
                    self.career_PO_totals[category] = "N/A"
                    self.career_PO_averages[category] = self.career_PO_totals[category]

        return self.career_PO_totals

    def get_career_PO_averages(self, startYear = 0, endYear = 0):
        self.get_career_PO_totals(startYear, endYear)
        return self.career_PO_averages

    def get_career_totals(self, startYear = 0, endYear = 0):
        if endYear == 0 or endYear > max(self.yearsPlayed):
            endYear = max(self.yearsPlayed)

        if startYear == 0 or startYear < min(self.yearsPlayed):
            startYear = min(self.yearsPlayed)

        RS_weeks_played_in_year = []
        PO_rounds_played_in_year = []
        yearTotals = {}

        for year in range(startYear, endYear + 1):
            # print(f"year: {year}")
            yearTotals[year] = list(self.regSeasons[year].get_team_totals().values())
            RS_weeks_played_in_year.append(self.regSeasons[year].get_team_weeks_played())

        for year in range(startYear, endYear+1):
            if self.playoffs.get(year).get_team_rounds_played() > 0:
                PO_rounds_played_in_year.append(self.playoffs.get(year).get_team_rounds_played())

        self.get_career_RS_totals(startYear, endYear)
        self.get_career_PO_totals(startYear, endYear)

        statCats = ['FG%', 'FT%', '3PTM', 'REB', 'AST', 'STL', 'BLK',
                    'TO', 'PTS', 'FGM', 'FGA', 'FTM', 'FTA', '3PTA', '3PT%']

        self.career_totals = {}
        self.career_averages = {}
        for category in statCats:
            if category == 'FG%':
                try:
                    self.career_totals[category] = (self.career_RS_totals['FGM']+self.career_PO_totals['FGM'])/(
                            self.career_RS_totals['FGA']+self.career_PO_totals['FGA'])
                except (TypeError, IndexError):
                    FGs = []
                    matchups = []
                    for year in range(startYear, endYear+1):
                        FGs.append(self.regSeasons[year].get_team_totals()['FG%'])
                        FGs.append(self.playoffs[year].get_team_PO_totals()['FG%'])
                        matchups.append(self.regSeasons[year].get_team_weeks_played())
                        matchups.append(self.playoffs[year].get_team_rounds_played())

                        FG_sumproduct = sum(x * y for x, y in zip(FGs, matchups))
                        self.career_totals[category] = FG_sumproduct/sum(matchups)

                self.career_averages[category] = self.career_totals[category]
            elif category == 'FT%':
                try:
                    self.career_totals[category] = (self.career_RS_totals['FTM'] + self.career_PO_totals['FTM']) / (
                                self.career_RS_totals['FTA'] + self.career_PO_totals['FTA'])
                except (TypeError, IndexError):
                    FTs = []
                    matchups = []
                    for year in range(startYear, endYear + 1):
                        FTs.append(self.regSeasons[year].get_team_totals()['FT%'])
                        FTs.append(self.playoffs[year].get_team_PO_totals()['FT%'])
                        matchups.append(self.regSeasons[year].get_team_weeks_played())
                        matchups.append(self.playoffs[year].get_team_rounds_played())

                        FT_sumproduct = sum(x * y for x, y in zip(FTs, matchups))
                        self.career_totals[category] = FT_sumproduct / sum(matchups)

                self.career_averages[category] = self.career_totals[category]
            else:
                try:
                    self.career_totals[category] = (self.get_career_RS_totals(startYear, endYear)[category]
                                                    + self.get_career_PO_totals(startYear, endYear)[category])
                    # print(f"{category}: {self.career_totals[category]}")
                    self.career_averages[category] = self.career_totals[category] / self.get_career_matchups_played(startYear, endYear)
                except TypeError:
                    self.career_totals[category] = 'N/A'
                    self.career_averages[category] = 'N/A'
        return self.career_totals

    def get_career_averages(self, startYear = 0, endYear = 0):
        self.get_career_totals(startYear, endYear)
        return self.career_averages

    def get_best_draft_pick(self, startYear = 0, endYear = 0):
        if endYear == 0 or endYear > max(self.yearsPlayed):
            endYear = max(self.yearsPlayed)

        if startYear == 0 or startYear < min(self.yearsPlayed):
            startYear = min(self.yearsPlayed)

        self.best_career_picks = []
        for year in range(startYear, endYear+1):
            self.best_career_picks.extend(self.draftInfo[year].teamBestPick)

        sortedPicks = sorted(self.best_career_picks, key=lambda pick: pick.score)
        sortedPicks.reverse()
        try:
            return sortedPicks[0]
        except IndexError:
            return None

    def get_worst_draft_pick(self, startYear = 0, endYear = 0):
        if endYear == 0 or endYear > max(self.yearsPlayed):
            endYear = max(self.yearsPlayed)

        if startYear == 0 or startYear < min(self.yearsPlayed):
            startYear = min(self.yearsPlayed)

        self.worst_career_picks = []
        for year in range(startYear, endYear+1):
            self.worst_career_picks.extend(self.draftInfo[year].teamWorstPick)

        sortedPicks = sorted(self.worst_career_picks, key=lambda pick: pick.score)
        try:
            return sortedPicks[0]
        except IndexError:
            return None

    def get_average_draft_pick_score(self, startYear=0, endYear=0):
        if endYear == 0 or endYear > max(self.yearsPlayed):
            endYear = max(self.yearsPlayed)

        if startYear == 0 or startYear < min(self.yearsPlayed):
            startYear = min(self.yearsPlayed)

        weightedDraftScore = 0
        picks = 0
        for year in range(startYear, endYear+1):
            draft = self.draftInfo[year]
            weightedDraftScore += draft.teamScore
            picks += draft.rosterSize

        return weightedDraftScore/picks

    def get_career_draft_score(self, startYear = 0, endYear = 0):
        if endYear == 0 or endYear > max(self.yearsPlayed):
            endYear = max(self.yearsPlayed)
        if startYear == 0 or startYear < min(self.yearsPlayed):
            startYear = min(self.yearsPlayed)
        
        self.totalDraftScore = 0
        for year in range(startYear, endYear+1):
            self.totalDraftScore += self.draftInfo[year].teamScore

        return self.totalDraftScore

    def get_average_draft_score(self, startYear = 0, endYear = 0):
        return self.get_career_draft_score(startYear, endYear)/len(self.yearsPlayed)

    def get_career_record_WL(self, startYear = 0, endYear = 0, format = 'r'):
        if endYear == 0 or endYear > max(self.yearsPlayed):
            endYear = max(self.yearsPlayed)
        if startYear == 0 or startYear < min(self.yearsPlayed):
            startYear = min(self.yearsPlayed)

        self.careerWinsWL = 0
        self.careerTiesWL = 0
        self.careerLossesWL = 0

        for year in range(startYear, endYear+1):
            # try:
            # print(self.regSeasons[year].get_WL_standings(0,False))
            self.careerWinsWL += self.regSeasons[year].get_WL_standings(0,False)[self.name]['wins']
            self.careerTiesWL += self.regSeasons[year].get_WL_standings(0,False)[self.name]['ties']
            self.careerLossesWL += self.regSeasons[year].get_WL_standings(0,False)[self.name]['losses']

        try:
            self.career_WL_percent = ((self.careerWinsWL + 0.49*self.careerTiesWL)/
                                      sum((self.careerWinsWL, self.careerTiesWL, self.careerLossesWL)))
        except ZeroDivisionError:
            self.career_WL_percent = 0

        if format == 'r': ## format is record
            return {'wins':self.careerWinsWL, 'ties':self.careerTiesWL, 'losses':self.careerLossesWL}
        elif format == 'p' or format == '%': ## format is percentage
            return self.career_WL_percent
        else:
            return {'wins': self.careerWinsWL, 'ties': self.careerTiesWL, 'losses': self.careerLossesWL}

    def get_career_record_Cats(self, startYear = 0, endYear = 0, format = 'r'):
        if endYear == 0 or endYear > max(self.yearsPlayed):
            endYear = max(self.yearsPlayed)
        if startYear == 0 or startYear < min(self.yearsPlayed):
            startYear = min(self.yearsPlayed)

        self.careerWinsCats = 0
        self.careerTiesCats = 0
        self.careerLossesCats = 0

        for year in range(startYear, endYear+1):
            # try:
            # print(self.regSeasons[year].get_Cats_standings(0,False))
            self.careerWinsCats += self.regSeasons[year].get_Cats_standings(0, False)[self.name]['wins']
            self.careerTiesCats += self.regSeasons[year].get_Cats_standings(0, False)[self.name]['ties']
            self.careerLossesCats += self.regSeasons[year].get_Cats_standings(0, False)[self.name]['losses']
            # except KeyError:
            #     pass

        try:
            self.career_Cats_percent = ((self.careerWinsCats + 0.49 * self.careerTiesCats) /
                                      sum((self.careerWinsCats, self.careerTiesCats, self.careerLossesCats)))
        except ZeroDivisionError:
            self.career_Cats_percent = 0

        if format == 'r':  ## format is record
            return {'wins': self.careerWinsCats, 'ties': self.careerTiesCats, 'losses': self.careerLossesCats}
        elif format == 'p' or format == '%':  ## format is percentage
            return self.career_Cats_percent
        else:
            return {'wins': self.careerWinsCats, 'ties': self.careerTiesCats, 'losses': self.careerLossesCats}

    def get_best_RS_finish(self, startYear = 0, endYear = 0):
        if endYear == 0 or endYear > max(self.yearsPlayed):
            endYear = max(self.yearsPlayed)
        if startYear == 0 or startYear < min(self.yearsPlayed):
            startYear = min(self.yearsPlayed)

        seasons = {}
        for year in range(startYear, endYear+1):
            try:
                if self.regSeasons[year].is_WL:
                    seasons[year] = self.regSeasons[year].get_team_position_Cats()
                else:
                    seasons[year] = self.regSeasons[year].get_team_position_Cats()
            except KeyError:
                # print("pass")
                pass

        bestFinish = min(seasons.values())
        worstFinish = max(seasons.values())
        # print(seasons)

        self.bestRS = [self.regSeasons[key] for key, value in seasons.items() if value == bestFinish]
        self.worstRS = [self.regSeasons[key] for key, value in seasons.items() if value == worstFinish]

        return self.bestRS

    def get_worst_RS_finish(self, startYear = 0, endYear = 0):
        self.get_best_RS_finish(startYear, endYear)
        return self.worstRS

    def get_avg_rating(self, startYear = 0, endYear = 0): #Get average REG SEASON rating across range of years
        if endYear == 0 or endYear > max(self.yearsPlayed):
            endYear = max(self.yearsPlayed)
        if startYear == 0 or startYear < min(self.yearsPlayed):
            startYear = min(self.yearsPlayed)

        yearlyWeightedRatings = []
        for year in range(startYear, endYear+1):
            season = self.regSeasons[year]
            yearlyWeightedRatings.append(season.get_team_avg_rating() * season.get_team_weeks_played())

        return sum(yearlyWeightedRatings)/self.get_career_matchups_played(startYear, endYear, "RS")

    def get_avg_opp_rating(self, startYear=0, endYear=0):
        if endYear == 0 or endYear > max(self.yearsPlayed):
            endYear = max(self.yearsPlayed)
        if startYear == 0 or startYear < min(self.yearsPlayed):
            startYear = min(self.yearsPlayed)

        oppRatings_weighted = sum([self.regSeasons[year].get_team_avg_opp_rating() * self.regSeasons[year].get_team_weeks_played()
                                   for year in range(startYear,endYear+1)])

        weeksPlayed = sum(self.regSeasons[year].get_team_weeks_played() for year in range(startYear, endYear + 1))

        return oppRatings_weighted/weeksPlayed

    def get_avg_car_opp_ratings(self, startYear = 0, endYear = 0, sortedReturn = True):
        if endYear == 0 or endYear > max(self.yearsPlayed):
            endYear = max(self.yearsPlayed)
        if startYear == 0 or startYear < min(self.yearsPlayed):
            startYear = min(self.yearsPlayed)

        oppRatings = {team: [] for team in allMembers}
        del oppRatings[self.name]

        for year in range(startYear, endYear+1):
            season = self.regSeasons[year]
            for week in range(1,season.RSweekCount+1):
                opp = season.teamStatDict[week]['Opp']
                if opp != 'BYE':
                    oppRatings[opp].append(season.get_team_opp_week_rating(week))

        oppAvgRatings = {team: sum(oppRatings[team])/len(oppRatings[team]) for team in oppRatings
                         if len(oppRatings[team]) != 0}
        sortedOpps = sorted(oppAvgRatings, key=lambda k: oppAvgRatings[k])
        sortedOppAvgRatings = {i+1: (sortedOpps[i], oppAvgRatings[sortedOpps[i]])
                               for i in range(len(sortedOpps))}

        if sortedReturn:
            return sortedOppAvgRatings
        else:
            return oppAvgRatings

    def get_car_opp_records(self, is_WL=True, startYear=0, endYear=0, format='r'):
        if endYear == 0 or endYear > max(self.yearsPlayed):
            endYear = max(self.yearsPlayed)
        if startYear == 0 or startYear < min(self.yearsPlayed):
            startYear = min(self.yearsPlayed)

        oppRecordsWL = {team:{'wins':0,'ties':0,'losses':0} for team in allMembers}
        oppRecordsCats = {team:{'wins':0,'ties':0,'losses':0} for team in allMembers}
        del oppRecordsWL[self.name]
        del oppRecordsCats[self.name]

        for year in range(startYear, endYear+1):
            season = self.regSeasons[year]
            for matchup_obj in season.teamMatchups:
                if matchup_obj.is_BYE:
                    continue
                if matchup_obj.team1 == self.name:
                    opp = matchup_obj.team2
                    oppRecordsCats[opp]['wins'] += len(matchup_obj.catsWon)
                    oppRecordsCats[opp]['ties'] += len(matchup_obj.catsTied)
                    oppRecordsCats[opp]['losses'] += len(matchup_obj.catsLost)
                else:
                    opp = matchup_obj.team1
                    oppRecordsCats[opp]['wins'] += len(matchup_obj.catsLost)
                    oppRecordsCats[opp]['ties'] += len(matchup_obj.catsTied)
                    oppRecordsCats[opp]['losses'] += len(matchup_obj.catsWon)

                if matchup_obj.winner == self.name:
                    oppRecordsWL[opp]['wins'] += 1
                elif matchup_obj.winner == opp:
                    oppRecordsWL[opp]['losses'] += 1
                else:
                    oppRecordsWL[opp]['ties'] += 1


        oppWinPctWL = {team: 1*oppRecordsWL[team]['wins']+0.49*oppRecordsWL[team]['ties'] for team in oppRecordsWL}
        oppWinPctCats = {team: 1 * oppRecordsCats[team]['wins'] + 0.49 * oppRecordsCats[team]['ties']
                       for team in oppRecordsCats}
        for team in oppWinPctWL:
            try:
                oppWinPctWL[team] = oppWinPctWL[team]/sum(oppRecordsWL[team].values())
                oppWinPctCats[team] = oppWinPctCats[team] / sum(oppRecordsCats[team].values())
            except ZeroDivisionError:
                pass

        if is_WL:
            if format == 'p' or format == '%':
                return oppWinPctWL
            else:
                return oppRecordsWL
        else:
            if format == 'p' or format == '%':
                return oppWinPctCats
            else:
                return oppRecordsCats

    def get_PO_chips(self, startYear=0, endYear=0):
        if endYear == 0 or endYear > max(self.yearsPlayed):
            endYear = max(self.yearsPlayed)
        if startYear == 0 or startYear < min(self.yearsPlayed):
            startYear = min(self.yearsPlayed)

        PO_chips = {year:0 for year in range(startYear,endYear+1)}

        for year in PO_chips:
            season = self.playoffs[year]
            try:
                if season.PO_champ == self.name:
                    PO_chips[year] = 1
            except AttributeError:
                pass

        return PO_chips

    def get_RS_chips(self, startYear=0, endYear=0):
        if endYear == 0 or endYear > max(self.yearsPlayed):
            endYear = max(self.yearsPlayed)
        if startYear == 0 or startYear < min(self.yearsPlayed):
            startYear = min(self.yearsPlayed)

        RS_chips = {year: 0 for year in range(startYear, endYear + 1)}

        for year in RS_chips:
            season = self.regSeasons[year]
            try:
                if season.RS_champ == self.name:
                    RS_chips[year] = 1
            except AttributeError:
                pass

        return RS_chips


class team_reg_season(regSeason):
    def __init__(self, name, year, extStatDict = None, extStatDF = None):
        super(team_reg_season, self).__init__(year, extStatDict, extStatDF)
        # super(team_reg_season, self)
        self.name = name
        self.otherTeams = list(self.teams)
        self.otherTeams.remove(self.name)

        self.teamStatDict = {week: self.statDict[week].get(self.name) for week in self.statDict}

        self.teamMatchups = [matchup_obj for matchup_obj in self.matchups if matchup_obj.team1 == self.name
                             or matchup_obj.team2 == self.name]

        self.recordWL = self.get_team_record_WL()
        self.positionWL = self.get_team_position_Cats()

        self.recordCats = self.get_team_record_Cats()
        self.positionCats = self.get_team_position_Cats()

    def __repr__(self):
        if self.is_WL:
            record = self.get_team_record_WL()
            return (f"{self.name}({self.year}, Pos: {self.get_team_position_Cats()}, "
                    f"{record["wins"]}W-{record["losses"]}L-{record["ties"]}D)")
        else:
            record = self.get_team_record_Cats()
            return (f"{self.name}({self.year}, Pos: {self.get_team_position_Cats()}, "
                    f"{record["wins"]}W-{record["losses"]}L-{record["ties"]}D)")

    def get_team_weeks_played(self):
        weeksPlayed = 0
        for week in range(self.currentWeek + 1):
            if self.teamStatDict.get(week):
                if self.teamStatDict.get(week).get('Opp') != 'BYE':
                    weeksPlayed += 1
        return weeksPlayed

    def get_team_week_stats(self, week):
        ## get the full stat line of the team for the specified week
        return self.statDict[week][self.name]

    def get_team_week_cat_stat(self, week, cat):
        ## get the value of the specified category for the specified week (for the team)
        return self.statDict[week][self.name].get(cat)

    def get_team_record_WL(self, upToWeek = 0, format ='r'):
        ## get the WL record of the team (at the specified week (if specified))
        if upToWeek == 0:
            upToWeek = self.currentWeek

        self.winsWL = self.get_WL_standings(upToWeek, False)[self.name]['wins']
        self.lossesWL = self.get_WL_standings(upToWeek, False)[self.name]['losses']
        self.tiesWL = self.get_WL_standings(upToWeek, False)[self.name]['ties']
        self.percentWL = (self.winsWL+0.49*self.tiesWL)/sum((self.winsWL,self.tiesWL,self.lossesWL))

        if format == 'p' or format == '%':
            return self.percentWL
        else:
            return {'wins': self.winsWL, 'ties': self.tiesWL, 'losses': self.lossesWL}

    def get_team_position_WL(self, upToWeek = 0):
        ## get the WL standings position of the team (at the specified week (if specified))
        if upToWeek == 0:
            upToWeek = self.currentWeek

        return self.get_WL_standings(upToWeek, False)[self.name]['position']

    def get_team_record_Cats(self, upToWeek=0, format ='r'):
        ## get the Category-WL record of the team (at the specified week (if specified))
        if upToWeek == 0:
            upToWeek = self.currentWeek

        self.winsCats = self.get_Cats_standings(upToWeek, False)[self.name]['wins']
        self.lossesCats = self.get_Cats_standings(upToWeek, False)[self.name]['losses']
        self.tiesCats = self.get_Cats_standings(upToWeek, False)[self.name]['ties']
        self.percentCats = (self.winsCats+0.49*self.tiesCats)/sum((self.winsCats,self.tiesCats,self.lossesCats))

        if format == 'p' or format == '%':
            return self.percentCats
        else:
            return {'wins': self.winsCats, 'ties': self.tiesCats, 'losses': self.lossesCats}

    def get_team_position_Cats(self, upToWeek = 0):
        ## get the Category-Cats standings position of the team (at the specified week (if specified))
        if upToWeek == 0:
            upToWeek = self.currentWeek

        return self.get_Cats_standings(upToWeek, False)[self.name]['position']

    def get_team_totals(self, startWeek = 0, endWeek = 0):
        ## get the totals of all available categories (up to speicified week (if specified))
        if endWeek <= 0 or endWeek > self.currentWeek:
            endWeek = self.currentWeek
        if startWeek <=0:
            startWeek = 1

        teamStats = {}
        for week in range(startWeek,endWeek+1):
            try:
                if not self.teamStatDict[week] or self.teamStatDict[week]['Opp'] == 'BYE':
                    pass
                else:
                    teamStats[week] = list(self.teamStatDict[week].values())
            except KeyError:
                pass

        statsByCat = list(zip(*teamStats.values()))
        # print(statsByCat)

        statCats = ['Opp','FG%', 'FT%', '3PTM', 'REB', 'AST', 'STL', 'BLK',
                    'TO', 'PTS', 'FGM', 'FGA', 'FTM', 'FTA', '3PTA', '3PT%']

        self.teamTotals = {}
        self.teamAverages = {}

        for category in statCats:
            if category == 'Opp':
                pass
            elif category == 'FG%':
                if statsByCat[statCats.index('FGM')][0] == None or statsByCat[statCats.index('FGM')][0] == '':
                    self.teamTotals[category] = sum(statsByCat[statCats.index(category)])/(endWeek+1-startWeek)
                else:
                    self.teamTotals[category] = sum(statsByCat[statCats.index('FGM')]) / sum(statsByCat[statCats.index('FGA')])
                self.teamAverages[category] = self.teamTotals[category]
            elif category == 'FT%':
                if statsByCat[statCats.index('FTM')][0] == None or statsByCat[statCats.index('FTM')][0] == '':
                    self.teamTotals[category] = sum(statsByCat[statCats.index(category)])/(endWeek+1-startWeek)
                else:
                    self.teamTotals[category] = sum(statsByCat[statCats.index('FTM')]) / sum(statsByCat[statCats.index('FTA')])
                self.teamAverages[category] = self.teamTotals[category]
            else:
                try:
                    self.teamTotals[category] = sum(statsByCat[statCats.index(category)])
                    self.teamAverages[category] = self.teamTotals[category]/(endWeek+1-startWeek)
                except TypeError:
                    self.teamTotals[category] = "N/A"
                    self.teamAverages[category] = self.teamTotals[category]

        # print(self.teamTotals)
        return self.teamTotals

    def get_team_averages(self, startWeek = 0, endWeek = 0):
        self.get_team_totals(startWeek, endWeek)
        return self.teamAverages

    def get_team_draft_results(self):
        if len(self.draftResults) == 0:
            self.runDraft()
        return self.draftDict[self.name]

    def get_team_draft_score(self):
        if len(self.draftResults) == 0:
            self.runDraft()
        self.draftScore = 0
        for player in self.draftDict[self.name]:
            self.draftScore += player.score

        return self.draftScore

    def get_team_week_rating(self, week):
        return self.get_week_rankings(week, False).get(self.name)

    def get_team_avg_rating(self, startWeek = 0, endWeek = 0):
        if endWeek <= 0:
            endWeek = self.currentWeek
        if startWeek <= 0:
            startWeek = 1

        weeklyRatings = [self.get_team_week_rating(week) for week in range(startWeek, endWeek + 1)
                         if self.get_team_week_rating(week)]
        return float(sum(weeklyRatings)/len(weeklyRatings))

    def get_team_avg_cat_ratings(self, startWeek=0, endWeek=0):
        if endWeek <= 0 or endWeek > self.currentWeek:
            endWeek = self.currentWeek
        if startWeek <= 0:
            startWeek = 1

        return self.get_avg_cat_rankings(startWeek, endWeek)[self.name]

    def get_team_opp_week_rating(self, week):
        opp = self.teamStatDict.get(week).get('Opp')
        return self.get_week_rankings(week, False).get(opp)


    def get_team_avg_opp_rating(self, startWeek = 0, endWeek = 0):
    ## get the average of weekly opponent ratings (in range of weeks (if specified))
        if endWeek <= 0:
            endWeek = self.currentWeek
        if startWeek <= 0:
            startWeek = 1

        oppRatings = []
        for week in range(startWeek, endWeek+1):
            if self.get_team_opp_week_rating(week): ## don't include NoneTypes (when opponent is BYE)
                oppRatings.append(self.get_team_opp_week_rating(week))

        return sum(oppRatings)/len(oppRatings)

    def get_team_opp_ratings(self, startWeek = 0, endWeek = 0, sortedReturn = True):
    # get (average) rating of each opponent across season
        if endWeek <= 0:
            endWeek = self.currentWeek
        if startWeek <= 0:
            startWeek = 1

        oppRatings = {team: [] for team in self.otherTeams}
        for week in range(startWeek, endWeek+1):
            try:
                opp = self.teamStatDict[week]['Opp']
                oppRatings[opp].append(self.get_team_opp_week_rating(week))
            except KeyError:
                pass

        avgOppRatings = {team: sum(oppRatings[team])/len(oppRatings[team])
                         for team in oppRatings}

        sortedAvgOpps = sorted(avgOppRatings, key=lambda k: avgOppRatings[k])
        sortedAvgOppRatings = {i+1: (sortedAvgOpps[i], avgOppRatings[sortedAvgOpps[i]])
                               for i in range(len(sortedAvgOpps))}

        if sortedReturn:
            return sortedAvgOppRatings
        else:
            return avgOppRatings

    def get_team_league_record_WL(self, startWeek = 0, endWeek = 0):
        if endWeek <= 0:
            endWeek = self.currentWeek
        if startWeek <= 0:
            startWeek = 1

        wins, ties, losses = 0,0,0

        for week in range(startWeek, endWeek+1):
            for team in self.otherTeams:

                mUp = matchup(self.year, week, self.name, team)
                mUp.getStats(self.statDict)
                mUp.getResults(self.statCats)

                if mUp.is_won:
                    wins += 1
                elif mUp.is_tied:
                    ties += 1
                else:
                    losses += 1

        return {'Wins':wins, 'Ties':ties, 'Losses':losses}

    def get_team_league_record_Cats(self, startWeek = 0, endWeek = 0):
        if endWeek <= 0:
            endWeek = self.currentWeek
        if startWeek <= 0:
            startWeek = 1

        wins, ties, losses = 0,0,0

        for week in range(startWeek, endWeek+1):
            for team in self.otherTeams:

                mUp = matchup(self.year, week, self.name, team)
                mUp.getStats(self.statDict)
                mUp.getResults(self.statCats)

                wins += mUp.wins
                ties += mUp.ties
                losses += mUp.losses

        return {'Wins':wins, 'Ties':ties, 'Losses':losses}

class team_PO_season(poSeason):
    def __init__(self, name, year, extStatDict = None, extStatDF = None):
        super().__init__(year, extStatDict, extStatDF)
        self.name = name
        self.teamTotals = {}
        self.teamAverages = {}

        # if self.PO_time:
        #     self.run_playoffs()
        # else:
        #     pass

    def get_team_final_standing(self):
        return self.get_final_PO_results(self.name)

    def get_team_rounds_played(self):
        roundsPlayed = 0
        if not self.PO_time:
            return roundsPlayed

        for week in range(self.RSweekCount+1,self.RSweekCount+1+self.rounds):
            for matchup_obj in self.POmatchupsByWeek[week]:
                if matchup_obj.team1 == self.name or matchup_obj.team2 == self.name:
                    roundsPlayed += 1
        return roundsPlayed

    def get_team_PO_totals(self):
        statCats = ['Opp', 'FG%', 'FT%', '3PTM', 'REB', 'AST', 'STL', 'BLK',
                    'TO', 'PTS', 'FGM', 'FGA', 'FTM', 'FTA', '3PTA', '3PT%']
        if not self.PO_time:
            return {cat:0 for cat in statCats[1:]}

        teamStats = {}

        if playoffTeamCount[self.year] == 'N/A':
            for category in statCats:
                self.teamTotals[category] = 0
                self.teamAverages[category] = 0
            return self.teamTotals

        for week in range(self.RSweekCount+1,self.RSweekCount+1+self.rounds):
            for matchup_obj in self.POmatchupsByWeek[week]:
                if matchup_obj.team1 == self.name or matchup_obj.team2 == self.name and matchup_obj.count:
                    teamStats[week] = list(self.statDict[week][self.name].values())

        if teamStats == {}:
            for category in statCats[1:]:
                self.teamTotals[category] = 0
                self.teamAverages[category] = 0
            return self.teamTotals

        else:
            statsByCat = list(zip(*teamStats.values()))

            for category in statCats:
                if category == 'Opp':
                    pass
                elif category == 'FG%':
                    if statsByCat[statCats.index('FGM')][0] == None or statsByCat[statCats.index('FGM')][0] == '':
                        self.teamTotals[category] = sum(statsByCat[statCats.index(category)])/len(statsByCat[statCats.index(category)])
                    else:
                        self.teamTotals[category] = sum(statsByCat[statCats.index('FGM')]) / sum(statsByCat[statCats.index('FGA')])
                    self.teamAverages[category] = self.teamTotals[category]
                elif category == 'FT%':
                    if statsByCat[statCats.index('FTM')][0] == None or statsByCat[statCats.index('FTM')][0] == '':
                        self.teamTotals[category] = sum(statsByCat[statCats.index(category)])/len(statsByCat[statCats.index(category)])
                    else:
                        self.teamTotals[category] = sum(statsByCat[statCats.index('FTM')]) / sum(statsByCat[statCats.index('FTA')])
                    self.teamAverages[category] = self.teamTotals[category]
                else:
                    try:
                        self.teamTotals[category] = sum(statsByCat[statCats.index(category)])
                        self.teamAverages[category] = self.teamTotals[category]/len(statsByCat[statCats.index(category)])
                    except TypeError:
                        self.teamTotals[category] = "N/A"
                        self.teamAverages[category] = self.teamTotals[category]

            return self.teamTotals

    def get_team_PO_avgs(self):
        self.get_team_PO_totals()
        return self.teamAverages

## TESTING TESTING TESTING
if __name__ == '__main__':
    import time
    testName = 'Fano'
    testNames = allMembers

    start = 0
    end = 0

    startW = 0
    endW = 0
    year = 2020



    # y = team_PO_season(testName, 2024)
    y = teamManager(testName)
    # print(y.compStatDF.loc[(y.compStatDF["Team"]==y.name) & (y.compStatDF["Week Name"].str.startswith("P"))])
    start = time.time()
    print(y.get_career_matchups_played2())
    print(f"df took: {time.time()-start}s")
    start = time.time()
    print(y.get_career_matchups_played())
    print(f"reg took: {time.time() - start}s")
    # print(y.get_career_PO_totals())
    # print(y.get_best_draft_pick())
    # # print(y.playOffs)
    # for playoff in y.playOffs.values():
    #     print(playoff.year, playoff.get_final_PO_standings())

    # x = team_reg_season(testName, year)
    # print(x.get_team_avg_cat_ratings())

    # print(y.get_PO_totals())

    # x = teamManager("Fano")
    # print(x.get_career_PO_totals())
    # print(y.getLeagueRecordWL())
    # print(y.getLeagueRecordCats())

    for name in si[year]['teams']:
        pass
        # y = teamManager(name)
        # y = team_reg_season(name, year)
        # print(y.getTotals())
        # print(name)

        # startTime = time.time()

        # y.get_avg_rating()

        ## totals/avgs
        # print(f"RS car totals: {y.get_career_RS_totals(start,end)}")
        # print(f"RS car avgs: {y.get_career_RS_averages(start,end)}")
        # print(f"PO car totals: {y.get_career_PO_totals(start,end)}")
        # print(f"PO car avgs: {y.get_career_PO_averages(start,end)}")
        # print(f"car total matchups: {y.get_career_matchups_played(start,end)}")
        # print(f"car totals: {y.get_career_totals(start,end)}")
        # print(f"car avgs: {y.get_career_averages(start,end)}")


        ## Draft
        # print(f"Drafts: {y.draftInfo}")
        # print(f"Best Pick: {y.get_best_draft_pick(start,end)}")
        # print(f"Worst Pick: {y.get_worst_draft_pick(start,end)}")
        # print(f"Total Score: {y.get_career_draft_score(start,end)}")
        # print(f"Average Score: {y.get_average_draft_score(start,end)}")
        # print(f"Roster: {y.draftInfo[2020].teamResults}")

        ## Record/Position/Ranking
        # print(f"Career WL Record: {y.get_career_record_WL(start,end,'p')}")
        # print(f"Career Cats Record: {y.get_career_record_Cats(start,end,'p')}")
        # print(f"Best Career Finish: {y.get_best_RS_finish(start,end)}")
        # print(f"Worst Career Finish: {y.get_worst_RS_finish(start,end)}")
        # print(f"average opp rating over career: {y.get_avg_car_opp_rating(start, end)}")
        # print(f"average career opp rating: {y.get_avg_car_opp_ratings(start,end)}")
        # print(f"average career rating: {y.get_career_average}")
        # print(f"car avg rating: {y.get_avg_rating(start,end)}")
        # print(f"car opp records: {y.get_car_opp_records()}")
        # print(f"car opp win%: {y.get_car_opp_records(True,0,0,'p')}")

        ## CHIPS
        # print(f"Career PO Chips: {(y.PO_chips, y.PO_years_won)}")
        # print(f"Career RS Chips: {(y.RS_chips, y.RS_years_won)}")

        ## Individual regular season stuff
        # for season in y.regSeasons.values():
        # #     # print(f"avg opp rating: {season.getAvgOppRating()}")
        # #     print(season.getOppSeasonRankings())
        #     print(season.getSeasonOppRatings(startW,endW))
        #     print(season.getSeasonOppRatings(0,10))
        #     print(season.getAvgRating())

        # endTime = time.time()
        # print(f"time: {endTime-startTime}s")
        # print("\n")




