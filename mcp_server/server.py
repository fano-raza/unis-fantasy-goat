"""Public, read-only MCP server for the league's stats.

Lets league members add the app as a custom connector in their own AI chat
(Claude, ChatGPT, ...) and ask questions like "who has the record for most
rebounds in week 2?". Every tool is a thin call to dashboard-api (the same
endpoints that power the website); this process holds no data of its own and
deliberately imports no pandas/Models so it stays small on the droplet.

See _planning/mcp-server.md for scope and decisions.
"""

from __future__ import annotations

import functools
import json
import logging
import os
import time
from datetime import date
from collections import defaultdict, deque
from typing import Any, Literal

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError as SDKToolError
from mcp.types import ToolAnnotations
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse

API_BASE = os.getenv("DASHBOARD_API_BASE_URL", "http://dashboard-api:8090").rstrip("/")
RATE_LIMIT_PER_MIN = int(os.getenv("MCP_RATE_LIMIT_PER_MIN", "60"))
META_TTL_S = 300

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mcp_server")

_http = httpx.Client(base_url=API_BASE, timeout=30.0)


# --------------------------------------------------------------------------
# dashboard-api helpers
# --------------------------------------------------------------------------


class ToolError(Exception):
    """Bad input; _logged re-raises it as the SDK's ToolError so the AI sees the message and can retry."""


def _get(path: str) -> Any:
    r = _http.get(path)
    r.raise_for_status()
    return r.json()


def _post(path: str, body: dict) -> Any:
    r = _http.post(path, json=body)
    if r.status_code == 400:
        raise ToolError(r.json().get("detail", r.text))
    r.raise_for_status()
    return r.json()


_cache: dict[str, tuple[float, Any]] = {}


def _cached(key: str, fn) -> Any:
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < META_TTL_S:
        return hit[1]
    val = fn()
    _cache[key] = (time.monotonic(), val)
    return val


def _meta() -> dict:
    return _cached("league_meta", lambda: _get("/league/meta"))


def _calendar(year: int) -> dict[int, dict]:
    rows = _cached(f"cal:{year}", lambda: _post("/league/week_calendar", {"year": year}))
    return {int(r["Week"]): r for r in rows}


def _team(name: str) -> str:
    """Case-insensitive match against every manager who has ever played."""
    members = _meta()["members"]
    for m in members:
        if m.lower() == name.strip().lower():
            return m
    raise ToolError(f"Unknown team '{name}'. Teams are named after their managers: {', '.join(members)}.")


def _teams(names: list[str] | None) -> list[str] | None:
    return [_team(n) for n in names] if names else None


def _year(year: int | None) -> int:
    meta = _meta()
    if year is None:
        return int(meta["current_year"])
    if year not in meta["years"]:
        raise ToolError(f"No data for season {year}. Seasons available: {meta['years']}.")
    return year


def _seasons(season: str) -> list[str] | None:
    return {"RS": ["RS"], "PO": ["PO"], "all": None}[season]


def _rnd(x: Any) -> Any:
    """Round floats recursively so payloads stay small and readable."""
    if isinstance(x, float):
        return round(x, 4) if abs(x) < 1 else round(x, 2)
    if isinstance(x, dict):
        return {k: _rnd(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_rnd(v) for v in x]
    return x


def _matchup_row(m: dict) -> dict:
    """Compact form of a weekly_leaderboard/head_to_head matchup row."""
    result = "W" if m.get("matchup_win") else "L" if m.get("matchup_loss") else "T"
    return {
        "team": m["team"],
        "opponent": m["opponent"],
        "year": m["year"],
        "week": m["week"],
        "season": m["season"],
        "result": result,
        "category_score": f"{m['cat_wins']}-{m['cat_losses']}-{m['cat_ties']}",
        "stats": m["stats"],
        "week_rating_0_100": m.get("rating"),
        "week_rank": m.get("rank"),
    }


SeasonFilter = Literal["RS", "PO", "all"]
RO = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)


# --------------------------------------------------------------------------
# Server + tools
# --------------------------------------------------------------------------

INSTRUCTIONS = """\
Stats for a private 9-category NBA fantasy basketball league (Yahoo, head-to-head, 2019 season onward).
Call league_info first: it explains the league's rules and quirks, which you need to read the numbers correctly.
Key facts:
- Teams are named after their managers (e.g. "Fano", "Amil"). A season is named by the year it ends (2026 = the 2025-26 NBA season).
- "Week" means a fantasy matchup period, numbered from 1 each season. Most are 7 days, but some are longer (the All-Star break, some playoff rounds) or shorter (week 1). Weekly totals from a long matchup aren't comparable with a normal week. team_week_records reports each matchup's days, so mention it when it matters.
- RS = regular season, PO = playoffs. For "all-time record" questions about a single week, include both unless the user says otherwise, but point out when the top result was a long matchup.
- TO (turnovers) is lower-is-better. FG% and FT% are percentages: never sum them across weeks.
- Use team_week_records for single-week records ("most rebounds in a week", "most points in week 2"). Use stats_query for career or season totals and averages, and for any slicing the other tools don't cover.
"""

mcp = MCPServer(
    name="Unis Fantasy GOAT",
    instructions=INSTRUCTIONS,
    website_url="https://unis-fantasy-goat.vercel.app",
    version="1.0.0",
)


def _logged(fn):
    """Log each tool call (name + args) so we can see what people ask for."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        t0 = time.monotonic()
        try:
            out = fn(*args, **kwargs)
            log.info("tool=%s args=%s ok %.0fms", fn.__name__, json.dumps(kwargs, default=str), (time.monotonic() - t0) * 1000)
            return out
        except ToolError as exc:
            log.info("tool=%s args=%s error=%s", fn.__name__, json.dumps(kwargs, default=str), exc)
            raise SDKToolError(str(exc)) from None
        except httpx.HTTPError as exc:
            log.warning("tool=%s args=%s upstream error=%r", fn.__name__, json.dumps(kwargs, default=str), exc)
            raise SDKToolError("The league stats API is temporarily unavailable. Try again in a minute.") from None

    return wrapper


@mcp.tool(annotations=RO)
@_logged
def league_info(year: int | None = None) -> dict:
    """League overview: members, seasons, current season/week, categories, each season's
    scoring format, playoff sizes, and the matchup calendar (week -> dates) for `year`
    (defaults to the current season). Read this first."""
    meta = _meta()
    y = _year(year)
    cal = _calendar(y)
    total = meta["total_matchup_count"].get(str(y))
    weeks = [
        {"week": w, "start": r["StartDate"], "end": r["EndDate"]}
        for w, r in sorted(cal.items())
        if total is None or w <= total
    ]
    return {
        "teams_ever": meta["members"],
        "seasons": meta["years"],
        "current_season": meta["current_year"],
        "current_week": meta["current_week"],
        "categories": meta["categories"],
        "category_notes": "9-category H2H. TO is lower-is-better. FG%/FT% are ratios (made/attempted), not counting stats.",
        "season_format": meta["season_format"],
        "season_format_notes": (
            "'wl': standings/seeding by matchup wins-losses-ties (each week is one W, L or T). "
            "'cats': standings/seeding by total category wins (each week counts as up to 9 category results)."
        ),
        "regular_season_weeks": meta["rs_week_count"],
        "total_matchups_incl_playoffs": meta["total_matchup_count"],
        "playoff_teams": meta["playoff_team_count"],
        "playoff_rounds": meta["playoff_rounds"],
        "goat": meta.get("goat"),
        "week_notes": (
            "The current week flips at 2 AM ET Monday, so stats for the current week are partial. "
            "A season is named by the year it ends."
        ),
        f"calendar_{y}": weeks,
    }


@mcp.tool(annotations=RO)
@_logged
def team_week_records(
    stat: str,
    weeks: list[int] | None = None,
    years: list[int] | None = None,
    teams: list[str] | None = None,
    opponents: list[str] | None = None,
    season: SeasonFilter = "all",
    lowest: bool = False,
    limit: int = 10,
) -> dict:
    """Single-week records: the best (or, with lowest=true, worst) individual team matchup-weeks
    for one stat, across all history unless filtered. Use for questions like "most rebounds in a
    week ever", "most points in week 2", "Fano's best steals week in 2024", "fewest turnovers in
    the playoffs".

    stat: PTS, REB, AST, STL, BLK, TO, 3PTM, FG%, FT%, FGM, FGA, FTM, FTA, 3PTA.
    weeks: matchup week numbers within a season (e.g. [2] = week 2 of every season).
    season: "RS" (regular season), "PO" (playoffs) or "all".
    lowest: true for the lowest values (for TO, lowest is the best).
    Each row includes the matchup's dates and length in days. Point out any multi-week matchup.
    """
    limit = max(1, min(limit, 50))
    out = _post(
        "/query",
        {
            "metric": stat,
            "aggregation": "sum",  # one row per team per matchup-week, so sum == that week's value
            "group_by": ["Team", "Opp", "Year", "Week", "Season"],
            "years": years,
            "weeks": weeks,
            "teams": _teams(teams),
            "opponents": _teams(opponents),
            "seasons": _seasons(season),
            "sort_desc": not lowest,
            "limit": limit,
        },
    )
    rows = []
    for r in out["rows"]:
        cal = _calendar(int(r["Year"])).get(int(r["Week"]))
        row = {
            "team": r["Team"],
            "opponent": r["Opp"],
            "year": r["Year"],
            "week": r["Week"],
            "season": r["Season"],
            "value": r["value"],
        }
        if cal:
            days = (date.fromisoformat(cal["EndDate"]) - date.fromisoformat(cal["StartDate"])).days + 1
            row.update(start=cal["StartDate"], end=cal["EndDate"], days=days)
        rows.append(row)
    return _rnd({"stat": out["metric"], "order": "lowest first" if lowest else "highest first", "rows": rows})


@mcp.tool(annotations=RO)
@_logged
def stats_query(
    metric: str,
    aggregation: Literal["sum", "avg", "min", "max", "count", "rank"] = "sum",
    group_by: list[str] = ["Team"],
    years: list[int] | None = None,
    weeks: list[int] | None = None,
    teams: list[str] | None = None,
    opponents: list[str] | None = None,
    season: SeasonFilter = "all",
    ascending: bool = False,
    limit: int = 25,
) -> dict:
    """Flexible aggregate over the league's per-team, per-matchup-week data: any metric, any
    aggregation, grouped and filtered as needed. Use for career/season totals and averages,
    win counts, and anything the other tools don't cover.

    metric: a box-score stat (PTS, REB, AST, STL, BLK, TO, 3PTM, FG%, FT%, FGM, FGA, FTM, FTA, 3PTA)
      or a results metric: MATCHUP_WINS, MATCHUP_LOSSES, MATCHUP_DRAWS, WIN_PCT, CAT_WINS,
      CAT_LOSSES, CAT_TIES, ALL_PLAY_WINS/LOSSES/TIES (record if you had played every team each week),
      ALL_PLAY_POINTS_AVG (expected wins), SCHEDULE_LUCK, DRAFT_SCORE, DRAFT_PICK_COUNT.
    aggregation: sum | avg (per-week average) | min | max | count (number of weeks) | rank.
      Never "sum" FG%/FT%: use "avg" (an average of weekly percentages).
    group_by: any of Team, Opp, Year, Week, Season. Examples: ["Team"] = career,
      ["Team","Year"] = per season, ["Team","Year","Week"] = single weeks (team_week_records does
      this with dates attached).
    season: "RS", "PO" or "all".
    ascending: true to list the smallest values first.
    """
    limit = max(1, min(limit, 100))
    out = _post(
        "/query",
        {
            "metric": metric,
            "aggregation": aggregation,
            "group_by": group_by,
            "years": years,
            "weeks": weeks,
            "teams": _teams(teams),
            "opponents": _teams(opponents),
            "seasons": _seasons(season),
            "sort_desc": not ascending,
            "limit": limit,
        },
    )
    return _rnd(out)


@mcp.tool(annotations=RO)
@_logged
def weekly_results(year: int | None = None, week: int | None = None) -> dict:
    """Every matchup for one week: each team's stats, opponent, result, category score, and the
    week's power rating/rank (rating 0-100 = how the team's stats ranked against the whole league
    that week). Also includes the weekly recap's upsets, blowouts and milestones when available.
    Defaults to the current season and week (which may still be in progress)."""
    meta = _meta()
    y = _year(year)
    w = week if week is not None else (meta["current_week"] if y == meta["current_year"] else 1)
    board = _post("/league/weekly_leaderboard", {"year": y, "week": w})
    if not board:
        raise ToolError(f"No results for {y} week {w}.")
    try:
        recap = _post("/league/weekly_recap", {"year": y, "week": w})
    except (ToolError, httpx.HTTPError):
        recap = None
    out: dict[str, Any] = {"year": y, "week": w, "teams": [_matchup_row(m) for m in board]}
    if recap:
        out["recap"] = {k: v for k, v in recap.items() if k not in ("rank_table", "posted_at") and v}
    return _rnd(out)


@mcp.tool(annotations=RO)
@_logged
def standings(year: int | None = None, from_week: int = 1, to_week: int | None = None) -> dict:
    """Regular-season standings for a season (default: current), optionally over a week range.
    Returns four tables: "wl" (matchup W-L-T), "cats" (category W-L-T), and the all-play versions
    ("league_*", the record if every team had played every other team each week). The season's
    official format (see league_info season_format) decides which of wl/cats is the real one.
    With from_week=1, rows in the official table include clinched/eliminated flags."""
    meta = _meta()
    y = _year(year)
    rs_weeks = int(meta["rs_week_count"].get(str(y), 18))
    hi = min(to_week or rs_weeks, rs_weeks)
    out = _post("/league/standings", {"year": y, "min_week": from_week, "max_week": hi})
    return _rnd({"year": y, "weeks": [from_week, hi], "official_format": meta["season_format"].get(str(y)), **out})


@mcp.tool(annotations=RO)
@_logged
def team_profile(teams: list[str] | None = None) -> dict:
    """Career profile per team: championships, finals, playoff appearances, MVPs, regular-season
    1st/last-place finishes, career W/L and category records (RS and PO), win/loss streaks, best
    ratings, draft scores, each with the years. Omit teams for every team."""
    rows = _post("/league/team_summary", {"teams": _teams(teams)})
    return _rnd({"teams": [{k: v for k, v in r.items() if v not in (None, "", 0)} | {"Team": r["Team"]} for r in rows]})


@mcp.tool(annotations=RO)
@_logged
def head_to_head(team_a: str, team_b: str, years: list[int] | None = None, season: SeasonFilter = "all") -> dict:
    """All-time (or filtered) head-to-head between two teams: matchup record and category record
    from team_a's point of view, plus every matchup with both teams' stats and the result."""
    a, b = _team(team_a), _team(team_b)
    out = _post(
        "/league/head_to_head",
        {"team_a": a, "team_b": b, "years": years, "RS": season != "PO", "PO": season != "RS"},
    )
    return _rnd(
        {
            "team_a": a,
            "team_b": b,
            "record": out["record"],
            "category_record": out["category_record"],
            "matchups": [_matchup_row(m) for m in out.get("matchups", [])],
        }
    )


@mcp.tool(annotations=RO)
@_logged
def records(years: list[int] | None = None, season: SeasonFilter = "all") -> dict:
    """League record book: best overall single week (by power rating), best single week per
    category, and longest win streaks. Single-week category records can come from long multi-week
    matchups. For filtered or ranked lists use team_week_records."""
    out = _post("/league/records", {"years": years, "RS": season != "PO", "PO": season != "RS"})
    best = out.get("best_week_overall")
    if best:
        out["best_week_overall"] = _matchup_row(best)
    return _rnd(out)


@mcp.tool(annotations=RO)
@_logged
def season_stats(
    years: list[int] | None = None,
    mode: Literal["totals", "averages"] = "totals",
    weeks: list[int] | None = None,
    season: SeasonFilter = "all",
) -> dict:
    """Per-team category totals or per-week averages over the selected seasons/weeks (all history
    if years is omitted), with each team's rank. The rating (0-1) is how the team's numbers
    compare to the rest of the league. A new manager with few weeks played can look extreme on
    totals, so use averages to compare teams with different numbers of weeks played."""
    body = {"years": years, "weeks": weeks, "RS": season != "PO", "PO": season != "RS"}
    out = _post("/league/totals" if mode == "totals" else "/league/averages", body)
    return _rnd({"mode": mode, "years": years or "all", "teams": out})


@mcp.tool(annotations=RO)
@_logged
def roster(team: str, year: int | None = None) -> dict:
    """A team's roster for a season (default: current): each player, NBA team, lineup slot
    (IR = injured reserve, BN = bench) and current player rank (lower = better)."""
    t = _team(team)
    y = _year(year)
    rows = _post("/league/roster_ranks", {"year": y})
    players = [
        {"player": r["Player"], "nba_team": r.get("NBATeam"), "slot": r.get("LineupSlot"), "rank": r.get("Rank")}
        for r in rows
        if r.get("FantasyTeam") == t
    ]
    if not players:
        raise ToolError(f"No roster found for {t} in {y}.")
    players.sort(key=lambda p: (p["rank"] is None, p["rank"] or 0))
    return {"team": t, "year": y, "players": players}


@mcp.tool(annotations=RO)
@_logged
def draft(year: int | None = None, team: str | None = None) -> dict:
    """Draft picks for a season (default: current), optionally for one team: round, pick, overall
    pick number, player, the player's end-of-season (or current) rank, and Score = overall pick
    minus rank (how much value the pick returned vs. its draft slot; higher = better pick,
    negative = the player finished worse than where he was drafted)."""
    y = _year(year)
    rows = _post("/league/draft_picks", {"years": [y], "teams": [_team(team)] if team else None})
    rows.sort(key=lambda r: r.get("Overall") or 0)
    return _rnd({"year": y, "picks": rows})


@mcp.tool(annotations=RO)
@_logged
def playoffs(year: int | None = None) -> dict:
    """Playoff bracket for a season (default: most recent one with playoffs): seeds, each round's
    matchups and winners, the champion and final standings, plus the regular-season finishing
    order. Always includes every season's champion."""
    brackets = _cached("brackets", lambda: _get("/league/playoff_brackets"))
    finish = _cached("rs_finish", lambda: _get("/league/rs_finish_history"))
    champions = {y: b.get("champion") for y, b in brackets.items()}
    if year is None:
        year = int(max(brackets))
    b = brackets.get(str(year))
    if b is None:
        raise ToolError(f"No playoff bracket for {year}. Seasons with playoffs: {sorted(brackets)}.")
    return {"year": year, "bracket": b, "regular_season_finish": finish.get(str(year)), "champions_by_year": champions}


@mcp.tool(annotations=RO)
@_logged
def nba_schedule(start_date: str, end_date: str) -> dict:
    """NBA games per team between two dates (YYYY-MM-DD, at most 14 days apart). Useful for
    'which NBA teams play the most games this week' streaming questions."""
    games = _post("/league/nba_schedule", {"start_date": start_date, "end_date": end_date})
    per_team: dict[str, int] = defaultdict(int)
    for g in games:
        per_team[g["HomeTeam"]] += 1
        per_team[g["AwayTeam"]] += 1
    return {
        "start_date": start_date,
        "end_date": end_date,
        "games_per_team": dict(sorted(per_team.items(), key=lambda kv: (-kv[1], kv[0]))),
        "games": [{"date_utc": g["Date"], "home": g["HomeTeam"], "away": g["AwayTeam"]} for g in games],
    }


# --------------------------------------------------------------------------
# HTTP app (streamable HTTP, stateless) + per-IP rate limit
# --------------------------------------------------------------------------


class RateLimit(BaseHTTPMiddleware):
    def __init__(self, app, per_min: int):
        super().__init__(app)
        self.per_min = per_min
        self.hits: dict[str, deque] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/mcp/health":
            return await call_next(request)
        ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0].strip()
        now = time.monotonic()
        q = self.hits[ip]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= self.per_min:
            return JSONResponse({"error": "rate limited, try again in a minute"}, status_code=429)
        q.append(now)
        if len(self.hits) > 5000:  # keep memory bounded
            self.hits = defaultdict(deque, {k: v for k, v in self.hits.items() if v and now - v[-1] < 60})
        return await call_next(request)


def build_app():
    # host="0.0.0.0" leaves DNS-rebinding protection off: this runs behind Caddy, is public and
    # read-only, and the Host header is the public sslip.io name.
    app = mcp.streamable_http_app(streamable_http_path="/mcp", stateless_http=True, json_response=True, host="0.0.0.0")

    async def health(_request):
        return PlainTextResponse("ok")

    app.add_route("/mcp/health", health)
    app.add_middleware(RateLimit, per_min=RATE_LIMIT_PER_MIN)
    return app


app = build_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8091")), proxy_headers=True, forwarded_allow_ips="*")
