"use client";

import { useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";
import Link from "next/link";
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
  // Ultra page only -- keeps the focus team's row pinned at index 0
  // regardless of the active column sort. Off by default so every other
  // page's StatTable usage (which sorts the focus row like any other row)
  // is unaffected.
  pinFocusRow?: boolean;
  // Ultra page only -- when set (a pixel offset, typically the height of
  // the page's own sticky filter bar, measured via useElementHeight rather
  // than hardcoded -- see that hook's comment for why), the header row
  // becomes sticky at that offset so it stays visible while scrolling the
  // table body vertically. Undefined disables it, unaffected elsewhere.
  stickyHeaderOffset?: number;
  // Ultra page only -- adds a yellow ring around a non-focus row's category
  // cell when its value is within 10% of the focus team's value in that
  // same category, on top of (not instead of) the existing green/red
  // comparison background. Off by default, unaffected elsewhere.
  highlightClose?: boolean;
}

// Within 10% of the focus team's own value in that category, relative to
// the focus team's value -- 0 is treated as "not close" to anything but 0
// itself, so a real 0 baseline doesn't divide-by-zero into a false match.
function isCloseValue(value: number | undefined, baseline: number | undefined): boolean {
  if (value === undefined || baseline === undefined) return false;
  if (baseline === 0) return value === 0;
  return Math.abs(value - baseline) <= 0.1 * Math.abs(baseline);
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
// showFocusScore is on, i.e. Weekly Stats) freezes right after it.
// `w-24` on the Team cell is only a hint, not authoritative: this table
// uses table-layout: auto (needed so the 9 category columns can size to
// their own content), and under auto layout the browser's own column-
// sizing algorithm can render a `width`-styled <td> narrower than its
// specified width (measured ~81px in practice, not 96px). A hardcoded
// `left-24` on Score assumed exactly 96px, leaving a gap that let
// horizontally-scrolled content show through between the two sticky
// columns on narrow viewports. Fixed below by measuring Team's actual
// rendered width and positioning Score there instead of assuming a
// constant.
const TEAM_COL_WIDTH = "w-24";

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
  style,
  children,
}: {
  sortKey: SortKey;
  sort: SortState | null;
  onToggle: (key: SortKey) => void;
  className?: string;
  style?: CSSProperties;
  children: ReactNode;
}) {
  const active = sort?.key === sortKey;
  return (
    <TableHead className={className} style={style}>
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

export function StatTable({
  rows,
  mode,
  focusTeam,
  showFocusScore,
  pinFocusRow,
  stickyHeaderOffset,
  highlightClose,
}: StatTableProps) {
  const headerSticky = stickyHeaderOffset !== undefined;
  const headerStickyClass = headerSticky ? "sticky z-20 bg-card" : undefined;
  const headerStickyStyle: CSSProperties | undefined = headerSticky ? { top: stickyHeaderOffset } : undefined;
  const [sort, setSort] = useState<SortState | null>(null);
  const baseline = focusTeam ? rows.find((r) => r.team === focusTeam) : undefined;

  // Measures the first row's actual rendered Team-cell width and positions
  // the sticky Score column there -- see the TEAM_COL_WIDTH comment above
  // for why a hardcoded offset isn't reliable here.
  const firstTeamCellRef = useRef<HTMLTableCellElement | null>(null);
  const [scoreLeft, setScoreLeft] = useState<number>(96);
  useEffect(() => {
    const el = firstTeamCellRef.current;
    if (!el || !showFocusScore) return;
    const update = () => setScoreLeft(el.getBoundingClientRect().width);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, [showFocusScore, rows]);

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

  // Ultra's pinned focus row: pulled to index 0 after the normal sort runs,
  // rather than baked into sortValue -- keeps the sort itself (and every
  // other page's unpinned usage) exactly as before.
  const displayRows = useMemo(() => {
    if (!pinFocusRow || !focusTeam) return sortedRows;
    const idx = sortedRows.findIndex((r) => r.team === focusTeam);
    if (idx <= 0) return sortedRows;
    const copy = [...sortedRows];
    const [pinned] = copy.splice(idx, 1);
    copy.unshift(pinned);
    return copy;
  }, [sortedRows, pinFocusRow, focusTeam]);

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <SortableHead
            sortKey="team"
            sort={sort}
            onToggle={toggleSort}
            className={cn(TEAM_COL_WIDTH, "sticky left-0 bg-card", headerSticky ? "z-30" : "z-10")}
            style={headerStickyStyle}
          >
            Team
          </SortableHead>
          {showFocusScore && (
            <SortableHead
              sortKey="score"
              sort={sort}
              onToggle={toggleSort}
              className={cn("text-right sticky bg-card", headerSticky ? "z-30" : "z-10")}
              style={{ left: scoreLeft, ...headerStickyStyle }}
            >
              Score
            </SortableHead>
          )}
          <SortableHead sortKey="rank" sort={sort} onToggle={toggleSort} className={headerStickyClass} style={headerStickyStyle}>
            Rank
          </SortableHead>
          {MAIN_CATS.map((cat) => (
            <SortableHead
              key={cat}
              sortKey={cat}
              sort={sort}
              onToggle={toggleSort}
              className={cn("text-right", headerStickyClass)}
              style={headerStickyStyle}
            >
              {cat}
            </SortableHead>
          ))}
          <SortableHead
            sortKey="rating"
            sort={sort}
            onToggle={toggleSort}
            className={cn("text-right", headerStickyClass)}
            style={headerStickyStyle}
          >
            Rating
          </SortableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {displayRows.map((row, i) => {
          const source = mode === "stat" ? row.stats : row.ratings;
          const baseSource = baseline ? (mode === "stat" ? baseline.stats : baseline.ratings) : undefined;
          const isFocus = row.team === focusTeam;
          return (
            <TableRow key={row.team} className={isFocus ? "bg-focus-row" : undefined}>
              <TableCell
                ref={i === 0 ? firstTeamCellRef : undefined}
                className={cn(
                  TEAM_COL_WIDTH,
                  "sticky left-0 z-10 bg-card font-sans font-extrabold tracking-wide uppercase",
                  // Same opaque --focus-row token as the row itself -- a
                  // sticky cell sits over horizontally scrolled content, so
                  // any transparency would let that content bleed through.
                  isFocus && "bg-focus-row text-primary",
                )}
              >
                <Link href={`/profile?team=${encodeURIComponent(row.team)}`} className="hover:underline">
                  {row.team}
                </Link>
              </TableCell>
              {showFocusScore && (
                <TableCell
                  className={cn("sticky z-10 bg-card text-right", isFocus && "bg-focus-row")}
                  style={{ left: scoreLeft }}
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
              <TableCell>
                <span className="inline-flex items-center justify-start gap-1">
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
                const close =
                  highlightClose && baseSource && !isFocus && isCloseValue(value, baseSource[cat]);
                return (
                  <TableCell
                    key={cat}
                    className={cn(
                      "text-right font-semibold",
                      comparisonClass[comparison],
                      close && "ring-1 ring-inset ring-yellow-400",
                    )}
                  >
                    {record ? (
                      <span className="flex flex-col items-end leading-tight">
                        <span>{formatValue(value, cat, mode)}</span>
                        <span className="font-mono text-[10px] text-muted-foreground">
                          ({record.w}-{record.l}
                          {record.t > 0 ? `-${record.t}` : ""})
                        </span>
                      </span>
                    ) : (
                      formatValue(value, cat, mode)
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
