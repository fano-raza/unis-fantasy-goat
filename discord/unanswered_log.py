import datetime
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

UNANSWERED_LOG_FILE = Path(__file__).resolve().parent / "unanswered_questions.jsonl"


def _parse_bool(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def should_log_unanswered() -> bool:
    # Defaults to enabled so missed coverage is captured automatically.
    return not _parse_bool(os.getenv("DISCORD_UNANSWERED_LOG_DISABLE", "0"))


def _sanitize_question(question: str) -> str:
    max_len_raw = os.getenv("DISCORD_UNANSWERED_LOG_MAX_QUESTION_CHARS", "500")
    try:
        max_len = max(50, int(max_len_raw))
    except ValueError:
        max_len = 500
    return (question or "")[:max_len]


def record_unanswered(question: str, spec: Any, reason: str) -> None:
    if not should_log_unanswered():
        return

    payload = {
        "ts": datetime.datetime.now(datetime.UTC).isoformat(),
        "reason": reason,
        "question": _sanitize_question(question),
    }

    try:
        payload["spec"] = asdict(spec) if spec is not None else None
    except Exception:
        payload["spec"] = {
            "intent": getattr(spec, "intent", None),
            "year": getattr(spec, "year", None),
            "scope": getattr(spec, "scope", None),
        }

    try:
        with UNANSWERED_LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass

