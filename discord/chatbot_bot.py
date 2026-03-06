import asyncio
import os
import ssl
import time
from pathlib import Path

import aiohttp
import disnake
from disnake.ext import commands

from .query_parser import QuerySpec, parse_query
from .stats_query_engine import answer_query
from .team_identity import resolve_user_team
from .usage_metrics import record_usage_event


def _ensure_ssl_ca_bundle() -> None:
    """
    Ensure aiohttp/disnake can validate TLS certificates.
    Useful on macOS/Python installs where CA bundle is missing from default trust path.
    """
    if os.getenv("SSL_CERT_FILE"):
        return
    try:
        import certifi
        os.environ["SSL_CERT_FILE"] = certifi.where()
    except Exception:
        pass


def _build_ssl_connector() -> aiohttp.TCPConnector | None:
    """
    Build connector with explicit CA bundle to avoid platform trust-store issues.
    """
    try:
        if os.getenv("DISCORD_SSL_NO_VERIFY", "0").strip() in {"1", "true", "TRUE", "yes", "YES"}:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            print("WARNING: DISCORD_SSL_NO_VERIFY is enabled. TLS cert verification is disabled.")
            return aiohttp.TCPConnector(ssl=ctx)

        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
        return aiohttp.TCPConnector(ssl=ctx)
    except Exception:
        return None


def _load_local_env() -> None:
    """
    Load env vars from local .env files if present.
    Precedence:
      1) Existing process environment
      2) discord/.env
      3) repo_root/.env
    """
    here = Path(__file__).resolve().parent
    repo_root = here.parent
    env_paths = [here / ".env", repo_root / ".env"]

    for env_path in env_paths:
        if not env_path.exists():
            continue

        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = value


def _strip_bot_mention(content: str, bot_user_id: int) -> str:
    return (
        content
        .replace(f"<@{bot_user_id}>", "")
        .replace(f"<@!{bot_user_id}>", "")
        .strip()
    )


def _run_answer_pipeline(question: str) -> tuple[str, QuerySpec]:
    spec = parse_query(question)
    return answer_query(question, spec), spec


def _record_message_usage(
    message: disnake.Message,
    question: str,
    response: str,
    spec: QuerySpec | None,
    ok: bool,
    latency_ms: int,
    error: str | None = None,
) -> None:
    team_match = resolve_user_team(
        user_id=getattr(message.author, "id", None),
        display_name=getattr(message.author, "display_name", None),
        username=getattr(message.author, "name", None),
    )
    record_usage_event(
        {
            "source": "mention",
            "guild_id": getattr(message.guild, "id", None),
            "channel_id": getattr(message.channel, "id", None),
            "message_id": getattr(message, "id", None),
            "user_id": getattr(message.author, "id", None),
            "username": getattr(message.author, "name", None),
            "display_name": getattr(message.author, "display_name", None),
            "mapped_team": team_match.team,
            "team_map_source": team_match.source,
            "question": question,
            "intent": getattr(spec, "intent", None),
            "year": getattr(spec, "year", None),
            "scope": getattr(spec, "scope", None),
            "ok": ok,
            "latency_ms": latency_ms,
            "error": error,
            "response_preview": response,
        }
    )


def _record_slash_usage(
    inter: disnake.ApplicationCommandInteraction,
    question: str,
    response: str,
    spec: QuerySpec | None,
    ok: bool,
    latency_ms: int,
    error: str | None = None,
) -> None:
    author = getattr(inter, "author", None)
    team_match = resolve_user_team(
        user_id=getattr(author, "id", None),
        display_name=getattr(author, "display_name", None),
        username=getattr(author, "name", None),
    )
    record_usage_event(
        {
            "source": "slash",
            "command": getattr(getattr(inter, "application_command", None), "name", None),
            "guild_id": getattr(inter.guild, "id", None),
            "channel_id": getattr(inter.channel, "id", None),
            "user_id": getattr(author, "id", None),
            "username": getattr(author, "name", None),
            "display_name": getattr(author, "display_name", None),
            "mapped_team": team_match.team,
            "team_map_source": team_match.source,
            "question": question,
            "intent": getattr(spec, "intent", None),
            "year": getattr(spec, "year", None),
            "scope": getattr(spec, "scope", None),
            "ok": ok,
            "latency_ms": latency_ms,
            "error": error,
            "response_preview": response,
        }
    )


def _parse_test_guild_ids() -> list[int] | None:
    raw = os.getenv("DISCORD_TEST_GUILD_IDS", "").strip()
    if not raw:
        return None
    ids = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            continue
    return ids or None


def _parse_allowed_channel_ids() -> set[int] | None:
    raw = os.getenv("DISCORD_ALLOWED_CHANNEL_IDS", "").strip()
    if not raw:
        return None
    ids = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            continue
    return ids or None


def run_bot() -> None:
    _load_local_env()
    _ensure_ssl_ca_bundle()
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "Missing DISCORD_BOT_TOKEN. Set it in env or create discord/.env from discord/.env.example."
        )

    intents = disnake.Intents.default()
    intents.message_content = True

    connector = _build_ssl_connector()
    bot = commands.Bot(command_prefix="!", intents=intents, connector=connector)
    test_guild_ids = _parse_test_guild_ids()
    slash_kwargs = {"guild_ids": test_guild_ids} if test_guild_ids else {}
    allowed_channel_ids = _parse_allowed_channel_ids()

    async def _ensure_allowed_interaction(inter: disnake.ApplicationCommandInteraction) -> bool:
        if not allowed_channel_ids:
            return True
        if inter.channel_id in allowed_channel_ids:
            return True
        await inter.response.send_message(
            "This bot is restricted to specific channels in this server.",
            ephemeral=True,
        )
        return False

    @bot.event
    async def on_ready():
        print(f"Discord bot logged in as {bot.user} (id={bot.user.id})")
        if test_guild_ids:
            print(f"Slash commands are guild-scoped for fast sync: {test_guild_ids}")
        else:
            print("Slash commands are global (can take time to appear).")
        if allowed_channel_ids:
            print(f"Bot responses restricted to channel IDs: {sorted(allowed_channel_ids)}")
        else:
            print("Bot responses are not channel-restricted.")

    @bot.slash_command(name="ask_stats", description="Ask a free-form stats question.", **slash_kwargs)
    async def ask_stats(
        inter: disnake.ApplicationCommandInteraction,
        question: str,
    ):
        if not await _ensure_allowed_interaction(inter):
            return
        await inter.response.defer()
        start = time.perf_counter()
        spec = None
        ok = True
        err = None
        try:
            spec = parse_query(question, use_llm=False)
            spec.deterministic_only = True
            response = await asyncio.to_thread(answer_query, question, spec)
        except Exception as exc:
            ok = False
            err = str(exc)
            response = f"I hit an error while processing that question: {exc}"
        _record_slash_usage(inter, question, response, spec, ok, int((time.perf_counter() - start) * 1000), err)
        await inter.edit_original_response(response)

    @bot.slash_command(name="standings", description="Get standings for a season.", **slash_kwargs)
    async def standings(
        inter: disnake.ApplicationCommandInteraction,
        year: int,
        format: str = commands.Param(choices=["auto", "wl", "cats"]),
    ):
        if not await _ensure_allowed_interaction(inter):
            return
        await inter.response.defer()
        q = f"standings {year}"
        spec = QuerySpec(intent="standings", year=year, standings_format=format, deterministic_only=True)
        start = time.perf_counter()
        ok = True
        err = None
        try:
            response = await asyncio.to_thread(answer_query, q, spec)
        except Exception as exc:
            ok = False
            err = str(exc)
            response = f"I hit an error while processing that question: {exc}"
        _record_slash_usage(inter, q, response, spec, ok, int((time.perf_counter() - start) * 1000), err)
        await inter.edit_original_response(response)

    @bot.slash_command(name="leader", description="Get leader(s) for a stat.", **slash_kwargs)
    async def leader(
        inter: disnake.ApplicationCommandInteraction,
        year: int,
        stat: str = commands.Param(choices=["PTS", "REB", "AST", "STL", "BLK", "TO", "3PTM", "FG%", "FT%"]),
        scope: str = commands.Param(choices=["ALL", "RS", "PO"], default="ALL"),
        top_n: int = 1,
        direction: str = commands.Param(choices=["max", "min"], default="max"),
    ):
        if not await _ensure_allowed_interaction(inter):
            return
        await inter.response.defer()
        spec = QuerySpec(
            intent="leader",
            year=year,
            stat=stat,
            scope=scope,
            top_n=max(1, min(10, top_n)),
            direction=direction,
            deterministic_only=True,
        )
        q = f"leader {year} {stat}"
        start = time.perf_counter()
        ok = True
        err = None
        try:
            response = await asyncio.to_thread(answer_query, q, spec)
        except Exception as exc:
            ok = False
            err = str(exc)
            response = f"I hit an error while processing that question: {exc}"
        _record_slash_usage(inter, q, response, spec, ok, int((time.perf_counter() - start) * 1000), err)
        await inter.edit_original_response(response)

    @bot.slash_command(name="compare", description="Compare two teams.", **slash_kwargs)
    async def compare(
        inter: disnake.ApplicationCommandInteraction,
        year: int,
        team1: str,
        team2: str,
        scope: str = commands.Param(choices=["ALL", "RS", "PO"], default="ALL"),
        stat: str = commands.Param(
            choices=["none", "PTS", "REB", "AST", "STL", "BLK", "TO", "3PTM", "FG%", "FT%"],
            default="none",
        ),
    ):
        if not await _ensure_allowed_interaction(inter):
            return
        await inter.response.defer()
        spec = QuerySpec(
            intent="team_compare",
            year=year,
            team=team1,
            team2=team2,
            scope=scope,
            stat=None if stat == "none" else stat,
            deterministic_only=True,
        )
        q = f"compare {team1} vs {team2}"
        start = time.perf_counter()
        ok = True
        err = None
        try:
            response = await asyncio.to_thread(answer_query, q, spec)
        except Exception as exc:
            ok = False
            err = str(exc)
            response = f"I hit an error while processing that question: {exc}"
        _record_slash_usage(inter, q, response, spec, ok, int((time.perf_counter() - start) * 1000), err)
        await inter.edit_original_response(response)

    @bot.slash_command(name="head_to_head", description="Head-to-head record and category score.", **slash_kwargs)
    async def head_to_head(
        inter: disnake.ApplicationCommandInteraction,
        year: int,
        team1: str,
        team2: str,
        scope: str = commands.Param(choices=["ALL", "RS", "PO"], default="ALL"),
    ):
        if not await _ensure_allowed_interaction(inter):
            return
        await inter.response.defer()
        spec = QuerySpec(
            intent="head_to_head",
            year=year,
            team=team1,
            team2=team2,
            scope=scope,
            deterministic_only=True,
        )
        q = f"head to head {team1} vs {team2}"
        start = time.perf_counter()
        ok = True
        err = None
        try:
            response = await asyncio.to_thread(answer_query, q, spec)
        except Exception as exc:
            ok = False
            err = str(exc)
            response = f"I hit an error while processing that question: {exc}"
        _record_slash_usage(inter, q, response, spec, ok, int((time.perf_counter() - start) * 1000), err)
        await inter.edit_original_response(response)

    @bot.slash_command(name="team_summary", description="Get a season summary for one team.", **slash_kwargs)
    async def team_summary(
        inter: disnake.ApplicationCommandInteraction,
        year: int,
        team: str,
        scope: str = commands.Param(choices=["ALL", "RS", "PO"], default="ALL"),
    ):
        if not await _ensure_allowed_interaction(inter):
            return
        await inter.response.defer()
        spec = QuerySpec(intent="team_summary", year=year, team=team, scope=scope, deterministic_only=True)
        q = f"team summary {team}"
        start = time.perf_counter()
        ok = True
        err = None
        try:
            response = await asyncio.to_thread(answer_query, q, spec)
        except Exception as exc:
            ok = False
            err = str(exc)
            response = f"I hit an error while processing that question: {exc}"
        _record_slash_usage(inter, q, response, spec, ok, int((time.perf_counter() - start) * 1000), err)
        await inter.edit_original_response(response)

    @bot.event
    async def on_message(message: disnake.Message):
        if message.author.bot or not bot.user:
            return
        if allowed_channel_ids and message.channel.id not in allowed_channel_ids:
            return

        if bot.user not in message.mentions:
            await bot.process_commands(message)
            return

        question = _strip_bot_mention(message.content, bot.user.id)
        if not question:
            await message.reply(
                "Ask me something like: `@bot in 2020, who had the most points?`",
                mention_author=False,
            )
            return

        start = time.perf_counter()
        parsed_spec = None
        ok = True
        err = None
        async with message.channel.typing():
            try:
                response, parsed_spec = await asyncio.to_thread(_run_answer_pipeline, question)
            except Exception as exc:
                ok = False
                err = str(exc)
                response = f"I hit an error while processing that question: {exc}"

        _record_message_usage(
            message,
            question,
            response,
            parsed_spec,
            ok,
            int((time.perf_counter() - start) * 1000),
            err,
        )
        await message.reply(response, mention_author=False)
        await bot.process_commands(message)

    bot.run(token)


if __name__ == "__main__":
    run_bot()
