"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { PlayoffTree } from "@/components/playoff-tree";
import { Switch } from "@/components/ui/switch";
import { SteppableSelect } from "@/components/steppable-select";
import { RoutedViewSwitcher } from "@/components/routed-view-switcher";
import { LoadingBasketballs } from "@/components/loading-basketballs";
import { StandingsTable, toRankMap } from "@/components/standings-table";
import { SeasonWeekRangeFilter } from "@/components/season-week-range-filter";
import { PositionOverTimeChart, buildHistoryChartData } from "@/components/position-over-time-chart";
import { categoricalPalette } from "@/lib/palette";
import {
  getPlayoffBrackets,
  getStandings,
  getStandingsBootstrap,
  getStandingsHistory,
  type LeagueMeta,
  type PlayoffBracketsResponse,
  type StandingsHistoryResponse,
  type StandingsResponse,
} from "@/lib/api";

const VIEW_OPTIONS = [
  { value: "1v1", label: "Season Standings" },
  { value: "league_wins", label: "League Wins" },
  { value: "ratings", label: "Ratings" },
];
const VIEW_PATHS = { "1v1": "/standings", league_wins: "/standings/league-wins", ratings: "/standings/ratings" };

export default function StandingsPage() {
  return (
    <Suspense fallback={<LoadingBasketballs label="Loading" />}>
      <StandingsPageInner />
    </Suspense>
  );
}

// useSearchParams() (for the ?year=/?tree= deep links) requires a Suspense
// boundary around whatever calls it, per Next.js -- the actual page content
// lives here, wrapped by the plain default export above.
function StandingsPageInner() {
  const [meta, setMeta] = useState<LeagueMeta | null>(null);
  const [year, setYear] = useState<number | null>(null);
  const [weekRange, setWeekRange] = useState<[number, number] | null>(null);
  const [oneVOneMode, setOneVOneMode] = useState<"wl" | "cats">("wl");
  const [showGraph, setShowGraph] = useState(true);
  const [showPlayoffTree, setShowPlayoffTree] = useState(false);
  const [standings, setStandings] = useState<StandingsResponse | null>(null);
  const [previousStandings, setPreviousStandings] = useState<StandingsResponse | null>(null);
  const [history, setHistory] = useState<StandingsHistoryResponse | null>(null);
  const [brackets, setBrackets] = useState<PlayoffBracketsResponse>({});
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const searchParams = useSearchParams();
  // Bootstrap fetches meta + the current year's default-range standings in
  // one round-trip; this flags that the next [year, weekRange] effect run
  // is that same default pair, so it doesn't re-fetch what bootstrap
  // already delivered. Left false (and thus a no-op) when a ?year= deep
  // link overrides the default year below, since bootstrap's rows are for
  // the wrong year in that case.
  const skipNextFetch = useRef(false);

  useEffect(() => {
    // A ?year= link (from a Profile stat-tile deep link) wins over the
    // default current year, if it's a real year for this league. A ?tree=1
    // alongside it pre-enables the Playoff Tree toggle (both used by the
    // Profile stat-tile links).
    const yearFromUrl = Number(searchParams.get("year"));
    if (searchParams.get("tree") === "1") setShowPlayoffTree(true);
    getStandingsBootstrap().then((b) => {
      setMeta(b.meta);
      const overrideYear = b.meta.years.includes(yearFromUrl) && yearFromUrl !== b.year;
      if (overrideYear) {
        setYear(yearFromUrl);
        return;
      }
      setYear(b.year ?? b.meta.current_year);
      if (b.standings) {
        skipNextFetch.current = true;
        setStandings(b.standings);
        setPreviousStandings(b.previous_standings);
        setHistory(b.history);
        setError(null);
        setIsLoading(false);
      }
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

  // Default to whatever format that season actually used (some years were
  // scored by matchup W/L, others by aggregate category wins -- see
  // dashboard_site/api/league_store.py's SEASON_IS_WL). Resets whenever the
  // year changes, also covering the initial load.
  useEffect(() => {
    if (!meta || year == null) return;
    setOneVOneMode(meta.season_format[String(year)] ?? "wl");
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
    if (skipNextFetch.current) {
      skipNextFetch.current = false;
      return;
    }
    // Set immediately (not inside the debounced timeout below) so a filter
    // change shows the loading state right away instead of leaving the
    // previous year/week-range's stale standings (or a stale error from an
    // earlier request) on screen for the debounce window.
    setIsLoading(true);
    setError(null);
    const [minWeek, maxWeekSel] = weekRange;
    const timeout = setTimeout(() => {
      // "Prior" = the same range with its single latest week dropped, so
      // the Place column can show a green/red movement arrow. Skipped for
      // a single-week range -- there's no earlier state to compare to.
      const priorReq = maxWeekSel > minWeek ? { year, min_week: minWeek, max_week: maxWeekSel - 1 } : null;
      Promise.all([
        getStandings({ year, min_week: minWeek, max_week: maxWeekSel }),
        priorReq ? getStandings(priorReq).catch(() => null) : Promise.resolve(null),
        getStandingsHistory({ year, min_week: minWeek, max_week: maxWeekSel }),
      ])
        .then(([current, prior, hist]) => {
          setStandings(current);
          setPreviousStandings(prior);
          setHistory(hist);
        })
        .catch((err) => {
          setStandings(null);
          setPreviousStandings(null);
          setHistory(null);
          setError(err instanceof Error ? err.message : String(err));
        })
        .finally(() => setIsLoading(false));
    }, 200);
    return () => clearTimeout(timeout);
  }, [year, weekRange]);

  const historyChartData = useMemo(() => {
    if (!history || !weekRange) return [];
    return buildHistoryChartData(history[oneVOneMode], weekRange[0], weekRange[1]);
  }, [history, oneVOneMode, weekRange]);
  const historyTeams = useMemo(() => {
    if (!history) return [];
    return Object.keys(history[oneVOneMode]).sort();
  }, [history, oneVOneMode]);
  const historyColors = useMemo(() => categoricalPalette(historyTeams.length), [historyTeams.length]);

  if (!meta || year == null || !weekRange) return <LoadingBasketballs label="Loading" />;

  return (
    <div className="flex flex-col gap-4">
      <div className="sticky top-0 z-30 flex flex-wrap items-center gap-3 rounded-sm border border-border bg-card px-3 py-2 shadow-sm">
        <SteppableSelect label="Season" value={year} onValueChange={setYear} options={meta.years} />
        <RoutedViewSwitcher options={VIEW_OPTIONS} current="1v1" paths={VIEW_PATHS} />
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
          {/* Controls above stay interactive regardless of load state -- a
              failed/loading fetch only swaps out the data area below, so a
              bad filter combination can always be changed back. */}
          {error ? (
            <p className="text-sm text-muted-foreground">No data for the current filters ({error}).</p>
          ) : isLoading || !standings ? (
            <LoadingBasketballs label="Loading standings" />
          ) : showPlayoffTree ? (
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

      {showGraph && !error && !isLoading && historyChartData.length > 0 && (
        <PositionOverTimeChart
          data={historyChartData}
          teams={historyTeams}
          colors={historyColors}
          weekRange={weekRange}
          modeLabel={oneVOneMode === "wl" ? "W/L" : "Cats"}
        />
      )}
    </div>
  );
}
