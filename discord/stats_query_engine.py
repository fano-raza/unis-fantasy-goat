import os
from functools import lru_cache
from typing import Dict, Optional

import pandas as pd

from Models.seasons import regSeason
from constants import currentYear, seasonInfo
from .llm_usage import budget_remaining, extract_usage, record_usage
from .query_parser import QuerySpec

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

    wl = rs.get_WL_standings()
    cats = rs.get_Cats_standings()

    wl_rows = [f"{k}. {v[0]} ({v[1]})" for k, v in wl.items()]
    cat_rows = [f"{k}. {v[0]} ({v[1]})" for k, v in cats.items()]

    sample = agg.round(4).to_csv()

    extra_sections = []
    if spec.team:
        opp_df = df.loc[df["Opp"] == spec.team].copy()
        if not opp_df.empty:
            cols = [c for c in ["Year", "Week", "Week Name", "Team", "Opp", "PTS", "REB", "AST", "STL", "BLK", "TO"] if c in opp_df.columns]
            top_opp = opp_df.sort_values("PTS", ascending=False).head(25)[cols]
            extra_sections.append(f"Top rows where Opp == {spec.team} (sorted by PTS):\n{top_opp.to_csv(index=False)}")

    return (
        f"Season: {spec.year}, scope: {spec.scope}\n"
        f"WL standings:\n" + "\n".join(wl_rows) + "\n\n"
        f"Category standings:\n" + "\n".join(cat_rows) + "\n\n"
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
    if spec.intent in {"leader", "standings", "team_compare", "head_to_head", "team_summary", "week_leader"}:
        handler_map = {
            "leader": _answer_leader,
            "standings": _answer_standings,
            "team_compare": _answer_team_compare,
            "head_to_head": _answer_head_to_head,
            "team_summary": _answer_team_summary,
            "week_leader": _answer_week_leader,
        }
        try:
            deterministic_hint = handler_map[spec.intent](spec)
            if deterministic_hint == "__NO_STAT_FOR_LEADER__":
                deterministic_hint = None
        except Exception:
            deterministic_hint = None

    ranking_instruction = ""
    if _is_ranking_question(question):
        ranking_instruction = (
            "This is a ranking-style question. "
            "Your answer must include BOTH: "
            "(1) the direct requested rank result (e.g., best/worst/top item), and "
            "(2) the full ordered ranking list across all relevant teams/years in the provided scope. "
            "Use numbered lines for the full ranking. "
        )

    sys_prompt = (
        "You are a fantasy basketball data analyst bot. "
        "Answer ONLY from provided data context and deterministic hint when present. "
        "Prefer concise responses. "
        "If the user asks a simple ranking/place question, answer in one short sentence. "
        "If the context is insufficient, say what is missing and ask one targeted follow-up. "
        + ranking_instruction
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

    handlers = {
        "leader": _answer_leader,
        "standings": _answer_standings,
        "team_compare": _answer_team_compare,
        "head_to_head": _answer_head_to_head,
        "team_summary": _answer_team_summary,
        "week_leader": _answer_week_leader,
    }

    handler = handlers.get(spec.intent)
    deterministic_response = None
    if handler:
        response = handler(spec)
        if response == "__NO_STAT_FOR_LEADER__":
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
            return (
                "This deterministic command can't reliably answer 'against <team>' phrasing yet. "
                "Try a more explicit deterministic command or use mention-based free-form mode."
            )
        return deterministic_response

    llm_answer = _answer_with_llm(question, spec)
    if llm_answer:
        return llm_answer

    if deterministic_response:
        if _requires_llm_for_accuracy(question, spec):
            if spec.deterministic_only:
                return (
                    "This deterministic command can't reliably answer 'against <team>' phrasing yet. "
                    "Try a more explicit deterministic command or use mention-based free-form mode."
                )
            return (
                "I need LLM answering enabled to reliably handle that phrasing (e.g., 'against <team>'). "
                "Please verify OPENAI_API_KEY is set, then ask again."
            )
        return deterministic_response

    # Final fallback when no deterministic handler matched.
    return (
        "I couldn't confidently parse that request yet. "
        "Try specifying: year, stat, scope (regular season/playoffs), and optionally teams/weeks. "
        "Example: 'compare Fano vs Ange in 2026 regular season for rebounds'."
    )
