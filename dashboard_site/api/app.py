from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .league_store import get_league_store
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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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


web_dir = (Path(__file__).resolve().parents[1] / "web").resolve()
app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(str(web_dir / "index.html"))
