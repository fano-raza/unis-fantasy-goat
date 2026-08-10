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
    QueryRequest,
    QueryResponse,
    RecordsRequest,
    ScheduleSwapRequest,
    SeasonLeadersRequest,
    StandingsRequest,
    TeamSummaryRequest,
    TimeSeriesRequest,
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
# on its own schedule (roughly daily, plus live-week polling during game
# hours) -- see GDoc/GDoc_updater.py. dashboard-api only reads those CSVs into
# memory once at boot, so without this it would keep serving a stale snapshot
# indefinitely. Reload from disk on a timer instead.
REFRESH_INTERVAL_SECONDS = 5 * 60

_state_lock = threading.Lock()
_data_last_updated: datetime | None = None


def _scan_data_mtime(ref_dir: Path) -> datetime | None:
    """Newest mtime among the ref-dir CSVs -- reflects when gdoc-updater
    actually last wrote new data, not merely when this process polled disk."""
    mtimes = [f.stat().st_mtime for f in ref_dir.glob("*.csv") if f.is_file()]
    if not mtimes:
        return None
    return datetime.fromtimestamp(max(mtimes), tz=timezone.utc)


def _refresh_data() -> None:
    global store, league_store, _data_last_updated
    new_store = StatsStore()
    reset_league_store()
    new_league_store = get_league_store(new_store)
    data_mtime = _scan_data_mtime(new_store.ref_dir)
    with _state_lock:
        store = new_store
        league_store = new_league_store
        _data_last_updated = data_mtime


def _refresh_loop() -> None:
    while True:
        time.sleep(REFRESH_INTERVAL_SECONDS)
        try:
            _refresh_data()
        except Exception as exc:
            print(f"dashboard data refresh failed: {exc}")


_data_last_updated = _scan_data_mtime(store.ref_dir)
threading.Thread(target=_refresh_loop, daemon=True).start()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/refresh_status")
def refresh_status() -> dict[str, str | None]:
    with _state_lock:
        return {
            "last_updated": _data_last_updated.isoformat() if _data_last_updated else None,
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


@app.post("/league/standings")
def league_standings(req: StandingsRequest) -> dict:
    try:
        return league_store.standings(req.year, req.min_week, req.max_week)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/league/standings_history")
def league_standings_history(req: StandingsRequest) -> dict:
    return league_store.standings_history(req.year, req.min_week, req.max_week)


web_dir = (Path(__file__).resolve().parents[1] / "web").resolve()
app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(str(web_dir / "index.html"))
