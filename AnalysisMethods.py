import matplotlib.pyplot as plt
from Models.League import *
from constants import *
import pandas as pd
import numpy as np
import seaborn as sns

def cat_rating_v_season_winP_WL(league: fantasyLeague, scatterPlot = False, corrPlot = False):
    season_cat_ratings = {cat:[] for cat in mainCats}
    season_winP_WL = []

    xlab = 'Category Ratings'
    ylab = 'WL Win%'

    for team in league.historicalMembers:
        for year in team.regSeasons:
            team_season = team.regSeasons[year]
            try:
                for cat in mainCats:
                    season_cat_ratings[cat].append(team_season.get_team_avg_cat_ratings()[cat])
                season_winP_WL.append(team_season.get_team_record_WL(format='p'))
            except ZeroDivisionError:
                pass

    if scatterPlot:
        f = plt.figure()
        f, axes = plt.subplots(nrows=3, ncols=3, sharex=True, sharey=True)
        x, y = 0, 0
        for cat in season_cat_ratings:
            if x == 3:
                x = 0
                y += 1
            axes[x][y].scatter(season_cat_ratings[cat], season_winP_WL)
            axes[x][y].set_title(cat)
            axes[x][y].set_xlim(10, 1)
            x += 1
        for ax in axes.flat:
            ax.set(xlabel=xlab, ylabel=ylab)
            ax.label_outer()
        plt.show()

    df = pd.DataFrame(season_cat_ratings)
    df[ylab] = season_winP_WL
    corrMat = df.corr()
    if corrPlot:
        corrMat.loc[ylab].plot(kind='barh')
        plt.show()
        sns.heatmap(corrMat, annot=True, cmap='coolwarm')
        plt.show()

    return corrMat

def cat_rating_v_season_winP_Cats(league: fantasyLeague, scatterPlot = False, corrPlot = False):
    season_cat_ratings = {cat:[] for cat in mainCats}
    season_winP_Cats = []

    xlab = 'Category Ratings'
    ylab = 'Category Win%'

    for team in league.historicalMembers:
        for year in team.regSeasons:
            team_season = team.regSeasons[year]
            try:
                for cat in mainCats:
                    season_cat_ratings[cat].append(team_season.get_team_avg_cat_ratings()[cat])
                season_winP_Cats.append(team_season.get_team_record_Cats(format='p'))
            except ZeroDivisionError:
                pass

    if scatterPlot:
        f = plt.figure()
        f, axes = plt.subplots(nrows=3, ncols=3, sharex=True, sharey=True)
        x, y = 0, 0
        for cat in season_cat_ratings:
            if x == 3:
                x = 0
                y += 1
            axes[x][y].scatter(season_cat_ratings[cat], season_winP_Cats)
            axes[x][y].set_title(cat)
            axes[x][y].set_xlim(10, 1)
            # axes[x][y].set_ylim(0, 1)
            x += 1
        axes.set_title(f"{xlab} vs. {ylab}")
        for ax in axes.flat:
            ax.set(xlabel=xlab, ylabel=ylab)
            ax.label_outer()
        plt.show()

    df = pd.DataFrame(season_cat_ratings)
    df[ylab] = season_winP_Cats
    corrMat = df.corr()
    if corrPlot:
        corrMat.loc[ylab].plot(kind='barh')
        # plt.xlabel = 'Correlation Coefficient'
        # plt.ylabel = 'Stat Category'
        plt.show()
        sns.heatmap(corrMat, annot=True, cmap='coolwarm')
        plt.show()

    return corrMat


def season_rating_v_season_winP_cats(league: fantasyLeague, scatterPlot = False):
    season_ratings = []
    season_winP = []

    xlab = 'Season Team Ratings'
    ylab = 'Category Win%'

    for team in league.historicalMembers:
        for year in team.regSeasons:
            team_season = team.regSeasons[year]
            try:
                season_ratings.append(team_season.get_team_avg_rating())
                season_winP.append(team_season.get_team_record_WL(format='p'))
            except ZeroDivisionError:
                pass

    x, y = np.array(season_ratings), np.array(season_winP)

    # Fit a linear regression line
    coefficients = np.polyfit(x, y, 1)  # Linear regression (degree=1)
    slope, intercept = coefficients
    y_pred = slope * x + intercept  # Predicted y values

    # Calculate R^2
    ss_res = np.sum((y - y_pred) ** 2)  # Residual sum of squares
    ss_tot = np.sum((y - np.mean(y)) ** 2)  # Total sum of squares
    r_2 = 1 - (ss_res / ss_tot)
    print(r_2)

    if scatterPlot:
        f = plt.figure()
        f, axes = plt.subplots(nrows=1, ncols=1, sharex=True, sharey=True)
        axes.scatter(season_ratings, season_winP)
        axes.plot(x, y_pred, color='red', label=f'Fit Line ($R^2$ = {r_2:.2f})')
        axes.set_title(f"{xlab} vs. {ylab}")
        axes.set_xlim(10,1)
        # axes.set_ylim()
        axes.set(xlabel=xlab, ylabel=ylab)
        axes.annotate("r-squared = {:.3f}".format(r_2), (9.75, 0.8))
        plt.show()


def cat_rating_v_season_rating(league: fantasyLeague, scatterPlot = False, corrPlot = False):

    season_team_ratings = []
    season_cat_ratings = {cat: [] for cat in mainCats}

    for team in league.historicalMembers:
        for year in team.regSeasons:
            team_season = team.regSeasons[year]
            try:
                for cat in mainCats:
                    season_cat_ratings[cat].append(team_season.get_team_avg_cat_ratings()[cat])
                season_team_ratings.append(team_season.get_team_avg_rating())
            except ZeroDivisionError:
                pass

    xlab = 'Season Category Ratings'
    ylab = 'Season Team Ratings'

    if scatterPlot:
        f = plt.figure()
        f, axes = plt.subplots(nrows=3, ncols=3, sharex=True, sharey=True)
        x, y = 0, 0
        for cat in season_cat_ratings:
            if x == 3:
                x = 0
                y += 1
            axes[x][y].scatter(season_cat_ratings[cat], season_team_ratings)
            axes[x][y].set_title(cat)
            axes[x][y].set_xlim(10, 1)
            axes[x][y].set_ylim(10, 1)
            x += 1

        for ax in axes.flat:
            ax.set(xlabel=xlab, ylabel=ylab)
            ax.label_outer()
        plt.show()

    df = pd.DataFrame(season_cat_ratings)
    df[ylab] = season_team_ratings
    corrMat = df.corr()
    if corrPlot:
        corrMat.loc[ylab].plot(kind='barh')
        plt.show()
        sns.heatmap(corrMat, annot=True, cmap='coolwarm')
        plt.show()

    return corrMat

def cat_rating_v_week_rating(league: fantasyLeague, scatterPlot = False, corrPlot = False):
    weekly_ratings = []
    weekly_cat_ratings = {cat: [] for cat in mainCats}

    xlab = 'Category Ratings'
    ylab = 'Weekly Team Ratings'

    for year in league.seasons:
        season = league.seasons[year]
        reg = season.regSsn
        for week in range(1, reg.currentWeek + 1):
            for team in season.teams:
                try:
                    weekly_ratings.append(reg.get_week_rankings(week, sortedRetrun=False)[team])
                    for cat in mainCats:
                        weekly_cat_ratings[cat].append(reg.get_week_cat_rankings(week)[team][cat])
                except (KeyError, ZeroDivisionError):
                    pass

    if scatterPlot:
        f = plt.figure()
        f, axes = plt.subplots(nrows=3, ncols=3, sharex=True, sharey=True)

        x, y = 0, 0
        for cat in weekly_cat_ratings:
            if x == 3:
                x = 0
                y += 1

            x_data = np.array(weekly_cat_ratings[cat])
            y_data = np.array(weekly_ratings)

            # Fit a linear regression line
            coefficients = np.polyfit(x_data, y_data, 1)  # Linear regression (degree=1)
            slope, intercept = coefficients
            y_pred = slope * x_data + intercept  # Predicted y values

            # Calculate R^2
            ss_res = np.sum((y_data - y_pred) ** 2)  # Residual sum of squares
            ss_tot = np.sum((y_data - np.mean(y)) ** 2)  # Total sum of squares
            r_2 = 1 - (ss_res / ss_tot)
            print(r_2)

            axes[x][y].scatter(x_data, y_data, s=2)
            axes[x][y].set_title(cat)
            axes[x][y].set_xlim(10, 1)
            axes[x][y].set_ylim(10, 1)
            x += 1

        for ax in axes.flat:
            ax.set(xlabel=xlab, ylabel=ylab)
            ax.label_outer()

        plt.show()

    df = pd.DataFrame(weekly_cat_ratings)
    df[ylab] = weekly_ratings
    corrMat = df.corr()
    if corrPlot:
        corrMat.loc[ylab].plot(kind='barh')
        plt.show()
        sns.heatmap(corrMat, annot=True, cmap='coolwarm')
        plt.show()

    return corrMat


if __name__ == '__main__':
    pass

    league = fantasyLeague()

    # print(cat_rating_v_season_winP_WL(league, scatterPlot=True, corrPlot=True))
    # print(cat_rating_v_season_winP_Cats(league, scatterPlot=False, corrPlot=True))

    # print(season_rating_v_season_winP_cats(league, scatterPlot=True))

    # print(cat_rating_v_season_rating(league, scatterPlot=False, corrPlot = True))
    print(cat_rating_v_week_rating(league, scatterPlot=True, corrPlot=True))


    # for team in league.historicalMembers:
    #     print(team)
    #     years = [year for year in team.yearsPlayed]
    #
    #     avg_rating = team.get_avg_rating()
    #
    #     win_pct_WL = team.get_career_record_WL(0, 0, 'p')
    #
    #     win_pct_Cats = team.get_career_record_Cats(0, 0, 'p')
    #
    #     year_win_pct_WL = [team.get_career_record_WL(0, endYear, 'p')
    #                        for endYear in range(team.yearsPlayed[0], team.yearsPlayed[-1] + 1)]
    #
    #     year_win_pct_Cats = [team.get_career_record_Cats(team.yearsPlayed[0], endYear, 'p')
    #                          for endYear in range(team.yearsPlayed[0], team.yearsPlayed[-1] + 1)]
    #
    #     totalWins_WL = [team.get_career_record_WL(team.yearsPlayed[0], endYear)['wins']
    #                     for endYear in range(team.yearsPlayed[0], team.yearsPlayed[-1] + 1)]
    #
    #     totalTies_Cats = [team.get_career_record_Cats(team.yearsPlayed[0], endYear)['ties']
    #                       for endYear in range(team.yearsPlayed[0], team.yearsPlayed[-1] + 1)]
    #
    #     total_CAT = [team.get_career_totals(team.yearsPlayed[0], endYear)['FG%']
    #                  for endYear in range(team.yearsPlayed[0], team.yearsPlayed[-1] + 1)]
    #
    #     yearly_CAT = [team.get_career_totals(endYear, endYear)['PTS']
    #                   for endYear in range(team.yearsPlayed[0], team.yearsPlayed[-1] + 1)]
    #
    #     car_draft_score = [team.get_career_draft_score(team.yearsPlayed[0], endYear)
    #                        for endYear in range(team.yearsPlayed[0], team.yearsPlayed[-1] + 1)]
    #
    #     season_rankings = {rSeason.year: rSeason.getAvgRating() for rSeason in team.regSeasons.values()}
    #
    #     season_record_WL = {rSeason.year: rSeason.getRecordWL(format = 'p') for rSeason in team.regSeasons.values()}
    #
    #     season_record_Cats = {rSeason.year: rSeason.getRecordCats(format = 'p') for rSeason in team.regSeasons.values()}
    #
    #     # plt.plot(years, total_CAT, label=team.name, marker=f"${team.name[:3]}$",
    #     #          markersize=15, linestyle=None)
    #     #
    #     # x, y, = list(season_rankings.values()), list(season_record_WL.values())
    #     # plt.scatter(x, y, label=f"{team}",
    #     #             # marker=f"${team.name[:2]}$",
    #     #             s=10, c="k")
    #     #
    #     # for i in range(len(x)):
    #     #     plt.annotate(f"{abbMembers[team.name]}{list(team.regSeasons.keys())[i]-2000}", (x[i], y[i]))
    #
    #     fig, ax = plt.subplots(3,3)
    #
    #     CAT_comparison = {cat: [] for cat in league.statCats}
    #     x = list(season_rankings.values())
    #     for cat in league.statCats:
    #         for season in list(team.regSeasons.values()):
    #             CAT_comparison[cat].append(season.getAverages()[cat] / season.getLeagueAvgs()[cat])
    #         y = CAT_comparison[cat]
    #         ax.scatter(x,y)
    #         # plt.scatter(list(season_rankings.values()), CAT_comparison[cat], label=cat, marker=f"${cat[:2]}$")

    # plt.plot(year, [1 for year in team.yearsPlayed], linestyle='--', marker=None)

    # plt.legend(loc='upper right', bbox_to_anchor=(0.5, 1.05), ncol=3, fancybox=True, shadow=True)
    # plt.grid(visible=True, which='both', axis='both')
    # plt.title(f"{team.name}")
    # plt.show()