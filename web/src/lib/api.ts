// Typed client for the dashboard_site FastAPI backend (`dashboard_site/api/app.py`).
// Response shapes mirror `dashboard_site/api/league_store.py`; request shapes mirror
// `dashboard_site/api/schemas.py`. See _planning/web-app-build-plan.md Phase 1 for the
// backend side of this contract.

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8090";

export const MAIN_CATS = [
  "FG%",
  "FT%",
  "3PTM",
  "REB",
  "AST",
  "STL",
  "BLK",
  "TO",
  "PTS",
] as const;

export type Category = (typeof MAIN_CATS)[number];

export type CategoryStats = Partial<Record<Category, number>>;

export interface LeagueMeta {
  years: number[];
  members: string[];
  current_year: number;
  current_week: number;
  rs_week_count: Record<string, number>;
  playoff_rounds: Record<string, number>;
  total_matchup_count: Record<string, number>;
  categories: Category[];
  // Some seasons were actually scored by matchup W/L, others by aggregate
  // category wins -- used to default the Standings page's toggles.
  season_format: Record<string, "wl" | "cats">;
  // Most Championships, tiebreak MVPs, then RS 1st Place, then career
  // head-to-head among the remaining tied teams. null only if there's no
  // team_summary data at all.
  goat: string | null;
}

export interface WeekRow {
  team: string;
  // "BYE" for a team with no opponent that week -- stats are still real,
  // but every comparison-derived field below is null (nothing to compare
  // against).
  opponent: string;
  year: number;
  week: number;
  season: "RS" | "PO";
  stats: CategoryStats;
  ratings: CategoryStats;
  cat_wins: number | null;
  cat_losses: number | null;
  cat_ties: number | null;
  matchup_win: boolean | null;
  matchup_loss: boolean | null;
  matchup_tie: boolean | null;
  rating: number | null;
  rank: number | null;
}

export interface AggregateRow {
  team: string;
  stats: CategoryStats;
  ratings: CategoryStats;
  rating: number;
  rank: number;
}

export interface AnalysisRow {
  team: string;
  opponent: string;
  year: number;
  week: number;
  season: "RS" | "PO";
  stats: CategoryStats;
  ratings: CategoryStats;
  ranks: CategoryStats;
  week_rating: number;
  week_rank: number;
  cat_wins: number;
  cat_losses: number;
  cat_ties: number;
  matchup_win: boolean;
  opponent_rating: number | null;
}

// Keys/values mirror scripts/export_team_summary.py's output columns exactly
// (spaces and all) -- used directly as row labels in the Comparison page.
export type TeamSummary = Record<string, string | number | null> & { Team: string };

export interface CategoryLeader {
  team?: string;
  value?: number;
}

export type LeadersResponse = Partial<Record<Category, CategoryLeader>>;

export interface HeadToHeadResponse {
  team_a: string;
  team_b: string;
  record: { wins: number; losses: number; ties: number };
  category_record: { wins: number; losses: number; ties: number };
  matchups: WeekRow[];
}

export interface CategoryRecord extends CategoryLeader {
  year?: number;
  week?: number;
}

export interface WinStreak {
  team: string;
  longest_win_streak: number;
}

export interface RecordsResponse {
  best_week_overall: WeekRow;
  best_week_by_category: Partial<Record<Category, CategoryRecord>>;
  longest_win_streaks: WinStreak[];
}

export interface WeeklyTeamRequest {
  year: number;
  week: number;
  team: string;
}

export interface WeeklyLeaderboardRequest {
  year: number;
  week: number;
}

export interface AggregateRequest {
  years?: number[];
  weeks?: number[];
  teams?: string[];
  RS?: boolean;
  PO?: boolean;
}

export interface LeadersRequest {
  years?: number[];
  RS?: boolean;
  PO?: boolean;
}

export interface HeadToHeadRequest {
  team_a: string;
  team_b: string;
  years?: number[];
  RS?: boolean;
  PO?: boolean;
}

export interface RecordsRequest {
  years?: number[];
  RS?: boolean;
  PO?: boolean;
}

export interface TeamSummaryRequest {
  teams?: string[];
}

export interface DraftPicksRequest {
  years?: number[];
  teams?: string[];
}

export interface DraftPick {
  Year: number;
  Round: number;
  Pick: number;
  Overall: number;
  Player: string;
  Team: string;
  // "N/A" for a still-in-progress draft's picks.
  Rank: string;
  Score: number;
}

export interface StandingsRequest {
  year: number;
  min_week: number;
  max_week: number;
}

export interface SeasonLeadersRequest {
  years?: number[];
  weeks?: number[];
  RS?: boolean;
  PO?: boolean;
  mode?: "totals" | "averages";
}

export interface SeasonLeaderEntry {
  team: string;
  value: number;
}

export interface SeasonLeadersResponse {
  [category: string]: { best: SeasonLeaderEntry; worst: SeasonLeaderEntry };
}

// year -> category -> {best, worst} -- RS-totals league leader/lowest per
// category per season, powering Profile's per-category badges.
export type CategoryHistoryResponse = Record<string, SeasonLeadersResponse>;

// year -> team -> RS standings rank (full RS range, that season's real
// scoring format) -- powers Profile's rating/place-finish-by-season chart.
export type RsFinishHistoryResponse = Record<string, Record<string, number>>;

export interface StandingsRow {
  team: string;
  wins: number;
  losses: number;
  ties: number;
  rank: number;
}

export interface StandingsResponse {
  wl: StandingsRow[];
  cats: StandingsRow[];
  league_wl: StandingsRow[];
  league_cats: StandingsRow[];
}

export interface StandingsHistoryPoint {
  week: number;
  rank: number;
}

export interface StandingsHistoryResponse {
  wl: Record<string, StandingsHistoryPoint[]>;
  cats: Record<string, StandingsHistoryPoint[]>;
  league_wl: Record<string, StandingsHistoryPoint[]>;
  league_cats: Record<string, StandingsHistoryPoint[]>;
}

export interface PlayoffMatchup {
  team1: string;
  team2: string;
  seed1: number | null;
  seed2: number | null;
  winner: string | null;
  loser: string | null;
  wins: number;
  losses: number;
  ties: number;
  tiebreak_applied: boolean;
  tiebreak_reason: string | null;
  // Only present on the Final round's two matchups.
  slot?: "Final" | "3rd Place";
}

export interface PlayoffRound {
  week: number;
  label: string;
  byes: string[];
  matchups: PlayoffMatchup[];
}

export interface PlayoffBracket {
  status: "Active" | "Complete";
  team_count: number;
  seeding: Record<string, string>;
  champion: string | null;
  standings: Record<string, string>;
  rounds: PlayoffRound[];
}

// year -> bracket, only present for years with a real (non-empty) playoff
// field -- e.g. 2020 (playoffTeamCount 0) is absent entirely.
export type PlayoffBracketsResponse = Record<string, PlayoffBracket>;

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new ApiError(res.status, body || res.statusText);
  }

  return res.json() as Promise<T>;
}

function post<T>(path: string, body: unknown): Promise<T> {
  return apiFetch<T>(path, { method: "POST", body: JSON.stringify(body) });
}

export const getLeagueMeta = () => apiFetch<LeagueMeta>("/league/meta");

export const getWeeklyTeam = (req: WeeklyTeamRequest) =>
  post<WeekRow>("/league/weekly_team", req);

export const getWeeklyLeaderboard = (req: WeeklyLeaderboardRequest) =>
  post<WeekRow[]>("/league/weekly_leaderboard", req);

export const getTotals = (req: AggregateRequest = {}) =>
  post<AggregateRow[]>("/league/totals", req);

export const getAverages = (req: AggregateRequest = {}) =>
  post<AggregateRow[]>("/league/averages", req);

export const getLeaders = (req: LeadersRequest = {}) =>
  post<LeadersResponse>("/league/leaders", req);

export const getSeasonLeaders = (req: SeasonLeadersRequest) =>
  post<SeasonLeadersResponse>("/league/season_leaders", req);

export const getCategoryHistory = () =>
  apiFetch<CategoryHistoryResponse>("/league/category_history");

export const getRsFinishHistory = () =>
  apiFetch<RsFinishHistoryResponse>("/league/rs_finish_history");

export const getHeadToHead = (req: HeadToHeadRequest) =>
  post<HeadToHeadResponse>("/league/head_to_head", req);

export const getRecords = (req: RecordsRequest = {}) =>
  post<RecordsResponse>("/league/records", req);

export const getAnalysisRows = (req: AggregateRequest = {}) =>
  post<AnalysisRow[]>("/league/analysis_rows", req);

export const getTeamSummary = (req: TeamSummaryRequest = {}) =>
  post<TeamSummary[]>("/league/team_summary", req);

export const getStandings = (req: StandingsRequest) =>
  post<StandingsResponse>("/league/standings", req);

export const getStandingsHistory = (req: StandingsRequest) =>
  post<StandingsHistoryResponse>("/league/standings_history", req);

export const getPlayoffBrackets = () =>
  apiFetch<PlayoffBracketsResponse>("/league/playoff_brackets");

export const getDraftPicks = (req: DraftPicksRequest = {}) =>
  post<DraftPick[]>("/league/draft_picks", req);

export interface RefreshStatus {
  // ISO 8601, or null if the backend hasn't found any ref-dir CSVs yet.
  last_updated: string | null;
}

export const getRefreshStatus = () =>
  apiFetch<RefreshStatus>("/refresh_status");

export interface QueryRequest {
  metric: string;
  aggregation?: "sum" | "avg" | "min" | "max" | "count" | "rank";
  group_by?: string[];
  years?: number[];
  weeks?: number[];
  teams?: string[];
  opponents?: string[];
  seasons?: string[];
  count_only?: boolean;
  sort_desc?: boolean;
  limit?: number;
}

export interface QueryRow {
  Team?: string;
  value: number;
}

export interface QueryResponse {
  rows: QueryRow[];
  row_count: number;
  metric: string;
  aggregation: string;
}

export const getQuery = (req: QueryRequest) => post<QueryResponse>("/query", req);
