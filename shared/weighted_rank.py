from __future__ import annotations

import numpy as np
import pandas as pd


def _minmax(values: np.ndarray) -> np.ndarray:
    """Scale a 1D array to [0, 1]. Matches sklearn.preprocessing.MinMaxScaler,
    including its zero-variance edge case (constant input maps to all zeros)."""
    values = values.astype(float)
    lo, hi = values.min(), values.max()
    span = hi - lo
    if span == 0:
        return np.zeros_like(values)
    return (values - lo) / span


def per_week_rating(
    df: pd.DataFrame,
    main_cats: list[str],
    neg_cats: list[str],
    team_count: int,
    week_col: str = "Week",
    team_col: str = "Team",
) -> pd.DataFrame:
    """Per-week Weighted Rank: minmax-scale each category within its week
    (inverted for neg_cats), average into a composite, then minmax-scale the
    composite again. Adds {cat}_rank/{cat}_wt_rank/{cat}_rating per category,
    plus week_wt_rank/week_rank/week_rating.

    team_count is the season's fixed roster size (not derived per-week), to
    match the original scalar `self.teamCount` used in the rank rescale.

    This mirrors Models/seasons.py::regSeason.df_build_out exactly — do not
    change this formula without updating both call sites (and re-verifying
    against a snapshot of the old output; the two formulas drifting apart
    silently would break "reproduce the existing stat views").
    """
    df = df.copy()
    pos_cats = [c for c in main_cats if c not in neg_cats]

    def minmax_rank_scale(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
        return frame.groupby(week_col)[columns].transform(lambda x: 1 - pd.Series(_minmax(x.values), index=x.index))

    def minmax_rating_scale(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
        return frame.groupby(week_col)[columns].transform(lambda x: pd.Series(_minmax(x.values), index=x.index)) * 100

    for col in pos_cats:
        df[f"{col}_rank"] = df.groupby(week_col)[col].rank(method="min", ascending=False)
        df[f"{col}_wt_rank"] = minmax_rank_scale(df, [col])
        df[f"{col}_rating"] = minmax_rating_scale(df, [col])

    neg_df = df.copy()
    neg_df[neg_cats] = -neg_df[neg_cats]
    for col in neg_cats:
        df[f"{col}_rank"] = df.groupby(week_col)[col].rank(method="min", ascending=True)
        df[f"{col}_wt_rank"] = minmax_rank_scale(neg_df, [col])
        df[f"{col}_rating"] = minmax_rating_scale(neg_df, [col])

    wt_rank_cols = [f"{c}_wt_rank" for c in main_cats]
    rating_cols = [f"{c}_rating" for c in main_cats]

    df["week_wt_rank"] = df[wt_rank_cols].mean(axis=1)
    df["week_wt_rank"] = 1 - minmax_rank_scale(df, ["week_wt_rank"])

    df["week_rank"] = df.groupby(week_col)["week_wt_rank"].rank(method="min", ascending=True)

    df["week_rating"] = df[rating_cols].mean(axis=1)
    df["week_rating"] = minmax_rating_scale(df, ["week_rating"])

    df[wt_rank_cols + ["week_wt_rank"]] = df[wt_rank_cols + ["week_wt_rank"]].apply(lambda x: (team_count - 1) * x + 1)

    return df


def aggregate_rating(df: pd.DataFrame, main_cats: list[str], neg_cats: list[str]) -> pd.DataFrame:
    """Aggregate (career/season) Weighted Rank: minmax-scale each category
    once across the given rows (no per-week grouping), average into
    avg_rating, rank descending. Adds {cat}_rank/{cat}_rating per category
    plus avg_rating/Rank.

    Mirrors Models/League.py::fantasyLeague.get_totals_df/get_avg_df exactly
    — same drift caveat as per_week_rating above.
    """
    df = df.copy()
    pos_cats = [c for c in main_cats if c not in neg_cats]

    def minmax_rating_scale(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
        return frame[columns].transform(lambda x: pd.Series(_minmax(x.values), index=x.index))

    for col in pos_cats:
        df[f"{col}_rank"] = df[col].rank(method="min", ascending=False)
        df[f"{col}_rating"] = minmax_rating_scale(df, [col])

    neg_df = df.copy()
    neg_df[neg_cats] = -neg_df[neg_cats]
    for col in neg_cats:
        df[f"{col}_rank"] = df[col].rank(method="min", ascending=True)
        df[f"{col}_rating"] = minmax_rating_scale(neg_df, [col])

    rating_cols = [f"{c}_rating" for c in main_cats]
    df["avg_rating"] = df[rating_cols].mean(axis=1)
    df["Rank"] = df["avg_rating"].rank(ascending=False)
    return df
