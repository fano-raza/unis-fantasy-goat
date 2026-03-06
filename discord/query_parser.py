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
    for canonical, aliases in STAT_SYNONYMS.items():
        canon = canonical.lower()
        canon_match = re.search(rf"\\b{re.escape(canon)}\\b", q_low) if len(canon) <= 3 else canon in q_low
        alias_match = any(
            re.search(rf"\\b{re.escape(alias)}\\b", q_low) if len(alias) <= 3 else alias in q_low
            for alias in aliases
        )
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
    elif team and team2 and any(k in q_low for k in ["vs", "versus", "compare", "between"]):
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


def _llm_parse(question: str) -> Optional[QuerySpec]:
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

    prompt = (
        "Extract the user query into JSON with keys: "
        "intent, year, stat, scope, direction, top_n, team, team2, week, start_week, end_week, standings_format, place. "
        f"intent one of {sorted(VALID_INTENTS)}. "
        f"stat one of {VALID_STATS} or null. "
        "scope one of ALL, RS, PO. direction one of max/min. "
        "top_n integer 1-10. standings_format one of auto/wl/cats. place is integer standing place or null. "
        "If not explicit, set intent='unknown'. Return ONLY JSON."
    )

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

        data = json.loads(text)
        year = int(data.get("year", currentYear))

        return QuerySpec(
            intent=_normalize_intent(data.get("intent")),
            year=year,
            stat=_normalize_stat(data.get("stat")),
            scope=_normalize_scope(data.get("scope")),
            direction="min" if str(data.get("direction", "max")).lower() == "min" else "max",
            top_n=max(1, min(10, int(data.get("top_n", 1)))),
            team=_normalize_team(data.get("team"), year),
            team2=_normalize_team(data.get("team2"), year),
            week=int(data["week"]) if data.get("week") is not None else None,
            start_week=int(data["start_week"]) if data.get("start_week") is not None else None,
            end_week=int(data["end_week"]) if data.get("end_week") is not None else None,
            standings_format=_normalize_standings_format(data.get("standings_format")),
            place=int(data["place"]) if data.get("place") is not None else None,
        )
    except Exception:
        return None


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
    if use_llm and prefer_llm:
        parsed = _llm_parse(question)
        if parsed and parsed.intent != "unknown":
            if routed:
                routed_spec = _spec_from_routed(routed)
                if _prefer_routed_over_llm(question, parsed, routed_spec):
                    return routed_spec
            return parsed

    if routed:
        return _spec_from_routed(routed)

    if use_llm:
        parsed = _llm_parse(question)
        if parsed and parsed.intent != "unknown":
            return parsed
    return _fallback_parse(question)
