// Which of a fantasy team's NBA games this week counted / will count --
// the one set of rules behind the Roster page's full-week grid AND the
// Weekly Stats page's Games column (user request 2026-10-31: the two must
// match exactly), so neither page re-derives it on its own.
//
// Per scheduled game (user spec 2026-10-31):
//   counted  -- past, he played in a lineup spot: stats counted
//   missed   -- past, didn't count: not on the roster that day, on the bench
//               or IR, or didn't play (0 minutes / injured)
//   upcoming -- healthy and in the lineup
//   doubtful -- upcoming, listed day-to-day (still counted)
//   benched  -- upcoming, currently in a bench slot (not counted)
//   out      -- upcoming but on IR, injured, or no longer on the roster
// "Played" = counted; "expected" = counted + upcoming + doubtful.

import type { NBAScheduleGame, RosterRankRow, RosterWeekPlayer } from "@/lib/api";

export type GameState = "counted" | "missed" | "upcoming" | "doubtful" | "benched" | "out";

const EASTERN_TZ = "America/New_York";

// Game dates group by Eastern date: a 10PM ET tip-off is already
// "tomorrow" in UTC.
export function easternDateKey(isoDate: string): string {
  return new Date(isoDate).toLocaleDateString("en-CA", { timeZone: EASTERN_TZ });
}

export function todayKey(): string {
  return new Date().toLocaleDateString("en-CA", { timeZone: EASTERN_TZ });
}

/** NBA team abbreviation -> the days (ET) it plays in `games`. */
export function gameDaysByNBATeam(games: NBAScheduleGame[]): Map<string, Set<string>> {
  const map = new Map<string, Set<string>>();
  for (const game of games) {
    const day = easternDateKey(game.Date);
    for (const abbr of [game.HomeTeam, game.AwayTeam]) {
      if (!map.has(abbr)) map.set(abbr, new Set());
      map.get(abbr)!.add(day);
    }
  }
  return map;
}

/** One team's week of lineup / games-played / injury data (from
 * /league/roster_week_status or /league/week_status), ready to judge games. */
export interface TeamWeek {
  players: Record<string, RosterWeekPlayer>;
  gameLogsThrough: string | null;
  // Days the lineup history covers -- on those, a player with no slot
  // wasn't on this roster.
  historyDays: Set<string>;
  today: string;
  // False when there's no lineup data at all (endpoint failed, old season):
  // past games are then assumed to have counted.
  hasData: boolean;
}

export function teamWeek(
  players: Record<string, RosterWeekPlayer> | null | undefined,
  gameLogsThrough: string | null | undefined,
  today: string,
): TeamWeek {
  const historyDays = new Set<string>();
  for (const p of Object.values(players ?? {})) for (const d of Object.keys(p.slots)) historyDays.add(d);
  return {
    players: players ?? {},
    gameLogsThrough: gameLogsThrough ?? null,
    historyDays,
    today,
    hasData: players != null && historyDays.size > 0,
  };
}

export interface RowOptions {
  // A what-if player shown in another's slot (Roster page swaps) -- judged
  // as if he'd been added (his current IR/bench slot ignored).
  swappedIn?: boolean;
  // On this roster earlier in the week, not anymore -- his upcoming games
  // can't count.
  departed?: boolean;
}

export function gameState(tw: TeamWeek, row: RosterRankRow, day: string, opts: RowOptions = {}): GameState {
  const status = tw.players[row.Player];
  const played = status?.played.includes(day) ?? false;
  // Today's game counts as past once he's logged playing in it.
  const past = day < tw.today || (day === tw.today && played);
  if (past) {
    if (!tw.hasData) return "counted"; // no data: assume it counted
    const slot = status?.slots[day];
    if (tw.historyDays.has(day) && !slot) return "missed"; // not on this roster that day
    if (slot === "BE" || slot === "IR") return "missed";
    const logsCover = tw.gameLogsThrough != null && day <= tw.gameLogsThrough;
    if (logsCover && !played) return "missed"; // injured / 0 minutes
    return "counted";
  }
  if (opts.departed) return "out";
  const slots = status ? Object.entries(status.slots).sort(([a], [b]) => a.localeCompare(b)) : [];
  const latestSlot = slots.length ? slots[slots.length - 1][1] : row.LineupSlot;
  if (status?.out || (!opts.swappedIn && latestSlot === "IR")) return "out";
  if (!opts.swappedIn && latestSlot === "BE") return "benched";
  if (status?.injury_status === "DAY_TO_DAY") return "doubtful";
  return "upcoming";
}

export const isExpected = (s: GameState) => s === "counted" || s === "upcoming" || s === "doubtful";
const isLeft = (s: GameState) => s === "upcoming" || s === "doubtful";

/** One player's week: games still to come that will count (`left`) and
 * every game that counted or will (`total`); played = total - left. */
export function rowGameCounts(
  tw: TeamWeek,
  row: RosterRankRow,
  days: Set<string> | undefined,
  opts: RowOptions = {},
): { left: number; total: number } {
  let left = 0;
  let total = 0;
  for (const day of days ?? []) {
    const state = gameState(tw, row, day, opts);
    if (isLeft(state)) left++;
    if (isExpected(state)) total++;
  }
  return { left, total };
}

/** Players on this team earlier in the week who aren't on `currentNames`
 * anymore (dropped / traded) -- their games for the team still count. */
export function departedRows(
  tw: TeamWeek,
  currentNames: Set<string>,
  rowsByName: Map<string, RosterRankRow>,
  year: number,
): RosterRankRow[] {
  return Object.keys(tw.players)
    .filter((name) => !currentNames.has(name))
    .map((name) => rowsByName.get(name) ?? { Year: year, FantasyTeam: null, Player: name, NBATeam: "", Rank: NaN })
    .sort((a, b) => a.Player.localeCompare(b.Player));
}

export interface CountedRow extends RowOptions {
  row: RosterRankRow;
}

/** A whole team's week: games played (counted so far) and expected
 * (played + still to come), across every row incl. departed players. */
export function teamGameTotals(
  tw: TeamWeek,
  rows: CountedRow[],
  daysByNBATeam: Map<string, Set<string>>,
): { played: number; left: number; total: number } {
  let left = 0;
  let total = 0;
  for (const r of rows) {
    const c = rowGameCounts(tw, r.row, daysByNBATeam.get(r.row.NBATeam), r);
    left += c.left;
    total += c.total;
  }
  return { played: total - left, left, total };
}
