import pandas as pd
from Models.TeamManager import *

def _record_dict_to_str(r: dict) -> str:
    if not isinstance(r, dict):
        return ""
    return f"{r.get('wins', 0)}-{r.get('losses', 0)}-{r.get('ties', 0)}"

def get_longest_win_streak(df: pd.DataFrame, year_reset = True) -> int:
    if df is None or df.empty:
        return 0

    df = df.sort_values(["Year", "Week"])
    streak = best = 0
    oldYear = df.iloc[0]["Year"]  # scalar, not a 1-row Series

    for _, row in df.iterrows():
        year = row["Year"]
        if year_reset:
            if year != oldYear:
                streak = 0

        win = int(row.get("matchup_win", 0) or 0)
        loss = int(row.get("matchup_loss", 0) or 0)

        if win == 1:
            streak += 1
            best = max(best, streak)
        else:
            # loss (or anything else): reset streak
            streak = 0

        oldYear = year

    return best

def get_longest_undefeated_streak(df: pd.DataFrame, year_reset = True) -> int:
    if df is None or df.empty:
        return 0

    df = df.sort_values(["Year", "Week"])
    streak = best = 0
    oldYear = df.iloc[0]["Year"]  # scalar, not a 1-row Series

    for _, row in df.iterrows():
        year = row["Year"]
        if year_reset:
            if year != oldYear:
                streak = 0

        win = int(row.get("matchup_win", 0) or 0)
        loss = int(row.get("matchup_loss", 0) or 0)

        if win == 1:
            streak += 1
            best = max(best, streak)
        elif win == 0 and loss == 0:
            # tie / no-result: don't reset streak
            pass
        else:
            # loss (or anything else): reset streak
            streak = 0

        oldYear = year

    return best


def get_longest_loss_streak(df: pd.DataFrame, year_reset = True) -> int:
    if df is None or df.empty:
        return 0

    df = df.sort_values(["Year", "Week"])
    streak = worst = 0
    oldYear = df.iloc[0]["Year"]  # scalar, not a 1-row Series

    for _, row in df.iterrows():
        year = row["Year"]
        if year_reset:
            if year != oldYear:
                streak = 0

        win = int(row.get("matchup_win", 0) or 0)
        loss = int(row.get("matchup_loss", 0) or 0)

        if loss == 1:
            streak += 1
            worst = max(worst, streak)
        else:
            # loss (or anything else): reset streak
            streak = 0

        oldYear = year

    return worst

def build_team_summary_df(teams: list | None = None, reuse_managers: dict | None = None) -> pd.DataFrame | None:
    """
    Returns 1 row per team with:
    - Playoffs: playoff seasons, chips, finals
    - Records: career/RS/PO WL + Cats, longest win streak
    - Ratings/Standings: MVP count, RS chip count, avg rating, #1 rating count, lowest rating count,
                         avg opp rating, ratio
    - Draft: overall/avg + best/worst score + season
    """
    if not teams and not reuse_managers:
        return None

    # Build dict of teamManager objects (or use provided ones)
    managers = {name: teamManager(name) for name in teams} if not reuse_managers else reuse_managers
    if not teams:
        teams = managers.keys()

    # --- MVP count + MVP years: for each year, find the team(s) with best (lowest) avg RS rating
    mvp_count = {name: 0 for name in allMembers}
    mvp_years = {name: [] for name in allMembers}

    years_all = sorted({y for tm in managers.values() for y in tm.yearsPlayed})

    for year in years_all:
        teams_that_year = [t for t in allMembers if year in managers[t].yearsPlayed]
        if not teams_that_year:
            continue

        year_avg = {}
        for t in teams_that_year:
            try:
                year_avg[t] = float(managers[t].regSeasons[year].get_team_avg_rating())
            except Exception:
                pass

        if not year_avg:
            continue

        best_val = min(year_avg.values())
        winners = [t for t, v in year_avg.items() if v == best_val]

        for w in winners:
            mvp_count[w] += 1
            mvp_years[w].append(year)

    rows = []

    # Precompute "lowest rating (worst rank) in week" flags per team for RS only
    # We compute per-year-week max rank and count where team rank == that max.
    def _lowest_rating_count_rs(tm: teamManager) -> int:
        df = tm.get_filtered_df(RS=True, PO=False, real=True)
        if df.empty or "week_rank" not in df.columns:
            return 0
        wk_max = df.groupby(["Year", "Week"])["week_rank"].transform("max")
        return int((df["week_rank"] == wk_max).sum())

    for name in teams:
        tm = managers[name]

        # --- Playoffs
        playoff_years = []
        finals_years = []
        chips_years = []

        for y in tm.yearsPlayed:
            po = tm.playoffs.get(y)
            if po is None:
                continue

            try:
                rounds = po.get_team_rounds_played()
            except Exception:
                rounds = 0

            if rounds and rounds > 0:
                playoff_years.append(y)

                # Finals: treat final standing 1 or 2 as "made finals"
                try:
                    standing = po.get_team_final_standing()
                    if standing in (1, 2):
                        finals_years.append(y)
                except Exception:
                    pass

        # chips by year (uses your existing method)
        po_chips_by_year = tm.get_PO_chips()
        chips_years = [y for y, v in po_chips_by_year.items() if v == 1]

        # --- Records (df-based so it matches your compStatDF definitions)
        # --- Records (dict + win% using your built-in 0.49 tie weight)
        career_wl = tm.get_career_record_WL_df(RS=True, PO=True, format="r")
        career_wl_pct = tm.get_career_record_WL_df(RS=True, PO=True, format="p")

        rs_wl = tm.get_career_record_WL_df(RS=True, PO=False, format="r")
        rs_wl_pct = tm.get_career_record_WL_df(RS=True, PO=False, format="p")

        po_wl = tm.get_career_record_WL_df(RS=False, PO=True, format="r")
        po_wl_pct = tm.get_career_record_WL_df(RS=False, PO=True, format="p")

        career_cats = tm.get_career_record_Cats_df(RS=True, PO=True, format="r")
        career_cats_pct = tm.get_career_record_Cats_df(RS=True, PO=True, format="p")

        rs_cats = tm.get_career_record_Cats_df(RS=True, PO=False, format="r")
        rs_cats_pct = tm.get_career_record_Cats_df(RS=True, PO=False, format="p")

        po_cats = tm.get_career_record_Cats_df(RS=False, PO=True, format="r")
        po_cats_pct = tm.get_career_record_Cats_df(RS=False, PO=True, format="p")

        # Longest win streak (career, RS+PO, real matchups only)
        streak_df = tm.get_filtered_df(RS=True, PO=True, real=True)[["Year", "Week", "Opp", "matchup_win", "matchup_loss"]]

        longest_win_streak = get_longest_win_streak(streak_df)
        longest_undefeated_streak = get_longest_undefeated_streak(streak_df)
        longest_loss_streak = get_longest_loss_streak(streak_df)

        longest_win_streak_no_reset = get_longest_win_streak(streak_df, year_reset=False)
        longest_undefeated_streak_no_reset = get_longest_undefeated_streak(streak_df, year_reset=False)
        longest_loss_streak_no_reset = get_longest_loss_streak(streak_df, year_reset=False)

        # --- Ratings/Standings (RS only)
        rs_df = tm.get_filtered_df(RS=True, PO=False, real=True)

        avg_rating = float(rs_df["week_rating"].mean()) if not rs_df.empty else 0.0
        avg_opp_rating = float(rs_df["week_rating_opp"].mean()) if (not rs_df.empty and "week_rating_opp" in rs_df.columns) else 0.0
        ratio_rating_to_opp = (avg_rating / avg_opp_rating) if avg_opp_rating != 0 else None

        num_rank_1_weeks = int((rs_df["week_rank"] == 1).sum()) if (not rs_df.empty and "week_rank" in rs_df.columns) else 0
        lowest_rating_count = int((rs_df["week_rating"] == 0).sum()) if (not rs_df.empty and "week_rank" in rs_df.columns) else 0

        # RS chips
        rs_chips_by_year = tm.get_RS_chips()
        rs_chip_count = int(sum(rs_chips_by_year.values()))
        rs_chip_years = [y for y, v in rs_chips_by_year.items() if v == 1]

        # --- Draft
        draft_scores_by_year = {}
        for y in tm.yearsPlayed:
            d = tm.draftInfo.get(y)
            if d is not None and hasattr(d, "teamScore"):
                draft_scores_by_year[y] = d.teamScore

        overall_draft_score = tm.get_career_draft_score()
        avg_draft_score = tm.get_average_draft_score()

        if draft_scores_by_year:
            best_draft_year = max(draft_scores_by_year, key=lambda y: draft_scores_by_year[y])
            worst_draft_year = min(draft_scores_by_year, key=lambda y: draft_scores_by_year[y])
            best_draft_score = draft_scores_by_year[best_draft_year]
            worst_draft_score = draft_scores_by_year[worst_draft_year]
        else:
            best_draft_year = worst_draft_year = None
            best_draft_score = worst_draft_score = None
        rows.append({
            "Team": name,

            # Playoffs
            "Chips": len(chips_years),
            "Chip Years": ", ".join(map(str, chips_years)),
            "Finals": len(finals_years),
            "Finals Years": ", ".join(map(str, finals_years)),
            "Playoffs": len(playoff_years),
            "Playoff Years": ", ".join(map(str, playoff_years)),

            "MVPs": mvp_count.get(name, 0),
            "MVP Years": ", ".join(map(str, mvp_years.get(name, []))),
            "RS 1st Place": rs_chip_count,
            "RS 1st Years": ", ".join(map(str, rs_chip_years)),

            # Records
            "Career W/L": _record_dict_to_str(career_wl),
            "Career W/L %": career_wl_pct,
            "RS W/L": _record_dict_to_str(rs_wl),
            "RS W/L %": rs_wl_pct,
            "PO W/L": _record_dict_to_str(po_wl),
            "PO W/L %": po_wl_pct,

            "Career Cats": _record_dict_to_str(career_cats),
            "Career Cats %": career_cats_pct,
            "RS Cats": _record_dict_to_str(rs_cats),
            "RS Cats %": rs_cats_pct,
            "PO Cats": _record_dict_to_str(po_cats),
            "PO Cats %": po_cats_pct,

            "Best Win Streak": longest_win_streak,
            "Worst Losing Streak": longest_loss_streak,
            "Best Undefeated Streak": longest_undefeated_streak,
            # "Best Win Streak No Reset": longest_win_streak_no_reset,
            # "Worst Losing Streak No Reset": longest_loss_streak_no_reset,
            # "Best Undefeated Streak No Reset": longest_undefeated_streak_no_reset,

            # Ratings
            "Avg Rating (out of 100)": avg_rating,
            "#1 Rating Weeks": num_rank_1_weeks,
            "Lowest Rating Weeks": lowest_rating_count,
            "Avg Opp Rating (out of 100)": avg_opp_rating,
            "Opponent Rating Ratio": ratio_rating_to_opp,

            # Draft
            "Career Draft Score": overall_draft_score,
            "Avg Draft Score": avg_draft_score,
            "Best Draft Score": best_draft_score,
            "Best Draft Season": best_draft_year,
            "Worst Draft Score": worst_draft_score,
            "Worst Draft Season": worst_draft_year,
        })

    df_out = pd.DataFrame(rows)

    # Optional: a nice default sort
    sort_cols = ["PO Chips (Count)", "RS Chips (Count)", "MVP Count (Best Avg RS Rating)"]
    sort_cols = [c for c in sort_cols if c in df_out.columns]
    if sort_cols:
        df_out = df_out.sort_values(sort_cols, ascending=False).reset_index(drop=True)

    return df_out

if __name__ == '__main__':
    # Example usage:
    summary_df = build_team_summary_df(teams=allMembers)
    print(summary_df[['Team','Best Win Streak', 'Best Undefeated Streak', 'Worst Losing Streak']])
    print(summary_df[['Team', 'MVP Count', 'RS Chips', 'RS Chip Years']])
    # print(summary_df[['Team', 'Undefeated Streak No Reset']])
