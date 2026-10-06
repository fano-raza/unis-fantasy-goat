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
import { Button } from "@/components/ui/button";
import { StatTable } from "@/components/stat-table";
import { LabeledSelect, NO_FOCUS_TEAM } from "@/components/labeled-select";
import { SteppableSelect } from "@/components/steppable-select";
import { useSelectedTeam } from "@/lib/use-selected-team";
import {
  API_BASE_URL,
  getWeeklyLeaderboard,
  getWeeklyLeaderboardSeason,
  getWeeklyRecap,
  getWeeklyStatsBootstrap,
  type LeagueMeta,
  type SeasonWeeks,
  type WeekRow,
  type WeeklyRecap,
  type WeeklyStatsBootstrap,
} from "@/lib/api";
import { LoadingBasketballs } from "@/components/loading-basketballs";
import { LoadingOverlay } from "@/components/loading-overlay";
import { cn } from "@/lib/utils";

// Standard competition ranking (ties share a rank) over just the rows
// actually shown, using each row's rating -- NOT the backend's raw `rank`.
// On playoff weeks the backend's rank is relative to a broader hidden pool
// (bracket + consolation, kept that way deliberately to match GDoc/Discord
// bot parity -- see dashboard_site/api/league_store.py::_ensure_rated_df),
// so the visible rows alone can show gaps like 3, 4, 5, 7. Re-ranking just
// what's on screen gives a clean 1..N sequence without touching that shared
// backend math. BYE rows (rating: null) are excluded, same as they are from
// the rating pool itself.
function computeDisplayRanks(rows: WeekRow[]): Map<string, number> {
  const ranked = rows.filter((r): r is WeekRow & { rating: number } => r.rating != null);
  const ranks = new Map<string, number>();
  for (const row of ranked) {
    const better = ranked.filter((r) => r.rating > row.rating).length;
    ranks.set(row.team, better + 1);
  }
  return ranks;
}

interface WeeklyStatsViewProps {
  // Fetched server-side (see app/page.tsx) so the bootstrap round-trip to
  // the backend happens during SSR/ISR instead of after the client
  // downloads, parses, and hydrates the page's JS -- null if the server
  // fetch failed (backend unreachable at render time), in which case this
  // falls back to the client-side fetch exactly as before.
  initialBootstrap: WeeklyStatsBootstrap | null;
}

export function WeeklyStatsView({ initialBootstrap }: WeeklyStatsViewProps) {
  return (
    <Suspense fallback={<LoadingBasketballs label="Loading" />}>
      <WeeklyStatsPageInner initialBootstrap={initialBootstrap} />
    </Suspense>
  );
}

// useSearchParams() (for the ?year=&week= deep link -- StatBot's Monday
// "Week N Rankings" post links here) requires a Suspense boundary around
// whatever calls it, per Next.js.
function WeeklyStatsPageInner({ initialBootstrap }: WeeklyStatsViewProps) {
  const [meta, setMeta] = useState<LeagueMeta | null>(initialBootstrap?.meta ?? null);
  const [metaError, setMetaError] = useState<unknown>(null);
  const [year, setYear] = useState<number | null>(null);
  const [week, setWeek] = useState<number | null>(null);
  const [focusTeam, setFocusTeam, focusTeamHydrated] = useSelectedTeam(NO_FOCUS_TEAM);
  const [mode, setMode] = useState<"stat" | "rating">("stat");
  const [rows, setRows] = useState<WeekRow[]>([]);
  const [rowsError, setRowsError] = useState<string | null>(null);
  const [rowsLoading, setRowsLoading] = useState(true);
  const [recap, setRecap] = useState<WeeklyRecap | null>(null);
  // Bootstrap fetches meta + the current week's rows in one round-trip; this
  // flags that the next [year, week] effect run is that same initial pair,
  // so it doesn't re-fetch what bootstrap already delivered.
  const skipNextLeaderboardFetch = useRef(false);
  // Every year's weeks fetched so far, keyed by year -- seeded from the
  // bootstrap's current-year season slice, then grown on demand whenever
  // the user switches to a year not yet in here (see the [year, week]
  // effect below). Switching weeks WITHIN an already-cached year is then a
  // synchronous lookup, not a fetch -- the whole point of this cache.
  const seasonCacheRef = useRef<Map<number, SeasonWeeks>>(new Map());

  const searchParams = useSearchParams();

  useEffect(() => {
    const yearFromUrl = Number(searchParams.get("year"));
    const weekFromUrl = Number(searchParams.get("week"));

    // Resolves the fetched-from-wherever bootstrap payload (server-provided
    // prop, or -- if that failed -- the client's own fetch below) the same
    // way regardless of source.
    function applyBootstrap(m: LeagueMeta, r: WeekRow[], season: SeasonWeeks) {
      setMeta(m);
      seasonCacheRef.current.set(m.current_year, season);
      // A deep link (e.g. StatBot's weekly rankings post) always names a
      // real, already-completed week -- fall through to the normal
      // [year, week] fetch effect below instead of using bootstrap's
      // current-week rows.
      const hasOverride = m.years.includes(yearFromUrl) && weekFromUrl >= 1;
      if (hasOverride) {
        setYear(yearFromUrl);
        setWeek(weekFromUrl);
        setRowsError(null);
        return;
      }
      skipNextLeaderboardFetch.current = true;
      setRows(r);
      setRowsError(null);
      setRowsLoading(false);
      setYear(m.current_year);
      setWeek(m.current_week);
    }

    if (initialBootstrap) {
      applyBootstrap(initialBootstrap.meta, initialBootstrap.rows, initialBootstrap.season);
      return;
    }

    getWeeklyStatsBootstrap()
      .then(({ meta: m, rows: r, season }) => applyBootstrap(m, r, season))
      .catch(setMetaError);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (year == null || week == null) return;
    getWeeklyRecap({ year, week })
      .then(setRecap)
      .catch(() => setRecap(null));
  }, [year, week]);

  useEffect(() => {
    if (year == null || week == null) return;
    if (skipNextLeaderboardFetch.current) {
      skipNextLeaderboardFetch.current = false;
      return;
    }

    // Fast path: this year's weeks are already cached (from bootstrap, or
    // from a previous switch to this year) -- synchronous, no fetch, no
    // loading flicker.
    const cachedWeek = seasonCacheRef.current.get(year)?.[String(week)];
    if (cachedWeek) {
      setRows(cachedWeek);
      setRowsError(null);
      setRowsLoading(false);
      return;
    }

    let cancelled = false;
    setRowsLoading(true);

    async function load() {
      try {
        let season = seasonCacheRef.current.get(year as number);
        if (!season) {
          season = await getWeeklyLeaderboardSeason(year as number);
          seasonCacheRef.current.set(year as number, season);
        }
        if (cancelled) return;
        const weekRows = season[String(week)];
        if (weekRows) {
          setRows(weekRows);
          setRowsError(null);
          return;
        }
        // Defensive fallback -- the season endpoint covers every real week,
        // so this shouldn't normally trigger, but a single-week fetch still
        // works standalone if it ever does.
        const r = await getWeeklyLeaderboard({ year: year as number, week: week as number });
        if (cancelled) return;
        setRows(r);
        setRowsError(null);
      } catch (err) {
        if (cancelled) return;
        setRows([]);
        setRowsError(err instanceof Error ? err.message : String(err));
      } finally {
        if (!cancelled) setRowsLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [year, week]);

  const displayRanks = useMemo(() => computeDisplayRanks(rows), [rows]);
  const displayRows = useMemo(
    () => rows.map((r) => ({ ...r, rank: displayRanks.get(r.team) ?? null })),
    [rows, displayRanks],
  );

  // Default (and re-default, if the current focus team disappears from a
  // new week's table) to whichever team displays as #1. Left alone once the
  // user manually picks a team that's still shown.
  useEffect(() => {
    if (!focusTeamHydrated || rows.length === 0) return;
    const teamsShown = new Set(rows.map((r) => r.team));
    if (focusTeam !== NO_FOCUS_TEAM && teamsShown.has(focusTeam)) return;
    const topTeam = rows.find((r) => displayRanks.get(r.team) === 1);
    setFocusTeam(topTeam?.team ?? NO_FOCUS_TEAM);
  }, [rows, displayRanks, focusTeam, focusTeamHydrated]);

  const weekOptions = useMemo(() => {
    if (!meta || year == null) return [];
    const max = meta.total_matchup_count[String(year)] ?? 1;
    return Array.from({ length: max }, (_, i) => i + 1);
  }, [meta, year]);

  // Only teams actually shown this week (now includes BYE teams), not the
  // full league roster.
  const focusOptions = useMemo(() => [...rows.map((r) => r.team)].sort(), [rows]);

  if (metaError) return <BackendUnreachable error={metaError} />;
  if (!meta || year == null || week == null) return <LoadingBasketballs label="Loading" />;

  const isPlayoffWeek = week > (meta.rs_week_count[String(year)] ?? Infinity);

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Weekly Stats</CardTitle>
          <CardDescription>
            League table for a given season and week
          </CardDescription>
        </CardHeader>
        <CardContent
          className={cn(
            "flex flex-wrap items-center gap-4",
            isPlayoffWeek && "rounded-sm border-2 border-[#4169E1] p-3",
          )}
        >
          <SteppableSelect label="Season" value={year} onValueChange={setYear} options={meta.years} />
          <div className="flex items-center gap-1">
            <SteppableSelect label="Week" value={week} onValueChange={setWeek} options={weekOptions} />
            {isPlayoffWeek && (
              <span className="rounded-sm bg-[#4169E1]/15 px-1.5 py-0.5 text-[10px] font-bold tracking-wider text-[#4169E1] uppercase">
                PLAYOFFS
              </span>
            )}
          </div>
          <Button
            variant="secondary"
            size="sm"
            disabled={year === meta.current_year && week === meta.current_week}
            onClick={() => {
              setYear(meta.current_year);
              setWeek(meta.current_week);
            }}
          >
            Current Week
          </Button>
          <LabeledSelect
            label="Focus team"
            value={focusTeam}
            onValueChange={setFocusTeam}
            options={[
              { value: NO_FOCUS_TEAM, label: "None" },
              ...focusOptions.map((m) => ({ value: m, label: m })),
            ]}
          />
          <label className="flex items-center gap-2 text-[11px] font-bold tracking-wider uppercase">
            <span className="text-muted-foreground">Stat</span>
            <Switch
              checked={mode === "rating"}
              onCheckedChange={(checked) => setMode(checked ? "rating" : "stat")}
            />
            <span className="text-muted-foreground">Rating</span>
          </label>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <LoadingOverlay active={rowsLoading} hasContent={rows.length > 0} label="Loading week">
            {rowsError ? (
              <p className="text-sm text-muted-foreground">
                No data for {year} week {week} ({rowsError}).
              </p>
            ) : (
              <StatTable
                rows={displayRows}
                mode={mode}
                focusTeam={focusTeam === NO_FOCUS_TEAM ? undefined : focusTeam}
                showFocusScore
              />
            )}
          </LoadingOverlay>
        </CardContent>
      </Card>

      {recap && (
        <Card>
          <CardHeader>
            <CardTitle>Week {recap.week} Recap</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {recap.beatdowns.length > 0 && (
              <div className="flex flex-col gap-1">
                <span className="text-[11px] font-bold tracking-wider text-muted-foreground uppercase">
                  Beatdowns
                </span>
                <ul className="flex flex-col gap-1">
                  {recap.beatdowns.map((s, i) => (
                    <li key={i} className="text-sm">
                      • {s}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {recap.upsets.length > 0 && (
              <div className="flex flex-col gap-1">
                <span className="text-[11px] font-bold tracking-wider text-muted-foreground uppercase">
                  Upsets
                </span>
                <ul className="flex flex-col gap-1">
                  {recap.upsets.map((s, i) => (
                    <li key={i} className="text-sm">
                      • {s}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {recap.milestones.length > 0 && (
              <div className="flex flex-col gap-1">
                <span className="text-[11px] font-bold tracking-wider text-muted-foreground uppercase">
                  Milestones
                </span>
                <ul className="flex flex-col gap-1">
                  {recap.milestones.map((s, i) => (
                    <li key={i} className="text-sm">
                      • {s}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {recap.playoff_race && (
              <div className="flex flex-col gap-1">
                <span className="text-[11px] font-bold tracking-wider text-muted-foreground uppercase">
                  Playoff Race
                </span>
                <p className="text-sm text-muted-foreground">{recap.playoff_race}</p>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function BackendUnreachable({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Backend unreachable</CardTitle>
        <CardDescription>
          Couldn&apos;t reach {API_BASE_URL}. Start it with:
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        <code className="rounded bg-muted px-2 py-1 text-xs">
          .venv-dashboard/bin/uvicorn dashboard_site.api.app:app --port 8090
        </code>
        <p className="text-sm text-muted-foreground">{message}</p>
      </CardContent>
    </Card>
  );
}
