from __future__ import annotations

from datetime import date
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


class RosterRanksRequest(BaseModel):
    year: int


class RosterOptimizerPasswordRequest(BaseModel):
    password: str


class RosterCategoryOddsRequest(BaseModel):
    team: str
    password: str
    # The hypothetical ACTIVE roster (player names); omitted -> real roster.
    roster: list[str] | None = Field(None, max_length=30)


class RosterOptimizerRequest(BaseModel):
    team: str
    password: str
    # Upper bound is the team's roster size, clamped server-side.
    max_swaps: int = Field(3, ge=1, le=20)


class WeekCalendarRequest(BaseModel):
    year: int


class NBAScheduleRequest(BaseModel):
    start_date: str  # "YYYY-MM-DD"
    end_date: str  # "YYYY-MM-DD"


class DraftPicksRequest(BaseModel):
    years: list[int] | None = None
    teams: list[str] | None = None


class StandingsRequest(BaseModel):
    year: int
    min_week: int
    max_week: int


class GamesLeaderboardRequest(BaseModel):
    game: str
    days_back: int | None = Field(None, ge=1, description="Last N days; omit for all time")


class GamesTopScoresRequest(BaseModel):
    game: str
    n: int = Field(10, ge=1, le=50)
    min_date: date | None = None
    max_date: date | None = None


class GamesDailyWinsRequest(BaseModel):
    game: str
    rank: Literal[1, 2, "last"] = 1


class GamesPlaysRequest(BaseModel):
    game: str | None = None
    player: str | None = None
    min_date: date | None = None
    max_date: date | None = None
    limit: int = Field(100, ge=1, le=500)

