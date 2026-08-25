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
import { StatTable } from "@/components/stat-table";
import { FilterPanel, type FilterPanelValue } from "@/components/filter-panel";
import { FilterDrawer } from "@/components/filter-drawer";
import { LabeledSelect, NO_FOCUS_TEAM } from "@/components/labeled-select";
import { SourceLastUpdated } from "@/components/source-last-updated";
import { LoadingBasketballs } from "@/components/loading-basketballs";
import { useSelectedTeam } from "@/lib/use-selected-team";
import {
  getAverages,
  getCareerBootstrap,
  getTotals,
  type AggregateRow,
  type LeagueMeta,
} from "@/lib/api";

export default function CareerStatsPage() {
  const [meta, setMeta] = useState<LeagueMeta | null>(null);
  const [mode, setMode] = useState<"stat" | "rating">("stat");
  const [statMode, setStatMode] = useState<"totals" | "averages">("totals");
  const [focusTeam, setFocusTeam, focusTeamHydrated] = useSelectedTeam(NO_FOCUS_TEAM);
  const [filter, setFilter] = useState<FilterPanelValue | null>(null);
  const [rows, setRows] = useState<AggregateRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  // Bootstrap fetches meta + the default (everything-selected) totals in one
  // round-trip; this flags that the next [filter, statMode] effect run is
  // that same default, so it doesn't re-fetch what bootstrap already
  // delivered. See web/src/app/page.tsx's matching comment.
  const skipNextFetch = useRef(false);

  useEffect(() => {
    getCareerBootstrap().then((b) => {
      setMeta(b.meta);
      setFilter({ years: b.years, weeks: b.weeks, teams: b.teams, rs: true, po: true });
      skipNextFetch.current = true;
      const priorRanks = new Map(b.previous_rows.map((r) => [r.team, r.rank]));
      setRows(b.rows.map((r) => ({ ...r, previousRank: priorRanks.get(r.team) ?? null })));
      setError(null);
      setLoading(false);
    });
  }, []);

  useEffect(() => {
    if (!filter) return;
    if (skipNextFetch.current) {
      skipNextFetch.current = false;
      return;
    }
    setLoading(true);
    const req = {
      years: filter.years,
      weeks: filter.weeks,
      teams: filter.teams,
      RS: filter.rs,
      PO: filter.po,
    };
    const fetcher = statMode === "totals" ? getTotals : getAverages;

    // "Prior" standings: the same filter with its single highest selected
    // week dropped, so the Rank column can show a green/red movement arrow
    // for one week's worth of change. Skipped (no arrow shown) when only
    // one week is selected -- there's no earlier state to compare against.
    const maxWeek = filter.weeks.length ? Math.max(...filter.weeks) : null;
    const priorReq =
      maxWeek != null && filter.weeks.length > 1
        ? { ...req, weeks: filter.weeks.filter((w) => w !== maxWeek) }
        : null;

    Promise.all([fetcher(req), priorReq ? fetcher(priorReq) : Promise.resolve(null)])
      .then(([current, prior]) => {
        const priorRanks = new Map((prior ?? []).map((r) => [r.team, r.rank]));
        setRows(current.map((r) => ({ ...r, previousRank: priorRanks.get(r.team) ?? null })));
        setError(null);
      })
      .catch((err) => {
        setRows([]);
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => setLoading(false));
  }, [filter, statMode]);

  const allWeeks = useMemo(() => {
    if (!meta) return [];
    const maxWeek = Math.max(...Object.values(meta.total_matchup_count), 1);
    return Array.from({ length: maxWeek }, (_, i) => i + 1);
  }, [meta]);

  // Only teams actually shown in the current filtered rows, not the full
  // league roster.
  const focusOptions = useMemo(() => [...rows.map((r) => r.team)].sort(), [rows]);

  // Default (and re-default, if the current focus team disappears from a
  // new filter's rows) to whichever team ranks #1. AggregateRow.rank is
  // already a plain full-league ranking (no bracket-exclusion gap like
  // Weekly Stats' week_rank), so it can be used directly.
  useEffect(() => {
    if (!focusTeamHydrated || rows.length === 0) return;
    const teamsShown = new Set(rows.map((r) => r.team));
    if (focusTeam !== NO_FOCUS_TEAM && teamsShown.has(focusTeam)) return;
    const topTeam = rows.find((r) => r.rank === 1);
    setFocusTeam(topTeam?.team ?? NO_FOCUS_TEAM);
  }, [rows, focusTeam, focusTeamHydrated]);

  if (!meta || !filter) return <LoadingBasketballs label="Loading" />;

  return (
    <div className="flex flex-col gap-4 sm:flex-row">
      <div className="hidden sm:block sm:w-64 sm:shrink-0">
        <FilterPanel
          allYears={meta.years}
          allWeeks={allWeeks}
          allTeams={meta.members}
          value={filter}
          onChange={setFilter}
        />
      </div>

      <div className="flex flex-1 flex-col gap-4">
        <div className="sm:hidden">
          <FilterDrawer
            allYears={meta.years}
            allWeeks={allWeeks}
            allTeams={meta.members}
            value={filter}
            onChange={setFilter}
          />
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Career Stats</CardTitle>
            <CardDescription>
              Aggregate totals/averages across the selected seasons, weeks, and
              season type
            </CardDescription>
            <CardAction>
              <SourceLastUpdated source="live" />
            </CardAction>
          </CardHeader>
          <CardContent className="flex flex-wrap items-center gap-6">
            <label className="flex items-center gap-2 text-[11px] font-bold tracking-wider uppercase">
              <span className="text-muted-foreground">Totals</span>
              <Switch
                checked={statMode === "averages"}
                onCheckedChange={(checked) =>
                  setStatMode(checked ? "averages" : "totals")
                }
              />
              <span className="text-muted-foreground">Averages</span>
            </label>
            <label className="flex items-center gap-2 text-[11px] font-bold tracking-wider uppercase">
              <span className="text-muted-foreground">Stat</span>
              <Switch
                checked={mode === "rating"}
                onCheckedChange={(checked) => setMode(checked ? "rating" : "stat")}
              />
              <span className="text-muted-foreground">Rating</span>
            </label>
            <LabeledSelect
              label="Focus team"
              value={focusTeam}
              onValueChange={setFocusTeam}
              options={[
                { value: NO_FOCUS_TEAM, label: "None" },
                ...focusOptions.map((m) => ({ value: m, label: m })),
              ]}
            />
          </CardContent>
        </Card>

        <Card>
          <CardContent>
            {loading ? (
              <LoadingBasketballs label="Loading" />
            ) : error ? (
              <p className="text-sm text-muted-foreground">
                No data for the current filters ({error}).
              </p>
            ) : (
              <StatTable
                rows={rows}
                mode={mode}
                focusTeam={focusTeam === NO_FOCUS_TEAM ? undefined : focusTeam}
              />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
