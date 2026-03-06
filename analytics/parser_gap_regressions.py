#!/usr/bin/env python3
from __future__ import annotations

import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from discord.query_parser import parse_query


CASES = [
    ("what team has zahir lost to the most", "record_vs_team"),
    ("who does fano struggle against the most", "record_vs_team"),
    ("who has the worst record against juan", "record_vs_team"),
    ("where is juan ranked this season", "standings"),
    ("what place is amil in right now", "standings"),
    ("who has tied the most games", "matchup_tie_leaders"),
    ("what years did ange tie his matchups", "matchup_tie_history"),
]


def main() -> int:
    bad = []
    for q, expected_intent in CASES:
        spec = parse_query(q, use_llm=False)
        if spec.intent != expected_intent:
            bad.append((q, expected_intent, spec.intent))
    if bad:
        print("Parser gap regression failures:")
        for q, exp, got in bad:
            print(f"- q={q!r} expected={exp} got={got}")
        return 1
    print(f"Parser gap regressions passed: {len(CASES)}/{len(CASES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

