from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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
    RecordsRequest,
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

store = StatsStore()
league_store = get_league_store(store)

# gdoc-updater (a separate container) recomputes the CSVs under FANTASY_REF_DIR
# on its own schedule -- but NOT all on the same schedule: *_CompStats.csv
# updates every ~2 minutes during game hours (a separate, more frequent loop
# in GDoc_updater.py), while draft results / player_stats.csv / team_summary.csv
# only refresh once during the once-daily(-ish) branch. A single global
# "newest file" timestamp was misleading -- it almost always reflected the
# fast-moving CompStats files, so a page showing yesterday's draft data could
# still claim "Updated 2 minutes ago." Track per-source mtimes instead.
# dashboard-api only reads these CSVs into memory once at boot, so without a
# periodic reload it would keep serving a stale snapshot indefinitely.
REFRESH_INTERVAL_SECONDS = 5 * 60

_state_lock = threading.Lock()
_source_mtimes: dict[str, datetime | None] = {}


def _newest_mtime(paths: list[Path]) -> datetime | None:
    mtimes = [p.stat().st_mtime for p in paths if p.is_file()]
    if not mtimes:
        return None
    return datetime.fromtimestamp(max(mtimes), tz=timezone.utc)


def _scan_source_mtimes(ref_dir: Path, data_store: StatsStore) -> dict[str, datetime | None]:
    """Per-source freshness, one entry per distinct refresh cadence -- see
    the "sources" docstring above `_source_mtimes` for why this replaced a
    single global max. "draft" reuses StatsStore._resolve_draft_roots()'s
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


def _refresh_data() -> None:
    global store, league_store, _source_mtimes
    new_store = StatsStore()
    reset_league_store()
    new_league_store = get_league_store(new_store)
    mtimes = _scan_source_mtimes(new_store.ref_dir, new_store)
    with _state_lock:
        store = new_store
        league_store = new_league_store
        _source_mtimes = mtimes


def _refresh_loop() -> None:
    while True:
        time.sleep(REFRESH_INTERVAL_SECONDS)
        try:
            _refresh_data()
        except Exception as exc:
            print(f"dashboard data refresh failed: {exc}")


_source_mtimes = _scan_source_mtimes(store.ref_dir, store)
threading.Thread(target=_refresh_loop, daemon=True).start()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/refresh_status")
def refresh_status() -> dict[str, str | dict[str, str | None] | None]:
    with _state_lock:
        sources = {k: v.isoformat() if v else None for k, v in _source_mtimes.items()}
        return {
            # Kept for any existing consumer of the old flat shape.
            "last_updated": sources.get("live"),
            "sources": sources,
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


@app.post("/league/draft_picks")
def league_draft_picks(req: DraftPicksRequest) -> list[dict]:
    return league_store.draft_picks(years=req.years, teams=req.teams)


web_dir = (Path(__file__).resolve().parents[1] / "web").resolve()
app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(str(web_dir / "index.html"))
