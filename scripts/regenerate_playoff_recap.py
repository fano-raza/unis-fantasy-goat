"""Forces a playoff-week recap's narrative text (verb_phrase/advancement
per matchup) to be re-rolled and re-persisted -- the escape hatch for the
"generate once, keep forever unless I specifically ask for it to be
changed" behavior (user request, 2026-10-09). Does NOT repost to Discord
on its own; prints the new message so a human (or a follow-up Claude Code
session acting on the user's behalf) can decide whether/where to post it,
since the original Discord message can't be edited by this script.

Usage: python scripts/regenerate_playoff_recap.py <year> <week>

Run this on the droplet (needs network access to dashboard-api and write
access to the Ref data dir -- feature-bot or stat-bot both qualify), e.g.:
  ssh root@134.209.168.108 "docker compose -f /opt/unisFantasyGOAT/infra/docker/docker-compose.yml exec -T feature-bot python scripts/regenerate_playoff_recap.py 2026 19"
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import aiohttp  # noqa: E402

from discord.weekly_rankings import build_playoff_recap_message, force_regenerate_playoff_recap  # noqa: E402

API_BASE_URL = os.getenv("DASHBOARD_API_BASE_URL", "http://dashboard-api:8090")


async def _api_get(path: str) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE_URL}{path}") as resp:
            resp.raise_for_status()
            return await resp.json()


async def main(year: int, week: int) -> None:
    recap = await force_regenerate_playoff_recap(_api_get, year, week)
    if recap is None:
        print(f"No decided playoff round found for {year} week {week} -- nothing regenerated.")
        return
    print(f"Regenerated and persisted {year} week {week} ({recap['round_label']}). New message:\n")
    print(build_playoff_recap_message(recap))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python scripts/regenerate_playoff_recap.py <year> <week>")
        sys.exit(1)
    asyncio.run(main(int(sys.argv[1]), int(sys.argv[2])))
