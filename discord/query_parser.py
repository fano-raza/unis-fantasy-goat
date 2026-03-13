import os
import re
from dataclasses import dataclass
from typing import Optional

from constants import allMembers, currentYear, seasonInfo
from .capability_router import route_question
from .capability_registry import VALID_INTENTS, lexical_retrieve
from .llm_planner import plan_query_with_llm

STAT_SYNONYMS = {
    "PTS": ["pts", "pt", "point", "points", "score", "scores", "scored", "scoring"],
    "REB": ["reb", "rebs", "rebound", "rebounds", "board", "boards"],
    "AST": ["ast", "asts", "assist", "assists"],
    "STL": ["stl", "stls", "steal", "steals"],
    "BLK": ["blk", "blks", "block", "blocks"],
    "TO": ["tos", "turnover", "turnovers"],
    "3PTM": ["3pt", "3ptm", "three pointers", "threes", "3 pointers", "3s"],
    "FG%": ["fg", "fg%", "field goal", "field goal percentage"],
    "FT%": ["ft", "ft%", "free throw", "free throw percentage"],
}

VALID_STATS = list(STAT_SYNONYMS.keys())
VALID_SCOPES = ["ALL", "RS", "PO"]


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
    parse_confidence: float = 1.0
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    suggestions: tuple[str, ...] = ()
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


def _has_explicit_timeframe(question: str) -> bool:
    q = question.lower()
    if re.search(r"\b20\d{2}\b", q):
        return True
    if any(
        k in q
        for k in [
            "this season",
            "current season",
            "last season",
            "all time",
            "all-time",
            "career",
            "regular season",
            "playoff",
            "postseason",
            "week ",
            "weeks ",
        ]
    ):
        return True
    if re.search(r"\b\d+\s+(season|seasons|year|years)\s+ago\b", q):
        return True
    return False


def _build_suggestions(question: str, routed_intent: str | None = None) -> tuple[str, ...]:
    q = question.strip().rstrip("?")
    suggestions: list[str] = []
    q_low = q.lower()

    if any(k in q_low for k in ["best week", "having the best week", "best in week", "best for week"]):
        suggestions.extend(
            [
                "who has the best record in week 20",
                "who had the most PTS in week 20",
                "who has the best week in weeks 18 to 20",
            ]
        )

    if q and not _has_explicit_timeframe(q):
        suggestions.append(f"{q} this season")
        suggestions.append(f"{q} all-time")

    for cap in lexical_retrieve(question, top_k=4):
        examples = cap.examples if isinstance(cap.examples, tuple) else (cap.examples,)
        for ex in examples:
            if ex and ex not in suggestions:
                suggestions.append(ex)
        if len(suggestions) >= 4:
            break

    if routed_intent == "week_leader" and not re.search(r"\b(pts|reb|ast|stl|blk|to|3ptm|fg%|ft%)\b", question.lower()):
        suggestions.append("who had the most PTS in week 7")
        suggestions.append("who had the best record in week 7")

    deduped = []
    for s in suggestions:
        if s not in deduped:
            deduped.append(s)
    return tuple(deduped[:4])


def _default_clarification_question(question: str) -> str:
    q_low = question.lower()
    if any(k in q_low for k in ["best week", "having the best week", "best in week", "best for week"]) and not re.search(
        r"\bweek\s*\d{1,2}\b", q_low
    ):
        return "Specify a week (e.g., 'week 5') or range (e.g., 'weeks 3 to 8')."
    if not _has_explicit_timeframe(question):
        return "Do you want current season, all-time, or a specific year?"
    if "week" in question.lower() and not re.search(r"\b(pts|reb|ast|stl|blk|to|3ptm|fg%|ft%)\b", question.lower()):
        return "Do you mean best record that week, or best stat leader that week?"
    return "Can you clarify the stat or comparison you want?"


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
    elif (week or start_week) and stat is None and any(
        k in q_low for k in ["best week", "having the best week", "best in week", "best for week"]
    ):
        intent = "standings"
        standings_format = "wl"
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


def _llm_plan(question: str, routed_spec: QuerySpec | None = None) -> Optional[dict]:
    routed_hint = None
    if routed_spec is not None:
        routed_hint = {
            "intent": routed_spec.intent,
            "year": routed_spec.year,
            "scope": routed_spec.scope,
            "stat": routed_spec.stat,
            "team": routed_spec.team,
            "team2": routed_spec.team2,
            "week": routed_spec.week,
            "start_week": routed_spec.start_week,
            "end_week": routed_spec.end_week,
        }
    return plan_query_with_llm(question, routed_hint=routed_hint, max_retries=1)


def _get_llm_parse_confidence_threshold() -> float:
    raw = os.getenv("DISCORD_LLM_PARSE_CONFIDENCE", "0.35").strip()
    try:
        v = float(raw)
    except Exception:
        return 0.35
    return max(0.0, min(1.0, v))


def _allow_llm_override_routed() -> bool:
    raw = os.getenv("DISCORD_LLM_OVERRIDE_ROUTED", "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


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
        week=routed.params.get("week"),
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

    # Safer default: deterministic routed intent first.
    if routed:
        routed_spec = _spec_from_routed(routed)
        if not (use_llm and prefer_llm and _allow_llm_override_routed()):
            return routed_spec

        # Optional override mode: allow high-confidence LLM plan to replace routed parse.
        plan = _llm_plan(question, routed_spec=routed_spec)
        if isinstance(plan, dict):
            parsed = _spec_from_llm_plan(plan)
            conf = 0.0
            try:
                conf = float(plan.get("confidence", 0.0))
            except Exception:
                conf = 0.0
            parsed.parse_confidence = conf
            if parsed.intent != "unknown" and conf >= llm_threshold:
                if _prefer_routed_over_llm(question, parsed, routed_spec):
                    return routed_spec
                return parsed
        return routed_spec

    if use_llm:
        plan = _llm_plan(question, routed_spec=None)
        if isinstance(plan, dict):
            parsed = _spec_from_llm_plan(plan)
            conf = 0.0
            try:
                conf = float(plan.get("confidence", 0.0))
            except Exception:
                conf = 0.0
            parsed.parse_confidence = conf
            if plan.get("needs_clarification") is True or parsed.intent == "unknown" or conf < llm_threshold:
                parsed.intent = "unknown"
                parsed.needs_clarification = True
                parsed.clarification_question = (
                    str(plan.get("clarification_question")).strip()
                    if isinstance(plan.get("clarification_question"), str)
                    else _default_clarification_question(question)
                )
                parsed.suggestions = _build_suggestions(question)
                return parsed
            if parsed and parsed.intent != "unknown" and conf >= llm_threshold:
                return parsed
    parsed = _fallback_parse(question)
    if parsed.intent == "unknown":
        parsed.needs_clarification = True
        parsed.clarification_question = _default_clarification_question(question)
        parsed.suggestions = _build_suggestions(question)
    return parsed
