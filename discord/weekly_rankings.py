"""Monday "Week N Rankings" post for #<RANKINGS_CHANNEL_ID>, plus a
Ref/weekly_recaps.csv row so the same content surfaces on the web app's
Weekly Stats page for that (year, week).

Deliberately split into a deterministic half and an AI half, per the
user's explicit request to conserve tokens for just the subjective part:

- build_header()/build_rank_table() are pure string formatting from
  /league/weekly_leaderboard's already-computed rank/rating -- zero
  tokens, zero AI, and correct even if the AI half is skipped entirely
  (missing OPENAI_API_KEY, budget exhausted, or a transient API error).
- build_commentary_facts() computes a SMALL JSON of facts only (rank,
  season-long streak/count at that rank, opponent, matchup result, season
  standing) for just the top and bottom team -- never raw stats, never
  free text -- so generate_commentary() can't invent anything not present
  in the facts.
- SYSTEM_PROMPT is a first-draft placeholder, tested live against real
  2026 season data (see _planning/web-app-build-plan.md's session log --
  one real call: 351 input + 122 output tokens). The user explicitly
  wants to hand-tune its exact wording/tone before this goes live in
  production; nothing else in this module depends on its exact text, so
  it's safe to edit freely.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Awaitable, Callable

from shared.runtime_config import weekly_recaps_csv_path

RANKINGS_CHANNEL_ID = 1029164739558903928
WEB_APP_BASE_URL = os.getenv("WEB_APP_BASE_URL", "https://unis-fantasy-goat.vercel.app")

# (path, payload) -> (status, response_json) -- matches discord/stat_bot.py's
# _api_post exactly, passed in rather than imported so this module has no
# hard dependency on stat_bot.py and can be exercised standalone (dry runs,
# tests) with a fake implementation.
ApiPost = Callable[[str, dict], Awaitable[tuple[int, dict]]]

SYSTEM_PROMPT = (
    "You write short, lightly humorous fantasy-basketball weekly recap blurbs for a Discord league. "
    "You will be given JSON facts about the TOP-ranked team and BOTTOM-ranked team for this week only. "
    "Write exactly two short paragraphs (2-3 sentences each, ~40-70 words), separated by a blank line: "
    "the first about the top team (positive/celebratory tone), the second about the bottom team "
    "(playful/disparaging tone, still good-natured). "
    "Use ONLY the facts provided -- never invent injuries, trades, player performances, or other context "
    "not present in the JSON. Refer to teams by their team/owner name. Do not include a title or header, "
    "just the two paragraphs."
)

CSV_FIELDS = ["year", "week", "rank_table_json", "top_team", "bottom_team", "commentary", "posted_at"]


def build_header(year: int, week: int) -> str:
    link = f"{WEB_APP_BASE_URL}/?year={year}&week={week}"
    return f"@everyone\n**Week {week} Rankings**\n{link}"


def build_rank_table(ranked_rows: list[dict]) -> str:
    """ranked_rows: weekly_leaderboard()'s rows, already filtered to
    rank-is-not-None and sorted by rank ascending (see
    fetch_ranked_rows())."""
    # 4-space separator matches the real historical "Week N Rankings"
    # posts' format exactly (pulled live from Discord this session).
    lines = ["Rank    Team"]
    for row in ranked_rows:
        lines.append(f"{row['rank']}    {row['team']}")
    return "\n".join(lines)


def build_message(year: int, week: int, ranked_rows: list[dict], commentary: str | None) -> str:
    parts = [build_header(year, week), build_rank_table(ranked_rows)]
    if commentary:
        parts.append(commentary)
    return "\n\n".join(parts)


async def determine_last_completed_week(
    api_post: ApiPost, year: int, now_eastern: datetime | None = None
) -> int | None:
    """The week that most recently ended, as of right now (Eastern time) --
    mirrors GDoc/GDoc_updater.py's own calendar-lookup + 2AM-cutoff logic
    (Sunday games extending past midnight still count as the prior day),
    but via the already-exposed /league/week_calendar endpoint instead of
    reading the calendar CSV directly (stat-bot has no filesystem access
    to DATA_ROOT). Returns None if there's no calendar data for `year` yet
    (e.g. the season hasn't been set up) or if `year`'s calendar's first
    week is still in progress (nothing has completed yet). Does NOT check
    whether the result is a regular-season week -- callers should compare
    against meta()'s rs_week_count themselves, since that boundary can
    shift year to year.

    `now_eastern` defaults to the real current time; tests pass a fixed
    value instead of monkeypatching datetime.now()."""
    from datetime import date, datetime, time, timedelta
    from zoneinfo import ZoneInfo

    status, calendar = await api_post("/league/week_calendar", {"year": year})
    if status != 200 or not calendar:
        return None

    if now_eastern is None:
        now_eastern = datetime.now(ZoneInfo("America/New_York"))
    today = now_eastern.date()
    if now_eastern.time() <= time(2, 0):
        today -= timedelta(days=1)

    current_week_in_progress = None
    for row in sorted(calendar, key=lambda r: r["Week"]):
        if today >= date.fromisoformat(row["StartDate"]):
            current_week_in_progress = row["Week"]

    if current_week_in_progress is None or current_week_in_progress <= 1:
        return None
    return current_week_in_progress - 1


async def fetch_ranked_rows(api_post: ApiPost, year: int, week: int) -> list[dict]:
    status, rows = await api_post("/league/weekly_leaderboard", {"year": year, "week": week})
    if status != 200:
        return []
    return sorted((r for r in rows if r.get("rank") is not None), key=lambda r: r["rank"])


def _result_label(row: dict) -> str | None:
    if row.get("matchup_win"):
        return "win"
    if row.get("matchup_loss"):
        return "loss"
    if row.get("matchup_tie"):
        return "tie"
    return None


async def _season_rank_history(
    api_post: ApiPost, year: int, week: int, top_team: str, bottom_team: str
) -> tuple[int, int, int, int]:
    """Walks backward from `week` to week 1, ONE /weekly_leaderboard call per
    week (shared between both teams, not one call per team), computing for
    each team both a consecutive streak (stops counting the moment the
    position breaks, walking backward from `week`) and a season-total count
    (keeps counting for every earlier week that position was held, even
    after a gap) -- both concepts show up in the real historical "Week N
    Rankings" posts ("third top rank of the season" vs. "third week in a
    row"), so both are computed and left for the commentary prompt to
    choose between.

    Returns (top_streak, top_total, bottom_streak, bottom_total).
    """
    top_streak = top_total = bottom_streak = bottom_total = 0
    top_streak_active = bottom_streak_active = True

    for w in range(week, 0, -1):
        status, rows = await api_post("/league/weekly_leaderboard", {"year": year, "week": w})
        if status != 200:
            break
        ranked = [r for r in rows if r.get("rank") is not None]
        if not ranked:
            continue
        bottom_rank = len(ranked)

        top_row = next((r for r in ranked if r["team"] == top_team), None)
        if top_row is not None and top_row["rank"] == 1:
            top_total += 1
            if top_streak_active:
                top_streak += 1
        else:
            top_streak_active = False

        bottom_row = next((r for r in ranked if r["team"] == bottom_team), None)
        if bottom_row is not None and bottom_row["rank"] == bottom_rank:
            bottom_total += 1
            if bottom_streak_active:
                bottom_streak += 1
        else:
            bottom_streak_active = False

    return top_streak, top_total, bottom_streak, bottom_total


async def build_commentary_facts(api_post: ApiPost, year: int, week: int, ranked_rows: list[dict]) -> dict | None:
    if not ranked_rows:
        return None
    top = ranked_rows[0]
    bottom = ranked_rows[-1]
    if top is bottom:
        # A 1-team week (shouldn't happen in a real league) -- nothing to
        # compare, so skip commentary rather than write a facts blob that
        # would just describe one team as both best and worst.
        return None

    top_streak, top_total, bottom_streak, bottom_total = await _season_rank_history(
        api_post, year, week, top["team"], bottom["team"]
    )

    status, standings = await api_post("/league/standings", {"year": year, "min_week": 1, "max_week": week})
    wl_rows = standings.get("wl", []) if status == 200 else []

    def season_info(team: str) -> dict:
        row = next((r for r in wl_rows if r["team"] == team), None)
        if row is None:
            return {"season_rank": None, "season_record": None}
        return {
            "season_rank": row["rank"],
            "season_record": f"{row['wins']}-{row['losses']}-{row['ties']}",
        }

    return {
        "week": week,
        "top_team": {
            "name": top["team"],
            "week_rank": top["rank"],
            "week_rating": top["rating"],
            "top_rank_streak_this_season": top_streak,
            "top_rank_count_this_season": top_total,
            "opponent": top["opponent"],
            "matchup_result": _result_label(top),
            **season_info(top["team"]),
        },
        "bottom_team": {
            "name": bottom["team"],
            "week_rank": bottom["rank"],
            "week_rating": bottom["rating"],
            "bottom_rank_streak_this_season": bottom_streak,
            "bottom_rank_count_this_season": bottom_total,
            "opponent": bottom["opponent"],
            "matchup_result": _result_label(bottom),
            **season_info(bottom["team"]),
        },
    }


async def generate_commentary(facts: dict) -> str | None:
    """Returns None (never raises) on any failure -- missing key, budget
    exhausted, or a transient API error -- so the deterministic rank-table
    message can still post on its own. See discord/llm_planner.py for the
    identical budget/error-handling shape this mirrors."""
    from discord.llm_usage import budget_remaining, extract_usage, record_usage

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

    model = os.getenv("DISCORD_QA_MODEL", "gpt-4.1-mini")
    client = OpenAI(api_key=api_key)
    try:
        resp = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(facts)},
            ],
            temperature=0.7,
            max_output_tokens=300,
        )
    except Exception as exc:
        print(f"Weekly rankings commentary generation failed: {exc}")
        return None

    in_tok, out_tok, total_tok = extract_usage(resp)
    record_usage("weekly_rankings_commentary", model, f"week {facts.get('week')}", in_tok, out_tok, total_tok)
    return getattr(resp, "output_text", None) or None


def _ensure_csv(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=CSV_FIELDS).writeheader()


def _existing_recap_keys(path: Path) -> set[tuple[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return {(row["year"], row["week"]) for row in csv.DictReader(f)}


def append_weekly_recap(
    year: int,
    week: int,
    ranked_rows: list[dict],
    top_team: str,
    bottom_team: str,
    commentary: str | None,
    posted_at: str,
) -> None:
    """Appends one row -- never overwrites prior weeks' rows, matching
    discord/daily_games.py's append-only convention. A no-op (not an
    error) if this exact (year, week) was already recorded, so a retried
    post (e.g. after a Discord send succeeds but a later step fails) can't
    write a duplicate row."""
    path = weekly_recaps_csv_path()
    _ensure_csv(path)
    key = (str(year), str(week))
    if key in _existing_recap_keys(path):
        return

    rank_table_json = json.dumps(
        [{"team": r["team"], "rank": r["rank"], "rating": r["rating"]} for r in ranked_rows]
    )
    row = {
        "year": year,
        "week": week,
        "rank_table_json": rank_table_json,
        "top_team": top_team,
        "bottom_team": bottom_team,
        "commentary": commentary or "",
        "posted_at": posted_at,
    }
    with path.open("a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=CSV_FIELDS).writerow(row)


async def post_weekly_rankings(bot, api_post: ApiPost, year: int, week: int) -> bool:
    """Builds and posts the full Monday message, then records the recap
    row for the web app. Returns True on success (message sent), False if
    there was no data to post (e.g. the week hasn't completed yet)."""
    from datetime import datetime, timezone

    ranked_rows = await fetch_ranked_rows(api_post, year, week)
    if not ranked_rows:
        return False

    facts = await build_commentary_facts(api_post, year, week, ranked_rows)
    commentary = await generate_commentary(facts) if facts else None
    message = build_message(year, week, ranked_rows, commentary)

    channel = bot.get_channel(RANKINGS_CHANNEL_ID) or await bot.fetch_channel(RANKINGS_CHANNEL_ID)
    await channel.send(message)

    top_team = ranked_rows[0]["team"]
    bottom_team = ranked_rows[-1]["team"]
    append_weekly_recap(
        year, week, ranked_rows, top_team, bottom_team, commentary,
        datetime.now(timezone.utc).isoformat(),
    )
    return True
