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
    q = question.lower()
    m = re.search(r"\b(20\d{2})\b", q)
    if m:
        return int(m.group(1))

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


def _extract_stat(question: str) -> str | None:
    q = question.lower()
    mapping = {
        "PTS": ["pts", "pt", "point", "points", "score", "scores", "scored", "scoring"],
        "REB": ["reb", "rebs", "rebound", "rebounds", "board", "boards"],
        "AST": ["ast", "asts", "assist", "assists"],
        "STL": ["stl", "stls", "steal", "steals"],
        "BLK": ["blk", "blks", "block", "blocks"],
        "TO": ["tos", "turnover", "turnovers"],
        "3PTM": ["3pt", "3ptm", "threes", "three pointers", "3 pointers", "3s"],
        "FG%": ["fg%", "field goal percentage", "field goal"],
        "FT%": ["ft%", "free throw percentage", "free throw"],
    }
    for stat, aliases in mapping.items():
        if any(
            (
                alias in q
                if re.search(r"[^a-z0-9 ]", alias)
                else (re.search(rf"\b{re.escape(alias)}\b", q) if len(alias) <= 3 else alias in q)
            )
            for alias in aliases
        ):
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


def _normalize_casual_text(question: str) -> str:
    q = question.lower().strip()
    replacements = {
        " rn ": " right now ",
        " rn?": " right now?",
        " rn.": " right now.",
        " this yr ": " this year ",
        " this szn ": " this season ",
        " reg szn ": " regular season ",
        " h2h ": " head to head ",
        " who's ": " who is ",
        " whats ": " what is ",
        " w/ ": " with ",
    }
    q = f" {q} "
    for src, dst in replacements.items():
        q = q.replace(src, dst)
    return " ".join(q.split())


def _contains_any(q: str, terms: list[str]) -> bool:
    return any(term in q for term in terms)


def _is_all_time(q: str) -> bool:
    return _contains_any(q, ["all-time", "all time", "entire career", "career"])


def _extract_place_hint(q: str) -> int | None:
    # numeric ordinals: "2nd", "3rd", ...
    m = re.search(r"\b(\d+)(?:st|nd|rd|th)\b", q)
    if m:
        return int(m.group(1))
    # word ordinals
    word_map = {
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
    for w, p in word_map.items():
        if re.search(rf"\b{w}\b", q):
            return p
    return None


def _infer_record_vs_team_metric(q: str) -> str:
    explicit_record_terms = ["best record", "worst record", "win percentage", "win%"]
    if _contains_any(q, explicit_record_terms):
        return "win_pct"

    wins_terms = [
        "most wins",
        "won the most",
        "won most games",
        "wins against",
        "wins over",
        "most wins over",
        "lost to the most",
        "lost to most",
        "beaten by",
        "beat me the most",
    ]
    if _contains_any(q, wins_terms):
        return "wins"

    # Ambiguous phrasing like "beaten X the most" can mean either
    # most wins or best win percentage vs that target.
    if ("beat" in q or "beaten" in q) and _contains_any(q, ["most", "best", "least", "worst"]):
        return "both"

    return "win_pct"


def _infer_record_vs_team_direction(q: str, metric: str) -> str:
    if metric == "wins":
        if _contains_any(q, ["least", "fewest", "lowest", "min"]):
            return "min"
        return "max"
    # win_pct / record semantics
    if _contains_any(q, ["worst", "least", "lowest", "struggle", "can't beat", "cannot beat"]):
        return "min"
    return "max"


def _match_record_vs_team(
    q: str,
    stat: str | None,
    team1: str | None,
    scope: str,
    year: int,
    start_week: int | None,
    end_week: int | None,
) -> CapabilityMatch | None:
    if stat is not None:
        return None
    if not team1:
        return None

    # Semantic buckets: target relation + comparison intent.
    relation_terms = [
        "against",
        "vs ",
        "versus ",
        "beaten",
        "beaten by",
        "beat ",
        "lost to",
        "losses to",
        "wins over",
        "won against",
        "record against",
        "record vs",
        "record over",
        "owns",
        "dominate",
        "dominates",
        "struggle against",
        "struggles against",
        "can't beat",
        "cannot beat",
    ]
    comparison_terms = [
        "best",
        "most",
        "worst",
        "least",
        "fewest",
        "who has",
        "who's",
        "top",
        "leader",
    ]

    # Also catch plain "who beat <team> the most" style.
    beat_superlative = (
        ("beat" in q or "lost to" in q or "beaten by" in q)
        and _contains_any(q, ["most", "best", "worst", "least", "fewest"])
    )

    if not (_contains_any(q, relation_terms) and _contains_any(q, comparison_terms)) and not beat_superlative:
        return None

    metric = _infer_record_vs_team_metric(q)
    return CapabilityMatch(
        intent="record_vs_team",
        params={
            "year": year,
            "team": team1,
            "scope": scope if scope in {"RS", "PO"} else "RS",
            "year_range": "ALL" if _is_all_time(q) else None,
            "metric": metric,
            "direction": _infer_record_vs_team_direction(q, metric),
            "start_week": start_week,
            "end_week": end_week,
        },
    )


def _match_head_to_head(
    q: str,
    team1: str | None,
    team2: str | None,
    scope: str,
    year: int,
    start_week: int | None,
    end_week: int | None,
) -> CapabilityMatch | None:
    if not team1 or not team2:
        return None

    h2h_terms = [
        "head to head",
        "head-to-head",
        "h2h",
        "current matchup",
        "currently winning",
        "matchup between",
        "record between",
        "who would win",
        "who wins",
    ]
    if not _contains_any(q, h2h_terms):
        return None

    inferred_scope = scope if scope in {"RS", "PO"} else "ALL"
    params = {
        "year": year,
        "team": team1,
        "team2": team2,
        "scope": inferred_scope,
        "start_week": start_week,
        "end_week": end_week,
    }

    # "this week" phrasing should be interpreted as current regular-season matchup.
    if "this week" in q:
        params["scope"] = "RS"

    return CapabilityMatch(
        intent="head_to_head",
        params=params,
    )


def _match_leader_vs_team(
    q: str,
    stat: str | None,
    team1: str | None,
    scope: str,
    year: int,
    start_week: int | None,
    end_week: int | None,
    top_n: int,
) -> CapabilityMatch | None:
    if not stat or not team1:
        return None
    if not _contains_any(q, ["against", "vs ", "versus ", "vs."]):
        return None

    direction = "min" if _contains_any(q, ["least", "fewest", "worst", "lowest"]) else "max"
    if stat == "TO" and direction == "max" and _contains_any(q, ["fewest", "least", "best"]):
        direction = "min"

    top_n_match = re.search(r"\btop\s*(\d+)\b", q)
    if top_n_match:
        top_n_local = int(top_n_match.group(1))
    elif _contains_any(q, ["best", "most", "least", "worst"]):
        top_n_local = 10
    else:
        top_n_local = top_n

    return CapabilityMatch(
        intent="leader_vs_team",
        params={
            "year": year,
            "stat": stat,
            "team": team1,
            "direction": direction,
            "scope": scope if scope in {"RS", "PO"} else "ALL",
            "top_n": max(1, min(30, top_n_local)),
            "start_week": start_week,
            "end_week": end_week,
            "year_range": "ALL" if _is_all_time(q) else None,
        },
    )


def _match_draft_questions(q: str, year: int, top_n: int) -> CapabilityMatch | None:
    if "draft" not in q:
        return None

    mode = "bottom" if _contains_any(q, ["worst", "bottom", "bust"]) else "top"
    year_range = "ALL" if _is_all_time(q) or _contains_any(q, ["across seasons", "overall", "total"]) else None
    n = max(1, min(50, int(top_n or 10)))
    if n == 1 and _contains_any(q, ["best", "worst", "top", "bottom", "most", "least"]):
        n = 10

    # Explicit "draft pick value" phrasing.
    if _contains_any(q, ["draft pick value", "pick value", "pick score"]):
        if year_range == "ALL":
            return CapabilityMatch(
                intent="draft_player_score",
                params={"year": year, "year_range": "ALL", "mode": mode, "n": n},
            )
        return CapabilityMatch(
            intent="draft_pick_value",
            params={"year": year, "mode": mode, "n": n},
        )

    if _contains_any(q, ["draft bust", "biggest bust"]):
        return CapabilityMatch(
            intent="draft_player_score",
            params={"year": year, "year_range": year_range, "mode": "bottom", "n": 1},
        )

    # Player-focused draft value queries.
    if _contains_any(q, ["player", "nba player"]) and _contains_any(q, ["best", "worst", "top", "bottom", "value", "score"]):
        return CapabilityMatch(
            intent="draft_player_score",
            params={
                "year": year,
                "year_range": year_range,
                "mode": mode,
                "n": n,
            },
        )

    # Team/manager draft score ranking queries.
    if _contains_any(q, ["team", "teams", "manager", "managers", "rank teams", "team score", "draft score", "drafted the most value"]):
        return CapabilityMatch(
            intent="draft_team_score",
            params={"year": year, "year_range": year_range or "single_year"},
        )

    # Generic "draft pick(s)" phrasing.
    if _contains_any(q, ["draft pick", "draft picks"]):
        if year_range == "ALL":
            return CapabilityMatch(
                intent="draft_player_score",
                params={"year": year, "year_range": "ALL", "mode": mode, "n": n},
            )
        return CapabilityMatch(
            intent="draft_pick_value",
            params={"year": year, "mode": mode, "n": n},
        )

    return None


def route_question(question: str) -> CapabilityMatch | None:
    q = _normalize_casual_text(question)
    year = _extract_year(question)
    scope = _extract_scope(question)
    start_week, end_week = _extract_weeks(question)
    top_n = _extract_top_n(question)
    team1, team2 = _extract_teams(question)
    stat = _extract_stat(question)

    if _contains_any(
        q,
        [
            "career totals",
            "all time totals",
            "all-time totals",
            "rs totals",
            "regular season totals",
            "po totals",
            "playoff totals",
            "career avgs",
            "career averages",
            "all time averages",
            "all-time averages",
            "rs avgs",
            "rs averages",
            "regular season averages",
            "po avgs",
            "po averages",
            "playoff averages",
        ],
    ):
        scope_hint = "ALL"
        if _contains_any(q, ["rs totals", "rs avgs", "rs averages", "regular season totals", "regular season averages"]):
            scope_hint = "RS"
        elif _contains_any(q, ["po totals", "po avgs", "po averages", "playoff totals", "playoff averages"]):
            scope_hint = "PO"
        method = "avg" if _contains_any(q, ["avg", "average", "averages"]) else "total"
        return CapabilityMatch(
            intent="all_time_stats_table",
            params={
                "scope": scope_hint,
                "method": method,
                "stat": stat,
                "team": team1,
                "direction": "min" if _contains_any(q, ["least", "fewest", "lowest", "worst"]) else "max",
                "top_n": max(1, min(30, top_n if top_n else 10)),
            },
        )

    if _contains_any(q, ["all time summary", "all-time summary", "summary sheet"]) and _contains_any(
        q, ["all time", "all-time", "career", "summary"]
    ):
        return CapabilityMatch(intent="all_time_summary", params={"team": team1, "top_n": max(1, min(30, top_n if top_n else 10))})

    if ("dead last" in q) or ("last place" in q):
        return CapabilityMatch(intent="standings", params={"year": year, "place": "last", "standings_format": "auto"})

    if "barely made playoffs" in q or "just made playoffs" in q:
        cutoff = max(1, len(allMembers) // 2)
        return CapabilityMatch(intent="standings", params={"year": year, "place": cutoff, "standings_format": "auto"})

    if (
        ("who is currently in" in q or "who is in" in q or "which team is in" in q)
        and _extract_place_hint(q) is not None
    ):
        return CapabilityMatch(
            intent="standings",
            params={"year": year, "place": _extract_place_hint(q), "standings_format": "auto"},
        )

    if _contains_any(q, ["best team", "top team"]) and _contains_any(q, ["right now", "currently", "this season", "current season", "rn"]):
        return CapabilityMatch(intent="best_team_snapshot", params={"year": year, "scope": "RS"})

    if _contains_any(q, ["best team", "top team"]) and not _contains_any(q, ["right now", "currently", "rn"]):
        return CapabilityMatch(intent="best_team_snapshot", params={"year": year, "scope": "RS"})

    if _contains_any(q, ["worst team", "bottom team"]) and not _contains_any(q, ["right now", "currently", "rn"]):
        return CapabilityMatch(intent="standings", params={"year": year, "place": "last", "standings_format": "auto"})

    if team1 and team2 and _contains_any(
        q,
        [
            "who was better",
            "who is better",
            "better in",
            "better team",
            "stronger team",
            "better season",
            "who did better",
        ],
    ):
        return CapabilityMatch(
            intent="team_compare",
            params={"year": year, "scope": scope if scope in {"RS", "PO"} else "RS", "team": team1, "team2": team2},
        )

    if ("who is #1" in q or "who's #1" in q or "#1 rn" in q or "#1 right now" in q):
        return CapabilityMatch(intent="standings", params={"year": year, "place": 1, "standings_format": "auto"})

    if _contains_any(q, ["best regular season record", "worst regular season record"]):
        place = 1 if "best" in q else "last"
        return CapabilityMatch(intent="standings", params={"year": year, "place": place, "standings_format": "wl"})

    if (
        (start_week is not None or end_week is not None)
        and stat is None
        and _contains_any(q, ["record", "wins", "won", "winning"])
        and not _contains_any(
            q,
            [
                "against",
                "vs ",
                "versus ",
                "beaten",
                "beat ",
                "wins over",
                "won against",
                "record against",
                "record vs",
            ],
        )
    ):
        place = 1 if _contains_any(q, ["best", "most", "top", "first"]) else None
        return CapabilityMatch(
            intent="standings",
            params={
                "year": year,
                "standings_format": "wl",
                "start_week": start_week,
                "end_week": end_week,
                "place": place,
            },
        )

    # Casual phrasing like "who is having the best week" should default to
    # "best record that week" when no stat is specified.
    if (
        (start_week is not None or end_week is not None)
        and stat is None
        and _contains_any(q, ["best week", "having the best week", "best in week", "best for week"])
    ):
        return CapabilityMatch(
            intent="standings",
            params={
                "year": year,
                "standings_format": "wl",
                "start_week": start_week,
                "end_week": end_week,
                "place": 1,
            },
        )

    if (
        "champions lounge" in q
        or "champion's lounge" in q
        or "most championships" in q
        or "most chips" in q
        or "most titles" in q
        or "championship leaderboard" in q
        or "won a championship" in q
        or "won championship" in q
        or "won championships" in q
        or "won a chip" in q
        or "won chips" in q
        or "won titles" in q
        or "won a title" in q
        or "when did" in q and _contains_any(q, ["win", "won"]) and _contains_any(q, ["championship", "championships", "chip", "chips", "title", "titles"])
        or "what year did" in q and _contains_any(q, ["win", "won"]) and _contains_any(q, ["championship", "championships", "chip", "chips", "title", "titles"])
        or ("all-time champions" in q)
    ):
        return CapabilityMatch(intent="champions_lounge", params={"year_range": "ALL", "team": team1})

    if ("most likely" in q or "likely" in q or "odds" in q) and (
        "chip" in q or "champ" in q or "title" in q or "win it all" in q
    ):
        return CapabilityMatch(intent="predict_champion", params={"year": year, "scope": "RS", "top_n": 10})

    if _contains_any(q, ["playoff odds", "projected final standings", "current pace", "most likely to finish first", "most likely to win playoffs"]):
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

    if ("top-seeded" in q or "top seeded" in q or "top seed" in q) and ("worst" in q or "best" in q):
        return CapabilityMatch(
            intent="record_vs_seed",
            params={
                "year": year,
                "seed": 3,
                "seed_mode": "top_k",
                "k": 3,
                "year_range": "ALL",
                "timing": "entering_week",
                "direction": "min" if "worst" in q else "max",
            },
        )

    if ("opponents" in q and ("overperform" in q or "underperform" in q or "suppress" in q)) or "avg opp delta" in q:
        return CapabilityMatch(intent="opponent_uplift", params={"year": year, "year_range": "ALL", "scope": "RS"})

    if _contains_any(q, ["#1 weekly ratings", "number 1 weekly ratings", "most #1 weeks", "most #1 weekly"]):
        return CapabilityMatch(
            intent="weekly_top_performer_count",
            params={"year": year, "year_range": "ALL" if _is_all_time(q) else None, "scope": "RS"},
        )

    if team1 and _contains_any(q, ["tie", "tied", "draw", "drew"]) and _contains_any(
        q,
        [
            "first time",
            "last time",
            "first season",
            "last season",
            "what years",
            "which years",
            "what seasons",
            "which seasons",
            "didn't tie",
            "did not tie",
            "no ties",
            "without ties",
        ],
    ):
        mode = "years_with_ties"
        no_tie_terms = ["didn't tie", "did not tie", "no ties", "without ties"]
        is_no_tie_query = _contains_any(q, no_tie_terms)
        if _contains_any(q, ["what years", "which years", "what seasons", "which seasons"]):
            mode = "years_without_ties" if is_no_tie_query else "years_with_ties"
        elif "is this the first season" in q:
            mode = "first_zero_check" if is_no_tie_query else "first_tie_check"
        elif "first" in q and ("this season" in q or "current season" in q):
            mode = "first_zero_check" if is_no_tie_query else "first_tie_check"
        elif "first" in q:
            mode = "first_zero_season" if is_no_tie_query else "first_tie_season"
        elif "last" in q:
            mode = "last_zero_season" if is_no_tie_query else "last_tie_season"

        return CapabilityMatch(
            intent="matchup_tie_history",
            params={
                "year": year,
                "team": team1,
                "scope": scope if scope in {"RS", "PO"} else "RS",
                "year_range": "ALL",
                "mode": mode,
            },
        )

    if _contains_any(q, ["tie", "tied", "draw", "drew"]) and (
        _contains_any(q, ["matchup", "matchups", "games", "game", "record"])
        or _contains_any(q, ["most", "least", "fewest", "best", "worst", "top", "bottom"])
    ):
        mode = "top"
        if _contains_any(q, ["least", "fewest", "lowest", "min", "worst"]):
            mode = "bottom"
        n = max(1, min(30, top_n if top_n > 1 else (10 if _contains_any(q, ["most", "best", "least", "fewest", "worst", "top", "bottom"]) else 1)))
        return CapabilityMatch(
            intent="matchup_tie_leaders",
            params={
                "year": year,
                "year_range": "ALL" if _is_all_time(q) else None,
                "scope": scope if scope in {"RS", "PO"} else "RS",
                "mode": mode,
                "n": n,
            },
        )

    record_vs_team_match = _match_record_vs_team(q, stat, team1, scope, year, start_week, end_week)
    if record_vs_team_match:
        return record_vs_team_match

    head_to_head_match = _match_head_to_head(q, team1, team2, scope, year, start_week, end_week)
    if head_to_head_match:
        return head_to_head_match

    if (
        ("best ranked team of the week" in q or "weekly #1" in q or "week #1" in q or "top team of the week" in q)
        and ("played against" in q or "face" in q or "faced" in q or "opponent" in q)
    ):
        return CapabilityMatch(intent="vs_weekly_top_team", params={"year": year, "year_range": "ALL", "scope": "RS"})

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

    if _contains_any(q, ["leaders for every category", "leader for every category", "every category leaders", "category leaders"]):
        return CapabilityMatch(
            intent="category_sweep",
            params={"year": year, "scope": scope if scope != "ALL" else "RS", "mode": "best"},
        )

    if _contains_any(q, ["losers for every category", "worst for every category", "category losers"]):
        return CapabilityMatch(
            intent="category_sweep",
            params={"year": year, "scope": scope if scope != "ALL" else "RS", "mode": "worst"},
        )

    if "likely category leaders" in q:
        return CapabilityMatch(
            intent="category_sweep",
            params={"year": year, "scope": scope if scope != "ALL" else "RS", "mode": "best"},
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

    draft_match = _match_draft_questions(q, year, top_n)
    if draft_match:
        return draft_match

    if ("standings" in q or "place" in q) and ("if we used" in q or "alternate" in q):
        return CapabilityMatch(intent="standings_alternate", params={"year": year})

    if "standings" in q:
        fmt = "cats" if "category" in q or "cats" in q else "wl" if "matchup" in q or "w/l" in q else "auto"
        return CapabilityMatch(intent="standings", params={"year": year, "standings_format": fmt})

    if (
        team1
        and not team2
        and stat is None
        and _contains_any(q, ["where is", "what rank", "what place", "ranked", "position"])
    ):
        return CapabilityMatch(intent="standings", params={"year": year, "team": team1, "standings_format": "auto"})

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

    if _contains_any(q, ["strongest and weakest categories", "strongest categories", "weakest categories"]):
        return CapabilityMatch(intent="team_summary", params={"year": year, "scope": scope if scope != "ALL" else "RS", "team": team1})

    if _contains_any(q, ["average rating by season", "avg rating by season"]):
        return CapabilityMatch(intent="team_rating_by_season", params={"year": year, "team": team1, "year_range": "ALL", "scope": "RS"})

    if team1 and _contains_any(q, ["best season", "worst season"]) and not _contains_any(q, ["draft", "playoff", "matchup tie"]):
        return CapabilityMatch(
            intent="team_rating_by_season",
            params={
                "year": year,
                "team": team1,
                "year_range": "ALL",
                "scope": "RS",
                "mode": "worst" if "worst season" in q else "best",
            },
        )

    if _contains_any(q, ["toughest 5-week stretch", "toughest five-week stretch", "toughest stretch"]) and team1:
        m = re.search(r"(\d+)\s*-\s*week|(\d+)\s*week", q)
        window = 5
        if m:
            window = int(next(g for g in m.groups() if g))
        return CapabilityMatch(
            intent="schedule_toughest_stretch",
            params={"year": year, "team": team1, "scope": scope if scope != "ALL" else "RS", "n": window},
        )

    if _contains_any(q, ["first half to second half", "first half", "second half"]) and _contains_any(q, ["improved", "improvement"]):
        return CapabilityMatch(intent="half_split_improvement", params={"year": year, "scope": scope if scope != "ALL" else "RS"})

    if _contains_any(q, ["most volatile", "volatile team", "volatile by week_rating"]):
        return CapabilityMatch(intent="consistency", params={"year": year, "year_range": "ALL", "mode": "volatile"})

    leader_vs_team_match = _match_leader_vs_team(q, stat, team1, scope, year, start_week, end_week, top_n)
    if leader_vs_team_match:
        return leader_vs_team_match

    if stat and ("leader" in q or "most" in q or "least" in q or "best" in q or "worst" in q or "top " in q or "selling in" in q):
        direction = "min" if any(tok in q for tok in ["least", "fewest", "worst", "lowest"]) else "max"
        if "selling in" in q:
            direction = "min"
        if stat == "TO" and any(tok in q for tok in ["worst", "most", "cumulative"]):
            direction = "max"
        top_n_match = re.search(r"\btop\s*(\d+)\b", q)
        if top_n_match:
            top_n_local = int(top_n_match.group(1))
        elif any(tok in q for tok in ["best", "most", "least", "worst"]):
            top_n_local = 10
        else:
            top_n_local = top_n
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
