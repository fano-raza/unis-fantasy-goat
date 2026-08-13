import { MAIN_CATS, type Category, type CategoryStats } from "./api";

// Mirrors dashboard_site/api/league_store.py's NEG_CATS -- TO is the only
// category where a lower value is better.
export const NEG_CATS: readonly Category[] = ["TO"];

export type Comparison = "better" | "worse" | "neutral";

// Highlight semantics, colored from the focus team's perspective and shown
// on the OTHER row: this row's cell is RED if the focus team is worse off
// than this row in that category (this row "beat" focus), GREEN if the
// focus team is better (this row "lost" to focus). `Comparison` names stay
// row-centric ("better"/"worse" = how this row's own value compares to the
// baseline) -- comparisonClass below is what actually inverts the color.
export function compareCell(
  value: number | undefined,
  baseline: number | undefined,
  category: Category,
  options?: {
    // Ratings are already direction-normalized -- a higher rating always
    // means "did better" in that category, even TO (a NEG_CATS member),
    // since the rating conversion itself already accounts for lower-TO-is-
    // better. The lower-is-better inversion below only makes sense for raw
    // stat totals/averages; re-applying it to rating values double-inverts
    // TO (was showing red on the higher, better rating). Defaults to false
    // (existing NEG_CATS-inversion behavior, unchanged) so every raw-stat
    // call site is unaffected.
    ratingMode?: boolean;
  },
): Comparison {
  if (value === undefined || baseline === undefined) return "neutral";
  if (value === baseline) return "neutral";
  const higherIsBetter = options?.ratingMode ? true : !NEG_CATS.includes(category);
  const isHigher = value > baseline;
  const better = higherIsBetter ? isHigher : !isHigher;
  return better ? "better" : "worse";
}

export const comparisonClass: Record<Comparison, string> = {
  better: "bg-loss/15 text-loss",
  worse: "bg-win/15 text-win",
  neutral: "",
};

export interface CategoryScore {
  wins: number;
  losses: number;
  ties: number;
}

// All-play category W-L-T for `stats` against `baseline` (Weekly Stats'
// "Score" column calls this with the focus team as `stats` and each other
// row as `baseline`, so wins/losses read as the focus team's own record
// against that opponent) -- reuses compareCell's per-category direction
// logic rather than re-deriving NEG_CATS a second time.
export function categoryScore(stats: CategoryStats, baseline: CategoryStats): CategoryScore {
  const score: CategoryScore = { wins: 0, losses: 0, ties: 0 };
  for (const cat of MAIN_CATS) {
    const comparison = compareCell(stats[cat], baseline[cat], cat);
    if (comparison === "better") score.wins += 1;
    else if (comparison === "worse") score.losses += 1;
    else score.ties += 1;
  }
  return score;
}

export const scoreClass = (score: CategoryScore): string => {
  if (score.wins > score.losses) return "bg-win/15 text-win";
  if (score.losses > score.wins) return "bg-loss/15 text-loss";
  return "";
};
