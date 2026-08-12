"""Moves a matching line in feature_requests.md from "## Open" to
"## Ignored" (the existing catch-all for requests that won't be pursued --
test messages and genuinely-declined asks alike), and -- if the line
carries a stored Discord message reference -- reacts to the original
message with ❌ (cross mark) so the rejection is visible in Discord, not
just in the file.

Usage: python scripts/mark_feature_request_rejected.py "<substring to match>"

Run this on the droplet (needs FEATURE_BOT_TOKEN + network access to
Discord's API) -- e.g.:
  ssh root@134.209.168.108 "docker compose -f /opt/unisFantasyGOAT/infra/docker/docker-compose.yml exec -T feature-bot python scripts/mark_feature_request_rejected.py '<substring>'"
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from discord.feature_bot import REJECTED_REACTION  # noqa: E402
from scripts._feature_request_ops import move_and_react  # noqa: E402

IGNORED_HEADER = "## Ignored"


def mark_rejected(substring: str) -> None:
    move_and_react(substring, IGNORED_HEADER, REJECTED_REACTION, "Rejected")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('Usage: python scripts/mark_feature_request_rejected.py "<substring to match>"')
        sys.exit(1)
    mark_rejected(sys.argv[1])
