"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { StatTable } from "@/components/stat-table";
import { ChecklistGroup } from "@/components/filter-panel";
import { GenericFilterDrawer } from "@/components/generic-filter-drawer";
import { LabeledSelect, NO_FOCUS_TEAM } from "@/components/labeled-select";
import { SteppableSelect } from "@/components/steppable-select";
import { SourceLastUpdated } from "@/components/source-last-updated";
import { LoadingBasketballs } from "@/components/loading-basketballs";
import { getAverages, getLeagueMeta, type AggregateRow, type LeagueMeta } from "@/lib/api";

export default function UltraPage() {
  const [meta, setMeta] = useState<LeagueMeta | null>(null);
  const [year, setYear] = useState<number | null>(null);
  const [weeks, setWeeks] = useState<number[]>([]);
  const [focusTeam, setFocusTeam] = useState<string>(NO_FOCUS_TEAM);
  const [rows, setRows] = useState<AggregateRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getLeagueMeta().then((m) => {
      setMeta(m);
      setYear(m.current_year);
    });
  }, []);

  // total_matchup_count (not rs_week_count) so playoff weeks are included
  // among the selectable filters.
  const allWeeks = useMemo(() => {
    if (!meta || year == null) return [];
    const maxWeek = meta.total_matchup_count[String(year)] ?? 1;
    return Array.from({ length: maxWeek }, (_, i) => i + 1);
  }, [meta, year]);

  // Reset to every week selected whenever the year changes (also covers the
  // initial load, once meta/year are both set).
  useEffect(() => {
    if (allWeeks.length) setWeeks(allWeeks);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allWeeks.length, year]);

  useEffect(() => {
    if (year == null || weeks.length === 0) return;
    setLoading(true);
    getAverages({ years: [year], weeks, RS: true, PO: true })
      .then((res) => {
        setRows(res);
        setError(null);
      })
      .catch((err) => {
        setRows([]);
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => setLoading(false));
  }, [year, weeks]);

  // Only teams actually shown in the current filtered rows, not the full
  // league roster.
  const focusOptions = useMemo(() => [...rows.map((r) => r.team)].sort(), [rows]);

  // Default (and re-default, if the current focus team disappears from a
  // new year/week selection) to whichever team ranks #1.
  useEffect(() => {
    const teamsShown = new Set(rows.map((r) => r.team));
    if (focusTeam !== NO_FOCUS_TEAM && teamsShown.has(focusTeam)) return;
    const topTeam = rows.find((r) => r.rank === 1);
    setFocusTeam(topTeam?.team ?? NO_FOCUS_TEAM);
  }, [rows, focusTeam]);

  if (!meta || year == null) return <LoadingBasketballs label="Loading" />;

  return (
    <div className="flex flex-col gap-4 sm:flex-row">
      <div className="hidden sm:block sm:w-64 sm:shrink-0">
        <ChecklistGroup
          label="Week"
          options={allWeeks}
          selected={weeks}
          onChange={setWeeks}
          scrollable
        />
      </div>

      <div className="flex flex-1 flex-col gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Ultra</CardTitle>
            <CardDescription>
              Per-team averages across the selected season and weeks
            </CardDescription>
            <CardAction>
              <SourceLastUpdated source="live" />
            </CardAction>
          </CardHeader>
          <CardContent className="flex flex-wrap items-center gap-6">
            <SteppableSelect label="Season" value={year} onValueChange={setYear} options={meta.years} />
            <LabeledSelect
              label="Focus team"
              value={focusTeam}
              onValueChange={setFocusTeam}
              options={[
                { value: NO_FOCUS_TEAM, label: "None" },
                ...focusOptions.map((m) => ({ value: m, label: m })),
              ]}
            />
            <div className="sm:hidden">
              <GenericFilterDrawer
                value={weeks}
                onChange={setWeeks}
                renderContent={(draft, setDraft) => (
                  <ChecklistGroup label="Week" options={allWeeks} selected={draft} onChange={setDraft} scrollable />
                )}
              />
            </div>
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
                mode="stat"
                focusTeam={focusTeam === NO_FOCUS_TEAM ? undefined : focusTeam}
                showFocusScore
                pinFocusRow
                stickyHeaderOffset={0}
              />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
