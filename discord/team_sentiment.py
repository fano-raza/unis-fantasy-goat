"""Classifies "my team is good/bad" self-assessments in live chat and tallies
them per user, for the /team-mood-check slash command (feature request,
2026-10-19: "can we get a tally on how many times someone on this chat says
their team is bad or good").

The lexicon and flip rules below aren't a generic sentiment analyzer --
they're reverse-engineered from a manual read of every historical message
containing "my team" in #nba_fantasy_general and #rankings (584 messages).
That read showed negative self-talk ("my team is ass/sucks/trash/...") far
outnumbers positive ("nice/good/beast/..."), and that naive keyword matching
on strong-looking words like "good" or "bad" misfires constantly on this
chat's style -- hedges ("isn't really that bad"), backhands ("only good at
3 cats"), subjunctive counterfactuals ("if my team was any good" implies
it currently isn't), and indirect negation ("not like I'm saying my team is
good") all flip the obvious reading. Scanning runs unsupervised on live
chat, so every rule below favors skipping (no tally) over guessing wrong.

Scope (user-confirmed, 2026-10-19): only the possessive "my" (not "our"/
"this"), paired with team/teams/squad/squads/roster -- not a broader
sentiment pass. Tracking is silent (no reaction on the matched message) and
limited to the two channels this lexicon was validated against.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Optional

import disnake

from shared.runtime_config import team_sentiment_tally_csv_path

# #nba_fantasy_general and #rankings -- see discord/weekly_rankings.py for
# the latter's own copy of this id (not imported from there, to keep this
# module standalone the way daily_games.py keeps its own CHANNEL_ID).
TRACKED_CHANNEL_IDS = {975528221934256128, 1029164739558903928}

CSV_FIELDS = ["message_id", "discord_user_id", "channel_id", "timestamp", "polarity", "matched_phrase"]

MY_TEAM_RE = re.compile(r"\bmy\s+(?:team|teams|squad|squads|roster)\b", re.IGNORECASE)

# (pattern, label) -- every entry is a word/phrase actually observed in the
# historical corpus, not a generic sentiment dictionary. Extend only from
# real misses, not guesses, to keep precision high.
POSITIVE_LEXICON: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bnice\b", re.IGNORECASE), "nice"),
    (re.compile(r"\bgood\b", re.IGNORECASE), "good"),
    (re.compile(r"\bbeast(?:ing)?\b", re.IGNORECASE), "beast"),
    (re.compile(r"\bop\b", re.IGNORECASE), "op"),
    (re.compile(r"\bstacked\b", re.IGNORECASE), "stacked"),
    (re.compile(r"\bperfect(?:ly)?\b", re.IGNORECASE), "perfect"),
    (re.compile(r"\bfire\b", re.IGNORECASE), "fire"),
    (re.compile(r"\bdominating\b", re.IGNORECASE), "dominating"),
    (re.compile(r"\bso back\b", re.IGNORECASE), "so back"),
    (re.compile(r"\b(?:going|went) off\b", re.IGNORECASE), "going off"),
    (re.compile(r"\bgoing well\b", re.IGNORECASE), "going well"),
    (re.compile(r"\btop 10 in the league\b", re.IGNORECASE), "top 10 in the league"),
    (re.compile(r"\bunparalleled\b", re.IGNORECASE), "unparalleled"),
    (re.compile(r"\bmvp\b", re.IGNORECASE), "mvp"),
    (re.compile(r"\bfinding its rhythm\b", re.IGNORECASE), "finding its rhythm"),
    (re.compile(r"\bdoing (?:so )?hot\b", re.IGNORECASE), "doing hot"),
    (re.compile(r"\bbest\b", re.IGNORECASE), "best"),
    (re.compile(r"\bbetter than\b", re.IGNORECASE), "better than"),
]

NEGATIVE_LEXICON: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bnot as good as\b", re.IGNORECASE), "not as good as"),
    (re.compile(r"\bworse than\b", re.IGNORECASE), "worse than"),
    (re.compile(r"\bass\b", re.IGNORECASE), "ass"),
    (re.compile(r"\bsucks?\b", re.IGNORECASE), "sucks"),
    (re.compile(r"\bbad\b", re.IGNORECASE), "bad"),
    (re.compile(r"\bstinks?\b", re.IGNORECASE), "stinks"),
    (re.compile(r"\bshitting the bed\b", re.IGNORECASE), "shitting the bed"),
    (re.compile(r"\bshit\b", re.IGNORECASE), "shit"),
    (re.compile(r"\bshite\b", re.IGNORECASE), "shite"),
    (re.compile(r"\bwhack\b", re.IGNORECASE), "whack"),
    (re.compile(r"\bdoo doo(?: butt)?\b", re.IGNORECASE), "doo doo"),
    (re.compile(r"\bbooty cheeks\b", re.IGNORECASE), "booty cheeks"),
    (re.compile(r"\bgarbage\b", re.IGNORECASE), "garbage"),
    (re.compile(r"\btrash\b", re.IGNORECASE), "trash"),
    (re.compile(r"\bbuns\b", re.IGNORECASE), "buns"),
    (re.compile(r"\bin shambles\b", re.IGNORECASE), "in shambles"),
    (re.compile(r"\bfalling apart\b", re.IGNORECASE), "falling apart"),
    (re.compile(r"\bimploding\b", re.IGNORECASE), "imploding"),
    (re.compile(r"\bdonezo\b", re.IGNORECASE), "donezo"),
    (re.compile(r"\bmid\b", re.IGNORECASE), "mid"),
    (re.compile(r"\bmediocre\b", re.IGNORECASE), "mediocre"),
    (re.compile(r"\bterrible\b", re.IGNORECASE), "terrible"),
    (re.compile(r"\batrocious\b", re.IGNORECASE), "atrocious"),
    (re.compile(r"\bscrubs\b", re.IGNORECASE), "scrubs"),
    (re.compile(r"\bnobodies\b", re.IGNORECASE), "nobodies"),
    (re.compile(r"\bcursed\b", re.IGNORECASE), "cursed"),
    (re.compile(r"\bunfixable\b", re.IGNORECASE), "unfixable"),
    (re.compile(r"\bpoo+\s?poo\b", re.IGNORECASE), "poopoo"),
    (re.compile(r"\bdisappointment\b", re.IGNORECASE), "disappointment"),
    (re.compile(r"\bgoing (?:down the drain|to shit)\b", re.IGNORECASE), "going down the drain"),
    (re.compile(r"\bwalking injury\b", re.IGNORECASE), "walking injury"),
]

# Discord content commonly uses a typographic apostrophe (U+2019, "'")
# instead of ASCII "'" -- mobile keyboards autocorrect to it by default.
# Every contraction below has to match both, or negation silently misses
# on the majority of real messages (confirmed: 117/584 of the historical
# corpus use "'", only 36 use ASCII "'").
_APOS = "['’]?"
_NEGATOR_RE = re.compile(
    rf"\b(?:not|isn{_APOS}t|ain{_APOS}t|wasn{_APOS}t|weren{_APOS}t|never|no way|far from)\b", re.IGNORECASE
)
_LIMITER_RE = re.compile(r"\b(?:only|just|barely)\b", re.IGNORECASE)
# "could be good but it probably isn't" -- a trailing "but ... isn't/can't/
# doesn't" past the matched word cancels a positive reading.
_BUT_CANCEL_RE = re.compile(
    rf"\bbut\b.{{0,20}}?\b(?:isn{_APOS}t|doesn{_APOS}t|can{_APOS}t|won{_APOS}t)\b", re.IGNORECASE
)
# "it's not like I'm even saying my team is good" -- the "not" is nowhere
# near "good" itself, it negates the whole claim from outside.
_INDIRECT_NEGATION_RE = re.compile(r"\bnot like\b.{0,40}?\b(?:saying|claiming)\b", re.IGNORECASE)
_HAS_IF_RE = re.compile(r"\bif\b", re.IGNORECASE)
_LEADING_VERB_RE = re.compile(rf"\s*(?:{_APOS}s)\b|\s*\b(was|were|is|are)\b", re.IGNORECASE)
# "can you say a good thing about my team" -- a request for a compliment,
# not a claim that the team actually is good.
_COMPLIMENT_FISHING_RE = re.compile(
    r"\b(?:say|tell|name)\b.{0,20}?\b(?:good|nice|positive)\b.{0,15}?\bthing\b.{0,15}?\babout\s*$",
    re.IGNORECASE,
)

_ALL_LEXICON = [(p, "positive", label) for p, label in POSITIVE_LEXICON] + [
    (p, "negative", label) for p, label in NEGATIVE_LEXICON
]


def _sentence_bounds(content: str, pos: int) -> tuple[int, int]:
    start = 0
    for m in re.finditer(r"[.!?\n]", content[:pos]):
        start = m.end()
    end_match = re.search(r"[.!?\n]", content[pos:])
    end = pos + end_match.start() if end_match else len(content)
    return start, end


def _classify_occurrence(content: str, match: re.Match) -> Optional[tuple[str, str]]:
    sent_start, sent_end = _sentence_bounds(content, match.start())
    is_question = sent_end < len(content) and content[sent_end] == "?"
    before_text = content[sent_start : match.start()]
    after_text = content[match.end() : sent_end]

    if is_question or _COMPLIMENT_FISHING_RE.search(before_text):
        return None

    best: Optional[tuple[int, str, str, re.Match]] = None
    for pattern, polarity, label in _ALL_LEXICON:
        m = pattern.search(after_text)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), polarity, label, m)
    if best is None:
        return None
    _, polarity, label, m = best

    pre_word = after_text[: m.start()]
    post_word = after_text[m.end() :]
    has_negator = bool(_NEGATOR_RE.search(pre_word))
    has_limiter = bool(_LIMITER_RE.search(pre_word))
    has_but_cancel = bool(_BUT_CANCEL_RE.search(post_word))

    if polarity == "positive" and (has_negator or has_limiter or has_but_cancel):
        polarity = "negative"
    elif polarity == "negative" and has_negator:
        polarity = "positive"

    if polarity == "positive" and _INDIRECT_NEGATION_RE.search(before_text):
        polarity = "negative"

    if polarity == "positive" and _HAS_IF_RE.search(before_text):
        verb_m = _LEADING_VERB_RE.match(after_text)
        if verb_m and verb_m.group(1) and verb_m.group(1).lower() in ("was", "were"):
            polarity = "negative"

    return polarity, label


def classify_message(content: str) -> Optional[tuple[str, str]]:
    """Returns (polarity, matched_phrase) for the first "my team"-style
    mention in content that resolves to a confident good/bad self-assessment,
    or None if there isn't one (most "my team" mentions are informational,
    not a sentiment claim -- see module docstring)."""
    for match in MY_TEAM_RE.finditer(content):
        result = _classify_occurrence(content, match)
        if result is not None:
            return result
    return None


def _ensure_csv(path: Path) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=CSV_FIELDS).writeheader()


def _record(message: disnake.Message, polarity: str, matched_phrase: str) -> None:
    path = team_sentiment_tally_csv_path()
    _ensure_csv(path)
    with path.open("a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=CSV_FIELDS).writerow(
            {
                "message_id": message.id,
                "discord_user_id": message.author.id,
                "channel_id": message.channel.id,
                "timestamp": message.created_at.isoformat(),
                "polarity": polarity,
                "matched_phrase": matched_phrase,
            }
        )


async def maybe_record(message: disnake.Message) -> Optional[str]:
    """Classifies and persists message if it's a team self-assessment in a
    tracked channel. Returns the polarity if one was tallied, else None.
    Never raises -- a scan miss shouldn't take down on_message."""
    if message.channel.id not in TRACKED_CHANNEL_IDS:
        return None
    try:
        result = classify_message(message.content)
        if result is None:
            return None
        polarity, matched_phrase = result
        _record(message, polarity, matched_phrase)
        return polarity
    except Exception as exc:
        print(f"team_sentiment scan failed for message {message.id}: {exc}")
        return None


def _load_rows() -> list[dict]:
    path = team_sentiment_tally_csv_path()
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def user_counts(discord_user_id: str) -> tuple[int, int]:
    """(positive_count, negative_count) for one user."""
    pos = neg = 0
    for row in _load_rows():
        if row["discord_user_id"] != discord_user_id:
            continue
        if row["polarity"] == "positive":
            pos += 1
        elif row["polarity"] == "negative":
            neg += 1
    return pos, neg


def leaderboard(polarity: str, limit: int = 10) -> list[tuple[str, int]]:
    """[(discord_user_id, count), ...] for the given polarity, sorted
    highest-count first."""
    counts: dict[str, int] = {}
    for row in _load_rows():
        if row["polarity"] != polarity:
            continue
        counts[row["discord_user_id"]] = counts.get(row["discord_user_id"], 0) + 1
    return sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:limit]
