"""Parses and persists #daily-games score posts (MapTap, Worldle, Flagle,
WhenTaken, Travle). Share-text formats were confirmed against real channel
history, not documentation -- see each regex's comment for the exact sample
that justified it (formats have drifted over time, e.g. Worldle's early
2023 posts didn't include the "(date)" field later posts have).

Storage: one row per game-play, appended to daily_games_history.csv
(shared.runtime_config.daily_games_history_path()). Scans are incremental --
daily_games_cursor_path() stores the last-processed message id so a daily
refresh only walks new messages, not the whole channel (currently ~2900
messages and growing) each time. First-ever call has no cursor, so it
naturally does a full backfill.
"""

from __future__ import annotations

import csv
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import disnake

from shared.runtime_config import (
    daily_games_cursor_path,
    daily_games_history_path,
    daily_games_last_synced_at_path,
)

CHANNEL_ID = 1142189924544696321
DISCORD_NAMES_CSV = Path(__file__).resolve().parent / "discord_names.csv"

# How stale the last scan can be before a leaderboard command triggers a
# fresh one itself, instead of relying solely on the hourly/4am loop.
FRESHNESS_WINDOW = timedelta(minutes=10)

CSV_FIELDS = ["message_id", "discord_user_id", "game", "date", "timestamp", "score", "solved"]

# "www.maptap.gg July 15\n98\U0001f525 94\U0001f3c5 58\U0001f92b 93\U0001f3c6 90\U0001f451\nFinal score: 857"
# -- deliberately requires "<Month> <day>" right after the bare domain, NOT
# just "www.maptap.gg" anywhere in the message: custom/community maps share
# the same "Final score: N" line but use a path instead, e.g.
# "www.maptap.gg/m/the-disasters-history-forgot-kyllh4" or
# "www.maptap.gg/@jwlc/names-that-mean-new-city" -- those aren't the daily
# challenge and would otherwise inflate games-played (confirmed against
# real channel history: 21 such posts in the most recent 14 days alone).
# No year in the text -- combined with the message's own post year below.
_MAPTAP_MONTH_NAMES = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)
_MAPTAP_MONTH_NUM = {name: i + 1 for i, name in enumerate(_MAPTAP_MONTH_NAMES)}
MAPTAP_MARKER = re.compile(
    rf"www\.maptap\.gg\s+({'|'.join(_MAPTAP_MONTH_NAMES)})\s+(\d{{1,2}})", re.IGNORECASE
)
MAPTAP_SCORE_RE = re.compile(r"final score:\s*([\d,]+)", re.IGNORECASE)

# "#Worldle #1673 (21.08.2026) 3/6 (100%)" -- the "(date)" group is optional:
# the earliest (2023-08-18) posts were "#Worldle #574 6/6 (100%)", no date.
WORLDLE_MARKER_RE = re.compile(r"#Worldle\b", re.IGNORECASE)
WORLDLE_RE = re.compile(
    r"#Worldle\s+#\d+\s*(?:\((\d{1,2}\.\d{1,2}\.\d{4})\)\s*)?(\d|X)/6(?:\s*\((\d+)%\))?", re.IGNORECASE
)

# "#Flagle #1642 (21.08.2026) 3/6" -- same shape as Worldle, no "(NN%)".
FLAGLE_MARKER_RE = re.compile(r"#Flagle\b", re.IGNORECASE)
FLAGLE_RE = re.compile(r"#Flagle\s+#\d+\s*(?:\((\d{1,2}\.\d{1,2}\.\d{4})\)\s*)?(\d|X)/6", re.IGNORECASE)

# "#WhenTaken #906 (21.08.2026)\n\nI scored 669/1000\U0001f397️\n..."
WHENTAKEN_MARKER_RE = re.compile(r"#WhenTaken\b", re.IGNORECASE)
WHENTAKEN_DATE_RE = re.compile(r"#WhenTaken\s+#\d+\s*\((\d{1,2}\.\d{1,2}\.\d{4})\)", re.IGNORECASE)
WHENTAKEN_SCORE_RE = re.compile(r"scored\s+(\d+)\s*/\s*1000", re.IGNORECASE)

# "#travle #1346 +1" (solved, 1 extra guess over par) / "#travle #1346 -2
# (Super Perfect)" (beat par -- negative is a real, better-than-0 result) /
# "#travle #1346 (1 away) (1 hint)" (didn't finish). No date in the text --
# always falls back to the message's own post date.
TRAVLE_MARKER_RE = re.compile(r"#travle\b", re.IGNORECASE)
TRAVLE_SOLVED_RE = re.compile(r"#travle\s+#\d+\s*([+-]\d+)", re.IGNORECASE)
TRAVLE_AWAY_RE = re.compile(r"#travle\s+#\d+\s*\(\d+\s*away\)", re.IGNORECASE)


def _parse_ddmmyyyy(raw: str) -> Optional[date]:
    day_s, month_s, year_s = raw.split(".")
    try:
        return date(int(year_s), int(month_s), int(day_s))
    except ValueError:
        return None

GAMES = ("maptap", "worldle", "flagle", "whentaken", "travle")
GAME_LABELS = {
    "maptap": "MapTap",
    "worldle": "Worldle",
    "flagle": "Flagle",
    "whentaken": "WhenTaken",
    "travle": "Travle",
}
# True = lower average is better (guess count / extra guesses over par).
# False = higher average is better (score out of 1000).
LOWER_IS_BETTER = {
    "maptap": False,
    "worldle": True,
    "flagle": True,
    "whentaken": False,
    "travle": True,
}
# True = the game has a fail state (Worldle/Flagle "X/6", Travle "(N away)"),
# so a play can be incomplete. MapTap and WhenTaken only ever post a score --
# there's no failure format for either -- so every play is complete.
CAN_BE_INCOMPLETE = {
    "maptap": False,
    "worldle": True,
    "flagle": True,
    "whentaken": False,
    "travle": True,
}
DEFAULT_DAYS_BACK = 7


def parse_message(content: str, posted_date: date) -> list[tuple[str, Optional[float], bool, Optional[date]]]:
    """(game, score, solved, explicit_date) for every game marker found in
    a message. score is None for a failed/incomplete play (still counts as
    a game played -- solved=False); normally 0 or 1 result per message.
    explicit_date is the puzzle date parsed out of the message text itself
    (Worldle/Flagle/WhenTaken carry a full DD.MM.YYYY; MapTap carries
    "<Month> <day>" with no year, so posted_date's year fills the gap --
    except right at a year boundary (posted in January about a December
    puzzle), where posted_date's year would be off by one; Travle carries
    no date at all) -- None means "fall back to the message's own post
    date", which the caller (scan_and_record) does."""
    results: list[tuple[str, Optional[float], bool, Optional[date]]] = []

    m = MAPTAP_MARKER.search(content)
    if m:
        score_m = MAPTAP_SCORE_RE.search(content)
        if score_m:
            month_num = _MAPTAP_MONTH_NUM[m.group(1).lower()]
            year = posted_date.year
            # Year-boundary corrections -- the puzzle text has no year, so
            # posted_date.year is only right if both dates fall in the same
            # calendar year. Two ways they can disagree, both real: a
            # December puzzle posted after UTC has already rolled to
            # January (year -= 1), or -- the mirror case -- a January
            # puzzle for a poster far enough ahead of UTC (e.g. UTC+13)
            # that their local Jan 1 lands while UTC still reads Dec 31
            # (year += 1).
            if month_num == 12 and posted_date.month == 1:
                year -= 1
            elif month_num == 1 and posted_date.month == 12:
                year += 1
            try:
                explicit_date = date(year, month_num, int(m.group(2)))
            except ValueError:
                explicit_date = None
            results.append(("maptap", float(score_m.group(1).replace(",", "")), True, explicit_date))

    if WORLDLE_MARKER_RE.search(content):
        m = WORLDLE_RE.search(content)
        if m:
            failed = m.group(2).upper() == "X"
            explicit_date = _parse_ddmmyyyy(m.group(1)) if m.group(1) else None
            results.append(("worldle", None if failed else float(m.group(2)), not failed, explicit_date))

    if FLAGLE_MARKER_RE.search(content):
        m = FLAGLE_RE.search(content)
        if m:
            failed = m.group(2).upper() == "X"
            explicit_date = _parse_ddmmyyyy(m.group(1)) if m.group(1) else None
            results.append(("flagle", None if failed else float(m.group(2)), not failed, explicit_date))

    if WHENTAKEN_MARKER_RE.search(content):
        m = WHENTAKEN_SCORE_RE.search(content)
        if m:
            date_m = WHENTAKEN_DATE_RE.search(content)
            explicit_date = _parse_ddmmyyyy(date_m.group(1)) if date_m else None
            results.append(("whentaken", float(m.group(1)), True, explicit_date))

    if TRAVLE_MARKER_RE.search(content):
        m = TRAVLE_SOLVED_RE.search(content)
        if m:
            results.append(("travle", float(m.group(1)), True, None))
        elif TRAVLE_AWAY_RE.search(content):
            results.append(("travle", None, False, None))

    return results


def _read_cursor() -> Optional[int]:
    path = daily_games_cursor_path()
    if not path.exists():
        return None
    try:
        return int(path.read_text().strip())
    except (ValueError, OSError):
        return None


def _write_cursor(message_id: int) -> None:
    path = daily_games_cursor_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(message_id))


def read_last_synced_at() -> Optional[datetime]:
    """UTC timestamp of the last successful scan_and_record() call, or None
    if it's never run."""
    path = daily_games_last_synced_at_path()
    if not path.exists():
        return None
    try:
        return datetime.fromisoformat(path.read_text().strip())
    except (ValueError, OSError):
        return None


def _write_last_synced_at(when: datetime) -> None:
    path = daily_games_last_synced_at_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(when.isoformat())


def _ensure_csv(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=CSV_FIELDS).writeheader()


async def scan_and_record(channel: disnake.abc.Messageable) -> int:
    """Scans for new score posts since the last recorded message id and
    appends them to daily_games_history.csv. Returns rows added. Safe to
    call repeatedly -- incremental after the first (full-backfill) call."""
    cursor = _read_cursor()
    after = disnake.Object(id=cursor) if cursor else None

    csv_path = daily_games_history_path()
    _ensure_csv(csv_path)

    new_rows: list[dict] = []
    last_seen_id = cursor

    async for message in channel.history(limit=None, after=after, oldest_first=True):
        last_seen_id = message.id
        posted_date = message.created_at.date()
        for game, score, solved, explicit_date in parse_message(message.content, posted_date):
            new_rows.append(
                {
                    "message_id": message.id,
                    "discord_user_id": message.author.id,
                    "game": game,
                    "date": (explicit_date or posted_date).isoformat(),
                    "timestamp": message.created_at.isoformat(),
                    "score": "" if score is None else score,
                    "solved": int(solved),
                }
            )

    if new_rows:
        with csv_path.open("a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=CSV_FIELDS).writerows(new_rows)

    if last_seen_id is not None:
        _write_cursor(last_seen_id)

    _write_last_synced_at(datetime.now(timezone.utc))

    return len(new_rows)


async def ensure_fresh(channel: disnake.abc.Messageable) -> datetime:
    """Scans for new #daily-games posts only if the last scan is missing or
    older than FRESHNESS_WINDOW -- called from leaderboard commands so they
    stay reasonably live without re-scanning the channel on every call (the
    4am/hourly loop in stat_bot.py still runs independently of this).
    Returns the resulting last-synced-at UTC timestamp, for display."""
    last_synced = read_last_synced_at()
    now = datetime.now(timezone.utc)
    if last_synced is None or now - last_synced > FRESHNESS_WINDOW:
        await scan_and_record(channel)
        return read_last_synced_at() or now
    return last_synced


def parse_days_arg(raw: Optional[str]) -> tuple[Optional[int], str]:
    """Returns (days_back, human label). days_back is None for "ever"
    (no date cutoff -- full history), otherwise a positive int. Raises
    ValueError on unparseable input, message meant to be shown to the user."""
    if raw is None or not raw.strip():
        return DEFAULT_DAYS_BACK, f"last {DEFAULT_DAYS_BACK} days"
    val = raw.strip()
    if val.lower() == "ever":
        return None, "all-time"
    try:
        n = int(val)
    except ValueError:
        raise ValueError(f'Invalid value "{raw}" -- use a number of days, or "ever" for all-time.')
    if n <= 0:
        raise ValueError("Days must be a positive number.")
    return n, f"last {n} day{'s' if n != 1 else ''}"


def load_history_rows(game: str) -> list[dict]:
    path = daily_games_history_path()
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return [row for row in csv.DictReader(f) if row["game"] == game]


def build_leaderboard(game: str, days_back: Optional[int]) -> list[dict]:
    """[{uid, gp, complete, incomplete, avg}], sorted best-first per the
    game's lower/higher-is-better convention. gp = complete + incomplete
    (total games played). avg is over complete plays only -- None (and
    sorted last) if the user has zero complete plays in range, even if
    incomplete > 0."""
    rows = load_history_rows(game)
    if days_back is not None:
        # Calendar-date arithmetic, not a raw timestamp subtraction: `date`
        # has no time-of-day, so `(now - N days).date()` would include
        # today (already partially elapsed) PLUS N full prior days -- N+1
        # distinct dates, not N. today - (days_back - 1) gives exactly
        # days_back distinct calendar dates ending today.
        cutoff = datetime.now(timezone.utc).date() - timedelta(days=days_back - 1)
        rows = [r for r in rows if date.fromisoformat(r["date"]) >= cutoff]

    by_uid: dict[int, list[Optional[float]]] = {}
    for r in rows:
        uid = int(r["discord_user_id"])
        score = float(r["score"]) if r["score"] not in ("", None) else None
        by_uid.setdefault(uid, []).append(score)

    lower_better = LOWER_IS_BETTER[game]
    result = []
    for uid, scores in by_uid.items():
        solved = [s for s in scores if s is not None]
        avg = sum(solved) / len(solved) if solved else None
        result.append(
            {
                "uid": uid,
                "gp": len(scores),
                "complete": len(solved),
                "incomplete": len(scores) - len(solved),
                "avg": avg,
            }
        )

    def sort_key(item: dict):
        if item["avg"] is None:
            return (1, 0.0)
        return (0, item["avg"] if lower_better else -item["avg"])

    result.sort(key=sort_key)
    return result


def load_display_names() -> dict[str, str]:
    """discord_user_id (str) -> team name, or display_name for users not
    linked to a fantasy team (e.g. daily-games-only players). Unlike
    stat_bot.py's _load_user_team_maps(), this does NOT skip rows with no
    team -- every #daily-games player should show up on a leaderboard."""
    names: dict[str, str] = {}
    if not DISCORD_NAMES_CSV.exists():
        return names
    with DISCORD_NAMES_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            uid = str(row.get("discord_user_id") or "").strip()
            if not uid:
                continue
            team = (row.get("team") or "").strip()
            display = (row.get("display_name") or "").strip()
            if team or display:
                names[uid] = team or display
    return names
