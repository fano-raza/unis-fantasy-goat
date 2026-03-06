#!/usr/bin/env python3
"""
Proactive parser coverage report.

Runs question-bank prompts through parse_query(use_llm=False) and reports:
- coverage by section
- unknown intents
- mismatches against expected intent families
- unanswered-log summary (optional)
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from discord.query_parser import parse_query

QUESTION_BANK = ROOT / "analytics" / "analytics_question_bank.md"
UNANSWERED_LOG = ROOT / "discord" / "unanswered_questions.jsonl"


EXPECTED = {
    "standings": {"standings", "standings_alternate"},
    "leaders": {"leader", "leader_vs_team"},
    "weekly_and_ranges": {"week_leader", "leader", "standings"},
    "head_to_head": {"head_to_head", "team_compare", "record_vs_team"},
    "team_summary": {"team_summary"},
    "schedule_strength": {"strength_of_schedule", "opponent_uplift"},
    "seed_performance": {"record_vs_seed"},
    "draft_value": {"draft_pick_value", "draft_player_score", "draft_team_score"},
    "correlations": {"correlation", "correlation_scan"},
    "trends_and_records": {
        "trend_split",
        "consistency",
        "vs_weekly_top_team",
        "weekly_top_performer_count",
        "leader",
        "record_vs_team",
    },
    "what_if": {"what_if_schedule_swap", "standings"},
    "predictive": {"predict_champion"},
    "language_variants": {
        "standings",
        "leader",
        "leader_vs_team",
        "record_vs_seed",
        "record_vs_team",
        "unknown",
    },
}


def load_question_bank(path: Path) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = defaultdict(list)
    current = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("## "):
            current = line[3:].strip()
            continue
        if current and line.startswith("- "):
            q = line[2:].strip()
            if q:
                sections[current].append(q)
    return sections


def run_coverage(sections: dict[str, list[str]]) -> tuple[list[dict], dict[str, Counter]]:
    rows = []
    by_section_intents: dict[str, Counter] = defaultdict(Counter)

    for section, questions in sections.items():
        expected = EXPECTED.get(section, set())
        for q in questions:
            spec = parse_query(q, use_llm=False)
            intent = spec.intent
            ok = intent in expected if expected else True
            rows.append(
                {
                    "section": section,
                    "question": q,
                    "intent": intent,
                    "ok": ok,
                    "expected": sorted(expected),
                }
            )
            by_section_intents[section][intent] += 1
    return rows, by_section_intents


def summarize_unanswered(path: Path, tail: int = 200) -> dict[str, Counter]:
    if not path.exists():
        return {"reasons": Counter(), "intents": Counter()}
    reasons = Counter()
    intents = Counter()
    lines = path.read_text(encoding="utf-8").splitlines()[-tail:]
    for line in lines:
        try:
            rec = json.loads(line)
        except Exception:
            continue
        reasons[str(rec.get("reason", "unknown"))] += 1
        spec = rec.get("spec") or {}
        intents[str(spec.get("intent", "unknown"))] += 1
    return {"reasons": reasons, "intents": intents}


def main() -> None:
    sections = load_question_bank(QUESTION_BANK)
    rows, section_counts = run_coverage(sections)
    total = len(rows)
    ok = sum(1 for r in rows if r["ok"])
    unknown = sum(1 for r in rows if r["intent"] == "unknown")

    print("== Parser Coverage Report ==")
    print(f"Question bank: {QUESTION_BANK}")
    print(f"Total prompts: {total}")
    print(f"Expected-family matches: {ok}/{total} ({(ok / total * 100.0) if total else 0:.1f}%)")
    print(f"Unknown intents: {unknown}")
    print("")

    print("== Coverage by Section ==")
    for section in sections:
        s_rows = [r for r in rows if r["section"] == section]
        s_total = len(s_rows)
        s_ok = sum(1 for r in s_rows if r["ok"])
        s_unknown = sum(1 for r in s_rows if r["intent"] == "unknown")
        print(f"- {section}: {s_ok}/{s_total} matched, unknown={s_unknown}, intents={dict(section_counts[section])}")
    print("")

    mismatches = [r for r in rows if not r["ok"]]
    if mismatches:
        print("== Mismatches (first 30) ==")
        for r in mismatches[:30]:
            exp = ", ".join(r["expected"]) if r["expected"] else "n/a"
            print(f"- [{r['section']}] intent={r['intent']} expected={exp} :: {r['question']}")
        print("")

    u = summarize_unanswered(UNANSWERED_LOG)
    if u["reasons"] or u["intents"]:
        print("== Unanswered Log (recent tail) ==")
        print(f"- reasons: {dict(u['reasons'])}")
        print(f"- intents: {dict(u['intents'])}")


if __name__ == "__main__":
    main()
