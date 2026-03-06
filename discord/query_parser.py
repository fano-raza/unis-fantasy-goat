import json
import os
import re
from dataclasses import dataclass
from typing import Optional

from constants import allMembers, currentYear, seasonInfo
from .capability_router import route_question
from .llm_usage import budget_remaining, extract_usage, record_usage

STAT_SYNONYMS = {
    "PTS": ["pts", "point", "points", "scoring"],
    "REB": ["reb", "rebound", "rebounds"],
    "AST": ["ast", "assist", "assists"],
    "STL": ["stl", "steal", "steals"],
    "BLK": ["blk", "block", "blocks"],
    "TO": ["turnover", "turnovers"],
    "3PTM": ["3pt", "3ptm", "three pointers", "threes", "3 pointers", "3s"],
    "FG%": ["fg", "fg%", "field goal", "field goal percentage"],
    "FT%": ["ft", "ft%", "free throw", "free throw percentage"],
}

VALID_STATS = list(STAT_SYNONYMS.keys())
VALID_SCOPES = ["ALL", "RS", "PO"]
VALID_INTENTS = {
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
    "week_leader",
    "schedule_toughest_stretch",
    "half_split_improvement",
    "weekly_top_performer_count",
    "record_vs_seed",
    "opponent_uplift",
    "correlation",
    "correlation_scan",
    "trend_split",
    "consistency",
    "what_if_schedule_swap",
    "recap_regular_season",
    "vs_weekly_top_team",
    "unknown",
}

CAPABILITY_CATALOG: list[dict[str, str]] = [
    {"intent": "leader", "description": "Top/bottom teams for a stat (PTS/REB/AST/etc.) in a season/scope."},
    {"intent": "leader_vs_team", "description": "Top/bottom teams in a stat specifically against a target team."},
    {"intent": "standings", "description": "Category or W-L standings, optionally by place/rank or specific team."},
    {"intent": "best_team_snapshot", "description": "Best team right now summary (standings + current metrics)."},
    {"intent": "standings_alternate", "description": "Alternative standings format comparison (category vs W-L)."},
    {"intent": "predict_champion", "description": "Champion prediction style ranking for a season."},
    {"intent": "champions_lounge", "description": "Historical champions summary across years."},
    {"intent": "mvp_by_avg_rating", "description": "MVP style ranking by average team rating."},
    {"intent": "category_sweep", "description": "Category leaders/laggards across multiple stats."},
    {"intent": "strength_of_schedule", "description": "Schedule difficulty by opponent quality."},
    {"intent": "draft_pick_value", "description": "Best/worst single draft picks in a season."},
    {"intent": "draft_player_score", "description": "Best/worst players by aggregate draft score across seasons."},
    {"intent": "draft_team_score", "description": "Best/worst drafting teams by aggregate draft score."},
    {"intent": "team_compare", "description": "Compare two teams on season stats/rankings."},
    {"intent": "head_to_head", "description": "Direct matchup result between two teams (week/current)."},
    {"intent": "record_vs_team", "description": "Best/worst record or most/fewest wins against a target team."},
    {"intent": "matchup_tie_leaders", "description": "Teams with most/fewest tied matchups."},
    {"intent": "matchup_tie_history", "description": "Year-by-year tie history for a team."},
    {"intent": "team_summary", "description": "Season summary/profile for one team."},
    {"intent": "team_rating_by_season", "description": "Best/worst season(s) for a team across years."},
    {"intent": "week_leader", "description": "Weekly leaders for a stat in one week/range."},
    {"intent": "schedule_toughest_stretch", "description": "Toughest/easiest week stretch for a team."},
    {"intent": "half_split_improvement", "description": "First-half vs second-half performance changes."},
    {"intent": "weekly_top_performer_count", "description": "Who finished #1 in weekly ratings most often."},
    {"intent": "record_vs_seed", "description": "Record versus top-k seeds or specific seed(s)."},
    {"intent": "opponent_uplift", "description": "Who faced strongest opponents on average."},
    {"intent": "correlation", "description": "Correlation between two metrics for one season."},
    {"intent": "correlation_scan", "description": "Scan strongest correlations across candidate metrics."},
    {"intent": "trend_split", "description": "Trend/split analysis by timing windows."},
    {"intent": "consistency", "description": "Most/least consistent teams over time."},
    {"intent": "what_if_schedule_swap", "description": "What-if schedule swap scenario analysis."},
    {"intent": "recap_regular_season", "description": "Regular-season recap for a target year."},
    {"intent": "vs_weekly_top_team", "description": "Who faced weekly #1 teams the most."},
]


@dataclass
class QuerySpec:
    intent: str = "leader"
    year: int = currentYear
    stat: Optional[str] = None
    scope: str = "ALL"  # ALL | RS | PO
    direction: str = "max"  # max | min
    top_n: int = 1
    team: Optional[str] = None
    team2: Optional[str] = None
    week: Optional[int] = None
    start_week: Optional[int] = None
    end_week: Optional[int] = None
    standings_format: str = "auto"  # auto | wl | cats
    place: Optional[int] = None
    seed: Optional[int] = None
    seed_mode: str = "exact"  # exact | top_k
    k: Optional[int] = None
    year_range: Optional[str] = None
    timing: Optional[str] = None
    method: Optional[str] = None
    mode: Optional[str] = None
    n: Optional[int] = None
    metric: Optional[str] = None
    target_metric: Optional[str] = None
    candidate_metrics: Optional[str] = None
    metric_x: Optional[str] = None
    metric_y: Optional[str] = None
    deterministic_only: bool = False


def _normalize_scope(raw: Optional[str]) -> str:
    if not raw:
        return "ALL"
    s = raw.strip().upper()
    return s if s in VALID_SCOPES else "ALL"


def _normalize_intent(raw: Optional[str]) -> str:
    if not raw:
        return "unknown"
    s = raw.strip().lower()
    return s if s in VALID_INTENTS else "unknown"


def _normalize_standings_format(raw: Optional[str]) -> str:
    if not raw:
        return "auto"
    s = raw.strip().lower()
    return s if s in {"auto", "wl", "cats"} else "auto"


def _normalize_year_range(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    s = str(raw).strip().upper()
    if s in {"ALL", "ALL_TIME", "ALLTIME", "CAREER"}:
        return "ALL"
    if s in {"NONE", "SINGLE", "SINGLE_YEAR", ""}:
        return None
    return s


def _normalize_stat(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None

    s = raw.strip().upper()
    if s in VALID_STATS:
        return s

    s_low = raw.strip().lower()
    for canonical, aliases in STAT_SYNONYMS.items():
        if s_low == canonical.lower() or any(alias in s_low for alias in aliases):
            return canonical
    return None


def _normalize_team(raw: Optional[str], year: int) -> Optional[str]:
    if not raw:
        return None
    target = raw.strip().lower()

    teams = seasonInfo.get(year, ([],))[0] if year in seasonInfo else allMembers
    for team in teams:
        if str(team).lower() == target:
            return team

    for team in allMembers:
        if str(team).lower() == target:
            return team

    return None


def _parse_scope(question: str) -> str:
    q = question.lower()
    if any(k in q for k in ["playoff", "playoffs", "postseason"]) or re.search(r"\\bpo\\b", q):
        return "PO"
    if any(k in q for k in ["regular season", "reg season"]) or re.search(r"\\brs\\b", q):
        return "RS"
    return "ALL"


def _parse_direction(question: str) -> str:
    q = question.lower()
    if any(k in q for k in ["least", "fewest", "lowest", "min"]):
        return "min"
    return "max"


def _extract_weeks(question: str):
    nums = [int(x) for x in re.findall(r"\bweek\s*(\d{1,2})\b", question.lower())]
    rng = re.search(r"weeks?\s*(\d{1,2})\s*(?:to|-|through)\s*(\d{1,2})", question.lower())

    week = nums[0] if nums else None
    start_week = end_week = None
    if rng:
        start_week = int(rng.group(1))
        end_week = int(rng.group(2))

    return week, start_week, end_week


def _extract_top_n(question: str) -> int:
    m = re.search(r"\btop\s*(\d+)\b", question.lower())
    if m:
        return max(1, min(10, int(m.group(1))))
    m = re.search(r"\b(\d+)\s*(?:best|leaders?)\b", question.lower())
    if m:
        return max(1, min(10, int(m.group(1))))
    return 1


def _extract_place(question: str) -> Optional[int]:
    q = question.lower()

    numeric = re.search(r"\b(\d+)(?:st|nd|rd|th)?\s+place\b", q)
    if numeric:
        return int(numeric.group(1))

    word_to_place = {
        "first": 1,
        "second": 2,
        "third": 3,
        "fourth": 4,
        "fifth": 5,
        "sixth": 6,
        "seventh": 7,
        "eighth": 8,
        "ninth": 9,
        "tenth": 10,
    }
    for word, place in word_to_place.items():
        if re.search(rf"\b{word}\s+place\b", q):
            return place
    return None


def _extract_teams(question: str, year: int):
    q = question.lower()
    teams = seasonInfo.get(year, ([],))[0] if year in seasonInfo else allMembers

    found = []
    for team in teams:
        t = str(team).lower()
        idx = q.find(t)
        if idx != -1:
            found.append((idx, team))

    found.sort(key=lambda x: x[0])

    # de-duplicate preserving mention order
    unique = []
    for _, t in found:
        if t not in unique:
            unique.append(t)

    t1 = unique[0] if len(unique) >= 1 else None
    t2 = unique[1] if len(unique) >= 2 else None
    return t1, t2


def _resolve_relative_year(question: str) -> int:
    q = question.lower()
    year_match = re.search(r"\b(20\d{2})\b", q)
    if year_match:
        return int(year_match.group(1))
    if "last season" in q:
        return currentYear - 1
    if "this season" in q or "current season" in q or "this year" in q:
        return currentYear
    ago = re.search(r"\b(\d+)\s*(?:season|seasons|year|years)\s+ago\b", q)
    if ago:
        return currentYear - int(ago.group(1))
    prev = re.search(r"\bprevious\s+(\d+)\s*(?:season|seasons|year|years)\b", q)
    if prev:
        return currentYear - int(prev.group(1))
    return currentYear


def _fallback_parse(question: str) -> QuerySpec:
    year = _resolve_relative_year(question)

    stat = None
    q_low = question.lower()

    def _has_alias(text: str, alias: str) -> bool:
        if re.search(r"[^a-z0-9 ]", alias):
            return alias in text
        if len(alias) <= 3:
            return re.search(rf"\b{re.escape(alias)}\b", text) is not None
        return alias in text

    for canonical, aliases in STAT_SYNONYMS.items():
        canon = canonical.lower()
        canon_match = _has_alias(q_low, canon)
        alias_match = any(_has_alias(q_low, alias) for alias in aliases)
        if canon_match or alias_match:
            stat = canonical
            break

    team, team2 = _extract_teams(question, year)
    week, start_week, end_week = _extract_weeks(question)
    top_n = _extract_top_n(question)
    place = _extract_place(question)

    intent = "unknown"
    standings_format = "auto"

    standings_signal = (
        "standings" in q_low
        or "seed" in q_low
        or "rank" in q_low
        or "place in the league" in q_low
        or "place in league" in q_low
        or place is not None
    )

    if standings_signal:
        intent = "standings"
        if "category" in q_low or "cat " in q_low or "cats" in q_low:
            standings_format = "cats"
        elif "w/l" in q_low or "matchup" in q_low or "record" in q_low:
            standings_format = "wl"
    elif (week or start_week) and stat is None and any(k in q_low for k in ["record", "wins", "won", "winning"]):
        intent = "standings"
        standings_format = "wl"
        if any(k in q_low for k in ["best", "most", "top", "first"]):
            place = 1
    elif any(k in q_low for k in ["head to head", "head-to-head", "h2h"]):
        intent = "head_to_head"
    elif team and team2 and any(k in q_low for k in ["who would win", "who wins", "currently winning", "current matchup", "this week"]):
        intent = "head_to_head"
        if week is None and start_week is None and end_week is None and "this week" in q_low:
            week = None
    elif team and team2 and any(k in q_low for k in ["vs", "versus", "compare", "between"]):
        intent = "team_compare"
    elif team and team2 and any(
        k in q_low
        for k in [
            "who was better",
            "who is better",
            "better in",
            "better team",
            "stronger team",
            "better season",
            "who did better",
        ]
    ):
        intent = "team_compare"
    elif team and stat is None and any(k in q_low for k in ["summary", "profile", "how did", "show me"]):
        intent = "team_summary"
    elif week or start_week:
        intent = "week_leader"
    elif stat and team and ("against" in q_low or "vs " in q_low or "versus " in q_low):
        intent = "leader_vs_team"
    elif stat:
        intent = "leader"

    return QuerySpec(
        intent=intent,
        year=year,
        stat=stat,
        scope=_parse_scope(question),
        direction=_parse_direction(question),
        top_n=top_n,
        team=team,
        team2=team2,
        week=week,
        start_week=start_week,
        end_week=end_week,
        standings_format=standings_format,
        place=place,
    )


def _llm_plan(question: str) -> Optional[dict]:
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

    model = os.getenv("DISCORD_QA_MODEL", "gpt-4.1-mini")
    client = OpenAI(api_key=api_key)
    teams_blob = ", ".join(map(str, allMembers))
    catalog_blob = "\n".join(
        f"- {entry['intent']}: {entry['description']}" for entry in CAPABILITY_CATALOG
    )

    prompt = f"""
You are a semantic planner for a fantasy-basketball bot.
Return ONE JSON object only (no prose, no markdown) with these keys:
intent, year, relative_year_offset, year_range, scope, stat, direction, top_n,
team, team2, week, start_week, end_week, standings_format, place,
seed, seed_mode, k, timing, method, mode, n, metric, target_metric, candidate_metrics, metric_x, metric_y, confidence.

Rules:
- intent must match one capability from this catalog:
{catalog_blob}
- stat must be one of {VALID_STATS} or null
- scope must be ALL|RS|PO (default ALL)
- direction must be max|min
- standings_format must be auto|wl|cats
- place can be integer or "last" or null
- year: explicit numeric year if present, else null
- relative_year_offset: 0 for "this/current season", -1 for "last season", -2 for "2 years ago", else null
- year_range: "ALL" for all-time/career, else null
- confidence: float 0..1
- if a capability can answer, choose it even with casual wording/slang
- do NOT output stats/results, only planning fields
- teams must be canonical names from: {teams_blob}
- if user asks for "best team right now", prefer intent=best_team_snapshot
- if user asks "best/worst season for team", prefer intent=team_rating_by_season and mode=best|worst
- if user asks record/wins against a team, prefer intent=record_vs_team

Interpretation:
- "who would win this week/team vs team this week/current matchup/currently winning" => intent=head_to_head scope=RS
- "best team right now/top team rn/current best team" => intent=best_team_snapshot
- "best/worst season for a team" => intent=team_rating_by_season with mode=best|worst and year_range=ALL
- "my/me/i" can map to team only if explicit team is present in text; otherwise leave null.

If ambiguous and cannot map reliably, set intent="unknown" and confidence <= 0.45.
"""

    try:
        response = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": question},
            ],
            temperature=0,
            max_output_tokens=128,
        )
        in_tok, out_tok, total_tok = extract_usage(response)
        record_usage("parse", model, question, in_tok, out_tok, total_tok)
        text = getattr(response, "output_text", "").strip()
        if not text:
            return None
        return json.loads(text)
    except Exception:
        return None


def _get_llm_parse_confidence_threshold() -> float:
    raw = os.getenv("DISCORD_LLM_PARSE_CONFIDENCE", "0.35").strip()
    try:
        v = float(raw)
    except Exception:
        return 0.35
    return max(0.0, min(1.0, v))


def _spec_from_llm_plan(data: dict) -> QuerySpec:
    year_raw = data.get("year")
    rel_raw = data.get("relative_year_offset")
    if year_raw is not None:
        try:
            year = int(year_raw)
        except Exception:
            year = currentYear
    elif rel_raw is not None:
        try:
            year = currentYear + int(rel_raw)
        except Exception:
            year = currentYear
    else:
        year = currentYear

    place_raw = data.get("place")
    place: Optional[int] = None
    if place_raw == "last":
        place = len(seasonInfo.get(year, (allMembers,))[0])
    elif place_raw is not None:
        try:
            place = int(place_raw)
        except Exception:
            place = None

    top_n_raw = data.get("top_n", 1)
    try:
        top_n = max(1, min(30, int(top_n_raw)))
    except Exception:
        top_n = 1

    intent = _normalize_intent(data.get("intent"))
    scope = _normalize_scope(data.get("scope"))
    direction = "min" if str(data.get("direction", "max")).lower() == "min" else "max"

    return QuerySpec(
        intent=intent,
        year=year,
        stat=_normalize_stat(data.get("stat")),
        scope=scope,
        direction=direction,
        top_n=top_n,
        team=_normalize_team(data.get("team"), year),
        team2=_normalize_team(data.get("team2"), year),
        week=int(data["week"]) if data.get("week") is not None else None,
        start_week=int(data["start_week"]) if data.get("start_week") is not None else None,
        end_week=int(data["end_week"]) if data.get("end_week") is not None else None,
        standings_format=_normalize_standings_format(data.get("standings_format")),
        place=place,
        seed=int(data["seed"]) if data.get("seed") is not None else None,
        seed_mode=str(data.get("seed_mode", "exact")),
        k=int(data["k"]) if data.get("k") is not None else None,
        year_range=_normalize_year_range(data.get("year_range")),
        timing=data.get("timing"),
        method=data.get("method"),
        mode=data.get("mode"),
        n=int(data["n"]) if data.get("n") is not None else None,
        metric=data.get("metric"),
        target_metric=data.get("target_metric"),
        candidate_metrics=data.get("candidate_metrics"),
        metric_x=data.get("metric_x"),
        metric_y=data.get("metric_y"),
    )


def _spec_from_routed(routed) -> QuerySpec:
    routed_year = int(routed.params.get("year", currentYear))
    routed_place = routed.params.get("place")
    if routed_place == "last":
        routed_place = len(seasonInfo.get(routed_year, (allMembers,))[0])
    return QuerySpec(
        intent=routed.intent,
        year=routed_year,
        stat=routed.params.get("stat"),
        scope=_normalize_scope(routed.params.get("scope")),
        direction=routed.params.get("direction", "max"),
        top_n=int(routed.params.get("top_n", 1)),
        team=_normalize_team(routed.params.get("team"), routed_year),
        team2=_normalize_team(routed.params.get("team2"), routed_year),
        start_week=routed.params.get("start_week"),
        end_week=routed.params.get("end_week"),
        standings_format=_normalize_standings_format(routed.params.get("standings_format")),
        place=routed_place,
        seed=routed.params.get("seed"),
        seed_mode=routed.params.get("seed_mode", "exact"),
        k=routed.params.get("k"),
        year_range=routed.params.get("year_range"),
        timing=routed.params.get("timing"),
        method=routed.params.get("method"),
        mode=routed.params.get("mode"),
        n=routed.params.get("n"),
        metric=routed.params.get("metric"),
        target_metric=routed.params.get("target_metric"),
        candidate_metrics=routed.params.get("candidate_metrics"),
        metric_x=routed.params.get("metric_x"),
        metric_y=routed.params.get("metric_y"),
    )


def _prefer_routed_over_llm(question: str, llm_spec: QuerySpec, routed_spec: QuerySpec) -> bool:
    q = question.lower()
    record_terms = ["record", "wins", "won", "beaten", "beat ", "against", "vs ", "versus "]
    if any(t in q for t in record_terms):
        if routed_spec.intent in {"record_vs_team", "head_to_head", "standings"} and llm_spec.intent in {"leader", "leader_vs_team"}:
            return True
    if any(t in q for t in ["last season", "this season", "current season", "years ago", "seasons ago"]):
        if routed_spec.year != llm_spec.year:
            return True
    return False


def parse_query(question: str, use_llm: bool = True) -> QuerySpec:
    prefer_llm = os.getenv("DISCORD_PREFER_LLM_PARSE", "1").strip().lower() in {"1", "true", "yes", "on"}
    routed = route_question(question)
    llm_threshold = _get_llm_parse_confidence_threshold()
    if use_llm and prefer_llm:
        plan = _llm_plan(question)
        if isinstance(plan, dict):
            parsed = _spec_from_llm_plan(plan)
            conf = 0.0
            try:
                conf = float(plan.get("confidence", 0.0))
            except Exception:
                conf = 0.0
            if parsed.intent != "unknown" and conf >= llm_threshold:
                if routed:
                    routed_spec = _spec_from_routed(routed)
                    if _prefer_routed_over_llm(question, parsed, routed_spec):
                        return routed_spec
                return parsed

    if routed:
        return _spec_from_routed(routed)

    if use_llm:
        plan = _llm_plan(question)
        if isinstance(plan, dict):
            parsed = _spec_from_llm_plan(plan)
            if parsed and parsed.intent != "unknown":
                return parsed
    return _fallback_parse(question)
