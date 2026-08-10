"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { AnalysisGraph } from "@/components/analysis-graph";
import { FilterPanel, type FilterPanelValue } from "@/components/filter-panel";
import { FilterDrawer } from "@/components/filter-drawer";
import { getAnalysisRows, getLeagueMeta, type AnalysisRow, type LeagueMeta } from "@/lib/api";

const MAX_GRAPHS = 3;
const FILTER_KEY = "analysis-filter";
const GRAPHS_KEY = "analysis-graphs";

interface SavedGraphs {
  ids: number[];
  nextId: number;
}

export default function AnalysisPage() {
  const [meta, setMeta] = useState<LeagueMeta | null>(null);
  const [filter, setFilter] = useState<FilterPanelValue | null>(null);
  const [rows, setRows] = useState<AnalysisRow[]>([]);
  const [graphIds, setGraphIds] = useState<number[]>([0]);
  const [nextGraphId, setNextGraphId] = useState(1);
  const [graphsHydrated, setGraphsHydrated] = useState(false);

  useEffect(() => {
    getLeagueMeta().then((m) => {
      setMeta(m);
      const maxWeek = Math.max(...Object.values(m.total_matchup_count), 1);
      const defaultFilter: FilterPanelValue = {
        years: m.years,
        weeks: Array.from({ length: maxWeek }, (_, i) => i + 1),
        teams: m.members,
        rs: true,
        po: true,
      };

      let restored = defaultFilter;
      try {
        const raw = localStorage.getItem(FILTER_KEY);
        if (raw) {
          const saved = JSON.parse(raw) as FilterPanelValue;
          restored = {
            years: saved.years.filter((y) => m.years.includes(y)),
            weeks: saved.weeks.filter((w) => w <= maxWeek),
            teams: saved.teams.filter((t) => m.members.includes(t)),
            rs: saved.rs,
            po: saved.po,
          };
        }
      } catch {}
      setFilter(restored);
    });
  }, []);

  useEffect(() => {
    if (filter) localStorage.setItem(FILTER_KEY, JSON.stringify(filter));
  }, [filter]);

  // Synchronous hydrate + a `hydrated` flag flipped in the same effect pass,
  // so the persist-effect below can't fire (and clobber storage with the
  // default [0]/1) before this read has happened -- see the identical
  // comment in comparison/page.tsx for why the guard has to be synchronous.
  useEffect(() => {
    try {
      const raw = localStorage.getItem(GRAPHS_KEY);
      if (raw) {
        const saved = JSON.parse(raw) as SavedGraphs;
        if (saved.ids?.length) {
          setGraphIds(saved.ids.slice(0, MAX_GRAPHS));
          setNextGraphId(saved.nextId);
        }
      }
    } catch {}
    setGraphsHydrated(true);
  }, []);

  useEffect(() => {
    if (!graphsHydrated) return;
    localStorage.setItem(GRAPHS_KEY, JSON.stringify({ ids: graphIds, nextId: nextGraphId }));
  }, [graphsHydrated, graphIds, nextGraphId]);

  useEffect(() => {
    if (!filter) return;
    getAnalysisRows({
      years: filter.years,
      weeks: filter.weeks,
      teams: filter.teams,
      RS: filter.rs,
      PO: filter.po,
    }).then(setRows);
  }, [filter]);

  const allWeeks = useMemo(() => {
    if (!meta) return [];
    const maxWeek = Math.max(...Object.values(meta.total_matchup_count), 1);
    return Array.from({ length: maxWeek }, (_, i) => i + 1);
  }, [meta]);

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
            <CardTitle>Analysis</CardTitle>
            <CardDescription>
              Build your own line graph(s) — all graphs share the filters but
              have their own axes and grouping
            </CardDescription>
          </CardHeader>
        </Card>

        {graphIds.map((id) => (
          <AnalysisGraph
            key={id}
            id={id}
            rows={rows}
            allYears={meta.years}
            onRemove={
              graphIds.length > 1
                ? () => {
                    localStorage.removeItem(`analysis-graph-${id}`);
                    setGraphIds((ids) => ids.filter((existing) => existing !== id));
                  }
                : undefined
            }
          />
        ))}

        {graphIds.length < MAX_GRAPHS && (
          <Button
            variant="outline"
            className="self-start"
            onClick={() => {
              setGraphIds((ids) => [...ids, nextGraphId]);
              setNextGraphId((n) => n + 1);
            }}
          >
            + Add graph
          </Button>
        )}
      </div>
    </div>
  );
}
