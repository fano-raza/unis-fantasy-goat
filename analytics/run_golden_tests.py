from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from constants import currentYear, seasonInfo
from discord.query_parser import parse_query

INTENT_ALIASES = {
    "leaderboard_stat": "leader",
}

SUPPORTED_INTENTS = {
    "leader",
    "standings",
    "standings_alternate",
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
    "correlation",
    "correlation_scan",
    "trend_split",
    "consistency",
    "what_if_schedule_swap",
    "recap_regular_season",
}

PARAM_ALIASES = {
    "format": "standings_format",
    "team_a": "team",
    "team_b": "team2",
    "week_start": "start_week",
    "week_end": "end_week",
}

SCOPE_ALIASES = {
    "regular_season": "RS",
    "playoffs": "PO",
    "full_season": "ALL",
}

YEAR_RANGE_ALIASES = {
    "all_time": "ALL",
    "single_year": "single_year",
}


def _normalize_expected(value):
    if isinstance(value, str) and value == "current_year":
        return currentYear
    if isinstance(value, str) and value in SCOPE_ALIASES:
        return SCOPE_ALIASES[value]
    return value


def _normalize_expected_param(key: str, value):
    if isinstance(value, str) and value == "current_year":
        return currentYear
    if key == "year_range" and isinstance(value, str):
        return YEAR_RANGE_ALIASES.get(value, value)
    if key == "scope" and isinstance(value, str) and value in YEAR_RANGE_ALIASES:
        return YEAR_RANGE_ALIASES[value]
    if isinstance(value, str):
        return SCOPE_ALIASES.get(value, value)
    return value


def _read_goldens(path: Path) -> list[dict]:
    tests = []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw:
            continue
        tests.append(json.loads(raw))
    return tests


def _get_actual_param(spec, key: str):
    if key == "scope":
        # Most intents use QuerySpec.scope; draft_team_score expects scope-like values
        # that map to QuerySpec.year_range.
        return spec.year_range if spec.intent == "draft_team_score" else spec.scope
    key = PARAM_ALIASES.get(key, key)
    if not hasattr(spec, key):
        return None
    return getattr(spec, key)


def run(path: Path) -> int:
    tests = _read_goldens(path)
    failures = []
    skipped = []

    for idx, test in enumerate(tests, start=1):
        q = test["question"]
        expected_intent = INTENT_ALIASES.get(test["expected_intent"], test["expected_intent"])
        if expected_intent not in SUPPORTED_INTENTS:
            skipped.append((idx, q, expected_intent))
            continue
        expected_params = test.get("expected_params", {})
        spec = parse_query(q, use_llm=False)

        row_failures = []
        if spec.intent != expected_intent:
            row_failures.append(f"intent expected={expected_intent} actual={spec.intent}")

        for k, v in expected_params.items():
            expected = _normalize_expected_param(k, v)
            if k == "place" and expected == "last":
                yr = expected_params.get("year", currentYear)
                yr = _normalize_expected(yr)
                expected = len(seasonInfo.get(int(yr), ([],))[0])
            actual = _get_actual_param(spec, k)
            if actual != expected:
                row_failures.append(f"param[{k}] expected={expected!r} actual={actual!r}")

        if row_failures:
            failures.append((idx, q, row_failures))

    total_ran = len(tests) - len(skipped)
    passed = total_ran - len(failures)
    print(f"Golden tests: {passed}/{total_ran} passed ({len(skipped)} skipped unsupported)")

    if failures:
        print("\nFailures:")
        for idx, q, errs in failures:
            print(f"- #{idx}: {q}")
            for err in errs:
                print(f"  - {err}")
        return 1

    if skipped:
        print("\nSkipped (unsupported intents):")
        for idx, q, intent in skipped:
            print(f"- #{idx} [{intent}] {q}")

    return 0


if __name__ == "__main__":
    golden_path = Path("analytics/analytics_goldens.jsonl")
    raise SystemExit(run(golden_path))
