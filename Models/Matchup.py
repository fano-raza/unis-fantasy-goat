from constants import *
from constants import seasonInfo as si
from espn_fr.basketball import *
from yfpy_fr import YahooFantasySportsQuery
import math
import time

class matchup():
    def __init__(self, year, week, team1, team2):
        self.year = year
        self.week = week
        self.weekName = f"M{week}" if week <= weekCountDict[self.year] else f"P{week % weekCountDict[self.year]}"
        self.team1 = team1
        self.team2 = team2
        self.teams = [self.team1, self.team2]

        if self.team2 != 'BYE':
            self.is_BYE = False
            self.count = True ## stats count if NOT a BYE week
        else:
            self.is_BYE = True
            self.count = False

        ## is it a regular season matchup or playoff?
        if week < weekCountDict[self.year]+1:
            self.is_reg = True
        else:
            self.is_reg = False

    def getStats(self, statDict = None):
        if statDict:
            self.stats1 = statDict.get(self.week).get(self.team1)
            if self.team2:
                self.stats2 = statDict.get(self.week).get(self.team2)

        else:
            if self.is_espn:
                league_data = self.espnLeague._fetch_league()
                sched = league_data.get("schedule")

    def getResults(self, statCats):
        if not self.is_BYE:
            self.catsWon = []
            self.catsLost = []
            self.catsTied = []
            self.wins = 0
            self.losses = 0
            self.ties = 0

            # team1 is main team for matchup, so self.wins refers to cats that team1 has won, etc.
            for cat in statCats:
                if cat != 'TO':
                    if self.stats1[cat] > self.stats2[cat]:
                        self.catsWon.append(cat)
                        self.wins += 1
                    elif self.stats2[cat] > self.stats1[cat]:
                        self.catsLost.append(cat)
                        self.losses += 1
                    else:
                        self.catsTied.append(cat)
                        self.ties += 1
                else:
                    if self.stats1[cat] < self.stats2[cat]:
                        self.catsWon.append(cat)
                        self.wins += 1
                    elif self.stats2[cat] < self.stats1[cat]:
                        self.catsLost.append(cat)
                        self.losses += 1
                    else:
                        self.catsTied.append(cat)
                        self.ties += 1

            # team1 is main team for matchup, so is_won indicates whether team1 won or not, etc.
            if len(self.catsWon) > len(self.catsLost):
                self.is_won, self.is_lost, self.is_tied = True, False, False
                self.winner, self.loser = self.team1, self.team2
            elif len(self.catsWon) == len(self.catsLost):
                self.is_won, self.is_lost, self.is_tied = False, False, True
                self.winner, self.loser = None, None
            else:
                self.is_won, self.is_lost, self.is_tied = False, True, False
                self.winner, self.loser = self.team2, self.team1

            self.score = (self.wins, self.losses, self.ties)

        else:
            self.is_won, self.is_lost, self.is_tied = False, False, False
            self.winner, self.loser = None, None

    def __repr__(self):
        try:
            return f"Matchup({self.year}, {self.weekName}, {self.team1} vs. {self.team2}, {self.wins}-{self.losses}-{self.ties})"
        except AttributeError:
            return f"Matchup({self.year}, {self.weekName}, {self.team1} vs. {self.team2})"


if __name__ == '__main__':
    year = 2025
    week = 2
    team1 = 'Fano'
    team2 = 'Chirayu'
    statCats = ['FG%', 'FT%', '3PTM', 'REB', 'AST', 'STL', 'BLK', 'TO', 'PTS']

    x = matchup(year, week, team1, team2)
    x.getStats()
    x.getResults(statCats)
    print(x)
