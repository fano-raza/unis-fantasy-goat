"use client";

import { ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";

// How a season's standings are decided (LeagueMeta.season_format): weekly
// matchups won ("wl") or total categories won ("cats").
export type SeasonFormat = "wl" | "cats";

const pct = (x: number) => `${Math.round(x * 100)}%`;

/**
 * Expected categories won in a typical week: the sum of the per-category
 * win probabilities, plus 0.5 for turnovers (the premium tools treat TO as
 * a coin flip and leave it out of the per-category numbers).
 */
export function expectedCategories(perCategory: Record<string, number>): number {
  return Object.values(perCategory).reduce((sum, p) => sum + p, 0) + 0.5;
}

/**
 * The big number on the premium win-probability panels, in the season's
 * own terms (user decision, 2026-10-28): W/L seasons -> weekly matchup win
 * probability; Cats seasons -> expected categories won per week (of 9).
 * `after` omitted -> just the current value.
 */
export function HeadlineOdds({
  format,
  startWin,
  startCats,
  after,
  extra,
}: {
  format: SeasonFormat;
  startWin: number;
  startCats: Record<string, number>;
  after?: { win: number; cats: Record<string, number> };
  // Small text after the number (e.g. "with 2 swaps").
  extra?: string;
}) {
  const cats = format === "cats";
  const before = cats ? expectedCategories(startCats) : startWin;
  const end = after ? (cats ? expectedCategories(after.cats) : after.win) : null;
  const fmt = (x: number) => (cats ? x.toFixed(1) : pct(x));
  // Same "visible change" bar as the rounded display.
  const delta = end === null ? 0 : end - before;
  const tiny = cats ? 0.05 : 0.005;
  return (
    <div className="flex flex-col gap-1">
      <span className="label">{cats ? "Expected categories won per week" : "Weekly matchup win probability"}</span>
      <span className="font-display text-3xl leading-none font-bold tabular-nums [font-variation-settings:'opsz'_36]">
        {fmt(before)}
        {end !== null && (
          <>
            <ArrowRight className="mx-1.5 inline size-5 align-[-2px] text-muted-foreground" aria-label="to" />
            <span className={cn(delta > tiny ? "text-win" : delta < -tiny ? "text-loss" : "text-foreground")}>{fmt(end)}</span>
          </>
        )}
        {cats && <span className="ml-1.5 font-sans text-sm font-normal text-muted-foreground">of 9</span>}
        {extra && <span className="ml-2 font-sans text-sm font-normal text-muted-foreground">{extra}</span>}
      </span>
    </div>
  );
}
