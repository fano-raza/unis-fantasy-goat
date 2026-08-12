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

Also runs a second, unrelated scheduled job: keeping 3 Discord roles
("Top 6", "Champs", "Current Champ") in sync with the league's live data
every Monday morning, plus a /manual-push slash command to trigger that
sync on demand for testing (see the "Weekly role sync" section below).
Folded into this bot rather than a new one since it's small and this is
already the catch-all "misc automation" bot.
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
from shared.runtime_config import feature_requests_path, weekly_role_sync_state_path

CHECKBOX_REACTION = "☑️"  # ballot box with check (☑️) -- acknowledges capture
COMPLETED_REACTION = "✅"  # white_check_mark -- added later, once the request ships
IN_PROGRESS_REACTION = "🚧"  # construction -- someone's actively working it, still open
REJECTED_REACTION = "❌"  # cross mark -- considered and declined, moved to "## Ignored"

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


# --- Weekly role sync (Top 6 / Champs / Current Champ) ----------------------
# Weekly, Monday-morning sync of 3 independent Discord roles against the
# league's live data, all via dashboard-api over HTTP (same pattern
# discord/stat_bot.py already uses to stay decoupled from Models):
#   - "Top 6": only the current top-6-in-standings teams.
#   - "Champs": every team that has ever won a championship (monotonic --
#     once won, a team never loses this).
#   - "Current Champ": whichever team won the *most recent* championship
#     (singular in practice; coded to tolerate a tie rather than assume one).
#
# Deliberately doesn't use the privileged GUILD_MEMBERS intent to enumerate
# the whole guild: the only accounts that could ever need one of these roles
# are already known ahead of time (discord/discord_names.csv), so each one
# is looked up directly via guild.fetch_member() -- a plain REST call, not
# the gateway member cache that intent would otherwise be needed for.
#
# Requires manual, one-time Discord-server setup this code cannot do for
# you, per role actually configured (see the env vars below): the role must
# already exist, the bot's own role must sit ABOVE it in the role
# hierarchy, and the bot needs the "Manage Roles" permission -- Discord's
# API silently refuses role edits below a bot's own hierarchy position
# regardless of permission flags, so this can't be fixed from code if
# skipped. A role that isn't configured (no *_ROLE_ID/*_ROLE_NAME match) is
# just skipped, not an error -- lets these 3 roles be turned on one at a
# time.

EASTERN = ZoneInfo("America/New_York")
WEEKLY_SYNC_RUN_HOUR = 9  # local (America/New_York) hour to run on Mondays


def _read_last_weekly_sync_date() -> date | None:
    path = weekly_role_sync_state_path()
    if not path.exists():
        return None
    try:
        return date.fromisoformat(path.read_text().strip())
    except (ValueError, OSError):
        return None


def _write_last_weekly_sync_date(d: date) -> None:
    path = weekly_role_sync_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(d.isoformat())


def _resolve_role(
    guild: disnake.Guild, id_env: str, name_env: str, default_name: str, label: str
) -> disnake.Role | None:
    role_id = os.getenv(id_env, "").strip()
    if role_id:
        role = guild.get_role(int(role_id))
        if not role:
            print(f"{label} role update: {id_env}={role_id} not found in guild {guild.id}.")
        return role
    role_name = os.getenv(name_env, default_name).strip()
    role = disnake.utils.get(guild.roles, name=role_name)
    if not role:
        print(f'{label} role update: no role named "{role_name}" in guild {guild.id} -- not configured, skipping.')
    return role


def _resolve_guild(bot: commands.Bot, label: str) -> disnake.Guild | None:
    guild_id_raw = os.getenv("FEATURE_BOT_GUILD_ID", "").strip()
    if not guild_id_raw:
        print(f"{label} role update: FEATURE_BOT_GUILD_ID not set, skipping.")
        return None
    guild = bot.get_guild(int(guild_id_raw))
    if guild is None:
        print(f"{label} role update: guild {guild_id_raw} not found (bot not a member, or not cached yet).")
        return None
    return guild


async def _sync_role_membership(
    guild: disnake.Guild,
    role: disnake.Role,
    should_have_teams: set[str],
    by_team: dict[str, list[str]],
    label: str,
) -> None:
    for team, user_ids in by_team.items():
        should_have = team in should_have_teams
        for user_id in user_ids:
            try:
                member = await guild.fetch_member(int(user_id))
            except (disnake.NotFound, disnake.HTTPException, ValueError) as exc:
                print(f"{label} role update: couldn't resolve member {user_id} ({team}): {exc}")
                continue

            has_role = role in member.roles
            if should_have and not has_role:
                try:
                    await member.add_roles(role, reason=f"{label} role update")
                    print(f"{label} role update: added to {member} ({team})")
                except disnake.HTTPException as exc:
                    print(f"{label} role update: failed to add role to {member}: {exc}")
            elif has_role and not should_have:
                try:
                    await member.remove_roles(role, reason=f"{label} role update")
                    print(f"{label} role update: removed from {member} ({team})")
                except disnake.HTTPException as exc:
                    print(f"{label} role update: failed to remove role from {member}: {exc}")


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


async def _compute_champs_teams() -> tuple[set[str], set[str]]:
    """(every team that's ever won a championship, team(s) who won the most
    recent one). Pulled from team_summary.csv's "Championships"/
    "Championship Years" columns via /league/team_summary (the same data
    the Comparison page's Playoffs section already shows) -- Championship
    Years is a comma-joined string, e.g. "2021, 2022", empty if none.
    Current champ is coded as a *set* (not a single team) to tolerate a
    genuine tie in the data rather than assume one team, even though a
    single-champion-per-season structure makes that unlikely in practice."""
    status, rows = await _api_post("/league/team_summary", {})
    if status != 200 or not isinstance(rows, list):
        print(f"Champs role update: /league/team_summary failed ({status}): {rows}")
        return set(), set()

    team_years: dict[str, list[int]] = {}
    for row in rows:
        team = row.get("Team")
        years_raw = row.get("Championship Years") or ""
        years = [int(y.strip()) for y in years_raw.split(",") if y.strip()]
        if team and years:
            team_years[team] = years

    if not team_years:
        return set(), set()
    latest_year = max(y for years in team_years.values() for y in years)
    current_champs = {team for team, years in team_years.items() if latest_year in years}
    return set(team_years.keys()), current_champs


async def run_top6_role_update(bot: commands.Bot) -> None:
    guild = _resolve_guild(bot, "Top 6")
    if guild is None:
        return
    role = _resolve_role(guild, "TOP6_ROLE_ID", "TOP6_ROLE_NAME", "Top 6", "Top 6")
    if role is None:
        return

    top6_teams = await _compute_top6_teams()
    if top6_teams is None:
        return

    _, by_team = _load_user_team_maps()
    await _sync_role_membership(guild, role, set(top6_teams), by_team, "Top 6")
    print(f"Top 6 role update: done. Top 6 = {top6_teams}")


async def run_champs_role_update(bot: commands.Bot) -> None:
    guild = _resolve_guild(bot, "Champs")
    if guild is None:
        return
    champs_role = _resolve_role(guild, "CHAMPS_ROLE_ID", "CHAMPS_ROLE_NAME", "Champs", "Champs")
    current_champ_role = _resolve_role(
        guild, "CURRENT_CHAMP_ROLE_ID", "CURRENT_CHAMP_ROLE_NAME", "Current Champ", "Current Champ"
    )
    if champs_role is None and current_champ_role is None:
        return

    champ_teams, current_champs = await _compute_champs_teams()
    _, by_team = _load_user_team_maps()

    if champs_role is not None:
        await _sync_role_membership(guild, champs_role, champ_teams, by_team, "Champs")
        print(f"Champs role update: done. Champs = {sorted(champ_teams)}")
    if current_champ_role is not None:
        await _sync_role_membership(guild, current_champ_role, current_champs, by_team, "Current Champ")
        print(f"Current Champ role update: done. Current Champ = {sorted(current_champs)}")


async def run_all_role_updates(bot: commands.Bot) -> None:
    await run_top6_role_update(bot)
    await run_champs_role_update(bot)


@tasks.loop(hours=1)
async def _weekly_role_sync_loop(bot: commands.Bot) -> None:
    now_eastern = datetime.now(EASTERN)
    # Monday, at or after the target hour.
    if now_eastern.weekday() != 0 or now_eastern.hour < WEEKLY_SYNC_RUN_HOUR:
        return
    today = now_eastern.date()
    if _read_last_weekly_sync_date() == today:
        return
    try:
        await run_all_role_updates(bot)
        # Only mark today as done on success -- a failed attempt (e.g.
        # dashboard-api briefly unreachable) should retry next hour, still
        # within the same Monday, rather than silently skip the week.
        _write_last_weekly_sync_date(today)
    except Exception as exc:
        print(f"Weekly role sync failed, will retry next hour: {exc}")


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
        if not _weekly_role_sync_loop.is_running():
            _weekly_role_sync_loop.start(bot)

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

    @bot.slash_command(
        name="manual-push",
        description="Immediately run the Top 6/Champs/Current Champ role sync (for testing -- doesn't wait for Monday).",
        # Restricted to members who already have Manage Roles (mirrors the
        # permission the bot itself needs for this) -- this triggers a real
        # server-wide role reassignment, not a read-only lookup like the
        # other commands in this file, so it isn't left open to everyone.
        default_member_permissions=disnake.Permissions(manage_roles=True),
        **slash_kwargs,
    )
    async def manual_push(inter: disnake.ApplicationCommandInteraction):
        # Deferred + ephemeral: the sync fetches every linked member one at
        # a time and can take longer than Discord's 3s interaction window,
        # and the result (who got added/removed) isn't meant to be a public
        # announcement -- same "silent" design as the scheduled run itself,
        # just visible to whoever triggered it instead of no one.
        await inter.response.defer(ephemeral=True)
        try:
            await run_all_role_updates(bot)
            await inter.followup.send(
                "✅ Role sync ran (Top 6, Champs, Current Champ) -- check the bot's console/logs for exactly who changed.",
                ephemeral=True,
            )
        except Exception as exc:
            print(f"/manual-push failed: {exc}")
            await inter.followup.send(f"❌ Top 6 role sync failed: {exc}", ephemeral=True)

    bot.run(token)
