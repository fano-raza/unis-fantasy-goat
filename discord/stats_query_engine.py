import os
import math
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from Models.seasons import regSeason
from Models.seasons import poSeason
from constants import currentYear, seasonInfo
from recaps.recap_utils import write_regular_season_recap
from shared.runtime_config import DATA_ROOT
from .llm_usage import budget_remaining, extract_usage, record_usage
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

NO_ANSWER_MSG = "I can't answer that with the data/functions I have right now."



@lru_cache(maxsize=16)
def _season(year: int) -> regSeason:
    return regSeason(year)


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
    df = _filter_df_by_weeks(df, week=week, start_week=start_week, end_week=end_week)
    if stat not in df.columns:
        return pd.Series(dtype="float64")

    agg = _aggregate_team_stat(df, stat)
    ascending = direction == "min"
    return agg.sort_values(ascending=ascending)


def _format_value(stat: str, value: float) -> str:
    if stat in ("FG%", "FT%"):
        return f"{value:.4f}"
    return f"{value:.2f}" if isinstance(value, float) else str(value)


def _scope_name(scope: str) -> str:
    return {"ALL": "entire season", "RS": "regular season", "PO": "playoffs"}.get(scope, "scope")


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

    if fmt == "wl":
        standings = rs.get_WL_standings()
        title = "W/L standings"
    else:
        standings = rs.get_Cats_standings()
        title = "Category standings"

    if spec.place is not None:
        if spec.place not in standings:
            return f"That league only has placements 1-{len(standings)} for {spec.year}."
        team, record = standings[spec.place]
        return f"{spec.year} {title}: **{team}** is in {_ordinal(spec.place)} place ({record})."

    lines = [f"{spec.year} {title}:"]
    for place, (team, record) in standings.items():
        lines.append(f"{place}. {team} ({record})")
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
    rows.sort(key=lambda x: (x[5], x[1], -x[2], x[0]), reverse=True)

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
    mx = spec.metric_x or "record_vs_seed_1"
    my = spec.metric_y or "overall_matchup_win_pct"

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
    df = pd.DataFrame(rows).dropna(subset=[mx, my])
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


def _answer_draft_team_score(spec: QuerySpec) -> str:
    scope = spec.year_range or "single_year"
    if scope == "ALL":
        tables = []
        for y in sorted(seasonInfo.keys()):
            path = DATA_ROOT / str(y) / f"{y} Draft Results.csv"
            if path.exists():
                tables.append(_load_draft_table(y)[["Team", "final_score"]])
        if not tables:
            return "No draft tables found for all-time aggregation."
        all_df = pd.concat(tables, ignore_index=True)
    else:
        all_df = _load_draft_table(spec.year)[["Team", "final_score"]]

    rank = all_df.groupby("Team")["final_score"].sum().sort_values(ascending=False)
    title = f"Draft team scores ({'all-time' if scope == 'ALL' else spec.year}):"
    lines = [title]
    for i, (team, val) in enumerate(rank.items(), 1):
        lines.append(f"{i}. {team} ({float(val):.2f})")
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
    rdf = pd.DataFrame(rows).groupby("Team")["std"].mean().sort_values()
    lines = ["Consistency ranking (lower std = more consistent):"]
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


def _answer_week_leader(spec: QuerySpec) -> str:
    if spec.week is None and spec.start_week is None:
        return "Specify a week (e.g., 'week 5') or range (e.g., 'weeks 3 to 8')."

    if not spec.stat:
        return "Specify a stat for weekly leaders (e.g., PTS, REB, AST...)."

    return _answer_leader(spec)


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
        "standings_alternate",
        "predict_champion",
        "champions_lounge",
        "mvp_by_avg_rating",
        "strength_of_schedule",
        "draft_pick_value",
        "draft_team_score",
        "team_compare",
        "head_to_head",
        "team_summary",
        "week_leader",
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
            "standings_alternate": _answer_standings_alternate,
            "predict_champion": _answer_predict_champion,
            "champions_lounge": _answer_champions_lounge,
            "mvp_by_avg_rating": _answer_mvp_by_avg_rating,
            "strength_of_schedule": _answer_strength_of_schedule,
            "draft_pick_value": _answer_draft_pick_value,
            "draft_team_score": _answer_draft_team_score,
            "team_compare": _answer_team_compare,
            "head_to_head": _answer_head_to_head,
            "team_summary": _answer_team_summary,
            "week_leader": _answer_week_leader,
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
    if "first place" in q or "second place" in q or "third place" in q:
        return True
    return False


def _requires_llm_for_accuracy(question: str, spec: QuerySpec) -> bool:
    q = question.lower()
    # These filters are not covered by deterministic handlers yet; avoid misleading fallback.
    if spec.intent == "leader" and ("against " in q or "vs " in q or "versus " in q):
        return True
    return False


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


def answer_query(question: str, spec: QuerySpec) -> str:
    invalid = _validate_year(spec)
    if invalid:
        return invalid

    # Keep year defaulted if parser left it empty by mistake.
    if not spec.year:
        spec.year = currentYear

    if spec.intent == "unknown":
        record_unanswered(question, spec, reason="unknown_intent")
        return NO_ANSWER_MSG

    handlers = {
        "leader": _answer_leader,
        "leader_vs_team": _answer_leader_vs_team,
        "standings": _answer_standings,
        "standings_alternate": _answer_standings_alternate,
        "predict_champion": _answer_predict_champion,
        "champions_lounge": _answer_champions_lounge,
        "mvp_by_avg_rating": _answer_mvp_by_avg_rating,
        "strength_of_schedule": _answer_strength_of_schedule,
        "draft_pick_value": _answer_draft_pick_value,
        "draft_team_score": _answer_draft_team_score,
        "team_compare": _answer_team_compare,
        "head_to_head": _answer_head_to_head,
        "team_summary": _answer_team_summary,
        "week_leader": _answer_week_leader,
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
        response = handler(spec)
        if response == "__NO_STAT_FOR_LEADER__":
            record_unanswered(question, spec, reason="missing_stat_for_leader")
            if spec.deterministic_only:
                return "For this command, specify a stat (PTS, REB, AST, STL, BLK, TO, 3PTM, FG%, FT%)."
            llm_answer = _answer_with_llm(question, spec)
            if llm_answer:
                return llm_answer
            return (
                "I couldn't identify the stat. Try one of: PTS, REB, AST, STL, BLK, TO, 3PTM, FG%, FT%, "
                "or ask standings/rank directly (e.g., 'who is in first place in 2026?')."
            )
        deterministic_response = response

    if deterministic_response and (_should_prefer_deterministic(question, spec) or spec.deterministic_only):
        if spec.deterministic_only and _requires_llm_for_accuracy(question, spec):
            record_unanswered(question, spec, reason="requires_llm_in_deterministic_mode")
            return (
                "This deterministic command can't reliably answer 'against <team>' phrasing yet. "
                "Try a more explicit deterministic command or use mention-based free-form mode."
            )
        if deterministic_response == NO_ANSWER_MSG:
            record_unanswered(question, spec, reason="deterministic_no_answer")
        return deterministic_response

    llm_answer = _answer_with_llm(question, spec)
    if llm_answer:
        return llm_answer

    if deterministic_response:
        if _requires_llm_for_accuracy(question, spec):
            if spec.deterministic_only:
                record_unanswered(question, spec, reason="requires_llm_in_deterministic_mode")
                return (
                    "This deterministic command can't reliably answer 'against <team>' phrasing yet. "
                    "Try a more explicit deterministic command or use mention-based free-form mode."
                )
            record_unanswered(question, spec, reason="requires_llm_but_unavailable")
            return (
                "I need LLM answering enabled to reliably handle that phrasing (e.g., 'against <team>'). "
                "Please verify OPENAI_API_KEY is set, then ask again."
            )
        if deterministic_response == NO_ANSWER_MSG:
            record_unanswered(question, spec, reason="deterministic_no_answer")
        return deterministic_response

    # Final fallback when no deterministic handler matched.
    record_unanswered(question, spec, reason="no_supported_handler")
    return NO_ANSWER_MSG
