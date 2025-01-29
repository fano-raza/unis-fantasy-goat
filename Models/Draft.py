from constants import *
from constants import seasonInfo as si
from espn_fr.basketball import *
from yfpy_fr import YahooFantasySportsQuery
from YahooQuery import *
import math
import time
import csv

class Draft:
    def __init__(self, year, extResults = None):
        ## Basic Variables
        self.year = year
        self.teams = si[year][0]
        self.teamCount = len(self.teams)
        self.is_espn = si[year][1]
        self.rosterSize = 13

        ## Draft Variables
        self.draftResults = extResults if extResults else []
        self.draftDict = {team: [] for team in self.teams}
        self.draftCSV = f"/Users/fano/Documents/Fantasy/Fantasy GOAT/{self.year}/{self.year} Draft Results.csv"
        self.bestPick = []
        self.worstPick = []
        self.draftScore = 0
        self.totalPicks = self.rosterSize * self.teamCount
        self.order = draftOrder[self.year]

        # ESPN
        self.espnLeague = None
        self.espnDraft = None
        # Yahoo
        self.yLeague = None
        self.yDraft = None

        self.runDraft(extResults)
        self.calcDraftScore(extResults)
        self.makeDraftCSV()

    def __repr__(self):
        return f"Draft({self.year-1-2000}/{self.year-2000} Season, Score: {self.draftScore})"

    def runDraft(self, extResults = None): #produce self.draftResults
        if extResults:
            # print("running existing draft")
            self.draftResults = extResults
            for player in self.draftResults:
                self.draftDict[player.team].append(player)
            return

        # Draft CSV exists:
        try:
            with open(self.draftCSV, 'r') as file:
                # print("running new draft from csv")
                csvFile = csv.reader(file)
                for line in csvFile:
                    if line[0] != 'Round':  ## skip header row
                        player = Pick(self.year, int(line[0]), int(line[1]), int(line[2]), line[3], line[4])

                        self.draftResults.append(player)
                        self.draftDict[player.team].append(player)

        # Draft CSV doesn't exist
        except FileNotFoundError:
            # print("running new draft from queries")
            # snake draft order: True when forwards, False when backwards
            order = True
            lastRound = 1

            # If ESPN league
            if self.is_espn:
                self.espnLeague = League(espn_leagueID, self.year, espn_s2, espn_swid)
                self.player_dict = {}
                player_data = self.espnLeague.espn_request.get_pro_players()
                for player in player_data:
                    self.player_dict[player['fullName']] = player
                self.espnDraft = self.espnLeague.draft

                for pick in range(self.totalPicks):
                    if self.espnDraft[pick].round_num != lastRound:
                        order = not order

                    player = Pick(
                        year = self.year,
                        round = self.espnDraft[pick].round_num,
                        round_pick=self.espnDraft[pick].round_pick,
                        oPick = pick + 1,
                        name = self.espnDraft[pick].playerName,
                        team = draftOrder[self.year][pick % self.teamCount] if order
                        else draftOrder[self.year][::-1][pick % self.teamCount]
                    )
                    self.draftResults.append(player)
                    self.draftDict[player.team].append(player)
                    # update the "last round" so that the loop can know if the round has changed when it loops back
                    lastRound = self.espnDraft[pick].round_num

            # If Yahoo league
            else:
                self.yLeague = YahooFantasySportsQuery(
                    '', str(yLeagueIDs[self.year]),
                    'nba',
                    yGameIDs[self.year],
                    False,
                    False,
                    yKey, ySec)
                self.yDraft = self.yLeague.get_league_draft_results()

                for pick in range(self.totalPicks):
                    if self.yDraft[pick].round != lastRound:
                        order = not order

                    player = Pick(
                        year = self.year,
                        round = self.yDraft[pick].round,
                        round_pick = self.yDraft[pick].pick % self.teamCount if self.yDraft[pick].pick % self.teamCount != 0
                        else self.yDraft[pick].pick // self.yDraft[pick].round,
                        oPick = pick + 1,
                        name = self.yLeague.get_player_draft_analysis(self.yDraft[pick].player_key).full_name,
                        team = draftOrder[self.year][pick % self.teamCount] if order
                        else draftOrder[self.year][::-1][pick % self.teamCount]
                    )

                    self.draftResults.append(player)
                    self.draftDict[player.team].append(player)
                    # update the "last round" so that the loop can know if the round has changed when it loops back
                    lastRound = self.yDraft[pick].round

    def calcDraftScore(self, extResults):
        if extResults:
            # print("calculating existing draft")
            for player in self.draftResults:
                self.draftScore += player.score
            return

        topScore, botScore = 0,10000
        try:
            with open(self.draftCSV, 'r') as file:
                # print("calculating new draft from csv")
                csvFile = csv.reader(file)
                i = 0
                for line in csvFile:
                    if line[0] != 'Round':  ## skip header row
                        # if player ranks are still -1, do not use draft CSV to get ranking
                        # player ranks will automatically be set to -1 *IN THE CSV* if the draft instance is of the
                        # current year's draft
                        if int(line[5]) == -1:
                            raise FileNotFoundError

                        player = self.draftResults[i]
                        player.rank = int(line[5])
                        player.score = player.oPick-player.rank
                        self.draftScore += player.score

                        player.updateList()

                        if player.score >= topScore:
                            topScore = player.score
                            if player.score >= topScore:
                                self.bestPick.clear()
                            self.bestPick.append(player)

                        elif player.score <= botScore:
                            if player.rank != 1000 or player.score < botScore:
                                botScore = player.score
                                self.worstPick.clear()
                            self.worstPick.append(player)

                        self.draftResults[i] = player
                        i += 1

        # If Draft CSV doesn't exist (yet)
        except FileNotFoundError:
            # print("calculating new draft from queries")
            rankDict = self.makeRankDict()
            for player in self.draftResults:
                player.rank = rankDict.get(player.name, 501)
                # if player name doesn't appear in rankDict, it probably means the player's rank fell out of the
                # arbitrary 500 rank limit (for Yahoo leagues)
                player.score = player.oPick - player.rank
                self.draftScore += player.score

                if player.score >= topScore:
                    topScore = player.score
                    if player.score >= topScore:
                        self.bestPick.clear()
                    self.bestPick.append(player)

                elif player.score <= botScore:
                    if player.rank != 1000 or player.score < botScore:
                        botScore = player.score
                        self.worstPick.clear()
                    self.worstPick.append(player)

        self.avgPickScore = self.draftScore / self.totalPicks

    def makeRankDict(self):
        rankDict = {}
        # if ESPN league
        if self.is_espn:
            for player in self.draftResults:
                rankDict[player.name] = self.espnLeague.player_info(player.name).rank

        # if Yahoo league
        else:
            limit = 500
            league_key = f"{yGameIDs.get(self.year)}.l.{yLeagueIDs.get(self.year)}"

            for startPoint in range(0, limit, 25):
                endpoint_player = construct_endpoint(
                    league_key,
                    resource="players",
                    # sort = OR (overall rank), AR (actual rank)
                    params={"sort": "AR", "start": startPoint}
                )
                playerList = list(make_yahoo_api_request(endpoint_player)['fantasy_content']['league'][1]['players'].values())
                # print(playerList[-2])
                for i in range(25):
                    rankDict[playerList[i]['player'][0][2]["name"]["full"]] = startPoint + i + 1
                    # rankDict[startPoint+i+1] = playerList[i]['player'][0][2]["name"]["full"]

        return rankDict

    def makeDraftCSV(self):
        pathname = self.draftCSV
        csvList = []
        for pick in self.draftResults:
            row = pick.list
            # player ranks will automatically be set to -1 *IN THE CSV* if the draft instance is of the
            # current year's draft
            if self.year == currentYear:
                row[5] = -1
            csvList.append(row)

        with open(pathname, 'w') as csvfile:
            header = ["Round", "Pick", "Overall", "Player", "Team", "Rank", "Score"]
            writer = csv.writer(csvfile)
            writer.writerow(header)
            writer.writerows(csvList)

class teamDraft(Draft):
    def __init__(self, team, year, extDraft):
        self.team = team
        super(teamDraft, self).__init__(year, extDraft)

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
    # y = Draft(2024)
    x = teamDraft("Chirayu", 2025)
    print(x.teamBestPick, x.teamWorstPick)
    print(x.bestPick, x.worstPick)
    print(x.teamScore)
    print(x.draftScore)
    # print(y.makeRankDict())
    # print(y.draftScore)
    # y.makeDraftCSV()
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