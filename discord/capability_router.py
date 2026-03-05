from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from constants import allMembers, currentYear


@dataclass
class CapabilityMatch:
    intent: str
    params: dict[str, Any] = field(default_factory=dict)


def _extract_year(question: str) -> int:
    m = re.search(r"\b(20\d{2})\b", question)
    return int(m.group(1)) if m else currentYear


def _extract_stat(question: str) -> str | None:
    q = question.lower()
    mapping = {
        "PTS": ["pts", "point", "points", "scoring"],
        "REB": ["reb", "rebound", "rebounds", "boards"],
        "AST": ["ast", "assist", "assists"],
        "STL": ["stl", "steal", "steals"],
        "BLK": ["blk", "block", "blocks"],
        "TO": ["turnover", "turnovers"],
        "3PTM": ["3pt", "3ptm", "threes", "three pointers", "3 pointers", "3s"],
        "FG%": ["fg%", "field goal percentage", "field goal"],
        "FT%": ["ft%", "free throw percentage", "free throw"],
    }
    for stat, aliases in mapping.items():
        if any(alias in q for alias in aliases):
            return stat
    return None


def _extract_scope(question: str) -> str:
    q = question.lower()
    if "regular season" in q or "reg season" in q or re.search(r"\brs\b", q):
        return "RS"
    if "playoff" in q or "postseason" in q or re.search(r"\bpo\b", q):
        return "PO"
    return "ALL"


def _extract_weeks(question: str) -> tuple[int | None, int | None]:
    q = question.lower()
    m = re.search(r"weeks?\s*(\d{1,2})\s*(?:to|-|through)\s*(\d{1,2})", q)
    if m:
        return int(m.group(1)), int(m.group(2))
    m2 = re.search(r"week\s*(\d{1,2})", q)
    if m2:
        w = int(m2.group(1))
        return w, w
    return None, None


def _extract_top_n(question: str) -> int:
    q = question.lower()
    m = re.search(r"\btop\s*(\d+)\b", q)
    if m:
        return max(1, min(30, int(m.group(1))))
    m = re.search(r"\bbest\s*(\d+)\b", q)
    if m:
        return max(1, min(30, int(m.group(1))))
    m = re.search(r"\bworst\s*(\d+)\b", q)
    if m:
        return max(1, min(30, int(m.group(1))))
    return 1


def _extract_teams(question: str) -> tuple[str | None, str | None]:
    q = question.lower()
    found = []
    for team in allMembers:
        t = str(team).lower()
        idx = q.find(t)
        if idx != -1:
            found.append((idx, team))
    found.sort(key=lambda x: x[0])
    unique = []
    for _, team in found:
        if team not in unique:
            unique.append(team)
    t1 = unique[0] if len(unique) >= 1 else None
    t2 = unique[1] if len(unique) >= 2 else None
    return t1, t2


def route_question(question: str) -> CapabilityMatch | None:
    q = question.lower().strip()
    year = _extract_year(question)
    scope = _extract_scope(question)
    start_week, end_week = _extract_weeks(question)
    top_n = _extract_top_n(question)
    team1, team2 = _extract_teams(question)

    if ("dead last" in q) or ("last place" in q):
        return CapabilityMatch(intent="standings", params={"year": year, "place": "last", "standings_format": "auto"})

    if (
        "champions lounge" in q
        or "champion's lounge" in q
        or "won a championship" in q
        or "won championship" in q
        or "won a chip" in q
        or ("all-time champions" in q)
    ):
        return CapabilityMatch(intent="champions_lounge", params={"year_range": "ALL"})

    if ("most likely" in q or "likely" in q or "odds" in q) and (
        "chip" in q or "champ" in q or "title" in q or "win it all" in q
    ):
        return CapabilityMatch(intent="predict_champion", params={"year": year, "scope": "RS", "top_n": 10})

    if "generate regular season recap" in q or "regular season recap" in q and "generate" in q:
        return CapabilityMatch(intent="recap_regular_season", params={"year": year})

    if "correlat" in q:
        if "which metric is most correlated" in q:
            return CapabilityMatch(
                intent="correlation_scan",
                params={
                    "year": year,
                    "target_metric": "playoff_success",
                    "candidate_metrics": "catalog",
                    "year_range": "ALL",
                },
            )
        metric_x = "record_vs_seed_1" if ("#1" in q or "top seed" in q or "seed" in q) else "avg_rating" if "avg rating" in q else None
        metric_y = (
            "overall_matchup_win_pct" if ("overall record" in q or "win percentage" in q or "win%" in q)
            else "standings_position" if ("playoff finish" in q or "finish" in q)
            else None
        )
        return CapabilityMatch(
            intent="correlation",
            params={
                "year": year,
                "metric_x": metric_x,
                "metric_y": metric_y,
                "year_range": "ALL",
                "method": "pearson",
            },
        )

    if ("#1 seed" in q or "#1 seeded" in q or "top seed" in q) and ("record" in q or "best" in q or "worst" in q):
        return CapabilityMatch(
            intent="record_vs_seed",
            params={
                "year": year,
                "seed": 1,
                "seed_mode": "exact",
                "year_range": "ALL",
                "timing": "entering_week",
            },
        )

    if ("top 3 seed" in q or "top 2 seed" in q or "top seeds" in q) and ("record" in q or "best" in q or "beat" in q):
        k = 3 if "top 3" in q else 2 if "top 2" in q else 3
        return CapabilityMatch(
            intent="record_vs_seed",
            params={
                "year": year,
                "seed": k,
                "seed_mode": "top_k",
                "k": k,
                "year_range": "ALL",
                "timing": "entering_week",
            },
        )

    if ("opponents" in q and ("overperform" in q or "underperform" in q or "suppress" in q)) or "avg opp delta" in q:
        return CapabilityMatch(intent="opponent_uplift", params={"year": year, "year_range": "ALL", "scope": "RS"})

    if "toughest schedule" in q or "easiest schedule" in q or "average opponent rating" in q:
        return CapabilityMatch(intent="strength_of_schedule", params={"year": year, "scope": "RS"})

    if "best average rating" in q or "mvp" in q:
        resolved_scope = scope if scope != "ALL" else "RS"
        return CapabilityMatch(
            intent="mvp_by_avg_rating",
            params={
                "year": year,
                "scope": resolved_scope,
                "start_week": start_week,
                "end_week": end_week,
                "metric": "avg_rating",
                "year_range": "ALL",
            },
        )

    if ("year-over-year" in q or "year over year" in q) and ("avg rating" in q or "rating" in q):
        return CapabilityMatch(intent="trend_split", params={"year": year, "metric": "avg_rating", "year_range": "ALL"})

    if "most consistent" in q or "consisten" in q:
        return CapabilityMatch(intent="consistency", params={"year": year, "year_range": "ALL"})

    if "what if" in q and "swapped schedules" in q:
        return CapabilityMatch(
            intent="what_if_schedule_swap",
            params={"year": year, "team": team1, "team2": team2, "standings_format": "wl"},
        )

    if "draft pick" in q and ("best" in q or "worst" in q):
        return CapabilityMatch(
            intent="draft_pick_value",
            params={
                "year": year,
                "mode": "bottom" if "worst" in q else "top",
                "n": top_n,
            },
        )

    if "draft score" in q and ("manager" in q or "teams" in q or "rank teams" in q or "all-time" in q or "all time" in q):
        return CapabilityMatch(
            intent="draft_team_score",
            params={"year": year, "year_range": "ALL" if ("all-time" in q or "all time" in q) else "single_year"},
        )

    if ("standings" in q or "place" in q) and ("if we used" in q or "alternate" in q):
        return CapabilityMatch(intent="standings_alternate", params={"year": year})

    if "standings" in q:
        fmt = "cats" if "category" in q or "cats" in q else "wl" if "matchup" in q or "w/l" in q else "auto"
        return CapabilityMatch(intent="standings", params={"year": year, "standings_format": fmt})

    if ("first place" in q or "second place" in q or "third place" in q or "ranked" in q) and "who" in q:
        place_map = {"first": 1, "second": 2, "third": 3}
        place = None
        for key, val in place_map.items():
            if f"{key} place" in q:
                place = val
                break
        return CapabilityMatch(intent="standings", params={"year": year, "place": place, "standings_format": "auto"})

    if "summarize" in q or "summary" in q or "profile" in q:
        return CapabilityMatch(intent="team_summary", params={"year": year, "scope": scope, "team": team1})

    stat = _extract_stat(question)
    if stat and team1 and ("against " in q or "vs " in q or "versus " in q):
        direction = "min" if any(tok in q for tok in ["least", "fewest", "worst", "lowest"]) else "max"
        if stat == "TO" and direction == "max" and any(tok in q for tok in ["fewest", "least", "best"]):
            direction = "min"
        return CapabilityMatch(
            intent="leader_vs_team",
            params={
                "year": year,
                "stat": stat,
                "team": team1,  # target opponent/team filter
                "direction": direction,
                "scope": scope,
                "top_n": max(1, min(30, top_n)),
                "start_week": start_week,
                "end_week": end_week,
                "year_range": "ALL" if "all-time" in q or "all time" in q else None,
            },
        )

    if stat and ("leader" in q or "most" in q or "least" in q or "best" in q or "worst" in q or "top " in q or "selling in" in q):
        direction = "min" if any(tok in q for tok in ["least", "fewest", "worst", "lowest"]) else "max"
        if "selling in" in q:
            direction = "min"
        if stat == "TO" and any(tok in q for tok in ["worst", "most", "cumulative"]):
            direction = "max"
        top_n_match = re.search(r"\btop\s*(\d+)\b", q)
        top_n_local = int(top_n_match.group(1)) if top_n_match else top_n
        return CapabilityMatch(
            intent="leader",
            params={
                "year": year,
                "stat": stat,
                "direction": direction,
                "top_n": max(1, min(30, top_n_local)),
                "scope": scope,
                "start_week": start_week,
                "end_week": end_week,
                "year_range": "ALL" if "all-time" in q or "all time" in q else None,
            },
        )

    return None
