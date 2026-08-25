"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { SteppableSelect } from "@/components/steppable-select";
import { RoutedViewSwitcher } from "@/components/routed-view-switcher";
import { LoadingBasketballs } from "@/components/loading-basketballs";
import { StandingsTable, toRankMap } from "@/components/standings-table";
import { SeasonWeekRangeFilter } from "@/components/season-week-range-filter";
import { PositionOverTimeChart, buildHistoryChartData } from "@/components/position-over-time-chart";
import { categoricalPalette } from "@/lib/palette";
import {
  getStandings,
  getStandingsBootstrap,
  getStandingsHistory,
  type LeagueMeta,
  type StandingsHistoryResponse,
  type StandingsResponse,
} from "@/lib/api";

const VIEW_OPTIONS = [
  { value: "1v1", label: "Season Standings" },
  { value: "league_wins", label: "League Wins" },
  { value: "ratings", label: "Ratings" },
];
const VIEW_PATHS = { "1v1": "/standings", league_wins: "/standings/league-wins", ratings: "/standings/ratings" };

export default function LeagueWinsPage() {
  return (
    <Suspense fallback={<LoadingBasketballs label="Loading" />}>
      <LeagueWinsPageInner />
    </Suspense>
  );
}

// useSearchParams() (for the ?year= deep link) requires a Suspense boundary
// around whatever calls it, per Next.js.
function LeagueWinsPageInner() {
  const [meta, setMeta] = useState<LeagueMeta | null>(null);
  const [year, setYear] = useState<number | null>(null);
  const [weekRange, setWeekRange] = useState<[number, number] | null>(null);
  const [leagueMode, setLeagueMode] = useState<"wl" | "cats">("wl");
  const [showGraph, setShowGraph] = useState(true);
  const [standings, setStandings] = useState<StandingsResponse | null>(null);
  const [previousStandings, setPreviousStandings] = useState<StandingsResponse | null>(null);
  const [history, setHistory] = useState<StandingsHistoryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const searchParams = useSearchParams();
  // See standings/page.tsx's matching comment -- same bootstrap/skip
  // pattern, shared backend endpoint (both pages render the same
  // StandingsResponse/StandingsHistoryResponse shape, just different fields).
  const skipNextFetch = useRef(false);

  useEffect(() => {
    const yearFromUrl = Number(searchParams.get("year"));
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
    setLeagueMode(meta.season_format[String(year)] ?? "wl");
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
    const key = leagueMode === "wl" ? "league_wl" : "league_cats";
    return buildHistoryChartData(history[key], weekRange[0], weekRange[1]);
  }, [history, leagueMode, weekRange]);
  const historyTeams = useMemo(() => {
    if (!history) return [];
    const key = leagueMode === "wl" ? "league_wl" : "league_cats";
    return Object.keys(history[key]).sort();
  }, [history, leagueMode]);
  const historyColors = useMemo(() => categoricalPalette(historyTeams.length), [historyTeams.length]);

  if (!meta || year == null || !weekRange) return <LoadingBasketballs label="Loading" />;

  return (
    <div className="flex flex-col gap-4">
      <div className="sticky top-0 z-30 flex flex-wrap items-center gap-3 rounded-sm border border-border bg-card px-3 py-2 shadow-sm">
        <SteppableSelect label="Season" value={year} onValueChange={setYear} options={meta.years} />
        <RoutedViewSwitcher options={VIEW_OPTIONS} current="league_wins" paths={VIEW_PATHS} />
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
          {error ? (
            <p className="text-sm text-muted-foreground">No data for the current filters ({error}).</p>
          ) : isLoading || !standings ? (
            <LoadingBasketballs label="Loading standings" />
          ) : (
            <StandingsTable
              rows={leagueMode === "wl" ? standings.league_wl : standings.league_cats}
              previousRanks={
                previousStandings
                  ? toRankMap(leagueMode === "wl" ? previousStandings.league_wl : previousStandings.league_cats)
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
          modeLabel={leagueMode === "wl" ? "W/L" : "Cats"}
        />
      )}
    </div>
  );
}
