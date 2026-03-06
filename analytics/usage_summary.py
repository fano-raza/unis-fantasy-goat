#!/usr/bin/env python3
"""
Usage analytics summary for Discord bot logs.

Reads:
- discord/bot_usage_log.jsonl
- discord/unanswered_questions.jsonl (optional)

Outputs:
- totals, success rate, error rate
- top users, top intents
- latency percentiles (p50/p95/p99)
- recent error samples
- unanswered reasons summary
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
USAGE_LOG = ROOT / "discord" / "bot_usage_log.jsonl"
UNANSWERED_LOG = ROOT / "discord" / "unanswered_questions.jsonl"


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    if p <= 0:
        return min(values)
    if p >= 100:
        return max(values)
    xs = sorted(values)
    k = (len(xs) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return xs[int(k)]
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def summarize_usage(records: list[dict], tail: int = 5000) -> None:
    if not records:
        print("No usage records found.")
        return

    rows = records[-tail:]
    total = len(rows)
    ok = sum(1 for r in rows if bool(r.get("ok", False)))
    errs = total - ok

    intents = Counter(str(r.get("intent") or "unknown") for r in rows)
    users = Counter(str(r.get("display_name") or r.get("username") or r.get("user_id") or "unknown") for r in rows)
    teams = Counter(str(r.get("mapped_team") or "unmapped") for r in rows)
    team_sources = Counter(str(r.get("team_map_source") or "none") for r in rows)
    sources = Counter(str(r.get("source") or "unknown") for r in rows)
    channels = Counter(str(r.get("channel_id") or "unknown") for r in rows)
    guilds = Counter(str(r.get("guild_id") or "dm") for r in rows)

    latency = [float(r.get("latency_ms", 0) or 0) for r in rows]
    latency = [x for x in latency if x >= 0]

    print("== Bot Usage Summary ==")
    print(f"Records considered: {total} (tail={tail})")
    print(f"Success: {ok} ({(ok/total)*100:.1f}%)")
    print(f"Errors: {errs} ({(errs/total)*100:.1f}%)")
    print(f"Sources: {dict(sources)}")
    print(f"Unique users: {len(users)} | channels: {len(channels)} | guilds: {len(guilds)}")
    print("")

    print("== Latency (ms) ==")
    print(f"- p50: {_percentile(latency, 50):.1f}")
    print(f"- p95: {_percentile(latency, 95):.1f}")
    print(f"- p99: {_percentile(latency, 99):.1f}")
    print("")

    print("== Top Intents ==")
    for k, v in intents.most_common(15):
        print(f"- {k}: {v}")
    print("")

    print("== Top Users ==")
    for k, v in users.most_common(15):
        print(f"- {k}: {v}")
    print("")

    print("== Top Mapped Teams ==")
    for k, v in teams.most_common(15):
        print(f"- {k}: {v}")
    print(f"- mapping_sources: {dict(team_sources)}")
    print("")

    print("== Recent Errors (max 10) ==")
    bad = [r for r in rows if not bool(r.get("ok", False))]
    for r in bad[-10:]:
        print(
            f"- ts={r.get('ts')} user={r.get('display_name') or r.get('username') or r.get('user_id')} "
            f"intent={r.get('intent')} latency={r.get('latency_ms')}ms err={r.get('error')}"
        )
        q = str(r.get("question", "")).strip()
        if q:
            print(f"  q: {q}")
    print("")


def summarize_unanswered(records: list[dict], tail: int = 5000) -> None:
    if not records:
        print("No unanswered records found.")
        return
    rows = records[-tail:]
    reasons = Counter(str(r.get("reason", "unknown")) for r in rows)
    intents = Counter(str((r.get("spec") or {}).get("intent", "unknown")) for r in rows)
    print("== Unanswered Summary ==")
    print(f"Records considered: {len(rows)} (tail={tail})")
    print(f"- reasons: {dict(reasons)}")
    print(f"- intents: {dict(intents)}")
    print("")


def main() -> None:
    usage = _read_jsonl(USAGE_LOG)
    unanswered = _read_jsonl(UNANSWERED_LOG)
    summarize_usage(usage, tail=5000)
    summarize_unanswered(unanswered, tail=5000)


if __name__ == "__main__":
    main()
