"""Moves a matching line in feature_requests.md from "## Open" to "## Done",
and -- if the line carries a stored Discord message reference (see
discord/feature_bot.py's docstring) -- reacts to the original message with
✅ (white_check_mark) so the completion is visible in Discord, not just in
the file.

Requests logged before message-ref tracking existed have no reference and
simply get moved with no reaction (not an error).

Usage: python scripts/mark_feature_request_done.py "<substring to match>"

Run this on the droplet (needs FEATURE_BOT_TOKEN + network access to
Discord's API) -- e.g.:
  ssh root@134.209.168.108 "docker compose -f /opt/unisFantasyGOAT/infra/docker/docker-compose.yml exec -T feature-bot python scripts/mark_feature_request_done.py '<substring>'"
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from discord.bot_env import load_local_env  # noqa: E402
from discord.feature_bot import COMPLETED_REACTION, parse_discord_ref  # noqa: E402
from shared.runtime_config import feature_requests_path  # noqa: E402

OPEN_HEADER = "## Open"
DONE_HEADER = "## Done"


def _parse(text: str) -> tuple[str, list[tuple[str, list[str]]]]:
    """Returns (preamble, sections): preamble is everything before the first
    "## " header (the "# Feature Requests" title line), and each section is
    (header, content_lines) with blank separator lines stripped out --
    _render always re-emits exactly one blank line between blocks, so
    editing never has to preserve exact original blank-line placement (that
    mismatch was a real bug caught in testing: appending a new line after an
    already-included trailing blank separator left a gap between it and the
    line before it)."""
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


def _render(preamble: str, sections: list[tuple[str, list[str]]]) -> str:
    blocks = [preamble] if preamble else []
    for header, lines in sections:
        blocks.append(header + ("\n" + "\n".join(lines) if lines else ""))
    return "\n\n".join(blocks) + "\n"


def _react(channel_id: int, message_id: int, token: str) -> None:
    import requests

    emoji = quote(COMPLETED_REACTION)
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}/reactions/{emoji}/@me"
    resp = requests.put(url, headers={"Authorization": f"Bot {token}"}, timeout=10)
    resp.raise_for_status()


def mark_done(substring: str) -> None:
    import os

    path = feature_requests_path()
    preamble, sections = _parse(path.read_text())

    matches: list[tuple[int, int, str]] = []  # (section_idx, line_idx, line)
    for si, (header, lines) in enumerate(sections):
        if header != OPEN_HEADER:
            continue
        for li, line in enumerate(lines):
            if substring.lower() in line.lower():
                matches.append((si, li, line))

    if not matches:
        print(f'No open request matching "{substring}" found.')
        return
    if len(matches) > 1:
        print(f'{len(matches)} open requests match "{substring}" -- be more specific:')
        for _, _, line in matches:
            print(f"  {line.strip()}")
        return

    si, li, line = matches[0]
    sections[si] = (sections[si][0], [l for i, l in enumerate(sections[si][1]) if i != li])

    done_line = line.replace("- [ ]", "- [x]", 1)
    for i, (header, lines) in enumerate(sections):
        if header == DONE_HEADER:
            sections[i] = (header, lines + [done_line])
            break
    else:
        sections.append((DONE_HEADER, [done_line]))

    path.write_text(_render(preamble, sections))

    print(f"Moved to Done: {done_line.strip()}")

    ref = parse_discord_ref(line)
    if not ref:
        print("No stored Discord message reference on this line -- can't react (logged before this feature existed).")
        return

    load_local_env()
    token = os.getenv("FEATURE_BOT_TOKEN")
    if not token:
        print("FEATURE_BOT_TOKEN not set -- moved the line but couldn't react.")
        return

    channel_id, message_id = ref
    try:
        _react(channel_id, message_id, token)
        print(f"Reacted {COMPLETED_REACTION} to the original message (channel={channel_id}, message={message_id}).")
    except Exception as exc:
        print(f"Moved the line but failed to react: {exc}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('Usage: python scripts/mark_feature_request_done.py "<substring to match>"')
        sys.exit(1)
    mark_done(sys.argv[1])
