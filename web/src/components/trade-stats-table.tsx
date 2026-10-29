"use client";

import { useState } from "react";
import { formatNumber } from "@/lib/format-number";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { MAIN_CATS, type Category, type PlayerStat, type StatWindow } from "@/lib/api";
import { compareCell, type Comparison } from "@/lib/highlight";
import { cn } from "@/lib/utils";

// The Trade Hub's side-by-side stat comparison of what each side sends
// (moved out of trade-hub.tsx unchanged, 2026-10-28, when the page gained
// team rosters and the premium win-chance panel).

const WINDOW_OPTIONS: { value: StatWindow; label: string }[] = [
  { value: "season", label: "Season" },
  { value: "d7", label: "7d" },
  { value: "d14", label: "14d" },
  { value: "d30", label: "30d" },
  { value: "d90", label: "90d" },
];

// Builds the {window}_{cat}_{total|avg} (or {window}_{cat} for FG%/FT%,
// which have no total/avg split -- see export_player_stats.py) key into a
// PlayerStat row. Returns null when that player has no games in the
// selected window (real during the NBA off-season, not a bug -- see the
// plan doc).
function getPlayerCatValue(player: PlayerStat, statWindow: StatWindow, cat: Category, mode: "totals" | "averages"): number | null {
  const key = cat === "FG%" || cat === "FT%" ? `${statWindow}_${cat}` : `${statWindow}_${cat}_${mode === "totals" ? "total" : "avg"}`;
  const value = player[key];
  return typeof value === "number" ? value : null;
}

// Aggregates a group of up to 5 players for one stat category -- what a
// side gives up, so always the players ADDED together: their totals over
// the window (Totals) or their per-game averages summed (Averages).
// FG%/FT% use the real weighted ratio (the group's makes / attempts) rather
// than a naive average of each player's percentage, which would misweight
// players with very different attempt volumes -- same reasoning as
// StatTable's Score column elsewhere in this app.
function aggregate(players: PlayerStat[], statWindow: StatWindow, mode: "totals" | "averages"): Record<Category, number | null> {
  const result = {} as Record<Category, number | null>;
  for (const cat of MAIN_CATS) {
    if (cat === "FG%" || cat === "FT%") {
      // Weighted by volume: the group's makes / attempts, summed per game in
      // Averages mode and over the window in Totals mode.
      const group = madeAttemptedValue(players, statWindow, cat, mode);
      result[cat] = group && group.att > 0 ? group.made / group.att : null;
      continue;
    }
    const values = players.map((p) => getPlayerCatValue(p, statWindow, cat, mode)).filter((v): v is number => v !== null);
    if (values.length === 0) {
      result[cat] = null;
      continue;
    }
    // Both modes ADD the players up (user correction, 2026-10-28): a side
    // that sends two players gives up both players' production, so in
    // Averages mode the side's line is the sum of their per-game averages
    // (it used to be their mean, which made a 2-player side look like one
    // average player).
    result[cat] = values.reduce((a, b) => a + b, 0);
  }
  return result;
}

function formatStat(cat: Category, value: number | null): string {
  if (value === null) return "—";
  if (cat === "FG%" || cat === "FT%") return value.toFixed(3);
  return formatNumber(value, 1);
}

// Direct (not inverted) coloring: `comparison` is Team A's own value
// relative to Team B, so Team A being "better" should read green here.
// `highlight.ts`'s `comparisonClass` is deliberately inverted for
// StatTable's different use case (a row colored relative to a separate
// focus-team baseline, not the row's own comparison) -- reusing it here
// was backwards, per the user's report. Applied directly to the Team A/
// Team B value cells (there's no separate Net column anymore).
const highlightClass: Record<Comparison, string> = {
  better: "bg-win/15 text-win",
  worse: "bg-loss/15 text-loss",
  neutral: "",
};

// Team B's cell colors from Team A's flipped perspective -- Team A "better"
// means Team B is "worse" in the same category, and vice versa.
function flip(comparison: Comparison): Comparison {
  if (comparison === "better") return "worse";
  if (comparison === "worse") return "better";
  return "neutral";
}

function formatSignedStat(cat: Category, value: number | null): string {
  if (value === null) return "—";
  const formatted = formatStat(cat, value);
  return value >= 0 ? `+${formatted}` : formatted;
}

// FGM/FGA and FTM/FTA -- informational volume rows (made/attempted for the
// group). Rendered directly after their matching percentage row (FG% / FT%),
// not grouped separately. They do get a Net value (the made/attempted diff,
// same "X/Y" shape as the value cells), just never colored red/green --
// a made/attempted pair isn't a single win/loss comparison the way a plain
// stat total is, so there's no "better" direction to highlight.
const MADE_ATTEMPTED_BY_CAT: Partial<Record<Category, { label: string }>> = {
  "FG%": { label: "FGM/FGA" },
  "FT%": { label: "FTM/FTA" },
};

interface MadeAttempted {
  made: number;
  att: number;
}

// Totals: real summed made/attempted across the group. Averages: each
// player's own per-game made/attempted, summed across the group -- the
// same "add the players up" rule as the counting categories (aggregate()
// above).
function madeAttemptedValue(
  players: PlayerStat[],
  statWindow: StatWindow,
  cat: "FG%" | "FT%",
  mode: "totals" | "averages",
): MadeAttempted | null {
  if (mode === "totals") {
    let made = 0;
    let att = 0;
    let any = false;
    for (const p of players) {
      const m = p[`${statWindow}_${cat}_made`];
      const a = p[`${statWindow}_${cat}_att`];
      if (typeof m === "number" && typeof a === "number") {
        made += m;
        att += a;
        any = true;
      }
    }
    return any ? { made, att } : null;
  }

  const madeRates: number[] = [];
  const attRates: number[] = [];
  for (const p of players) {
    const m = p[`${statWindow}_${cat}_made`];
    const a = p[`${statWindow}_${cat}_att`];
    const gp = p[`${statWindow}_GP`];
    if (typeof m === "number" && typeof a === "number" && typeof gp === "number" && gp > 0) {
      madeRates.push(m / gp);
      attRates.push(a / gp);
    }
  }
  if (madeRates.length === 0) return null;
  // Summed per-game rates (see aggregate() above).
  return {
    made: madeRates.reduce((sum, v) => sum + v, 0),
    att: attRates.reduce((sum, v) => sum + v, 0),
  };
}

function formatMadeAttempted(value: MadeAttempted | null, mode: "totals" | "averages"): string {
  if (!value) return "—";
  const fmt = (n: number) => (mode === "totals" ? String(n) : n.toFixed(1));
  return `${fmt(value.made)}/${fmt(value.att)}`;
}

function formatMadeAttemptedNet(a: MadeAttempted | null, b: MadeAttempted | null, mode: "totals" | "averages"): string {
  if (!a || !b) return "—";
  const fmt = (n: number) => {
    const s = mode === "totals" ? String(n) : n.toFixed(1);
    return n >= 0 ? `+${s}` : s;
  };
  return `${fmt(a.made - b.made)}/${fmt(a.att - b.att)}`;
}


export function TradeStatsComparison({
  playersA,
  playersB,
  labelA,
  labelB,
}: {
  playersA: PlayerStat[];
  playersB: PlayerStat[];
  labelA: string;
  labelB: string;
}) {
  // Defaults to "season" -- during the NBA off-season the rolling windows
  // have no data at all (verified against the real export), so a rolling
  // statWindow default would open on an empty table.
  const [statWindow, setWindow] = useState<StatWindow>("season");
  const [mode, setMode] = useState<"totals" | "averages">("averages");
  const [view, setView] = useState<"stats" | "net">("stats");
  const aggA = aggregate(playersA, statWindow, mode);
  const aggB = aggregate(playersB, statWindow, mode);

  return (
    <Card>
      <CardHeader className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
        <CardTitle>Stat comparison</CardTitle>
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <div className="flex items-center gap-1.5 label text-foreground">
            <span className="mr-0.5 text-muted-foreground">Window</span>
            {WINDOW_OPTIONS.map((opt) => (
              <Button
                key={opt.value}
                variant={statWindow === opt.value ? "default" : "outline"}
                size="sm"
                onClick={() => setWindow(opt.value)}
              >
                {opt.label}
              </Button>
            ))}
          </div>
          <label className="flex items-center gap-2 label text-foreground">
            <span className="text-muted-foreground">Totals</span>
            <Switch checked={mode === "averages"} onCheckedChange={(c) => setMode(c ? "averages" : "totals")} />
            <span className="text-muted-foreground">Averages</span>
          </label>
          <label className="flex items-center gap-2 label text-foreground">
            <span className="text-muted-foreground">Stats</span>
            <Switch checked={view === "net"} onCheckedChange={(c) => setView(c ? "net" : "stats")} />
            <span className="text-muted-foreground">Net</span>
          </label>
        </div>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Category</TableHead>
              <TableHead className="text-right">{labelA}</TableHead>
              <TableHead className="text-right">{labelB}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {MAIN_CATS.flatMap((cat) => {
              const a = aggA[cat];
              const b = aggB[cat];
              const comparison = a !== null && b !== null ? compareCell(a, b, cat) : "neutral";
              const valueA = view === "stats" ? formatStat(cat, a) : formatSignedStat(cat, a !== null && b !== null ? a - b : null);
              const valueB = view === "stats" ? formatStat(cat, b) : formatSignedStat(cat, a !== null && b !== null ? b - a : null);
              const rows = [
                <TableRow key={cat}>
                  <TableCell className="font-sans font-medium text-muted-foreground">{cat}</TableCell>
                  <TableCell className={cn("text-right font-mono font-extrabold tabular-nums", highlightClass[comparison])}>
                    {valueA}
                  </TableCell>
                  <TableCell className={cn("text-right font-mono font-extrabold tabular-nums", highlightClass[flip(comparison)])}>
                    {valueB}
                  </TableCell>
                </TableRow>,
              ];
              // FGM/FGA directly after FG%, FTM/FTA directly after FT%
              // -- not grouped separately at the end.
              const madeAttRow = MADE_ATTEMPTED_BY_CAT[cat];
              if (madeAttRow) {
                const maCat = cat as "FG%" | "FT%";
                const aVal = madeAttemptedValue(playersA, statWindow, maCat, mode);
                const bVal = madeAttemptedValue(playersB, statWindow, maCat, mode);
                rows.push(
                  <TableRow key={madeAttRow.label}>
                    <TableCell className="font-sans font-medium text-muted-foreground">{madeAttRow.label}</TableCell>
                    {/* No red/green here (unlike the other rows) -- a
                        made/attempted pair has no single "better"
                        direction to highlight. */}
                    <TableCell className="text-right font-mono tabular-nums">
                      {view === "stats" ? formatMadeAttempted(aVal, mode) : formatMadeAttemptedNet(aVal, bVal, mode)}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {view === "stats" ? formatMadeAttempted(bVal, mode) : formatMadeAttemptedNet(bVal, aVal, mode)}
                    </TableCell>
                  </TableRow>,
                );
              }
              return rows;
            })}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
