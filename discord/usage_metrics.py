import datetime
import json
import os
from pathlib import Path
from typing import Any

USAGE_LOG_FILE = Path(__file__).resolve().parent / "bot_usage_log.jsonl"


def _parse_bool(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def should_log_usage() -> bool:
    # enabled by default
    return not _parse_bool(os.getenv("DISCORD_USAGE_LOG_DISABLE", "0"))


def _trim(text: str | None, max_chars_env: str, default_max: int) -> str:
    raw = os.getenv(max_chars_env, str(default_max)).strip()
    try:
        n = max(20, int(raw))
    except ValueError:
        n = default_max
    return (text or "")[:n]


def record_usage_event(payload: dict[str, Any]) -> None:
    if not should_log_usage():
        return

    out = {
        "ts": datetime.datetime.now(datetime.UTC).isoformat(),
    }
    out.update(payload)
    out["question"] = _trim(str(out.get("question", "")), "DISCORD_USAGE_LOG_MAX_QUESTION_CHARS", 500)
    out["response_preview"] = _trim(str(out.get("response_preview", "")), "DISCORD_USAGE_LOG_MAX_RESPONSE_CHARS", 300)

    try:
        with USAGE_LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(out) + "\n")
    except Exception:
        pass

