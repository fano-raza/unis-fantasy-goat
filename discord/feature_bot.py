"""FeatureBot: tag it in Discord with a feature request and it logs the exact
message to a plain Markdown checklist, then reacts with a checkbox to
acknowledge the request was captured. No LLM, no stats querying -- this is a
much smaller, independent bot from chatbot_bot.py (kept separate rather than
extending that file, since the two have nothing in common and the plan is to
retire chatbot_bot.py eventually).

The request list lives at shared.runtime_config.feature_requests_path() (a
plain file on the droplet's persistent data volume, not a database or an
external service) so it can be read and edited directly -- new requests are
appended under "## Open"; moving a line to "## Done" or "## Ignored" is a
plain text edit.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import disnake
from disnake.ext import commands

from discord.bot_env import build_ssl_connector, ensure_ssl_ca_bundle, load_local_env, strip_bot_mention
from shared.runtime_config import feature_requests_path

CHECKBOX_REACTION = "☑️"  # ballot box with check (☑️)

SECTION_HEADERS = ["## Open", "## Done", "## Ignored"]


def _ensure_file(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Feature Requests\n\n" + "\n\n".join(f"{h}\n" for h in SECTION_HEADERS))


def append_feature_request(author: str, location: str, content: str) -> None:
    path = feature_requests_path()
    _ensure_file(path)
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = f"- [ ] [{date}] {author} in {location}: \"{content}\"\n"

    text = path.read_text()
    marker = "## Open\n"
    idx = text.find(marker)
    if idx == -1:
        # File exists but somehow lost its Open header -- append one rather
        # than silently dropping the request.
        text = text.rstrip() + "\n\n" + marker + entry
    else:
        insert_at = idx + len(marker)
        text = text[:insert_at] + entry + text[insert_at:]
    path.write_text(text)


def run_bot() -> None:
    load_local_env()
    ensure_ssl_ca_bundle()
    token = os.getenv("FEATURE_BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "Missing FEATURE_BOT_TOKEN. Set it in env or create discord/.env from "
            "discord/feature_bot.env.example."
        )

    intents = disnake.Intents.default()
    intents.message_content = True

    connector = build_ssl_connector()
    bot = commands.Bot(command_prefix="!", intents=intents, connector=connector)

    @bot.event
    async def on_ready():
        print(f"FeatureBot logged in as {bot.user} (id={bot.user.id})")

    @bot.event
    async def on_message(message: disnake.Message):
        if message.author.bot or not bot.user:
            return
        if bot.user not in message.mentions:
            return

        content = strip_bot_mention(message.content, bot.user.id)
        if not content:
            return

        location = f"#{message.channel.name}" if hasattr(message.channel, "name") else "a DM"
        append_feature_request(
            author=str(message.author.display_name or message.author.name),
            location=location,
            content=content,
        )

        try:
            await message.add_reaction(CHECKBOX_REACTION)
        except Exception as exc:
            print(f"Failed to react to feature request message: {exc}")

    bot.run(token)
