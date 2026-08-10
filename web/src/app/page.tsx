"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { StatTable } from "@/components/stat-table";
import { LabeledSelect, NO_FOCUS_TEAM } from "@/components/labeled-select";
import {
  API_BASE_URL,
  getLeagueMeta,
  getWeeklyLeaderboard,
  type LeagueMeta,
  type WeekRow,
} from "@/lib/api";

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
  const [focusTeam, setFocusTeam] = useState<string>(NO_FOCUS_TEAM);
  const [mode, setMode] = useState<"stat" | "rating">("stat");
  const [rows, setRows] = useState<WeekRow[]>([]);
  const [rowsError, setRowsError] = useState<string | null>(null);

  useEffect(() => {
    getLeagueMeta()
      .then((m) => {
        setMeta(m);
        setYear(m.current_year);
        setWeek(m.current_week);
      })
      .catch(setMetaError);
  }, []);

  useEffect(() => {
    if (year == null || week == null) return;
    getWeeklyLeaderboard({ year, week })
      .then((r) => {
        setRows(r);
        setRowsError(null);
      })
      .catch((err) => {
        setRows([]);
        setRowsError(err instanceof Error ? err.message : String(err));
      });
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
    const teamsShown = new Set(rows.map((r) => r.team));
    if (focusTeam !== NO_FOCUS_TEAM && teamsShown.has(focusTeam)) return;
    const topTeam = rows.find((r) => displayRanks.get(r.team) === 1);
    setFocusTeam(topTeam?.team ?? NO_FOCUS_TEAM);
  }, [rows, displayRanks, focusTeam]);

  const weekOptions = useMemo(() => {
    if (!meta || year == null) return [];
    const max = meta.total_matchup_count[String(year)] ?? 1;
    return Array.from({ length: max }, (_, i) => i + 1);
  }, [meta, year]);

  // Only teams actually shown this week (now includes BYE teams), not the
  // full league roster.
  const focusOptions = useMemo(() => [...rows.map((r) => r.team)].sort(), [rows]);

  if (metaError) return <BackendUnreachable error={metaError} />;
  if (!meta || year == null || week == null) return null;

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Weekly Stats</CardTitle>
          <CardDescription>
            League table for a given season and week
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-4">
          <LabeledSelect
            label="Season"
            value={String(year)}
            onValueChange={(v) => setYear(Number(v))}
            options={meta.years.map((y) => ({ value: String(y), label: String(y) }))}
          />
          <LabeledSelect
            label="Week"
            value={String(week)}
            onValueChange={(v) => setWeek(Number(v))}
            options={weekOptions.map((w) => ({ value: String(w), label: String(w) }))}
          />
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
