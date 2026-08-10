"use client";

import { useMemo, useState, type ReactNode } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { MAIN_CATS, type Category, type CategoryStats } from "@/lib/api";
import { categoryScore, compareCell, comparisonClass, scoreClass } from "@/lib/highlight";
import { cn } from "@/lib/utils";
import { ArrowDown, ArrowUp } from "lucide-react";

export interface StatTableRow {
  team: string;
  stats: CategoryStats;
  ratings: CategoryStats;
  rating: number | null;
  rank: number | null;
  // Rank as of one week earlier than the current selection -- when present
  // and different from `rank`, StatTable renders a green/red movement
  // arrow. Left unset by pages that don't compute this (e.g. Weekly Stats).
  previousRank?: number | null;
}

export type StatDisplayMode = "stat" | "rating";

interface StatTableProps {
  rows: StatTableRow[];
  mode: StatDisplayMode;
  focusTeam?: string;
  // Weekly Stats only -- an extra column giving the focus team's all-play
  // category W-L-T against each other row's raw stats. Off by default so
  // Career Stats/Profile's StatTable usages are unaffected.
  showFocusScore?: boolean;
}

function allPlayRecord(
  cat: Category,
  baseline: StatTableRow,
  rows: StatTableRow[],
): { w: number; l: number; t: number } {
  let w = 0;
  let l = 0;
  let t = 0;
  for (const row of rows) {
    if (row.team === baseline.team) continue;
    const cmp = compareCell(baseline.stats[cat], row.stats[cat], cat);
    if (cmp === "better") w++;
    else if (cmp === "worse") l++;
    else t++;
  }
  return { w, l, t };
}

function formatValue(value: number | undefined, cat: Category, mode: StatDisplayMode): string {
  if (value === undefined) return "—";
  if (mode === "rating") return value.toFixed(1);
  if (cat === "FG%" || cat === "FT%") return value.toFixed(3);
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

// Team is always frozen on horizontal scroll; Score (only present when
// showFocusScore is on, i.e. Weekly Stats) freezes right after it. Fixed
// widths make the Score column's sticky `left` offset a reliable constant
// rather than depending on Team's variable text width.
const TEAM_COL_WIDTH = "w-24";
const SCORE_COL_LEFT = "left-24";

type SortKey = "team" | "score" | "rank" | "rating" | Category;
type SortDir = "desc" | "asc";
interface SortState {
  key: SortKey;
  dir: SortDir;
}

function SortableHead({
  sortKey,
  sort,
  onToggle,
  className,
  children,
}: {
  sortKey: SortKey;
  sort: SortState | null;
  onToggle: (key: SortKey) => void;
  className?: string;
  children: ReactNode;
}) {
  const active = sort?.key === sortKey;
  return (
    <TableHead className={className}>
      <button
        type="button"
        onClick={() => onToggle(sortKey)}
        className={cn(
          "inline-flex items-center gap-0.5 hover:text-foreground",
          active && "text-foreground",
        )}
      >
        {children}
        {active &&
          (sort!.dir === "desc" ? (
            <ArrowDown className="size-3" />
          ) : (
            <ArrowUp className="size-3" />
          ))}
      </button>
    </TableHead>
  );
}

export function StatTable({ rows, mode, focusTeam, showFocusScore }: StatTableProps) {
  const [sort, setSort] = useState<SortState | null>(null);
  const baseline = focusTeam ? rows.find((r) => r.team === focusTeam) : undefined;

  // Click a header: first click sorts largest-to-smallest (or A-Z for
  // Team), a second click on the same column flips to smallest-to-largest,
  // clicking a different column starts over at largest-to-smallest.
  function toggleSort(key: SortKey) {
    setSort((prev) => {
      if (prev?.key === key) return { key, dir: prev.dir === "desc" ? "asc" : "desc" };
      return { key, dir: "desc" };
    });
  }

  const sortedRows = useMemo(() => {
    if (!sort) return rows;
    const { key, dir } = sort;

    function sortValue(row: StatTableRow): number | string | undefined {
      if (key === "team") return row.team;
      if (key === "rank") return row.rank ?? undefined;
      if (key === "rating") return row.rating ?? undefined;
      if (key === "score") {
        if (!baseline || row.team === baseline.team) return undefined;
        const score = categoryScore(baseline.stats, row.stats);
        return score.wins - score.losses;
      }
      const source = mode === "stat" ? row.stats : row.ratings;
      return source[key];
    }

    return [...rows].sort((a, b) => {
      const av = sortValue(a);
      const bv = sortValue(b);
      if (av === undefined && bv === undefined) return 0;
      if (av === undefined) return 1;
      if (bv === undefined) return -1;
      if (typeof av === "string" || typeof bv === "string") {
        const cmp = String(av).localeCompare(String(bv));
        return dir === "asc" ? cmp : -cmp;
      }
      return dir === "asc" ? av - bv : bv - av;
    });
  }, [rows, sort, mode, baseline]);

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <SortableHead
            sortKey="team"
            sort={sort}
            onToggle={toggleSort}
            className={cn(TEAM_COL_WIDTH, "sticky left-0 z-10 bg-card")}
          >
            Team
          </SortableHead>
          {showFocusScore && (
            <SortableHead
              sortKey="score"
              sort={sort}
              onToggle={toggleSort}
              className={cn("text-right", "sticky z-10 bg-card", SCORE_COL_LEFT)}
            >
              Score
            </SortableHead>
          )}
          <SortableHead sortKey="rank" sort={sort} onToggle={toggleSort} className="text-right">
            Rank
          </SortableHead>
          {MAIN_CATS.map((cat) => (
            <SortableHead key={cat} sortKey={cat} sort={sort} onToggle={toggleSort} className="text-right">
              {cat}
            </SortableHead>
          ))}
          <SortableHead sortKey="rating" sort={sort} onToggle={toggleSort} className="text-right">
            Rating
          </SortableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sortedRows.map((row) => {
          const source = mode === "stat" ? row.stats : row.ratings;
          const baseSource = baseline ? (mode === "stat" ? baseline.stats : baseline.ratings) : undefined;
          const isFocus = row.team === focusTeam;
          return (
            <TableRow key={row.team} className={isFocus ? "bg-focus-row" : undefined}>
              <TableCell
                className={cn(
                  TEAM_COL_WIDTH,
                  "sticky left-0 z-10 bg-card font-sans font-extrabold tracking-wide uppercase",
                  // Same opaque --focus-row token as the row itself -- a
                  // sticky cell sits over horizontally scrolled content, so
                  // any transparency would let that content bleed through.
                  isFocus && "bg-focus-row text-primary",
                )}
              >
                {row.team}
              </TableCell>
              {showFocusScore && (
                <TableCell
                  className={cn(
                    "sticky z-10 bg-card text-right",
                    SCORE_COL_LEFT,
                    isFocus && "bg-focus-row",
                  )}
                >
                  {baseline && !isFocus ? (
                    (() => {
                      const score = categoryScore(baseline.stats, row.stats);
                      return (
                        <span
                          className={cn(
                            "inline-block rounded-sm px-2 py-0.5 font-bold",
                            scoreClass(score),
                          )}
                        >
                          {score.wins}-{score.losses}-{score.ties}
                        </span>
                      );
                    })()
                  ) : (
                    "—"
                  )}
                </TableCell>
              )}
              <TableCell className="text-right">
                <span className="inline-flex items-center justify-end gap-1">
                  {row.rank ?? "—"}
                  {row.rank != null &&
                    row.previousRank != null &&
                    row.previousRank !== row.rank &&
                    (row.rank < row.previousRank ? (
                      <ArrowUp className="size-3 text-win" />
                    ) : (
                      <ArrowDown className="size-3 text-loss" />
                    ))}
                </span>
              </TableCell>
              {MAIN_CATS.map((cat) => {
                const value = source[cat];
                const comparison =
                  baseSource && !isFocus ? compareCell(value, baseSource[cat], cat) : "neutral";
                // All-play record for this single week: the focus team's
                // raw stat in this category vs. every other row's raw stat
                // (always computed from `stats`, not `ratings` -- ratings
                // are already direction-normalized, so re-running
                // compareCell's NEG_CATS inversion on them would double-
                // invert TO).
                const record =
                  showFocusScore && isFocus && baseline
                    ? allPlayRecord(cat, baseline, rows)
                    : undefined;
                return (
                  <TableCell
                    key={cat}
                    className={cn("text-right font-semibold", comparisonClass[comparison])}
                  >
                    {formatValue(value, cat, mode)}
                    {record && (
                      <span className="ml-1 font-mono text-xs text-muted-foreground">
                        ({record.w}-{record.l}
                        {record.t > 0 ? `-${record.t}` : ""})
                      </span>
                    )}
                  </TableCell>
                );
              })}
              <TableCell className="text-right font-extrabold text-primary">
                {row.rating ?? "—"}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
