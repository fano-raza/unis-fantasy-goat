import os
import re
import math
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from Models.seasons import regSeason
from Models.seasons import poSeason
from constants import currentYear, seasonInfo, gDocStatCats, allMembers, playoffTeamCount
from recaps.recap_utils import write_regular_season_recap
from shared.runtime_config import DATA_ROOT
from .llm_usage import budget_remaining, extract_usage, record_usage
from .local_lookup import resolve_metric, resolve_operator_method, resolve_operator_explicit
from .query_parser import QuerySpec
from .unanswered_log import record_unanswered

SCOPE_TO_PREFIX = {
    "RS": "M",
    "PO": "P",
}

STAT_LABELS = {
    "PTS": "points",
    "REB": "rebounds",
    "AST": "assists",
    "STL": "steals",
    "BLK": "blocks",
    "TO": "turnovers",
    "3PTM": "3PTM",
    "FG%": "FG%",
    "FT%": "FT%",
}

UNIVERSAL_METRIC_ALIASES = {
    "PTS": ["pts", "points", "point", "score", "scores", "scoring"],
    "REB": ["reb", "rebs", "rebound", "rebounds", "boards", "board"],
    "AST": ["ast", "asts", "assist", "assists"],
    "STL": ["stl", "stls", "steal", "steals"],
    "BLK": ["blk", "blks", "block", "blocks"],
    "TO": ["to", "tos", "turnover", "turnovers"],
    "3PTM": ["3ptm", "3pt", "threes", "three pointers", "3 pointers", "3s"],
    "FG%": ["fg%", "fg percentage", "field goal percentage", "field goal %"],
    "FT%": ["ft%", "ft percentage", "free throw percentage", "free throw %"],
    "AVG_RATING": ["average rating", "avg rating", "week rating", "rating"],
    "AVG_OPP_RATING": ["average opponent rating", "avg opp rating", "avg opponent rating", "sos", "strength of schedule"],
    "SOS_RANK": ["schedule rank", "strength of schedule rank", "toughness rank", "sos rank"],
    "CONSISTENCY": ["consistency", "most consistent", "least consistent"],
    "VOLATILITY": ["volatility", "most volatile", "least stable"],
    "TOP1_WEEKS": ["#1 weeks", "number 1 weeks", "top 1 weeks", "first-place weeks", "weekly #1 finishes"],
    "TOP3_RATE": ["top 3 rate", "top3 rate", "top 3 weeks", "top 3 finish rate"],
    "PLAYOFF_APPEARANCES": [
        "playoff appearances",
        "playoffs made",
        "made playoffs",
        "made the playoffs",
        "playoff years",
        "playoff seasons",
        "years in playoffs",
        "seasons in playoffs",
        "postseason appearances",
        "postseason years",
    ],
    "PLAYOFF_APP_RATE": ["playoff appearance rate", "playoff rate", "playoffs rate"],
    "FINALS": ["finals appearances", "made finals", "finals made"],
    "CHIPS": ["chips", "titles", "championships", "rings"],
    "FINALS_CONVERSION": ["finals conversion", "chip conversion", "championship conversion"],
    "WEIGHTED_RANK": ["weighted rank", "wt rank", "week weighted rank", "week wt rank"],
    "RANK": ["rank", "ranking", "week rank"],
    "DRAFT_SCORE": ["draft score", "draft value", "draft points", "draft rating"],
    "DRAFT_SCORE_PER_PICK": ["draft score per pick", "draft efficiency", "average draft score per pick"],
    "W": ["wins", "won", "w"],
    "L": ["losses", "lost", "l"],
    "D": ["draws", "ties", "tie", "d"],
    "CAT_W": ["category wins", "cat wins", "cats won"],
    "CAT_L": ["category losses", "cat losses", "cats lost"],
    "CAT_D": ["category ties", "cat ties", "cats tied"],
    "WIN_PCT": ["win%", "win pct", "win percentage", "record", "best record", "worst record"],
    "CAT_WIN_PCT": ["category win%", "category win pct", "category win percentage", "cat win%", "cat win pct"],
}

# Default timeframe when user does not provide a concrete time anchor.
# None => keep single-season default (current/requested year).
DEFAULT_YEAR_RANGE_BY_METRIC = {
    # Career-style outcomes are typically interpreted as all-time.
    "PLAYOFF_APPEARANCES": "ALL",
    "PLAYOFF_APP_RATE": "ALL",
    "FINALS": "ALL",
    "CHIPS": "ALL",
    "FINALS_CONVERSION": "ALL",
    # Draft value is usually asked across all seasons unless scoped.
    "DRAFT_SCORE": "ALL",
    "DRAFT_SCORE_PER_PICK": "ALL",
}

DEFAULT_METHOD_BY_METRIC = {
    "FG%": "avg",
    "FT%": "avg",
    "AVG_RATING": "avg",
    "AVG_OPP_RATING": "avg",
    "RANK": "avg",
    "WEIGHTED_RANK": "avg",
    "TOP3_RATE": "avg",
    "WIN_PCT": "avg",
    "CAT_WIN_PCT": "avg",
    "PLAYOFF_APP_RATE": "avg",
    "FINALS_CONVERSION": "avg",
    "DRAFT_SCORE_PER_PICK": "avg",
}

METHOD_BACKUP_METRICS = {
    "PTS",
    "REB",
    "AST",
    "STL",
    "BLK",
    "TO",
    "3PTM",
    "FG%",
    "FT%",
    "AVG_RATING",
    "AVG_OPP_RATING",
    "W",
    "L",
    "D",
    "CAT_W",
    "CAT_L",
    "CAT_D",
    "RANK",
    "WEIGHTED_RANK",
    "DRAFT_SCORE",
}

NO_ANSWER_MSG = "I can't answer that with the data/functions I have right now."
LLM_BUDGET_EXHAUSTED_MSG = (
    "I hit this month's LLM token limit. "
    "I can still answer deterministic stats queries, but natural-language interpretation is currently limited."
)


def _clarification_response(spec: QuerySpec) -> str:
    prompt = spec.clarification_question or "I couldn't confidently map that request."
    suggestions = [s for s in (spec.suggestions or ()) if s]
    if suggestions:
        rows = "\n".join(f"- {s}" for s in suggestions[:4])
        return f"{prompt}\n\nClosest things I can answer:\n{rows}"
    return prompt



@lru_cache(maxsize=16)
def _season(year: int) -> regSeason:
    return regSeason(year)


@lru_cache(maxsize=16)
def _po_team_set(year: int) -> set[str]:
    """
    Championship-playoff field only (excludes consolation bracket teams).
    """
    try:
        p = poSeason(year)
        teams = [str(t) for t in getattr(p, "PO_teams", []) if t]
        if teams:
            po_results = getattr(p, "PO_results", {}) or {}
            below_top4 = {str(team) for team, res in po_results.items() if team and str(res).strip().lower() == "below top 4"}
            return set(teams) - below_top4 if below_top4 else set(teams)
    except Exception:
        pass

    # Conservative fallback to top-N from standings if PO_teams is unavailable.
    try:
        n = int(playoffTeamCount.get(year, 0) or 0)
    except Exception:
        n = 0
    if n <= 0:
        return set()
    try:
        rs = _season(year)
        wl = rs.get_WL_standings()
        top = [str(wl[i][0]) for i in sorted(wl.keys())[:n] if i in wl]
        return set(top)
    except Exception:
        return set()


def _filter_df_by_scope(df: pd.DataFrame, scope: str) -> pd.DataFrame:
    if scope in SCOPE_TO_PREFIX:
        prefix = SCOPE_TO_PREFIX[scope]
        return df.loc[df["Week Name"].str.startswith(prefix)]
    return df.loc[df["Week Name"].str.startswith(("M", "P"))]


def _filter_df_by_weeks(df: pd.DataFrame, week: Optional[int], start_week: Optional[int], end_week: Optional[int]) -> pd.DataFrame:
    if week is not None:
        return df.loc[df["Week"] == week]
    if start_week is not None and end_week is not None:
        return df.loc[(df["Week"] >= min(start_week, end_week)) & (df["Week"] <= max(start_week, end_week))]
    if start_week is not None:
        return df.loc[df["Week"] >= start_week]
    return df


def _aggregate_team_stat(df: pd.DataFrame, stat: str) -> pd.Series:
    src = df.loc[(df["Team"] != "BYE") & (df["Opp"] != "BYE")]
    if "real_matchup" in src.columns:
        src = src.loc[src["real_matchup"] >= 1]
    if src.empty:
        return pd.Series(dtype="float64")

    if stat in ("FG%", "FT%"):
        return src.groupby("Team")[stat].mean()

    return src.groupby("Team")[stat].sum()


def _rank_for_scope(year: int, stat: str, scope: str, direction: str, week: Optional[int] = None,
                    start_week: Optional[int] = None, end_week: Optional[int] = None) -> pd.Series:
    rs = _season(year)
    df = _filter_df_by_scope(rs.statDF, scope)
    if scope == "PO":
        po_teams = _po_team_set(year)
        if po_teams:
            df = df[df["Team"].isin(po_teams) & df["Opp"].isin(po_teams)]
    df = _filter_df_by_weeks(df, week=week, start_week=start_week, end_week=end_week)
    if stat not in df.columns:
        return pd.Series(dtype="float64")

    agg = _aggregate_team_stat(df, stat)
    ascending = direction == "min"
    return agg.sort_values(ascending=ascending)


def _top_teams_for_stat(
    year: int,
    stat: str,
    direction: str,
    scope: str,
    top_n: int = 1,
    week: Optional[int] = None,
    start_week: Optional[int] = None,
    end_week: Optional[int] = None,
) -> list[tuple[str, float]]:
    ranked = _rank_for_scope(
        year,
        stat,
        scope,
        direction,
        week=week,
        start_week=start_week,
        end_week=end_week,
    )
    if ranked.empty:
        return []
    sample = ranked.head(max(1, min(int(top_n or 1), len(ranked))))
    return [(str(team), float(val)) for team, val in sample.items()]


def _format_value(stat: str, value: float) -> str:
    if stat in ("FG%", "FT%"):
        return f"{value:.4f}"
    return f"{value:.2f}" if isinstance(value, float) else str(value)


def _scope_name(scope: str) -> str:
    return {"ALL": "entire season", "RS": "regular season", "PO": "playoffs"}.get(scope, "scope")


def _window_label(week: Optional[int], start_week: Optional[int], end_week: Optional[int]) -> str:
    if week is not None:
        return f"week {week}"
    if start_week is not None and end_week is not None:
        a, b = sorted((int(start_week), int(end_week)))
        if a == b:
            return f"week {a}"
        return f"weeks {a}-{b}"
    if start_week is not None:
        return f"week {int(start_week)}+"
    return ""


def _extract_universal_metric(question: str) -> Optional[str]:
    # prioritize more-specific composite metrics first
    metric_order = [
        "DRAFT_SCORE_PER_PICK",
        "DRAFT_SCORE",
        "FINALS_CONVERSION",
        "CHIPS",
        "FINALS",
        "PLAYOFF_APP_RATE",
        "PLAYOFF_APPEARANCES",
        "TOP3_RATE",
        "TOP1_WEEKS",
        "VOLATILITY",
        "CONSISTENCY",
        "SOS_RANK",
        "AVG_OPP_RATING",
        "WEIGHTED_RANK",
        "RANK",
        "CAT_WIN_PCT",
        "WIN_PCT",
        "CAT_W",
        "CAT_L",
        "CAT_D",
        "AVG_RATING",
        "FG%",
        "FT%",
        "3PTM",
        "PTS",
        "REB",
        "AST",
        "STL",
        "BLK",
        "TO",
        "W",
        "L",
        "D",
    ]
    return resolve_metric(question, metric_order=metric_order, aliases=UNIVERSAL_METRIC_ALIASES)


def _method_from_question(question: str) -> str:
    return resolve_operator_method(question, default="total")


def _direction_from_question(question: str, metric: str) -> str:
    q = (question or "").lower()
    if metric in {"CONSISTENCY"}:
        if any(k in q for k in ["worst", "least", "highest", "max"]):
            return "max"
        return "min"
    if metric in {"VOLATILITY", "AVG_OPP_RATING"}:
        if any(k in q for k in ["least", "lowest", "min", "easiest"]):
            return "min"
        return "max"
    if metric in {"SOS_RANK"}:
        if any(k in q for k in ["worst", "highest", "largest", "max"]):
            return "max"
        return "min"
    if metric in {"RANK", "WEIGHTED_RANK"}:
        if any(k in q for k in ["worst", "highest", "largest", "max", "bottom"]):
            return "max"
        return "min"
    if any(k in q for k in ["worst", "least", "fewest", "lowest", "bottom", "min"]):
        return "min"
    if metric == "TO" and any(k in q for k in ["best", "lowest turnovers", "fewest turnovers"]):
        return "min"
    return "max"


def _top_n_from_question(question: str, default_top_n: int = 1) -> int:
    q = (question or "").lower()
    m = re.search(r"\btop\s*(\d+)\b", q)
    if m:
        return max(1, min(30, int(m.group(1))))
    if any(k in q for k in ["best", "most", "worst", "least", "leaders", "rankings"]):
        return max(1, min(30, default_top_n if default_top_n > 1 else 10))
    return max(1, min(30, default_top_n or 1))


def _universal_metric_series(df: pd.DataFrame, metric: str, method: str) -> pd.Series:
    grp = df.groupby("Team", as_index=True)

    # raw stat families
    if metric in {"PTS", "REB", "AST", "STL", "BLK", "TO", "3PTM"}:
        if method == "avg":
            return grp[metric].mean()
        return grp[metric].sum()
    if metric in {"FG%", "FT%", "AVG_RATING"}:
        col = "week_rating" if metric == "AVG_RATING" else metric
        return grp[col].mean() if method == "avg" else grp[col].sum()
    if metric == "AVG_OPP_RATING":
        if "week_rating_opp" not in df.columns:
            return pd.Series(dtype="float64")
        return grp["week_rating_opp"].mean() if method == "avg" else grp["week_rating_opp"].sum()
    if metric in {"CONSISTENCY", "VOLATILITY"}:
        if "week_rating" not in df.columns:
            return pd.Series(dtype="float64")
        # std as volatility; consistency uses same value but direction differs.
        return grp["week_rating"].std().fillna(0.0)
    if metric == "TOP1_WEEKS":
        if "week_rank" not in df.columns:
            return pd.Series(dtype="float64")
        return grp.apply(lambda g: float((g["week_rank"] == 1).sum()))
    if metric == "TOP3_RATE":
        if "week_rank" not in df.columns:
            return pd.Series(dtype="float64")
        return grp.apply(lambda g: float((g["week_rank"] <= 3).mean()))
    if metric in {"RANK", "WEIGHTED_RANK"}:
        col = "week_rank" if metric == "RANK" else "week_wt_rank"
        if col not in df.columns:
            return pd.Series(dtype="float64")
        return grp[col].mean() if method == "avg" else grp[col].sum()

    # matchup outcome families
    if metric in {"W", "L", "D", "CAT_W", "CAT_L", "CAT_D"}:
        col_map = {
            "W": "matchup_win",
            "L": "matchup_loss",
            "D": "matchup_tie",
            "CAT_W": "cat_wins",
            "CAT_L": "cat_losses",
            "CAT_D": "cat_ties",
        }
        col = col_map[metric]
        return grp[col].mean() if method == "avg" else grp[col].sum()

    if metric == "WIN_PCT":
        agg = grp[["matchup_win", "matchup_loss", "matchup_tie"]].sum()
        denom = agg["matchup_win"] + agg["matchup_loss"] + agg["matchup_tie"]
        numer = agg["matchup_win"] + 0.5 * agg["matchup_tie"]
        return (numer / denom.replace(0, pd.NA)).fillna(0.0)

    if metric == "CAT_WIN_PCT":
        agg = grp[["cat_wins", "cat_losses", "cat_ties"]].sum()
        denom = agg["cat_wins"] + agg["cat_losses"] + agg["cat_ties"]
        numer = agg["cat_wins"] + 0.5 * agg["cat_ties"]
        return (numer / denom.replace(0, pd.NA)).fillna(0.0)

    return pd.Series(dtype="float64")


def _format_universal_value(metric: str, value: float) -> str:
    if metric in {"FG%", "FT%", "WIN_PCT", "CAT_WIN_PCT", "TOP3_RATE", "PLAYOFF_APP_RATE", "FINALS_CONVERSION"}:
        return f"{float(value):.4f}"
    return f"{float(value):.2f}"


def _label_for_universal_metric(metric: str, method: str) -> str:
    labels = {
        "PTS": "points",
        "REB": "rebounds",
        "AST": "assists",
        "STL": "steals",
        "BLK": "blocks",
        "TO": "turnovers",
        "3PTM": "3PTM",
        "FG%": "FG%",
        "FT%": "FT%",
        "AVG_RATING": "average rating",
        "AVG_OPP_RATING": "average opponent rating",
        "SOS_RANK": "schedule rank",
        "CONSISTENCY": "consistency (std dev)",
        "VOLATILITY": "volatility (std dev)",
        "TOP1_WEEKS": "#1 weeks",
        "TOP3_RATE": "top-3 week rate",
        "PLAYOFF_APPEARANCES": "playoff appearances",
        "PLAYOFF_APP_RATE": "playoff appearance rate",
        "FINALS": "finals appearances",
        "CHIPS": "championships",
        "FINALS_CONVERSION": "finals conversion",
        "WEIGHTED_RANK": "weighted rank",
        "RANK": "rank",
        "DRAFT_SCORE": "draft score",
        "DRAFT_SCORE_PER_PICK": "draft score per pick",
        "W": "wins",
        "L": "losses",
        "D": "draws",
        "CAT_W": "category wins",
        "CAT_L": "category losses",
        "CAT_D": "category draws",
        "WIN_PCT": "win%",
        "CAT_WIN_PCT": "category win%",
    }
    base = labels.get(metric, metric)
    if metric in {"SOS_RANK", "CONSISTENCY", "VOLATILITY", "TOP1_WEEKS", "DRAFT_SCORE_PER_PICK"}:
        return base
    if metric not in {"FG%", "FT%", "WIN_PCT", "CAT_WIN_PCT", "TOP3_RATE", "PLAYOFF_APP_RATE", "FINALS_CONVERSION"}:
        return f"{'average' if method == 'avg' else 'total'} {base}"
    return base


def _draft_team_metric_series(years: list[int], method: str) -> pd.Series:
    tables = []
    for y in years:
        path = DATA_ROOT / str(y) / f"{y} Draft Results.csv"
        if not path.exists():
            continue
        df = _load_draft_table(y)[["Team", "final_score"]].copy()
        df["Year"] = y
        tables.append(df)
    if not tables:
        return pd.Series(dtype="float64")
    all_df = pd.concat(tables, ignore_index=True)
    grp = all_df.groupby("Team")["final_score"]
    if method == "avg":
        return grp.mean()
    return grp.sum()


def _draft_team_per_pick_series(years: list[int]) -> pd.Series:
    tables = []
    for y in years:
        path = DATA_ROOT / str(y) / f"{y} Draft Results.csv"
        if not path.exists():
            continue
        df = _load_draft_table(y)[["Team", "final_score"]].copy()
        tables.append(df)
    if not tables:
        return pd.Series(dtype="float64")
    all_df = pd.concat(tables, ignore_index=True)
    return all_df.groupby("Team")["final_score"].mean()


def _playoff_outcome_metric_series(years: list[int], metric: str) -> pd.Series:
    teams = sorted(allMembers)
    counts = {t: {"seasons": 0, "playoffs": 0, "finals": 0, "chips": 0} for t in teams}

    for y in years:
        for t in teams:
            if t in seasonInfo.get(y, ([],))[0]:
                counts[t]["seasons"] += 1
        try:
            po = poSeason(y)
            po_teams = set(getattr(po, "PO_teams", []) or [])
            po_results = getattr(po, "PO_results", {}) or {}
            for t in po_teams:
                if t in counts:
                    counts[t]["playoffs"] += 1
            for t, res in po_results.items():
                if t not in counts:
                    continue
                if isinstance(res, int):
                    if res in (1, 2):
                        counts[t]["finals"] += 1
                    if res == 1:
                        counts[t]["chips"] += 1
        except Exception:
            continue

    vals = {}
    for t, d in counts.items():
        if metric == "PLAYOFF_APPEARANCES":
            vals[t] = float(d["playoffs"])
        elif metric == "PLAYOFF_APP_RATE":
            vals[t] = float(d["playoffs"]) / float(d["seasons"]) if d["seasons"] > 0 else 0.0
        elif metric == "FINALS":
            vals[t] = float(d["finals"])
        elif metric == "CHIPS":
            vals[t] = float(d["chips"])
        elif metric == "FINALS_CONVERSION":
            vals[t] = float(d["chips"]) / float(d["finals"]) if d["finals"] > 0 else 0.0
    return pd.Series(vals, dtype="float64")


def _try_answer_universal_metric_query(
    question: str,
    spec: QuerySpec,
    *,
    include_backups: bool = True,
    forced_method: Optional[str] = None,
    forced_is_all_time: Optional[bool] = None,
    clear_week_filters: bool = False,
) -> Optional[str]:
    metric = _extract_universal_metric(question)
    if not metric:
        return None

    scope = spec.scope if spec.scope in {"ALL", "RS", "PO"} else "ALL"
    explicit_method = resolve_operator_explicit(question)
    if forced_method:
        method = forced_method.lower()
    elif spec.method:
        method = str(spec.method).lower()
    elif explicit_method:
        method = explicit_method
    else:
        method = DEFAULT_METHOD_BY_METRIC.get(metric, _method_from_question(question))
    method = "avg" if method in {"avg", "average", "mean"} else "total"
    direction = _direction_from_question(question, metric)
    top_n = _top_n_from_question(question, spec.top_n or 1)
    q_low = (question or "").lower()
    is_all_time = (spec.year_range or "").upper() == "ALL" or any(k in q_low for k in ["all time", "all-time", "career", "entire career"])
    # Determine if user gave a concrete time anchor.
    has_concrete_time_anchor = (
        bool(re.search(r"\b20\d{2}\b", q_low))
        or any(k in q_low for k in ["this season", "current season", "last season", "all time", "all-time", "career", "entire career"])
        or bool(re.search(r"\bweek\s*\d+\b", q_low))
        or bool(re.search(r"\b\d+\s+(season|seasons|year|years)\s+ago\b", q_low))
        or bool(re.search(r"\bprevious\s+\d+\s+(season|seasons|year|years)\b", q_low))
    )
    # Apply per-metric default timeframe only when user did not specify time.
    if not has_concrete_time_anchor and not (spec.year_range or "").upper() == "ALL":
        if DEFAULT_YEAR_RANGE_BY_METRIC.get(metric) == "ALL":
            is_all_time = True

    if metric in {"PLAYOFF_APPEARANCES", "PLAYOFF_APP_RATE", "FINALS", "CHIPS", "FINALS_CONVERSION"} and not has_concrete_time_anchor:
        is_all_time = True
    if forced_is_all_time is not None:
        is_all_time = bool(forced_is_all_time)
    years = sorted(seasonInfo.keys()) if is_all_time else [spec.year if spec.year in seasonInfo else currentYear]
    week = None if clear_week_filters else spec.week
    start_week = None if clear_week_filters else spec.start_week
    end_week = None if clear_week_filters else spec.end_week
    if not clear_week_filters and week is None and start_week is None and end_week is None:
        rng = re.search(r"weeks?\s*(\d{1,2})\s*(?:to|-|through)\s*(\d{1,2})", q_low)
        if rng:
            start_week, end_week = int(rng.group(1)), int(rng.group(2))
        else:
            w = re.search(r"\bweek\s*(\d{1,2})\b", q_low)
            if w:
                week = int(w.group(1))

    # Draft-score metrics are sourced from draft tables.
    if metric in {"DRAFT_SCORE", "DRAFT_SCORE_PER_PICK"}:
        if metric == "DRAFT_SCORE":
            series = _draft_team_metric_series(years, method)
        else:
            series = _draft_team_per_pick_series(years)
        if series.empty:
            return None
        if spec.team and not spec.team2:
            team_name = str(spec.team)
            if team_name in series.index:
                year_label = "all-time" if is_all_time else str(years[0])
                label = _label_for_universal_metric(metric, method)
                return f"{year_label}: {team_name} had {_format_universal_value(metric, float(series.loc[team_name]))} {label}."
        ascending = (direction == "min")
        ranked = series.sort_values(ascending=ascending)
        label = _label_for_universal_metric(metric, method)
        year_label = "all-time" if is_all_time else str(years[0])
        rows = [f"{i}. {team} ({_format_universal_value(metric, float(val))})" for i, (team, val) in enumerate(ranked.head(top_n).items(), 1)]
        primary = "\n".join([f"{year_label} top {top_n} by {label}:", *rows])
        if not include_backups:
            return primary
        return _with_universal_backups(
            primary=primary,
            metric=metric,
            method=method,
            is_all_time=is_all_time,
            has_week_filter=bool(week is not None or start_week is not None or end_week is not None),
            question=question,
            spec=spec,
            clear_week_filters=clear_week_filters,
        )

    # Playoff/championship outcomes are also sourced outside statDF.
    if metric in {"PLAYOFF_APPEARANCES", "PLAYOFF_APP_RATE", "FINALS", "CHIPS", "FINALS_CONVERSION"}:
        series = _playoff_outcome_metric_series(years, metric)
        if series.empty:
            return None
        if spec.team and not spec.team2:
            team_name = str(spec.team)
            if team_name in series.index:
                year_label = "all-time" if is_all_time else str(years[0])
                label = _label_for_universal_metric(metric, method)
                return f"{year_label}: {team_name} had {_format_universal_value(metric, float(series.loc[team_name]))} {label}."
        ascending = (direction == "min")
        ranked = series.sort_values(ascending=ascending)
        label = _label_for_universal_metric(metric, method)
        year_label = "all-time" if is_all_time else str(years[0])
        rows = [f"{i}. {team} ({_format_universal_value(metric, float(val))})" for i, (team, val) in enumerate(ranked.head(top_n).items(), 1)]
        primary = "\n".join([f"{year_label} top {top_n} by {label}:", *rows])
        if not include_backups:
            return primary
        return _with_universal_backups(
            primary=primary,
            metric=metric,
            method=method,
            is_all_time=is_all_time,
            has_week_filter=bool(week is not None or start_week is not None or end_week is not None),
            question=question,
            spec=spec,
            clear_week_filters=clear_week_filters,
        )

    frames = []
    for y in years:
        rs = _season(y)
        d = _filter_df_by_scope(rs.statDF, scope)
        if scope == "PO":
            po_teams = _po_team_set(y)
            if po_teams:
                d = d[d["Team"].isin(po_teams) & d["Opp"].isin(po_teams)]
        d = _filter_df_by_weeks(d, week, start_week, end_week)
        d = d[(d["Team"] != "BYE") & (d["Opp"] != "BYE")]
        if "real_matchup" in d.columns:
            d = d[d["real_matchup"] >= 1]
        if not d.empty:
            d = d.copy()
            d["Year"] = y
            frames.append(d)
    if not frames:
        return None
    df = pd.concat(frames, ignore_index=True)

    opp_filter = any(k in q_low for k in [" against ", " vs ", " versus ", "vs."])
    target_team = spec.team
    if opp_filter and target_team:
        df = df[df["Opp"].astype(str).str.lower() == str(target_team).lower()]
    elif target_team and not spec.team2:
        # Single-team focus query
        df = df[df["Team"].astype(str).str.lower() == str(target_team).lower()]

    if df.empty:
        return None

    if metric == "SOS_RANK":
        # 1 = toughest schedule (highest average opponent rating).
        opp = _universal_metric_series(df, "AVG_OPP_RATING", "avg")
        if opp.empty:
            return None
        series = opp.rank(ascending=False, method="min")
    else:
        series = _universal_metric_series(df, metric, method)
        if series.empty:
            return None

    ascending = (direction == "min")
    ranked = series.sort_values(ascending=ascending)
    label = _label_for_universal_metric(metric, method)

    # If filtered to one team, return scalar summary.
    if target_team and not opp_filter and not spec.team2:
        team_name = str(target_team)
        if team_name in ranked.index:
            val = float(ranked.loc[team_name])
            year_label = "all-time" if is_all_time else str(years[0])
            window_lbl = _window_label(week, start_week, end_week)
            window_part = f" ({window_lbl})" if window_lbl else ""
            primary = f"{year_label} {_scope_name(scope)}{window_part}: {team_name} had {_format_universal_value(metric, val)} {label}."
            if not include_backups:
                return primary
            return _with_universal_backups(
                primary=primary,
                metric=metric,
                method=method,
                is_all_time=is_all_time,
                has_week_filter=bool(week is not None or start_week is not None or end_week is not None),
                question=question,
                spec=spec,
                clear_week_filters=clear_week_filters,
            )

    rows = []
    for i, (team, val) in enumerate(ranked.head(top_n).items(), 1):
        rows.append(f"{i}. {team} ({_format_universal_value(metric, float(val))})")

    against_suffix = f" against {target_team}" if opp_filter and target_team else ""
    year_label = "all-time" if is_all_time else str(years[0])
    window_lbl = _window_label(week, start_week, end_week)
    window_part = f" ({window_lbl})" if window_lbl else ""
    header = f"{year_label} {_scope_name(scope)}{window_part} top {top_n} by {label}{against_suffix}:"
    primary = "\n".join([header, *rows])
    if not include_backups:
        return primary
    return _with_universal_backups(
        primary=primary,
        metric=metric,
        method=method,
        is_all_time=is_all_time,
        has_week_filter=bool(week is not None or start_week is not None or end_week is not None),
        question=question,
        spec=spec,
        clear_week_filters=clear_week_filters,
    )


def _with_universal_backups(
    *,
    primary: str,
    metric: str,
    method: str,
    is_all_time: bool,
    has_week_filter: bool,
    question: str,
    spec: QuerySpec,
    clear_week_filters: bool,
) -> str:
    sections = [primary]
    backup_candidates: list[str] = []

    # Companion method view (total <-> average) when meaningful.
    if metric in METHOD_BACKUP_METRICS:
        alt_method = "avg" if method == "total" else "total"
        alt = _try_answer_universal_metric_query(
            question,
            spec,
            include_backups=False,
            forced_method=alt_method,
            forced_is_all_time=is_all_time,
            clear_week_filters=clear_week_filters,
        )
        if alt and alt != primary:
            backup_candidates.append(f"{'Average' if alt_method == 'avg' else 'Total'} view:\n{alt}")

    # Companion all-time view when primary is single-season.
    if not is_all_time:
        alt_all = _try_answer_universal_metric_query(
            question,
            spec,
            include_backups=False,
            forced_method=method,
            forced_is_all_time=True,
            clear_week_filters=clear_week_filters,
        )
        if alt_all and alt_all != primary:
            backup_candidates.append(f"All-time view:\n{alt_all}")

    # Companion full-season view when week filters are applied.
    if has_week_filter and not clear_week_filters:
        alt_full_season = _try_answer_universal_metric_query(
            question,
            spec,
            include_backups=False,
            forced_method=method,
            forced_is_all_time=is_all_time,
            clear_week_filters=True,
        )
        if alt_full_season and alt_full_season != primary:
            # Put this first by priority (most specific correction of week-window slicing).
            backup_candidates.insert(0, f"Full-season range:\n{alt_full_season}")

    # At most one backup item.
    if backup_candidates:
        # Priority order:
        # 1) Full-season range (if week-filtered)
        # 2) All-time view (if single-season primary)
        # 3) Method companion (total<->average)
        chosen = None
        for candidate in backup_candidates:
            if candidate.startswith("Full-season range:"):
                chosen = candidate
                break
        if not chosen:
            for candidate in backup_candidates:
                if candidate.startswith("All-time view:"):
                    chosen = candidate
                    break
        if not chosen:
            chosen = backup_candidates[0]
        sections.append("Backup:\n" + chosen)

    return "\n\n".join(sections)


def _ordinal(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def _validate_year(spec: QuerySpec) -> Optional[str]:
    if spec.year not in seasonInfo:
        valid = ", ".join(str(y) for y in sorted(seasonInfo.keys()))
        return f"I only have season data for: {valid}."
    return None


def _resolve_years(spec: QuerySpec) -> list[int]:
    if (spec.year_range or "").upper() == "ALL":
        return sorted(seasonInfo.keys())
    if spec.year in seasonInfo:
        return [spec.year]
    return sorted(seasonInfo.keys())


def _all_time_stats_df(scope: str, method: str) -> pd.DataFrame:
    years = sorted(seasonInfo.keys())
    frames = []
    for y in years:
        rs = _season(y)
        df = rs.statDF.copy()
        if scope == "RS":
            df = df[df["Week Name"].str.startswith("M")]
        elif scope == "PO":
            df = df[df["Week Name"].str.startswith("P")]
            po_teams = _po_team_set(y)
            if po_teams:
                df = df[df["Team"].isin(po_teams) & df["Opp"].isin(po_teams)]
        else:
            df = df[df["Week Name"].str.startswith(("M", "P"))]
        df = df[(df["Team"] != "BYE") & (df["Opp"] != "BYE")]
        if "real_matchup" in df.columns:
            df = df[df["real_matchup"] >= 1]
        frames.append(df)

    all_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if all_df.empty:
        return pd.DataFrame()

    method = (method or "total").lower()
    if method in {"avg", "average", "averages"}:
        agg = all_df.groupby("Team", as_index=False)[gDocStatCats].mean()
    else:
        agg_dict = {cat: ("mean" if cat in {"FG%", "FT%"} else "sum") for cat in gDocStatCats}
        agg = all_df.groupby("Team", as_index=False).agg(agg_dict)
    return agg


def _get_llm_max_output_tokens() -> int:
    raw = os.getenv("DISCORD_LLM_MAX_OUTPUT_TOKENS", "300").strip()
    try:
        return max(16, int(raw))
    except ValueError:
        return 300


def _answer_leader(spec: QuerySpec) -> str:
    if not spec.stat:
        return "__NO_STAT_FOR_LEADER__"

    scopes = [spec.scope] if spec.scope in ("RS", "PO") else ["ALL", "RS", "PO"]
    lines = []

    for scope in scopes:
        ranked = _rank_for_scope(
            spec.year,
            spec.stat,
            scope,
            spec.direction,
            week=spec.week,
            start_week=spec.start_week,
            end_week=spec.end_week,
        )
        if ranked.empty:
            continue

        top_n = max(1, min(spec.top_n, 10))
        sample = ranked.head(top_n)
        qualifier = "lowest" if spec.direction == "min" else "most"
        stat_label = STAT_LABELS.get(spec.stat, spec.stat)

        week_text = ""
        if spec.week is not None:
            week_text = f", week {spec.week}"
        elif spec.start_week is not None and spec.end_week is not None:
            week_text = f", weeks {min(spec.start_week, spec.end_week)}-{max(spec.start_week, spec.end_week)}"

        if top_n == 1:
            team = sample.index[0]
            val = float(sample.iloc[0])
            lines.append(
                f"{_scope_name(scope).title()}{week_text}: **{team}** had the {qualifier} {stat_label} ({_format_value(spec.stat, val)})."
            )
        else:
            rows = [f"{i+1}. {team} ({_format_value(spec.stat, float(val))})" for i, (team, val) in enumerate(sample.items())]
            lines.append(
                f"{_scope_name(scope).title()}{week_text} top {top_n} by {stat_label} ({qualifier} first):\n" + "\n".join(rows)
            )

    if not lines:
        return f"I couldn't find usable {spec.stat} data for {spec.year}."

    return "\n\n".join(lines)


def _answer_leader_vs_team(spec: QuerySpec) -> str:
    if not spec.stat or not spec.team:
        return "__NO_STAT_FOR_LEADER__"

    years = _resolve_years(spec)
    series_list = []
    for year in years:
        rs = _season(year)
        df = _filter_df_by_scope(rs.statDF, spec.scope)
        df = _filter_df_by_weeks(df, week=spec.week, start_week=spec.start_week, end_week=spec.end_week)
        df = df.loc[(df["Opp"] == spec.team) & (df["Team"] != "BYE") & (df["Opp"] != "BYE")]
        if "real_matchup" in df.columns:
            df = df.loc[df["real_matchup"] >= 1]
        if df.empty or spec.stat not in df.columns:
            continue

        if spec.stat in ("FG%", "FT%"):
            s = df.groupby("Team")[spec.stat].mean()
        else:
            s = df.groupby("Team")[spec.stat].sum()
        series_list.append(s)

    if not series_list:
        return NO_ANSWER_MSG

    if spec.stat in ("FG%", "FT%"):
        combined = pd.concat(series_list).groupby(level=0).mean()
    else:
        combined = pd.concat(series_list).groupby(level=0).sum()

    ranked = combined.sort_values(ascending=(spec.direction == "min"))
    if ranked.empty:
        return NO_ANSWER_MSG

    top_n = max(1, min(spec.top_n, len(ranked)))
    sample = ranked.head(top_n)
    winner_team = ranked.index[0]
    winner_val = float(ranked.iloc[0])
    stat_label = STAT_LABELS.get(spec.stat, spec.stat)
    qualifier = "lowest" if spec.direction == "min" else "most"
    scope_label = _scope_name(spec.scope)
    year_label = "all seasons" if (spec.year_range or "").upper() == "ALL" else str(spec.year)

    lines = [
        f"{year_label} {scope_label}: **{winner_team}** had the {qualifier} {stat_label} against **{spec.team}** ({_format_value(spec.stat, winner_val)}).",
        "Full ranking:",
    ]
    for i, (team, val) in enumerate(sample.items(), 1):
        lines.append(f"{i}. {team} ({_format_value(spec.stat, float(val))})")
    return "\n".join(lines)


def _answer_standings(spec: QuerySpec) -> str:
    rs = _season(spec.year)

    fmt = spec.standings_format
    if fmt == "auto":
        fmt = "wl" if rs.is_WL else "cats"

    start_week = spec.start_week
    end_week = spec.end_week
    if spec.week is not None:
        start_week = spec.week
        end_week = spec.week
    use_week_window = start_week is not None or end_week is not None

    if fmt == "wl":
        if use_week_window:
            sw = int(start_week) if start_week is not None else 1
            ew = int(end_week) if end_week is not None else sw
            standings = rs.get_WL_standings(sw, ew)
            title = f"W/L standings (weeks {sw}-{ew})"
        else:
            standings = rs.get_WL_standings()
            title = "W/L standings"
    else:
        if use_week_window:
            sw = int(start_week) if start_week is not None else 1
            ew = int(end_week) if end_week is not None else sw
            standings = rs.get_Cats_standings(sw, ew)
            title = f"Category standings (weeks {sw}-{ew})"
        else:
            standings = rs.get_Cats_standings()
            title = "Category standings"

    if spec.place is not None:
        if spec.place not in standings:
            return f"That league only has placements 1-{len(standings)} for {spec.year}."
        team, record = standings[spec.place]
        return f"{spec.year} {title}: **{team}** is in {_ordinal(spec.place)} place ({record})."

    if spec.team:
        for place, (team, record) in standings.items():
            if str(team).lower() == str(spec.team).lower():
                return f"{spec.year} {title}: **{team}** is in {_ordinal(place)} place ({record})."
        return f"{spec.team} is not a recognized team for {spec.year}."

    lines = [f"{spec.year} {title}:"]
    for place, (team, record) in standings.items():
        lines.append(f"{place}. {team} ({record})")
    return "\n".join(lines)


def _answer_best_team_snapshot(spec: QuerySpec) -> str:
    rs = _season(spec.year)
    week = int(getattr(rs, "currentWeek", 0) or 0)

    wl = rs.get_WL_standings()
    season_ranks = rs.get_season_rankings()
    week_ranks = rs.get_week_rankings(week) if week > 0 else {}

    lines = [f"{spec.year} best-team snapshot (current week: {week}):"]

    lines.append("Current standings (W/L):")
    for place, (team, record) in wl.items():
        lines.append(f"{place}. {team} ({record})")

    lines.append("")
    lines.append("Current overall rankings (season average rank):")
    for place, (team, score) in season_ranks.items():
        lines.append(f"{place}. {team} ({score:.2f})")

    if week_ranks:
        lines.append("")
        lines.append(f"Current week rankings (Week {week}):")
        for place, (team, score) in week_ranks.items():
            lines.append(f"{place}. {team} ({score:.2f})")

    return "\n".join(lines)


def _answer_standings_alternate(spec: QuerySpec) -> str:
    rs = _season(spec.year)
    if rs.is_WL:
        standings = rs.get_Cats_standings()
        title = "Category standings (alternate format)"
    else:
        standings = rs.get_WL_standings()
        title = "W/L standings (alternate format)"

    lines = [f"{spec.year} {title}:"]
    for place, (team, record) in standings.items():
        lines.append(f"{place}. {team} ({record})")
    return "\n".join(lines)


def _answer_predict_champion(spec: QuerySpec) -> str:
    rs = _season(spec.year)
    df = rs.statDF.copy()
    df = df[(df["Week Name"].str.startswith("M")) & (df["Team"] != "BYE") & (df["Opp"] != "BYE")]
    if "real_matchup" in df.columns:
        df = df[df["real_matchup"] >= 1]
    if df.empty:
        return "No regular-season rows available for title projection."

    half_life = float(os.getenv("DISCORD_RECENCY_HALF_LIFE_WEEKS", "4"))
    half_life = max(0.5, half_life)
    max_week = int(df["Week"].max())
    decay = math.log(2) / half_life
    df = df.copy()
    df["recency_w"] = df["Week"].apply(lambda w: math.exp(-decay * (max_week - int(w))))

    def _wavg(g: pd.DataFrame, col: str) -> float:
        w = g["recency_w"]
        return float((g[col] * w).sum() / w.sum()) if float(w.sum()) > 0 else float("nan")

    by_team = []
    for team, g in df.groupby("Team"):
        by_team.append(
            {
                "Team": team,
                "avg_rating_w": _wavg(g, "week_rating"),
                "pts_pg_w": _wavg(g, "PTS"),
                "fg_w": _wavg(g, "FG%"),
                "ft_w": _wavg(g, "FT%"),
                "sos_w": _wavg(g, "week_rating_opp"),
            }
        )
    tdf = pd.DataFrame(by_team)

    standings = rs.get_WL_standings() if rs.is_WL else rs.get_Cats_standings()
    seed_of = {v[0]: int(k) for k, v in standings.items()}
    tdf["seed"] = tdf["Team"].map(seed_of).fillna(99).astype(int)

    n = len(tdf)
    for col, asc in [
        ("seed", True),
        ("avg_rating_w", False),
        ("pts_pg_w", False),
        ("fg_w", False),
        ("ft_w", False),
        ("sos_w", False),
    ]:
        tdf[f"r_{col}"] = tdf[col].rank(method="min", ascending=asc)
        tdf[f"z_{col}"] = (n + 1 - tdf[f"r_{col}"]) / n

    # Composite title-likelihood score with recency-weighted stats.
    tdf["title_score"] = (
        0.40 * tdf["z_avg_rating_w"]
        + 0.25 * tdf["z_seed"]
        + 0.15 * tdf["z_pts_pg_w"]
        + 0.08 * tdf["z_fg_w"]
        + 0.07 * tdf["z_ft_w"]
        + 0.05 * tdf["z_sos_w"]
    )
    tdf = tdf.sort_values(["title_score", "avg_rating_w"], ascending=False).reset_index(drop=True)

    lines = [f"Recency-weighted title likelihood ({spec.year}, RS, half-life={half_life:.1f} weeks):"]
    lines.append(f"Most likely champion right now: **{tdf.iloc[0]['Team']}**.")
    lines.append("Full ranking:")
    for i, row in enumerate(tdf.itertuples(index=False), 1):
        lines.append(
            f"{i}. {row.Team} — score {row.title_score:.3f}, seed {int(row.seed)}, "
            f"rating {row.avg_rating_w:.2f}, PTS {row.pts_pg_w:.1f}"
        )
    return "\n".join(lines)


def _answer_champions_lounge(spec: QuerySpec) -> str:
    champs = defaultdict(list)
    for year in sorted(seasonInfo.keys()):
        po = poSeason(year)
        team = getattr(po, "PO_champ", None)
        if team:
            champs[team].append(year)

    if not champs:
        return NO_ANSWER_MSG

    if spec.team:
        years = sorted(champs.get(spec.team, []))
        if not years:
            return f"{spec.team} has not won a league championship in the available data."
        years_str = ", ".join(str(y) for y in years)
        return f"{spec.team} won {len(years)} championship(s): {years_str}."

    rows = sorted(champs.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    lines = ["Champions lounge (teams with at least one league championship):"]
    for i, (team, years) in enumerate(rows, 1):
        years_str = ", ".join(str(y) for y in sorted(years))
        lines.append(f"{i}. {team} — {len(years)} chip(s) [{years_str}]")
    return "\n".join(lines)


def _answer_record_vs_seed(spec: QuerySpec) -> str:
    seed = spec.seed or 1
    seed_mode = spec.seed_mode or "exact"
    rec = defaultdict(lambda: {"W": 0, "L": 0, "T": 0, "G": 0})

    years = _resolve_years(spec)
    for year in years:
        rs = _season(year)
        for week in range(2, rs.RSweekCount + 1):
            standings_prev = rs.get_WL_standings(1, week - 1) if rs.is_WL else rs.get_Cats_standings(1, week - 1)
            seed_of = {standings_prev[i][0]: i for i in standings_prev if isinstance(i, int)}
            week_matchups = [m for m in rs.matchups if m.week == week and m.is_reg and m.count]

            for m in week_matchups:
                for team, opp in [(m.team1, m.team2), (m.team2, m.team1)]:
                    opp_seed = seed_of.get(opp)
                    if opp_seed is None:
                        continue
                    include = opp_seed == seed if seed_mode == "exact" else opp_seed <= seed
                    if not include:
                        continue
                    if m.is_tied:
                        rec[team]["T"] += 1
                    elif m.winner == team:
                        rec[team]["W"] += 1
                    else:
                        rec[team]["L"] += 1
                    rec[team]["G"] += 1

    rows = []
    for team, r in rec.items():
        if r["G"] == 0:
            continue
        pct = (r["W"] + 0.5 * r["T"]) / r["G"]
        rows.append((team, r["W"], r["L"], r["T"], r["G"], pct))
    reverse = (spec.direction or "max") != "min"
    rows.sort(key=lambda x: (x[5], x[1], -x[2], x[0]), reverse=reverse)

    if not rows:
        return "No qualifying matchups found for that seed filter."

    label = f"top-{seed} seeds" if seed_mode == "top_k" else f"#{seed} seed"
    lines = [f"Record vs {label} (regular season, seed entering matchup week):"]
    for i, (team, w, l, t, g, pct) in enumerate(rows, 1):
        lines.append(f"{i}. {team} — {w}-{l}-{t} ({pct:.3f}, {g} games)")
    return "\n".join(lines)


def _answer_opponent_uplift(spec: QuerySpec) -> str:
    rows = []
    years = _resolve_years(spec)
    for year in years:
        rs = _season(year)
        df = rs.statDF.copy()
        df = df[(df["Week Name"].str.startswith("M")) & (df["real_matchup"] == 1)]
        opp_avg = df.groupby("Team")["week_rating"].mean().to_dict()
        for _, row in df.iterrows():
            team = row["Team"]
            opp = row["Opp"]
            if opp == "BYE" or opp not in opp_avg:
                continue
            diff = float(row["week_rating_opp"]) - float(opp_avg[opp])
            rows.append({"team": team, "diff": diff})

    if not rows:
        return "No opponent uplift rows found."

    ddf = pd.DataFrame(rows)
    agg = (
        ddf.groupby("team")
        .agg(
            games=("diff", "size"),
            avg_opp_delta=("diff", "mean"),
            median_opp_delta=("diff", "median"),
        )
        .reset_index()
        .sort_values("avg_opp_delta")
    )

    lines = ["Opponent uplift/suppression (opponent weekly rating vs you minus opponent season-average rating):"]
    for i, row in enumerate(agg.itertuples(index=False), 1):
        lines.append(
            f"{i}. {row.team} — avg {row.avg_opp_delta:+.2f}, median {row.median_opp_delta:+.2f}, games {int(row.games)}"
        )
    return "\n".join(lines)


def _answer_vs_weekly_top_team(spec: QuerySpec) -> str:
    years = _resolve_years(spec)
    counts = defaultdict(int)

    for year in years:
        rs = _season(year)
        df = rs.statDF.copy()
        df = _filter_df_by_scope(df, "RS")
        df = df.loc[(df["Team"] != "BYE") & (df["Opp"] != "BYE")]
        if "real_matchup" in df.columns:
            df = df.loc[df["real_matchup"] >= 1]
        if df.empty:
            continue

        for _, wk in df.groupby("Week Name"):
            tr = wk.groupby("Team", as_index=False)["week_rating"].mean()
            if tr.empty:
                continue
            mx = tr["week_rating"].max()
            top_teams = set(tr.loc[tr["week_rating"] == mx, "Team"])
            pairs = wk[["Team", "Opp"]].drop_duplicates()
            for _, row in pairs.iterrows():
                if row["Opp"] in top_teams:
                    counts[row["Team"]] += 1

    if not counts:
        return "No qualifying regular-season matchups found for weekly #1-opponent counts."

    rows = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    lines = [
        "Times each team faced an opponent that finished as weekly #1 rating (regular season, all-time scope if requested):"
    ]
    for i, (team, c) in enumerate(rows, 1):
        lines.append(f"{i}. {team} — {c}")
    return "\n".join(lines)


def _answer_correlation(spec: QuerySpec) -> str:
    # Supported initial metric names
    mx = (spec.metric_x or "record_vs_seed_1").strip().lower()
    my = (spec.metric_y or "overall_matchup_win_pct").strip().lower()

    aliases = {
        "regular season finish": "standings_position",
        "regular_season_finish": "standings_position",
        "playoff finish": "standings_position",
        "playoff_finish": "standings_position",
        "finish": "standings_position",
        "position": "standings_position",
        "standing position": "standings_position",
        "standings_position": "standings_position",
        "draft score": "draft_score",
        "draft_score": "draft_score",
    }
    mx = aliases.get(mx, mx)
    my = aliases.get(my, my)

    base = defaultdict(lambda: {"w": 0, "l": 0, "t": 0, "g": 0})
    overall = defaultdict(lambda: {"w": 0, "l": 0, "t": 0, "g": 0, "cat_w": 0, "cat_l": 0, "cat_t": 0, "rating_sum": 0.0, "weeks": 0})

    years = _resolve_years(spec)
    for year in years:
        rs = _season(year)
        for m in rs.matchups:
            if not (m.is_reg and m.count):
                continue
            t1, t2 = m.team1, m.team2
            if m.is_tied:
                overall[t1]["t"] += 1
                overall[t2]["t"] += 1
            else:
                overall[m.winner]["w"] += 1
                overall[m.loser]["l"] += 1
            overall[t1]["g"] += 1
            overall[t2]["g"] += 1
            overall[t1]["cat_w"] += m.wins
            overall[t1]["cat_l"] += m.losses
            overall[t1]["cat_t"] += m.ties
            overall[t2]["cat_w"] += m.losses
            overall[t2]["cat_l"] += m.wins
            overall[t2]["cat_t"] += m.ties

        rs_df = rs.statDF[(rs.statDF["Week Name"].str.startswith("M")) & (rs.statDF["real_matchup"] == 1)]
        gr = rs_df.groupby("Team")["week_rating"].agg(["sum", "count"]).to_dict("index")
        for team, vals in gr.items():
            overall[team]["rating_sum"] += float(vals["sum"])
            overall[team]["weeks"] += int(vals["count"])

        for week in range(2, rs.RSweekCount + 1):
            standings_prev = rs.get_WL_standings(1, week - 1) if rs.is_WL else rs.get_Cats_standings(1, week - 1)
            one = standings_prev[1][0]
            for m in [x for x in rs.matchups if x.week == week and x.is_reg and x.count]:
                if one not in (m.team1, m.team2):
                    continue
                ch = m.team2 if m.team1 == one else m.team1
                if m.is_tied:
                    base[ch]["t"] += 1
                elif m.winner == ch:
                    base[ch]["w"] += 1
                else:
                    base[ch]["l"] += 1
                base[ch]["g"] += 1

    def pct(w: int, l: int, t: int, g: int) -> float:
        return (w + 0.5 * t) / g if g else float("nan")

    rows = []
    for team in sorted(set(list(base.keys()) + list(overall.keys()))):
        b = base[team]
        o = overall[team]
        cat_den = o["cat_w"] + o["cat_l"] + o["cat_t"]
        rows.append(
            {
                "Team": team,
                "record_vs_seed_1": pct(b["w"], b["l"], b["t"], b["g"]),
                "overall_matchup_win_pct": pct(o["w"], o["l"], o["t"], o["g"]),
                "overall_category_win_pct": (o["cat_w"] + 0.5 * o["cat_t"]) / cat_den if cat_den else float("nan"),
                "avg_rating": (o["rating_sum"] / o["weeks"]) if o["weeks"] else float("nan"),
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return f"Not enough data to correlate {mx} vs {my}."

    # Lower standings_position is better. We proxy from cumulative matchup win%.
    if "standings_position" in (mx, my):
        df["standings_position"] = df["overall_matchup_win_pct"].rank(ascending=False, method="average")

    if "draft_score" in (mx, my):
        draft_tables = []
        for y in years:
            path = DATA_ROOT / str(y) / f"{y} Draft Results.csv"
            if path.exists():
                draft_tables.append(_load_draft_table(y)[["Team", "final_score"]])
        if draft_tables:
            draft_df = (
                pd.concat(draft_tables, ignore_index=True)
                .groupby("Team", as_index=False)["final_score"]
                .sum()
                .rename(columns={"final_score": "draft_score"})
            )
            df = df.merge(draft_df, on="Team", how="left")

    for m in (mx, my):
        if m not in df.columns:
            return f"Unsupported correlation metric '{m}'."

    df = df.dropna(subset=[mx, my])
    if df.empty:
        return f"Not enough data to correlate {mx} vs {my}."

    pear = df[[mx, my]].corr(method="pearson").iloc[0, 1]
    spear = df[[mx, my]].corr(method="spearman").iloc[0, 1]
    return (
        f"Correlation for {mx} vs {my} (n={len(df)} teams):\n"
        f"- Pearson: {pear:.4f}\n"
        f"- Spearman: {spear:.4f}"
    )


def _answer_mvp_by_avg_rating(spec: QuerySpec) -> str:
    rs = _season(spec.year)
    df = _filter_df_by_scope(rs.statDF, spec.scope)
    df = _filter_df_by_weeks(df, spec.week, spec.start_week, spec.end_week)
    df = df[(df["Team"] != "BYE") & (df["Opp"] != "BYE")]
    if "real_matchup" in df.columns:
        df = df[df["real_matchup"] >= 1]
    if df.empty:
        return "No rows found for MVP by average rating."

    rank = df.groupby("Team")["week_rating"].mean().sort_values(ascending=False)
    lines = ["Average rating ranking:"]
    for i, (team, val) in enumerate(rank.items(), 1):
        lines.append(f"{i}. {team} ({val:.2f})")
    return "\n".join(lines)


def _answer_category_sweep(spec: QuerySpec) -> str:
    stats = ["FG%", "FT%", "3PTM", "REB", "AST", "STL", "BLK", "TO", "PTS"]
    mode = (spec.mode or "best").lower()
    direction = "min" if mode == "worst" else "max"
    lines = [f"Category {'losers' if direction == 'min' else 'leaders'} ({spec.year}, {_scope_name(spec.scope)}):"]
    for stat in stats:
        row = _top_teams_for_stat(spec.year, stat, direction=direction, scope=spec.scope, top_n=1, start_week=spec.start_week, end_week=spec.end_week)
        if not row:
            continue
        team, val = row[0]
        lines.append(f"- {stat}: {team} ({_format_value(stat, float(val))})")
    return "\n".join(lines)


def _answer_strength_of_schedule(spec: QuerySpec) -> str:
    rs = _season(spec.year)
    df = _filter_df_by_scope(rs.statDF, spec.scope)
    df = _filter_df_by_weeks(df, spec.week, spec.start_week, spec.end_week)
    df = df[(df["Team"] != "BYE") & (df["Opp"] != "BYE")]
    if "real_matchup" in df.columns:
        df = df[df["real_matchup"] >= 1]
    if df.empty:
        return "No rows found for strength of schedule."

    rank = df.groupby("Team")["week_rating_opp"].mean().sort_values(ascending=False)
    lines = ["Strength of schedule (avg opponent rating, higher=tougher):"]
    for i, (team, val) in enumerate(rank.items(), 1):
        lines.append(f"{i}. {team} ({val:.2f})")
    return "\n".join(lines)


def _answer_team_rating_by_season(spec: QuerySpec) -> str:
    if not spec.team:
        return "Specify a team (e.g., 'average rating by season for Zahir')."
    years = sorted(seasonInfo.keys()) if (spec.year_range or "").upper() == "ALL" else [spec.year]
    rows = []
    for year in years:
        rs = _season(year)
        df = _filter_df_by_scope(rs.statDF, "RS")
        df = df[(df["Week Name"].str.startswith("M")) & (df["Team"] == spec.team)]
        if "real_matchup" in df.columns:
            df = df[df["real_matchup"] >= 1]
        if df.empty:
            continue
        rows.append((year, float(df["week_rating"].mean())))
    if not rows:
        return f"No average-rating rows found for {spec.team}."
    mode = (spec.mode or "").lower()
    if mode in {"best", "worst"}:
        best = mode == "best"
        y, v = max(rows, key=lambda x: x[1]) if best else min(rows, key=lambda x: x[1])
        return f"{spec.team}'s {'best' if best else 'worst'} season by average rating was {y} ({v:.2f})."
    lines = [f"{spec.team} average rating by season:"]
    for y, v in rows:
        lines.append(f"- {y}: {v:.2f}")
    return "\n".join(lines)


def _answer_schedule_toughest_stretch(spec: QuerySpec) -> str:
    if not spec.team:
        return "Specify a team for toughest stretch."
    window = max(2, min(10, int(spec.n or 5)))
    rs = _season(spec.year)
    df = _filter_df_by_scope(rs.statDF, spec.scope)
    df = df[(df["Week Name"].str.startswith("M")) & (df["Team"] == spec.team)]
    if "real_matchup" in df.columns:
        df = df[df["real_matchup"] >= 1]
    if df.empty:
        return f"No schedule rows found for {spec.team} in {spec.year}."

    wk = (
        df.groupby("Week", as_index=False)["week_rating_opp"]
        .mean()
        .sort_values("Week")
        .reset_index(drop=True)
    )
    if len(wk) < window:
        return f"Not enough weeks for a {window}-week stretch."

    best = None
    for i in range(0, len(wk) - window + 1):
        seg = wk.iloc[i : i + window]
        avg = float(seg["week_rating_opp"].mean())
        s = int(seg["Week"].iloc[0])
        e = int(seg["Week"].iloc[-1])
        if best is None or avg > best[0]:
            best = (avg, s, e)
    avg, s, e = best
    return (
        f"Toughest {window}-week stretch for {spec.team} in {spec.year} "
        f"({_scope_name(spec.scope)}): weeks {s}-{e}, avg opp rating {avg:.2f}."
    )


def _answer_half_split_improvement(spec: QuerySpec) -> str:
    rs = _season(spec.year)
    df = _filter_df_by_scope(rs.statDF, spec.scope)
    df = df[(df["Week Name"].str.startswith("M")) & (df["Team"] != "BYE")]
    if "real_matchup" in df.columns:
        df = df[df["real_matchup"] >= 1]
    if df.empty:
        return "No rows found for first-half vs second-half analysis."

    max_week = int(df["Week"].max())
    mid = max(1, max_week // 2)
    first = df[df["Week"] <= mid].groupby("Team")["week_rating"].mean()
    second = df[df["Week"] > mid].groupby("Team")["week_rating"].mean()
    joined = (
        pd.DataFrame({"first_half": first, "second_half": second})
        .dropna()
        .assign(delta=lambda t: t["second_half"] - t["first_half"])
        .sort_values("delta", ascending=False)
    )
    if joined.empty:
        return "No team had both first-half and second-half data."

    lines = [f"First-half to second-half improvement ({spec.year}, split at week {mid}):"]
    for i, (team, row) in enumerate(joined.iterrows(), 1):
        lines.append(f"{i}. {team} — {row['delta']:+.2f} ({row['first_half']:.2f} -> {row['second_half']:.2f})")
    return "\n".join(lines)


def _load_draft_table(year: int) -> pd.DataFrame:
    draft_path = DATA_ROOT / str(year) / f"{year} Draft Results.csv"
    df = pd.read_csv(draft_path)
    df["Rank_num"] = pd.to_numeric(df["Rank"], errors="coerce")
    df["Score_num"] = pd.to_numeric(df["Score"], errors="coerce")
    df["Overall_num"] = pd.to_numeric(df["Overall"], errors="coerce")
    df["quality"] = df["Rank_num"].apply(lambda r: 2 if pd.notna(r) and r != 501 else 1 if pd.notna(r) else 0)
    dedup = (
        df.sort_values(["Overall_num", "quality"], ascending=[True, False])
        .drop_duplicates(subset=["Overall_num"], keep="first")
        .copy()
    )
    dedup["final_rank"] = dedup["Rank_num"].fillna(501)
    dedup["final_score"] = dedup["Score_num"].where(
        dedup["Score_num"].notna(), dedup["Overall_num"] - dedup["final_rank"]
    )
    return dedup


def _answer_draft_pick_value(spec: QuerySpec) -> str:
    df = _load_draft_table(spec.year)
    mode = spec.mode or "top"
    n = spec.n or spec.top_n or 10
    n = max(1, min(50, int(n)))
    ranked = df.sort_values("final_score", ascending=(mode == "bottom")).head(n)
    lines = [f"Draft pick value ({mode} {n}) for {spec.year}:"]
    for i, (_, row) in enumerate(ranked.reset_index(drop=True).iterrows(), 1):
        lines.append(
            f"{i}. #{int(row['Overall_num'])} {row['Player']} ({row['Team']}) — {float(row['final_score']):.2f}"
        )
    return "\n".join(lines)


def _answer_draft_player_score(spec: QuerySpec) -> str:
    scope = (spec.year_range or "ALL").upper()
    mode = spec.mode or "top"
    method = (spec.method or "total").lower()
    n = spec.n or spec.top_n or 10
    n = max(1, min(50, int(n)))

    tables = []
    if scope == "ALL":
        years = sorted(seasonInfo.keys())
    else:
        years = [spec.year]

    for y in years:
        path = DATA_ROOT / str(y) / f"{y} Draft Results.csv"
        if not path.exists():
            continue
        df = _load_draft_table(y)[["Player", "final_score"]].copy()
        df["Year"] = y
        tables.append(df)

    if not tables:
        return "No draft tables found for player-level aggregation."

    all_df = pd.concat(tables, ignore_index=True)
    agg = (
        all_df.groupby("Player")
        .agg(total_score=("final_score", "sum"), selections=("final_score", "count"), avg_score=("final_score", "mean"))
        .reset_index()
    )
    rank_col = "avg_score" if method in {"avg", "average", "mean"} else "total_score"
    ranked = agg.sort_values(rank_col, ascending=(mode == "bottom")).head(n)

    title_scope = "all-time" if scope == "ALL" else str(spec.year)
    title_metric = "average score" if rank_col == "avg_score" else "total score"
    lines = [f"Draft player scores ({mode} {n} by {title_metric}, {title_scope}):"]
    for i, row in enumerate(ranked.itertuples(index=False), 1):
        lines.append(
            f"{i}. {row.Player} — total {float(row.total_score):.2f}, selections {int(row.selections)}, avg {float(row.avg_score):.2f}"
        )
    return "\n".join(lines)


def _answer_draft_team_score(spec: QuerySpec) -> str:
    scope = spec.year_range or "single_year"
    method = (spec.method or "total").lower()
    use_avg = method in {"avg", "average", "mean"}
    if scope == "ALL":
        tables = []
        for y in sorted(seasonInfo.keys()):
            path = DATA_ROOT / str(y) / f"{y} Draft Results.csv"
            if path.exists():
                df = _load_draft_table(y)[["Team", "final_score"]].copy()
                df["Year"] = y
                tables.append(df)
        if not tables:
            return "No draft tables found for all-time aggregation."
        all_df = pd.concat(tables, ignore_index=True)
    else:
        all_df = _load_draft_table(spec.year)[["Team", "final_score"]].copy()
        all_df["Year"] = spec.year

    grp = all_df.groupby("Team")
    if use_avg:
        per_team = grp.agg(
            score=("final_score", "mean"),
            selections=("final_score", "count"),
            seasons=("Year", pd.Series.nunique),
        ).sort_values("score", ascending=False)
        title_metric = "average draft score"
    else:
        per_team = grp.agg(
            score=("final_score", "sum"),
            selections=("final_score", "count"),
            seasons=("Year", pd.Series.nunique),
        ).sort_values("score", ascending=False)
        title_metric = "draft team scores"

    title = f"{title_metric.capitalize()} ({'all-time' if scope == 'ALL' else spec.year}):"
    lines = [title]
    for i, (team, row) in enumerate(per_team.iterrows(), 1):
        if use_avg:
            lines.append(
                f"{i}. {team} ({float(row['score']):.2f}; selections={int(row['selections'])}, seasons={int(row['seasons'])})"
            )
        else:
            lines.append(f"{i}. {team} ({float(row['score']):.2f})")
    return "\n".join(lines)


def _answer_correlation_scan(spec: QuerySpec) -> str:
    # baseline table from _answer_correlation data build
    base = defaultdict(lambda: {"w": 0, "l": 0, "t": 0, "g": 0})
    overall = defaultdict(lambda: {"w": 0, "l": 0, "t": 0, "g": 0, "cat_w": 0, "cat_l": 0, "cat_t": 0, "rating_sum": 0.0, "weeks": 0})
    for year in sorted(seasonInfo.keys()):
        rs = _season(year)
        for m in rs.matchups:
            if not (m.is_reg and m.count):
                continue
            t1, t2 = m.team1, m.team2
            if m.is_tied:
                overall[t1]["t"] += 1
                overall[t2]["t"] += 1
            else:
                overall[m.winner]["w"] += 1
                overall[m.loser]["l"] += 1
            overall[t1]["g"] += 1
            overall[t2]["g"] += 1
            overall[t1]["cat_w"] += m.wins
            overall[t1]["cat_l"] += m.losses
            overall[t1]["cat_t"] += m.ties
            overall[t2]["cat_w"] += m.losses
            overall[t2]["cat_l"] += m.wins
            overall[t2]["cat_t"] += m.ties
        rs_df = rs.statDF[(rs.statDF["Week Name"].str.startswith("M")) & (rs.statDF["real_matchup"] == 1)]
        gr = rs_df.groupby("Team")["week_rating"].agg(["sum", "count"]).to_dict("index")
        for team, vals in gr.items():
            overall[team]["rating_sum"] += float(vals["sum"])
            overall[team]["weeks"] += int(vals["count"])
        standings = rs.get_WL_standings() if rs.is_WL else rs.get_Cats_standings()
        pos = {standings[p][0]: p for p in standings}
        for team, p in pos.items():
            overall[team]["pos_sum"] = overall[team].get("pos_sum", 0) + p
            overall[team]["pos_n"] = overall[team].get("pos_n", 0) + 1

        for week in range(2, rs.RSweekCount + 1):
            standings_prev = rs.get_WL_standings(1, week - 1) if rs.is_WL else rs.get_Cats_standings(1, week - 1)
            one = standings_prev[1][0]
            for m in [x for x in rs.matchups if x.week == week and x.is_reg and x.count]:
                if one not in (m.team1, m.team2):
                    continue
                ch = m.team2 if m.team1 == one else m.team1
                if m.is_tied:
                    base[ch]["t"] += 1
                elif m.winner == ch:
                    base[ch]["w"] += 1
                else:
                    base[ch]["l"] += 1
                base[ch]["g"] += 1

    def pct(w, l, t, g):
        return (w + 0.5 * t) / g if g else float("nan")

    rows = []
    for team in sorted(set(base) | set(overall)):
        b, o = base[team], overall[team]
        cat_den = o["cat_w"] + o["cat_l"] + o["cat_t"]
        rows.append(
            {
                "Team": team,
                "playoff_success": 1 / (o.get("pos_sum", 999) / o.get("pos_n", 1)),
                "record_vs_seed_1": pct(b["w"], b["l"], b["t"], b["g"]),
                "overall_matchup_win_pct": pct(o["w"], o["l"], o["t"], o["g"]),
                "overall_category_win_pct": (o["cat_w"] + 0.5 * o["cat_t"]) / cat_den if cat_den else float("nan"),
                "avg_rating": (o["rating_sum"] / o["weeks"]) if o["weeks"] else float("nan"),
            }
        )
    df = pd.DataFrame(rows).dropna(subset=["playoff_success"])
    candidates = ["record_vs_seed_1", "overall_matchup_win_pct", "overall_category_win_pct", "avg_rating"]
    vals = []
    for c in candidates:
        tmp = df[["playoff_success", c]].dropna()
        if len(tmp) < 4:
            continue
        vals.append((c, tmp["playoff_success"].corr(tmp[c]), len(tmp)))
    vals.sort(key=lambda x: abs(x[1]), reverse=True)
    lines = ["Metric correlations vs playoff_success:"]
    for i, (metric, corr, n) in enumerate(vals, 1):
        lines.append(f"{i}. {metric} — corr {corr:.4f} (n={n})")
    return "\n".join(lines)


def _answer_trend_split(spec: QuerySpec) -> str:
    metric = spec.metric or "avg_rating"
    rows = []
    for year in sorted(seasonInfo.keys()):
        rs = _season(year)
        df = rs.statDF[(rs.statDF["Week Name"].str.startswith("M")) & (rs.statDF["real_matchup"] == 1)]
        avg = df.groupby("Team")["week_rating"].mean()
        for team, val in avg.items():
            rows.append({"Year": year, "Team": team, metric: float(val)})
    tdf = pd.DataFrame(rows).sort_values(["Team", "Year"])
    tdf["prev"] = tdf.groupby("Team")[metric].shift(1)
    tdf["delta"] = tdf[metric] - tdf["prev"]
    out = tdf.dropna(subset=["delta"]).sort_values("delta", ascending=False)
    if out.empty:
        return "No year-over-year trend rows available."
    lines = [f"Year-over-year jumps for {metric}:"]
    for i, (_, row) in enumerate(out.head(15).iterrows(), 1):
        lines.append(f"{i}. {row['Team']} {int(row['Year'])-1}->{int(row['Year'])}: {row['delta']:+.2f}")
    return "\n".join(lines)


def _answer_consistency(spec: QuerySpec) -> str:
    years = [spec.year] if (spec.year_range or "") != "ALL" and spec.year in seasonInfo else sorted(seasonInfo.keys())
    rows = []
    for year in years:
        rs = _season(year)
        df = rs.statDF[(rs.statDF["Week Name"].str.startswith("M")) & (rs.statDF["real_matchup"] == 1)]
        for team, val in df.groupby("Team")["week_rating"].std().items():
            rows.append({"Team": team, "std": float(val)})
    if not rows:
        return "No consistency rows available."
    volatile = (spec.mode or "").lower() == "volatile"
    rdf = pd.DataFrame(rows).groupby("Team")["std"].mean().sort_values(ascending=volatile)
    lines = ["Volatility ranking (higher std = more volatile):" if volatile else "Consistency ranking (lower std = more consistent):"]
    for i, (team, val) in enumerate(rdf.items(), 1):
        lines.append(f"{i}. {team} ({val:.2f})")
    return "\n".join(lines)


def _answer_what_if_schedule_swap(spec: QuerySpec) -> str:
    if not spec.team or not spec.team2:
        return "Need two teams for schedule swap."
    rs = _season(spec.year)
    fmt = spec.standings_format if spec.standings_format in {"wl", "cats"} else "wl"
    standings = rs.get_swapped_schedule_standings(spec.team, spec.team2, format=fmt)
    lines = [f"What-if swapped schedules ({spec.team} <-> {spec.team2}) in {spec.year}, format={fmt}:"]
    for place in sorted(standings):
        team, rec = standings[place]
        lines.append(f"{place}. {team} ({rec})")
    return "\n".join(lines)


def _answer_recap_regular_season(spec: QuerySpec) -> str:
    out = write_regular_season_recap(spec.year, output_path=Path(f"recaps/{spec.year}_regular_season_recap.md"))
    return f"Generated recap markdown: {out}"


def _answer_team_compare(spec: QuerySpec) -> str:
    if not spec.team or not spec.team2:
        return "For team comparison, include two teams (e.g., 'compare Fano vs Ange in 2026')."

    rs = _season(spec.year)
    df = _filter_df_by_scope(rs.statDF, spec.scope)
    df = _filter_df_by_weeks(df, spec.week, spec.start_week, spec.end_week)

    t1_df = df.loc[df["Team"] == spec.team]
    t2_df = df.loc[df["Team"] == spec.team2]

    if t1_df.empty or t2_df.empty:
        return f"I couldn't find enough data to compare {spec.team} and {spec.team2} in {spec.year}."

    if spec.stat:
        s1 = _aggregate_team_stat(t1_df, spec.stat)
        s2 = _aggregate_team_stat(t2_df, spec.stat)
        v1 = float(s1.iloc[0]) if not s1.empty else 0.0
        v2 = float(s2.iloc[0]) if not s2.empty else 0.0

        if spec.stat == "TO":
            winner = spec.team if v1 < v2 else spec.team2 if v2 < v1 else "Tie"
        else:
            winner = spec.team if v1 > v2 else spec.team2 if v2 > v1 else "Tie"

        return (
            f"{spec.year} {_scope_name(spec.scope)} comparison for {spec.stat}:\n"
            f"- {spec.team}: {_format_value(spec.stat, v1)}\n"
            f"- {spec.team2}: {_format_value(spec.stat, v2)}\n"
            f"Winner: **{winner}**"
        )

    cat_summary = []
    stat_cats = ["FG%", "FT%", "3PTM", "PTS", "REB", "AST", "STL", "BLK", "TO"]
    t1_wins = t2_wins = ties = 0
    for cat in stat_cats:
        v1 = float(_aggregate_team_stat(t1_df, cat).iloc[0])
        v2 = float(_aggregate_team_stat(t2_df, cat).iloc[0])

        if cat == "TO":
            if v1 < v2:
                t1_wins += 1
                win_team = spec.team
            elif v2 < v1:
                t2_wins += 1
                win_team = spec.team2
            else:
                ties += 1
                win_team = "Tie"
        else:
            if v1 > v2:
                t1_wins += 1
                win_team = spec.team
            elif v2 > v1:
                t2_wins += 1
                win_team = spec.team2
            else:
                ties += 1
                win_team = "Tie"

        cat_summary.append(f"- {cat}: {spec.team} {_format_value(cat, v1)} | {spec.team2} {_format_value(cat, v2)} -> {win_team}")

    return (
        f"{spec.year} {_scope_name(spec.scope)} category comparison: {spec.team} vs {spec.team2}\n"
        f"Category score: **{spec.team} {t1_wins} - {t2_wins} {spec.team2}** (ties: {ties})\n"
        + "\n".join(cat_summary)
    )


def _answer_head_to_head(spec: QuerySpec) -> str:
    if not spec.team or not spec.team2:
        return "For head-to-head, include two teams (e.g., 'head to head Fano vs Ange in 2026')."

    rs = _season(spec.year)
    df = _filter_df_by_scope(rs.statDF, spec.scope)
    df = _filter_df_by_weeks(df, spec.week, spec.start_week, spec.end_week)

    h2h = df.loc[(df["Team"] == spec.team) & (df["Opp"] == spec.team2)]
    if h2h.empty:
        return f"No direct head-to-head rows found for {spec.team} vs {spec.team2} in {spec.year} ({_scope_name(spec.scope)})."

    cat_wins = int(h2h["cat_wins"].sum())
    cat_losses = int(h2h["cat_losses"].sum())
    cat_ties = int(h2h["cat_ties"].sum())
    matchup_wins = int(h2h["matchup_win"].sum())
    matchup_losses = int(h2h["matchup_loss"].sum())
    matchup_ties = int(h2h["matchup_tie"].sum())

    return (
        f"Head-to-head {spec.year} ({_scope_name(spec.scope)}): {spec.team} vs {spec.team2}\n"
        f"- Matchups: {matchup_wins}W-{matchup_losses}L-{matchup_ties}D\n"
        f"- Category score: {cat_wins}W-{cat_losses}L-{cat_ties}D"
    )


def _answer_record_vs_team(spec: QuerySpec) -> str:
    if not spec.team:
        return "Specify a target team (e.g., 'best record against Juan')."

    target = spec.team
    years = _resolve_years(spec)
    rec = defaultdict(lambda: {"W": 0, "L": 0, "T": 0, "G": 0})

    for year in years:
        rs = _season(year)
        df = _filter_df_by_scope(rs.statDF, spec.scope)
        df = _filter_df_by_weeks(df, spec.week, spec.start_week, spec.end_week)
        df = df[(df["Team"] != "BYE") & (df["Opp"] != "BYE")]
        if "real_matchup" in df.columns:
            df = df[df["real_matchup"] >= 1]
        df = df[(df["Opp"] == target) & (df["Team"] != target)]
        if df.empty:
            continue

        gr = (
            df.groupby("Team")[["matchup_win", "matchup_loss", "matchup_tie"]]
            .sum()
            .reset_index()
        )
        for _, row in gr.iterrows():
            team = row["Team"]
            w = int(row["matchup_win"])
            l = int(row["matchup_loss"])
            t = int(row["matchup_tie"])
            rec[team]["W"] += w
            rec[team]["L"] += l
            rec[team]["T"] += t
            rec[team]["G"] += w + l + t

    rows = []
    for team, r in rec.items():
        if r["G"] <= 0:
            continue
        pct = (r["W"] + 0.5 * r["T"]) / r["G"]
        rows.append((team, r["W"], r["L"], r["T"], r["G"], pct))

    if not rows:
        return f"No qualifying matchups found against {target}."

    metric = spec.metric or "win_pct"
    direction = (spec.direction or "max").lower()
    asc = direction == "min"
    period = "all-time" if (spec.year_range or "").upper() == "ALL" else str(spec.year)
    scope_label = _scope_name(spec.scope)

    def _fmt_rows(sorted_rows, n: int = 10) -> list[str]:
        lines = []
        for i, (team, w, l, t, g, pct) in enumerate(sorted_rows[:n], 1):
            lines.append(f"{i}. {team} — {w}-{l}-{t} ({pct:.3f}, {g} games)")
        return lines

    if metric == "both":
        wins_rows = sorted(rows, key=lambda x: (x[1], x[5], -x[2], x[0]), reverse=not asc)
        pct_rows = sorted(rows, key=lambda x: (x[5], x[1], -x[2], x[0]), reverse=not asc)
        wins_title = f"{'Fewest' if asc else 'Most'} wins vs {target} ({period}, {scope_label}):"
        pct_title = f"{'Worst' if asc else 'Best'} record vs {target} ({period}, {scope_label}):"
        return "\n".join(
            [wins_title, *_fmt_rows(wins_rows), "", pct_title, *_fmt_rows(pct_rows)]
        )

    if metric == "wins":
        rows.sort(key=lambda x: (x[1], x[5], -x[2], x[0]), reverse=not asc)
        title = (
            f"{'Fewest' if asc else 'Most'} wins vs {target} "
            f"({period}, {scope_label}):"
        )
    else:
        rows.sort(key=lambda x: (x[5], x[1], -x[2], x[0]), reverse=not asc)
        title = (
            f"{'Worst' if asc else 'Best'} record vs {target} "
            f"({period}, {scope_label}):"
        )

    lines = [title]
    for i, (team, w, l, t, g, pct) in enumerate(rows, 1):
        lines.append(f"{i}. {team} — {w}-{l}-{t} ({pct:.3f}, {g} games)")
    return "\n".join(lines)


def _answer_matchup_tie_leaders(spec: QuerySpec) -> str:
    years = _resolve_years(spec)
    ties_by_team = Counter()
    games_by_team = Counter()

    for year in years:
        rs = _season(year)
        df = _filter_df_by_scope(rs.statDF, spec.scope)
        df = _filter_df_by_weeks(df, spec.week, spec.start_week, spec.end_week)
        df = df[(df["Team"] != "BYE") & (df["Opp"] != "BYE")]
        if "real_matchup" in df.columns:
            df = df[df["real_matchup"] >= 1]
        if df.empty:
            continue

        agg = (
            df.groupby("Team")[["matchup_tie", "matchup_win", "matchup_loss"]]
            .sum()
            .reset_index()
        )
        for _, row in agg.iterrows():
            team = str(row["Team"])
            t = int(row["matchup_tie"])
            w = int(row["matchup_win"])
            l = int(row["matchup_loss"])
            g = w + l + t
            ties_by_team[team] += t
            games_by_team[team] += g

    rows = []
    for team, ties in ties_by_team.items():
        g = int(games_by_team.get(team, 0))
        rate = (ties / g) if g > 0 else 0.0
        rows.append((team, int(ties), g, rate))

    if not rows:
        return "No matchup tie data found."

    mode = (spec.mode or "top").lower()
    if mode == "bottom":
        rows.sort(key=lambda x: (x[1], x[3], x[0]))
        title = f"Fewest matchup ties ({'all-time' if (spec.year_range or '').upper() == 'ALL' else spec.year}, {_scope_name(spec.scope)}):"
    else:
        rows.sort(key=lambda x: (-x[1], -x[3], x[0]))
        title = f"Most matchup ties ({'all-time' if (spec.year_range or '').upper() == 'ALL' else spec.year}, {_scope_name(spec.scope)}):"

    n = max(1, int(spec.n or spec.top_n or 10))
    out = rows[:n]
    lines = [title]
    for i, (team, ties, g, rate) in enumerate(out, 1):
        lines.append(f"{i}. {team} — {ties} ties ({g} games, {rate:.3f} tie rate)")
    return "\n".join(lines)


def _answer_matchup_tie_history(spec: QuerySpec) -> str:
    if not spec.team:
        return "Specify a team (e.g., 'what years did Ange tie matchups?')."

    years = sorted(_resolve_years(spec))
    rows = []
    for year in years:
        rs = _season(year)
        df = _filter_df_by_scope(rs.statDF, spec.scope)
        df = _filter_df_by_weeks(df, spec.week, spec.start_week, spec.end_week)
        df = df[(df["Team"] != "BYE") & (df["Opp"] != "BYE")]
        if "real_matchup" in df.columns:
            df = df[df["real_matchup"] >= 1]
        tdf = df.loc[df["Team"] == spec.team]
        if tdf.empty:
            continue
        t = int(tdf["matchup_tie"].sum())
        g = int(tdf["matchup_win"].sum() + tdf["matchup_loss"].sum() + tdf["matchup_tie"].sum())
        rows.append((year, t, g))

    if not rows:
        return f"No matchup tie history found for {spec.team}."

    years_with = [(y, t, g) for y, t, g in rows if t > 0]
    years_without = [(y, t, g) for y, t, g in rows if t == 0]
    mode = (spec.mode or "years_with_ties").lower()

    if mode == "first_zero_check":
        cur = next(((y, t, g) for y, t, g in rows if y == spec.year), None)
        if not cur:
            return f"No data for {spec.team} in {spec.year}."
        _, cur_t, _ = cur
        if cur_t > 0:
            return f"No. {spec.team} has {cur_t} matchup ties in {spec.year}."
        prior_zero = [y for y, t, _ in rows if y < spec.year and t == 0]
        if not prior_zero:
            return f"Yes. {spec.year} is the first season {spec.team} had 0 matchup ties."
        return f"No. {spec.team} also had 0 matchup ties in: {', '.join(map(str, prior_zero))}."

    if mode == "first_tie_check":
        cur = next(((y, t, g) for y, t, g in rows if y == spec.year), None)
        if not cur:
            return f"No data for {spec.team} in {spec.year}."
        _, cur_t, _ = cur
        if cur_t == 0:
            return f"No. {spec.team} has 0 matchup ties in {spec.year}."
        prior_tie = [y for y, t, _ in rows if y < spec.year and t > 0]
        if not prior_tie:
            return f"Yes. {spec.year} is the first season {spec.team} had matchup ties."
        return f"No. {spec.team} had matchup ties before: {', '.join(map(str, prior_tie))}."

    if mode == "first_tie_season":
        if not years_with:
            return f"{spec.team} has never had a matchup tie."
        y, t, g = min(years_with, key=lambda x: x[0])
        return f"First season {spec.team} had matchup ties: {y} ({t} ties in {g} games)."

    if mode == "last_tie_season":
        if not years_with:
            return f"{spec.team} has never had a matchup tie."
        y, t, g = max(years_with, key=lambda x: x[0])
        return f"Last season {spec.team} had matchup ties: {y} ({t} ties in {g} games)."

    if mode == "first_zero_season":
        if not years_without:
            return f"{spec.team} has matchup ties in every season with data."
        y, _, g = min(years_without, key=lambda x: x[0])
        return f"First season {spec.team} had 0 matchup ties: {y} ({g} games)."

    if mode == "last_zero_season":
        if not years_without:
            return f"{spec.team} has matchup ties in every season with data."
        y, _, g = max(years_without, key=lambda x: x[0])
        return f"Last season {spec.team} had 0 matchup ties: {y} ({g} games)."

    if mode == "years_without_ties":
        if not years_without:
            return f"{spec.team} has matchup ties in every season with data."
        lines = [f"Seasons {spec.team} had 0 matchup ties:"]
        for y, _, g in years_without:
            lines.append(f"- {y} ({g} games)")
        return "\n".join(lines)

    # default: years_with_ties
    if not years_with:
        return f"{spec.team} has no seasons with matchup ties."
    lines = [f"Seasons {spec.team} had matchup ties:"]
    for y, t, g in years_with:
        lines.append(f"- {y}: {t} ties ({g} games)")
    return "\n".join(lines)


def _answer_team_summary(spec: QuerySpec) -> str:
    if not spec.team:
        return "For team summary, include a team name (e.g., 'summary for Fano in 2026')."

    rs = _season(spec.year)
    df = _filter_df_by_scope(rs.statDF, spec.scope)
    df = _filter_df_by_weeks(df, spec.week, spec.start_week, spec.end_week)
    tdf = df.loc[df["Team"] == spec.team]
    if tdf.empty:
        return f"No data found for {spec.team} in {spec.year} ({_scope_name(spec.scope)})."

    lines = [f"{spec.team} summary, {spec.year} ({_scope_name(spec.scope)}):"]

    for stat in ["FG%", "FT%", "3PTM", "PTS", "REB", "AST", "STL", "BLK", "TO"]:
        val = _aggregate_team_stat(tdf, stat)
        if val.empty:
            continue
        lines.append(f"- {stat}: {_format_value(stat, float(val.iloc[0]))}")

    lines.append(
        f"- Matchup record rows: {int(tdf['matchup_win'].sum())}W-{int(tdf['matchup_loss'].sum())}L-{int(tdf['matchup_tie'].sum())}D"
    )

    return "\n".join(lines)


def _answer_all_time_stats_table(spec: QuerySpec) -> str:
    scope = spec.scope if spec.scope in {"ALL", "RS", "PO"} else "ALL"
    method = (spec.method or "total").lower()
    method = "avg" if method in {"avg", "average", "averages"} else "total"
    df = _all_time_stats_df(scope, method)
    if df.empty:
        return "No all-time stats rows found."

    if spec.team:
        row = df.loc[df["Team"].str.lower() == str(spec.team).lower()]
        if row.empty:
            return f"{spec.team} is not recognized for all-time stats."
        row = row.iloc[0]
        lines = [f"{row['Team']} {scope} {'averages' if method == 'avg' else 'totals'}:"]
        for cat in gDocStatCats:
            lines.append(f"- {cat}: {_format_value(cat, float(row[cat]))}")
        return "\n".join(lines)

    if spec.stat and spec.stat in gDocStatCats:
        ranked = df[["Team", spec.stat]].sort_values(spec.stat, ascending=(spec.direction == "min"))
        n = max(1, min(int(spec.top_n or 10), len(ranked)))
        title = f"All-time {scope} {'averages' if method == 'avg' else 'totals'} by {spec.stat}:"
        lines = [title]
        for i, (_, r) in enumerate(ranked.head(n).iterrows(), 1):
            lines.append(f"{i}. {r['Team']} ({_format_value(spec.stat, float(r[spec.stat]))})")
        return "\n".join(lines)

    lines = [f"All-time {scope} {'averages' if method == 'avg' else 'totals'} (GDoc table coverage):"]
    for _, r in df.sort_values("Team").iterrows():
        vals = ", ".join(f"{cat}={_format_value(cat, float(r[cat]))}" for cat in gDocStatCats)
        lines.append(f"- {r['Team']}: {vals}")
    return "\n".join(lines)


def _answer_all_time_summary(spec: QuerySpec) -> str:
    teams = list(allMembers)
    years = sorted(seasonInfo.keys())

    chips = Counter()
    finals = Counter()
    playoffs = Counter()
    team_rows = []

    for y in years:
        po = poSeason(y)
        champ = getattr(po, "PO_champ", None)
        if champ:
            chips[champ] += 1
        po_teams = list(getattr(po, "PO_teams", []) or [])
        for t in po_teams:
            playoffs[t] += 1
        for t in po_teams:
            try:
                standing = po.standings.get(t)
                if standing in (1, 2):
                    finals[t] += 1
            except Exception:
                pass

    # Build lightweight all-time summary table.
    for t in teams:
        # Approx all-time avg rating from weekly rating means across RS.
        vals = []
        for y in years:
            sdf = _season(y).statDF
            tdf = sdf[(sdf["Week Name"].str.startswith("M")) & (sdf["Team"] == t)]
            if "real_matchup" in tdf.columns:
                tdf = tdf[tdf["real_matchup"] >= 1]
            if not tdf.empty:
                vals.append(float(tdf["week_rating"].mean()))
        avg_rating = float(sum(vals) / len(vals)) if vals else 0.0
        team_rows.append(
            {
                "Team": t,
                "Chips": int(chips.get(t, 0)),
                "Finals": int(finals.get(t, 0)),
                "Playoffs": int(playoffs.get(t, 0)),
                "Avg Rating": avg_rating,
            }
        )

    smry = pd.DataFrame(team_rows)
    if smry.empty:
        return "No all-time summary rows found."

    if spec.team:
        row = smry.loc[smry["Team"].str.lower() == str(spec.team).lower()]
        if row.empty:
            return f"{spec.team} is not recognized in all-time summary."
        r = row.iloc[0]
        return (
            f"{r['Team']} all-time summary:\n"
            f"- Chips: {int(r['Chips'])}\n"
            f"- Finals: {int(r['Finals'])}\n"
            f"- Playoffs: {int(r['Playoffs'])}\n"
            f"- Avg Rating: {float(r['Avg Rating']):.2f}"
        )

    ranked = smry.sort_values(["Chips", "Finals", "Playoffs", "Avg Rating"], ascending=False)
    n = max(1, min(int(spec.top_n or 10), len(ranked)))
    lines = ["All-time summary (top teams by Chips, Finals, Playoffs, Avg Rating):"]
    for i, (_, r) in enumerate(ranked.head(n).iterrows(), 1):
        lines.append(
            f"{i}. {r['Team']} — Chips {int(r['Chips'])}, Finals {int(r['Finals'])}, Playoffs {int(r['Playoffs'])}, AvgRating {float(r['Avg Rating']):.2f}"
        )
    return "\n".join(lines)


def _answer_week_leader(spec: QuerySpec) -> str:
    if spec.week is None and spec.start_week is None:
        return "Specify a week (e.g., 'week 5') or range (e.g., 'weeks 3 to 8')."

    if not spec.stat:
        return "Specify a stat for weekly leaders (e.g., PTS, REB, AST...)."

    return _answer_leader(spec)


def _answer_weekly_top_performer_count(spec: QuerySpec) -> str:
    years = _resolve_years(spec)
    counts = Counter()

    for year in years:
        rs = _season(year)
        df = _filter_df_by_scope(rs.statDF, spec.scope)
        df = df[(df["Week Name"].str.startswith("M")) & (df["Team"] != "BYE") & (df["Opp"] != "BYE")]
        if "real_matchup" in df.columns:
            df = df[df["real_matchup"] >= 1]
        if df.empty:
            continue

        for _, wk in df.groupby("Week Name"):
            mx = wk["week_rating"].max()
            winners = wk.loc[wk["week_rating"] == mx, "Team"].unique().tolist()
            for team in winners:
                counts[str(team)] += 1

    if not counts:
        return "No weekly top-performer data found."

    rows = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    title = f"Most #1 weekly ratings ({'all-time' if (spec.year_range or '').upper() == 'ALL' else spec.year}):"
    lines = [title]
    for i, (team, n) in enumerate(rows, 1):
        lines.append(f"{i}. {team} ({n})")
    return "\n".join(lines)


def _build_context_tables(spec: QuerySpec) -> str:
    rs = _season(spec.year)
    df = _filter_df_by_scope(rs.statDF, spec.scope)
    df = _filter_df_by_weeks(df, spec.week, spec.start_week, spec.end_week)
    df = df.loc[(df["Team"] != "BYE") & (df["Opp"] != "BYE")]
    if "real_matchup" in df.columns:
        df = df.loc[df["real_matchup"] >= 1]

    if df.empty:
        return "No rows in selected scope/week range."

    agg = df.groupby("Team")[["PTS", "REB", "AST", "STL", "BLK", "TO", "3PTM", "FG%", "FT%"]].agg({
        "PTS": "sum",
        "REB": "sum",
        "AST": "sum",
        "STL": "sum",
        "BLK": "sum",
        "TO": "sum",
        "3PTM": "sum",
        "FG%": "mean",
        "FT%": "mean",
    }).sort_values("PTS", ascending=False)

    sample = agg.round(4).to_csv()

    extra_sections = []
    if spec.team:
        opp_df = df.loc[df["Opp"] == spec.team].copy()
        if not opp_df.empty:
            cols = [c for c in ["Year", "Week", "Week Name", "Team", "Opp", "PTS", "REB", "AST", "STL", "BLK", "TO"] if c in opp_df.columns]
            top_opp = opp_df.sort_values("PTS", ascending=False).head(25)[cols]
            extra_sections.append(f"Top rows where Opp == {spec.team} (sorted by PTS):\n{top_opp.to_csv(index=False)}")

    standings_blob = ""
    if spec.intent in {"standings", "standings_alternate", "predict_champion", "record_vs_seed", "correlation", "correlation_scan"}:
        wl = rs.get_WL_standings()
        cats = rs.get_Cats_standings()
        wl_rows = [f"{k}. {v[0]} ({v[1]})" for k, v in wl.items()]
        cat_rows = [f"{k}. {v[0]} ({v[1]})" for k, v in cats.items()]
        standings_blob = (
            f"WL standings:\n" + "\n".join(wl_rows) + "\n\n"
            f"Category standings:\n" + "\n".join(cat_rows) + "\n\n"
        )

    return (
        f"Season: {spec.year}, scope: {spec.scope}\n"
        f"{standings_blob}"
        f"Team aggregate table:\n{sample}\n\n"
        + ("\n\n".join(extra_sections) if extra_sections else "")
    )


def _answer_with_llm(question: str, spec: QuerySpec) -> Optional[str]:
    if spec.deterministic_only:
        return None

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    remaining, limit = budget_remaining()
    if limit > 0 and remaining <= 0:
        return None

    try:
        from openai import OpenAI
    except Exception:
        return None

    client = OpenAI(api_key=api_key)
    model = os.getenv("DISCORD_QA_MODEL", "gpt-4.1-mini")

    context = _build_context_tables(spec)
    deterministic_hint = None
    if spec.intent in {
        "leader",
        "leader_vs_team",
        "standings",
        "best_team_snapshot",
        "standings_alternate",
        "predict_champion",
        "champions_lounge",
        "mvp_by_avg_rating",
        "category_sweep",
        "strength_of_schedule",
        "draft_pick_value",
        "draft_player_score",
        "draft_team_score",
        "team_compare",
        "head_to_head",
        "record_vs_team",
        "matchup_tie_leaders",
        "matchup_tie_history",
        "team_summary",
        "team_rating_by_season",
        "all_time_stats_table",
        "all_time_summary",
        "week_leader",
        "schedule_toughest_stretch",
        "half_split_improvement",
        "weekly_top_performer_count",
        "record_vs_seed",
        "opponent_uplift",
        "vs_weekly_top_team",
        "correlation",
        "correlation_scan",
        "trend_split",
        "consistency",
        "what_if_schedule_swap",
        "recap_regular_season",
    }:
        handler_map = {
            "leader": _answer_leader,
            "leader_vs_team": _answer_leader_vs_team,
            "standings": _answer_standings,
            "best_team_snapshot": _answer_best_team_snapshot,
            "standings_alternate": _answer_standings_alternate,
            "predict_champion": _answer_predict_champion,
            "champions_lounge": _answer_champions_lounge,
            "mvp_by_avg_rating": _answer_mvp_by_avg_rating,
            "category_sweep": _answer_category_sweep,
            "strength_of_schedule": _answer_strength_of_schedule,
            "draft_pick_value": _answer_draft_pick_value,
            "draft_player_score": _answer_draft_player_score,
            "draft_team_score": _answer_draft_team_score,
            "team_compare": _answer_team_compare,
            "head_to_head": _answer_head_to_head,
            "record_vs_team": _answer_record_vs_team,
            "matchup_tie_leaders": _answer_matchup_tie_leaders,
            "matchup_tie_history": _answer_matchup_tie_history,
            "team_summary": _answer_team_summary,
            "team_rating_by_season": _answer_team_rating_by_season,
            "all_time_stats_table": _answer_all_time_stats_table,
            "all_time_summary": _answer_all_time_summary,
            "week_leader": _answer_week_leader,
            "schedule_toughest_stretch": _answer_schedule_toughest_stretch,
            "half_split_improvement": _answer_half_split_improvement,
            "weekly_top_performer_count": _answer_weekly_top_performer_count,
            "record_vs_seed": _answer_record_vs_seed,
            "opponent_uplift": _answer_opponent_uplift,
            "vs_weekly_top_team": _answer_vs_weekly_top_team,
            "correlation": _answer_correlation,
            "correlation_scan": _answer_correlation_scan,
            "trend_split": _answer_trend_split,
            "consistency": _answer_consistency,
            "what_if_schedule_swap": _answer_what_if_schedule_swap,
            "recap_regular_season": _answer_recap_regular_season,
        }
        try:
            deterministic_hint = handler_map[spec.intent](spec)
            if deterministic_hint == "__NO_STAT_FOR_LEADER__":
                deterministic_hint = None
        except Exception:
            deterministic_hint = None

    sys_prompt = (
        "You are a fantasy basketball data analyst bot. "
        "Answer ONLY from provided data context and deterministic hint when present. "
        "Prefer concise responses. "
        "If the user asks a simple ranking/place question, answer in one short sentence. "
        "If the context is insufficient, say what is missing and ask one targeted follow-up. "
        "Do not include league standings unless the question explicitly asks for standings or seed/place."
    )

    try:
        resp = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": sys_prompt},
                {
                    "role": "user",
                    "content": (
                        f"Question: {question}\n\n"
                        f"Deterministic hint (if available):\n{deterministic_hint}\n\n"
                        f"Data context:\n{context}"
                    ),
                },
            ],
            temperature=0.2,
            max_output_tokens=_get_llm_max_output_tokens(),
        )
        in_tok, out_tok, total_tok = extract_usage(resp)
        record_usage("answer", model, question, in_tok, out_tok, total_tok)
        text = getattr(resp, "output_text", "").strip()
        return text or None
    except Exception:
        return None


def _should_prefer_deterministic(question: str, spec: QuerySpec) -> bool:
    q = question.lower()
    # Keep trivial place/rank responses terse and deterministic.
    if spec.intent == "standings" and spec.place is not None:
        return True
    if spec.intent in {
        "record_vs_team",
        "matchup_tie_leaders",
        "matchup_tie_history",
        "best_team_snapshot",
        "record_vs_seed",
        "vs_weekly_top_team",
        "weekly_top_performer_count",
        "opponent_uplift",
        "draft_player_score",
        "draft_team_score",
        "head_to_head",
        "team_compare",
        "category_sweep",
        "team_rating_by_season",
        "all_time_stats_table",
        "all_time_summary",
        "schedule_toughest_stretch",
        "half_split_improvement",
    }:
        return True
    if "first place" in q or "second place" in q or "third place" in q:
        return True
    return False


def _requires_llm_for_accuracy(question: str, spec: QuerySpec) -> bool:
    q = question.lower()
    # These filters are not covered by deterministic handlers yet; avoid misleading fallback.
    if spec.intent == "leader" and ("against " in q or "vs " in q or "versus " in q):
        return True
    return False


def _is_llm_budget_exhausted() -> bool:
    remaining, limit = budget_remaining()
    return limit > 0 and remaining <= 0


def _is_ranking_question(question: str) -> bool:
    q = question.lower()
    ranking_terms = [
        "rank",
        "ranking",
        "place",
        "best",
        "worst",
        "most",
        "least",
        "top",
        "leader",
        "first",
        "second",
        "third",
    ]
    return any(term in q for term in ranking_terms)


def _has_explicit_timeframe(question: str) -> bool:
    q = question.lower()
    if re.search(r"\b20\d{2}\b", q):
        return True
    explicit_terms = [
        "all-time",
        "all time",
        "career",
        "entire career",
        "this season",
        "current season",
        "last season",
        "regular season",
        "playoffs",
        "postseason",
    ]
    if any(term in q for term in explicit_terms):
        return True
    if re.search(r"\bweeks?\b|\bweek\s*\d+\b", q):
        return True
    return False


def _should_return_both_current_and_all_time(question: str, spec: QuerySpec) -> bool:
    if _has_explicit_timeframe(question):
        return False
    if (spec.year_range or "").upper() == "ALL":
        return False
    dual_intents = {
        "record_vs_team",
        "matchup_tie_leaders",
        "record_vs_seed",
        "opponent_uplift",
        "vs_weekly_top_team",
        "weekly_top_performer_count",
        "draft_player_score",
        "draft_team_score",
    }
    return spec.intent in dual_intents


def _is_current_matchup_question(question: str) -> bool:
    q = question.lower()
    return (
        "current matchup" in q
        or "currently winning" in q
        or "this week" in q
        or "who would win this week" in q
        or "who wins this week" in q
        or ("winning" in q and "matchup" in q and "current" in q)
        or ("winning" in q and "between" in q and "matchup" in q)
    )


def _is_matchup_winner_question(question: str) -> bool:
    q = question.lower()
    return (
        "who would win" in q
        or "who wins" in q
        or "currently winning" in q
        or "current matchup" in q
        or ("winning" in q and "matchup" in q)
    )


def answer_query(question: str, spec: QuerySpec) -> str:
    invalid = _validate_year(spec)
    if invalid:
        return invalid

    # Keep year defaulted if parser left it empty by mistake.
    if not spec.year:
        spec.year = currentYear

    # Interpret "current matchup" as current-week regular-season head-to-head.
    if (
        spec.team
        and spec.team2
        and _is_current_matchup_question(question)
        and spec.week is None
        and spec.start_week is None
        and spec.end_week is None
    ):
        spec.intent = "head_to_head"
        spec.scope = "RS"
        try:
            spec.week = int(_season(spec.year).currentWeek)
        except Exception:
            pass

    # Normalize week-based "who wins" phrasing into head-to-head instead of weekly stat leaders.
    if (
        spec.intent == "week_leader"
        and spec.stat is None
        and _is_matchup_winner_question(question)
    ):
        spec.intent = "head_to_head"
        spec.scope = "RS"
        if spec.week is None and spec.start_week is not None and spec.end_week is not None and spec.start_week == spec.end_week:
            spec.week = spec.start_week

    # Universal metric engine handles flexible metric+operator+filter combinations.
    # Try this early for broad stat queries to reduce intent-fragility.
    universal = _try_answer_universal_metric_query(question, spec)
    if universal and spec.intent in {"unknown", "leader", "week_leader", "standings", "team_compare", "draft_team_score", "draft_player_score", "champions_lounge"}:
        return universal

    if spec.intent == "unknown":
        if spec.needs_clarification:
            return _clarification_response(spec)
        if re.search(r"\b(me|my|myself)\b", question.lower()):
            return (
                "I couldn't map 'me' to a team. Add your Discord user ID to the user-team map CSV "
                "and restart the bot."
            )
        if _is_llm_budget_exhausted():
            return LLM_BUDGET_EXHAUSTED_MSG
        record_unanswered(question, spec, reason="unknown_intent")
        return NO_ANSWER_MSG

    if spec.intent == "head_to_head" and (not spec.team or not spec.team2):
        if re.search(r"\b(me|my|myself)\b", question.lower()):
            return (
                "I couldn't map 'me' to a team. Add your Discord user ID to the user-team map CSV "
                "and restart the bot."
            )

    handlers = {
        "leader": _answer_leader,
        "leader_vs_team": _answer_leader_vs_team,
        "standings": _answer_standings,
        "best_team_snapshot": _answer_best_team_snapshot,
        "standings_alternate": _answer_standings_alternate,
        "predict_champion": _answer_predict_champion,
        "champions_lounge": _answer_champions_lounge,
        "mvp_by_avg_rating": _answer_mvp_by_avg_rating,
        "category_sweep": _answer_category_sweep,
        "strength_of_schedule": _answer_strength_of_schedule,
        "draft_pick_value": _answer_draft_pick_value,
        "draft_player_score": _answer_draft_player_score,
        "draft_team_score": _answer_draft_team_score,
        "team_compare": _answer_team_compare,
        "head_to_head": _answer_head_to_head,
        "record_vs_team": _answer_record_vs_team,
        "matchup_tie_leaders": _answer_matchup_tie_leaders,
        "matchup_tie_history": _answer_matchup_tie_history,
        "team_summary": _answer_team_summary,
        "team_rating_by_season": _answer_team_rating_by_season,
        "all_time_stats_table": _answer_all_time_stats_table,
        "all_time_summary": _answer_all_time_summary,
        "week_leader": _answer_week_leader,
        "schedule_toughest_stretch": _answer_schedule_toughest_stretch,
        "half_split_improvement": _answer_half_split_improvement,
        "weekly_top_performer_count": _answer_weekly_top_performer_count,
        "record_vs_seed": _answer_record_vs_seed,
        "opponent_uplift": _answer_opponent_uplift,
        "vs_weekly_top_team": _answer_vs_weekly_top_team,
        "correlation": _answer_correlation,
        "correlation_scan": _answer_correlation_scan,
        "trend_split": _answer_trend_split,
        "consistency": _answer_consistency,
        "what_if_schedule_swap": _answer_what_if_schedule_swap,
        "recap_regular_season": _answer_recap_regular_season,
    }

    handler = handlers.get(spec.intent)
    deterministic_response = None
    if handler:
        if _should_return_both_current_and_all_time(question, spec):
            current_spec = QuerySpec(**vars(spec))
            current_spec.year_range = None
            all_time_spec = QuerySpec(**vars(spec))
            all_time_spec.year_range = "ALL"

            current_resp = handler(current_spec)
            all_time_resp = handler(all_time_spec)
            response = (
                f"Current season ({spec.year}):\n{current_resp}\n\n"
                f"All-time:\n{all_time_resp}"
            )
        else:
            response = handler(spec)
        if response == "__NO_STAT_FOR_LEADER__":
            record_unanswered(question, spec, reason="missing_stat_for_leader")
            return (
                "I couldn't identify the stat. Try one of: PTS, REB, AST, STL, BLK, TO, 3PTM, FG%, FT%, "
                "or ask standings/rank directly (e.g., 'who is in first place in 2026?')."
            )
        deterministic_response = response

    if deterministic_response and (_should_prefer_deterministic(question, spec) or spec.deterministic_only):
        if deterministic_response == NO_ANSWER_MSG:
            if _is_llm_budget_exhausted():
                return LLM_BUDGET_EXHAUSTED_MSG
            record_unanswered(question, spec, reason="deterministic_no_answer")
        return deterministic_response

    if deterministic_response:
        if deterministic_response == NO_ANSWER_MSG:
            if _is_llm_budget_exhausted():
                return LLM_BUDGET_EXHAUSTED_MSG
            record_unanswered(question, spec, reason="deterministic_no_answer")
        return deterministic_response

    # Final fallback when no deterministic handler matched.
    if _is_llm_budget_exhausted():
        return LLM_BUDGET_EXHAUSTED_MSG
    record_unanswered(question, spec, reason="no_supported_handler")
    return NO_ANSWER_MSG
