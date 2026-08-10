"use client";

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

export interface StatTableRow {
  team: string;
  stats: CategoryStats;
  ratings: CategoryStats;
  rating: number | null;
  rank: number | null;
}

export type StatDisplayMode = "stat" | "rating";

interface StatTableProps {
  rows: StatTableRow[];
  mode: StatDisplayMode;
  focusTeam?: string;
  // Weekly Stats only -- an extra column giving each row's all-play
  // category W-L-T against focusTeam's raw stats. Off by default so
  // Career Stats/Profile's StatTable usages are unaffected.
  showFocusScore?: boolean;
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

export function StatTable({ rows, mode, focusTeam, showFocusScore }: StatTableProps) {
  const baseline = focusTeam ? rows.find((r) => r.team === focusTeam) : undefined;

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className={cn(TEAM_COL_WIDTH, "sticky left-0 z-10 bg-card")}>Team</TableHead>
          {showFocusScore && (
            <TableHead className={cn("text-right", "sticky z-10 bg-card", SCORE_COL_LEFT)}>
              Score
            </TableHead>
          )}
          <TableHead className="text-right">Rank</TableHead>
          {MAIN_CATS.map((cat) => (
            <TableHead key={cat} className="text-right">
              {cat}
            </TableHead>
          ))}
          <TableHead className="text-right">Rating</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => {
          const source = mode === "stat" ? row.stats : row.ratings;
          const baseSource = baseline ? (mode === "stat" ? baseline.stats : baseline.ratings) : undefined;
          const isFocus = row.team === focusTeam;
          return (
            <TableRow key={row.team} className={isFocus ? "bg-muted/50" : undefined}>
              <TableCell
                className={cn(
                  TEAM_COL_WIDTH,
                  "sticky left-0 z-10 bg-card font-sans font-extrabold tracking-wide uppercase",
                  // Opaque bg-muted, not the row's semi-transparent
                  // bg-muted/50 -- a sticky cell sits over horizontally
                  // scrolled content, so any transparency lets that
                  // content bleed through underneath it.
                  isFocus && "bg-muted text-primary",
                )}
              >
                {row.team}
              </TableCell>
              {showFocusScore && (
                <TableCell
                  className={cn(
                    "sticky z-10 bg-card text-right",
                    SCORE_COL_LEFT,
                    isFocus && "bg-muted",
                  )}
                >
                  {baseline && !isFocus ? (
                    (() => {
                      const score = categoryScore(row.stats, baseline.stats);
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
              <TableCell className="text-right">{row.rank ?? "—"}</TableCell>
              {MAIN_CATS.map((cat) => {
                const value = source[cat];
                const comparison =
                  baseSource && !isFocus ? compareCell(value, baseSource[cat], cat) : "neutral";
                return (
                  <TableCell
                    key={cat}
                    className={cn("text-right font-semibold", comparisonClass[comparison])}
                  >
                    {formatValue(value, cat, mode)}
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
