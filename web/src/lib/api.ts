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

export interface RosterRankRow {
  Year: number;
  // null for a free agent -- not on any fantasy roster that season.
  FantasyTeam: string | null;
  Player: string;
  NBATeam: string;
  Rank: number;
}

export interface RosterRanksRequest {
  year: number;
}

export interface NBAScheduleGame {
  Date: string;
  HomeTeam: string;
  AwayTeam: string;
}

export interface NBAScheduleRequest {
  start_date: string;
  end_date: string;
}

export interface WeekCalendarRow {
  Year: number;
  Week: number;
  StartDate: string;
  EndDate: string;
}

export interface WeekCalendarRequest {
  year: number;
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
  // GET bootstrap/meta endpoints now send a short (30s) Cache-Control from
  // the backend (see app.py's add_short_cache_header) -- letting the
  // browser's own HTTP cache honor that (instead of forcing "no-store")
  // means repeat navigation/back-forward/multi-tab can skip the round
  // trip to the droplet entirely. POST endpoints are user-driven ad-hoc
  // queries and stay "no-store": browsers never cache non-GET anyway, but
  // being explicit keeps intent clear. Exception: a caller passing its own
  // `next.revalidate` (the server components that fetch a default POST
  // bootstrap, e.g. draft picks) -- Next's fetch rejects `cache` and
  // `next.revalidate` set together, so an explicit `next` always wins and
  // `cache` is left for Next/the browser to decide.
  const hasExplicitRevalidate = (init as { next?: { revalidate?: unknown } } | undefined)?.next?.revalidate !== undefined;
  const isGet = !init?.method || init.method === "GET";
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    cache: hasExplicitRevalidate ? undefined : isGet ? undefined : "no-store",
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

function post<T>(path: string, body: unknown, init?: RequestInit): Promise<T> {
  return apiFetch<T>(path, { ...init, method: "POST", body: JSON.stringify(body) });
}

export const getLeagueMeta = (init?: RequestInit) => apiFetch<LeagueMeta>("/league/meta", init);

// Every week of a season, keyed by week number as a string (JSON object
// keys are always strings, even though the backend's dict is int-keyed --
// see dashboard_site/api/league_store.py::weekly_leaderboard_season).
export type SeasonWeeks = Record<string, WeekRow[]>;

export interface WeeklyStatsBootstrap {
  meta: LeagueMeta;
  rows: WeekRow[];
  // Every week of meta.current_year, for weekly-stats-view.tsx's
  // seasonCache -- switching weeks within the year the page loaded with
  // is then a client-side lookup, not a fresh fetch.
  season: SeasonWeeks;
}

// Combines meta + the current week's leaderboard + the whole current
// season into one round-trip, for the Weekly Stats page's initial load
// (see dashboard_site/api/app.py's /league/weekly_stats_bootstrap for why
// this exists instead of the separate calls below). Takes an optional
// `init` so the server component in app/page.tsx can pass
// `{ next: { revalidate: 30 } }` -- that fetch runs during SSR/ISR rather
// than after the client hydrates, and Next's Data Cache then serves repeat
// requests within that window without touching the backend at all.
export const getWeeklyStatsBootstrap = (init?: RequestInit) =>
  apiFetch<WeeklyStatsBootstrap>("/league/weekly_stats_bootstrap", init);

// On-demand version of the season slice above, for switching to a year
// that wasn't the one the page loaded with.
export const getWeeklyLeaderboardSeason = (year: number) =>
  apiFetch<SeasonWeeks>(`/league/weekly_leaderboard_season?year=${year}`);

export const getWeeklyTeam = (req: WeeklyTeamRequest) =>
  post<WeekRow>("/league/weekly_team", req);

export const getWeeklyLeaderboard = (req: WeeklyLeaderboardRequest) =>
  post<WeekRow[]>("/league/weekly_leaderboard", req);

// StatBot's Monday "Week N Recap" Discord post, mirrored for the web
// page -- null if that week hasn't had a recap posted yet (a normal case,
// not an error: past weeks only get one once the Monday job actually
// runs). See discord/weekly_rankings.py and
// dashboard_site/api/league_store.py::weekly_recap(). rank_table isn't
// surfaced here -- the page's own StatTable already shows this week's
// ranks, no need to duplicate it.
export interface RegularSeasonWeeklyRecap {
  kind: "regular_season";
  year: number;
  week: number;
  beatdowns: string[];
  upsets: string[];
  milestones: string[];
  playoff_race: string | null;
  posted_at: string;
}

// Playoff-week counterpart (feature request, 2026-10-07) -- built live from
// the precomputed playoff bracket (see PlayoffMatchup above, same shape
// playoff_brackets() already returns), not an AI-commented Discord post, so
// there's no posted_at/beatdowns/upsets/milestones. champion/final_standings
// are only populated on the last round once that year's bracket is Complete.
// Only decided matchups (winner set) are ever included here.
export interface PlayoffWeeklyRecap {
  kind: "playoff";
  year: number;
  week: number;
  round_label: string;
  byes: string[];
  matchups: PlayoffMatchup[];
  champion: string | null;
  final_standings: Record<string, string> | null;
}

export type WeeklyRecap = RegularSeasonWeeklyRecap | PlayoffWeeklyRecap;

export const getWeeklyRecap = (req: WeeklyLeaderboardRequest) =>
  post<WeeklyRecap | null>("/league/weekly_recap", req);

export const getTotals = (req: AggregateRequest = {}, init?: RequestInit) =>
  post<AggregateRow[]>("/league/totals", req, init);

export const getAverages = (req: AggregateRequest = {}, init?: RequestInit) =>
  post<AggregateRow[]>("/league/averages", req, init);

export interface CareerBootstrap {
  meta: LeagueMeta;
  years: number[];
  weeks: number[];
  teams: string[];
  rows: AggregateRow[];
  previous_rows: AggregateRow[];
}

// Combines meta + Career Stats' default (everything selected) totals into
// one round-trip (see league_store.py's career_bootstrap()). Not a fit for
// Analysis, which restores a persisted custom filter from localStorage
// client-side rather than always defaulting to "everything."
export const getCareerBootstrap = (init?: RequestInit) =>
  apiFetch<CareerBootstrap>("/league/career_bootstrap", init);

export interface UltraBootstrap {
  meta: LeagueMeta;
  year: number | null;
  weeks: number[];
  rows: AggregateRow[];
}

// Combines meta + Ultra's default (current year, every week, averages) rows
// into one round-trip (see league_store.py's ultra_bootstrap()).
export const getUltraBootstrap = (init?: RequestInit) =>
  apiFetch<UltraBootstrap>("/league/ultra_bootstrap", init);

export const getLeaders = (req: LeadersRequest = {}) =>
  post<LeadersResponse>("/league/leaders", req);

export const getSeasonLeaders = (req: SeasonLeadersRequest) =>
  post<SeasonLeadersResponse>("/league/season_leaders", req);

export const getCategoryHistory = (init?: RequestInit) =>
  apiFetch<CategoryHistoryResponse>("/league/category_history", init);

export const getRsFinishHistory = () =>
  apiFetch<RsFinishHistoryResponse>("/league/rs_finish_history");

export const getHeadToHead = (req: HeadToHeadRequest) =>
  post<HeadToHeadResponse>("/league/head_to_head", req);

export const getRecords = (req: RecordsRequest = {}) =>
  post<RecordsResponse>("/league/records", req);

export const getAnalysisRows = (req: AggregateRequest = {}) =>
  post<AnalysisRow[]>("/league/analysis_rows", req);

export const getTeamSummary = (req: TeamSummaryRequest = {}, init?: RequestInit) =>
  post<TeamSummary[]>("/league/team_summary", req, init);

export const getRosterRanks = (req: RosterRanksRequest) =>
  post<RosterRankRow[]>("/league/roster_ranks", req);

export const getNBASchedule = (req: NBAScheduleRequest) =>
  post<NBAScheduleGame[]>("/league/nba_schedule", req);

export const getWeekCalendar = (req: WeekCalendarRequest) =>
  post<WeekCalendarRow[]>("/league/week_calendar", req);

export const getStandings = (req: StandingsRequest) =>
  post<StandingsResponse>("/league/standings", req);

export const getStandingsHistory = (req: StandingsRequest) =>
  post<StandingsHistoryResponse>("/league/standings_history", req);

export interface StandingsBootstrap {
  meta: LeagueMeta;
  year: number | null;
  week_range: [number, number];
  standings: StandingsResponse | null;
  previous_standings: StandingsResponse | null;
  history: StandingsHistoryResponse | null;
}

// Combines meta + the current year's default-range standings/history into
// one round-trip, for the Standings and League Wins pages' initial load
// (mirrors getWeeklyStatsBootstrap -- see dashboard_site/api/league_store.py's
// standings_bootstrap()).
export const getStandingsBootstrap = (init?: RequestInit) =>
  apiFetch<StandingsBootstrap>("/league/standings_bootstrap", init);

export interface RatingsBootstrap {
  meta: LeagueMeta;
  year: number | null;
  week_range: [number, number];
  rows: AggregateRow[];
  previous_rows: AggregateRow[];
  leaders: SeasonLeadersResponse;
  history: AnalysisRow[];
}

// Same combining trick as getStandingsBootstrap, for the Ratings page's
// default filters (see league_store.py's ratings_bootstrap()).
export const getRatingsBootstrap = (init?: RequestInit) =>
  apiFetch<RatingsBootstrap>("/league/ratings_bootstrap", init);

export const getPlayoffBrackets = () =>
  apiFetch<PlayoffBracketsResponse>("/league/playoff_brackets");

export type StatWindow = "season" | "d7" | "d14" | "d30" | "d90";

// Real NBA player stats (scripts/export_player_stats.py, via nba_api) for
// the Players page's Trade Hub. Loosely typed rather than one field per of
// the ~100 {window}_{cat}_{total|avg|made|att} columns -- see
// web/src/app/players/page.tsx's getPlayerCatValue for the accessor that
// builds the right key.
export interface PlayerStat {
  PlayerId: number;
  Player: string;
  Team: string;
  [field: string]: number | string | null;
}

export const getPlayerStats = (init?: RequestInit) => apiFetch<PlayerStat[]>("/league/player_stats", init);

export const getDraftPicks = (req: DraftPicksRequest = {}, init?: RequestInit) =>
  post<DraftPick[]>("/league/draft_picks", req, init);

export type RefreshSource = "live" | "draft" | "player_stats" | "team_summary";

export interface RefreshStatus {
  // ISO 8601, or null if the backend hasn't found any ref-dir CSVs yet --
  // kept for back-compat, equal to sources.live.
  last_updated: string | null;
  // Per-source freshness -- different ref-dir files refresh on genuinely
  // different cadences (live *_CompStats.csv every ~2min during game hours
  // vs. draft/player_stats/team_summary once daily-ish), so a single global
  // timestamp was misleading. See SourceLastUpdated for the per-page display.
  sources: Record<RefreshSource, string | null>;
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

export const getQuery = (req: QueryRequest, init?: RequestInit) => post<QueryResponse>("/query", req, init);
