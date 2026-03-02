import datetime
import json
import os
from pathlib import Path
from typing import Any

STATE_FILE = Path(__file__).resolve().parent / "llm_usage_state.json"
REQUEST_LOG_FILE = Path(__file__).resolve().parent / "llm_request_log.jsonl"


def _parse_bool(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def should_log_requests() -> bool:
    return _parse_bool(os.getenv("DISCORD_LLM_LOG_REQUESTS", "0"))


def current_month_key() -> str:
    return datetime.date.today().strftime("%Y-%m")


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"month": current_month_key(), "tokens_used": 0}
    try:
        with STATE_FILE.open("r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception:
        return {"month": current_month_key(), "tokens_used": 0}

    if state.get("month") != current_month_key():
        return {"month": current_month_key(), "tokens_used": 0}
    return state


def save_state(state: dict) -> None:
    try:
        with STATE_FILE.open("w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception:
        pass


def get_monthly_token_limit() -> int:
    raw = os.getenv("DISCORD_LLM_MAX_TOKENS_MONTH", "0").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def budget_remaining() -> tuple[int, int]:
    """
    Returns (remaining_tokens, monthly_limit).
    If limit is 0, remaining is effectively unlimited (-1).
    """
    limit = get_monthly_token_limit()
    if limit <= 0:
        return -1, 0
    state = load_state()
    used = int(state.get("tokens_used", 0))
    return max(0, limit - used), limit


def extract_usage(resp: Any) -> tuple[int, int, int]:
    usage = getattr(resp, "usage", None)
    if usage is None:
        return 0, 0, 0

    def _get(obj: Any, key: str):
        if isinstance(obj, dict):
            return obj.get(key)
        return getattr(obj, key, None)

    inp = _get(usage, "input_tokens")
    out = _get(usage, "output_tokens")
    total = _get(usage, "total_tokens")

    try:
        inp_i = int(inp) if inp is not None else 0
    except Exception:
        inp_i = 0
    try:
        out_i = int(out) if out is not None else 0
    except Exception:
        out_i = 0

    if total is None:
        total_i = inp_i + out_i
    else:
        try:
            total_i = int(total)
        except Exception:
            total_i = inp_i + out_i

    return inp_i, out_i, total_i


def record_usage(call_type: str, model: str, question: str, input_tokens: int, output_tokens: int, total_tokens: int) -> None:
    if total_tokens <= 0:
        return

    state = load_state()
    state["tokens_used"] = int(state.get("tokens_used", 0)) + int(total_tokens)
    save_state(state)

    if not should_log_requests():
        return

    try:
        max_q_chars_raw = os.getenv("DISCORD_LLM_LOG_MAX_QUESTION_CHARS", "240")
        max_q_chars = max(20, int(max_q_chars_raw))
    except ValueError:
        max_q_chars = 240

    payload = {
        "ts": datetime.datetime.now(datetime.UTC).isoformat(),
        "month": current_month_key(),
        "call_type": call_type,
        "model": model,
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "total_tokens": int(total_tokens),
        "question_preview": (question or "")[:max_q_chars],
    }

    try:
        with REQUEST_LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass
