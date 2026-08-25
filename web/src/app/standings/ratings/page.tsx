"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
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
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";
import { StatTable } from "@/components/stat-table";
import { LabeledSelect, NO_FOCUS_TEAM } from "@/components/labeled-select";
import { SteppableSelect } from "@/components/steppable-select";
import { RoutedViewSwitcher } from "@/components/routed-view-switcher";
import { useSelectedTeam } from "@/lib/use-selected-team";
import { LoadingBasketballs } from "@/components/loading-basketballs";
import { SeasonWeekRangeFilter } from "@/components/season-week-range-filter";
import { categoricalPalette } from "@/lib/palette";
import {
  getAnalysisRows,
  getAverages,
  getRatingsBootstrap,
  getSeasonLeaders,
  getTotals,
  MAIN_CATS,
  type AggregateRow,
  type AnalysisRow,
  type Category,
  type LeagueMeta,
  type SeasonLeadersResponse,
} from "@/lib/api";

const VIEW_OPTIONS = [
  { value: "1v1", label: "Season Standings" },
  { value: "league_wins", label: "League Wins" },
  { value: "ratings", label: "Ratings" },
];
const VIEW_PATHS = { "1v1": "/standings", league_wins: "/standings/league-wins", ratings: "/standings/ratings" };

function formatCatValue(cat: Category, value: number): string {
  if (cat === "FG%" || cat === "FT%") return value.toFixed(3);
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

// This view's graph: at week X, each team's value is the average of its
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

export default function RatingsPage() {
  return (
    <Suspense fallback={<LoadingBasketballs label="Loading" />}>
      <RatingsPageInner />
    </Suspense>
  );
}

// useSearchParams() (for the ?year= deep link) requires a Suspense boundary
// around whatever calls it, per Next.js.
function RatingsPageInner() {
  const [meta, setMeta] = useState<LeagueMeta | null>(null);
  const [year, setYear] = useState<number | null>(null);
  const [weekRange, setWeekRange] = useState<[number, number] | null>(null);
  const [showGraph, setShowGraph] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const [ratingsStatMode, setRatingsStatMode] = useState<"totals" | "averages">("totals");
  const [ratingsRs, setRatingsRs] = useState(true);
  const [ratingsPo, setRatingsPo] = useState(true);
  const [ratingsFocusTeam, setRatingsFocusTeam, ratingsFocusTeamHydrated] = useSelectedTeam(NO_FOCUS_TEAM);
  const [ratingsDisplay, setRatingsDisplay] = useState<"table" | "leaders">("table");
  const [ratingsRows, setRatingsRows] = useState<AggregateRow[]>([]);
  const [ratingsLeaders, setRatingsLeaders] = useState<SeasonLeadersResponse | null>(null);
  const [ratingsHistory, setRatingsHistory] = useState<AnalysisRow[]>([]);

  const searchParams = useSearchParams();
  // See standings/page.tsx's matching comment -- same bootstrap/skip
  // pattern. Bootstrap covers this page's default filters only (totals
  // mode, full RS-week range, RS+PO both on); a ?year= override or any
  // filter change afterward falls through to the normal fetch effect.
  const skipNextFetch = useRef(false);

  useEffect(() => {
    const yearFromUrl = Number(searchParams.get("year"));
    getRatingsBootstrap().then((b) => {
      setMeta(b.meta);
      const overrideYear = b.meta.years.includes(yearFromUrl) && yearFromUrl !== b.year;
      if (overrideYear) {
        setYear(yearFromUrl);
        return;
      }
      setYear(b.year ?? b.meta.current_year);
      skipNextFetch.current = true;
      const priorRanks = new Map(b.previous_rows.map((r) => [r.team, r.rank]));
      setRatingsRows(b.rows.map((r) => ({ ...r, previousRank: priorRanks.get(r.team) ?? null })));
      setRatingsLeaders(b.leaders);
      setRatingsHistory(b.history);
      setError(null);
      setIsLoading(false);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const maxWeek = useMemo(() => {
    if (!meta || year == null) return 1;
    return meta.rs_week_count[String(year)] ?? 1;
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
  // and this payload is tiny, so a full Apply-gated flow (like Career
  // Stats/Analysis' mobile filter drawer) would be unnecessary friction here.
  useEffect(() => {
    if (year == null || weeksInRange.length === 0) return;
    if (skipNextFetch.current) {
      skipNextFetch.current = false;
      return;
    }
    setIsLoading(true);
    setError(null);
    const timeout = setTimeout(() => {
      const ratingsReq = { years: [year], weeks: weeksInRange, RS: ratingsRs, PO: ratingsPo };
      const ratingsFetcher = ratingsStatMode === "totals" ? getTotals : getAverages;
      // "Prior" ratings: the same week set with its single highest week
      // dropped, so the Rank column can show a green/red movement arrow for
      // one week's worth of change -- same pattern as Career Stats' own
      // previousRank fetch. Skipped (no arrow) when only one week is
      // selected -- there's no earlier state to compare against.
      const ratingsMaxWeek = weeksInRange.length ? Math.max(...weeksInRange) : null;
      const priorRatingsReq =
        ratingsMaxWeek != null && weeksInRange.length > 1
          ? { ...ratingsReq, weeks: weeksInRange.filter((w) => w !== ratingsMaxWeek) }
          : null;
      Promise.all([
        ratingsFetcher(ratingsReq),
        priorRatingsReq ? ratingsFetcher(priorRatingsReq).catch(() => null) : Promise.resolve(null),
        getSeasonLeaders({ ...ratingsReq, mode: ratingsStatMode }),
        getAnalysisRows(ratingsReq),
      ])
        .then(([rows, priorRows, leaders, analysisRows]) => {
          const priorRanks = new Map((priorRows ?? []).map((r) => [r.team, r.rank]));
          setRatingsRows(rows.map((r) => ({ ...r, previousRank: priorRanks.get(r.team) ?? null })));
          setRatingsLeaders(leaders);
          setRatingsHistory(analysisRows);
        })
        .catch((err) => {
          setRatingsRows([]);
          setRatingsLeaders(null);
          setRatingsHistory([]);
          setError(err instanceof Error ? err.message : String(err));
        })
        .finally(() => setIsLoading(false));
    }, 200);
    return () => clearTimeout(timeout);
  }, [year, weeksInRange, ratingsStatMode, ratingsRs, ratingsPo]);

  // Only teams actually shown in the current ratings rows, not the full
  // league roster.
  const ratingsFocusOptions = useMemo(() => [...ratingsRows.map((r) => r.team)].sort(), [ratingsRows]);

  // Default (and re-default, if the current focus team disappears from a
  // new filter's rows) to whichever team ranks #1.
  useEffect(() => {
    if (!ratingsFocusTeamHydrated || ratingsRows.length === 0) return;
    const teamsShown = new Set(ratingsRows.map((r) => r.team));
    if (ratingsFocusTeam !== NO_FOCUS_TEAM && teamsShown.has(ratingsFocusTeam)) return;
    const topTeam = ratingsRows.find((r) => r.rank === 1);
    setRatingsFocusTeam(topTeam?.team ?? NO_FOCUS_TEAM);
  }, [ratingsRows, ratingsFocusTeam, ratingsFocusTeamHydrated]);

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
        <RoutedViewSwitcher options={VIEW_OPTIONS} current="ratings" paths={VIEW_PATHS} />
      </div>

      <SeasonWeekRangeFilter
        weekRange={weekRange}
        onWeekRangeChange={setWeekRange}
        maxWeek={maxWeek}
        showGraph={showGraph}
        onShowGraphChange={setShowGraph}
      />

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

          {/* Controls above stay interactive regardless of load state -- a
              failed/loading fetch only swaps out the data area below, so a
              bad filter combination can always be changed back. */}
          {error ? (
            <p className="text-sm text-muted-foreground">No data for the current filters ({error}).</p>
          ) : isLoading ? (
            <LoadingBasketballs label="Loading standings" />
          ) : ratingsDisplay === "table" ? (
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

      {showGraph && !error && !isLoading && ratingsChartData.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Rating Over Time</CardTitle>
            <CardDescription>
              Each team&apos;s rating, averaged cumulatively from the range&apos;s first week through each week shown
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
                    ticks={Array.from({ length: weekRange[1] - weekRange[0] + 1 }, (_, i) => weekRange[0] + i)}
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
                    itemSorter={(item) => (typeof item.value === "number" ? -item.value : 0)}
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
    </div>
  );
}
