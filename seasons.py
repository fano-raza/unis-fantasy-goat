from constants import *
from constants import seasonInfo as si
from espn_fr.basketball import *
from yfpy_fr import YahooFantasySportsQuery
import math
import datetime
import time
from Matchup import matchup
import csv
from gdoc_writer import bs_calList, genWeekStats
from StatSheetGenerator import genStatDict

class regSeason:
    def __init__(self, year, extStatDict = None):
        ## Basic Variables
        self.year = year

        self.teams = si[year][0]
        self.teamCount = len(self.teams)
        self.is_espn = si[year][1]
        self.is_WL = si[year][2]

        self.statCats = ['FG%', 'FT%', '3PTM', 'REB', 'AST', 'STL', 'BLK', 'TO', 'PTS']
        self.RSweekCount = weekCountDict[self.year] # from constants

        if self.year == currentYear:
            calPath = f"/Users/fano/Documents/Fantasy/Fantasy GOAT/{self.year}/{self.year}_matchup_cal.csv"

            with open(calPath, 'r') as csvfile:
                reader = csv.reader(csvfile, delimiter=',')
                next(reader)
                calList = [[int(week[0]), datetime.date(int(week[1]), int(week[2]), int(week[3])),
                            datetime.date(int(week[4]), int(week[5]), int(week[6]))]
                           for week in reader]
            today = datetime.date.today()
            self.currentWeek = min(bs_calList(today, calList), self.RSweekCount)
        else:
            self.currentWeek = self.RSweekCount

        self.statCSV = f"/Users/fano/Documents/Fantasy/Fantasy GOAT/ref/{self.year}_CompStats.csv"
        self.statDict = {} if not extStatDict else extStatDict
        if len(self.statDict)==0:
            self.makeStatDict()

        self.matchups = []
        self.makeMatchups()
        if self.is_WL:
            self.RS_champ = self.get_rsWinnerWL()
        else:
            self.RS_champ = self.get_rsWinnerCats()

    def makeStatDict(self):

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
            print(f"creating statDict...make take some time")
            self.statDict = genStatDict(self.year)[self.year]

    def makeMatchups(self):

        for week in range(1, self.currentWeek+1):
            # print(week, self.year)
            teams = []
            if week not in self.statDict:
                break
            for team in self.statDict.get(week):
                teams.append(team)
                opp = self.statDict.get(week).get(team)['Opp']
                if opp not in teams:
                    # start = time.time()
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

    def getCatStandings(self, week = 0, sortedReturn = True):
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

    def get_rsWinnerWL(self):
        return self.get_WL_standings()[1][0]

    def get_rsWinnerCats(self):
        return self.getCatStandings()[1][0]

    def getWeekRankings(self, week, sortedRetrun = True):
    ## returns dictionary of
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
                    weightedCatRanks[team][cat] = ((max(statsByCat[self.statCats.index(cat)])-statsByCat[self.statCats.index(cat)][teams.index(team)])/
                                                (max(statsByCat[self.statCats.index(cat)])-min(statsByCat[self.statCats.index(cat)]))) * (self.teamCount-1)+1
                ##
                else: ## if cat IS TO
                    weightedCatRanks[team][cat] = ((min(statsByCat[self.statCats.index(cat)]) - statsByCat[self.statCats.index(cat)][teams.index(team)]) /
                                                   (min(statsByCat[self.statCats.index(cat)]) - max(statsByCat[self.statCats.index(cat)]))) * (self.teamCount-1) + 1
        # print(weightedCatRanks)

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

    def getSeasonRankings(self, startWeek = 0, endWeek = 0, sortedReturn = True):
        rankingsDict = {}
        averageRankDict = {}
        rankedDict = {}

        if endWeek <= 0 or endWeek > self.currentWeek:
            endWeek = self.currentWeek
        if startWeek <= 0:
            startWeek = 1

        for team in self.teams:
            rankingsDict[team] = []
            for week in range(startWeek, endWeek+1):
                try:
                    rankingsDict[team].append(self.getWeekRankings(week, False)[team])
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

    def getOppWeekRankings(self, week = 0, sortedReturn = True):
        if week <= 0 or week > self.currentWeek:
            print("Invalid Week Input")
            return None

        weekRankings = self.getWeekRankings(week, False)
        oppWeekRankings = {team: weekRankings[self.statDict[week][team]["Opp"]] for team in weekRankings}

        sortedOppWeightedRank = sorted(oppWeekRankings, key=lambda k: oppWeekRankings[k])

        sortedDict = {i+1: (sortedOppWeightedRank[i], oppWeekRankings[sortedOppWeightedRank[i]])
                      for i in range(len(sortedOppWeightedRank))}

        if sortedReturn:
            return sortedDict
        else:
            return oppWeekRankings

    def getOppSeasonRankings(self, startWeek = 0, endWeek = 0, sortedReturn = True):
        if endWeek <= 0 or endWeek > self.currentWeek:
            endWeek = self.currentWeek
        if startWeek <=0:
            startWeek = 1

        OppRankings = {}

        for team in self.teams:
            OppRankings[team] = []
            for week in range(startWeek, endWeek+1):
                try:
                    OppRankings[team].append(self.getOppWeekRankings(week,False)[team])
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

    def getLeagueTotals(self, startWeek = 0, endWeek = 0):
        if endWeek <= 0 or endWeek > self.currentWeek:
            endWeek = self.currentWeek
        if startWeek <=0:
            startWeek = 1

        catTotals = {cat: 0 for cat in self.statCats}
        if self.is_espn:
            catTotals['FGM'] = 0
            catTotals['FGA'] = 0
            catTotals['FTM'] = 0
            catTotals['FTA'] = 0
        for week in range(startWeek,endWeek+1):
            theWeek = self.statDict[week]
            for team in theWeek:
                if theWeek[team]['Opp'] != 'BYE' and team != 'BYE':
                    for cat in catTotals:
                        if cat == 'FG%':
                            try:
                                catTotals['FGM'] += theWeek[team]['FGM']
                                catTotals['FGA'] += theWeek[team]['FGA']
                            except KeyError:
                                catTotals[cat] += theWeek[team][cat]/(self.currentWeek*math.floor(len(self.teams)/2)*2)
                        elif cat == 'FT%':
                            try:
                                catTotals['FTM'] += theWeek[team]['FTM']
                                catTotals['FTA'] += theWeek[team]['FTA']
                            except KeyError:
                                catTotals[cat] += theWeek[team][cat]/(self.currentWeek*math.floor(len(self.teams)/2)*2)
                        else:
                            catTotals[cat]+=theWeek[team][cat]

        if catTotals['FG%']==0:
            catTotals['FG%'] = catTotals['FGM']/catTotals['FGA']
            catTotals['FT%'] = catTotals['FTM']/catTotals['FTA']

        return catTotals

    def getLeagueAvgs(self, startWeek = 0, endWeek = 0):
        if endWeek <= 0 or endWeek > self.currentWeek:
            endWeek = self.currentWeek
        if startWeek <=0:
            startWeek = 1

        catTotals = self.getLeagueTotals(startWeek,endWeek)
        catAvgs = {cat: catTotals[cat]/(self.currentWeek * math.floor(len(self.teams)/2)*2) for cat in catTotals}
        catAvgs['FG%'] = catTotals['FG%']
        catAvgs['FT%'] = catTotals['FT%']

        return catAvgs

    def getLeagueWinsStandingsWL(self, startWeek = 0, endWeek = 0):
        if endWeek <= 0 or endWeek > self.currentWeek:
            endWeek = self.currentWeek
        if startWeek <=0:
            startWeek = 1

class poSeason(regSeason):
    def __init__(self, year, extStatDict = None):
        super(poSeason, self).__init__(year, extStatDict)
        try:
            self.rounds = int(playoffTeamCount[self.year]/2) # from constants
        except TypeError:
            self.rounds = 0
        self.PO_weeks = self.RSweekCount+self.rounds
        
        if self.year == currentYear:
            calPath = f"/Users/fano/Documents/Fantasy/Fantasy GOAT/{self.year}/{self.year}_matchup_cal.csv"

            with open(calPath, 'r') as csvfile:
                reader = csv.reader(csvfile, delimiter=',')
                next(reader)
                calList = [[int(week[0]), datetime.date(int(week[1]), int(week[2]), int(week[3])),
                            datetime.date(int(week[4]), int(week[5]), int(week[6]))]
                           for week in reader]
            today = datetime.date.today()
            self.PO_currentWeek = min(bs_calList(today, calList), self.PO_weeks)
        else:
            self.PO_currentWeek = self.PO_weeks

        self.PO_time = False if self.PO_currentWeek <= self.RSweekCount else True

        if self.PO_time:
            self.makeMatchups()
            self.PO_teams = []
            self.POseeding = {}
            self.POmatchupsByWeek = {"Final":None,"3rd Place":None}
            self.PO_champ = None

            if self.rounds > 0:
                for i in range(1,playoffTeamCount[self.year]+1):
                    if self.is_WL:
                        self.PO_teams.append(self.get_WL_standings()[i][0])
                        self.POseeding[i] = self.get_WL_standings()[i][0]
                    else:
                        self.PO_teams.append(self.getCatStandings()[i][0])
                        self.POseeding[i] = self.getCatStandings()[i][0]

                self.make_PO_Matchups()
                self.runPlayoffs()
                self.PO_champ = self.getWinner()

    def make_PO_Matchups(self):
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

    def runPlayoffs(self):
        ## if year didn't have playoffs (e.g. 2020 season)
        if playoffTeamCount[self.year] == 0 or self.POmatchupsByWeek['Final']==None:
            # print("passed")
            return None

        else:
            elimTeams = []
            thirdPlace = []
            self.PO_results = {}

            print(self.year, self.POmatchupsByWeek)

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
                        except:
                            pass

            # if self.POmatchupsByWeek['Final']:
            self.PO_champ = self.getWinner()
            self.PO_standings = {1: self.PO_champ,
                                2: self.POmatchupsByWeek['Final'].loser,
                                3: self.POmatchupsByWeek['3rd Place'].winner,
                                4: self.POmatchupsByWeek['3rd Place'].loser}

            for standing in self.PO_standings:
                self.PO_results[self.PO_standings[standing]] = standing

    def getWinner(self):
        if playoffTeamCount[self.year] == 0 or self.POmatchupsByWeek['Final']==None:
            # print(f"the {year - 1}/{year} season did not have any Playoffs\nThe Regular Season Champ was {self.get_rsWinnerWL()}")
            return None
        else:
            return self.POmatchupsByWeek['Final'].winner

    def getFinalStandings(self):
        if playoffTeamCount[self.year] == 'N/A':
            return f"the {year-1}/{year} season did not have any Playoffs\nThe Regular Season Standings were: {self.get_WL_standings()}"
        else:
            return self.PO_standings

    def getFinalResults(self, team = None):
        if playoffTeamCount[self.year] == 'N/A':
            return f"the {year - 1}/{year} season did not have any Playoffs\nThe Regular Season Standings were: {self.get_WL_standings()}"
        else:
            if team == None:
                return self.PO_results
            else:
                return self.PO_results.get(team, "DNQ")

## TESTING ##
if __name__ == '__main__':
    x = regSeason(2025)
    # print(x.statDict)
    # print(x.matchups)
    print(x.getCatStandings())
    print(x.getCatStandings(x.currentWeek-1))
    # print(x.getLeagueTotals())
    # print(x.getLeagueAvgs())