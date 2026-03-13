#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from discord.query_parser import parse_query
from discord.stats_query_engine import NO_ANSWER_MSG, answer_query


@dataclass(frozen=True)
class ParseCase:
    q: str
    intent: str
    stat: str | None = None
    year: int | None = None


INTENT_CASES: list[ParseCase] = [
    ParseCase("what team has zahir lost to the most", "record_vs_team"),
    ParseCase("who does fano struggle against the most", "record_vs_team"),
    ParseCase("who has the worst record against juan", "record_vs_team"),
    ParseCase("where is juan ranked this season", "standings"),
    ParseCase("what place is amil in right now", "standings"),
    ParseCase("who has tied the most games", "matchup_tie_leaders"),
    ParseCase("what years did ange tie his matchups", "matchup_tie_history"),
    ParseCase("who had the most stls in 2023", "leader", stat="STL", year=2023),
    ParseCase("who had the most asts in 2024", "leader", stat="AST", year=2024),
    ParseCase("who had the most rebs in 2025", "leader", stat="REB", year=2025),
    ParseCase("who had the most blks in 2025", "leader", stat="BLK", year=2025),
    ParseCase("who had the least tos in 2026", "leader", stat="TO", year=2026),
    ParseCase("who scores most against juan", "leader_vs_team", stat="PTS", year=2026),
    ParseCase("who is having the best week week 20", "standings", year=2026),
    ParseCase("when did chirayu win his chips", "champions_lounge"),
    ParseCase("what year did chirayu win his chip", "champions_lounge"),
    ParseCase("who was the best team in 2023", "best_team_snapshot", year=2023),
    ParseCase("who would win this week, rohil or sama", "head_to_head"),
]


ANSWER_GUARD_CASES = [
    "who had the most stls in 2023",
    "when did chirayu win his chips",
    "what year did chirayu win his chip",
    "who was the best team in 2023",
]


def main() -> int:
    bad_parse = []
    for case in INTENT_CASES:
        q = case.q
        spec = parse_query(q, use_llm=False)
        errs = []
        if spec.intent != case.intent:
            errs.append(f"intent expected={case.intent} got={spec.intent}")
        if case.stat is not None and spec.stat != case.stat:
            errs.append(f"stat expected={case.stat} got={spec.stat}")
        if case.year is not None and spec.year != case.year:
            errs.append(f"year expected={case.year} got={spec.year}")
        if errs:
            bad_parse.append((q, errs))

    bad_answer = []
    for q in ANSWER_GUARD_CASES:
        spec = parse_query(q, use_llm=False)
        resp = answer_query(q, spec)
        if (
            not resp
            or resp.strip() == NO_ANSWER_MSG
            or "Can you clarify" in resp
            or "Closest things I can answer" in resp
        ):
            bad_answer.append((q, spec.intent, resp))

    if bad_parse or bad_answer:
        print("Parser regression failures:")
        for q, errs in bad_parse:
            print(f"- q={q!r}")
            for e in errs:
                print(f"  - {e}")
        if bad_answer:
            print("\nAnswer-guard failures:")
            for q, intent, resp in bad_answer:
                print(f"- q={q!r} intent={intent} resp={resp!r}")
        return 1
    print(
        "Parser gap regressions passed: "
        f"{len(INTENT_CASES)} parse checks + {len(ANSWER_GUARD_CASES)} answer guards"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
