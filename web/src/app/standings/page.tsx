"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ChartLegend } from "@/components/chart-legend";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { LabeledSelect } from "@/components/labeled-select";
import { LoadingBasketballs } from "@/components/loading-basketballs";
import { categoricalPalette } from "@/lib/palette";
import {
  getLeagueMeta,
  getStandings,
  getStandingsHistory,
  type LeagueMeta,
  type StandingsHistoryResponse,
  type StandingsResponse,
  type StandingsRow,
} from "@/lib/api";
import { ArrowDown, ArrowUp } from "lucide-react";

// Games Behind: leader's score minus this row's score, score = wins + 0.5*ties
// (the user's own explicit formula -- note this is a plain half-point, not
// the 0.49 tie-weight fudge factor used for ranking tiebreaks elsewhere in
// this app). Leader shows "-" (standard sports-table convention for GB=0).
function gamesBehind(rows: StandingsRow[]): Map<string, number> {
  const score = (r: StandingsRow) => r.wins + 0.5 * r.ties;
  const leaderScore = Math.max(...rows.map(score));
  return new Map(rows.map((r) => [r.team, leaderScore - score(r)]));
}

function formatGB(value: number): string {
  if (value === 0) return "-";
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function StandingsTable({
  rows,
  previousRanks,
}: {
  rows: StandingsRow[];
  // Rank as of one week earlier than the current week-range selection --
  // when present and different, renders a green/red movement arrow next to
  // Place. Omitted (no arrows) when the selected range is a single week.
  previousRanks?: Map<string, number>;
}) {
  const gb = gamesBehind(rows);
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Place</TableHead>
          <TableHead>Team</TableHead>
          <TableHead className="text-right">Record</TableHead>
          <TableHead className="text-right">GB</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => {
          const previousRank = previousRanks?.get(row.team);
          return (
            <TableRow key={row.team}>
              <TableCell>
                <span className="inline-flex items-center gap-1">
                  {row.rank}
                  {previousRank != null &&
                    previousRank !== row.rank &&
                    (row.rank < previousRank ? (
                      <ArrowUp className="size-3 text-win" />
                    ) : (
                      <ArrowDown className="size-3 text-loss" />
                    ))}
                </span>
              </TableCell>
              <TableCell className="font-sans font-extrabold tracking-wide uppercase">
                <Link href={`/profile?team=${encodeURIComponent(row.team)}`} className="hover:underline">
                  {row.team}
                </Link>
              </TableCell>
              <TableCell className="text-right">
                {row.wins}-{row.losses}-{row.ties}
              </TableCell>
              <TableCell className="text-right">{formatGB(gb.get(row.team) ?? 0)}</TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}

// Reshapes standings_history's {type: {team: [{week, rank}]}} into one row
// per week with a rank column per team, the shape recharts' LineChart wants.
function buildHistoryChartData(
  byTeam: Record<string, { week: number; rank: number }[]>,
  minWeek: number,
  maxWeek: number,
): Record<string, number>[] {
  const teams = Object.keys(byTeam);
  const rows: Record<string, number>[] = [];
  for (let week = minWeek; week <= maxWeek; week++) {
    const row: Record<string, number> = { week };
    for (const team of teams) {
      const point = byTeam[team]?.find((p) => p.week === week);
      if (point) row[team] = point.rank;
    }
    rows.push(row);
  }
  return rows;
}

// team -> rank, for the prior-week movement arrows.
function toRankMap(rows: StandingsRow[]): Map<string, number> {
  return new Map(rows.map((r) => [r.team, r.rank]));
}

export default function StandingsPage() {
  const [meta, setMeta] = useState<LeagueMeta | null>(null);
  const [year, setYear] = useState<number | null>(null);
  const [weekRange, setWeekRange] = useState<[number, number] | null>(null);
  const [oneVOneMode, setOneVOneMode] = useState<"wl" | "cats">("wl");
  const [leagueMode, setLeagueMode] = useState<"wl" | "cats">("wl");
  const [showGraph, setShowGraph] = useState(true);
  const [standings, setStandings] = useState<StandingsResponse | null>(null);
  const [previousStandings, setPreviousStandings] = useState<StandingsResponse | null>(null);
  const [history, setHistory] = useState<StandingsHistoryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getLeagueMeta().then((m) => {
      setMeta(m);
      setYear(m.current_year);
    });
  }, []);

  const maxWeek = useMemo(() => {
    if (!meta || year == null) return 1;
    return meta.rs_week_count[String(year)] ?? 1;
  }, [meta, year]);

  // Default both toggles to whatever format that season actually used
  // (some years were scored by matchup W/L, others by aggregate category
  // wins -- see dashboard_site/api/league_store.py's SEASON_IS_WL). Resets
  // whenever the year changes, also covering the initial load.
  useEffect(() => {
    if (!meta || year == null) return;
    const format = meta.season_format[String(year)] ?? "wl";
    setOneVOneMode(format);
    setLeagueMode(format);
  }, [meta, year]);

  // Reset to the full RS range whenever the year changes (also covers the
  // initial load, once meta/year are both set).
  useEffect(() => {
    if (!meta || year == null) return;
    setWeekRange([1, maxWeek]);
  }, [meta, year, maxWeek]);

  // Debounced live-refetch -- a slider drag fires many intermediate values,
  // and this payload is tiny (a handful of teams' summed W-L-T), so a full
  // Apply-gated flow (like Career Stats/Analysis' mobile filter drawer)
  // would be unnecessary friction here.
  useEffect(() => {
    if (year == null || !weekRange) return;
    const [minWeek, maxWeek] = weekRange;
    const timeout = setTimeout(() => {
      // "Prior" = the same range with its single latest week dropped, so
      // the Place column can show a green/red movement arrow. Skipped for
      // a single-week range -- there's no earlier state to compare to.
      const priorReq = maxWeek > minWeek ? { year, min_week: minWeek, max_week: maxWeek - 1 } : null;
      Promise.all([
        getStandings({ year, min_week: minWeek, max_week: maxWeek }),
        priorReq ? getStandings(priorReq).catch(() => null) : Promise.resolve(null),
        getStandingsHistory({ year, min_week: minWeek, max_week: maxWeek }),
      ])
        .then(([current, prior, hist]) => {
          setStandings(current);
          setPreviousStandings(prior);
          setHistory(hist);
          setError(null);
        })
        .catch((err) => {
          setStandings(null);
          setPreviousStandings(null);
          setHistory(null);
          setError(err instanceof Error ? err.message : String(err));
        });
    }, 200);
    return () => clearTimeout(timeout);
  }, [year, weekRange]);

  // Line-graph data: mirrors the 1v1 Standings card's own WL/Cats toggle,
  // no separate control (per the plan's clarified scope).
  const historyChartData = useMemo(() => {
    if (!history || !weekRange) return [];
    return buildHistoryChartData(history[oneVOneMode], weekRange[0], weekRange[1]);
  }, [history, oneVOneMode, weekRange]);
  const historyTeams = useMemo(
    () => (history ? Object.keys(history[oneVOneMode]).sort() : []),
    [history, oneVOneMode],
  );
  const historyColors = useMemo(() => categoricalPalette(historyTeams.length), [historyTeams.length]);

  if (!meta || year == null || !weekRange) return <LoadingBasketballs label="Loading" />;

  return (
    <div className="flex flex-col gap-4">
      <div className="sticky top-0 z-30 flex items-center gap-2 rounded-sm border border-border bg-card px-3 py-2 shadow-sm">
        <LabeledSelect
          label="Season"
          value={String(year)}
          onValueChange={(v) => setYear(Number(v))}
          options={meta.years.map((y) => ({ value: String(y), label: String(y) }))}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Standings</CardTitle>
          <CardDescription>
            Regular-season standings for any week range
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-6">
          <div className="flex flex-col gap-3">
            <span className="text-[11px] font-bold tracking-wider text-muted-foreground uppercase">
              Week {weekRange[0]} &ndash; Week {weekRange[1]}
            </span>
            <Slider
              min={1}
              max={maxWeek}
              step={1}
              minStepsBetweenValues={1}
              value={weekRange}
              onValueChange={(v) => setWeekRange(v as [number, number])}
              thumbLabels={[`Week ${weekRange[0]}`, `Week ${weekRange[1]}`]}
            />
          </div>
          <label className="flex items-center gap-2 self-start text-[11px] font-bold tracking-wider uppercase">
            <span className="text-muted-foreground">Hide Graph</span>
            <Switch checked={showGraph} onCheckedChange={setShowGraph} />
            <span className="text-muted-foreground">Show Graph</span>
          </label>
        </CardContent>
      </Card>

      {error ? (
        <Card>
          <CardContent>
            <p className="text-sm text-muted-foreground">No data for the current filters ({error}).</p>
          </CardContent>
        </Card>
      ) : !standings ? (
        <LoadingBasketballs label="Loading standings" />
      ) : (
        standings && (
          <>
            <Card>
              <CardHeader>
                <CardTitle>1v1 Standings</CardTitle>
                <CardDescription>Real matchup win-loss-tie record, by matchup outcome or aggregate category record</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                <label className="flex items-center gap-2 self-start text-[11px] font-bold tracking-wider uppercase">
                  <span className="text-muted-foreground">W/L</span>
                  <Switch
                    checked={oneVOneMode === "cats"}
                    onCheckedChange={(checked) => setOneVOneMode(checked ? "cats" : "wl")}
                  />
                  <span className="text-muted-foreground">Cats</span>
                </label>
                <StandingsTable
                  rows={oneVOneMode === "wl" ? standings.wl : standings.cats}
                  previousRanks={
                    previousStandings
                      ? toRankMap(oneVOneMode === "wl" ? previousStandings.wl : previousStandings.cats)
                      : undefined
                  }
                />
              </CardContent>
            </Card>

            {showGraph && historyChartData.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>Position Over Time</CardTitle>
                  <CardDescription>
                    Each team&apos;s {oneVOneMode === "wl" ? "W/L" : "Cats"} standings place,
                    week by week over the selected range
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="h-[360px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={historyChartData} margin={{ left: 8, right: 16, top: 8, bottom: 24 }}>
                        <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                        <XAxis
                          dataKey="week"
                          type="number"
                          domain={[weekRange[0], weekRange[1]]}
                          ticks={Array.from(
                            { length: weekRange[1] - weekRange[0] + 1 },
                            (_, i) => weekRange[0] + i,
                          )}
                          tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
                          stroke="var(--border)"
                          label={{
                            value: "Week",
                            position: "insideBottom",
                            offset: -4,
                            fill: "var(--muted-foreground)",
                            fontSize: 12,
                          }}
                        />
                        <YAxis
                          reversed
                          allowDecimals={false}
                          domain={[1, historyTeams.length]}
                          width={32}
                          tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
                          stroke="var(--border)"
                          label={{
                            value: "Place",
                            angle: -90,
                            position: "insideLeft",
                            fill: "var(--muted-foreground)",
                            fontSize: 12,
                          }}
                        />
                        <Tooltip
                          contentStyle={{
                            background: "var(--card)",
                            border: "1px solid var(--border)",
                            fontSize: 12,
                          }}
                          labelFormatter={(w) => `Week ${w}`}
                          itemSorter={(item) => (typeof item.value === "number" ? item.value : Infinity)}
                        />
                        {historyTeams.map((team, i) => (
                          <Line
                            key={team}
                            dataKey={team}
                            name={team}
                            stroke={historyColors[i]}
                            connectNulls
                            dot={{ r: 2 }}
                            isAnimationActive={false}
                          />
                        ))}
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                  <ChartLegend items={historyTeams.map((team, i) => ({ key: team, color: historyColors[i] }))} />
                </CardContent>
              </Card>
            )}

            <Card>
              <CardHeader>
                <CardTitle>League Wins Standings</CardTitle>
                <CardDescription>
                  All-play record -- every team vs. every other team, every week
                </CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                <label className="flex items-center gap-2 self-start text-[11px] font-bold tracking-wider uppercase">
                  <span className="text-muted-foreground">W/L</span>
                  <Switch
                    checked={leagueMode === "cats"}
                    onCheckedChange={(checked) => setLeagueMode(checked ? "cats" : "wl")}
                  />
                  <span className="text-muted-foreground">Cats</span>
                </label>
                <StandingsTable
                  rows={leagueMode === "wl" ? standings.league_wl : standings.league_cats}
                  previousRanks={
                    previousStandings
                      ? toRankMap(
                          leagueMode === "wl" ? previousStandings.league_wl : previousStandings.league_cats,
                        )
                      : undefined
                  }
                />
              </CardContent>
            </Card>
          </>
        )
      )}
    </div>
  );
}
