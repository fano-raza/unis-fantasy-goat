from constants import *
from constants import seasonInfo as si
from espn_fr.basketball import *
from yfpy_fr import YahooFantasySportsQuery
import math
import time
import csv

class Draft:
    def __init__(self, year):
        ## Basic Variables
        self.year = year
        self.teams = si[year][0]
        self.teamCount = len(self.teams)
        self.is_espn = si[year][1]
        self.rosterSize = 13

        ## Draft Variables
        self.draftResults = []
        self.draftDict = {}
        for team in self.teams:
            self.draftDict[team] = []
        self.draftCSV = f"/Users/fano/Documents/Fantasy/Fantasy GOAT/{self.year}/{self.year} Draft Results.csv"
        self.bestPick = []
        self.worstPick = []
        self.draftScore = 0
        self.draftResults = []
        self.totalPicks = self.rosterSize * self.teamCount
        self.order = draftOrder[self.year]

        self.runDraft()

    def __repr__(self):
        return f"Draft({self.year-1-2000}/{self.year-2000} Season, Score: {self.draftScore})"

    def runDraft(self, new = False):
        topScore = 0
        botScore = 0

        try:
            if new == True:
                raise FileNotFoundError
            with open(self.draftCSV, 'r') as file:
                csvFile = csv.reader(file)
                for line in csvFile:
                    if line[0] != 'Round':  ## skip header row
                        player = Pick(self.year, int(line[0]), int(line[1]), int(line[2]), line[3], line[4])
                        player.rank = int(line[5])
                        player.score = player.oPick - player.rank
                        player.updateList()

                        self.draftResults.append(player)
                        self.draftDict[player.team].append(player)
                        self.draftScore += player.score

                        if player.score > topScore:
                            topScore = player.score
                            self.bestPick.clear()
                            self.bestPick.append(player)

                        elif player.score == topScore:
                            self.bestPick.append(player)

                        elif player.score < botScore:
                            if player.rank != 1000:
                                botScore = player.score
                                self.worstPick.clear()
                            self.worstPick.append(player)

                        elif player.score == botScore:
                            self.worstPick.append(player)

        except FileNotFoundError: # If Draft CSV doesn't exist (yet)
            # snake draft order: True when forwards, False when backwards
            order = True
            lastRound = 1

            if not self.is_espn: #If Yahoo league
                self.yLeague = YahooFantasySportsQuery(
                    '', str(yahooLeagueID),
                    'nba',
                    None,
                    False,
                    False,
                    yKey, ySec)
                self.yDraft = self.yLeague.get_league_draft_results()

                rank_dict = {}
                pathname = f"/Users/fano/Documents/Fantasy/Fantasy GOAT/{self.year}/draft rankings {self.year}.csv"
                try:
                    with open(pathname, 'r') as file:
                        csvFile = csv.reader(file)
                        for line in csvFile:
                            print(line)
                            try:
                                rank_dict[line[0]] = int(line[3])
                            except:
                                pass
                except FileNotFoundError:
                    pass

            else:
                self.espnLeague = League(espn_leagueID, self.year, espn_s2, espn_swid)
                self.player_dict = {}
                player_data = self.espnLeague.espn_request.get_pro_players()
                for player in player_data:
                    self.player_dict[player['fullName']] = player
                self.espnDraft = self.espnLeague.draft

            for pick in range(self.totalPicks):
                if self.is_espn:
                    if self.espnDraft[pick].round_num != lastRound:
                        order = not order

                    if order:
                        player = Pick(
                            self.year, self.espnDraft[pick].round_num, self.espnDraft[pick].round_pick, pick + 1,
                            self.espnDraft[pick].playerName, draftOrder[self.year][pick % self.teamCount]
                        )

                    else:
                        player = Pick(
                            self.year, self.espnDraft[pick].round_num, self.espnDraft[pick].round_pick, pick + 1,
                            self.espnDraft[pick].playerName, draftOrder[self.year][::-1][pick % self.teamCount]
                        )

                    player.rank = self.espnLeague.player_info(player.name).rank
                    player.score = player.oPick - player.rank
                    self.draftScore += player.score
                    player.updateList()
                    # print(player)

                else:  ## a Yahoo League
                    if self.yDraft[pick].round != lastRound:
                        order = not order

                    if order:
                        player = Pick(
                            self.year,
                            self.yDraft[pick].round,
                            self.yDraft[pick].pick % self.teamCount if self.yDraft[pick].pick % self.teamCount != 0
                            else self.yDraft[pick].pick // self.yDraft[pick].round,
                            pick + 1, self.yLeague.get_player_draft_analysis(self.yDraft[pick].player_key).full_name,
                            draftOrder[self.year][pick % self.teamCount]
                        )

                    else:
                        player = Pick(
                            self.year,
                            self.yDraft[pick].round,
                            self.yDraft[pick].pick % self.teamCount if self.yDraft[pick].pick % self.teamCount != 0
                            else self.yDraft[pick].pick // self.yDraft[pick].round,
                            pick + 1, self.yLeague.get_player_draft_analysis(self.yDraft[pick].player_key).full_name,
                            draftOrder[self.year][::-1][pick % self.teamCount]
                        )

                    if player.rank in rank_dict:
                        player.rank = rank_dict[player.name]
                        player.score = player.oPick - player.rank
                    else:
                        player.rank = -1
                        player.score = 0
                    self.draftScore += player.score
                    player.updateList()

                # TODO figure out what to do if two players have the same draft score
                if player.score > topScore:
                    topScore = player.score
                    self.bestPick.clear()
                    self.bestPick.append(player)

                elif player.score == topScore:
                    self.bestPick.append(player)

                elif player.score < botScore:
                    if player.rank != 1000:
                        botScore = player.score
                        self.worstPick.clear()
                    self.worstPick.append(player)

                self.draftResults.append(player)

                # update the "last round" so that the loop can know if the round has changed when it loops back
                lastRound = self.espnDraft[pick].round_num if self.is_espn else self.yDraft[pick].round

            self.makeDraftCSV()
        self.avgPickScore = self.draftScore/self.totalPicks

    def makeDraftCSV(self):
        pathname = self.draftCSV
        csvList = []
        for pick in self.draftResults:
            # pick.getScore(self.espn)
            csvList.append(pick.list)

        with open(pathname, 'w') as csvfile:
            header = ["Round", "Pick", "Overall", "Player", "Team", "Rank", "Score"]
            writer = csv.writer(csvfile)
            writer.writerow(header)
            writer.writerows(csvList)

class teamDraft(Draft):
    def __init__(self, team, year):
        self.team = team
        super(teamDraft, self).__init__(year)

        self.teamResults = []
        self.teamScore = 0
        self.teamBestPick = []
        self.teamWorstPick = []
        self.topScore = 0
        self.botScore = 0

        for pick in self.draftResults:
            if pick.team == self.team:
                self.teamResults.append(pick)
                self.teamScore += pick.score

                if pick.score > self.topScore:
                    self.teamBestPick.clear()
                    self.teamBestPick.append(pick)
                    self.topScore = pick.score

                elif pick.score == self.topScore:
                    self.teamBestPick.append(pick)

                elif pick.score < self.botScore:
                    if pick.rank != 1000:
                        self.botScore = pick.score
                        self.teamWorstPick.clear()
                    self.teamWorstPick.append(pick)

                elif pick.score == self.botScore:
                    self.teamWorstPick.append(pick)

        self.team_avg_pick_score = self.teamScore/self.rosterSize

    def __repr__(self):
        return f"Draft({self.team}, {self.year-1-2000}/{self.year-2000} Season, Score: {self.teamScore})"

class Pick:
    def __init__(self, year, round, round_pick, oPick, name, team):
        self.year = year
        self.round = round
        self.oPick = oPick
        self.round_pick = round_pick
        self.name = name
        self.team = team
        self.rank = "N/A"
        self.score = "N/A"

        self.list = [self.round, self.round_pick, self.oPick, self.name, self.team, self.rank, self.score]

    def updateList(self):
        self.list = [self.round, self.round_pick, self.oPick, self.name, self.team, self.rank, self.score]

    def __repr__(self):
        return 'Pick(%s, #%s, %s, %s, %s)' % (self.year, self.oPick, self.name, self.team, self.score)


## TESTING TESTING TESTING ##
if __name__ == '__main__':
    # team = "Fano"
    #
    y = Draft(2024)
    y.makeDraftCSV()
    # y.runDraft(True)
    # for year in range(2019,2025):
    #     x = Draft(year)
    #     y = teamDraft(team, year)
    #     # print(x)
    #     print(y)
    #     print(f"best pick: {y.teamBestPick}")
    #     print(f"worst pick: {y.teamWorstPick}\n")
        # print(x.draftScore)
    #     print((x.bestPick, x.worstPick))