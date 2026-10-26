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
import { cn } from "@/lib/utils";
import {
  getNBASchedule,
  getRosterRanks,
  getWeekCalendar,
  type LeagueMeta,
  type NBAScheduleGame,
  type RosterOptimizerResult,
  type RosterRankRow,
  type WeekCalendarRow,
} from "@/lib/api";
import { useSelectedTeam } from "@/lib/use-selected-team";
import { ordinal } from "@/lib/team-summary-fields";
import { ArrowDown, ArrowLeftRight, ArrowUp, RotateCcw, TriangleAlert } from "lucide-react";

const EASTERN_TZ = "America/New_York";
// This league starts 10 players -- a day where more than 10 of a team's
// rostered players have real games is a real scheduling conflict (someone
// with a game is forced to sit), worth flagging.
const MAX_STARTERS = 10;

// The America/New_York calendar date a game falls on -- NOT the raw UTC
// date. A 10PM ET tip-off is already "tomorrow" in UTC (e.g.
// "2026-10-06T02:00Z" is really a Monday night game, Eastern time), so
// grouping by UTC date would silently shift some games onto the wrong day
// for this app's US-based audience. Matches this app's other US-Eastern
// date logic (e.g. FeatureBot's weekly role sync).
function easternDateKey(isoDate: string): string {
  return new Date(isoDate).toLocaleDateString("en-CA", { timeZone: EASTERN_TZ });
}

function todayKey(): string {
  return new Date().toLocaleDateString("en-CA", { timeZone: EASTERN_TZ });
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
  const today = todayKey();
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

  // Every other player in the league that year -- rostered by someone
  // else, or a free agent (FantasyTeam === "") -- the pool any slot can
  // be swapped to.
  const otherTeamsPlayers = useMemo(
    () => rosterRows.filter((r) => r.FantasyTeam !== team).sort((a, b) => a.Rank - b.Rank),
    [rosterRows, team],
  );

  // One "slot" per real roster spot, holding either the real player or
  // whatever they've been hypothetically swapped for.
  const slots = useMemo(
    () => teamRoster.map((orig) => ({ originalPlayer: orig.Player, display: swaps.get(orig.Player) ?? orig })),
    [teamRoster, swaps],
  );
  const sortedSlots = useMemo(() => [...slots].sort((a, b) => a.display.Rank - b.display.Rank), [slots]);
  const displayedRoster = useMemo(() => sortedSlots.map((s) => s.display), [sortedSlots]);
  const simulating = swaps.size > 0;

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
    for (const row of displayedRoster) {
      const games = gamesByNBATeam.get(row.NBATeam) ?? [];
      const daysPlaying = new Set(games.map((g) => easternDateKey(g.Date)));
      for (const day of daysPlaying) {
        if (weekDays.includes(day)) counts.set(day, (counts.get(day) ?? 0) + 1);
      }
    }
    return counts;
  }, [displayedRoster, gamesByNBATeam, weekDays]);

  const now = Date.now();
  const today = todayKey();

  function gamesLeftLabel(row: RosterRankRow): ReactNode {
    if (scheduleLoading) return "…";
    const games = gamesByNBATeam.get(row.NBATeam) ?? [];
    const remaining = games.filter((g) => new Date(g.Date).getTime() > now).length;
    return `${remaining}/${games.length}`;
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
  const colSpan = showFullWeek ? Math.max(weekDays.length, 1) : 1;

  return (
    <div className="flex flex-col gap-4">
      <Card variant="plain">
        <CardContent className="flex flex-wrap items-center gap-6">
          <SteppableSelect label="Season" value={year} onValueChange={setYear} options={meta.years} />
          <LabeledSelect
            label="Team"
            value={team}
            onValueChange={setTeam}
            options={meta.members.map((m) => ({ value: m, label: m }))}
          />
          {weekOptions.length > 0 && week != null && (
            <div className="flex items-center gap-2">
              <SteppableSelect label="Week" value={week} onValueChange={setWeek} options={weekOptions} />
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
              disabled={optimizing}
              onRunningChange={setOptimizing}
              onResult={(res) => {
                // Ignore an answer for a team the page has since moved off.
                if (res.team !== currentTeam.current) return;
                setSwaps(new Map());
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
              <Button type="button" variant="outline" size="sm" onClick={() => setSwaps(new Map())}>
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
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="sticky left-0 z-10 bg-card">Player</TableHead>
                  <TableHead>NBA Team</TableHead>
                  <TableHead className="text-right">Rank</TableHead>
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
                  </TableCell>
                  <TableCell />
                  <TableCell className="text-right font-mono font-extrabold tabular-nums text-primary">
                    {displayedAvgRank !== null ? displayedAvgRank.toFixed(1) : "—"}
                    {teamPlacement !== null && (
                      <span className="ml-1 font-sans text-xs font-bold text-muted-foreground">
                        ({ordinal(teamPlacement)})
                      </span>
                    )}
                  </TableCell>
                  <TableCell colSpan={colSpan} />
                </TableRow>
                {sortedSlots.map((slot) => {
                  const row = slot.display;
                  const games = gamesByNBATeam.get(row.NBATeam) ?? [];
                  const totalThisWeek = games.length;
                  const remaining = games.filter((g) => new Date(g.Date).getTime() > now).length;
                  const gameDaysThisWeek = new Set(games.map((g) => easternDateKey(g.Date)));
                  const isSwappedIn = row.Player !== slot.originalPlayer;
                  const candidates = candidatesForSlot(slot.originalPlayer);
                  return (
                    <TableRow key={slot.originalPlayer}>
                      <TableCell className="sticky left-0 z-10 bg-card font-sans font-semibold">
                        <div className="flex items-center gap-1.5">
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
                                  <CommandGroup>
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
                          <span className={cn(isSwappedIn && "text-yellow-500")}>{row.Player}</span>
                          {isSwappedIn && (
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              className="size-6 shrink-0 text-muted-foreground"
                              title={`Put ${slot.originalPlayer} back`}
                              aria-label={`Put ${slot.originalPlayer} back`}
                              onClick={() =>
                                setSwaps((prev) => {
                                  const next = new Map(prev);
                                  next.delete(slot.originalPlayer);
                                  return next;
                                })
                              }
                            >
                              <RotateCcw className="size-3.5" />
                            </Button>
                          )}
                        </div>
                      </TableCell>
                      <TableCell className="text-muted-foreground">{row.NBATeam}</TableCell>
                      <TableCell className="text-right font-mono tabular-nums">{row.Rank}</TableCell>
                      {scheduleLoading ? (
                        <TableCell colSpan={colSpan} className="text-center text-muted-foreground">
                          <LoadingBasketballs />
                        </TableCell>
                      ) : showFullWeek ? (
                        weekDays.map((day) => (
                          <TableCell key={day} className="text-center">
                            {gameDaysThisWeek.has(day) ? (
                              <span className={cn("text-win", day < today && "opacity-40")}>●</span>
                            ) : (
                              <span className="text-muted-foreground/30">—</span>
                            )}
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
              </TableBody>
            </Table>
          )}
          </LoadingOverlay>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Roster Rankings</CardTitle>
          <CardDescription>Every team&apos;s roster, ordered by average player rank (lower is better)</CardDescription>
        </CardHeader>
        <CardContent>
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
        </CardContent>
      </Card>
    </div>
  );
}
