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
    "You write short, trash-talking fantasy-basketball weekly recap blurbs for a Discord league of guys "
    "who talk shit to each other. Every team is owned and managed by a man -- always refer to team owners "
    "with he/him/his pronouns, never they/them/theirs. "
    "You will be given JSON facts about the TOP-ranked team and BOTTOM-ranked team for this week only. "
    "Write exactly two short paragraphs (2-3 sentences each, ~40-70 words), separated by a blank line: "
    "the first about the top team (hype, celebratory), the second about the bottom team (mocking, "
    "disparaging) -- still good-natured trash talk between friends, not genuinely cruel. "
    "Use blunt, colloquial trash-talk phrasing instead of generic sports-recap language. Examples of the "
    "style to hit (don't just reuse these verbatim every time -- vary it, invent similar ones): "
    "'beat the fuck out of him' instead of 'beat him'; 'ran him out of the gym' or 'put a beating on him' "
    "instead of 'won convincingly'; 'got smoked' or 'got run off the court' instead of 'lost badly'; "
    "'is balling out' or 'is on a heater' instead of 'is playing well'; 'is a fucking mess' or 'can't buy "
    "a win' instead of 'is struggling'; 'is running the league' instead of 'is the best team'. "
    "Separately: you may replace an intensifier like 'very'/'really' with 'fucking' (e.g. 'fucking "
    "dominant', 'fucking brutal') -- at most ONCE across the whole message, not once per paragraph. That "
    "cap is only for the very/really-replacement use -- it doesn't limit profanity used inside a colloquial "
    "phrase like the examples above. Don't reach for any other profanity beyond what's shown here. "
    "The facts include more than just this week's result -- use whichever of these are actually notable "
    "(don't force all of them into two short paragraphs): matchup_win_streak/matchup_loss_streak (his real "
    "head-to-head streak RIGHT NOW, separate from his weekly ranking); top_rank_streak_this_season/"
    "bottom_rank_streak_this_season and the _count_this_season versions (how long/how often he's held that "
    "exact position); weekly_rank_history plus is_season_best_week_rank/is_season_worst_week_rank (has he "
    "been consistently near this spot all year, or is this a season-high/season-low outlier); "
    "season_rank_last_week vs. season_rank plus passed_in_standings_this_week/"
    "passed_by_in_standings_this_week (name-drop who he specifically passed or got passed by, if anyone); "
    "and career_record/career_best_win_streak/career_worst_losing_streak (each team's OWN career numbers). "
    "league_record_win_streak is DIFFERENT from all of those -- it is the single best win streak ever "
    "posted by ANY team in league history, which usually belongs to some OTHER team entirely, not "
    "necessarily the one you're writing about. Never state it as if it were this team's own streak. Only "
    "mention it at all when sets_new_league_record_win_streak is true, meaning THIS team's current "
    "matchup_win_streak just tied or broke that outright all-time record -- that's a huge deal and "
    "deserves a real callout when it happens; otherwise ignore league_record_win_streak completely. "
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


async def _fetch_weeks_desc(api_post: ApiPost, year: int, week: int) -> list[tuple[int, list[dict]]]:
    """[(week_num, ranked_rows), ...] for week, week-1, ..., 1 (skipping any
    week with no data), newest-first. Fetched once and shared across both
    teams' history walks below rather than re-fetched per team."""
    out: list[tuple[int, list[dict]]] = []
    for w in range(week, 0, -1):
        status, rows = await api_post("/league/weekly_leaderboard", {"year": year, "week": w})
        if status != 200:
            break
        ranked = [r for r in rows if r.get("rank") is not None]
        if ranked:
            out.append((w, ranked))
    return out


def _team_history_from_weeks(weeks_desc: list[tuple[int, list[dict]]], team: str, target: str) -> dict:
    """target: "top" (this team holds rank 1) or "bottom" (this team holds
    the worst rank that week). Both a consecutive streak (stops counting
    the moment it breaks, walking backward from the most recent week) and
    a season-total count (keeps counting every earlier week that position
    was held, even after a gap) are computed -- both concepts show up in
    the real historical "Week N Rankings" posts ("third top rank of the
    season" vs. "third week in a row"), left for the prompt to choose
    between. matchup_win_streak/matchup_loss_streak are the team's real
    head-to-head result streak (independent of rank), same "stop at the
    first break" logic -- only one of the two is ever nonzero, since which
    one is active flips permanently the moment the other type appears.
    weekly_rank_history is this team's performance rank for every week
    seen, oldest-first, for describing season-long consistency without a
    rigid pre-computed tier system."""
    rank_streak = rank_total = win_streak = loss_streak = 0
    rank_active = win_active = loss_active = True
    weekly_ranks_desc: list[int] = []

    for _, ranked in weeks_desc:
        row = next((r for r in ranked if r["team"] == team), None)
        if row is None:
            continue
        weekly_ranks_desc.append(row["rank"])

        target_rank = 1 if target == "top" else len(ranked)
        if row["rank"] == target_rank:
            rank_total += 1
            if rank_active:
                rank_streak += 1
        else:
            rank_active = False

        if row.get("matchup_win"):
            if win_active:
                win_streak += 1
            loss_active = False
        elif row.get("matchup_loss"):
            if loss_active:
                loss_streak += 1
            win_active = False
        else:
            win_active = loss_active = False

    return {
        "rank_streak": rank_streak,
        "rank_total": rank_total,
        "matchup_win_streak": win_streak,
        "matchup_loss_streak": loss_streak,
        "weekly_rank_history": list(reversed(weekly_ranks_desc)),
    }


def _passed_teams(team: str, this_week_ranks: dict[str, int], last_week_ranks: dict[str, int]) -> tuple[list[str], list[str]]:
    """Which team(s) `team` passed in the season standings this week (was
    behind last week, now ahead), and which passed `team` (the mirror) --
    from two already-fetched {team: season_rank} snapshots, no extra API
    calls. Empty lists (not an error) if either snapshot is missing this
    team, or on week 1 (no "last week" to compare against)."""
    this_rank = this_week_ranks.get(team)
    last_rank = last_week_ranks.get(team)
    if this_rank is None or last_rank is None:
        return [], []

    passed, passed_by = [], []
    for other, other_last in last_week_ranks.items():
        if other == team:
            continue
        other_now = this_week_ranks.get(other)
        if other_now is None:
            continue
        if other_last < last_rank and other_now > this_rank:
            passed.append(other)
        elif other_last > last_rank and other_now < this_rank:
            passed_by.append(other)
    return passed, passed_by


async def _standings_snapshot(api_post: ApiPost, year: int, week: int) -> dict[str, int]:
    status, standings = await api_post("/league/standings", {"year": year, "min_week": 1, "max_week": week})
    if status != 200:
        return {}
    return {r["team"]: r["rank"] for r in standings.get("wl", [])}


async def _career_facts(api_post: ApiPost, top_team: str, bottom_team: str) -> dict[str, dict]:
    """Career/league-history facts, per the user's explicit request to
    include these (career record, personal-best/-worst streaks, and
    whether an in-progress streak ties or breaks the outright all-time
    league record) -- all read from data that already exists
    (Ref/team_summary.csv via /league/team_summary, and /league/records'
    already-computed cross-team win-streak leaderboard), nothing new
    computed here."""
    status, summary_rows = await api_post("/league/team_summary", {"teams": [top_team, bottom_team]})
    summary_by_team = {r["Team"]: r for r in summary_rows} if status == 200 else {}

    status2, records = await api_post("/league/records", {})
    league_best_win_streak = None
    if status2 == 200:
        streaks = records.get("longest_win_streaks", [])
        if streaks:
            league_best_win_streak = streaks[0]["longest_win_streak"]

    def facts_for(team: str) -> dict:
        row = summary_by_team.get(team, {})
        return {
            "career_record": row.get("Career W/L"),
            "career_best_win_streak": row.get("Best Win Streak"),
            "career_worst_losing_streak": row.get("Worst Losing Streak"),
            "league_record_win_streak": league_best_win_streak,
        }

    return {top_team: facts_for(top_team), bottom_team: facts_for(bottom_team)}


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
    top_team, bottom_team = top["team"], bottom["team"]

    weeks_desc = await _fetch_weeks_desc(api_post, year, week)
    top_hist = _team_history_from_weeks(weeks_desc, top_team, "top")
    bottom_hist = _team_history_from_weeks(weeks_desc, bottom_team, "bottom")

    this_week_ranks = await _standings_snapshot(api_post, year, week)
    last_week_ranks = await _standings_snapshot(api_post, year, week - 1) if week > 1 else {}
    status, standings = await api_post("/league/standings", {"year": year, "min_week": 1, "max_week": week})
    wl_rows = standings.get("wl", []) if status == 200 else []

    career = await _career_facts(api_post, top_team, bottom_team)

    def season_info(team: str) -> dict:
        row = next((r for r in wl_rows if r["team"] == team), None)
        record = f"{row['wins']}-{row['losses']}-{row['ties']}" if row else None
        passed, passed_by = _passed_teams(team, this_week_ranks, last_week_ranks)
        return {
            "season_rank": row["rank"] if row else None,
            "season_rank_last_week": last_week_ranks.get(team),
            "season_record": record,
            "passed_in_standings_this_week": passed,
            "passed_by_in_standings_this_week": passed_by,
        }

    def consistency_info(hist: dict) -> dict:
        history = hist["weekly_rank_history"]
        current = history[-1] if history else None
        return {
            "weekly_rank_history": history,
            "season_best_week_rank": min(history) if history else None,
            "season_worst_week_rank": max(history) if history else None,
            "is_season_best_week_rank": bool(history) and current == min(history),
            "is_season_worst_week_rank": bool(history) and current == max(history),
        }

    def streak_info(hist: dict, career_row: dict) -> dict:
        win_streak = hist["matchup_win_streak"]
        career_best = career_row.get("career_best_win_streak")
        league_best = career_row.get("league_record_win_streak")
        return {
            "matchup_win_streak": win_streak,
            "matchup_loss_streak": hist["matchup_loss_streak"],
            "ties_or_breaks_career_best_win_streak": (
                win_streak > 0 and career_best is not None and win_streak >= career_best
            ),
            "sets_new_league_record_win_streak": (
                win_streak > 0 and league_best is not None and win_streak > league_best
            ),
        }

    return {
        "week": week,
        "top_team": {
            "name": top_team,
            "week_rank": top["rank"],
            "week_rating": top["rating"],
            "top_rank_streak_this_season": top_hist["rank_streak"],
            "top_rank_count_this_season": top_hist["rank_total"],
            "opponent": top["opponent"],
            "matchup_result": _result_label(top),
            **streak_info(top_hist, career[top_team]),
            **consistency_info(top_hist),
            **season_info(top_team),
            **career[top_team],
        },
        "bottom_team": {
            "name": bottom_team,
            "week_rank": bottom["rank"],
            "week_rating": bottom["rating"],
            "bottom_rank_streak_this_season": bottom_hist["rank_streak"],
            "bottom_rank_count_this_season": bottom_hist["rank_total"],
            "opponent": bottom["opponent"],
            "matchup_result": _result_label(bottom),
            **streak_info(bottom_hist, career[bottom_team]),
            **consistency_info(bottom_hist),
            **season_info(bottom_team),
            **career[bottom_team],
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
