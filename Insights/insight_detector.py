# insights_engine.py
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


# -------------------------
# Insight object
# -------------------------

@dataclass
class Insight:
    type: str
    year: int
    week: int
    team: str
    opp: Optional[str]
    facts: Dict[str, Any]
    tags: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# -------------------------
# Helpers: filtering
# -------------------------

def _filter_real_games(df: pd.DataFrame, year: int, week: int, rs_only: bool = True) -> pd.DataFrame:
    """
    Returns 1 row per team for the given year/week (real matchups only).
    Expects df has: Year, Week, real_matchup, Week Name.
    """
    out = df[(df["Year"] == year) & (df["Week"] == week)]
    if "real_matchup" in out.columns:
        out = out[out["real_matchup"] >= 1]
    if rs_only and "Week Name" in out.columns:
        out = out[out["Week Name"].astype(str).str.startswith("M")]
    return out


def _filter_real_games_through_week(df: pd.DataFrame, year: int, week: int, rs_only: bool = True) -> pd.DataFrame:
    """
    Returns all real games for that year up to week (inclusive).
    """
    out = df[(df["Year"] == year) & (df["Week"] <= week)]
    if "real_matchup" in out.columns:
        out = out[out["real_matchup"] >= 1]
    if rs_only and "Week Name" in out.columns:
        out = out[out["Week Name"].astype(str).str.startswith("M")]
    return out


# -------------------------
# Helpers: streaks
# -------------------------

def current_streak_len(
    team_df: pd.DataFrame,
    kind: str,
    year_reset: bool = False,
) -> int:
    """
    kind:
      - "win": consecutive matchup_win == 1
      - "loss": consecutive matchup_loss == 1
      - "undefeated": consecutive (win or tie)
    Assumes team_df already filtered to real games and sorted.
    """
    if team_df is None or team_df.empty:
        return 0

    df = team_df.sort_values(["Year", "Week"])

    streak = 0
    last_year = int(df.iloc[-1]["Year"])  # end year
    for _, row in reversed(list(df.iterrows())):
        y = int(row["Year"])

        if year_reset and y != last_year:
            break

        w = int(row.get("matchup_win", 0) or 0)
        l = int(row.get("matchup_loss", 0) or 0)
        t = int(row.get("matchup_tie", 0) or 0)

        if kind == "win":
            ok = (w == 1)
        elif kind == "loss":
            ok = (l == 1)
        elif kind == "undefeated":
            ok = (w == 1 or t == 1)
        else:
            raise ValueError(f"Unknown kind: {kind}")

        if ok:
            streak += 1
        else:
            break

        last_year = y

    return streak


def all_streak_instances(
    team_df: pd.DataFrame,
    kind: str,
    year_reset: bool = True,
) -> List[int]:
    """
    Enumerates EVERY streak length instance for a given team, across the dataframe.
    Useful for "2nd longest of all time" type rankings.

    year_reset=True means streaks do not carry across season boundaries.
    """
    if team_df is None or team_df.empty:
        return []

    df = team_df.sort_values(["Year", "Week"])
    streaks: List[int] = []
    streak = 0
    prev_year = int(df.iloc[0]["Year"])

    def is_ok(row) -> bool:
        w = int(row.get("matchup_win", 0) or 0)
        l = int(row.get("matchup_loss", 0) or 0)
        t = int(row.get("matchup_tie", 0) or 0)
        if kind == "win":
            return w == 1
        if kind == "loss":
            return l == 1
        if kind == "undefeated":
            return (w == 1 or t == 1)
        raise ValueError(f"Unknown kind: {kind}")

    for _, row in df.iterrows():
        y = int(row["Year"])

        if year_reset and y != prev_year:
            if streak > 0:
                streaks.append(streak)
            streak = 0

        if is_ok(row):
            streak += 1
        else:
            if streak > 0:
                streaks.append(streak)
            streak = 0

        prev_year = y

    if streak > 0:
        streaks.append(streak)

    return streaks


def dense_rank_desc(value: int, population: List[int]) -> Tuple[int, bool]:
    """
    Dense rank among UNIQUE lengths (descending).
    Returns (rank, is_tied_at_rank).
      rank=1 means best/longest.
    """
    if value <= 0:
        return (0, False)
    uniq = sorted(set(population), reverse=True)
    if not uniq:
        return (1, False)
    # if value exceeds historical, it becomes new #1
    if value > uniq[0]:
        return (1, False)

    try:
        idx = uniq.index(value)
        rank = idx + 1
        tied = population.count(value) > 1
        return (rank, tied)
    except ValueError:
        # between existing values -> rank after next larger
        larger = [u for u in uniq if u > value]
        rank = len(larger) + 1
        return (rank, False)


# -------------------------
# Detector: streak headline (season + all-time)
# -------------------------

def detect_streak_records(
    *,
    year: int,
    week: int,
    season_stat_df: pd.DataFrame,
    all_time_team_dfs: Dict[str, pd.DataFrame],
    kind: str = "loss",
) -> List[Insight]:
    """
    Example output:
      - "Team X now has the longest losing streak this season"
      - "... and 2nd longest in league history"
    """
    through = _filter_real_games_through_week(season_stat_df, year, week, rs_only=True)

    insights: List[Insight] = []

    # current streak per team (this season)
    season_current: Dict[str, int] = {}
    for team, tdf in through.groupby("Team"):
        season_current[team] = current_streak_len(tdf, kind=kind, year_reset=True)

    # season ranks
    season_values = list(season_current.values())
    season_uniq = sorted(set(season_values), reverse=True)

    # all-time streak population (all instances, across all teams)
    all_instances: List[int] = []
    for team, df in all_time_team_dfs.items():
        # assume caller already filtered df to real games if desired
        all_instances.extend(all_streak_instances(df, kind=kind, year_reset=True))

    # build per-team insight if meaningful
    for team, cur_len in season_current.items():
        if cur_len <= 0:
            continue

        # season rank (dense, among unique lengths)
        s_rank, s_tied = dense_rank_desc(cur_len, season_values)

        # all-time rank (dense, among unique lengths)
        a_rank, a_tied = dense_rank_desc(cur_len, all_instances)

        # only surface if it's notable
        notable = (s_rank == 1) or (a_rank <= 3) or (cur_len >= 4)
        if not notable:
            continue

        insights.append(
            Insight(
                type=f"streak.{kind}",
                year=year,
                week=week,
                team=team,
                opp=None,
                facts={
                    "current_streak": cur_len,
                    "season_rank_dense": s_rank,
                    "season_tied": s_tied,
                    "all_time_rank_dense": a_rank,
                    "all_time_tied": a_tied,
                    "season_best": season_uniq[0] if season_uniq else cur_len,
                    "all_time_best": max(all_instances) if all_instances else cur_len,
                },
                tags=["streak", "records", "season", "all_time"],
            )
        )

    return insights


# -------------------------
# Detector: week superlatives (rating / rank)
# -------------------------

def detect_week_superlatives(
    *,
    year: int,
    week: int,
    season_stat_df: pd.DataFrame,
    top_n: int = 1,
) -> List[Insight]:
    """
    Finds best/worst week_rating and best/worst week_rank for the week.
    """
    wk = _filter_real_games(season_stat_df, year, week, rs_only=True)
    if wk.empty:
        return []

    insights: List[Insight] = []

    if "week_rating" in wk.columns:
        top = wk.sort_values("week_rating", ascending=False).head(top_n)
        bot = wk.sort_values("week_rating", ascending=True).head(top_n)

        for _, row in top.iterrows():
            insights.append(
                Insight(
                    type="week.best_rating",
                    year=year,
                    week=week,
                    team=str(row["Team"]),
                    opp=str(row.get("Opp")) if "Opp" in row else None,
                    facts={"week_rating": float(row["week_rating"])},
                    tags=["week", "rating", "superlative"],
                )
            )
        for _, row in bot.iterrows():
            insights.append(
                Insight(
                    type="week.worst_rating",
                    year=year,
                    week=week,
                    team=str(row["Team"]),
                    opp=str(row.get("Opp")) if "Opp" in row else None,
                    facts={"week_rating": float(row["week_rating"])},
                    tags=["week", "rating", "superlative"],
                )
            )

    if "week_rank" in wk.columns:
        # smaller rank = better (based on your df_build_out)
        best = wk.sort_values("week_rank", ascending=True).head(top_n)
        worst = wk.sort_values("week_rank", ascending=False).head(top_n)

        for _, row in best.iterrows():
            insights.append(
                Insight(
                    type="week.best_rank",
                    year=year,
                    week=week,
                    team=str(row["Team"]),
                    opp=str(row.get("Opp")) if "Opp" in row else None,
                    facts={"week_rank": float(row["week_rank"])},
                    tags=["week", "rank", "superlative"],
                )
            )
        for _, row in worst.iterrows():
            insights.append(
                Insight(
                    type="week.worst_rank",
                    year=year,
                    week=week,
                    team=str(row["Team"]),
                    opp=str(row.get("Opp")) if "Opp" in row else None,
                    facts={"week_rank": float(row["week_rank"])},
                    tags=["week", "rank", "superlative"],
                )
            )

    return insights


# -------------------------
# Detector: upset wins (won despite worse rating)
# -------------------------

def detect_upsets(
    *,
    year: int,
    week: int,
    season_stat_df: pd.DataFrame,
    min_rating_gap: float = 0.12,
) -> List[Insight]:
    """
    Flags wins where team had meaningfully lower week_rating than opponent.
    week_rating is min-max scaled by week in your df_build_out, so gaps are 0..1-ish.
    """
    wk = _filter_real_games(season_stat_df, year, week, rs_only=True)
    if wk.empty:
        return []

    required = {"week_rating", "week_rating_opp", "matchup_win", "Team", "Opp"}
    if not required.issubset(set(wk.columns)):
        return []

    out: List[Insight] = []
    for _, row in wk.iterrows():
        if int(row.get("matchup_win", 0) or 0) != 1:
            continue

        r_team = float(row["week_rating"])
        r_opp = float(row["week_rating_opp"])
        gap = r_team - r_opp  # negative means team "should have" lost

        if gap <= -min_rating_gap:
            out.append(
                Insight(
                    type="matchup.upset",
                    year=year,
                    week=week,
                    team=str(row["Team"]),
                    opp=str(row["Opp"]),
                    facts={
                        "week_rating": r_team,
                        "opp_week_rating": r_opp,
                        "rating_gap": gap,
                        "cat_wins": int(row.get("cat_wins", 0) or 0),
                        "cat_losses": int(row.get("cat_losses", 0) or 0),
                        "cat_ties": int(row.get("cat_ties", 0) or 0),
                    },
                    tags=["matchup", "upset"],
                )
            )

    return out


# -------------------------
# Detector: standings movement (WL-based)
# -------------------------

def compute_wl_standings_from_df(
    df_real_rs: pd.DataFrame,
) -> pd.DataFrame:
    """
    Computes WL standings from a df with matchup_win/loss/tie.
    Returns df indexed by Team with columns: wins, losses, ties, score.
    score = wins + 0.5*ties
    """
    g = df_real_rs.groupby("Team")[["matchup_win", "matchup_loss", "matchup_tie"]].sum()
    g = g.rename(columns={"matchup_win": "wins", "matchup_loss": "losses", "matchup_tie": "ties"})
    g["score"] = g["wins"] + 0.5 * g["ties"]
    # higher score is better
    g = g.sort_values(["score", "wins"], ascending=False)
    g["position"] = range(1, len(g) + 1)
    return g


def detect_standings_swings(
    *,
    year: int,
    week: int,
    season_stat_df: pd.DataFrame,
) -> List[Insight]:
    """
    Detects position changes from week-1 to week in WL standings.
    """
    if week <= 1:
        return []

    prev_df = _filter_real_games_through_week(season_stat_df, year, week - 1, rs_only=True)
    cur_df = _filter_real_games_through_week(season_stat_df, year, week, rs_only=True)

    prev = compute_wl_standings_from_df(prev_df)
    cur = compute_wl_standings_from_df(cur_df)

    out: List[Insight] = []
    for team in cur.index:
        if team not in prev.index:
            continue
        prev_pos = int(prev.loc[team, "position"])
        cur_pos = int(cur.loc[team, "position"])
        delta = prev_pos - cur_pos  # positive means moved up

        if abs(delta) >= 2 or cur_pos == 1 or prev_pos == 1:
            out.append(
                Insight(
                    type="standings.swing",
                    year=year,
                    week=week,
                    team=str(team),
                    opp=None,
                    facts={
                        "prev_position": prev_pos,
                        "cur_position": cur_pos,
                        "delta_positions": delta,
                        "record_prev": f"{int(prev.loc[team,'wins'])}-{int(prev.loc[team,'losses'])}-{int(prev.loc[team,'ties'])}",
                        "record_cur": f"{int(cur.loc[team,'wins'])}-{int(cur.loc[team,'losses'])}-{int(cur.loc[team,'ties'])}",
                    },
                    tags=["standings", "movement", "wl"],
                )
            )

    return out

import pandas as pd
from typing import Dict, List, Tuple, Any, Optional

# ---- helpers ----

def _safe_pct(w: float, l: float, t: float) -> float:
    denom = w + l + t
    return 0.0 if denom <= 0 else (w + 0.5 * t) / denom

def _dense_rank_desc_float(value: float, population: List[float], eps: float = 1e-12) -> Tuple[int, bool]:
    """
    Dense rank among UNIQUE values (descending). Float-safe via rounding-ish eps.
    Returns (rank, tied).
    """
    if population is None or len(population) == 0:
        return (1, False)

    # bucket near-equals to avoid float noise
    def key(x: float) -> float:
        return round(float(x), 10)

    pop = [key(x) for x in population]
    v = key(value)
    uniq = sorted(set(pop), reverse=True)

    if v > uniq[0]:
        return (1, False)

    if v in uniq:
        rank = uniq.index(v) + 1
        tied = pop.count(v) > 1
        return (rank, tied)

    larger = [u for u in uniq if u > v]
    return (len(larger) + 1, False)

def compute_cats_standings_from_df(df_real_rs: pd.DataFrame) -> pd.DataFrame:
    """
    Cats standings based on summed cat_wins/cat_losses/cat_ties.
    score = cat_wins + 0.5*cat_ties
    """
    g = df_real_rs.groupby("Team")[["cat_wins", "cat_losses", "cat_ties"]].sum()
    g["score"] = g["cat_wins"] + 0.5 * g["cat_ties"]
    g = g.sort_values(["score", "cat_wins"], ascending=False)
    g["position"] = range(1, len(g) + 1)
    return g

def detect_standings_swings_cats(*, year: int, week: int, season_stat_df: pd.DataFrame) -> List["Insight"]:
    """
    Detects position changes in Cats standings from week-1 to week.
    """
    if week <= 1:
        return []

    prev_df = _filter_real_games_through_week(season_stat_df, year, week - 1, rs_only=True)
    cur_df  = _filter_real_games_through_week(season_stat_df, year, week, rs_only=True)

    # require cats fields
    req = {"cat_wins", "cat_losses", "cat_ties"}
    if not req.issubset(set(cur_df.columns)) or not req.issubset(set(prev_df.columns)):
        return []

    prev = compute_cats_standings_from_df(prev_df)
    cur  = compute_cats_standings_from_df(cur_df)

    out: List["Insight"] = []
    for team in cur.index:
        if team not in prev.index:
            continue
        prev_pos = int(prev.loc[team, "position"])
        cur_pos  = int(cur.loc[team, "position"])
        delta = prev_pos - cur_pos

        # same threshold logic as WL
        if abs(delta) >= 2 or cur_pos == 1 or prev_pos == 1:
            out.append(
                Insight(
                    type="standings.swing_cats",
                    year=year,
                    week=week,
                    team=str(team),
                    opp=None,
                    facts={
                        "prev_position": prev_pos,
                        "cur_position": cur_pos,
                        "delta_positions": delta,
                        "cats_prev": f"{int(prev.loc[team,'cat_wins'])}-{int(prev.loc[team,'cat_losses'])}-{int(prev.loc[team,'cat_ties'])}",
                        "cats_cur":  f"{int(cur.loc[team,'cat_wins'])}-{int(cur.loc[team,'cat_losses'])}-{int(cur.loc[team,'cat_ties'])}",
                    },
                    tags=["standings", "movement", "cats"],
                )
            )
    return out


# ---- win% + totals detectors ----

def _season_team_totals(df_through: pd.DataFrame) -> pd.DataFrame:
    """
    Returns per-team season-to-date totals for WL and Cats.
    """
    cols_needed = ["matchup_win","matchup_loss","matchup_tie","cat_wins","cat_losses","cat_ties"]
    missing = [c for c in cols_needed if c not in df_through.columns]
    if missing:
        # gracefully handle if some are missing
        pass

    g = df_through.groupby("Team").agg({
        "matchup_win":"sum","matchup_loss":"sum","matchup_tie":"sum",
        "cat_wins":"sum","cat_losses":"sum","cat_ties":"sum",
    }).reset_index()

    g["wl_pct"]   = g.apply(lambda r: _safe_pct(r["matchup_win"], r["matchup_loss"], r["matchup_tie"]), axis=1)
    g["cats_pct"] = g.apply(lambda r: _safe_pct(r["cat_wins"], r["cat_losses"], r["cat_ties"]), axis=1)
    return g

def _career_team_totals(all_time_team_dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Returns per-team career totals for WL and Cats across provided dfs.
    Assumes dfs already filtered to real RS if that’s what you want in “career”.
    """
    rows = []
    for team, df in all_time_team_dfs.items():
        rows.append({
            "Team": team,
            "matchup_win": float(df.get("matchup_win", pd.Series([])).sum()) if len(df) else 0.0,
            "matchup_loss": float(df.get("matchup_loss", pd.Series([])).sum()) if len(df) else 0.0,
            "matchup_tie": float(df.get("matchup_tie", pd.Series([])).sum()) if len(df) else 0.0,
            "cat_wins": float(df.get("cat_wins", pd.Series([])).sum()) if len(df) else 0.0,
            "cat_losses": float(df.get("cat_losses", pd.Series([])).sum()) if len(df) else 0.0,
            "cat_ties": float(df.get("cat_ties", pd.Series([])).sum()) if len(df) else 0.0,
        })
    out = pd.DataFrame(rows)
    out["wl_pct"]   = out.apply(lambda r: _safe_pct(r["matchup_win"], r["matchup_loss"], r["matchup_tie"]), axis=1)
    out["cats_pct"] = out.apply(lambda r: _safe_pct(r["cat_wins"], r["cat_losses"], r["cat_ties"]), axis=1)
    return out

def _historical_team_season_pcts(all_time_team_dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Builds a table of (Team, Year) final-season pcts across history (based on whatever rows you pass in).
    Used for: "this season's win% ranks X among all team-seasons ever".
    """
    frames = []
    for team, df in all_time_team_dfs.items():
        if df is None or df.empty:
            continue
        if "Year" not in df.columns:
            continue
        tmp = df.copy()
        tmp["Team"] = team  # ensure
        frames.append(tmp)

    if not frames:
        return pd.DataFrame(columns=["Team","Year","wl_pct","cats_pct"])

    big = pd.concat(frames, ignore_index=True)

    # group by team-year
    g = big.groupby(["Team","Year"]).agg({
        "matchup_win":"sum","matchup_loss":"sum","matchup_tie":"sum",
        "cat_wins":"sum","cat_losses":"sum","cat_ties":"sum",
    }).reset_index()

    g["wl_pct"]   = g.apply(lambda r: _safe_pct(r["matchup_win"], r["matchup_loss"], r["matchup_tie"]), axis=1)
    g["cats_pct"] = g.apply(lambda r: _safe_pct(r["cat_wins"], r["cat_losses"], r["cat_ties"]), axis=1)
    return g

def detect_win_pcts_and_totals(
    *,
    year: int,
    week: int,
    season_stat_df: pd.DataFrame,
    all_time_team_dfs: Dict[str, pd.DataFrame],
    notable_rank_cutoff: int = 3,
) -> List["Insight"]:
    """
    Emits insights for:
      - season-to-date WL% and Cats% (with ranks vs current season + historical team-seasons)
      - career WL% and Cats% (rank among teams all-time)
      - season-to-date totals W/L/T and Cats W/L/T, plus career totals (rank among teams)
    """
    through = _filter_real_games_through_week(season_stat_df, year, week, rs_only=True)
    if through.empty:
        return []

    season_totals = _season_team_totals(through)
    career_totals = _career_team_totals(all_time_team_dfs)
    hist_season_pcts = _historical_team_season_pcts(all_time_team_dfs)

    # populations for ranking
    season_wl_pcts = season_totals["wl_pct"].tolist()
    season_cats_pcts = season_totals["cats_pct"].tolist()
    career_wl_pcts = career_totals["wl_pct"].tolist()
    career_cats_pcts = career_totals["cats_pct"].tolist()

    hist_wl_pcts = hist_season_pcts["wl_pct"].tolist()
    hist_cats_pcts = hist_season_pcts["cats_pct"].tolist()

    out: List["Insight"] = []

    # per team (season-to-date + career)
    for _, row in season_totals.iterrows():
        team = str(row["Team"])

        # Season pcts
        wl_pct = float(row["wl_pct"])
        cats_pct = float(row["cats_pct"])

        s_wl_rank, s_wl_tied = _dense_rank_desc_float(wl_pct, season_wl_pcts)
        s_c_rank, s_c_tied = _dense_rank_desc_float(cats_pct, season_cats_pcts)

        # Historical team-season ranks (compare current season-to-date to historical season finals)
        h_wl_rank, h_wl_tied = _dense_rank_desc_float(wl_pct, hist_wl_pcts) if hist_wl_pcts else (0, False)
        h_c_rank,  h_c_tied  = _dense_rank_desc_float(cats_pct, hist_cats_pcts) if hist_cats_pcts else (0, False)

        # Career pcts (rank among teams)
        c_row = career_totals[career_totals["Team"] == team]
        if not c_row.empty:
            c_wl = float(c_row.iloc[0]["wl_pct"])
            c_cats = float(c_row.iloc[0]["cats_pct"])
            c_wl_rank, c_wl_tied = _dense_rank_desc_float(c_wl, career_wl_pcts)
            c_c_rank, c_c_tied = _dense_rank_desc_float(c_cats, career_cats_pcts)
        else:
            c_wl = 0.0
            c_cats = 0.0
            c_wl_rank = c_c_rank = 0
            c_wl_tied = c_c_tied = False

        # Totals
        w = int(row["matchup_win"]); l = int(row["matchup_loss"]); t = int(row["matchup_tie"])
        cw = int(row["cat_wins"]);  cl = int(row["cat_losses"]);  ct = int(row["cat_ties"])

        # career totals
        cW = int(c_row.iloc[0]["matchup_win"]) if not c_row.empty else 0
        cL = int(c_row.iloc[0]["matchup_loss"]) if not c_row.empty else 0
        cT = int(c_row.iloc[0]["matchup_tie"]) if not c_row.empty else 0
        cCW = int(c_row.iloc[0]["cat_wins"]) if not c_row.empty else 0
        cCL = int(c_row.iloc[0]["cat_losses"]) if not c_row.empty else 0
        cCT = int(c_row.iloc[0]["cat_tie"]) if ("cat_tie" in c_row.columns and not c_row.empty) else (int(c_row.iloc[0]["cat_ties"]) if not c_row.empty else 0)

        # ranks for career totals (wins/losses/ties)
        wins_pop = career_totals["matchup_win"].tolist()
        losses_pop = career_totals["matchup_loss"].tolist()
        ties_pop = career_totals["matchup_tie"].tolist()
        cwins_pop = career_totals["cat_wins"].tolist()
        closs_pop = career_totals["cat_losses"].tolist()
        ctie_pop = career_totals["cat_ties"].tolist()

        cW_rank, cW_tied = _dense_rank_desc_float(float(cW), [float(x) for x in wins_pop]) if wins_pop else (0, False)
        cL_rank, cL_tied = _dense_rank_desc_float(float(cL), [float(x) for x in losses_pop]) if losses_pop else (0, False)
        cT_rank, cT_tied = _dense_rank_desc_float(float(cT), [float(x) for x in ties_pop]) if ties_pop else (0, False)

        cCW_rank, cCW_tied = _dense_rank_desc_float(float(cCW), [float(x) for x in cwins_pop]) if cwins_pop else (0, False)
        cCL_rank, cCL_tied = _dense_rank_desc_float(float(cCL), [float(x) for x in closs_pop]) if closs_pop else (0, False)
        cCT_rank, cCT_tied = _dense_rank_desc_float(float(cCT), [float(x) for x in ctie_pop]) if ctie_pop else (0, False)

        # ---- Notability rules (you can tune these) ----
        notable_pct = (
            s_wl_rank <= notable_rank_cutoff or
            s_c_rank <= notable_rank_cutoff or
            c_wl_rank <= notable_rank_cutoff or
            c_c_rank <= notable_rank_cutoff or
            (h_wl_rank and h_wl_rank <= notable_rank_cutoff) or
            (h_c_rank and h_c_rank <= notable_rank_cutoff) or
            wl_pct >= 0.70 or cats_pct >= 0.70
        )

        notable_totals = (
            cW_rank <= notable_rank_cutoff or
            cL_rank <= notable_rank_cutoff or
            cCW_rank <= notable_rank_cutoff or
            cCL_rank <= notable_rank_cutoff
        )

        if notable_pct:
            out.append(
                Insight(
                    type="pct.summary",
                    year=year,
                    week=week,
                    team=team,
                    opp=None,
                    facts={
                        "season_wl_pct": wl_pct,
                        "season_wl_rank": s_wl_rank, "season_wl_tied": s_wl_tied,
                        "season_cats_pct": cats_pct,
                        "season_cats_rank": s_c_rank, "season_cats_tied": s_c_tied,

                        "career_wl_pct": c_wl,
                        "career_wl_rank": c_wl_rank, "career_wl_tied": c_wl_tied,
                        "career_cats_pct": c_cats,
                        "career_cats_rank": c_c_rank, "career_cats_tied": c_c_tied,

                        "hist_season_wl_rank": h_wl_rank, "hist_season_wl_tied": h_wl_tied,
                        "hist_season_cats_rank": h_c_rank, "hist_season_cats_tied": h_c_tied,
                    },
                    tags=["pct", "season", "career", "rank"],
                )
            )

        if notable_totals:
            out.append(
                Insight(
                    type="totals.wlt",
                    year=year,
                    week=week,
                    team=team,
                    opp=None,
                    facts={
                        "season_w": w, "season_l": l, "season_t": t,
                        "season_cw": cw, "season_cl": cl, "season_ct": ct,

                        "career_w": cW, "career_l": cL, "career_t": cT,
                        "career_cw": cCW, "career_cl": cCL, "career_ct": cCT,

                        "career_w_rank": cW_rank, "career_w_tied": cW_tied,
                        "career_l_rank": cL_rank, "career_l_tied": cL_tied,
                        "career_t_rank": cT_rank, "career_t_tied": cT_tied,

                        "career_cw_rank": cCW_rank, "career_cw_tied": cCW_tied,
                        "career_cl_rank": cCL_rank, "career_cl_tied": cCL_tied,
                        "career_ct_rank": cCT_rank, "career_ct_tied": cCT_tied,
                    },
                    tags=["totals", "wlt", "cats", "career", "rank"],
                )
            )

    return out


# ---- head-to-head record detector (all-time) ----

def detect_head_to_head_all_time(
    *,
    year: int,
    week: int,
    season_stat_df: pd.DataFrame,
    all_time_team_dfs: Dict[str, pd.DataFrame],
) -> List["Insight"]:
    """
    For each matchup this week, emit an insight for Team vs Opp showing all-time series records.
    """
    wk = _filter_real_games(season_stat_df, year, week, rs_only=True)
    if wk.empty or "Opp" not in wk.columns:
        return []

    out: List["Insight"] = []
    seen_pairs = set()

    for _, row in wk.iterrows():
        team = str(row["Team"])
        opp = str(row["Opp"])

        # avoid duplicates (A vs B and B vs A both appear)
        pair_key = tuple(sorted([team, opp]))
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)

        # compute series from team perspective
        def series(team_name: str, opp_name: str) -> Dict[str, Any]:
            df = all_time_team_dfs.get(team_name)
            if df is None or df.empty:
                return {"w":0,"l":0,"t":0,"cw":0,"cl":0,"ct":0,"games":0}
            d = df[df["Opp"].astype(str) == opp_name]
            return {
                "w": int(d.get("matchup_win", pd.Series([])).sum()) if len(d) else 0,
                "l": int(d.get("matchup_loss", pd.Series([])).sum()) if len(d) else 0,
                "t": int(d.get("matchup_tie", pd.Series([])).sum()) if len(d) else 0,
                "cw": int(d.get("cat_wins", pd.Series([])).sum()) if len(d) else 0,
                "cl": int(d.get("cat_losses", pd.Series([])).sum()) if len(d) else 0,
                "ct": int(d.get("cat_ties", pd.Series([])).sum()) if len(d) else 0,
                "games": int(len(d)),
            }

        a = series(team, opp)
        b = series(opp, team)

        out.append(
            Insight(
                type="h2h.series",
                year=year,
                week=week,
                team=team,
                opp=opp,
                facts={
                    "team_wlt": f"{a['w']}-{a['l']}-{a['t']}",
                    "team_cats": f"{a['cw']}-{a['cl']}-{a['ct']}",
                    "opp_wlt": f"{b['w']}-{b['l']}-{b['t']}",
                    "opp_cats": f"{b['cw']}-{b['cl']}-{b['ct']}",
                    "games": a["games"],  # should equal b["games"]
                },
                tags=["h2h", "history"],
            )
        )

    return out


# ---- 7-2 / 8-1 / 9-0 counts detector ----

def _blowout_bucket(cw: int, cl: int) -> Optional[str]:
    # wins
    if cw == 9 and cl == 0: return "9-0"
    if cw == 8 and cl == 1: return "8-1"
    if cw == 7 and cl == 2: return "7-2"
    # losses
    if cw == 0 and cl == 9: return "0-9"
    if cw == 1 and cl == 8: return "1-8"
    if cw == 2 and cl == 7: return "2-7"
    return None

def _count_blowouts(df: pd.DataFrame) -> Dict[str, int]:
    counts = {"9-0":0,"8-1":0,"7-2":0,"2-7":0,"1-8":0,"0-9":0}
    if df is None or df.empty:
        return counts
    if not {"cat_wins","cat_losses"}.issubset(set(df.columns)):
        return counts
    for _, r in df.iterrows():
        b = _blowout_bucket(int(r["cat_wins"]), int(r["cat_losses"]))
        if b:
            counts[b] += 1
    return counts

def detect_blowout_counts(
    *,
    year: int,
    week: int,
    season_stat_df: pd.DataFrame,
    all_time_team_dfs: Dict[str, pd.DataFrame],
    notable_rank_cutoff: int = 3,
) -> List["Insight"]:
    """
    Detect:
      - if someone had a 9-0 / 8-1 / 7-2 (or got swept) THIS week
      - track season-to-date & career counts and ranks for each bucket
    """
    wk = _filter_real_games(season_stat_df, year, week, rs_only=True)
    through = _filter_real_games_through_week(season_stat_df, year, week, rs_only=True)

    out: List["Insight"] = []

    # per-team counts
    season_counts = {team: _count_blowouts(tdf) for team, tdf in through.groupby("Team")}
    career_counts = {team: _count_blowouts(df) for team, df in all_time_team_dfs.items()}

    # build populations for ranks (by bucket)
    buckets = ["9-0","8-1","7-2","2-7","1-8","0-9"]
    career_pop = {b: [career_counts.get(team, {}).get(b, 0) for team in all_time_team_dfs.keys()] for b in buckets}

    # week-level callouts
    for _, row in wk.iterrows():
        team = str(row["Team"])
        opp = str(row.get("Opp")) if "Opp" in row else None
        cw = int(row.get("cat_wins", 0) or 0)
        cl = int(row.get("cat_losses", 0) or 0)
        b = _blowout_bucket(cw, cl)
        if not b:
            continue

        # ranks for career and season count in that bucket
        season_n = season_counts.get(team, {}).get(b, 0)
        career_n = career_counts.get(team, {}).get(b, 0)

        c_rank, c_tied = _dense_rank_desc_float(float(career_n), [float(x) for x in career_pop[b]]) if career_pop[b] else (0, False)

        notable = (b in ["9-0","0-9"]) or (c_rank and c_rank <= notable_rank_cutoff) or (career_n >= 3)
        if not notable:
            continue

        out.append(
            Insight(
                type="cats.blowout",
                year=year,
                week=week,
                team=team,
                opp=opp,
                facts={
                    "bucket": b,
                    "this_week_line": f"{cw}-{cl}-{int(row.get('cat_ties', 0) or 0)}",
                    "season_count": season_n,
                    "career_count": career_n,
                    "career_rank": c_rank,
                    "career_tied": c_tied,
                },
                tags=["cats", "blowout", "history", "count"],
            )
        )

    return out

from typing import Dict, List, Tuple, Any, Optional
import pandas as pd

def _dense_rank_asc_float(value: float, population: List[float]) -> Tuple[int, bool]:
    # Dense rank among UNIQUE values (ascending). rank=1 means smallest.
    if not population:
        return (1, False)
    def key(x: float) -> float:
        return round(float(x), 10)
    pop = [key(x) for x in population]
    v = key(value)
    uniq = sorted(set(pop))
    if v < uniq[0]:
        return (1, False)
    if v in uniq:
        rank = uniq.index(v) + 1
        tied = pop.count(v) > 1
        return (rank, tied)
    smaller = [u for u in uniq if u < v]
    return (len(smaller) + 1, False)

def _concat_all_time(all_time_team_dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    frames = []
    for team, df in all_time_team_dfs.items():
        if df is None or df.empty:
            continue
        frames.append(df.copy())
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

from typing import Dict, List, Tuple, Any, Optional
import pandas as pd

def _dense_rank_asc_float(value: float, population: List[float]) -> Tuple[int, bool]:
    # Dense rank among UNIQUE values (ascending). rank=1 means smallest.
    if not population:
        return (1, False)
    def key(x: float) -> float:
        return round(float(x), 10)
    pop = [key(x) for x in population]
    v = key(value)
    uniq = sorted(set(pop))
    if v < uniq[0]:
        return (1, False)
    if v in uniq:
        rank = uniq.index(v) + 1
        tied = pop.count(v) > 1
        return (rank, tied)
    smaller = [u for u in uniq if u < v]
    return (len(smaller) + 1, False)

def _concat_all_time(all_time_team_dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    frames = []
    for team, df in all_time_team_dfs.items():
        if df is None or df.empty:
            continue
        frames.append(df.copy())
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

def detect_week_category_extremes(
    *,
    year: int,
    week: int,
    season_stat_df: pd.DataFrame,
    all_time_team_dfs: Dict[str, pd.DataFrame],
    cats: Optional[List[str]] = None,
    lower_is_better: Optional[set] = None,
    top_k: int = 3,
) -> List["Insight"]:
    """
    For each team this week and each category in `cats`, compute:
      - season rank (vs all team-weeks in season up to `week`)
      - all-time rank (vs all team-weeks ever)
    and emit insights if it's top/bottom `top_k` in season or all-time.

    lower_is_better defaults to {"TO"}.
    """
    if lower_is_better is None:
        lower_is_better = {"TO"}

    wk = _filter_real_games(season_stat_df, year, week, rs_only=True)
    if wk.empty:
        return []

    through = _filter_real_games_through_week(season_stat_df, year, week, rs_only=True)
    if through.empty:
        return []

    # default categories: anything that looks like a stat cat and exists in df
    if cats is None:
        # common 9-cat default
        cats = ["FG%", "FT%", "3PTM", "REB", "AST", "STL", "BLK", "TO", "PTS"]
    cats = [c for c in cats if c in wk.columns and c in through.columns]

    all_time_df = _concat_all_time(all_time_team_dfs)
    if all_time_df.empty:
        # still can do season-only ranks
        all_time_df = pd.DataFrame()

    out: List["Insight"] = []

    for cat in cats:
        # build populations (season-to-date, all-time)
        season_pop = pd.to_numeric(through[cat], errors="coerce").dropna().astype(float).tolist()
        all_pop = (
            pd.to_numeric(all_time_df[cat], errors="coerce").dropna().astype(float).tolist()
            if (not all_time_df.empty and cat in all_time_df.columns)
            else []
        )

        if not season_pop:
            continue

        # season extremes for reference
        season_max = max(season_pop)
        season_min = min(season_pop)
        all_max = max(all_pop) if all_pop else None
        all_min = min(all_pop) if all_pop else None

        for _, row in wk.iterrows():
            team = str(row["Team"])
            opp = str(row["Opp"]) if "Opp" in row else None

            val = pd.to_numeric(pd.Series([row[cat]]), errors="coerce").iloc[0]
            if pd.isna(val):
                continue
            val = float(val)

            # ranks in "good direction"
            if cat in lower_is_better:
                # lower is better
                season_best_rank, season_best_tied = _dense_rank_asc_float(val, season_pop)
                season_worst_rank, season_worst_tied = _dense_rank_desc_float(val, season_pop)  # biggest is worst
                all_best_rank, all_best_tied = (_dense_rank_asc_float(val, all_pop) if all_pop else (0, False))
                all_worst_rank, all_worst_tied = (_dense_rank_desc_float(val, all_pop) if all_pop else (0, False))
                direction = "lower_is_better"
            else:
                # higher is better
                season_best_rank, season_best_tied = _dense_rank_desc_float(val, season_pop)
                season_worst_rank, season_worst_tied = _dense_rank_asc_float(val, season_pop)
                all_best_rank, all_best_tied = (_dense_rank_desc_float(val, all_pop) if all_pop else (0, False))
                all_worst_rank, all_worst_tied = (_dense_rank_asc_float(val, all_pop) if all_pop else (0, False))
                direction = "higher_is_better"

            notable = (
                season_best_rank <= top_k or season_worst_rank <= top_k or
                (all_best_rank and all_best_rank <= top_k) or (all_worst_rank and all_worst_rank <= top_k)
            )
            if not notable:
                continue

            # what kind of extreme is it?
            extreme = []
            if season_best_rank <= top_k: extreme.append("season_high" if direction=="higher_is_better" else "season_low")
            if season_worst_rank <= top_k: extreme.append("season_low" if direction=="higher_is_better" else "season_high")
            if all_best_rank and all_best_rank <= top_k: extreme.append("all_time_high" if direction=="higher_is_better" else "all_time_low")
            if all_worst_rank and all_worst_rank <= top_k: extreme.append("all_time_low" if direction=="higher_is_better" else "all_time_high")

            out.append(
                Insight(
                    type="cat.week_extreme",
                    year=year,
                    week=week,
                    team=team,
                    opp=opp,
                    facts={
                        "category": cat,
                        "value": val,
                        "direction": direction,

                        "season_best_rank": season_best_rank,
                        "season_best_tied": season_best_tied,
                        "season_worst_rank": season_worst_rank,
                        "season_worst_tied": season_worst_tied,
                        "season_max": season_max,
                        "season_min": season_min,

                        "all_time_best_rank": all_best_rank,
                        "all_time_best_tied": all_best_tied,
                        "all_time_worst_rank": all_worst_rank,
                        "all_time_worst_tied": all_worst_tied,
                        "all_time_max": all_max,
                        "all_time_min": all_min,

                        "extreme_flags": extreme,
                    },
                    tags=["category", "weekly", "extreme", "rank"],
                )
            )

    return out

# -------------------------
# One function to run the MVP suite
# -------------------------

def generate_week_insights(
    *,
    year: int,
    week: int,
    season_stat_df: pd.DataFrame,
    all_time_team_dfs: Dict[str, pd.DataFrame],
) -> List[Insight]:
    """
    MVP: streak records + superlatives + upsets + standings swings
    """
    insights: List[Insight] = []
    insights += detect_streak_records(
        year=year,
        week=week,
        season_stat_df=season_stat_df,
        all_time_team_dfs=all_time_team_dfs,
        kind="loss",
    )
    insights += detect_streak_records(
        year=year,
        week=week,
        season_stat_df=season_stat_df,
        all_time_team_dfs=all_time_team_dfs,
        kind="win",
    )
    insights += detect_week_superlatives(year=year, week=week, season_stat_df=season_stat_df, top_n=1)
    insights += detect_upsets(year=year, week=week, season_stat_df=season_stat_df, min_rating_gap=0.12)
    insights += detect_standings_swings(year=year, week=week, season_stat_df=season_stat_df)

    insights: List["Insight"] = []
    insights += detect_streak_records(year=year, week=week, season_stat_df=season_stat_df,
                                      all_time_team_dfs=all_time_team_dfs, kind="loss")
    insights += detect_streak_records(year=year, week=week, season_stat_df=season_stat_df,
                                      all_time_team_dfs=all_time_team_dfs, kind="win")
    insights += detect_week_superlatives(year=year, week=week, season_stat_df=season_stat_df, top_n=1)
    insights += detect_upsets(year=year, week=week, season_stat_df=season_stat_df, min_rating_gap=0.12)
    insights += detect_standings_swings(year=year, week=week, season_stat_df=season_stat_df)
    insights += detect_standings_swings_cats(year=year, week=week, season_stat_df=season_stat_df)

    insights += detect_win_pcts_and_totals(year=year, week=week, season_stat_df=season_stat_df,
                                           all_time_team_dfs=all_time_team_dfs)
    insights += detect_head_to_head_all_time(year=year, week=week, season_stat_df=season_stat_df,
                                             all_time_team_dfs=all_time_team_dfs)
    insights += detect_blowout_counts(year=year, week=week, season_stat_df=season_stat_df,
                                      all_time_team_dfs=all_time_team_dfs)


    insights += detect_week_category_extremes(
        year=year,
        week=week,
        season_stat_df=season_stat_df,
        all_time_team_dfs=all_time_team_dfs,
        cats=["FG%", "FT%", "3PTM", "REB", "AST", "STL", "BLK", "TO", "PTS"],
        lower_is_better={"TO"},
        top_k=3,
    )

    return insights
