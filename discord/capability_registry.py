from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CapabilityDef:
    intent: str
    description: str
    required_args: tuple[str, ...] = ()
    optional_args: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()


CAPABILITIES: tuple[CapabilityDef, ...] = (
    CapabilityDef(
        intent="leader",
        description="Top/bottom teams for one stat in a season/scope/week window.",
        required_args=("stat",),
        optional_args=("year", "scope", "direction", "top_n", "week", "start_week", "end_week"),
        aliases=("best in", "most", "least", "leaders", "top"),
        examples=("who has the most points", "best FT% in 2025"),
    ),
    CapabilityDef(
        intent="leader_vs_team",
        description="Top/bottom teams in one stat specifically against a target team.",
        required_args=("stat", "team"),
        optional_args=("year", "scope", "direction", "top_n", "week", "start_week", "end_week", "year_range"),
        aliases=("against", "vs", "versus"),
        examples=("who scores most against Juan"),
    ),
    CapabilityDef(
        intent="standings",
        description="Category or W/L standings, optionally by place/rank/team and week range.",
        optional_args=("year", "standings_format", "place", "team", "start_week", "end_week"),
        aliases=("standings", "record", "first place", "best team"),
        examples=("who is first place", "week 3 best record"),
    ),
    CapabilityDef(
        intent="best_team_snapshot",
        description="Best team right now snapshot across standings and current metrics.",
        optional_args=("year", "scope"),
        aliases=("best team right now", "top team rn", "who's the best team"),
    ),
    CapabilityDef(
        intent="standings_alternate",
        description="Compare category standings and matchup W/L standings.",
        optional_args=("year",),
        aliases=("alternate standings", "if we used matchup standings"),
    ),
    CapabilityDef(
        intent="predict_champion",
        description="Champion prediction style ranking from regular-season indicators.",
        optional_args=("year", "scope", "top_n"),
        aliases=("champ odds", "likely champion", "playoff odds"),
    ),
    CapabilityDef(
        intent="champions_lounge",
        description="Historical championships by team, including years/titles/chips.",
        optional_args=("team", "year_range"),
        aliases=("chips", "titles", "championships", "rings"),
    ),
    CapabilityDef(
        intent="mvp_by_avg_rating",
        description="Rank teams by average week rating for season/scope.",
        optional_args=("year", "scope", "start_week", "end_week", "metric", "year_range"),
        aliases=("mvp", "best average rating"),
    ),
    CapabilityDef(
        intent="category_sweep",
        description="Show leaders/laggards across all tracked categories.",
        optional_args=("year", "scope", "mode"),
        aliases=("category leaders", "category losers", "every category"),
    ),
    CapabilityDef(
        intent="strength_of_schedule",
        description="Schedule difficulty by opponent quality metrics.",
        optional_args=("year", "scope"),
        aliases=("toughest schedule", "easiest schedule", "avg opponent rating"),
    ),
    CapabilityDef(
        intent="draft_pick_value",
        description="Best/worst single draft picks in one season.",
        optional_args=("year", "mode", "n"),
        aliases=("draft pick value", "best draft picks"),
    ),
    CapabilityDef(
        intent="draft_player_score",
        description="Best/worst NBA players by aggregate draft value across seasons.",
        optional_args=("year", "year_range", "mode", "n", "method"),
        aliases=("best drafted players", "all-time draft players", "draft score player"),
    ),
    CapabilityDef(
        intent="draft_team_score",
        description="Best/worst managers by aggregate draft value.",
        optional_args=("year", "year_range", "method"),
        aliases=("best drafting team", "draft team score"),
    ),
    CapabilityDef(
        intent="team_compare",
        description="Compare two teams on one stat or broad summary.",
        required_args=("team", "team2"),
        optional_args=("year", "scope", "stat"),
        aliases=("vs", "versus", "better in", "compare"),
    ),
    CapabilityDef(
        intent="head_to_head",
        description="Head-to-head matchup result between two teams (current/week/all year).",
        required_args=("team", "team2"),
        optional_args=("year", "scope", "week", "start_week", "end_week"),
        aliases=("head to head", "current matchup", "who would win"),
    ),
    CapabilityDef(
        intent="record_vs_team",
        description="Best/worst record or wins against a target team.",
        required_args=("team",),
        optional_args=("year", "scope", "year_range", "metric", "direction", "start_week", "end_week"),
        aliases=("record against", "wins against", "lost to the most", "beaten"),
    ),
    CapabilityDef(
        intent="matchup_tie_leaders",
        description="Teams with most/fewest tied matchups.",
        optional_args=("year", "scope", "year_range", "mode", "n"),
        aliases=("most ties", "fewest ties", "tie matchups"),
    ),
    CapabilityDef(
        intent="matchup_tie_history",
        description="Tie history for one team, including first/last/no-tie season checks.",
        required_args=("team",),
        optional_args=("year", "scope", "year_range", "mode"),
        aliases=("first time tied", "last time tied", "what years tied"),
    ),
    CapabilityDef(
        intent="team_summary",
        description="One team season profile (strengths, weaknesses, totals).",
        optional_args=("year", "scope", "team"),
        aliases=("summary", "profile", "how did team do"),
    ),
    CapabilityDef(
        intent="team_rating_by_season",
        description="Best/worst season for a team across years.",
        required_args=("team",),
        optional_args=("year", "scope", "year_range", "mode"),
        aliases=("best season", "worst season"),
    ),
    CapabilityDef(
        intent="week_leader",
        description="Stat leaders for a specific week or week range.",
        required_args=("stat",),
        optional_args=("year", "scope", "week", "start_week", "end_week", "top_n", "direction"),
        aliases=("week", "weekly leader"),
    ),
    CapabilityDef(
        intent="schedule_toughest_stretch",
        description="Toughest/easiest N-week stretch for a team.",
        required_args=("team",),
        optional_args=("year", "scope", "n"),
        aliases=("toughest stretch", "easiest stretch"),
    ),
    CapabilityDef(
        intent="half_split_improvement",
        description="First-half vs second-half improvement.",
        optional_args=("year", "scope"),
        aliases=("first half", "second half", "improved"),
    ),
    CapabilityDef(
        intent="weekly_top_performer_count",
        description="Count how often teams were #1 in weekly rating.",
        optional_args=("year", "scope", "year_range"),
        aliases=("#1 weeks", "top performer count"),
    ),
    CapabilityDef(
        intent="record_vs_seed",
        description="Record versus top-k or exact seed.",
        optional_args=("year", "seed", "seed_mode", "k", "year_range", "timing", "direction"),
        aliases=("record vs seed", "vs top seed", "vs #1"),
    ),
    CapabilityDef(
        intent="opponent_uplift",
        description="Who faced strongest opponents by week rating context.",
        optional_args=("year", "scope", "year_range"),
        aliases=("strongest opponents", "unluckiest schedule"),
    ),
    CapabilityDef(
        intent="correlation",
        description="Correlation between two explicit metrics.",
        optional_args=("year", "metric_x", "metric_y", "year_range", "method"),
        aliases=("correlation", "correlate"),
    ),
    CapabilityDef(
        intent="correlation_scan",
        description="Find strongest correlation to a target metric across candidates.",
        optional_args=("year", "target_metric", "candidate_metrics", "year_range"),
        aliases=("most correlated", "correlation scan"),
    ),
    CapabilityDef(
        intent="trend_split",
        description="Trend analysis and split comparison over time windows.",
        optional_args=("year", "metric", "timing", "year_range"),
        aliases=("trend", "year-over-year"),
    ),
    CapabilityDef(
        intent="consistency",
        description="Most/least consistent teams over time.",
        optional_args=("year", "year_range", "mode"),
        aliases=("consistent", "volatile"),
    ),
    CapabilityDef(
        intent="what_if_schedule_swap",
        description="What-if scenario swapping two teams' schedules.",
        required_args=("team", "team2"),
        optional_args=("year", "standings_format"),
        aliases=("what if swapped schedules"),
    ),
    CapabilityDef(
        intent="recap_regular_season",
        description="Generate regular-season recap output for one year.",
        optional_args=("year",),
        aliases=("regular season recap"),
    ),
    CapabilityDef(
        intent="vs_weekly_top_team",
        description="Who faced weekly #1 team most often.",
        optional_args=("year", "scope", "year_range"),
        aliases=("played against weekly #1", "best ranked team of week"),
    ),
    CapabilityDef(
        intent="all_time_stats_table",
        description="All-time tables for career/RS/PO totals and averages.",
        optional_args=("scope", "method", "stat", "team", "direction", "top_n"),
        aliases=("career totals", "career averages", "rs totals", "po averages"),
    ),
    CapabilityDef(
        intent="all_time_summary",
        description="All-time summary table metrics by team.",
        optional_args=("team", "top_n"),
        aliases=("all time summary", "summary sheet"),
    ),
)

VALID_INTENTS: set[str] = {cap.intent for cap in CAPABILITIES} | {"unknown"}


_GUIDE_CACHE: dict[str, Any] | None = None


def _load_capability_guide() -> dict[str, Any]:
    global _GUIDE_CACHE
    if _GUIDE_CACHE is not None:
        return _GUIDE_CACHE

    guide_path = Path(__file__).resolve().parent / "capability_guide.json"
    if not guide_path.exists():
        _GUIDE_CACHE = {}
        return _GUIDE_CACHE

    try:
        raw = json.loads(guide_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            _GUIDE_CACHE = raw
        else:
            _GUIDE_CACHE = {}
    except Exception:
        _GUIDE_CACHE = {}
    return _GUIDE_CACHE


def _guide_for_intent(intent: str) -> dict[str, Any]:
    guide = _load_capability_guide()
    entries = guide.get("intents", {}) if isinstance(guide, dict) else {}
    row = entries.get(intent, {}) if isinstance(entries, dict) else {}
    return row if isinstance(row, dict) else {}


def out_of_domain_response_for(question: str) -> str | None:
    guide = _load_capability_guide()
    ood = guide.get("out_of_domain", {}) if isinstance(guide, dict) else {}
    if not isinstance(ood, dict):
        return None
    phrases = ood.get("phrases", [])
    if not isinstance(phrases, list):
        return None
    q = (question or "").lower()
    if any(isinstance(p, str) and p.lower() in q for p in phrases):
        resp = ood.get("response")
        return str(resp) if isinstance(resp, str) and resp.strip() else None
    return None


def capability_catalog_lines() -> list[str]:
    return [f"- {cap.intent}: {cap.description}" for cap in CAPABILITIES]


def capability_by_intent(intent: str) -> CapabilityDef | None:
    for cap in CAPABILITIES:
        if cap.intent == intent:
            return cap
    return None


def lexical_retrieve(question: str, top_k: int = 8) -> list[CapabilityDef]:
    """
    Lightweight retrieval over capability descriptions/aliases.
    Avoids sending full catalog every request.
    """
    q = (question or "").lower()
    if not q:
        return list(CAPABILITIES[:top_k])

    scored: list[tuple[int, CapabilityDef]] = []
    for cap in CAPABILITIES:
        score = 0
        guide_row = _guide_for_intent(cap.intent)
        guide_phrases = []
        for key in ("phrases", "aliases", "patterns", "examples", "negative_patterns"):
            vals = guide_row.get(key, [])
            if isinstance(vals, list):
                guide_phrases.extend(str(v) for v in vals if isinstance(v, str))
        haystack: list[str] = [cap.intent, cap.description, *cap.aliases, *cap.examples, *guide_phrases]
        for phrase in haystack:
            p = phrase.lower()
            if p and p in q:
                score += 6
        # token overlap fallback
        q_tokens = set(tok for tok in q.replace("?", " ").replace(",", " ").split() if len(tok) >= 3)
        cap_tokens = set()
        for item in haystack:
            cap_tokens |= set(tok for tok in item.lower().replace("/", " ").replace("-", " ").split() if len(tok) >= 3)
        score += len(q_tokens & cap_tokens)
        if score > 0:
            scored.append((score, cap))

    if not scored:
        return list(CAPABILITIES[:top_k])

    scored.sort(key=lambda x: (-x[0], x[1].intent))
    return [cap for _, cap in scored[: max(1, top_k)]]


def capability_json_schema_fragment(caps: list[CapabilityDef]) -> dict[str, Any]:
    return {
        "allowed_intents": [cap.intent for cap in caps],
        "capabilities": [
            {
                "intent": cap.intent,
                "description": cap.description,
                "required_args": list(cap.required_args),
                "optional_args": list(cap.optional_args),
                "guide_phrases": list(_guide_for_intent(cap.intent).get("phrases", []))[:10],
                "guide_examples": list(_guide_for_intent(cap.intent).get("examples", []))[:10],
                "guide_negative_patterns": list(_guide_for_intent(cap.intent).get("negative_patterns", []))[:5],
            }
            for cap in caps
        ],
    }
