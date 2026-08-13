"use client";

import { useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight } from "lucide-react";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { ChecklistGroup } from "@/components/filter-panel";
import { GenericFilterDrawer } from "@/components/generic-filter-drawer";
import { SourceLastUpdated } from "@/components/source-last-updated";
import { LoadingBasketballs } from "@/components/loading-basketballs";
import { getDraftPicks, type DraftPick, type LeagueMeta } from "@/lib/api";
import { cn } from "@/lib/utils";

// Unselecting every dimension IS "None" -- no separate None button/state
// (per the user's explicit ask). Player is mutually exclusive with Team/
// Year (not spec'd as combinable -- toggling one clears the other, see
// toggleGroupBy below) since a single player's identity already implies
// one row; combining it with Team/Year grouping has no defined column
// behavior in the spec this was built from.
interface DraftGroupBy {
  team: boolean;
  player: boolean;
  year: boolean;
}
const DEFAULT_GROUP_BY: DraftGroupBy = { team: false, player: false, year: false };

interface DraftFilters {
  years: number[];
  teams: string[];
}

interface DraftDisplayRow {
  key: string;
  year: number | null;
  player: string | null;
  team: string | null;
  round: number | null;
  roundPick: number | null;
  overallPick: number | null;
  draftScore: number;
  rank: number | null;
}

function parseRank(rank: string): number | null {
  const n = Number(rank);
  return Number.isFinite(n) ? n : null;
}

function average(values: number[]): number | null {
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
}

// Real aggregation, not visual grouping -- one row per group value, with
// each column's meaning redefined per the user's exact spec:
// - Ungrouped: every pick is its own row, real values throughout.
// - Player group: Player = the player; Team/Round Pick/Year = N/A; Round
//   and Overall Pick = averaged (a player drafted more than once can have a
//   meaningful "typically picked around here"); Draft Score = total/average
//   (toggle); Rank = average.
// - Team and/or Year group: Team = team if Team selected else N/A; Year =
//   year if Year selected else N/A; Player/Round/Round Pick/Overall Pick =
//   N/A (no single coherent value across many different picks); Draft
//   Score = total/average; Rank = average.
function aggregateDraftPicks(
  picks: DraftPick[],
  groupBy: DraftGroupBy,
  statMode: "totals" | "averages",
): DraftDisplayRow[] {
  const isGrouped = groupBy.team || groupBy.player || groupBy.year;

  if (!isGrouped) {
    return picks.map((p) => ({
      key: `${p.Year}-${p.Overall}-${p.Team}`,
      year: p.Year,
      player: p.Player,
      team: p.Team,
      round: p.Round,
      roundPick: p.Pick,
      overallPick: p.Overall,
      draftScore: p.Score,
      rank: parseRank(p.Rank),
    }));
  }

  const groups = new Map<string, DraftPick[]>();
  for (const p of picks) {
    const key = groupBy.player ? `player:${p.Player}` : `team:${groupBy.team ? p.Team : ""}|year:${groupBy.year ? p.Year : ""}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(p);
  }

  const rows: DraftDisplayRow[] = [];
  for (const [key, groupPicks] of groups) {
    const scores = groupPicks.map((p) => p.Score);
    const scoreSum = scores.reduce((a, b) => a + b, 0);
    const draftScore = statMode === "totals" ? scoreSum : scoreSum / scores.length;
    const rank = average(groupPicks.map((p) => parseRank(p.Rank)).filter((r): r is number => r !== null));

    if (groupBy.player) {
      rows.push({
        key,
        year: null,
        player: groupPicks[0].Player,
        team: null,
        round: average(groupPicks.map((p) => p.Round)),
        roundPick: null,
        overallPick: average(groupPicks.map((p) => p.Overall)),
        draftScore,
        rank,
      });
    } else {
      rows.push({
        key,
        year: groupBy.year ? groupPicks[0].Year : null,
        player: null,
        team: groupBy.team ? groupPicks[0].Team : null,
        round: null,
        roundPick: null,
        overallPick: null,
        draftScore,
        rank,
      });
    }
  }
  return rows;
}

function formatNum(value: number | null): string {
  if (value === null) return "—";
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

type SortKey = "year" | "player" | "team" | "round" | "roundPick" | "overallPick" | "draftScore" | "rank";
type SortDir = "desc" | "asc";
interface SortState {
  key: SortKey;
  dir: SortDir;
}

const COLUMN_LABELS: Record<SortKey, string> = {
  year: "Year",
  player: "Player",
  team: "Team",
  round: "Round",
  roundPick: "Round Pick",
  overallPick: "Overall Pick",
  draftScore: "Draft Score",
  rank: "Rank",
};

const RIGHT_ALIGNED = new Set<SortKey>(["round", "roundPick", "overallPick", "draftScore", "rank"]);

function cellClassName(key: SortKey): string {
  if (key === "player") return "font-sans font-semibold";
  if (key === "team") return "font-sans font-extrabold tracking-wide uppercase";
  if (key === "draftScore") return "text-right font-extrabold text-primary";
  if (key === "rank") return "text-right text-muted-foreground";
  if (key === "year") return "text-muted-foreground";
  return "text-right";
}

function cellValue(row: DraftDisplayRow, key: SortKey): ReactNode {
  if (key === "year") return row.year ?? "—";
  if (key === "player") return row.player ?? "—";
  if (key === "team") return row.team ?? "—";
  return formatNum(row[key]);
}

// Whichever identity dimensions (Team/Player/Year) are the active group-by
// become the leftmost, frozen columns, immediately followed by Draft Score
// (per the user's exact spec) -- Team/Year keep their button order (Team
// before Year) when both are active, Player is always alone (see the
// mutual-exclusivity comment on toggleGroupBy). Ungrouped: no frozen
// columns, Year/Player/Team stay in their natural order up front, and
// Draft Score simply moves to right after them.
function getColumnLayout(groupBy: DraftGroupBy): { order: SortKey[]; frozen: SortKey[] } {
  if (!groupBy.team && !groupBy.player && !groupBy.year) {
    return { order: ["year", "player", "team", "draftScore", "round", "roundPick", "overallPick", "rank"], frozen: [] };
  }
  const frozen: SortKey[] = groupBy.player ? ["player"] : (["team", "year"] as const).filter((k) => groupBy[k]);
  const remainingIdentity = (["year", "player", "team"] as SortKey[]).filter((k) => !frozen.includes(k));
  return {
    order: [...frozen, "draftScore", ...remainingIdentity, "round", "roundPick", "overallPick", "rank"],
    frozen,
  };
}

function DraftSortHead({
  sortKey,
  sort,
  onToggle,
  className,
  style,
  headerRef,
  children,
}: {
  sortKey: SortKey;
  sort: SortState;
  onToggle: (key: SortKey) => void;
  className?: string;
  style?: CSSProperties;
  headerRef?: (el: HTMLTableCellElement | null) => void;
  children: ReactNode;
}) {
  const active = sort.key === sortKey;
  return (
    <TableHead ref={headerRef} className={className} style={style}>
      <button
        type="button"
        onClick={() => onToggle(sortKey)}
        className={cn("inline-flex items-center gap-0.5 hover:text-foreground", active && "text-foreground")}
      >
        {children}
        {active && (sort.dir === "desc" ? <ArrowDown className="size-3" /> : <ArrowUp className="size-3" />)}
      </button>
    </TableHead>
  );
}

const PAGE_SIZE = 25;

export function DraftHub({ meta }: { meta: LeagueMeta }) {
  const [filters, setFilters] = useState<DraftFilters>({ years: meta.years, teams: meta.members });
  const [groupBy, setGroupBy] = useState<DraftGroupBy>(DEFAULT_GROUP_BY);
  const [statMode, setStatMode] = useState<"totals" | "averages">("totals");
  const [picks, setPicks] = useState<DraftPick[]>([]);
  const [picksLoading, setPicksLoading] = useState(true);
  const [sort, setSort] = useState<SortState>({ key: "draftScore", dir: "desc" });
  const [page, setPage] = useState(0);

  useEffect(() => {
    setPicksLoading(true);
    getDraftPicks({ years: filters.years, teams: filters.teams })
      .then(setPicks)
      .finally(() => setPicksLoading(false));
  }, [filters]);

  useEffect(() => {
    setPage(0);
  }, [filters, groupBy, statMode]);

  const isGrouped = groupBy.team || groupBy.player || groupBy.year;

  function toggleGroupBy(dim: keyof DraftGroupBy) {
    setGroupBy((g) => {
      if (dim === "player") return g.player ? DEFAULT_GROUP_BY : { team: false, player: true, year: false };
      return { ...g, player: false, [dim]: !g[dim] };
    });
  }

  function toggleSort(key: SortKey) {
    setSort((prev) => (prev.key === key ? { key, dir: prev.dir === "desc" ? "asc" : "desc" } : { key, dir: "desc" }));
  }

  const rows = useMemo(() => aggregateDraftPicks(picks, groupBy, statMode), [picks, groupBy, statMode]);

  const sortedRows = useMemo(() => {
    const { key, dir } = sort;
    function value(row: DraftDisplayRow): number | string | null {
      if (key === "player") return row.player;
      if (key === "team") return row.team;
      return row[key];
    }
    return [...rows].sort((a, b) => {
      const av = value(a);
      const bv = value(b);
      if (av === null && bv === null) return 0;
      if (av === null) return 1;
      if (bv === null) return -1;
      if (typeof av === "string" || typeof bv === "string") {
        const cmp = String(av).localeCompare(String(bv));
        return dir === "asc" ? cmp : -cmp;
      }
      return dir === "asc" ? av - bv : bv - av;
    });
  }, [rows, sort]);

  const pageCount = Math.max(1, Math.ceil(sortedRows.length / PAGE_SIZE));
  const pageRows = sortedRows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const { order: columnOrder, frozen: frozenColumns } = useMemo(() => getColumnLayout(groupBy), [groupBy]);

  // Cumulative left offsets for the frozen (group-by) columns, measured off
  // the header cells' real rendered widths -- same reasoning as StatTable's
  // sticky Score column (a hardcoded offset drifts out of sync with actual
  // content width, e.g. "Chirayu" vs "Sai"). At most 2 frozen columns here
  // (Team+Year, or Player alone), so a plain ref map is simpler than a
  // generic N-column sticky-offset abstraction.
  const frozenHeaderRefs = useRef<Partial<Record<SortKey, HTMLTableCellElement | null>>>({});
  const [frozenOffsets, setFrozenOffsets] = useState<Partial<Record<SortKey, number>>>({});
  const frozenKey = frozenColumns.join("|");
  useEffect(() => {
    function recompute() {
      let sum = 0;
      const next: Partial<Record<SortKey, number>> = {};
      for (const key of frozenColumns) {
        next[key] = sum;
        sum += frozenHeaderRefs.current[key]?.getBoundingClientRect().width ?? 0;
      }
      setFrozenOffsets(next);
    }
    recompute();
    const observers = frozenColumns
      .map((key) => frozenHeaderRefs.current[key])
      .filter((el): el is HTMLTableCellElement => !!el)
      .map((el) => {
        const observer = new ResizeObserver(recompute);
        observer.observe(el);
        return observer;
      });
    return () => observers.forEach((o) => o.disconnect());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frozenKey, pageRows.length]);

  function stickyProps(key: SortKey): { className: string; style?: CSSProperties; ref?: (el: HTMLTableCellElement | null) => void } {
    if (!frozenColumns.includes(key)) return { className: "" };
    return {
      className: "sticky z-10 bg-card",
      style: { left: frozenOffsets[key] ?? 0 },
      ref: (el) => {
        frozenHeaderRefs.current[key] = el;
      },
    };
  }

  return (
    <div className="flex flex-col gap-4 sm:flex-row">
      <div className="hidden sm:flex sm:w-64 sm:shrink-0 sm:flex-col sm:gap-3">
        <ChecklistGroup
          label="Season"
          options={meta.years}
          selected={filters.years}
          onChange={(years) => setFilters((f) => ({ ...f, years }))}
          scrollable
        />
        <ChecklistGroup
          label="Team"
          options={meta.members}
          selected={filters.teams}
          onChange={(teams) => setFilters((f) => ({ ...f, teams }))}
          scrollable
        />
      </div>

      <div className="flex flex-1 flex-col gap-4">
        <div className="sm:hidden">
          <GenericFilterDrawer
            value={filters}
            onChange={setFilters}
            renderContent={(draft, setDraft) => (
              <div className="flex flex-col gap-3">
                <ChecklistGroup
                  label="Season"
                  options={meta.years}
                  selected={draft.years}
                  onChange={(years) => setDraft({ ...draft, years })}
                  scrollable
                />
                <ChecklistGroup
                  label="Team"
                  options={meta.members}
                  selected={draft.teams}
                  onChange={(teams) => setDraft({ ...draft, teams })}
                  scrollable
                />
              </div>
            )}
          />
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Draft Hub</CardTitle>
            <CardDescription>
              Every draft pick across the selected seasons and teams -- group by to aggregate, click any column to sort
            </CardDescription>
            <CardAction>
              <SourceLastUpdated source="draft" />
            </CardAction>
          </CardHeader>
          <CardContent className="flex flex-wrap items-center gap-6">
            <div className="flex items-center gap-2 text-[11px] font-bold tracking-wider uppercase">
              <span className="text-muted-foreground">Group by</span>
              {(["team", "player", "year"] as const).map((dim) => (
                <Button
                  key={dim}
                  variant={groupBy[dim] ? "default" : "outline"}
                  size="sm"
                  onClick={() => toggleGroupBy(dim)}
                >
                  {dim[0].toUpperCase() + dim.slice(1)}
                </Button>
              ))}
            </div>
            <label
              className={cn(
                "flex items-center gap-2 text-[11px] font-bold tracking-wider uppercase",
                !isGrouped && "opacity-50",
              )}
            >
              <span className="text-muted-foreground">Total</span>
              <Switch
                disabled={!isGrouped}
                checked={statMode === "averages"}
                onCheckedChange={(checked) => setStatMode(checked ? "averages" : "totals")}
              />
              <span className="text-muted-foreground">Average</span>
            </label>
          </CardContent>
        </Card>

        <Card>
          <CardContent>
            {picksLoading ? (
              <LoadingBasketballs label="Loading" />
            ) : rows.length === 0 ? (
              <p className="text-sm text-muted-foreground">No picks for the current filters.</p>
            ) : (
              <>
                <Table>
                  <TableHeader>
                    <TableRow>
                      {columnOrder.map((key) => {
                        const sticky = stickyProps(key);
                        return (
                          <DraftSortHead
                            key={key}
                            sortKey={key}
                            sort={sort}
                            onToggle={toggleSort}
                            className={cn(RIGHT_ALIGNED.has(key) && "text-right", sticky.className)}
                            style={sticky.style}
                            headerRef={sticky.ref}
                          >
                            {COLUMN_LABELS[key]}
                          </DraftSortHead>
                        );
                      })}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {pageRows.map((row) => (
                      <TableRow key={row.key}>
                        {columnOrder.map((key) => {
                          const sticky = stickyProps(key);
                          return (
                            <TableCell key={key} className={cn(cellClassName(key), sticky.className)} style={sticky.style}>
                              {cellValue(row, key)}
                            </TableCell>
                          );
                        })}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>

                <div className="mt-4 flex items-center justify-center gap-3">
                  <Button
                    variant="outline"
                    size="icon-sm"
                    disabled={page === 0}
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                    aria-label="Previous page"
                  >
                    <ChevronLeft className="size-4" />
                  </Button>
                  <span className="text-xs text-muted-foreground">
                    Page {page + 1} of {pageCount}
                  </span>
                  <Button
                    variant="outline"
                    size="icon-sm"
                    disabled={page >= pageCount - 1}
                    onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
                    aria-label="Next page"
                  >
                    <ChevronRight className="size-4" />
                  </Button>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
