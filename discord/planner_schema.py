from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .capability_registry import VALID_INTENTS


ALLOWED_KEYS = {
    "intent",
    "year",
    "relative_year_offset",
    "year_range",
    "scope",
    "stat",
    "direction",
    "top_n",
    "team",
    "team2",
    "week",
    "start_week",
    "end_week",
    "standings_format",
    "place",
    "seed",
    "seed_mode",
    "k",
    "timing",
    "method",
    "mode",
    "n",
    "metric",
    "target_metric",
    "candidate_metrics",
    "metric_x",
    "metric_y",
    "confidence",
    "reasoning",
    "needs_clarification",
    "clarification_question",
}


@dataclass
class PlannerValidationResult:
    ok: bool
    errors: list[str]


def _is_int_or_none(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, bool):
        return False
    try:
        int(v)
        return True
    except Exception:
        return False


def validate_plan_obj(plan: Any) -> PlannerValidationResult:
    errors: list[str] = []
    if not isinstance(plan, dict):
        return PlannerValidationResult(False, ["plan_not_object"])

    unknown = sorted(set(plan.keys()) - ALLOWED_KEYS)
    if unknown:
        errors.append(f"unknown_keys:{','.join(unknown)}")

    intent = plan.get("intent")
    if not isinstance(intent, str) or intent not in VALID_INTENTS:
        errors.append("invalid_intent")

    if plan.get("scope") is not None and str(plan.get("scope")).upper() not in {"ALL", "RS", "PO"}:
        errors.append("invalid_scope")

    if plan.get("direction") is not None and str(plan.get("direction")).lower() not in {"max", "min"}:
        errors.append("invalid_direction")

    if plan.get("standings_format") is not None and str(plan.get("standings_format")).lower() not in {"auto", "wl", "cats"}:
        errors.append("invalid_standings_format")

    if plan.get("year_range") is not None and str(plan.get("year_range")).upper() not in {
        "ALL", "ALL_TIME", "ALLTIME", "CAREER", "SINGLE", "SINGLE_YEAR", "NONE", ""
    }:
        errors.append("invalid_year_range")

    for k in ["year", "relative_year_offset", "top_n", "week", "start_week", "end_week", "seed", "k", "n"]:
        if not _is_int_or_none(plan.get(k)):
            errors.append(f"invalid_{k}")

    place = plan.get("place")
    if place is not None:
        if isinstance(place, str):
            if place != "last":
                try:
                    int(place)
                except Exception:
                    errors.append("invalid_place")
        elif not _is_int_or_none(place):
            errors.append("invalid_place")

    conf = plan.get("confidence")
    if conf is not None:
        try:
            c = float(conf)
            if c < 0 or c > 1:
                errors.append("invalid_confidence")
        except Exception:
            errors.append("invalid_confidence")

    needs = plan.get("needs_clarification")
    if needs is not None and not isinstance(needs, bool):
        errors.append("invalid_needs_clarification")

    cq = plan.get("clarification_question")
    if cq is not None and not isinstance(cq, str):
        errors.append("invalid_clarification_question")

    return PlannerValidationResult(ok=not errors, errors=errors)
