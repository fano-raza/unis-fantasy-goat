import matplotlib.pyplot as plt
import matplotlib.axes as axs
import tkinter
from League import *

# Import module
import tkinter as tk
from tkinter import *

# # Create object
# root = Tk()
# # Adjust size
# root.geometry("1000x1000")
# # Change the label text
# def show():
#     label.config(text=clicked.get())
# # Dropdown menu options
# options = range(15)
# # datatype of menu text
# clicked = tk.StringVar()
#
# # initial menu text
# clicked.set("Monday")
#
# # Create Dropdown menu
# drop = OptionMenu(root, clicked, *options)
# drop.pack()
#
# # Create button, it will change label text
# button = Button(root, text="click Me", command=show).pack()
#
# # Create Label
# label = Label(root, text=" ")
# label.pack()
#
# def on_button_toggle():
#     if var.get() == 1:
#         print("Checkbutton is selected")
#     else:
#         print("Checkbutton is deselected")
#
# var = tk.IntVar()
#
# for i in range(10):
#     checkbutton = tk.Checkbutton(root, text="Enable Feature", variable=var,
#                                  onvalue=1, offvalue=0, command=on_button_toggle)
#
#     # Setting options for the Checkbutton
#     checkbutton.config(bg="lightgrey", fg="blue", font=("Arial", 12),
#                        selectcolor="green", relief="raised", padx=10, pady=5)
#
#     # Adding a bitmap to the Checkbutton
#     checkbutton.config(bitmap="info", width=20, height=20)
#
#     # Placing the Checkbutton in the window
#     checkbutton.pack(padx=0, pady=0)
#
#     # Calling methods on the Checkbutton
#     checkbutton.flash()
#
# v1 = DoubleVar()
#
#
# def show1():
#     sel = "Horizontal Scale Value = " + str(v1.get())
#     l1.config(text=sel, font=("Courier", 14))
#
#
# s1 = Scale(root, variable=v1,
#            from_=2019, to=2024,
#            orient=HORIZONTAL)
#
# l3 = Label(root, text="Horizontal Scaler")
#
# b1 = Button(root, text="Display Horizontal",
#             command=show1,
#             bg="yellow")
#
# l1 = Label(root)
#
# s1.pack(anchor=CENTER)
# l3.pack()
# b1.pack(anchor=CENTER)
# l1.pack()
#
# v2 = DoubleVar()
#
#
# def show2():
#     sel = "Vertical Scale Value = " + str(v2.get())
#     l2.config(text=sel, font=("Courier", 14))
#
#
# s2 = Scale(root, variable=v2,
#            from_=50, to=1,
#            orient=VERTICAL)
#
# l4 = Label(root, text="Vertical Scaler")
#
# b2 = Button(root, text="Display Vertical",
#             command=show2,
#             bg="purple",
#             fg="white")
#
# l2 = Label(root)
#
# s2.pack(anchor=CENTER)
# l4.pack()
# b2.pack()
# l2.pack()

# Execute tkinter
# root.mainloop()

if __name__ == '__main__':
    pass
    # name = 'Fano'
    #
    # for season in league.seasons:
    #     year = season.year
    #     # for team in season.teamRegSeasons:
    #     for team in [team_reg_season(name,year)]:
    #         x = team.getAvgRating()
    #         y = team.getPositionCats()
    #         if season.playoffs.PO_champ==team.name:
    #             color="y"
    #         elif team.get_rsWinnerWL()==team.name:
    #             color="g"
    #         else:
    #             color="k"
    #
    #         plt.scatter(x,y,label=f"{team}-{year}",marker=f"${team.name[:3]}:{year-2000}$",
    #                     s=1500,c=color)
    #         plt.plot(range(12),range(12),linestyle='--')
    #
    # plt.grid(visible=True, which='both', axis='both')
    # plt.xlabel("WL Position")
    # plt.ylabel("Category Position")
    # ax = plt.gca()
    # ax.set_xlim([11, 0])
    # ax.set_ylim([11, 0])
    # plt.show()



    # name = 'Sama'
    # team = teamManager(name)
    #
    # year = [year for year in team.yearsPlayed]
    #
    # CAT_comparison = {cat: [] for cat in leagueSeason(2024).statCats}
    #
    # for cat in leagueSeason(2024).statCats:
    #     for year in team.yearsPlayed:
    #         season = team.regSeasons[year]
    #         CAT_comparison[cat].append(season.getAverages()[cat]/season.getLeagueAvgs()[cat])
    #
        # plt.plot(year, CAT_comparison[cat], label=cat, marker=f"${cat[:2]}$",markersize=15,linestyle=None)
    #     plt.plot(year, [1 for year in year], linestyle='--', marker=None)
    #
    #
    # plt.legend(loc='upper center', bbox_to_anchor=(0.5, 1.05), ncol=3, fancybox=True, shadow=True)
    # plt.grid(visible=True, which='both', axis='both')
    # plt.show()

    league = fantasyLeague()

    for team in league.historicalMembers:
        print(team)
        years = [year for year in team.yearsPlayed]

        avg_rating = team.get_avg_rating()

        win_pct_WL = team.get_career_record_WL(0, 0, 'p')

        win_pct_Cats = team.get_career_record_Cats(0, 0, 'p')

        year_win_pct_WL = [team.get_career_record_WL(0, endYear, 'p')
                           for endYear in range(min(team.yearsPlayed), team.yearsPlayed[-1] + 1)]

        year_win_pct_Cats = [team.get_career_record_Cats(min(team.yearsPlayed), endYear, 'p')
                             for endYear in range(min(team.yearsPlayed), team.yearsPlayed[-1] + 1)]

        totalWins_WL = [team.get_career_record_WL(min(team.yearsPlayed), endYear)['wins']
                        for endYear in range(min(team.yearsPlayed), team.yearsPlayed[-1] + 1)]

        totalTies_Cats = [team.get_career_record_Cats(min(team.yearsPlayed), endYear)['ties']
                          for endYear in range(min(team.yearsPlayed), team.yearsPlayed[-1] + 1)]

        total_CAT = [team.get_career_totals(min(team.yearsPlayed), endYear)['FG%']
                     for endYear in range(min(team.yearsPlayed), team.yearsPlayed[-1] + 1)]

        yearly_CAT = [team.get_career_totals(endYear, endYear)['PTS']
                      for endYear in range(min(team.yearsPlayed), team.yearsPlayed[-1] + 1)]

        car_draft_score = [team.get_career_draft_score(min(team.yearsPlayed), endYear)
                           for endYear in range(min(team.yearsPlayed), team.yearsPlayed[-1] + 1)]

        # plt.plot(years, total_CAT, label=team.name, marker=f"${team.name[:3]}$",
        #          markersize=15, linestyle=None)
        #
        # plt.scatter(avg_rating, win_pct_Cats, label=f"{team}", marker=f"${team.name[:3]}$",
        #             s=1500, c="k")

        CAT_comparison = {cat: [] for cat in league.statCats}
        # for cat in league.statCats:
        #     for year in team.yearsPlayed:
                # season = team.regSeasons[year]
                # CAT_comparison[cat].append(season.getAverages()[cat] / season.getLeagueAvgs()[cat])
                # plt.plot(year, CAT_comparison[cat], label=cat, marker=f"${cat[:2]}$", linestyle=None)
        
        i = 0
        for year in team.yearsPlayed:
            x = year
            y = year_win_pct_Cats
            print(y)
            plt.plot(x, y[i], label=team, marker=f"${team.name[:2]}{year-2000}$", linestyle=None, ms = 10)
            i += 1
            
    # plt.plot(year, [1 for year in team.yearsPlayed], linestyle='--', marker=None)

    # plt.legend(loc='upper right', bbox_to_anchor=(0.5, 1.05), ncol=3, fancybox=True, shadow=True)
    plt.grid(visible=True, which='both', axis='both')
    # plt.title(f"{team.name}")
    plt.show()