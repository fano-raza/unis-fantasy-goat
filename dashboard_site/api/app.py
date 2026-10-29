from __future__ import annotations

import hmac
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import daily_games_store
from .league_store import get_league_store, reset_league_store
from .query_engine import StatsStore
from .schemas import (
    AggregateRequest,
    HeadToHeadRequest,
    LeadersRequest,
    MetaResponse,
    NBAScheduleRequest,
    QueryRequest,
    QueryResponse,
    DraftPicksRequest,
    GamesDailyWinsRequest,
    GamesLeaderboardRequest,
    GamesPlaysRequest,
    GamesTopScoresRequest,
    RecordsRequest,
    RosterCategoryOddsRequest,
    TradeOddsRequest,
    TradeRecommendRequest,
    RosterOptimizerPasswordRequest,
    RosterOptimizerRequest,
    RosterRanksRequest,
    ScheduleSwapRequest,
    SeasonLeadersRequest,
    StandingsRequest,
    TeamSummaryRequest,
    TimeSeriesRequest,
    WeekCalendarRequest,
    WeeklyLeaderboardRequest,
    WeeklyTeamRequest,
)

app = FastAPI(title="Fantasy Dashboard API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# GET /league/* endpoints are read-only snapshots of in-memory data that's
# only ever as fresh as the last _refresh_data() pass anyway (every 5 min,
# see below) -- letting the browser reuse a response for a short window
# costs at most a few seconds of extra staleness on top of that, in
# exchange for skipping a full round trip to the droplet on repeat
# navigation/back-forward/multi-tab. Scoped to GET only; POST endpoints
# (user-driven queries with arbitrary filters) are left alone since
# browsers don't cache non-GET responses regardless.
@app.middleware("http")
async def add_short_cache_header(request: Request, call_next):
    response = await call_next(request)
    if request.method == "GET" and request.url.path.startswith("/refresh_status"):
        # Open pages poll this to decide when to re-fetch their tables -- a
        # cached answer would delay every live update by up to its max-age.
        response.headers["Cache-Control"] = "no-store"
    elif request.method == "GET" and request.url.path.startswith(("/league/", "/meta")):
        response.headers["Cache-Control"] = "public, max-age=30, stale-while-revalidate=60"
    return response

store = StatsStore()
league_store = get_league_store(store)

# stat-updater (a separate container) recomputes the CSVs under FANTASY_REF_DIR
# on its own schedule -- but NOT all on the same schedule: *_CompStats.csv
# updates every ~2 minutes during game hours (a separate, more frequent loop
# in stat_updater.py), while draft results / player_stats.csv / team_summary.csv
# only refresh once during the once-daily(-ish) branch. A single global
# "newest file" timestamp was misleading -- it almost always reflected the
# fast-moving CompStats files, so a page showing yesterday's draft data could
# still claim "Updated 2 minutes ago." Track per-source mtimes instead.
# dashboard-api only reads these CSVs into memory once at boot, so without a
# periodic reload it would keep serving a stale in-memory snapshot
# indefinitely. Governs ONLY the actual data reload now -- /refresh_status's
# freshness badge scans file mtimes live on every request instead of
# reading this cycle's cached result (see refresh_status() below for why).
# Was 5 minutes -- fine back when nothing refreshed meaningfully faster than
# that, but stat_updater.py's game-hours loop now writes genuinely live
# scores to *_CompStats.csv every ~2 minutes (this session's cumulativeScoreLive
# fix). Lowered to stay close behind that cadence instead of trailing it by
# more than double.
REFRESH_INTERVAL_SECONDS = 90

_state_lock = threading.Lock()


def _newest_mtime(paths: list[Path]) -> datetime | None:
    mtimes = [p.stat().st_mtime for p in paths if p.is_file()]
    if not mtimes:
        return None
    return datetime.fromtimestamp(max(mtimes), tz=timezone.utc)


def _scan_source_mtimes(ref_dir: Path, data_store: StatsStore) -> dict[str, datetime | None]:
    """Per-source freshness, one entry per distinct refresh cadence -- see
    the comment above REFRESH_INTERVAL_SECONDS for why this is a per-source
    dict rather than a single global max. "draft" reuses StatsStore._resolve_draft_roots()'s
    exact glob (not reinvented) so this stays in sync with wherever
    _load_draft_picks actually looks."""
    draft_paths: list[Path] = []
    for root in data_store._resolve_draft_roots():
        draft_paths.extend(root.glob("*/**/*Draft Results.csv"))
    return {
        "live": _newest_mtime(list(ref_dir.glob("*_CompStats.csv"))),
        "draft": _newest_mtime(draft_paths),
        "player_stats": _newest_mtime([ref_dir / "player_stats.csv"]),
        "team_summary": _newest_mtime([ref_dir / "team_summary.csv"]),
    }


def _iso_sources(sources: dict[str, datetime | None]) -> dict[str, str | None]:
    return {k: v.isoformat() if v else None for k, v in sources.items()}


def _refresh_data() -> None:
    global store, league_store, loaded_sources
    # Scanned BEFORE reading the files, so these timestamps never claim newer
    # data than what actually got loaded (a write landing mid-reload just
    # shows up on the next cycle).
    scanned = _iso_sources(_scan_source_mtimes(store.ref_dir, store))
    new_store = StatsStore()
    reset_league_store()
    new_league_store = get_league_store(new_store)
    with _state_lock:
        store = new_store
        league_store = new_league_store
        loaded_sources = scanned


def _refresh_loop() -> None:
    while True:
        time.sleep(REFRESH_INTERVAL_SECONDS)
        try:
            _refresh_data()
        except Exception as exc:
            print(f"dashboard data refresh failed: {exc}")


# Per-source file timestamps as of the data currently in memory -- what open
# pages compare to decide when re-fetching would actually return new numbers
# (see /refresh_status). Lags `sources` by up to one reload cycle.
loaded_sources: dict[str, str | None] = _iso_sources(_scan_source_mtimes(store.ref_dir, store))

threading.Thread(target=_refresh_loop, daemon=True).start()


def _trade_warm_loop() -> None:
    """Keeps every team's league-wide trade recommendation precomputed for
    the current data (premium Trade Hub), so "Recommend trade" is usually
    instant instead of a 15-20 s search on this small server. Only when
    premium is configured; already-cached teams are skipped, so after the
    first pass this only does work when rosters or the daily data change."""
    time.sleep(60)  # let the first data load and requests settle
    while True:
        if os.environ.get("ROSTER_OPTIMIZER_PASSWORD"):
            try:
                with _state_lock:
                    current = league_store
                done = current.warm_trade_recommendations()
                if done:
                    print(f"trade recommendations precomputed for {done} teams")
            except Exception as exc:
                print(f"trade recommendation warm-up failed: {exc}")
        time.sleep(600)


threading.Thread(target=_trade_warm_loop, daemon=True).start()


@app.get("/health")
def health() -> dict[str, str]:
    # Used to be a dumb static check -- "the process is up" -- which is
    # exactly why it didn't catch any of the real incidents today (empty
    # CSV, non-unique multi-index, NaN crashes): the uvicorn process was
    # always up, league_store.meta() was what kept throwing. Now actually
    # exercises the data path the deploy script's post-deploy check (and
    # every /league/* endpoint) depends on -- cheap after the first call,
    # since meta() caches itself on the LeagueStore instance.
    league_store.meta()
    return {"status": "ok"}


@app.get("/refresh_status")
def refresh_status() -> dict[str, str | dict[str, str | None] | None]:
    # Scans file mtimes live on every call instead of reading the
    # _refresh_data() cache -- a stat() call is essentially free, and this
    # is the "Updated X ago" freshness badge every page shows, so it should
    # report the real, current file state rather than being gated by the
    # same (slower) cadence as the actual in-memory data reload. Confirmed
    # live: with the old cached version, the badge could claim "Updated 2
    # min ago" while the data it was describing was still a stale snapshot
    # from several minutes before that, since both numbers came from the
    # same reload. Grabs `store` under the lock (a plain reference swap,
    # cheap) so the scan always uses the StatsStore that's actually live
    # right now, even if a reload is mid-flight.
    with _state_lock:
        current_store = store
        current_loaded = loaded_sources
    sources = _iso_sources(_scan_source_mtimes(current_store.ref_dir, current_store))
    return {
        # Kept for any existing consumer of the old flat shape.
        "last_updated": sources.get("live"),
        "sources": sources,
        # What the API is actually serving right now; when one of these
        # changes, open pages quietly re-fetch (web/src/lib/live-data.tsx).
        "loaded": current_loaded,
    }


@app.get("/meta", response_model=MetaResponse)
def meta() -> MetaResponse:
    return MetaResponse(**store.available_meta())


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest) -> QueryResponse:
    try:
        out = store.query(
            metric=req.metric,
            aggregation=req.aggregation,
            group_by=req.group_by,
            years=req.years,
            weeks=req.weeks,
            teams=req.teams,
            opponents=req.opponents,
            seasons=req.seasons,
            count_only=req.count_only,
            sort_desc=req.sort_desc,
            limit=req.limit,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    rows = out.to_dict(orient="records")
    return QueryResponse(
        rows=rows,
        row_count=len(rows),
        metric=req.metric,
        aggregation=req.aggregation,
    )


@app.post("/timeseries", response_model=QueryResponse)
def timeseries(req: TimeSeriesRequest) -> QueryResponse:
    try:
        out = store.timeseries(
            metric=req.metric,
            aggregation=req.aggregation,
            group_by=req.group_by,
            years=req.years,
            weeks=req.weeks,
            teams=req.teams,
            opponents=req.opponents,
            seasons=req.seasons,
            count_only=req.count_only,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    rows = out.to_dict(orient="records")
    return QueryResponse(
        rows=rows,
        row_count=len(rows),
        metric=req.metric,
        aggregation=req.aggregation,
    )


@app.post("/schedule_swap", response_model=QueryResponse)
def schedule_swap(req: ScheduleSwapRequest) -> QueryResponse:
    try:
        out = store.schedule_swap(
            years=req.years,
            weeks=req.weeks,
            teams=req.teams,
            seasons=req.seasons,
            limit=req.limit,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    rows = out.to_dict(orient="records")
    return QueryResponse(
        rows=rows,
        row_count=len(rows),
        metric="SCHEDULE_LUCK",
        aggregation="sum",
    )


@app.get("/league/meta")
def league_meta() -> dict:
    return league_store.meta()


@app.get("/league/weekly_stats_bootstrap")
def league_weekly_stats_bootstrap() -> dict:
    # Combines /league/meta + /league/weekly_leaderboard (current year/week)
    # + the current year's *entire* season (every week, see
    # weekly_leaderboard_season) into one response -- so the Weekly Stats
    # page's initial load pays a single network round-trip to the droplet,
    # and switching weeks within the current year afterward is a client-
    # side cache lookup, not a fresh fetch. All three pieces are already
    # cheap/cached (see meta()'s and weekly_leaderboard()'s own caching),
    # so RTT was the actual cost here, not computation.
    m = league_store.meta()
    year, week = m.get("current_year"), m.get("current_week")
    rows: list[dict] = []
    season: dict[int, list[dict]] = {}
    if year is not None and week is not None:
        try:
            rows = league_store.weekly_leaderboard(year, week)
        except ValueError:
            rows = []
        season = league_store.weekly_leaderboard_season(year)
    return {"meta": m, "rows": rows, "season": season}


@app.get("/league/weekly_leaderboard_season")
def league_weekly_leaderboard_season(year: int) -> dict[int, list[dict]]:
    # On-demand version of the above, for when the client switches to a
    # year that wasn't the one the page loaded with -- see
    # weekly-stats-view.tsx's seasonCache.
    return league_store.weekly_leaderboard_season(year)


@app.get("/league/category_history")
def league_category_history() -> dict:
    return league_store.category_history()


@app.get("/league/rs_finish_history")
def league_rs_finish_history() -> dict:
    return league_store.rs_finish_history()


@app.get("/league/playoff_brackets")
def league_playoff_brackets() -> dict:
    return league_store.playoff_brackets()


@app.get("/league/player_stats")
def league_player_stats() -> list[dict]:
    try:
        return league_store.player_stats()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/league/weekly_team")
def league_weekly_team(req: WeeklyTeamRequest) -> dict:
    try:
        return league_store.weekly_team(req.year, req.week, req.team)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/league/weekly_leaderboard")
def league_weekly_leaderboard(req: WeeklyLeaderboardRequest) -> list[dict]:
    try:
        return league_store.weekly_leaderboard(req.year, req.week)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/league/weekly_recap")
def league_weekly_recap(req: WeeklyLeaderboardRequest) -> dict | None:
    return league_store.weekly_recap(req.year, req.week)


@app.post("/league/totals")
def league_totals(req: AggregateRequest) -> list[dict]:
    return league_store.totals(years=req.years, weeks=req.weeks, teams=req.teams, RS=req.RS, PO=req.PO)


@app.post("/league/averages")
def league_averages(req: AggregateRequest) -> list[dict]:
    return league_store.averages(years=req.years, weeks=req.weeks, teams=req.teams, RS=req.RS, PO=req.PO)


@app.post("/league/leaders")
def league_leaders(req: LeadersRequest) -> dict:
    return league_store.leaders(years=req.years, RS=req.RS, PO=req.PO)


@app.post("/league/season_leaders")
def league_season_leaders(req: SeasonLeadersRequest) -> dict:
    return league_store.season_leaders(
        years=req.years, weeks=req.weeks, RS=req.RS, PO=req.PO, mode=req.mode
    )


@app.post("/league/head_to_head")
def league_head_to_head(req: HeadToHeadRequest) -> dict:
    try:
        return league_store.head_to_head(req.team_a, req.team_b, years=req.years, RS=req.RS, PO=req.PO)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/league/records")
def league_records(req: RecordsRequest) -> dict:
    try:
        return league_store.records(years=req.years, RS=req.RS, PO=req.PO)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/league/analysis_rows")
def league_analysis_rows(req: AggregateRequest) -> list[dict]:
    return league_store.analysis_rows(years=req.years, weeks=req.weeks, teams=req.teams, RS=req.RS, PO=req.PO)


@app.post("/league/team_summary")
def league_team_summary(req: TeamSummaryRequest) -> list[dict]:
    return league_store.team_summary(teams=req.teams)


@app.post("/league/roster_ranks")
def league_roster_ranks(req: RosterRanksRequest) -> list[dict]:
    try:
        return league_store.roster_ranks(req.year)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _check_roster_optimizer_password(password: str) -> None:
    """The password lives only in the server's environment
    (ROSTER_OPTIMIZER_PASSWORD, set from infra/docker/env/dashboard-api.env on
    the droplet) -- never in the frontend bundle. Unset -> the feature is off
    (503); wrong -> 401."""
    expected = os.environ.get("ROSTER_OPTIMIZER_PASSWORD", "")
    if not expected:
        raise HTTPException(status_code=503, detail="The roster optimizer isn't set up on this server.")
    if not hmac.compare_digest(password.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Wrong password.")


@app.post("/premium/check_password")
@app.post("/league/roster_optimizer/check_password")
def premium_check_password(req: RosterOptimizerPasswordRequest) -> dict:
    """Premium mode login: confirms the password (the same one every premium
    feature checks server-side) without running anything. The old
    /league/roster_optimizer/check_password path is kept as an alias."""
    _check_roster_optimizer_password(req.password)
    return {"ok": True}


@app.post("/league/roster_category_odds")
def league_roster_category_odds(req: RosterCategoryOddsRequest) -> dict:
    """Premium: per-category weekly win probabilities for a team's roster, before
    and after the Roster page's manual what-if swaps."""
    _check_roster_optimizer_password(req.password)
    try:
        return league_store.roster_category_odds(req.team, req.roster)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/league/trade_odds")
def league_trade_odds(req: TradeOddsRequest) -> dict:
    """Premium: both teams' weekly win probabilities before and after a Trade Hub
    trade."""
    _check_roster_optimizer_password(req.password)
    try:
        return league_store.trade_odds(req.team_a, req.team_b, req.a_sends, req.b_sends, req.drops)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/league/trade_recommend")
def league_trade_recommend(req: TradeRecommendRequest) -> dict:
    """Premium: the Trade Finder's recommendation for team A (fair first,
    else the least lopsided trade that still helps team A)."""
    _check_roster_optimizer_password(req.password)
    try:
        return league_store.trade_recommend(req.team_a, req.team_b, req.give)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/league/roster_optimizer")
def league_roster_optimizer(req: RosterOptimizerRequest) -> dict:
    """Password-gated Roster Optimizer (_planning/roster-optimizer.md)."""
    _check_roster_optimizer_password(req.password)
    try:
        return league_store.roster_optimizer(req.team, req.max_swaps)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/league/nba_schedule")
def league_nba_schedule(req: NBAScheduleRequest) -> list[dict]:
    try:
        return league_store.nba_schedule(req.start_date, req.end_date)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/league/week_calendar")
def league_week_calendar(req: WeekCalendarRequest) -> list[dict]:
    try:
        return league_store.week_calendar(req.year)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/league/standings")
def league_standings(req: StandingsRequest) -> dict:
    try:
        return league_store.standings(req.year, req.min_week, req.max_week)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/league/standings_history")
def league_standings_history(req: StandingsRequest) -> dict:
    return league_store.standings_history(req.year, req.min_week, req.max_week)


@app.get("/league/standings_bootstrap")
def league_standings_bootstrap() -> dict:
    return league_store.standings_bootstrap()


@app.get("/league/ratings_bootstrap")
def league_ratings_bootstrap() -> dict:
    return league_store.ratings_bootstrap()


@app.get("/league/career_bootstrap")
def league_career_bootstrap() -> dict:
    return league_store.career_bootstrap()


@app.get("/league/ultra_bootstrap")
def league_ultra_bootstrap() -> dict:
    return league_store.ultra_bootstrap()


@app.post("/league/draft_picks")
def league_draft_picks(req: DraftPicksRequest) -> list[dict]:
    return league_store.draft_picks(years=req.years, teams=req.teams)


# #daily-games stats (Worldle, MapTap, ...) -- same logic as StatBot's Discord
# commands, see daily_games_store.py. Used by the MCP server's game tools.
@app.get("/games/meta")
def games_meta() -> dict:
    return daily_games_store.meta()


@app.post("/games/leaderboard")
def games_leaderboard(req: GamesLeaderboardRequest) -> list[dict]:
    try:
        return daily_games_store.leaderboard(req.game, req.days_back)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/games/top_scores")
def games_top_scores(req: GamesTopScoresRequest) -> list[dict]:
    try:
        return daily_games_store.top_scores(req.game, req.n, req.min_date, req.max_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/games/daily_wins")
def games_daily_wins(req: GamesDailyWinsRequest) -> list[dict]:
    try:
        return daily_games_store.daily_wins(req.game, req.rank)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/games/plays")
def games_plays(req: GamesPlaysRequest) -> list[dict]:
    try:
        return daily_games_store.plays(req.game, req.player, req.min_date, req.max_date, req.limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


web_dir = (Path(__file__).resolve().parents[1] / "web").resolve()
app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(str(web_dir / "index.html"))
