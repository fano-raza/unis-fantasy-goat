"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Switch } from "@/components/ui/switch";
import { Button, buttonVariants } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { LabeledSelect } from "@/components/labeled-select";
import { SteppableSelect } from "@/components/steppable-select";
import { LoadingBasketballs } from "@/components/loading-basketballs";
import { LoadingOverlay } from "@/components/loading-overlay";
import { OPTIMIZER_PHRASE_MS, OptimizerResults, RosterOptimizerButton } from "@/components/roster-optimizer";
import { OPTIMIZER_PHRASES } from "@/lib/loading-phrases";
import { RosterCategoryOddsCard } from "@/components/roster-category-odds";
import { RosterWinProbabilityTab } from "@/components/roster-win-probability";
import { cn, shortName } from "@/lib/utils";
import {
  departedRows as findDepartedRows,
  easternDateKey,
  gameDaysByNBATeam,
  gameState as judgeGame,
  isExpected,
  rowGameCounts,
  teamGameTotals,
  teamWeek,
  todayKey,
  type CountedRow,
  type GameState,
} from "@/lib/game-states";
import {
  getNBASchedule,
  getRosterWeekStatus,
  getRosterRanks,
  getWeekCalendar,
  type LeagueMeta,
  type NBAScheduleGame,
  type RosterOptimizerResult,
  type RosterRankRow,
  type RosterWeekStatus,
  type WeekCalendarRow,
} from "@/lib/api";
import { useSelectedTeam } from "@/lib/use-selected-team";
import { ordinal } from "@/lib/team-summary-fields";
import { ArrowDown, ArrowLeftRight, ArrowUp, Crown, RotateCcw, TriangleAlert, X } from "lucide-react";

const EASTERN_TZ = "America/New_York";
// This league starts 10 players -- a day where more than 10 of a team's
// rostered players have real games is a real scheduling conflict (someone
// with a game is forced to sit), worth flagging.
const MAX_STARTERS = 10;

// Circle per game state (rules: lib/game-states.ts, shared with the
// Weekly Stats page). Blue rather than green per the user (2026-10-31).
const GAME_STATE_STYLE: Record<GameState, string> = {
  // Slightly muted (it's in the past) but still clearly blue next to grey.
  counted: "bg-primary/75",
  missed: "bg-muted-foreground/30",
  upcoming: "border-2 border-primary",
  doubtful: "border-2 border-yellow-500",
  benched: "border-2 border-muted-foreground/60",
  out: "border-2 border-loss",
};

const GAME_STATE_LABEL: Record<GameState, string> = {
  counted: "Played, counted",
  missed: "Didn't count",
  upcoming: "Upcoming game",
  doubtful: "Upcoming, day-to-day",
  benched: "Upcoming, on the bench: won't count",
  out: "Upcoming, won't count (IR, injured or off the roster)",
};

// The league's day for week boundaries: the Eastern date, but until 2 AM ET
// it's still the previous day (late West Coast games) -- same cutoff as the
// API's "current week" and stat_updater.py.
function leagueTodayKey(): string {
  const hourMinute = new Date().toLocaleTimeString("en-GB", { timeZone: EASTERN_TZ, hour12: false, hour: "2-digit", minute: "2-digit" });
  const beforeCutoff = hourMinute <= "02:00";
  return new Date(Date.now() - (beforeCutoff ? 24 * 60 * 60 * 1000 : 0)).toLocaleDateString("en-CA", { timeZone: EASTERN_TZ });
}

// Every "YYYY-MM-DD" date in [start, end] inclusive, both ISO date-only
// strings. A fantasy week isn't always a clean 7-day Mon-Sun block --
// ESPN-era week 1 runs Tue-Sun (6 days), and some seasons' playoff
// matchup periods span 2 calendar weeks (14 days) -- so this scales to
// whatever the real range is instead of assuming exactly 7 columns.
function dateRange(start: string, end: string): string[] {
  const days: string[] = [];
  const cursor = new Date(`${start}T12:00:00Z`); // noon UTC avoids DST-edge date-shift on pure-date parsing
  const endDate = new Date(`${end}T12:00:00Z`);
  while (cursor.getTime() <= endDate.getTime()) {
    days.push(cursor.toISOString().slice(0, 10));
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return days;
}

function dayLabel(day: string): string {
  const d = new Date(`${day}T12:00:00Z`);
  const weekday = d.toLocaleDateString("en-US", { timeZone: "UTC", weekday: "short" });
  const md = d.toLocaleDateString("en-US", { timeZone: "UTC", month: "numeric", day: "numeric" });
  return `${weekday} ${md}`;
}

// The most recent week that's already started as of today, real time --
// for the current season this lands on "this week" (or the final week,
// once the season's over); for a past season every week has already
// started, so this always resolves to that season's last week. One
// formula, no isCurrentSeason branch needed.
function latestWeek(weeks: WeekCalendarRow[]): number | null {
  if (weeks.length === 0) return null;
  const today = leagueTodayKey();
  const started = weeks.filter((w) => w.StartDate <= today);
  return started.length > 0 ? started[started.length - 1].Week : weeks[0].Week;
}

function average(values: number[]): number | null {
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
}

export function RosterView({ meta }: { meta: LeagueMeta }) {
  const [year, setYear] = useState(meta.current_year);
  const [team, setTeam] = useSelectedTeam(meta.members[0] ?? "");
  const [week, setWeek] = useState<number | null>(null);
  const [showFullWeek, setShowFullWeek] = useState(false);
  // Roster Rankings sub-tab (user request): average player rank, or the
  // premium win-probability ranking. The latter needs live rosters, so it
  // only applies to the current season -- switching years away from it
  // falls back to Average Rank.
  const [rankingsTab, setRankingsTab] = useState<"avg" | "winprob">("avg");
  useEffect(() => {
    if (year !== meta.current_year) setRankingsTab("avg");
  }, [year, meta.current_year]);

  const [rosterRows, setRosterRows] = useState<RosterRankRow[]>([]);
  const [rosterLoading, setRosterLoading] = useState(true);
  const [rosterError, setRosterError] = useState<string | null>(null);

  const [weekCalendar, setWeekCalendar] = useState<WeekCalendarRow[]>([]);

  const [scheduleGames, setScheduleGames] = useState<NBAScheduleGame[]>([]);
  const [scheduleLoading, setScheduleLoading] = useState(true);

  // Hypothetical swaps: any number of this roster's real "slots" can each
  // be independently replaced with any other rostered player in the
  // league that year. Keyed by the ORIGINAL player each slot represents
  // (not by whatever's currently displayed there), so re-opening a slot
  // that's already been swapped still targets the same slot, not a new
  // one. One-sided -- only this team's roster/rank changes, a replacement
  // player's real team is untouched, since this is a "what if I had them"
  // simulation, not a real trade.
  const [swaps, setSwaps] = useState<Map<string, RosterRankRow>>(new Map());
  // Real roster players simulated as removed outright (the row's X), keyed
  // by original player like `swaps`.
  const [removed, setRemoved] = useState<Set<string>>(new Set());
  const [openSwapSlot, setOpenSwapSlot] = useState<string | null>(null);

  // Roster Optimizer run in progress / its answer, shown in place of the
  // roster table until "Back to roster" (see roster-optimizer.tsx).
  const [optimizing, setOptimizing] = useState(false);
  const [optResult, setOptResult] = useState<RosterOptimizerResult | null>(null);
  // The team on screen right now, for discarding an optimizer answer that
  // arrives after the user has switched teams mid-run.
  const currentTeam = useRef(team);
  useEffect(() => {
    currentTeam.current = team;
  }, [team]);

  // Changing team/year invalidates whatever swaps were being simulated,
  // and any optimizer answer (it was for the previous team).
  useEffect(() => {
    setSwaps(new Map());
    setRemoved(new Set());
    setOptResult(null);
  }, [team, year]);

  useEffect(() => {
    setRosterLoading(true);
    getRosterRanks({ year })
      .then((rows) => {
        setRosterRows(rows);
        setRosterError(null);
      })
      .catch((err) => {
        setRosterRows([]);
        setRosterError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => setRosterLoading(false));
  }, [year]);

  // Week calendar is season-specific (real dates differ by year), so a
  // year switch needs a fresh fetch. Default (and re-default, if the
  // current week is no longer selectable in the new season) to that
  // season's latest started week.
  useEffect(() => {
    getWeekCalendar({ year }).then((rows) => {
      setWeekCalendar(rows);
      const latest = latestWeek(rows);
      const stillValid = latest != null && rows.some((r) => r.Week === week && r.Week >= latest);
      setWeek(stillValid ? week : latest);
    });
    // Deliberately excludes `week` -- this effect should only re-run on a
    // year switch, not every time the user steps to a new week within the
    // same year (that would fight the user's own navigation).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year]);

  const selectedWeek = useMemo(() => weekCalendar.find((w) => w.Week === week) ?? null, [weekCalendar, week]);
  const weekDays = useMemo(
    () => (selectedWeek ? dateRange(selectedWeek.StartDate, selectedWeek.EndDate) : []),
    [selectedWeek],
  );

  // Lineup slots / games played / injury status for this team's week (see
  // gameState below). Optional: if it fails, the grid falls back to the
  // schedule alone (past = counted, upcoming = healthy).
  // Keyed by what it was fetched for, so a team/week switch shows nothing
  // stale while the next one loads.
  const weekStatusKey = selectedWeek && team ? `${year}|${team}|${selectedWeek.StartDate}` : null;
  const [fetchedStatus, setFetchedStatus] = useState<{ key: string; data: RosterWeekStatus } | null>(null);
  const weekStatus = fetchedStatus && fetchedStatus.key === weekStatusKey ? fetchedStatus.data : null;
  useEffect(() => {
    if (!selectedWeek || !team || !weekStatusKey) return;
    let cancelled = false;
    getRosterWeekStatus({ year, team, start_date: selectedWeek.StartDate, end_date: selectedWeek.EndDate })
      .then((data) => !cancelled && setFetchedStatus({ key: weekStatusKey, data }))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [year, team, selectedWeek, weekStatusKey]);

  useEffect(() => {
    if (!selectedWeek) {
      setScheduleGames([]);
      setScheduleLoading(false);
      return;
    }
    setScheduleLoading(true);
    getNBASchedule({ start_date: selectedWeek.StartDate, end_date: selectedWeek.EndDate })
      .then(setScheduleGames)
      .finally(() => setScheduleLoading(false));
  }, [selectedWeek]);

  const teamRoster = useMemo(
    () => rosterRows.filter((r) => r.FantasyTeam === team).sort((a, b) => a.Rank - b.Rank),
    [rosterRows, team],
  );
  // The optimizer's "optimize against" choices: every other team this
  // season (free agents have an empty FantasyTeam and aren't a team).
  const opponents = useMemo(
    () =>
      [...new Set(rosterRows.map((r) => r.FantasyTeam).filter((t): t is string => !!t && t !== team))].sort((a, b) =>
        a.localeCompare(b),
      ),
    [rosterRows, team],
  );

  // Every other player in the league that year -- rostered by someone
  // else, or a free agent (FantasyTeam === "") -- the pool any slot can
  // be swapped to.
  const otherTeamsPlayers = useMemo(
    () => rosterRows.filter((r) => r.FantasyTeam !== team).sort((a, b) => a.Rank - b.Rank),
    [rosterRows, team],
  );

  // This team's players sitting in an IR slot (not playing). Shown greyed
  // out, left out of the win-chance math, and offered first in every other
  // slot's swap menu ("bring him back from IR in place of X").
  const irPlayers = useMemo(() => new Set(teamRoster.filter((r) => r.LineupSlot === "IR").map((r) => r.Player)), [teamRoster]);

  // One "slot" per real roster spot, holding either the real player or
  // whatever they've been hypothetically swapped for. An IR player swapped
  // into another slot is "activated": his own IR row is hidden while he
  // shows in that slot.
  const slots = useMemo(() => {
    const activated = new Set([...swaps.values()].map((r) => r.Player).filter((p) => irPlayers.has(p)));
    return teamRoster
      .filter((orig) => !activated.has(orig.Player))
      .map((orig) => {
        const display = swaps.get(orig.Player) ?? orig;
        return {
          originalPlayer: orig.Player,
          display,
          onIR: irPlayers.has(display.Player) && display.Player === orig.Player,
          removed: removed.has(orig.Player),
        };
      });
  }, [teamRoster, swaps, removed, irPlayers]);
  const sortedSlots = useMemo(() => [...slots].sort((a, b) => a.display.Rank - b.display.Rank), [slots]);
  // Everyone still on the (possibly simulated) roster, IR included -- what
  // Average Rank and Roster Rankings use, same as every other team's.
  const displayedRoster = useMemo(() => sortedSlots.filter((s) => !s.removed).map((s) => s.display), [sortedSlots]);
  // Only players who'd actually play: no IR, no removed.
  const activeRoster = useMemo(() => sortedSlots.filter((s) => !s.removed && !s.onIR).map((s) => s.display), [sortedSlots]);
  const simulating = swaps.size > 0 || removed.size > 0;
  // The simulated active roster for the premium category panel (null = the
  // real roster, no what-if).
  const simulatedActiveNames = useMemo(() => (simulating ? activeRoster.map((r) => r.Player) : null), [simulating, activeRoster]);

  const displayedAvgRank = useMemo(() => average(displayedRoster.map((r) => r.Rank)), [displayedRoster]);

  // Selectable replacements for a given slot -- every other team's
  // player, minus whoever's already occupying one of THIS team's other
  // slots (no duplicating a player across two slots on the same
  // simulated roster).
  function candidatesForSlot(originalPlayer: string): RosterRankRow[] {
    const displayedElsewhere = new Set(
      slots.filter((s) => s.originalPlayer !== originalPlayer).map((s) => s.display.Player),
    );
    return otherTeamsPlayers.filter((r) => !displayedElsewhere.has(r.Player));
  }

  // This team's own IR players that can be brought back in a given slot's
  // place -- not removed, and not already activated into another slot.
  function irCandidatesForSlot(originalPlayer: string): RosterRankRow[] {
    const usedElsewhere = new Set(
      [...swaps.entries()].filter(([orig]) => orig !== originalPlayer).map(([, r]) => r.Player),
    );
    return teamRoster.filter((r) => irPlayers.has(r.Player) && !removed.has(r.Player) && !usedElsewhere.has(r.Player));
  }

  function undoSlot(originalPlayer: string) {
    setSwaps((prev) => {
      const next = new Map(prev);
      next.delete(originalPlayer);
      return next;
    });
  }

  // This team's roster after the optimizer's swaps (null unless an answer
  // with at least one swap is on screen). Incoming players' rows come from
  // roster_ranks, which includes free agents.
  const optimizedRoster = useMemo(() => {
    if (!optResult || optResult.swaps.length === 0) return null;
    const byName = new Map(rosterRows.map((r) => [r.Player, r]));
    const dropped = new Set(optResult.swaps.map((sw) => sw.drop.name));
    return [
      ...teamRoster.filter((r) => !dropped.has(r.Player)),
      ...optResult.swaps.map(
        (sw): RosterRankRow =>
          byName.get(sw.add.name) ?? {
            Year: optResult.year,
            FantasyTeam: null,
            Player: sw.add.name,
            NBATeam: sw.add.nba_team ?? "",
            Rank: NaN,
          },
      ),
    ];
  }, [optResult, rosterRows, teamRoster]);

  const teamAverages = useMemo(() => {
    const byTeam = new Map<string, number[]>();
    for (const row of rosterRows) {
      // Free agents (FantasyTeam === "") aren't a real team -- excluded so
      // they don't show up as a bogus 11th entry in Roster Rankings.
      if (!row.FantasyTeam) continue;
      if (!byTeam.has(row.FantasyTeam)) byTeam.set(row.FantasyTeam, []);
      byTeam.get(row.FantasyTeam)!.push(row.Rank);
    }
    const rows = [...byTeam.entries()].map(([t, ranks]) => {
      const avg = average(ranks) ?? Infinity;
      return { team: t, avgRank: avg, realAvgRank: avg };
    });
    // Swap in the simulated average for this team only -- every other
    // team's real roster/rank is unaffected by a one-sided hypothetical.
    // An optimizer answer on screen takes precedence over manual swaps
    // (running the optimizer clears them anyway).
    const simRoster = optimizedRoster ?? (simulating ? displayedRoster : null);
    if (simRoster) {
      const simAvg = average(simRoster.map((r) => r.Rank).filter(Number.isFinite)) ?? Infinity;
      for (const row of rows) {
        if (row.team === team) row.avgRank = simAvg;
      }
    }
    return rows.sort((a, b) => a.avgRank - b.avgRank);
  }, [rosterRows, simulating, displayedRoster, optimizedRoster, team]);
  const rankingsSimulated = optimizedRoster != null || simulating;

  // This team's place in teamAverages (1-indexed) -- shown inline next to
  // Average Rank so it doesn't require scrolling down to Roster Rankings.
  const teamPlacement = useMemo(() => {
    const idx = teamAverages.findIndex((r) => r.team === team);
    return idx === -1 ? null : idx + 1;
  }, [teamAverages, team]);

  // Where this team would place in Roster Rankings with a given average
  // rank (every other team's real average unchanged).
  function placementFor(avgRank: number): number | null {
    if (!team) return null;
    return teamAverages.filter((r) => r.team !== team && r.avgRank < avgRank).length + 1;
  }

  // NBA team abbreviation -> that week's games, pre-grouped so per-player
  // lookups below are O(1) instead of re-scanning every game per player.
  const gamesByNBATeam = useMemo(() => {
    const map = new Map<string, NBAScheduleGame[]>();
    for (const game of scheduleGames) {
      for (const abbr of [game.HomeTeam, game.AwayTeam]) {
        if (!map.has(abbr)) map.set(abbr, []);
        map.get(abbr)!.push(game);
      }
    }
    return map;
  }, [scheduleGames]);

  // Per-day count of how many of the displayed roster's players have a
  // real game that day -- more than MAX_STARTERS means someone with a
  // game is forced to sit.
  const playersPerDay = useMemo(() => {
    const counts = new Map<string, number>();
    // IR/removed players don't take a starting spot.
    for (const row of activeRoster) {
      const games = gamesByNBATeam.get(row.NBATeam) ?? [];
      const daysPlaying = new Set(games.map((g) => easternDateKey(g.Date)));
      for (const day of daysPlaying) {
        if (weekDays.includes(day)) counts.set(day, (counts.get(day) ?? 0) + 1);
      }
    }
    return counts;
  }, [activeRoster, gamesByNBATeam, weekDays]);

  const today = todayKey();

  // Days the lineup history covers -- on those, a player with no slot
  // wasn't on this roster.
  // This team's week, judged by the shared rules (lib/game-states.ts) --
  // the Weekly Stats page's Games column uses the very same functions.
  const tw = useMemo(
    () => teamWeek(weekStatus?.players, weekStatus?.game_logs_through, today),
    [weekStatus, today],
  );
  const daysByNBATeam = useMemo(() => gameDaysByNBATeam(scheduleGames), [scheduleGames]);

  function gameState(row: RosterRankRow, day: string, swappedIn = false, departed = false): GameState {
    return judgeGame(tw, row, day, { swappedIn, departed });
  }
  function gameCounts(row: RosterRankRow, swappedIn = false, departed = false): { left: number; total: number } {
    return rowGameCounts(tw, row, daysByNBATeam.get(row.NBATeam), { swappedIn, departed });
  }

  // Players on this team at some point this week who aren't anymore
  // (dropped / traded): shown greyed out under the roster, since the games
  // they played for the team still count toward its totals.
  const departedRows = useMemo((): RosterRankRow[] => {
    if (!weekStatus) return [];
    return findDepartedRows(
      tw,
      new Set(teamRoster.map((r) => r.Player)),
      new Map(rosterRows.map((r) => [r.Player, r])),
      year,
    );
  }, [weekStatus, tw, teamRoster, rosterRows, year]);

  // Every row the grid shows, with how to judge it -- for the team totals.
  const countedRows: CountedRow[] = [
    ...sortedSlots
      .filter((s) => !s.removed)
      .map((s) => ({ row: s.display, swappedIn: s.display.Player !== s.originalPlayer, departed: false })),
    ...departedRows.map((row) => ({ row, swappedIn: false, departed: true })),
  ];
  function teamGameCounts(): { left: number; total: number; played: number } {
    return teamGameTotals(tw, countedRows, daysByNBATeam);
  }
  // Games that count (or will) on one day, across the whole team.
  function teamGamesOn(day: string): number {
    return countedRows.filter((r) => daysByNBATeam.get(r.row.NBATeam)?.has(day) && isExpected(gameState(r.row, day, r.swappedIn, r.departed))).length;
  }

  function gameCell(row: RosterRankRow, day: string, swappedIn: boolean, departed: boolean, hasGame: boolean): ReactNode {
    if (!hasGame) return <span className="text-muted-foreground/30">—</span>;
    const state = gameState(row, day, swappedIn, departed);
    return (
      <span
        className={cn("inline-block size-3.5 rounded-full align-middle", GAME_STATE_STYLE[state])}
        role="img"
        aria-label={GAME_STATE_LABEL[state]}
        title={GAME_STATE_LABEL[state]}
      />
    );
  }

  function gamesLeftLabel(row: RosterRankRow): ReactNode {
    if (scheduleLoading) return "…";
    const { left, total } = gameCounts(row);
    return `${left}/${total}`;
  }
  // Roster data isn't week-aware -- Ref/roster_ranks.csv is a single
  // per-season snapshot (frozen end-of-season for closed years, "as of
  // today" for the current year), not tracked week by week. Showing it
  // against an arbitrary PAST week would pair real historical games with
  // a roster that wasn't necessarily accurate back then, so only the
  // latest started week and weeks after it are selectable.
  const weekOptions = useMemo(() => {
    const latest = latestWeek(weekCalendar);
    if (latest == null) return [];
    return weekCalendar.filter((w) => w.Week >= latest).map((w) => w.Week);
  }, [weekCalendar]);
  const atLatestWeek = week != null && week === latestWeek(weekCalendar);
  const avgRankValue = (
    <span className="font-mono font-extrabold tabular-nums text-primary">
      {displayedAvgRank !== null ? displayedAvgRank.toFixed(1) : "—"}
      {teamPlacement !== null && (
        <span className="ml-1 font-sans text-xs font-bold text-muted-foreground">
          ({ordinal(teamPlacement)})
        </span>
      )}
    </span>
  );
  const colSpan = showFullWeek ? Math.max(weekDays.length, 1) : 1;

  return (
    <div className="flex flex-col gap-4">
      <Card variant="plain">
        <CardContent className="flex flex-wrap items-center gap-6">
          <SteppableSelect label="Season" value={year} onValueChange={setYear} options={meta.years} stackOnMobile />
          <LabeledSelect
            stackOnMobile
            label="Team"
            value={team}
            onValueChange={setTeam}
            options={meta.members.map((m) => ({ value: m, label: m }))}
          />
          {weekOptions.length > 0 && week != null && (
            <div className="flex items-end gap-2 sm:items-center">
              <SteppableSelect label="Week" value={week} onValueChange={setWeek} options={weekOptions} stackOnMobile />
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={atLatestWeek}
                onClick={() => setWeek(latestWeek(weekCalendar))}
              >
                Latest Week
              </Button>
            </div>
          )}
          <label className="flex items-center gap-2 label text-foreground">
            <span className="text-muted-foreground">Games Left</span>
            <Switch checked={showFullWeek} onCheckedChange={setShowFullWeek} disabled={optResult != null && optResult.swaps.length > 0} />
            <span className="text-muted-foreground">Full Week Grid</span>
          </label>
          {/* Works on current rosters and free agents, so current season only. */}
          {year === meta.current_year && (
            <RosterOptimizerButton
              team={team}
              rosterSize={teamRoster.length}
              opponents={opponents}
              disabled={optimizing}
              onRunningChange={setOptimizing}
              onResult={(res) => {
                // Ignore an answer for a team the page has since moved off.
                if (res.team !== currentTeam.current) return;
                setSwaps(new Map());
                setRemoved(new Set());
                setOptResult(res);
              }}
            />
          )}
        </CardContent>
      </Card>

      <Card>
        {simulating && !optResult && (
          <CardHeader>
            <CardDescription className="font-semibold text-primary">
              Simulated roster
            </CardDescription>
            <CardAction>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  setSwaps(new Map());
                  setRemoved(new Set());
                }}
              >
                Reset Roster
              </Button>
            </CardAction>
          </CardHeader>
        )}
        <CardContent>
          <LoadingOverlay
            active={rosterLoading || optimizing}
            hasContent={rosterRows.length > 0}
            label={optimizing ? "Optimizing roster" : "Loading roster"}
            phrases={optimizing ? OPTIMIZER_PHRASES : undefined}
            intervalMs={optimizing ? OPTIMIZER_PHRASE_MS : undefined}
          >
          {optResult && (
            <OptimizerResults
              result={optResult}
              format={meta.season_format[String(year)] ?? "wl"}
              roster={teamRoster}
              allPlayers={rosterRows}
              gamesLeft={gamesLeftLabel}
              placementFor={placementFor}
              onClose={() => setOptResult(null)}
            />
          )}
          {optResult && optResult.swaps.length > 0 ? null : rosterError ? (
            <p className="text-sm text-muted-foreground">No roster data for {year} ({rosterError}).</p>
          ) : teamRoster.length === 0 ? (
            <p className="text-sm text-muted-foreground">No roster data for {team} in {year}.</p>
          ) : (
            <>
            {!scheduleLoading && (() => {
              const { played, total } = teamGameCounts();
              return (
                <p className="mb-3 text-sm text-muted-foreground" title="Games that counted so far / games expected to count this week">
                  <span className="font-mono text-base font-extrabold tabular-nums text-primary">
                    {played}/{total}
                  </span>{" "}
                  games played / expected this week
                </p>
              );
            })()}
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="sticky left-0 z-10 bg-card">Player</TableHead>
                  <TableHead className={cn(!showFullWeek && "max-sm:hidden")}>NBA Team</TableHead>
                  {!showFullWeek && <TableHead className="text-right">Rank</TableHead>}
                  {showFullWeek
                    ? weekDays.map((d) => {
                        const count = playersPerDay.get(d) ?? 0;
                        const overStarters = count > MAX_STARTERS;
                        return (
                          <TableHead key={d} className={cn("text-center", d < today && "text-muted-foreground/50")}>
                            <span
                              className="inline-flex items-center justify-center gap-1"
                              title={overStarters ? `${count} players have games -- only ${MAX_STARTERS} starting spots` : undefined}
                            >
                              {dayLabel(d)}
                              {overStarters && <TriangleAlert className="size-3.5 text-loss" />}
                            </span>
                          </TableHead>
                        );
                      })
                    : <TableHead className="text-right">Games Left</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow className="bg-focus-row">
                  <TableCell className="sticky left-0 z-10 bg-focus-row team-name text-primary">
                    Average Rank
                    {showFullWeek && <span className="ml-2">{avgRankValue}</span>}
                  </TableCell>
                  <TableCell className={cn(!showFullWeek && "max-sm:hidden")} />
                  {!showFullWeek && (
                    <TableCell className="text-right font-mono font-extrabold tabular-nums text-primary">
                      {avgRankValue}
                    </TableCell>
                  )}
                  {/* Team totals: games that count (played + still to
                      come), including players who've left the roster. */}
                  {scheduleLoading ? (
                    <TableCell colSpan={colSpan} />
                  ) : showFullWeek ? (
                    weekDays.map((day) => {
                      const n = teamGamesOn(day);
                      return (
                        <TableCell key={day} className="text-center font-mono font-bold tabular-nums text-primary" title={`${n} games that count`}>
                          {n || "—"}
                        </TableCell>
                      );
                    })
                  ) : (
                    (() => {
                      const { left, total } = teamGameCounts();
                      return (
                        <TableCell className="text-right font-mono font-extrabold tabular-nums text-primary" title="Team games left / total this week">
                          {left}/{total}
                        </TableCell>
                      );
                    })()
                  )}
                </TableRow>
                {sortedSlots.map((slot) => {
                  const row = slot.display;
                  const games = gamesByNBATeam.get(row.NBATeam) ?? [];
                  const gameDaysThisWeek = new Set(games.map((g) => easternDateKey(g.Date)));
                  const isSwappedIn = row.Player !== slot.originalPlayer;
                  const { left: remaining, total: totalThisWeek } = gameCounts(row, isSwappedIn);
                  const candidates = candidatesForSlot(slot.originalPlayer);
                  const irCandidates = irCandidatesForSlot(slot.originalPlayer);
                  // IR (still on IR) and removed rows are dimmed: neither plays.
                  const dimmed = slot.onIR || slot.removed;
                  return (
                    <TableRow key={slot.originalPlayer} className={cn(dimmed && "text-muted-foreground [&>td]:opacity-60")}>
                      <TableCell className="sticky left-0 z-10 bg-card font-sans font-semibold">
                        <div className="flex items-center gap-1.5">
                          {slot.onIR || slot.removed ? (
                            // Keeps names aligned with the swappable rows.
                            <span className="size-6 shrink-0" aria-hidden />
                          ) : (
                          <Popover
                            open={openSwapSlot === slot.originalPlayer}
                            onOpenChange={(open) => setOpenSwapSlot(open ? slot.originalPlayer : null)}
                          >
                            <PopoverTrigger
                              className={buttonVariants({ variant: "ghost", size: "icon", className: "size-6 shrink-0" })}
                              title={`Swap ${row.Player}`}
                            >
                              <ArrowLeftRight className="size-3.5" />
                            </PopoverTrigger>
                            <PopoverContent className="w-64 p-0">
                              <Command>
                                <CommandInput placeholder="Search players..." />
                                <CommandList>
                                  <CommandEmpty>No players found.</CommandEmpty>
                                  {irCandidates.length > 0 && (
                                    <CommandGroup heading="Activate from IR">
                                      {irCandidates.map((r) => (
                                        <CommandItem
                                          key={`ir-${r.Player}`}
                                          onSelect={() => {
                                            setSwaps((prev) => new Map(prev).set(slot.originalPlayer, r));
                                            setOpenSwapSlot(null);
                                          }}
                                        >
                                          {r.Player} <span className="ml-1 text-muted-foreground">({r.NBATeam})</span>
                                        </CommandItem>
                                      ))}
                                    </CommandGroup>
                                  )}
                                  <CommandGroup heading={irCandidates.length > 0 ? "Other players" : undefined}>
                                    {candidates.map((r) => (
                                      <CommandItem
                                        key={r.Player}
                                        onSelect={() => {
                                          setSwaps((prev) => new Map(prev).set(slot.originalPlayer, r));
                                          setOpenSwapSlot(null);
                                        }}
                                      >
                                        {r.Player} <span className="ml-1 text-muted-foreground">({r.NBATeam})</span>
                                      </CommandItem>
                                    ))}
                                  </CommandGroup>
                                </CommandList>
                              </Command>
                            </PopoverContent>
                          </Popover>
                          )}
                          <span className={cn(isSwappedIn && "text-yellow-500", slot.removed && "line-through")}>
                            <span className="max-sm:hidden">{row.Player}</span>
                            <span className="sm:hidden">{shortName(row.Player)}</span>
                          </span>
                          {slot.onIR && (
                            <span className="rounded-sm bg-muted px-1 font-sans text-[0.6875rem] font-bold text-muted-foreground" title="On injured reserve: not counted in win probabilities">
                              IR
                            </span>
                          )}
                          {slot.removed ? (
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              className="size-6 shrink-0 text-muted-foreground"
                              title={`Put ${row.Player} back`}
                              aria-label={`Put ${row.Player} back`}
                              onClick={() =>
                                setRemoved((prev) => {
                                  const next = new Set(prev);
                                  next.delete(slot.originalPlayer);
                                  return next;
                                })
                              }
                            >
                              <RotateCcw className="size-3.5" />
                            </Button>
                          ) : (
                            <>
                              {isSwappedIn && (
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="icon"
                                  className="size-6 shrink-0 text-muted-foreground"
                                  title={`Put ${slot.originalPlayer} back`}
                                  aria-label={`Put ${slot.originalPlayer} back`}
                                  onClick={() => undoSlot(slot.originalPlayer)}
                                >
                                  <RotateCcw className="size-3.5" />
                                </Button>
                              )}
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                className="size-6 shrink-0 text-muted-foreground hover:text-loss"
                                title={`Remove ${row.Player} from the roster`}
                                aria-label={`Remove ${row.Player} from the roster`}
                                onClick={() => {
                                  // Removing the slot also drops any swap in it.
                                  undoSlot(slot.originalPlayer);
                                  setRemoved((prev) => new Set(prev).add(slot.originalPlayer));
                                }}
                              >
                                <X className="size-3.5" />
                              </Button>
                            </>
                          )}
                        </div>
                      </TableCell>
                      <TableCell className={cn("text-muted-foreground", !showFullWeek && "max-sm:hidden")}>{row.NBATeam}</TableCell>
                      {!showFullWeek && <TableCell className="text-right font-mono tabular-nums">{row.Rank}</TableCell>}
                      {scheduleLoading ? (
                        <TableCell colSpan={colSpan} className="text-center text-muted-foreground">
                          <LoadingBasketballs />
                        </TableCell>
                      ) : showFullWeek ? (
                        weekDays.map((day) => (
                          <TableCell key={day} className="text-center">
                            {gameCell(row, day, isSwappedIn, false, gameDaysThisWeek.has(day))}
                          </TableCell>
                        ))
                      ) : (
                        <TableCell className="text-right font-mono tabular-nums">
                          {remaining}/{totalThisWeek}
                        </TableCell>
                      )}
                    </TableRow>
                  );
                })}
                {departedRows.map((row) => {
                  const days = new Set((gamesByNBATeam.get(row.NBATeam) ?? []).map((g) => easternDateKey(g.Date)));
                  const { left, total } = gameCounts(row, false, true);
                  return (
                    <TableRow key={`departed-${row.Player}`} className="text-muted-foreground [&>td]:opacity-60">
                      <TableCell className="sticky left-0 z-10 bg-card font-sans font-semibold">
                        <div className="flex items-center gap-1.5">
                          {/* Keeps names aligned with the swappable rows. */}
                          <span className="size-6 shrink-0" aria-hidden />
                          <span className="max-sm:hidden">{row.Player}</span>
                          <span className="sm:hidden">{shortName(row.Player)}</span>
                          <span
                            className="rounded-sm bg-muted px-1 font-sans text-[0.6875rem] font-bold text-muted-foreground"
                            title="Was on this roster earlier this week: his games for the team still count"
                          >
                            Left roster
                          </span>
                        </div>
                      </TableCell>
                      <TableCell className={cn(!showFullWeek && "max-sm:hidden")}>{row.NBATeam || "—"}</TableCell>
                      {!showFullWeek && (
                        <TableCell className="text-right font-mono tabular-nums">{Number.isFinite(row.Rank) ? row.Rank : "—"}</TableCell>
                      )}
                      {scheduleLoading ? (
                        <TableCell colSpan={colSpan} />
                      ) : showFullWeek ? (
                        weekDays.map((day) => (
                          <TableCell key={day} className="text-center">
                            {gameCell(row, day, false, true, days.has(day))}
                          </TableCell>
                        ))
                      ) : (
                        <TableCell className="text-right font-mono tabular-nums">
                          {left}/{total}
                        </TableCell>
                      )}
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
            </>
          )}
          {showFullWeek && !optResult && (
            <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-muted-foreground" aria-label="Game key">
              {(
                [
                  ["counted", "Played, counted"],
                  ["missed", "Didn't count (bench, IR, off roster or didn't play)"],
                  ["upcoming", "Upcoming"],
                  ["doubtful", "Upcoming, day-to-day"],
                  ["benched", "Upcoming, on the bench"],
                  ["out", "Upcoming, won't count (IR, injured or off the roster)"],
                ] as const
              ).map(([state, label]) => (
                <li key={state} className="flex items-center gap-1.5">
                  <span className={cn("inline-block size-3 rounded-full", GAME_STATE_STYLE[state])} aria-hidden />
                  {label}
                </li>
              ))}
            </ul>
          )}
          </LoadingOverlay>
        </CardContent>
      </Card>

      {/* Premium (current season only -- it scores current rosters and
          projections). Hidden while an optimizer answer is on screen, which
          has its own category breakdown. */}
      {year === meta.current_year && team && !(optResult && optResult.swaps.length > 0) && (
        <RosterCategoryOddsCard team={team} roster={simulatedActiveNames} format={meta.season_format[String(year)] ?? "wl"} />
      )}

      <Card>
        <CardHeader>
          <CardTitle>Roster Rankings</CardTitle>
          <CardDescription>
            {rankingsTab === "avg"
              ? "Every team's roster, ordered by average player rank (lower is better)"
              : "Every team's real roster, ordered by weekly matchup win probability (higher is better)"}
          </CardDescription>
          {year === meta.current_year && (
            <CardAction>
              <label className="flex items-center gap-2 label text-foreground">
                <span className={cn("text-muted-foreground", rankingsTab === "winprob" && "opacity-50")}>Average Rank</span>
                <Switch
                  checked={rankingsTab === "winprob"}
                  onCheckedChange={(checked) => setRankingsTab(checked ? "winprob" : "avg")}
                />
                <span className={cn("flex items-center gap-1 text-muted-foreground", rankingsTab === "avg" && "opacity-50")}>
                  <Crown className="size-3.5 text-gold" aria-hidden />
                  Win Probability
                </span>
              </label>
            </CardAction>
          )}
        </CardHeader>
        <CardContent>
          {rankingsTab === "winprob" && year === meta.current_year ? (
            <RosterWinProbabilityTab team={team} format={meta.season_format[String(year)] ?? "wl"} />
          ) : (
          <LoadingOverlay active={rosterLoading} hasContent={rosterRows.length > 0} label="Loading">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Place</TableHead>
                  <TableHead>Team</TableHead>
                  <TableHead className="text-right">Avg Rank</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {teamAverages.map((row, i) => (
                  <TableRow key={row.team} className={cn(row.team === team && "bg-focus-row")}>
                    <TableCell>{i + 1}</TableCell>
                    <TableCell
                      className={cn(
                        "team-name",
                        rankingsSimulated && row.team === team && "text-yellow-500",
                      )}
                    >
                      {row.team}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {rankingsSimulated && row.team === team && Number.isFinite(row.realAvgRank) && (
                        <span className="mr-2 font-sans text-xs text-muted-foreground">
                          was {row.realAvgRank.toFixed(1)}
                        </span>
                      )}
                      {rankingsSimulated && row.team === team && Number.isFinite(row.avgRank) && row.avgRank !== row.realAvgRank && (
                        // Lower average rank is better, so a drop is an improvement.
                        row.avgRank < row.realAvgRank ? (
                          <ArrowUp className="mr-1 inline size-3.5 align-[-2px] text-win" aria-label="Improved" />
                        ) : (
                          <ArrowDown className="mr-1 inline size-3.5 align-[-2px] text-loss" aria-label="Worse" />
                        )
                      )}
                      {Number.isFinite(row.avgRank) ? row.avgRank.toFixed(1) : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </LoadingOverlay>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
