import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

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
from shared.runtime_config import comp_stats_csv_path
from shared.weighted_rank import per_week_rating

class regSeason:
    def __init__(self, year, extStatDict = None, extStatDF = None):
        ## Basic Variables
        self.year = year

        self.teams = si[year]['teams']
        self.teamCount = len(self.teams)
        self.is_espn = si[year]['is_espn']
        self.is_WL = si[year]['is_WL']

        self.statCats = ['FG%', 'FT%', '3PTM', 'REB', 'AST', 'STL', 'BLK', 'TO', 'PTS']
        self.standings_tiebreakers = [
            "head_to_head_cat_score",
            "total_category_wins",
            "season_category_totals_matchup",
        ]
        self.RSweekCount = RS_weekCountDict[self.year] # from constants

        if self.year == currentYear:
            self.currentWeek = min(getLastWeek(self.year), self.RSweekCount)
        else:
            self.currentWeek = self.RSweekCount

        # Stat Data Structures
        self.statCSV = comp_stats_csv_path(self.year)
        self.statDict = {} if not extStatDict else extStatDict
        self.statDF = extStatDF if isinstance(extStatDF, pd.DataFrame) else pd.DataFrame()
        if len(self.statDict)==0 or self.statDF.size==0:
            self.make_stats()

        self.matchups = []
        self.full_matchups = []
        self.make_matchups()
        self.make_full_matchups()

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

    def _get_regular_season_df(self, startWeek, endWeek):
        startWeek, endWeek = self.get_week_range(startWeek, endWeek)
        endWeek = min(endWeek, self.RSweekCount)

        return self.statDF.loc[
            (self.statDF["Week"] >= startWeek) &
            (self.statDF["Week"] <= endWeek) &
            (self.statDF["Week Name"].str.startswith("M")) &
            (self.statDF["Team"].isin(self.teams))
        ]

    def _get_team_category_profile(self, rs_df, team):
        team_df = rs_df.loc[(rs_df["Team"] == team) & (rs_df["Opp"] != "BYE")]
        profile = {cat: 0 for cat in self.statCats}

        if team_df.empty:
            return profile

        for cat in self.statCats:
            if cat in ("FG%", "FT%"):
                profile[cat] = float(team_df[cat].mean())
            else:
                profile[cat] = float(team_df[cat].sum())

        return profile

    def _get_profile_matchup_score(self, profile1, profile2):
        wins = losses = ties = 0
        for cat in self.statCats:
            v1, v2 = profile1[cat], profile2[cat]
            if cat == "TO":
                if v1 < v2:
                    wins += 1
                elif v1 > v2:
                    losses += 1
                else:
                    ties += 1
            else:
                if v1 > v2:
                    wins += 1
                elif v1 < v2:
                    losses += 1
                else:
                    ties += 1
        return wins + 0.49 * ties

    def _get_tiebreak_values(self, teams, startWeek, endWeek):
        rs_df = self._get_regular_season_df(startWeek, endWeek)
        values = {
            team: {
                "head_to_head_cat_score": 0.0,
                "total_category_wins": 0.0,
                "season_category_totals_matchup": 0.0,
            }
            for team in teams
        }

        # 1) Head-to-head category score among tied teams
        h2h_df = rs_df.loc[(rs_df["Team"].isin(teams)) & (rs_df["Opp"].isin(teams))]
        if not h2h_df.empty:
            h2h_agg = h2h_df.groupby("Team")[["cat_wins", "cat_ties"]].sum()
            for team in teams:
                if team in h2h_agg.index:
                    values[team]["head_to_head_cat_score"] = float(
                        h2h_agg.loc[team, "cat_wins"] + 0.49 * h2h_agg.loc[team, "cat_ties"]
                    )

        # 2) Total category wins across regular season
        wins_df = rs_df.loc[(rs_df["Team"].isin(teams))]
        if not wins_df.empty:
            wins_agg = wins_df.groupby("Team")["cat_wins"].sum()
            for team in teams:
                if team in wins_agg.index:
                    values[team]["total_category_wins"] = float(wins_agg.loc[team])

        # 3) Category battle using season totals (FG%/FT% use averages)
        profiles = {team: self._get_team_category_profile(rs_df, team) for team in teams}
        for team1 in teams:
            score = 0.0
            for team2 in teams:
                if team1 == team2:
                    continue
                score += self._get_profile_matchup_score(profiles[team1], profiles[team2])
            values[team1]["season_category_totals_matchup"] = score

        return values

    def _sort_with_tiebreakers(self, recDict, startWeek, endWeek, tiebreaker_order=None):
        order = tiebreaker_order or self.standings_tiebreakers
        for tiebreaker in order:
            if tiebreaker not in self.standings_tiebreakers:
                raise ValueError(f"Invalid tiebreaker: {tiebreaker}")

        # Start from primary score order, then break ties by requested tiebreakers
        initial = sorted(recDict.keys(), key=lambda t: (-recDict[t]["score"], t))
        sorted_teams = []
        i = 0
        while i < len(initial):
            team = initial[i]
            group = [team]
            j = i + 1
            team_score = round(recDict[team]["score"], 6)
            while j < len(initial) and round(recDict[initial[j]]["score"], 6) == team_score:
                group.append(initial[j])
                j += 1

            if len(group) == 1:
                sorted_teams.extend(group)
            else:
                tiebreak_values = self._get_tiebreak_values(group, startWeek, endWeek)
                group = sorted(
                    group,
                    key=lambda t: tuple([-tiebreak_values[t][tb] for tb in order] + [t])
                )
                sorted_teams.extend(group)
            i = j

        return sorted_teams

    # returns filtered df for use in any future function that uses filtered data
    def get_filtered_df(self, weeks=[], teams=[], opps=[], RS=True, PO=True, real=True):
        if len(weeks)==0:
            weeks = list(range(1, max(RS_weekCountDict.values()) + max(playoffRounds.values())))
        if len(teams)==0:
            teams = self.teams
        if len(opps)==0:
            opps = self.teams

        season_include = ("M", "P") if RS and PO else ("M") if RS and not PO else ("P") if PO and not RS else ()

        real_include = 1 if real else 0

        filtered_df = self.statDF.loc[
            (self.statDF["Team"].isin(teams)) &
            (self.statDF["Opp"].isin(opps)) &
            (self.statDF["Week"].isin(weeks)) &
            (self.statDF["Week Name"].str.startswith(season_include)) &
            (self.statDF["real_matchup"] >= real_include)
        ]

        # Strict playoff counting:
        # - exclude non-qualifiers
        # - exclude teams eliminated before semifinals (Below Top 4)
        # for any PO-week records.
        if PO and real and not filtered_df.empty:
            po_counting_teams = self._get_playoff_counting_teams()
            if po_counting_teams:
                po_mask = filtered_df["Week Name"].str.startswith("P")
                keep_po = filtered_df["Team"].isin(po_counting_teams) & filtered_df["Opp"].isin(po_counting_teams)
                filtered_df = filtered_df.loc[(~po_mask) | keep_po]

        return filtered_df

    def _get_playoff_counting_teams(self):
        cache_attr = "_po_counting_teams_cache"
        if hasattr(self, cache_attr):
            return getattr(self, cache_attr)

        teams = set()
        try:
            # If already a poSeason instance, use in-memory playoff outputs.
            po_obj = self if hasattr(self, "PO_teams") and hasattr(self, "PO_results") else \
                poSeason(self.year, extStatDict=self.statDict, extStatDF=self.statDF)

            po_teams = set(getattr(po_obj, "PO_teams", []) or [])
            po_results = getattr(po_obj, "PO_results", {}) or {}
            below_top4 = {team for team, res in po_results.items() if team and str(res).strip().lower() == "below top 4"}

            teams = po_teams - below_top4 if po_teams else set()
        except Exception:
            teams = set()

        setattr(self, cache_attr, teams)
        return teams

    def make_stats(self):
        # Try to find CompStat csv for that year
        try:
            with open(self.statCSV, 'r') as file:
                csvFile = csv.reader(file)
                for line in csvFile:
                    if line[1] != 'Week' and line[1]:
                        week = int(line[1])
                        if week not in self.statDict:
                            self.statDict[week] = {}

                        team = line[5]
                        self.statDict[week][team] = {}
                        self.statDict[week][team]['Opp'] = line[6]
                        next_ind = 7
                        for i, stat in enumerate(statCats):
                            try:
                                self.statDict[week][line[5]][stat] = float(line[i+next_ind])
                            except ValueError:
                                self.statDict[week][line[5]][stat] = line[i+next_ind]
                            except IndexError:
                                self.statDict[week][line[5]][stat] = None

        # If CompStat csv doesn't exist (takes longer, esp w Yahoo)
        except FileNotFoundError:
            print(f"Creating stat database for {self.year} season...make take some time")
            self.statDict = genStatDict(self.year)

        statList = genStatList(self.year, extStatDict=self.statDict)
        self.statDF = genStatDF(self.year, extStatList=statList)

    def make_matchups(self):
        for week in range(1, self.currentWeek+1):
            teams = []
            if week not in self.statDict:
                break
            for team in self.statDict[week]:
                teams.append(team)
                opp = self.statDict[week][team]['Opp']
                if opp not in teams:
                    self.matchups.append(matchup(self.year, week, team, opp))
                    # print(f"matchup {team} vs {opp}: {time.time()-start}s")

        for matchupObj in self.matchups:
            matchupObj.getStats(self.statDict)
            matchupObj.getResults(self.statCats)

    def make_full_matchups(self):
        for week in range(1, self.currentWeek+1):
            if week not in self.statDict:
                break
            for team in self.statDict[week]:
                for opp in self.statDict[week]:
                    if opp == team:
                        continue
                    matchup_obj = matchup(self.year, week, team, opp)
                    matchup_obj.getStats(self.statDict)
                    matchup_obj.getResults(self.statCats)
                    if matchup_obj not in self.matchups:
                        matchup_obj.count = False

                    self.full_matchups.append(matchup_obj)

    def get_WL_standings(self, startWeek = 0, endWeek = 0, sortedReturn = True, tiebreaker_order=None):
        recDict = {}
        if endWeek <= 0 or endWeek >= self.currentWeek:
            endWeek = self.currentWeek
        if startWeek <= 0 or startWeek >= self.currentWeek:
            startWeek = 1

        for team in self.teams:
            recDict[team] = {'wins': 0, 'losses': 0, 'ties': 0, 'score': 0}
        # print(recDict)

        for matchup in self.matchups[math.ceil(self.teamCount / 2) * (startWeek - 1):
        math.ceil(self.teamCount / 2) * endWeek]:
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


        sortedTeams = self._sort_with_tiebreakers(recDict, startWeek, endWeek, tiebreaker_order=tiebreaker_order)

        standingsDict = {}
        if self.is_WL and self.year in standingsOverwrite:
            for place in standingsOverwrite[self.year]:
                team = standingsOverwrite[self.year][place]
                standingsDict[place] = (
                team, f"{recDict[team]['wins']}W-{recDict[team]['losses']}L-{recDict[team]['ties']}D")
                recDict[team]['position'] = place
        else:
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

    def get_WL_standings_DF(self, sortedReturn = True, tiebreaker_order=None):
        recDF = self.statDF.loc[(self.statDF['Week'] <= self.RSweekCount)] \
            .groupby('Team')[['matchup_win', 'matchup_loss', 'matchup_tie']].sum()

        recDict = {team: {'wins':recDF.loc[team, 'matchup_win'],
                          'ties': recDF.loc[team, 'matchup_tie'],
                          'losses': recDF.loc[team, 'matchup_loss'],
                          'score': recDF.loc[team, 'matchup_win']+0.49*recDF.loc[team, 'matchup_tie']
                          } for team in self.teams}

        sortedTeams = self._sort_with_tiebreakers(
            recDict,
            startWeek=1,
            endWeek=min(self.currentWeek, self.RSweekCount),
            tiebreaker_order=tiebreaker_order,
        )

        standingsDict = {}
        if self.is_WL and self.year in standingsOverwrite:
            for place in standingsOverwrite[self.year]:
                team = standingsOverwrite[self.year][place]
                standingsDict[place] = (team,f"{recDict[team]['wins']}W-{recDict[team]['losses']}L-{recDict[team]['ties']}D")
                recDict[team]['position'] = place
        else:
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

    def get_Cats_standings(self, startWeek = 0, endWeek = 0, sortedReturn = True, tiebreaker_order=None):
        recDict = {}
        if endWeek <= 0 or endWeek >= self.currentWeek:
            endWeek = self.currentWeek
        if startWeek <= 0 or startWeek >= self.currentWeek:
            startWeek = 1

        for team in self.teams:
            recDict[team] = {'wins': 0, 'losses': 0, 'ties': 0, 'score': 0}
        # print(recDict)

        for matchup_obj in self.matchups[math.ceil(self.teamCount / 2) * (startWeek-1) :
                                            math.ceil(self.teamCount / 2) * endWeek]:
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

        sortedTeams = self._sort_with_tiebreakers(recDict, startWeek, endWeek, tiebreaker_order=tiebreaker_order)

        standingsDict = {}
        if not self.is_WL and self.year in standingsOverwrite:
            for place in standingsOverwrite[self.year]:
                team = standingsOverwrite[self.year][place]
                standingsDict[place] = (team,f"{recDict[team]['wins']}W-{recDict[team]['losses']}L-{recDict[team]['ties']}D")
                recDict[team]['position'] = place

        else:
            place = 1
            for team in sortedTeams:
                standingsDict[place] = (team,f"{recDict[team]['wins']}W-{recDict[team]['losses']}L-{recDict[team]['ties']}D")
                recDict[team]['position'] = place
                place += 1

        if sortedReturn:
            return standingsDict
        else:
            return recDict

    def get_swapped_schedule_standings(
            self,
            teamA: str,
            teamB: str,
            startWeek: int = 0,
            endWeek: int = 0,
            format: str = "def",  # "def" | "wl" | "cats" (case-insensitive)
            sortedReturn: bool = True,
    ):
        """
        Returns standings if teamA and teamB swapped schedules for the given week range.
        If teamA and teamB play each other in a week, that matchup is kept as-is.

        format:
          - "wl"   -> matchup W/L standings
          - "cats" -> category W/L standings
          - anything else (default "def") -> uses the season's current format (self.is_WL)
        """

        if teamA == teamB:
            raise ValueError("teamA and teamB must be different.")
        if teamA not in self.teams or teamB not in self.teams:
            raise ValueError("Both teams must be in this season's teams list.")

        startWeek, endWeek = self.get_week_range(startWeek, endWeek)
        endWeek = min(endWeek, self.RSweekCount)

        fmt = (format or "def").strip().lower()
        if fmt not in ("wl", "cats"):
            fmt = "wl" if self.is_WL else "cats"

        # --- Build per-week opponent mapping for the swapped schedule
        swapped_rows = []
        for week in range(startWeek, endWeek + 1):
            if week not in self.statDict:
                continue

            # base mapping from actual schedule
            opp_map = {}
            for t in self.teams:
                try:
                    opp_map[t] = self.statDict[week][t]["Opp"]
                except (KeyError, TypeError):
                    opp_map[t] = None

            origA = opp_map.get(teamA)
            origB = opp_map.get(teamB)

            if origA is None or origB is None:
                continue

            # keep head-to-head week as-is
            head_to_head = (origA == teamB) or (origB == teamA)
            if not head_to_head:
                # Swap teamA and teamB opponents
                opp_map[teamA] = origB
                opp_map[teamB] = origA

                # Maintain reciprocity for their opponents (unless BYE)
                if origB not in ("BYE", None):
                    opp_map[origB] = teamA
                if origA not in ("BYE", None):
                    opp_map[origA] = teamB

            # collect rows for all teams that have a matchup (non-BYE)
            for t, opp in opp_map.items():
                if opp in (None, "BYE"):
                    continue
                swapped_rows.append({"Week": week, "Team": t, "Opp": opp})

        if not swapped_rows:
            return {} if sortedReturn else {}

        swap_df = pd.DataFrame(swapped_rows).drop_duplicates()

        # --- Pull the matchup result rows from statDF for those swapped opponents
        base_df = self.statDF.loc[
            (self.statDF["Week"].between(startWeek, endWeek)) &
            (self.statDF["Week"] <= self.RSweekCount) &
            (self.statDF["Week Name"].str.startswith("M"))
            ]

        use_df = base_df.merge(swap_df, on=["Week", "Team", "Opp"], how="inner")

        # --- Build standings
        recDict = {t: {"wins": 0, "losses": 0, "ties": 0, "score": 0} for t in self.teams}

        if fmt == "wl":
            agg = use_df.groupby("Team")[["matchup_win", "matchup_loss", "matchup_tie"]].sum()
            for t in agg.index:
                w = float(agg.loc[t, "matchup_win"])
                l = float(agg.loc[t, "matchup_loss"])
                d = float(agg.loc[t, "matchup_tie"])
                recDict[t]["wins"] = w
                recDict[t]["losses"] = l
                recDict[t]["ties"] = d
                recDict[t]["score"] = w + 0.49 * d

        else:  # fmt == "cats"
            agg = use_df.groupby("Team")[["cat_wins", "cat_losses", "cat_ties"]].sum()
            for t in agg.index:
                w = float(agg.loc[t, "cat_wins"])
                l = float(agg.loc[t, "cat_losses"])
                d = float(agg.loc[t, "cat_ties"])
                recDict[t]["wins"] = w
                recDict[t]["losses"] = l
                recDict[t]["ties"] = d
                recDict[t]["score"] = w + 0.49 * d

        sortedTeams = sorted(recDict, key=lambda k: recDict[k]["score"], reverse=True)

        standingsDict = {}
        place = 1
        for t in sortedTeams:
            standingsDict[place] = (
                t,
                f"{int(recDict[t]['wins'])}W-{int(recDict[t]['losses'])}L-{int(recDict[t]['ties'])}D"
            )
            recDict[t]["position"] = place
            place += 1

        return standingsDict if sortedReturn else recDict

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

        # have to build this separately to accommodate exception for when team has a BYE week
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

    def get_league_wins_standings_WL(self, startWeek = 0, endWeek = 0, sortedReturn = True):
        recDict = {}
        if endWeek <= 0 or endWeek >= self.currentWeek:
            endWeek = self.currentWeek
        if startWeek <= 0 or startWeek >= self.currentWeek:
            startWeek = 1

        for team in self.teams:
            recDict[team] = {'wins': 0, 'losses': 0, 'ties': 0, 'score': 0}
        # print(recDict)

        for matchup in self.full_matchups[self.teamCount * (self.teamCount - 1) * (startWeek - 1) :
                                            self.teamCount * (self.teamCount-1) * endWeek]:
            if matchup.is_reg:
                # only do team1 because hyp_matchups will have a separate matchup obj for team2 (where team2 is team1)
                # NOTE: was previously a try/except KeyError expecting matchup.winner/.loser lookups to raise on
                # a tie, but they're both None on a tie (not a missing dict key) -- neither comparison below ever
                # matched, no exception was ever raised, and every all-play tie silently vanished from every
                # team's record (confirmed: 0 ties reported across every season). Checking is_tied directly fixes it.
                if matchup.is_tied:
                    recDict[matchup.team1]['ties'] += 1
                    recDict[matchup.team1]['score'] += 0.49
                elif matchup.winner == matchup.team1:
                    recDict[matchup.team1]['wins'] += 1
                    recDict[matchup.team1]['score'] += 1
                elif matchup.loser == matchup.team1:
                    recDict[matchup.team1]['losses'] += 1

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

    def get_league_wins_standings_Cats(self, startWeek = 0, endWeek = 0, sortedReturn = True):
        recDict = {}
        if endWeek <= 0 or endWeek >= self.currentWeek:
            endWeek = self.currentWeek
        if startWeek <= 0 or startWeek >= self.currentWeek:
            startWeek = 1

        for team in self.teams:
            recDict[team] = {'wins': 0, 'losses': 0, 'ties': 0, 'score': 0}
        # print(recDict)

        for matchup in self.full_matchups[self.teamCount * (self.teamCount - 1) * (startWeek - 1):
        self.teamCount * (self.teamCount - 1) * endWeek]:
            if matchup.is_reg:
                recDict[matchup.team1]['wins'] += matchup.wins
                recDict[matchup.team1]['losses'] += matchup.losses
                recDict[matchup.team1]['ties'] += matchup.ties
                recDict[matchup.team1]['score'] += matchup.wins + 0.49 * matchup.ties

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

    # DATAFRAME PREP FUNCTIONS
    def _apply_global_count_flags(self):
        """
        Global counting rules applied across regular season and playoffs.
        Any BYE row is non-counting.
        """
        if self.statDF is None or self.statDF.empty:
            return None

        bye_mask = (self.statDF["Team"] == "BYE") | (self.statDF["Opp"] == "BYE")
        if bye_mask.any():
            if "Count" in self.statDF.columns:
                self.statDF.loc[bye_mask, "Count"] = False
            if "real_matchup" in self.statDF.columns:
                self.statDF.loc[bye_mask, "real_matchup"] = 0

            # Keep matchup outcome flags consistent for non-counting rows.
            for col in ("matchup_win", "matchup_loss", "matchup_tie"):
                if col in self.statDF.columns:
                    self.statDF.loc[bye_mask, col] = 0
        return None

    def df_build_out(self):
        posCats = [cat for cat in mainCats if cat != 'TO']
        posCats_opp = [cat + "_opp" for cat in posCats]
        negCats, negCats_opp = ['TO'], ['TO_opp']
        self.statDF.drop('Count', axis=1)

        self.statDF = per_week_rating(self.statDF, mainCats, negCats, self.teamCount)

        self.statDF['real_matchup'] = 1
        # add rows so that there is a row for every hypothetical matchup in which a team played another team
        # these will be used to calculate league wins
        self.statDF = self.statDF.merge(
            self.statDF[['Week','Team'] + mainCats + ['week_wt_rank', 'week_rating']],
            on=["Week"],
            suffixes=("", "_opp"),
            how="left"  # Ensures unmatched rows still exist
        )
        # remove duplicate row where
        self.statDF = self.statDF[self.statDF["Team"] != self.statDF["Team_opp"]]
        # set new rows (non-real matchups) real_matchup value to 0
        self.statDF.loc[self.statDF['Team_opp'] != self.statDF['Opp'], 'real_matchup'] = 0
        self.statDF['Opp'] = self.statDF['Team_opp']
        self.statDF.drop('Team_opp', axis=1)

        # # add columns for category WLD and matchup WLD
        self.statDF['cat_wins'] = (self.statDF[posCats].values > self.statDF[posCats_opp].values).sum(axis=1) + \
                                  (self.statDF[negCats].values < self.statDF[negCats_opp].values).sum(axis=1)
        self.statDF['cat_losses'] = (self.statDF[posCats].values < self.statDF[posCats_opp].values).sum(axis=1) + \
                                  (self.statDF[negCats].values > self.statDF[negCats_opp].values).sum(axis=1)
        self.statDF['cat_ties'] = len(mainCats)-(self.statDF[['cat_wins', 'cat_losses']]).sum(axis=1)

        self.statDF['matchup_win'] = (self.statDF['cat_wins'] > self.statDF['cat_losses']).astype(int)
        self.statDF['matchup_loss'] = (self.statDF['cat_wins'] < self.statDF['cat_losses']).astype(int)
        self.statDF['matchup_tie'] = (self.statDF['cat_wins'] == self.statDF['cat_losses']).astype(int)

        self.statDF['matchup_length'] = self.statDF.apply(lambda row: float(playoffRoundLength[row['Year']])
                                if row['Week Name'].startswith('P') else 1.0, axis=1)
        self._apply_global_count_flags()
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
        self.roundLength = playoffRoundLength[self.year]

        self.PO_currentWeek = min(getLastWeek(self.year), self.PO_weeks) if self.year == currentYear else self.PO_weeks

        self.PO_time = False if self.PO_currentWeek <= self.RSweekCount else True
        self.PO_teams = []
        self.PO_seeding = {}
        self.PO_matchups_by_week = {"Final":None, "3rd Place":None}
        self.PO_champ = None
        self.PO_results = {}
        self.PO_standings = {}

        if self.PO_time and self.rounds > 0:
            # if standings need to be overwritten
            if self.year in standingsOverwrite:
                self.PO_teams = list(standingsOverwrite[self.year].values())[:playoffTeamCount[self.year]]
                self.PO_seeding = {i + 1:name for i, name in enumerate(self.PO_teams)}

            # standings don't need to be overwritten
            else:
                for i in range(1,playoffTeamCount[self.year]+1):
                    if self.is_WL:
                        self.PO_teams.append(self.get_WL_standings()[i][0])
                        self.PO_seeding[i] = self.get_WL_standings()[i][0]
                    else:
                        self.PO_teams.append(self.get_Cats_standings()[i][0])
                        self.PO_seeding[i] = self.get_Cats_standings()[i][0]

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
                self.PO_matchups_by_week[week] = []

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
                            self.PO_matchups_by_week[week].append(newMatchup)
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
        self.elim_week = {}
        thirdPlace = []
        for week in range(self.RSweekCount + 1, self.PO_currentWeek + 1):
            # print(f"eliminated teams: {elimTeams}")
            remover = []

            for matchup_obj in self.PO_matchups_by_week[week]:
                ## remove BYE week matchups (during first round)
                if matchup_obj.is_BYE:
                    remover.append(matchup_obj)

            for matchup_obj in self.PO_matchups_by_week[week]:
                # Resolve playoff ties using league tiebreak order so elimination
                # and bracket advancement are deterministic.
                if matchup_obj.is_tied and not matchup_obj.is_BYE:
                    self._resolve_playoff_tie(matchup_obj)

                ## if past the first week, remove any matchups that include eliminated teams
                if week > self.RSweekCount + 1:
                    if matchup_obj.team1 in elimTeams or matchup_obj.team2 in elimTeams:
                        remover.append(matchup_obj)
                    # print(f"past first week remover: {remover}")

                ## teams that lost in quarterfinals or earlier are added to eliminated teams
                if week < self.RSweekCount + self.rounds-1:
                    loser = self._effective_loser(matchup_obj)
                    if loser:
                        elimTeams.append(loser)
                        self.elim_week[loser] = week
                        self.PO_results[loser] = 'Below Top 4'
                    # print(f"loser: {matchup_obj.loser}")

                ## teams that lost in the semi-final are added to third place game
                elif week == self.RSweekCount + self.rounds-1:
                    loser = self._effective_loser(matchup_obj)
                    if loser:
                        thirdPlace.append(loser)

                ## in final week, teams in 3rd place list are part of 3rd place game
                ## teams not in 3rd place list are part of final
                elif week == self.RSweekCount + self.rounds:
                    if matchup_obj.team1 in thirdPlace or matchup_obj.team2 in thirdPlace:
                        self.PO_matchups_by_week['3rd Place'] = matchup_obj
                    else:
                        self.PO_matchups_by_week['Final'] = matchup_obj

                for matchup_obj in remover:
                    try:
                        self.PO_matchups_by_week[week].remove(matchup_obj)
                        self.statDF = self.statDF.loc[~((self.statDF['Week'] == week) & \
                                                      (self.statDF['Team'].isin(matchup_obj.teams)))]
                    except:
                        pass
                    # print(self.statDF.loc[self.statDF['Week']>self.RSweekCount][['Week','Team','Opp']])

        if self.PO_currentWeek==self.PO_weeks:
            # if self.POmatchupsByWeek['Final']:
            self.PO_champ = self.get_PO_winner()
            final_matchup = self.PO_matchups_by_week['Final']
            third_place_matchup = self.PO_matchups_by_week['3rd Place']
            self.PO_standings = {
                1: self.PO_champ,
                2: self._effective_loser(final_matchup) if final_matchup else None,
                3: self._effective_winner(third_place_matchup) if third_place_matchup else None,
                4: self._effective_loser(third_place_matchup) if third_place_matchup else None
            }

            for standing in self.PO_standings:
                team = self.PO_standings[standing]
                if team:
                    self.PO_results[team] = standing

        # Enforce strict playoff counting semantics in the season dataframe:
        # remove/count-out any playoff-week rows involving teams that are not
        # in the championship playoff field after excluding pre-semifinal exits.
        self._apply_playoff_count_flags()

    def _h2h_record_score(self, team_a: str, team_b: str):
        # Use only direct regular-season matchups between the two teams.
        # This avoids overcounting from expanded dataframe views.
        matchup_score = 0.0
        cat_score = 0.0
        for m in self.matchups:
            if not m.is_reg or not m.count or m.is_BYE:
                continue
            if {m.team1, m.team2} != {team_a, team_b}:
                continue

            if m.team1 == team_a:
                matchup_score += 1.0 if m.winner == team_a else 0.49 if m.is_tied else 0.0
                cat_score += float(m.wins + 0.49 * m.ties)
            else:
                matchup_score += 1.0 if m.winner == team_a else 0.49 if m.is_tied else 0.0
                cat_score += float(m.losses + 0.49 * m.ties)
        return matchup_score, cat_score

    def _resolve_playoff_tie(self, matchup_obj):
        team1 = matchup_obj.team1
        team2 = matchup_obj.team2

        t1_h2h, t1_h2h_cat = self._h2h_record_score(team1, team2)
        t2_h2h, t2_h2h_cat = self._h2h_record_score(team2, team1)

        # 1) H2H record
        if round(t1_h2h, 6) != round(t2_h2h, 6):
            winner = team1 if t1_h2h > t2_h2h else team2
            reason = "H2H record"
        # 2) H2H category record
        elif round(t1_h2h_cat, 6) != round(t2_h2h_cat, 6):
            winner = team1 if t1_h2h_cat > t2_h2h_cat else team2
            reason = "H2H category record"
        # 3) Final seeding (better seed = lower number)
        else:
            seed_by_team = {team: seed for seed, team in (self.PO_seeding or {}).items()}
            s1 = seed_by_team.get(team1, 999)
            s2 = seed_by_team.get(team2, 999)
            winner = team1 if s1 <= s2 else team2
            reason = "Final seeding"

        loser = team2 if winner == team1 else team1
        matchup_obj.official_winner = winner
        matchup_obj.official_loser = loser
        matchup_obj.tiebreak_applied = True
        matchup_obj.tiebreak_reason = reason
        return winner, loser

    def _effective_winner(self, matchup_obj):
        if matchup_obj is None:
            return None
        return getattr(matchup_obj, "official_winner", None) or matchup_obj.winner

    def _effective_loser(self, matchup_obj):
        if matchup_obj is None:
            return None
        return getattr(matchup_obj, "official_loser", None) or matchup_obj.loser

    def _apply_playoff_count_flags(self):
        if self.statDF is None or self.statDF.empty:
            return None

        po_mask = self.statDF["Week Name"].astype(str).str.startswith("P")
        if not po_mask.any():
            return None

        elim_week = getattr(self, "elim_week", None) or {}
        if not elim_week:
            return None

        # A team eliminated in an early playoff round should stop counting for
        # weeks strictly AFTER their elimination week -- not the elimination
        # week itself, which is the real game that eliminated them and must
        # still count. (Using a static "not in the final top-4 field" check
        # here previously zeroed out the elimination-round game entirely --
        # including the winner's row, since the winner's Opp was the very
        # team just eliminated -- which silently dropped week-19-style
        # play-in rounds whenever a team was actually eliminated there.)
        def eliminated_before_this_week(team_col: str):
            elim_at = self.statDF[team_col].map(elim_week)
            return elim_at.notna() & (self.statDF["Week"] > elim_at)

        non_count_mask = po_mask & (
            eliminated_before_this_week("Team") | eliminated_before_this_week("Opp")
        )
        if non_count_mask.any():
            if "Count" in self.statDF.columns:
                self.statDF.loc[non_count_mask, "Count"] = False
            if "real_matchup" in self.statDF.columns:
                self.statDF.loc[non_count_mask, "real_matchup"] = 0
        return None

    def get_PO_winner(self):
        if playoffTeamCount[self.year] == 0 or self.PO_matchups_by_week['Final']==None:
            # print(f"the {year - 1}/{year} season did not have any Playoffs\nThe Regular Season Champ was {self.get_rsWinnerWL()}")
            return None
        else:
            return self._effective_winner(self.PO_matchups_by_week['Final'])

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
    rs = regSeason(2020)
    # print(rs.get_WL_standings())
    print(rs.get_swapped_schedule_standings('Fano', 'Sama'))
    print(rs.get_WL_standings())

    # x = poSeason(2025)
    # print(x.PO_currentWeek)
    # print(x.PO_time)
    # print(x.PO_matchups_by_week)
    # print(x.statDF[['Week', 'Team', 'Opp', 'real_matchup', 'week_rating_opp']])
    # print(x.statDF.columns)
    # print(x.statDF.loc[x.statDF['Week']==1][['PTS', 'PTS_rank', 'PTS_rating', 'TO', 'TO_rank', 'TO_rating']].sort_values('TO'))
    # y = poSeason(2024)
    # print(y.statDF.loc[y.statDF['Week']>18][['Week','Team','Opp']])
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

    pass
