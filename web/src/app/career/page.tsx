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
import { FilterPanel, type FilterPanelValue } from "@/components/filter-panel";
import { FilterDrawer } from "@/components/filter-drawer";
import { LabeledSelect, NO_FOCUS_TEAM } from "@/components/labeled-select";
import {
  getAverages,
  getLeagueMeta,
  getTotals,
  type AggregateRow,
  type LeagueMeta,
} from "@/lib/api";

export default function CareerStatsPage() {
  const [meta, setMeta] = useState<LeagueMeta | null>(null);
  const [mode, setMode] = useState<"stat" | "rating">("stat");
  const [statMode, setStatMode] = useState<"totals" | "averages">("totals");
  const [focusTeam, setFocusTeam] = useState<string>(NO_FOCUS_TEAM);
  const [filter, setFilter] = useState<FilterPanelValue | null>(null);
  const [rows, setRows] = useState<AggregateRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getLeagueMeta().then((m) => {
      setMeta(m);
      const maxWeek = Math.max(...Object.values(m.total_matchup_count), 1);
      setFilter({
        years: m.years,
        weeks: Array.from({ length: maxWeek }, (_, i) => i + 1),
        teams: m.members,
        rs: true,
        po: true,
      });
    });
  }, []);

  useEffect(() => {
    if (!filter) return;
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
      });
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
    const teamsShown = new Set(rows.map((r) => r.team));
    if (focusTeam !== NO_FOCUS_TEAM && teamsShown.has(focusTeam)) return;
    const topTeam = rows.find((r) => r.rank === 1);
    setFocusTeam(topTeam?.team ?? NO_FOCUS_TEAM);
  }, [rows, focusTeam]);

  if (!meta || !filter) return null;

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
            {error ? (
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
