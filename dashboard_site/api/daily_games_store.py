"""Read-only #daily-games stats (MapTap, Worldle, Flagle, WhenTaken, Travle,
Krillion) for the API -- used by the MCP server's game tools.

Reuses StatBot's own logic in discord/daily_games.py (leaderboard ranking,
top scores, daily-win counts) so the numbers always match the Discord
/leaderboard-style commands. That file is loaded by path rather than as
`discord.daily_games`: importing the `discord` package runs its __init__,
which pulls in Discord-side dependencies (requests, ...) this image doesn't
install. daily_games.py itself only needs disnake for its Discord-sync
functions, which import it locally.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "discord" / "daily_games.py"
_spec = importlib.util.spec_from_file_location("daily_games_stats", _PATH)
dg = importlib.util.module_from_spec(_spec)
sys.modules["daily_games_stats"] = dg
_spec.loader.exec_module(dg)


def _check_game(game: str) -> str:
    g = game.strip().lower()
    if g not in dg.GAMES:
        raise ValueError(f"Unknown game '{game}'. Games: {', '.join(dg.GAMES)}")
    return g


def _name(names: dict[str, str], uid) -> str:
    return names.get(str(uid), f"unlinked user {uid}")


def _date_range(rows: list[dict]) -> tuple[str | None, str | None]:
    dates = sorted(r["date"] for r in rows if r.get("date"))
    return (dates[0], dates[-1]) if dates else (None, None)


def meta() -> dict:
    synced = dg.read_last_synced_at()
    games = {}
    for g in dg.GAMES:
        rows = dg.load_history_rows(g)
        first, last = _date_range(rows)
        games[g] = {
            "label": dg.GAME_LABELS[g],
            "scoring": "lower is better (number of tries)" if dg.LOWER_IS_BETTER[g] else "higher is better (points)",
            "can_fail": dg.CAN_BE_INCOMPLETE[g],
            "plays": len(rows),
            "first_date": first,
            "last_date": last,
        }
    return {"games": games, "last_synced_at": synced.isoformat() if synced else None}


def leaderboard(game: str, days_back: int | None) -> list[dict]:
    g = _check_game(game)
    names = dg.load_display_names()
    out = []
    for i, r in enumerate(dg.build_leaderboard(g, days_back), start=1):
        row = {
            "rank": i,
            "player": _name(names, r["uid"]),
            "games_played": r["gp"],
            "completed": r["complete"],
            "failed": r["incomplete"],
            "avg": r["avg"],
            "median": r["median"],
        }
        if "rate" in r:
            row["completion_rate"] = r["rate"]
        out.append(row)
    return out


def top_scores(game: str, n: int, min_date: date | None, max_date: date | None) -> list[dict]:
    g = _check_game(game)
    names = dg.load_display_names()
    return [
        {"player": _name(names, p["uid"]), "date": p["date"], "score": p["score"]}
        for p in dg.top_scores(g, n, min_date=min_date, max_date=max_date)
    ]


def daily_wins(game: str, rank: int | str) -> list[dict]:
    g = _check_game(game)
    names = dg.load_display_names()
    return [{"player": _name(names, r["uid"]), "days": r["count"]} for r in dg.champion_counts(g, rank)]


def plays(
    game: str | None,
    player: str | None,
    min_date: date | None,
    max_date: date | None,
    limit: int,
) -> list[dict]:
    names = dg.load_display_names()
    games = [_check_game(game)] if game else list(dg.GAMES)
    out = []
    for g in games:
        for r in dg.load_history_rows(g):
            who = _name(names, r["discord_user_id"])
            if player and who.lower() != player.strip().lower():
                continue
            d = date.fromisoformat(r["date"])
            if (min_date and d < min_date) or (max_date and d > max_date):
                continue
            score = float(r["score"]) if r.get("score") not in ("", None) else None
            out.append({"game": g, "player": who, "date": r["date"], "score": score, "failed": score is None})
    out.sort(key=lambda p: (p["date"], p["game"], p["player"]), reverse=True)
    return out[:limit]
