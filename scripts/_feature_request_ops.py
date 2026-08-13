"""Shared plumbing for scripts/mark_feature_request_*.py -- parsing/
rendering feature_requests.md's section structure, and reacting to a
logged request's original Discord message. Not meant to be run directly;
see mark_feature_request_done.py/_in_progress.py/_rejected.py for the
actual CLI entry points.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from discord.bot_env import load_local_env  # noqa: E402
from discord.feature_bot import IN_PROGRESS_REACTION, parse_discord_ref  # noqa: E402
from shared.runtime_config import feature_requests_path  # noqa: E402

OPEN_HEADER = "## Open"


def parse(text: str) -> tuple[str, list[tuple[str, list[str]]]]:
    """Returns (preamble, sections): preamble is everything before the first
    "## " header (the "# Feature Requests" title line), and each section is
    (header, content_lines) with blank separator lines stripped out --
    render() always re-emits exactly one blank line between blocks, so
    editing never has to preserve exact original blank-line placement."""
    sections: list[tuple[str, list[str]]] = []
    preamble_lines: list[str] = []
    header: str | None = None
    lines: list[str] = []
    for raw in text.splitlines():
        if raw.startswith("## "):
            if header is not None:
                sections.append((header, [l for l in lines if l.strip()]))
            else:
                preamble_lines = [l for l in lines if l.strip()]
            header = raw
            lines = []
        else:
            lines.append(raw)
    if header is not None:
        sections.append((header, [l for l in lines if l.strip()]))
    return "\n".join(preamble_lines), sections


def render(preamble: str, sections: list[tuple[str, list[str]]]) -> str:
    blocks = [preamble] if preamble else []
    for header, lines in sections:
        blocks.append(header + ("\n" + "\n".join(lines) if lines else ""))
    return "\n\n".join(blocks) + "\n"


def react(channel_id: int, message_id: int, emoji: str, token: str) -> None:
    import requests

    encoded = quote(emoji)
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}/reactions/{encoded}/@me"
    resp = requests.put(url, headers={"Authorization": f"Bot {token}"}, timeout=10)
    resp.raise_for_status()


def unreact(channel_id: int, message_id: int, emoji: str, token: str) -> None:
    """Removes the bot's own reaction -- same endpoint as react(), DELETE
    instead of PUT. A 404 here just means the bot never reacted with this
    emoji on this message (e.g. a request marked Done without ever having
    been marked in-progress first), which is a normal case, not an error."""
    import requests

    encoded = quote(emoji)
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}/reactions/{encoded}/@me"
    resp = requests.delete(url, headers={"Authorization": f"Bot {token}"}, timeout=10)
    if resp.status_code == 404:
        return
    resp.raise_for_status()


def find_single_open_match(
    sections: list[tuple[str, list[str]]], substring: str
) -> tuple[int, int, str] | None:
    """Finds the one line in the "## Open" section containing `substring`
    (case-insensitive). Prints and returns None on zero or multiple
    matches -- ambiguity here should stop the caller, not guess."""
    matches: list[tuple[int, int, str]] = []
    for si, (header, lines) in enumerate(sections):
        if header != OPEN_HEADER:
            continue
        for li, line in enumerate(lines):
            if substring.lower() in line.lower():
                matches.append((si, li, line))

    if not matches:
        print(f'No open request matching "{substring}" found.')
        return None
    if len(matches) > 1:
        print(f'{len(matches)} open requests match "{substring}" -- be more specific:')
        for _, _, line in matches:
            print(f"  {line.strip()}")
        return None
    return matches[0]


def _resolve_ref_and_token(line: str, verbose: bool = True) -> tuple[int, int, str] | None:
    ref = parse_discord_ref(line)
    if not ref:
        if verbose:
            print("No stored Discord message reference on this line -- can't react (logged before this feature existed).")
        return None

    load_local_env()
    token = os.getenv("FEATURE_BOT_TOKEN")
    if not token:
        if verbose:
            print("FEATURE_BOT_TOKEN not set -- couldn't react.")
        return None

    channel_id, message_id = ref
    return channel_id, message_id, token


def react_to_line(line: str, emoji: str, label: str) -> None:
    """Reacts to a logged line's original Discord message, if it has one
    (requests logged before message-ref tracking existed have no reference
    and simply can't be reacted to -- not an error)."""
    resolved = _resolve_ref_and_token(line)
    if resolved is None:
        return
    channel_id, message_id, token = resolved
    try:
        react(channel_id, message_id, emoji, token)
        print(f"Reacted {emoji} to the original message (channel={channel_id}, message={message_id}).")
    except Exception as exc:
        print(f"Failed to react: {exc}")


def unreact_to_line(line: str, emoji: str) -> None:
    """Removes a previously-added reaction (e.g. the 🚧 in-progress marker
    once a request reaches a resolved outcome) from a logged line's
    original Discord message, if it has one. Silent no-op if there's no
    stored reference or no token -- this is always a secondary cleanup
    step alongside react_to_line, which already reports those cases."""
    resolved = _resolve_ref_and_token(line, verbose=False)
    if resolved is None:
        return
    channel_id, message_id, token = resolved
    try:
        unreact(channel_id, message_id, emoji, token)
    except Exception as exc:
        print(f"Failed to remove {emoji} reaction: {exc}")


def react_only(substring: str, emoji: str, label: str) -> None:
    """For transient status signals (e.g. "in progress") that aren't a
    resolved outcome -- reacts to the original message but leaves the line
    in "## Open" untouched (still unchecked, still open)."""
    path = feature_requests_path()
    match = find_single_open_match(parse(path.read_text())[1], substring)
    if match is None:
        return
    _, _, line = match
    react_to_line(line, emoji, label)


def move_and_react(substring: str, target_header: str, emoji: str, label: str) -> None:
    """For resolved outcomes (done, rejected) -- moves the matching line
    from "## Open" to target_header (created at the end of the file if it
    doesn't exist yet), ticking its checkbox, then reacts to the original
    message."""
    path = feature_requests_path()
    preamble, sections = parse(path.read_text())
    match = find_single_open_match(sections, substring)
    if match is None:
        return
    si, li, line = match

    sections[si] = (sections[si][0], [l for i, l in enumerate(sections[si][1]) if i != li])
    moved_line = line.replace("- [ ]", "- [x]", 1)
    for i, (header, lines) in enumerate(sections):
        if header == target_header:
            sections[i] = (header, lines + [moved_line])
            break
    else:
        sections.append((target_header, [moved_line]))

    path.write_text(render(preamble, sections))
    print(f"Moved to {target_header.removeprefix('## ')}: {moved_line.strip()}")
    # A resolved outcome (Done or Rejected) supersedes "in progress" -- clear
    # that marker so a shipped/declined request doesn't still show 🚧.
    unreact_to_line(moved_line, IN_PROGRESS_REACTION)
    react_to_line(moved_line, emoji, label)
