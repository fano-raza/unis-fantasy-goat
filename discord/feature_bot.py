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

Also runs a second, unrelated scheduled job: keeping a "Top 6" Discord role
in sync with the league's live standings every Monday morning (see the
"Top 6 role" section below). Folded into this bot rather than a new one
since it's small and this is already the catch-all "misc automation" bot.
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import disnake
from disnake.ext import commands, tasks

from discord.bot_env import (
    build_ssl_connector,
    ensure_ssl_ca_bundle,
    load_local_env,
    parse_test_guild_ids,
    strip_bot_mention,
)
from discord.stat_bot import _api_get, _api_post, _load_user_team_maps
from shared.runtime_config import feature_requests_path, top6_role_state_path

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


# --- Top 6 role -------------------------------------------------------------
# Weekly, Monday-morning role sync: only the current top-6-in-standings
# teams' linked Discord accounts should hold the "Top 6" role. Standings
# math is never reimplemented here -- reuses dashboard-api (the same
# /league/standings the web app's Standings page calls) over HTTP, same
# pattern discord/stat_bot.py already uses to stay decoupled from Models.
#
# Deliberately doesn't use the privileged GUILD_MEMBERS intent to enumerate
# the whole guild: the only accounts that could ever need this role are
# already known ahead of time (discord/discord_names.csv), so each one is
# looked up directly via guild.fetch_member() -- a plain REST call, not the
# gateway member cache that intent would otherwise be needed for.
#
# Requires manual, one-time Discord-server setup this code cannot do for
# you: a role named (or ID'd via TOP6_ROLE_ID) TOP6_ROLE_NAME must already
# exist, the bot's own role must sit ABOVE it in the role hierarchy, and the
# bot needs the "Manage Roles" permission -- Discord's API silently refuses
# role edits below a bot's own hierarchy position regardless of permission
# flags, so this can't be fixed from code if skipped.

EASTERN = ZoneInfo("America/New_York")
TOP6_RUN_HOUR = 9  # local (America/New_York) hour to run on Mondays


def _read_last_top6_run_date() -> date | None:
    path = top6_role_state_path()
    if not path.exists():
        return None
    try:
        return date.fromisoformat(path.read_text().strip())
    except (ValueError, OSError):
        return None


def _write_last_top6_run_date(d: date) -> None:
    path = top6_role_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(d.isoformat())


def _resolve_top6_role(guild: disnake.Guild) -> disnake.Role | None:
    role_id = os.getenv("TOP6_ROLE_ID", "").strip()
    if role_id:
        role = guild.get_role(int(role_id))
        if not role:
            print(f"Top 6 role update: TOP6_ROLE_ID={role_id} not found in guild {guild.id}.")
        return role
    role_name = os.getenv("TOP6_ROLE_NAME", "Top 6").strip()
    role = disnake.utils.get(guild.roles, name=role_name)
    if not role:
        print(f'Top 6 role update: no role named "{role_name}" in guild {guild.id} -- create it first.')
    return role


async def _compute_top6_teams() -> list[str] | None:
    """Current top 6 teams by that season's real standings format (WL or
    Cats), cumulative through the latest recorded week -- the same
    definition of "current" the Standings page itself already defaults to
    (GET /league/meta's current_year/current_week/season_format)."""
    meta = await _api_get("/league/meta")
    year = meta.get("current_year")
    week = meta.get("current_week")
    if year is None or week is None:
        print("Top 6 role update: /league/meta has no current_year/current_week yet, skipping.")
        return None
    is_wl = meta.get("season_format", {}).get(str(year), "wl") == "wl"

    status, standings = await _api_post("/league/standings", {"year": year, "min_week": 1, "max_week": week})
    if status != 200:
        print(f"Top 6 role update: /league/standings failed ({status}): {standings}")
        return None

    rows = standings.get("wl" if is_wl else "cats", [])
    ranked = sorted(rows, key=lambda r: r["rank"])
    return [r["team"] for r in ranked[:6]]


async def run_top6_role_update(bot: commands.Bot) -> None:
    guild_id_raw = os.getenv("FEATURE_BOT_GUILD_ID", "").strip()
    if not guild_id_raw:
        print("Top 6 role update: FEATURE_BOT_GUILD_ID not set, skipping.")
        return
    guild = bot.get_guild(int(guild_id_raw))
    if guild is None:
        print(f"Top 6 role update: guild {guild_id_raw} not found (bot not a member, or not cached yet).")
        return

    role = _resolve_top6_role(guild)
    if role is None:
        return

    top6_teams = await _compute_top6_teams()
    if top6_teams is None:
        return
    top6_set = set(top6_teams)

    _, by_team = _load_user_team_maps()
    for team, user_ids in by_team.items():
        should_have = team in top6_set
        for user_id in user_ids:
            try:
                member = await guild.fetch_member(int(user_id))
            except (disnake.NotFound, disnake.HTTPException, ValueError) as exc:
                print(f"Top 6 role update: couldn't resolve member {user_id} ({team}): {exc}")
                continue

            has_role = role in member.roles
            if should_have and not has_role:
                try:
                    await member.add_roles(role, reason="Top 6 standings update")
                    print(f"Top 6 role update: added to {member} ({team})")
                except disnake.HTTPException as exc:
                    print(f"Top 6 role update: failed to add role to {member}: {exc}")
            elif has_role and not should_have:
                try:
                    await member.remove_roles(role, reason="Top 6 standings update")
                    print(f"Top 6 role update: removed from {member} ({team})")
                except disnake.HTTPException as exc:
                    print(f"Top 6 role update: failed to remove role from {member}: {exc}")

    print(f"Top 6 role update: done. Top 6 = {top6_teams}")


@tasks.loop(hours=1)
async def _top6_role_loop(bot: commands.Bot) -> None:
    now_eastern = datetime.now(EASTERN)
    # Monday, at or after the target hour.
    if now_eastern.weekday() != 0 or now_eastern.hour < TOP6_RUN_HOUR:
        return
    today = now_eastern.date()
    if _read_last_top6_run_date() == today:
        return
    try:
        await run_top6_role_update(bot)
        # Only mark today as done on success -- a failed attempt (e.g.
        # dashboard-api briefly unreachable) should retry next hour, still
        # within the same Monday, rather than silently skip the week.
        _write_last_top6_run_date(today)
    except Exception as exc:
        print(f"Top 6 role update failed, will retry next hour: {exc}")


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
        # on_ready can fire again after a reconnect -- guard against
        # starting a second concurrent copy of the hourly loop.
        if not _top6_role_loop.is_running():
            _top6_role_loop.start(bot)

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
