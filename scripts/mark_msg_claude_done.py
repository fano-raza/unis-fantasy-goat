"""Moves a matching line in msg_claude.md from "## Open" to "## Done", and
-- if the line carries a stored Discord message reference -- reacts to
the original message with ✅ (white_check_mark) so the reply is visible
in Discord, not just in the file. Same shape as
mark_feature_request_done.py, just pointed at msg_claude.md.

Used by "Discord Mode" (see this repo's CLAUDE.md) to check off a chat
message once Claude has responded to it.

Usage: python scripts/mark_msg_claude_done.py "<substring to match>"

Run this on the droplet (needs FEATURE_BOT_TOKEN + network access to
Discord's API) -- e.g.:
  ssh root@134.209.168.108 "docker compose -f /opt/unisFantasyGOAT/infra/docker/docker-compose.yml exec -T feature-bot python scripts/mark_msg_claude_done.py '<substring>'"
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from discord.feature_bot import COMPLETED_REACTION  # noqa: E402
from scripts._feature_request_ops import move_and_react  # noqa: E402
from shared.runtime_config import msg_claude_path  # noqa: E402

DONE_HEADER = "## Done"


def mark_done(substring: str) -> None:
    move_and_react(msg_claude_path(), substring, DONE_HEADER, COMPLETED_REACTION, "Done")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('Usage: python scripts/mark_msg_claude_done.py "<substring to match>"')
        sys.exit(1)
    mark_done(sys.argv[1])
