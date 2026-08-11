from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


Aggregation = Literal["sum", "avg", "min", "max", "count", "rank"]


class QueryRequest(BaseModel):
    metric: str = Field(..., description="Metric alias or canonical metric key")
    aggregation: Aggregation = "sum"
    group_by: list[str] = Field(default_factory=lambda: ["Team"])

    years: list[int] | None = None
    weeks: list[int] | None = None
    teams: list[str] | None = None
    opponents: list[str] | None = None
    seasons: list[str] | None = Field(default=None, description="RS and/or PO")
    count_only: bool = True

    sort_desc: bool = True
    limit: int = 25


class TimeSeriesRequest(BaseModel):
    metric: str
    aggregation: Literal["sum", "avg"] = "sum"
    group_by: Literal["Week", "Year"] = "Week"

    years: list[int] | None = None
    weeks: list[int] | None = None
    teams: list[str] | None = None
    opponents: list[str] | None = None
    seasons: list[str] | None = None
    count_only: bool = True


class QueryResponse(BaseModel):
    rows: list[dict]
    row_count: int
    metric: str
    aggregation: str


class MetaResponse(BaseModel):
    years: list[int]
    weeks: list[int]
    teams: list[str]
    opponents: list[str]
    metrics: dict[str, str]


class ScheduleSwapRequest(BaseModel):
    years: list[int] | None = None
    weeks: list[int] | None = None
    teams: list[str] | None = None
    seasons: list[str] | None = None
    limit: int = 25


class WeeklyTeamRequest(BaseModel):
    year: int
    week: int
    team: str


class WeeklyLeaderboardRequest(BaseModel):
    year: int
    week: int


class AggregateRequest(BaseModel):
    years: list[int] | None = None
    weeks: list[int] | None = None
    teams: list[str] | None = None
    RS: bool = True
    PO: bool = True


class LeadersRequest(BaseModel):
    years: list[int] | None = None
    RS: bool = True
    PO: bool = True


class SeasonLeadersRequest(BaseModel):
    years: list[int] | None = None
    weeks: list[int] | None = None
    RS: bool = True
    PO: bool = True
    mode: str = "totals"


class HeadToHeadRequest(BaseModel):
    team_a: str
    team_b: str
    years: list[int] | None = None
    RS: bool = True
    PO: bool = True


class RecordsRequest(BaseModel):
    years: list[int] | None = None
    RS: bool = True
    PO: bool = True


class TeamSummaryRequest(BaseModel):
    teams: list[str] | None = None


class DraftPicksRequest(BaseModel):
    years: list[int] | None = None
    teams: list[str] | None = None


class StandingsRequest(BaseModel):
    year: int
    min_week: int
    max_week: int
