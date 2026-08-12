"""Reacts to a matching feature request's original Discord message with
🚧 (construction), signaling it's actively being worked on. Unlike
mark_feature_request_done.py/_rejected.py, this does NOT move the line out
of "## Open" or tick its checkbox -- "in progress" isn't a resolved
outcome, it's a transient status on a request that's still open.

Usage: python scripts/mark_feature_request_in_progress.py "<substring to match>"

Run this on the droplet (needs FEATURE_BOT_TOKEN + network access to
Discord's API) -- e.g.:
  ssh root@134.209.168.108 "docker compose -f /opt/unisFantasyGOAT/infra/docker/docker-compose.yml exec -T feature-bot python scripts/mark_feature_request_in_progress.py '<substring>'"
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from discord.feature_bot import IN_PROGRESS_REACTION  # noqa: E402
from scripts._feature_request_ops import react_only  # noqa: E402


def mark_in_progress(substring: str) -> None:
    react_only(substring, IN_PROGRESS_REACTION, "In Progress")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('Usage: python scripts/mark_feature_request_in_progress.py "<substring to match>"')
        sys.exit(1)
    mark_in_progress(sys.argv[1])
