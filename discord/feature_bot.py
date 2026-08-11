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

Each logged line carries a hidden `<!-- discord: channel_id=... message_id=...
-->` comment (invisible when the file is rendered as Markdown, visible in raw
text) so a later "mark as done" pass -- see scripts/mark_feature_request_done.py
-- can find the original message and react to it, without needing a separate
database to track the link. Requests logged before this existed have no
comment and simply can't be reacted to retroactively.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path

import disnake
from disnake.ext import commands

from discord.bot_env import (
    build_ssl_connector,
    ensure_ssl_ca_bundle,
    load_local_env,
    parse_test_guild_ids,
    strip_bot_mention,
)
from shared.runtime_config import feature_requests_path

CHECKBOX_REACTION = "☑️"  # ballot box with check (☑️) -- acknowledges capture
COMPLETED_REACTION = "✅"  # white_check_mark -- added later, once the request ships

SECTION_HEADERS = ["## Open", "## Done", "## Ignored"]

_DISCORD_REF_RE = re.compile(r"<!--\s*discord:\s*channel_id=(\d+)\s+message_id=(\d+)\s*-->")


def _ensure_file(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Feature Requests\n\n" + "\n\n".join(f"{h}\n" for h in SECTION_HEADERS))


def _location_for(channel) -> str:
    return f"#{channel.name}" if hasattr(channel, "name") else "a DM"


def parse_discord_ref(line: str) -> tuple[int, int] | None:
    """Extracts (channel_id, message_id) from a logged line's hidden comment,
    or None if the line predates this feature (no comment present)."""
    m = _DISCORD_REF_RE.search(line)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def append_feature_request(
    author: str,
    location: str,
    content: str,
    channel_id: int | None = None,
    message_id: int | None = None,
) -> None:
    path = feature_requests_path()
    _ensure_file(path)
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ref_comment = f" <!-- discord: channel_id={channel_id} message_id={message_id} -->" if channel_id and message_id else ""
    entry = f"- [ ] [{date}] {author} in {location}: \"{content}\"{ref_comment}\n"

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
    # No prefix commands here, only slash + mention-based -- avoids disnake's
    # warning about a "!" prefix needing Message Content intent for
    # functionality this bot never uses.
    bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents, connector=connector)
    test_guild_ids = parse_test_guild_ids()
    slash_kwargs = {"guild_ids": test_guild_ids} if test_guild_ids else {}

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

        append_feature_request(
            author=str(message.author.display_name or message.author.name),
            location=_location_for(message.channel),
            content=content,
            channel_id=message.channel.id,
            message_id=message.id,
        )

        try:
            await message.add_reaction(CHECKBOX_REACTION)
        except Exception as exc:
            print(f"Failed to react to feature request message: {exc}")

    @bot.slash_command(
        name="feature-request",
        description="Log a feature request without tagging the bot.",
        **slash_kwargs,
    )
    async def feature_request(inter: disnake.ApplicationCommandInteraction, request: str):
        # Reply first so there's a message to attach the Discord ref to --
        # append_feature_request needs the response message's own id, not
        # the (nonexistent) slash-command invocation's.
        await inter.response.send_message(f'📋 Logged: "{request}"')
        msg = None
        try:
            msg = await inter.original_response()
        except Exception as exc:
            print(f"Failed to fetch feature request confirmation message: {exc}")

        append_feature_request(
            author=str(inter.author.display_name or inter.author.name),
            location=_location_for(inter.channel),
            content=request,
            channel_id=inter.channel.id if inter.channel else None,
            message_id=msg.id if msg else None,
        )

        if msg:
            try:
                await msg.add_reaction(CHECKBOX_REACTION)
            except Exception as exc:
                print(f"Failed to react to feature request confirmation: {exc}")

    bot.run(token)
