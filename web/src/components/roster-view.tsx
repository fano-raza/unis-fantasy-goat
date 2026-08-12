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
import { LabeledSelect } from "@/components/labeled-select";
import { SteppableSelect } from "@/components/steppable-select";
import { LoadingBasketballs } from "@/components/loading-basketballs";
import { cn } from "@/lib/utils";
import {
  getNBASchedule,
  getRosterRanks,
  type LeagueMeta,
  type NBAScheduleGame,
  type RosterRankRow,
} from "@/lib/api";
import { useSelectedTeam } from "@/lib/use-selected-team";

const EASTERN_TZ = "America/New_York";
const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

// The America/New_York calendar date a game falls on -- NOT the raw UTC
// date. A 10PM ET tip-off is already "tomorrow" in UTC (e.g.
// "2026-10-06T02:00Z" is really a Monday night game, Eastern time), so
// grouping by UTC date would silently shift some games onto the wrong day
// for this app's US-based audience. Matches this app's other US-Eastern
// date logic (e.g. FeatureBot's weekly role sync).
function easternDateKey(isoDate: string): string {
  return new Date(isoDate).toLocaleDateString("en-CA", { timeZone: EASTERN_TZ });
}

// Monday-Sunday range containing today (Eastern time), as "YYYY-MM-DD"
// bounds for the /league/nba_schedule request.
function currentEasternWeek(): { start: string; end: string; days: string[] } {
  const todayKey = new Date().toLocaleDateString("en-CA", { timeZone: EASTERN_TZ });
  const today = new Date(`${todayKey}T12:00:00Z`); // noon UTC avoids DST-edge date-shift on the pure-date parse
  const dow = today.getUTCDay(); // 0=Sun..6=Sat
  const diffToMonday = dow === 0 ? -6 : 1 - dow;
  const monday = new Date(today);
  monday.setUTCDate(today.getUTCDate() + diffToMonday);

  const days: string[] = [];
  for (let i = 0; i < 7; i++) {
    const d = new Date(monday);
    d.setUTCDate(monday.getUTCDate() + i);
    days.push(d.toISOString().slice(0, 10));
  }
  return { start: days[0], end: days[6], days };
}

function average(values: number[]): number | null {
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
}

export function RosterView({ meta }: { meta: LeagueMeta }) {
  const [year, setYear] = useState(meta.current_year);
  const [team, setTeam] = useSelectedTeam(meta.members[0] ?? "");
  const [showFullWeek, setShowFullWeek] = useState(false);

  const [rosterRows, setRosterRows] = useState<RosterRankRow[]>([]);
  const [rosterLoading, setRosterLoading] = useState(true);
  const [rosterError, setRosterError] = useState<string | null>(null);

  const [scheduleGames, setScheduleGames] = useState<NBAScheduleGame[]>([]);
  const [scheduleLoading, setScheduleLoading] = useState(true);

  const isCurrentSeason = year === meta.current_year;
  const week = useMemo(() => currentEasternWeek(), []);

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

  // Real-world "this week" schedule is only meaningful for the current
  // fantasy season -- a historical season's roster is a frozen snapshot
  // from years ago, so "games this week" has no coherent meaning there.
  useEffect(() => {
    if (!isCurrentSeason) {
      setScheduleLoading(false);
      return;
    }
    setScheduleLoading(true);
    getNBASchedule({ start_date: week.start, end_date: week.end })
      .then(setScheduleGames)
      .finally(() => setScheduleLoading(false));
  }, [isCurrentSeason, week.start, week.end]);

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

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Roster</CardTitle>
          <CardDescription>
            A team&apos;s full roster, player ranks, and (for the current season) each player&apos;s games this week
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-6">
          <SteppableSelect label="Season" value={year} onValueChange={setYear} options={meta.years} />
          <LabeledSelect
            label="Team"
            value={team}
            onValueChange={setTeam}
            options={meta.members.map((m) => ({ value: m, label: m }))}
          />
          {isCurrentSeason && (
            <label className="flex items-center gap-2 text-[11px] font-bold tracking-wider uppercase">
              <span className="text-muted-foreground">This Week</span>
              <Switch checked={showFullWeek} onCheckedChange={setShowFullWeek} />
              <span className="text-muted-foreground">Full Week Grid</span>
            </label>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          {rosterLoading ? (
            <LoadingBasketballs label="Loading roster" />
          ) : rosterError ? (
            <p className="text-sm text-muted-foreground">No roster data for {year} ({rosterError}).</p>
          ) : teamRoster.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No roster data for {team} in {year}
              {!isCurrentSeason ? "" : " yet"}.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Player</TableHead>
                  <TableHead>NBA Team</TableHead>
                  <TableHead className="text-right">Rank</TableHead>
                  {isCurrentSeason &&
                    (showFullWeek ? (
                      DAY_LABELS.map((d) => (
                        <TableHead key={d} className="text-center">
                          {d}
                        </TableHead>
                      ))
                    ) : (
                      <TableHead className="text-right">Games Left</TableHead>
                    ))}
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
                  {isCurrentSeason && (
                    <TableCell colSpan={showFullWeek ? 7 : 1} />
                  )}
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
                      {isCurrentSeason &&
                        (scheduleLoading ? (
                          <TableCell colSpan={showFullWeek ? 7 : 1} className="text-center text-muted-foreground">
                            <LoadingBasketballs />
                          </TableCell>
                        ) : showFullWeek ? (
                          week.days.map((day) => (
                            <TableCell key={day} className="text-center">
                              {gameDaysThisWeek.has(day) ? (
                                <span className="text-win">●</span>
                              ) : (
                                <span className="text-muted-foreground/30">—</span>
                              )}
                            </TableCell>
                          ))
                        ) : (
                          <TableCell className="text-right font-mono tabular-nums">
                            {remaining}/{totalThisWeek}
                          </TableCell>
                        ))}
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
