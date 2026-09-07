"""One-off backfill for MapTap's raw_score column (see discord/daily_games.py's
backfill_maptap_raw_scores()) on rows recorded before that column existed.
Re-scans #daily-games from the beginning via a short-lived disnake.Client
login -- separate from the always-on stat-bot connection -- only far enough
to resolve every currently-missing row, then disconnects. Safe to re-run;
a no-op once nothing's missing.

Usage: python -m scripts.backfill_maptap_raw_scores
(reads STAT_BOT_TOKEN the same way discord/stat_bot.py's run_bot() does.)
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import disnake

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from discord import daily_games
from discord.bot_env import build_ssl_connector, ensure_ssl_ca_bundle, load_local_env


async def main() -> None:
    load_local_env()
    ensure_ssl_ca_bundle()
    token = os.getenv("STAT_BOT_TOKEN")
    if not token:
        print("Missing STAT_BOT_TOKEN.", file=sys.stderr)
        sys.exit(1)

    intents = disnake.Intents.default()
    intents.message_content = True
    client = disnake.Client(intents=intents, connector=build_ssl_connector())

    @client.event
    async def on_ready() -> None:
        try:
            channel = client.get_channel(daily_games.CHANNEL_ID) or await client.fetch_channel(
                daily_games.CHANNEL_ID
            )
            updated = await daily_games.backfill_maptap_raw_scores(channel)
            print(f"Backfilled raw_score for {updated} row(s).")
        finally:
            await client.close()

    await client.start(token)


if __name__ == "__main__":
    asyncio.run(main())
