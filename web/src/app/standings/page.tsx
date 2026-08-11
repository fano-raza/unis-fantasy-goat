"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
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
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ChartLegend } from "@/components/chart-legend";
import { PlayoffTree } from "@/components/playoff-tree";
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";
import { Slider } from "@/components/ui/slider";
import { StatTable } from "@/components/stat-table";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { LabeledSelect, NO_FOCUS_TEAM } from "@/components/labeled-select";
import { SteppableSelect } from "@/components/steppable-select";
import { ArrowToggle } from "@/components/arrow-toggle";
import { LoadingBasketballs } from "@/components/loading-basketballs";
import { categoricalPalette } from "@/lib/palette";
import {
  getAnalysisRows,
  getAverages,
  getLeagueMeta,
  getPlayoffBrackets,
  getSeasonLeaders,
  getStandings,
  getStandingsHistory,
  getTotals,
  MAIN_CATS,
  type AggregateRow,
  type AnalysisRow,
  type Category,
  type LeagueMeta,
  type PlayoffBracketsResponse,
  type SeasonLeadersResponse,
  type StandingsHistoryResponse,
  type StandingsResponse,
  type StandingsRow,
} from "@/lib/api";
import { ArrowDown, ArrowUp } from "lucide-react";

type View = "1v1" | "league_wins" | "ratings";
const VIEW_OPTIONS = [
  { value: "1v1", label: "Season Standings" },
  { value: "league_wins", label: "League Wins" },
  { value: "ratings", label: "Ratings" },
];

function isView(value: string | null): value is View {
  return value === "1v1" || value === "league_wins" || value === "ratings";
}

function formatCatValue(cat: Category, value: number): string {
  if (cat === "FG%" || cat === "FT%") return value.toFixed(3);
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

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

// Ratings view's graph: at week X, each team's value is the average of its
// week_rating from the range's min week through X (a cumulative running
// average, not a single flat per-range average) -- the user's explicit spec.
function buildRatingHistoryChartData(
  rows: AnalysisRow[],
  minWeek: number,
  maxWeek: number,
): Record<string, number>[] {
  const byTeam = new Map<string, Map<number, number>>();
  for (const r of rows) {
    if (!byTeam.has(r.team)) byTeam.set(r.team, new Map());
    byTeam.get(r.team)!.set(r.week, r.week_rating);
  }
  const chartRows: Record<string, number>[] = [];
  for (let week = minWeek; week <= maxWeek; week++) {
    const row: Record<string, number> = { week };
    for (const [team, weekRatings] of byTeam) {
      const seen: number[] = [];
      for (let w = minWeek; w <= week; w++) {
        const v = weekRatings.get(w);
        if (v !== undefined) seen.push(v);
      }
      if (seen.length) row[team] = seen.reduce((a, b) => a + b, 0) / seen.length;
    }
    chartRows.push(row);
  }
  return chartRows;
}

// team -> rank, for the prior-week movement arrows.
function toRankMap(rows: StandingsRow[]): Map<string, number> {
  return new Map(rows.map((r) => [r.team, r.rank]));
}

export default function StandingsPage() {
  return (
    <Suspense fallback={<LoadingBasketballs label="Loading" />}>
      <StandingsPageInner />
    </Suspense>
  );
}

// useSearchParams() (for the ?year=/?view=/?tree= deep links) requires a
// Suspense boundary around whatever calls it, per Next.js -- the actual page
// content lives here, wrapped by the plain default export above.
function StandingsPageInner() {
  const [meta, setMeta] = useState<LeagueMeta | null>(null);
  const [year, setYear] = useState<number | null>(null);
  const [weekRange, setWeekRange] = useState<[number, number] | null>(null);
  const [view, setView] = useState<View>("1v1");
  const [oneVOneMode, setOneVOneMode] = useState<"wl" | "cats">("wl");
  const [leagueMode, setLeagueMode] = useState<"wl" | "cats">("wl");
  const [showGraph, setShowGraph] = useState(true);
  const [showPlayoffTree, setShowPlayoffTree] = useState(false);
  const [standings, setStandings] = useState<StandingsResponse | null>(null);
  const [previousStandings, setPreviousStandings] = useState<StandingsResponse | null>(null);
  const [history, setHistory] = useState<StandingsHistoryResponse | null>(null);
  const [brackets, setBrackets] = useState<PlayoffBracketsResponse>({});
  const [error, setError] = useState<string | null>(null);

  // Ratings view (absorbed from the retired Season page).
  const [ratingsStatMode, setRatingsStatMode] = useState<"totals" | "averages">("totals");
  const [ratingsRs, setRatingsRs] = useState(true);
  const [ratingsPo, setRatingsPo] = useState(true);
  const [ratingsFocusTeam, setRatingsFocusTeam] = useState<string>(NO_FOCUS_TEAM);
  const [ratingsDisplay, setRatingsDisplay] = useState<"table" | "leaders">("table");
  const [ratingsRows, setRatingsRows] = useState<AggregateRow[]>([]);
  const [ratingsLeaders, setRatingsLeaders] = useState<SeasonLeadersResponse | null>(null);
  const [ratingsHistory, setRatingsHistory] = useState<AnalysisRow[]>([]);

  const searchParams = useSearchParams();

  useEffect(() => {
    // A ?year= link (from a Profile stat-tile deep link) wins over the
    // default current year, if it's a real year for this league. A
    // ?tree=1 alongside it pre-enables the Playoff Tree toggle, and a
    // ?view= alongside it jumps straight to that arrow-toggle state (both
    // used by the Profile stat-tile links).
    const yearFromUrl = Number(searchParams.get("year"));
    if (searchParams.get("tree") === "1") setShowPlayoffTree(true);
    const viewFromUrl = searchParams.get("view");
    if (isView(viewFromUrl)) setView(viewFromUrl);
    getLeagueMeta().then((m) => {
      setMeta(m);
      setYear(m.years.includes(yearFromUrl) ? yearFromUrl : m.current_year);
    });
    // Deliberately only reads searchParams once, at mount -- see the
    // matching comment on Profile's ?team= handling for why.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // All years' bracket data is a single small payload -- fetched once, not
  // refetched per year switch (mirrors getLeagueMeta's own one-shot fetch).
  useEffect(() => {
    getPlayoffBrackets().then(setBrackets);
  }, []);

  const maxWeek = useMemo(() => {
    if (!meta || year == null) return 1;
    return meta.rs_week_count[String(year)] ?? 1;
  }, [meta, year]);

  // Default both 1v1/League Wins toggles to whatever format that season
  // actually used (some years were scored by matchup W/L, others by
  // aggregate category wins -- see dashboard_site/api/league_store.py's
  // SEASON_IS_WL). Resets whenever the year changes, also covering the
  // initial load.
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

  const weeksInRange = useMemo(() => {
    if (!weekRange) return [];
    return Array.from({ length: weekRange[1] - weekRange[0] + 1 }, (_, i) => weekRange[0] + i);
  }, [weekRange]);

  // Debounced live-refetch -- a slider drag fires many intermediate values,
  // and this payload is tiny (a handful of teams' summed W-L-T), so a full
  // Apply-gated flow (like Career Stats/Analysis' mobile filter drawer)
  // would be unnecessary friction here. Fetches all 3 views' data
  // unconditionally regardless of which is active, same eager-fetch pattern
  // this app already uses elsewhere (e.g. Profile) -- the payloads are small.
  useEffect(() => {
    if (year == null || !weekRange || weeksInRange.length === 0) return;
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

      const ratingsReq = { years: [year], weeks: weeksInRange, RS: ratingsRs, PO: ratingsPo };
      const ratingsFetcher = ratingsStatMode === "totals" ? getTotals : getAverages;
      Promise.all([
        ratingsFetcher(ratingsReq),
        getSeasonLeaders({ ...ratingsReq, mode: ratingsStatMode }),
        getAnalysisRows(ratingsReq),
      ]).then(([rows, leaders, analysisRows]) => {
        setRatingsRows(rows);
        setRatingsLeaders(leaders);
        setRatingsHistory(analysisRows);
      });
    }, 200);
    return () => clearTimeout(timeout);
  }, [year, weekRange, weeksInRange, ratingsStatMode, ratingsRs, ratingsPo]);

  // Only teams actually shown in the current ratings rows, not the full
  // league roster.
  const ratingsFocusOptions = useMemo(() => [...ratingsRows.map((r) => r.team)].sort(), [ratingsRows]);

  // Default (and re-default, if the current focus team disappears from a
  // new filter's rows) to whichever team ranks #1.
  useEffect(() => {
    const teamsShown = new Set(ratingsRows.map((r) => r.team));
    if (ratingsFocusTeam !== NO_FOCUS_TEAM && teamsShown.has(ratingsFocusTeam)) return;
    const topTeam = ratingsRows.find((r) => r.rank === 1);
    setRatingsFocusTeam(topTeam?.team ?? NO_FOCUS_TEAM);
  }, [ratingsRows, ratingsFocusTeam]);

  // Line-graph data: mirrors the 1v1/League Wins card's own WL/Cats toggle,
  // no separate control (per the plan's clarified scope).
  const historyChartData = useMemo(() => {
    if (!history || !weekRange) return [];
    const key = view === "league_wins" ? (leagueMode === "wl" ? "league_wl" : "league_cats") : oneVOneMode;
    return buildHistoryChartData(history[key], weekRange[0], weekRange[1]);
  }, [history, oneVOneMode, leagueMode, view, weekRange]);
  const historyTeams = useMemo(() => {
    if (!history) return [];
    const key = view === "league_wins" ? (leagueMode === "wl" ? "league_wl" : "league_cats") : oneVOneMode;
    return Object.keys(history[key]).sort();
  }, [history, oneVOneMode, leagueMode, view]);
  const historyColors = useMemo(() => categoricalPalette(historyTeams.length), [historyTeams.length]);

  const ratingsChartData = useMemo(() => {
    if (!weekRange) return [];
    return buildRatingHistoryChartData(ratingsHistory, weekRange[0], weekRange[1]);
  }, [ratingsHistory, weekRange]);
  const ratingsTeams = useMemo(
    () => [...new Set(ratingsHistory.map((r) => r.team))].sort(),
    [ratingsHistory],
  );
  const ratingsColors = useMemo(() => categoricalPalette(ratingsTeams.length), [ratingsTeams.length]);

  if (!meta || year == null || !weekRange) return <LoadingBasketballs label="Loading" />;

  return (
    <div className="flex flex-col gap-4">
      <div className="sticky top-0 z-30 flex flex-wrap items-center gap-3 rounded-sm border border-border bg-card px-3 py-2 shadow-sm">
        <SteppableSelect label="Season" value={year} onValueChange={setYear} options={meta.years} />
        <ArrowToggle options={VIEW_OPTIONS} value={view} onChange={(v) => setView(v as View)} />
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
        <>
          {view === "1v1" && (
            <>
              <Card>
                <CardHeader>
                  <CardTitle>Season Standings</CardTitle>
                  <CardDescription>Real matchup win-loss-tie record, by matchup outcome or aggregate category record</CardDescription>
                  <CardAction>
                    <label className="flex items-center gap-2 text-[11px] font-bold tracking-wider uppercase">
                      <span className="text-muted-foreground">Playoff Tree</span>
                      <Switch checked={showPlayoffTree} onCheckedChange={setShowPlayoffTree} />
                    </label>
                  </CardAction>
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
                  {showPlayoffTree ? (
                    <PlayoffTree bracket={brackets[String(year)]} year={year} />
                  ) : (
                    <StandingsTable
                      rows={oneVOneMode === "wl" ? standings.wl : standings.cats}
                      previousRanks={
                        previousStandings
                          ? toRankMap(oneVOneMode === "wl" ? previousStandings.wl : previousStandings.cats)
                          : undefined
                      }
                    />
                  )}
                </CardContent>
              </Card>
            </>
          )}

          {view === "league_wins" && (
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
          )}

          {(view === "1v1" || view === "league_wins") &&
            showGraph &&
            historyChartData.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>Position Over Time</CardTitle>
                  <CardDescription>
                    Each team&apos;s {(view === "league_wins" ? leagueMode : oneVOneMode) === "wl" ? "W/L" : "Cats"} standings
                    place, week by week over the selected range
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

          {view === "ratings" && (
            <>
              <Card>
                <CardHeader>
                  <CardTitle>Ratings</CardTitle>
                  <CardDescription>Ranked by overall Weighted Rank rating</CardDescription>
                  <CardAction>
                    <label className="flex items-center gap-2 text-[11px] font-bold tracking-wider uppercase">
                      <span className="text-muted-foreground">Table</span>
                      <Switch
                        checked={ratingsDisplay === "leaders"}
                        onCheckedChange={(checked) => setRatingsDisplay(checked ? "leaders" : "table")}
                      />
                      <span className="text-muted-foreground">Leaders/Losers</span>
                    </label>
                  </CardAction>
                </CardHeader>
                <CardContent className="flex flex-col gap-4">
                  <div className="flex flex-wrap items-center gap-6">
                    <label className="flex items-center gap-2 text-[11px] font-bold tracking-wider uppercase">
                      <span className="text-muted-foreground">Totals</span>
                      <Switch
                        checked={ratingsStatMode === "averages"}
                        onCheckedChange={(checked) => setRatingsStatMode(checked ? "averages" : "totals")}
                      />
                      <span className="text-muted-foreground">Averages</span>
                    </label>
                    <div className="flex items-center gap-3 text-[11px] font-bold tracking-wider uppercase">
                      <label className="flex items-center gap-1.5">
                        <Checkbox checked={ratingsRs} onCheckedChange={() => setRatingsRs((v) => !v)} />
                        <span className="text-muted-foreground">Reg Season</span>
                      </label>
                      <label className="flex items-center gap-1.5">
                        <Checkbox checked={ratingsPo} onCheckedChange={() => setRatingsPo((v) => !v)} />
                        <span className="text-muted-foreground">Playoffs</span>
                      </label>
                    </div>
                    <LabeledSelect
                      label="Focus team"
                      value={ratingsFocusTeam}
                      onValueChange={setRatingsFocusTeam}
                      options={[
                        { value: NO_FOCUS_TEAM, label: "None" },
                        ...ratingsFocusOptions.map((m) => ({ value: m, label: m })),
                      ]}
                    />
                  </div>

                  {ratingsDisplay === "table" ? (
                    <StatTable
                      rows={ratingsRows}
                      mode="stat"
                      focusTeam={ratingsFocusTeam === NO_FOCUS_TEAM ? undefined : ratingsFocusTeam}
                    />
                  ) : (
                    ratingsLeaders && (
                      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                        {MAIN_CATS.map((cat) => {
                          const entry = ratingsLeaders[cat];
                          if (!entry) return null;
                          return (
                            <div key={cat} className="rounded-sm border border-border p-3">
                              <div className="text-[11px] font-bold tracking-wider text-muted-foreground uppercase">
                                {cat}
                              </div>
                              <div className="mt-2 flex items-center justify-between gap-2">
                                <span className="text-xs font-bold tracking-wide text-foreground uppercase">
                                  {entry.best.team}
                                </span>
                                <span className="font-mono text-sm font-extrabold tabular-nums text-foreground">
                                  {formatCatValue(cat, entry.best.value)}
                                </span>
                              </div>
                              <div className="mt-1 flex items-center justify-between gap-2">
                                <span className="text-xs font-bold tracking-wide text-muted-foreground uppercase">
                                  {entry.worst.team}
                                </span>
                                <span className="font-mono text-sm font-extrabold tabular-nums text-muted-foreground">
                                  {formatCatValue(cat, entry.worst.value)}
                                </span>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )
                  )}
                </CardContent>
              </Card>

              {showGraph && ratingsChartData.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle>Rating Over Time</CardTitle>
                    <CardDescription>
                      Each team&apos;s rating, averaged cumulatively from the range&apos;s first week through
                      each week shown
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="h-[360px] w-full">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={ratingsChartData} margin={{ left: 8, right: 16, top: 8, bottom: 24 }}>
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
                            width={40}
                            tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
                            stroke="var(--border)"
                            label={{
                              value: "Rating",
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
                            formatter={(value) => (typeof value === "number" ? value.toFixed(1) : value)}
                          />
                          {ratingsTeams.map((team, i) => (
                            <Line
                              key={team}
                              dataKey={team}
                              name={team}
                              stroke={ratingsColors[i]}
                              connectNulls
                              dot={{ r: 2 }}
                              isAnimationActive={false}
                            />
                          ))}
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                    <ChartLegend items={ratingsTeams.map((team, i) => ({ key: team, color: ratingsColors[i] }))} />
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
