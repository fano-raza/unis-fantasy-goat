from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path


# Extra phrase coverage beyond hardcoded aliases in parser/query engine.
# This is intentionally deterministic and local (no API calls).
EXTRA_METRIC_ALIASES: dict[str, list[str]] = {
    "PTS": ["bucket", "buckets", "scored points", "put up points"],
    "REB": ["glass", "on the glass", "crash the glass"],
    "AST": ["dimes", "diming", "playmaking"],
    "STL": ["picks", "swipes"],
    "BLK": ["rejections", "swats"],
    "TO": ["giveaways", "cough-ups"],
    "3PTM": ["triples", "treys", "threes made", "3s made"],
    "FG%": ["fg pct", "field goal pct"],
    "FT%": ["ft pct", "free throw pct"],
    "W": ["matchup wins", "games won"],
    "L": ["matchup losses", "games lost"],
    "D": ["matchup ties", "games tied"],
    "CAT_W": ["cat wins", "category w"],
    "CAT_L": ["cat losses", "category l"],
    "CAT_D": ["cat ties", "category d"],
    "WIN_PCT": ["winning percentage", "record pct", "record percentage"],
    "CAT_WIN_PCT": ["category winning percentage", "cat winning percentage"],
    "AVG_RATING": ["avg week rating", "average week rating"],
    "AVG_OPP_RATING": ["opp rating", "opponent strength", "strength of schedule"],
    "SOS_RANK": ["schedule strength rank", "sos ranking"],
    "RANK": ["overall rank", "ranking average"],
    "WEIGHTED_RANK": ["wt ranking", "weighted ranking"],
    "DRAFT_SCORE": ["draft grade", "draft grades", "draft performance"],
    "DRAFT_SCORE_PER_PICK": ["draft score avg", "avg draft score", "draft score average"],
    "TOP1_WEEKS": ["weeks at #1", "weeks ranked #1"],
    "TOP3_RATE": ["top three rate", "top-3 percentage"],
    "PLAYOFF_APPEARANCES": ["playoff berths", "made the playoffs"],
    "PLAYOFF_APP_RATE": ["playoff berth rate", "playoffs appearance rate"],
    "FINALS": ["finals berths", "made the finals"],
    "CHIPS": ["chips", "titles", "championships", "rings"],
    "FINALS_CONVERSION": ["title conversion", "chip rate in finals"],
}

WORDNET_ALIAS_PATH = Path(__file__).resolve().parent / "metric_aliases_wordnet.json"


OPERATOR_ALIASES: dict[str, tuple[str, ...]] = {
    "avg": ("average", "avg", "mean", "per game", "per week", "per season", "on average"),
    "total": ("total", "totals", "sum", "cumulative", "overall"),
}


def _contains_alias(q: str, alias: str) -> bool:
    a = alias.lower().strip()
    if not a:
        return False
    if len(a) <= 3 and a.isalpha():
        return re.search(rf"\b{re.escape(a)}\b", q) is not None
    return a in q


@lru_cache(maxsize=16)
def merged_metric_aliases(base_alias_items: tuple[tuple[str, tuple[str, ...]], ...]) -> dict[str, tuple[str, ...]]:
    merged: dict[str, tuple[str, ...]] = {}
    dynamic = _load_wordnet_aliases()
    for metric, aliases in base_alias_items:
        extra = tuple(EXTRA_METRIC_ALIASES.get(metric, [])) + tuple(dynamic.get(metric, []))
        seen = []
        for a in tuple(aliases) + extra:
            low = a.lower().strip()
            if low and low not in seen:
                seen.append(low)
        merged[metric] = tuple(seen)
    # Keep extras even if not present in base table yet.
    for metric, extras in {**EXTRA_METRIC_ALIASES, **dynamic}.items():
        if metric not in merged:
            merged[metric] = tuple(dict.fromkeys([e.lower().strip() for e in extras if e.strip()]))
    return merged


def _load_wordnet_aliases() -> dict[str, list[str]]:
    if not WORDNET_ALIAS_PATH.exists():
        return {}
    try:
        raw = json.loads(WORDNET_ALIAS_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        out: dict[str, list[str]] = {}
        for k, v in raw.items():
            if isinstance(k, str) and isinstance(v, list):
                out[k] = [str(x).strip().lower() for x in v if str(x).strip()]
        return out
    except Exception:
        return {}


def resolve_metric(question: str, metric_order: list[str], aliases: dict[str, list[str]]) -> str | None:
    q = (question or "").lower()
    base_items = tuple((k, tuple(v)) for k, v in aliases.items())
    merged = merged_metric_aliases(base_items)
    for metric in metric_order:
        for alias in merged.get(metric, ()):
            if _contains_alias(q, alias):
                return metric
    return None


def resolve_operator_method(question: str, default: str = "total") -> str:
    q = (question or "").lower()
    if any(_contains_alias(q, a) for a in OPERATOR_ALIASES["avg"]):
        return "avg"
    if any(_contains_alias(q, a) for a in OPERATOR_ALIASES["total"]):
        return "total"
    return default


def resolve_basic_stat(question: str, stat_aliases: dict[str, list[str]]) -> str | None:
    q = (question or "").lower()
    base_items = tuple((k, tuple(v)) for k, v in stat_aliases.items())
    merged = merged_metric_aliases(base_items)
    # Keep common box-score ordering for deterministic precedence.
    metric_order = ["PTS", "REB", "AST", "STL", "BLK", "TO", "3PTM", "FG%", "FT%"]
    for metric in metric_order:
        for alias in merged.get(metric, ()):
            if _contains_alias(q, alias):
                return metric
    return None
