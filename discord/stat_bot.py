"""StatBot: a handful of slash commands for quick league stat lookups and
trash talk, backed entirely by the existing lightweight dashboard-api (the
same API the web app uses) over plain HTTP -- no Models/constants import,
unlike the old chatbot_bot.py, so this stays a small, fast, low-memory bot
suited to the droplet's constrained RAM. Independent of feature_bot.py too
(different purpose, different command surface), sharing only the small
env/SSL helpers in bot_env.py.
"""

from __future__ import annotations

import csv
import os
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import aiohttp
import disnake
from disnake.ext import commands, tasks

from discord import daily_games
from discord.bot_env import build_ssl_connector, ensure_ssl_ca_bundle, load_local_env, parse_test_guild_ids
from shared.runtime_config import daily_games_last_run_path

API_BASE_URL = os.getenv("DASHBOARD_API_BASE_URL", "http://dashboard-api:8090")

EASTERN = ZoneInfo("America/New_York")
DAILY_GAMES_SYNC_HOUR = 4  # local (America/New_York) hour to run the daily #daily-games scan


def _load_user_team_maps() -> tuple[dict[str, str], dict[str, list[str]]]:
    """discord_user_id -> team, and team -> [discord_user_id, ...] (a team
    can have more than one linked account, e.g. alts). Read directly from
    discord_names.csv -- deliberately not reusing team_identity.py's loader,
    since that pulls in constants.py (heavy: gspread/espn_fr/yfpy_fr as an
    import-time side effect) just to validate team names against
    allMembers. Validating against /league/meta's member list instead would
    need a network round-trip at load time for no real benefit here."""
    raw_path = os.getenv("DISCORD_USER_TEAM_MAP_CSV", "").strip()
    path = Path(raw_path) if raw_path else Path(__file__).resolve().parent / "discord_names.csv"

    by_user_id: dict[str, str] = {}
    by_team: dict[str, list[str]] = {}
    if not path.exists():
        return by_user_id, by_team

    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            uid = str(row.get("discord_user_id") or "").strip()
            team = (row.get("team") or "").strip()
            if not uid or not team:
                continue
            by_user_id[uid] = team
            by_team.setdefault(team, []).append(uid)
    return by_user_id, by_team


async def _api_get(path: str) -> dict:
    async with aiohttp.ClientSession(connector=build_ssl_connector()) as session:
        async with session.get(f"{API_BASE_URL}{path}") as resp:
            resp.raise_for_status()
            return await resp.json()


async def _api_post(path: str, payload: dict) -> tuple[int, dict]:
    async with aiohttp.ClientSession(connector=build_ssl_connector()) as session:
        async with session.post(f"{API_BASE_URL}{path}", json=payload) as resp:
            data = await resp.json()
            return resp.status, data


def _years_suffix(years: str | None) -> str:
    return f" ({years})" if years else ""


def _read_last_daily_games_sync_date() -> date | None:
    path = daily_games_last_run_path()
    if not path.exists():
        return None
    try:
        return date.fromisoformat(path.read_text().strip())
    except (ValueError, OSError):
        return None


def _write_last_daily_games_sync_date(d: date) -> None:
    path = daily_games_last_run_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(d.isoformat())


def run_bot() -> None:
    load_local_env()
    ensure_ssl_ca_bundle()
    token = os.getenv("STAT_BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "Missing STAT_BOT_TOKEN. Set it in env or create discord/.env from "
            "discord/stat_bot.env.example."
        )

    by_user_id, by_team = _load_user_team_maps()

    intents = disnake.Intents.default()
    intents.message_content = True
    connector = build_ssl_connector()
    # No prefix commands here, only slash commands -- when_mentioned avoids
    # disnake's warning about a "!" prefix needing Message Content intent
    # for functionality this bot never uses.
    bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents, connector=connector)
    test_guild_ids = parse_test_guild_ids()
    slash_kwargs = {"guild_ids": test_guild_ids} if test_guild_ids else {}

    @tasks.loop(hours=1)
    async def _daily_games_sync_loop() -> None:
        now_eastern = datetime.now(EASTERN)
        if now_eastern.hour < DAILY_GAMES_SYNC_HOUR:
            return
        today = now_eastern.date()
        if _read_last_daily_games_sync_date() == today:
            return
        try:
            channel = bot.get_channel(daily_games.CHANNEL_ID) or await bot.fetch_channel(daily_games.CHANNEL_ID)
            added = await daily_games.scan_and_record(channel)
            # Only mark today as done on success -- a failed attempt (e.g.
            # channel briefly unreachable) should retry next hour, still
            # within the same day, rather than silently skip a whole day.
            _write_last_daily_games_sync_date(today)
            print(f"Daily games sync: added {added} new row(s)")
        except Exception as exc:
            print(f"Daily games sync failed, will retry next hour: {exc}")

    def _resolve_team(user: disnake.User | disnake.Member) -> Optional[str]:
        return by_user_id.get(str(user.id))

    def _mention_for_team(team: str) -> str:
        ids = by_team.get(team)
        return f"<@{ids[0]}>" if ids else f"**{team}**"

    @bot.event
    async def on_ready():
        print(f"StatBot logged in as {bot.user} (id={bot.user.id})")
        # on_ready can fire again after a reconnect -- guard against
        # starting a second concurrent copy of the hourly loop.
        if not _daily_games_sync_loop.is_running():
            _daily_games_sync_loop.start()

    @bot.event
    async def on_message(message: disnake.Message):
        if message.author.bot or not bot.user:
            return
        if bot.user not in message.mentions:
            return
        game_lines = "\n".join(
            f"`/{game} [days]` — {daily_games.GAME_LABELS[game]} leaderboard (default: last 7 days, or \"ever\" for all-time)"
            for game in daily_games.GAMES
        )
        await message.channel.send(
            "🤖 **StatBot commands:**\n\n"
            "**Fantasy Commands:**\n"
            "`/standings-check [year]` — league standings for a season\n"
            "`/champ-check [user]` — has this team ever won a title?\n"
            "`/mvp-check [user]` — has this team ever won MVP?\n"
            "`/l-check [user]` — has this team ever finished dead last?\n"
            "`/score-check` — your current matchup score\n"
            "`/rival-check <user>` — career head-to-head record\n"
            "`/trophy-case [user]` — career trophy summary\n"
            "`/goat-check` — who's the league GOAT?\n\n"
            "**Daily Games Commands:**\n" + game_lines
        )

    @bot.slash_command(name="standings-check", description="Show league standings for a season.", **slash_kwargs)
    async def standings_check(
        inter: disnake.ApplicationCommandInteraction,
        year: Optional[int] = None,
    ):
        meta = await _api_get("/league/meta")
        year = year if year in meta["years"] else meta["current_year"]
        # Cap at the regular season's own last week, not current_week -- once
        # playoffs start, current_week moves past the RS (e.g. 21 for a
        # season whose RS is only 18 weeks), which would wrongly blend
        # playoff-week results into what's meant to be regular-season
        # standings. Safe even mid-season: weeks that haven't been played
        # yet simply have no rows, so this doesn't pull in phantom data.
        week = meta["rs_week_count"].get(str(year), meta["current_week"])
        fmt = meta["season_format"].get(str(year), "wl")
        status, standings = await _api_post(
            "/league/standings", {"year": year, "min_week": 1, "max_week": week}
        )
        if status != 200:
            await inter.response.send_message("Couldn't load standings right now.", ephemeral=True)
            return

        rows = standings["wl"] if fmt == "wl" else standings["cats"]
        rows = sorted(rows, key=lambda r: r["rank"])
        lines = [f"{r['rank']}. **{r['team']}** — {r['wins']}-{r['losses']}-{r['ties']}" for r in rows]
        label = "W/L" if fmt == "wl" else "Cats"
        await inter.response.send_message(
            f"📊 **{year} Regular Season Standings** (through Week {week}, {label})\n" + "\n".join(lines)
        )

    @bot.slash_command(name="goat-check", description="Who's the league GOAT?", **slash_kwargs)
    async def goat_check(inter: disnake.ApplicationCommandInteraction):
        meta = await _api_get("/league/meta")
        goat = meta.get("goat")
        if not goat:
            await inter.response.send_message("No GOAT determined yet.", ephemeral=True)
            return
        await inter.response.send_message(f"🐐 The league GOAT is **{goat}**.")

    @bot.slash_command(name="champ-check", description="Has this user's team ever won a championship?", **slash_kwargs)
    async def champ_check(
        inter: disnake.ApplicationCommandInteraction,
        user: Optional[disnake.User] = None,
    ):
        target = user or inter.author
        team = _resolve_team(target)
        if not team:
            await inter.response.send_message(
                f"Couldn't find a team linked to {target.mention}.", ephemeral=True
            )
            return
        status, rows = await _api_post("/league/team_summary", {"teams": [team]})
        if status != 200 or not rows:
            await inter.response.send_message("Couldn't load that team's data.", ephemeral=True)
            return
        row = rows[0]
        count = row.get("Championships") or 0
        years = row.get("Championship Years")
        if count > 0:
            await inter.response.send_message(
                f"🏆 **{team}** is a champion! ({count} title{'s' if count != 1 else ''}{_years_suffix(years)})"
            )
        else:
            await inter.response.send_message(f"❌ **{team}** has never won a championship.")

    @bot.slash_command(name="mvp-check", description="Has this user's team ever won MVP?", **slash_kwargs)
    async def mvp_check(
        inter: disnake.ApplicationCommandInteraction,
        user: Optional[disnake.User] = None,
    ):
        target = user or inter.author
        team = _resolve_team(target)
        if not team:
            await inter.response.send_message(
                f"Couldn't find a team linked to {target.mention}.", ephemeral=True
            )
            return
        status, rows = await _api_post("/league/team_summary", {"teams": [team]})
        if status != 200 or not rows:
            await inter.response.send_message("Couldn't load that team's data.", ephemeral=True)
            return
        row = rows[0]
        count = row.get("MVPs") or 0
        years = row.get("MVP Years")
        if count > 0:
            await inter.response.send_message(
                f"⭐ **{team}** has won MVP! ({count} time{'s' if count != 1 else ''}{_years_suffix(years)})"
            )
        else:
            await inter.response.send_message(f"❌ **{team}** has never won MVP.")

    @bot.slash_command(name="l-check", description="Has this user's team ever finished dead last?", **slash_kwargs)
    async def l_check(
        inter: disnake.ApplicationCommandInteraction,
        user: Optional[disnake.User] = None,
    ):
        target = user or inter.author
        team = _resolve_team(target)
        if not team:
            await inter.response.send_message(
                f"Couldn't find a team linked to {target.mention}.", ephemeral=True
            )
            return
        status, rows = await _api_post("/league/team_summary", {"teams": [team]})
        if status != 200 or not rows:
            await inter.response.send_message("Couldn't load that team's data.", ephemeral=True)
            return
        row = rows[0]
        count = row.get("RS Last Place") or 0
        years = row.get("RS Last Years")
        if count > 0:
            await inter.response.send_message(
                f"💀 **{team}** has finished dead last! ({count} time{'s' if count != 1 else ''}{_years_suffix(years)})"
            )
        else:
            await inter.response.send_message(f"✅ **{team}** has never finished dead last.")

    @bot.slash_command(name="score-check", description="Your current matchup score.", **slash_kwargs)
    async def score_check(inter: disnake.ApplicationCommandInteraction):
        team = _resolve_team(inter.author)
        if not team:
            await inter.response.send_message("Couldn't find a team linked to your account.", ephemeral=True)
            return

        meta = await _api_get("/league/meta")
        year, week = meta["current_year"], meta["current_week"]
        status, data = await _api_post("/league/weekly_team", {"year": year, "week": week, "team": team})
        if status == 404 or data.get("opponent") == "BYE" or data.get("cat_wins") is None:
            await inter.response.send_message(f"🚫 **{team}** has no current matchup this week (N/A).")
            return

        opp_mention = _mention_for_team(data["opponent"])
        w, l, t = data["cat_wins"], data["cat_losses"], data["cat_ties"]
        record = f"{w}-{l}" + (f"-{t}" if t else "")
        await inter.response.send_message(
            f"📈 **{team}**'s Week {week} score: **{record}** vs {opp_mention}"
        )

    @bot.slash_command(name="rival-check", description="Career head-to-head record against another team.", **slash_kwargs)
    async def rival_check(
        inter: disnake.ApplicationCommandInteraction,
        user: disnake.User,
    ):
        team_a = _resolve_team(inter.author)
        team_b = _resolve_team(user)
        if not team_a:
            await inter.response.send_message("Couldn't find a team linked to your account.", ephemeral=True)
            return
        if not team_b:
            await inter.response.send_message(f"Couldn't find a team linked to {user.mention}.", ephemeral=True)
            return

        status, data = await _api_post("/league/head_to_head", {"team_a": team_a, "team_b": team_b})
        if status == 404:
            await inter.response.send_message(f"⚔️ **{team_a}** and **{team_b}** haven't played each other yet.")
            return

        rec = data["record"]
        cat = data["category_record"]
        await inter.response.send_message(
            f"⚔️ **{team_a}** vs **{team_b}** all-time:\n"
            f"Matchup record: **{rec['wins']}-{rec['losses']}-{rec['ties']}**\n"
            f"Category record: **{cat['wins']}-{cat['losses']}-{cat['ties']}**"
        )

    @bot.slash_command(name="trophy-case", description="Career trophy summary for this user's team.", **slash_kwargs)
    async def trophy_case(
        inter: disnake.ApplicationCommandInteraction,
        user: Optional[disnake.User] = None,
    ):
        target = user or inter.author
        team = _resolve_team(target)
        if not team:
            await inter.response.send_message(
                f"Couldn't find a team linked to {target.mention}.", ephemeral=True
            )
            return
        status, rows = await _api_post("/league/team_summary", {"teams": [team]})
        if status != 200 or not rows:
            await inter.response.send_message("Couldn't load that team's data.", ephemeral=True)
            return
        row = rows[0]
        await inter.response.send_message(
            f"🏆 **{team}'s Trophy Case**\n"
            f"Championships: **{row.get('Championships') or 0}**{_years_suffix(row.get('Championship Years'))}\n"
            f"MVPs: **{row.get('MVPs') or 0}**{_years_suffix(row.get('MVP Years'))}\n"
            f"RS 1st Place: **{row.get('RS 1st Place') or 0}**{_years_suffix(row.get('RS 1st Years'))}"
        )

    async def _game_leaderboard(
        inter: disnake.ApplicationCommandInteraction,
        game: str,
        days: Optional[str],
    ) -> None:
        try:
            days_back, range_label = daily_games.parse_days_arg(days)
        except ValueError as e:
            await inter.response.send_message(f"⚠️ {e}", ephemeral=True)
            return

        board = daily_games.build_leaderboard(game, days_back)
        label = daily_games.GAME_LABELS[game]
        if not board:
            await inter.response.send_message(f"No {label} data for {range_label} yet.")
            return

        display_names = daily_games.load_display_names()
        lines = [f"🏆 **{label}** — {range_label}"]
        for rank, entry in enumerate(board, start=1):
            name = display_names.get(str(entry["uid"]), f"<@{entry['uid']}>")
            avg = f"{entry['avg']:.2f}" if entry["avg"] is not None else "—"
            lines.append(f"{rank}. **{name}** — {avg} avg ({entry['gp']} GP)")
        await inter.response.send_message("\n".join(lines))

    # One /<game> slash command per daily_games.GAMES entry, all sharing
    # _game_leaderboard -- default last 7 days, optional `days` free-text
    # arg (a number, or "ever" for full history since channel creation).
    for _game in daily_games.GAMES:

        def _register(game: str = _game) -> None:
            @bot.slash_command(
                name=game,
                description=f"{daily_games.GAME_LABELS[game]} leaderboard (default: last 7 days).",
                **slash_kwargs,
            )
            async def _game_command(
                inter: disnake.ApplicationCommandInteraction,
                days: Optional[str] = None,
            ):
                await _game_leaderboard(inter, game, days)

        _register()

    bot.run(token)
