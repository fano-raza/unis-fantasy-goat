"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Card,
  CardAction,
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
import { SourceLastUpdated } from "@/components/source-last-updated";
import {
  API_BASE_URL,
  getWeeklyLeaderboard,
  getWeeklyStatsBootstrap,
  type LeagueMeta,
  type WeekRow,
} from "@/lib/api";
import { LoadingBasketballs } from "@/components/loading-basketballs";
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

export default function WeeklyStatsPage() {
  const [meta, setMeta] = useState<LeagueMeta | null>(null);
  const [metaError, setMetaError] = useState<unknown>(null);
  const [year, setYear] = useState<number | null>(null);
  const [week, setWeek] = useState<number | null>(null);
  const [focusTeam, setFocusTeam, focusTeamHydrated] = useSelectedTeam(NO_FOCUS_TEAM);
  const [mode, setMode] = useState<"stat" | "rating">("stat");
  const [rows, setRows] = useState<WeekRow[]>([]);
  const [rowsError, setRowsError] = useState<string | null>(null);
  const [rowsLoading, setRowsLoading] = useState(true);
  // Bootstrap fetches meta + the current week's rows in one round-trip; this
  // flags that the next [year, week] effect run is that same initial pair,
  // so it doesn't re-fetch what bootstrap already delivered.
  const skipNextLeaderboardFetch = useRef(false);

  useEffect(() => {
    getWeeklyStatsBootstrap()
      .then(({ meta: m, rows: r }) => {
        setMeta(m);
        skipNextLeaderboardFetch.current = true;
        setRows(r);
        setRowsError(null);
        setRowsLoading(false);
        setYear(m.current_year);
        setWeek(m.current_week);
      })
      .catch(setMetaError);
  }, []);

  useEffect(() => {
    if (year == null || week == null) return;
    if (skipNextLeaderboardFetch.current) {
      skipNextLeaderboardFetch.current = false;
      return;
    }
    setRowsLoading(true);
    getWeeklyLeaderboard({ year, week })
      .then((r) => {
        setRows(r);
        setRowsError(null);
      })
      .catch((err) => {
        setRows([]);
        setRowsError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => setRowsLoading(false));
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
          <CardAction>
            <SourceLastUpdated source="live" />
          </CardAction>
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
          {rowsLoading ? (
            <LoadingBasketballs label="Loading week" />
          ) : rowsError ? (
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
        </CardContent>
      </Card>
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
