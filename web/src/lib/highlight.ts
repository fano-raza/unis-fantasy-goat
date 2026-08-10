import { MAIN_CATS, type Category, type CategoryStats } from "./api";

// Mirrors dashboard_site/api/league_store.py's NEG_CATS -- TO is the only
// category where a lower value is better.
export const NEG_CATS: readonly Category[] = ["TO"];

export type Comparison = "better" | "worse" | "neutral";

// Weekly Stats highlight semantics (per the user's spec, the mirror image of
// DashApp's red/green): green if THIS row's value is better than the
// highlighted team's value, yellow if worse, neutral on a tie or no baseline.
export function compareCell(
  value: number | undefined,
  baseline: number | undefined,
  category: Category,
): Comparison {
  if (value === undefined || baseline === undefined) return "neutral";
  if (value === baseline) return "neutral";
  const higherIsBetter = !NEG_CATS.includes(category);
  const isHigher = value > baseline;
  const better = higherIsBetter ? isHigher : !isHigher;
  return better ? "better" : "worse";
}

export const comparisonClass: Record<Comparison, string> = {
  better: "bg-win/15 text-win",
  worse: "bg-loss/15 text-loss",
  neutral: "",
};

export interface CategoryScore {
  wins: number;
  losses: number;
  ties: number;
}

// All-play category W-L-T for one row's raw stats against a baseline row's
// (Weekly Stats' "Score vs focus team" column) -- reuses compareCell's
// per-category direction logic rather than re-deriving NEG_CATS a second
// time.
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
