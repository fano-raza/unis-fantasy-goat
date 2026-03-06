from __future__ import annotations

import json
import os
from typing import Any

from constants import allMembers
from .capability_registry import capability_json_schema_fragment, lexical_retrieve
from .llm_usage import budget_remaining, extract_usage, record_usage
from .planner_schema import validate_plan_obj


def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None

    # direct parse
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass

    # fenced block
    if "```" in raw:
        parts = raw.split("```")
        for chunk in parts:
            c = chunk.strip()
            if c.lower().startswith("json"):
                c = c[4:].strip()
            if not c:
                continue
            try:
                parsed = json.loads(c)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                continue

    # best-effort first-brace to last-brace
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        snippet = raw[start : end + 1]
        try:
            parsed = json.loads(snippet)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None
    return None


def _planner_prompt(question: str, retrieved_caps: list, routed_hint: dict[str, Any] | None) -> str:
    teams_blob = ", ".join(map(str, allMembers))
    schema_fragment = capability_json_schema_fragment(retrieved_caps)

    return (
        "You are a strict query planner for a fantasy basketball bot.\n"
        "Your job is ONLY to map user language to a deterministic capability and arguments.\n"
        "Never compute statistics or invent numerical results.\n"
        "Return ONLY one JSON object with no markdown.\n\n"
        "Planner fields you may output:\n"
        "intent, year, relative_year_offset, year_range, scope, stat, direction, top_n,\n"
        "team, team2, week, start_week, end_week, standings_format, place,\n"
        "seed, seed_mode, k, timing, method, mode, n, metric, target_metric, candidate_metrics, metric_x, metric_y,\n"
        "confidence, needs_clarification, clarification_question, reasoning\n\n"
        "Rules:\n"
        "- intent must be one of the allowed intents in the capability list below.\n"
        "- scope must be ALL|RS|PO when present.\n"
        "- direction must be max|min when present.\n"
        "- standings_format must be auto|wl|cats when present.\n"
        "- year_range should be ALL for all-time/career wording.\n"
        "- Use relative_year_offset for wording like last season (-1), this season (0), 2 years ago (-2).\n"
        "- Teams must be canonical and chosen from: " + teams_blob + "\n"
        "- If the user asks 'me/my', keep team null unless explicit team can be inferred from question text itself.\n"
        "- If ambiguous, choose the best supported intent and set confidence lower.\n"
        "- Set needs_clarification=true only if no supported intent can answer reliably.\n\n"
        "Common language mappings:\n"
        "- 'who would win this week, A or B' => intent=head_to_head scope=RS with team/team2\n"
        "- 'best team right now' => intent=best_team_snapshot\n"
        "- 'best/worst season for team X' => intent=team_rating_by_season mode=best|worst year_range=ALL\n"
        "- 'who has beaten X the most' => intent=record_vs_team team=X metric=wins direction=max year_range=ALL\n"
        "- 'who has best record against X' => intent=record_vs_team team=X metric=win_pct direction=max\n"
        "- 'titles/chips/championships' => intent=champions_lounge\n"
        "- 'career totals/averages' => intent=all_time_stats_table\n\n"
        f"Retrieved capability slice:\n{json.dumps(schema_fragment, indent=2)}\n\n"
        f"Deterministic routed hint (may be null):\n{json.dumps(routed_hint or {}, indent=2)}\n\n"
        f"User question:\n{question}\n"
    )


def plan_query_with_llm(
    question: str,
    *,
    routed_hint: dict[str, Any] | None = None,
    max_retries: int = 1,
) -> dict[str, Any] | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    remaining, limit = budget_remaining()
    if limit > 0 and remaining <= 0:
        return None

    try:
        from openai import OpenAI
    except Exception:
        return None

    model = os.getenv("DISCORD_PARSE_MODEL", os.getenv("DISCORD_QA_MODEL", "gpt-4.1-mini"))
    client = OpenAI(api_key=api_key)

    retrieved = lexical_retrieve(question, top_k=8)
    prompt = _planner_prompt(question, retrieved, routed_hint)

    for _ in range(max(1, max_retries + 1)):
        try:
            resp = client.responses.create(
                model=model,
                input=[
                    {"role": "system", "content": "Return strictly valid JSON object only."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_output_tokens=220,
            )
            in_tok, out_tok, total_tok = extract_usage(resp)
            record_usage("parse", model, question, in_tok, out_tok, total_tok)
            text = getattr(resp, "output_text", "")
            plan = _extract_json_object(text)
            if not plan:
                continue
            validation = validate_plan_obj(plan)
            if validation.ok:
                return plan
        except Exception:
            return None

    return None
