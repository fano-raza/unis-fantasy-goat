"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Card,
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
import { Button } from "@/components/ui/button";
import { LabeledSelect } from "@/components/labeled-select";
import { SteppableSelect } from "@/components/steppable-select";
import { LoadingBasketballs } from "@/components/loading-basketballs";
import { cn } from "@/lib/utils";
import {
  getNBASchedule,
  getRosterRanks,
  getWeekCalendar,
  type LeagueMeta,
  type NBAScheduleGame,
  type RosterRankRow,
  type WeekCalendarRow,
} from "@/lib/api";
import { useSelectedTeam } from "@/lib/use-selected-team";

const EASTERN_TZ = "America/New_York";

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
  // current week isn't in the new season's calendar) to that season's
  // latest started week.
  useEffect(() => {
    getWeekCalendar({ year }).then((rows) => {
      setWeekCalendar(rows);
      setWeek((w) => (w != null && rows.some((r) => r.Week === w) ? w : latestWeek(rows)));
    });
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
  const teamAvgRank = useMemo(() => average(teamRoster.map((r) => r.Rank)), [teamRoster]);

  const teamAverages = useMemo(() => {
    const byTeam = new Map<string, number[]>();
    for (const row of rosterRows) {
      if (!byTeam.has(row.FantasyTeam)) byTeam.set(row.FantasyTeam, []);
      byTeam.get(row.FantasyTeam)!.push(row.Rank);
    }
    return [...byTeam.entries()]
      .map(([t, ranks]) => ({ team: t, avgRank: average(ranks) ?? Infinity }))
      .sort((a, b) => a.avgRank - b.avgRank);
  }, [rosterRows]);

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

  const now = Date.now();
  const today = todayKey();
  const weekOptions = useMemo(() => weekCalendar.map((w) => w.Week), [weekCalendar]);
  const atLatestWeek = week != null && week === latestWeek(weekCalendar);
  const colSpan = showFullWeek ? Math.max(weekDays.length, 1) : 1;

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Roster</CardTitle>
          <CardDescription>A team&apos;s full roster, player ranks, and each player&apos;s games for the selected week</CardDescription>
        </CardHeader>
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
          <label className="flex items-center gap-2 text-[11px] font-bold tracking-wider uppercase">
            <span className="text-muted-foreground">Games Left</span>
            <Switch checked={showFullWeek} onCheckedChange={setShowFullWeek} />
            <span className="text-muted-foreground">Full Week Grid</span>
          </label>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          {rosterLoading ? (
            <LoadingBasketballs label="Loading roster" />
          ) : rosterError ? (
            <p className="text-sm text-muted-foreground">No roster data for {year} ({rosterError}).</p>
          ) : teamRoster.length === 0 ? (
            <p className="text-sm text-muted-foreground">No roster data for {team} in {year}.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Player</TableHead>
                  <TableHead>NBA Team</TableHead>
                  <TableHead className="text-right">Rank</TableHead>
                  {showFullWeek
                    ? weekDays.map((d) => (
                        <TableHead key={d} className={cn("text-center", d < today && "text-muted-foreground/50")}>
                          {dayLabel(d)}
                        </TableHead>
                      ))
                    : <TableHead className="text-right">Games Left</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow className="bg-focus-row">
                  <TableCell colSpan={2} className="font-sans font-extrabold tracking-wide uppercase text-primary">
                    Average Rank
                  </TableCell>
                  <TableCell className="text-right font-mono font-extrabold tabular-nums text-primary">
                    {teamAvgRank !== null ? teamAvgRank.toFixed(1) : "—"}
                  </TableCell>
                  <TableCell colSpan={colSpan} />
                </TableRow>
                {teamRoster.map((row) => {
                  const games = gamesByNBATeam.get(row.NBATeam) ?? [];
                  const totalThisWeek = games.length;
                  const remaining = games.filter((g) => new Date(g.Date).getTime() > now).length;
                  const gameDaysThisWeek = new Set(games.map((g) => easternDateKey(g.Date)));
                  return (
                    <TableRow key={row.Player}>
                      <TableCell className="font-sans font-semibold">{row.Player}</TableCell>
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
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Roster Rankings</CardTitle>
          <CardDescription>Every team&apos;s roster, ordered by average player rank (lower is better)</CardDescription>
        </CardHeader>
        <CardContent>
          {rosterLoading ? (
            <LoadingBasketballs label="Loading" />
          ) : (
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
                    <TableCell className="font-sans font-extrabold tracking-wide uppercase">
                      {row.team}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {Number.isFinite(row.avgRank) ? row.avgRank.toFixed(1) : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
