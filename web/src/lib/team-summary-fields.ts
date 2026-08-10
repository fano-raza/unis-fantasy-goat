import type { TeamSummary } from "./api";

// Direction map for scripts/export_team_summary.py's columns -- which fields
// are meaningfully "higher is better" / "lower is better" for the Comparison
// page's best/worst highlighting, and which aren't comparable at all (year
// lists, W-L-T strings, a season number) so are left unhighlighted.
export type Direction = "higher" | "lower" | "skip";

const FIELD_DIRECTIONS: Record<string, Direction> = {
  Championships: "higher",
  "Championship Years": "skip",
  Finals: "higher",
  "Finals Years": "skip",
  Playoffs: "higher",
  "Playoff Years": "skip",
  MVPs: "higher",
  "MVP Years": "skip",
  "RS 1st Place": "higher",
  "RS 1st Years": "skip",
  "Best RS Rating": "higher",
  "Best RS Rating Years": "skip",
  "Best RS Finish": "lower",
  "Best RS Finish Years": "skip",
  "Career W/L": "skip",
  "Career W/L %": "higher",
  "Career Matchups": "skip",
  "RS W/L": "skip",
  "RS W/L %": "higher",
  "PO W/L": "skip",
  "PO W/L %": "higher",
  "Career Cats": "skip",
  "Career Cats %": "higher",
  "Career Cat Games": "skip",
  "RS Cats": "skip",
  "RS Cats %": "higher",
  "PO Cats": "skip",
  "PO Cats %": "higher",
  "Best Win Streak": "higher",
  "Worst Losing Streak": "lower",
  "Best Undefeated Streak": "higher",
  "Avg Rating (out of 100)": "higher",
  "Avg Rank": "lower",
  "Avg Weighted Rank": "lower",
  "Best Week Rating": "higher",
  "Worst Week Rating": "higher",
  "#1 Rating Weeks": "higher",
  "Lowest Rating Weeks": "lower",
  "Avg Opp Rating (out of 100)": "skip",
  "Opponent Rating Ratio": "higher",
  "Career Draft Score": "higher",
  "Avg Draft Score": "higher",
  "Best Draft Score": "higher",
  "Best Draft Season": "skip",
  "Worst Draft Score": "higher",
  "Worst Draft Season": "skip",
};

export function directionFor(field: string): Direction {
  return FIELD_DIRECTIONS[field] ?? "skip";
}

// Comparison-page styling: fields called out as "always worth noticing"
// (bold + slightly larger) vs. auxiliary year/season lists that sit next to
// a count/value stat and should recede (muted/more transparent).
export const EMPHASIZED_FIELDS = new Set([
  "Championships",
  "MVPs",
  "RS 1st Place",
  "Career W/L %",
  "Career Cats %",
  "Best Win Streak",
  "Avg Rating (out of 100)",
  "Avg Opp Rating (out of 100)",
  "Career Draft Score",
  "Best Draft Score",
]);

// Comparison-page only: a single-week fluke isn't a meaningful comparison
// stat. Separate from TOP3_EXCLUDED (Profile-only), even though both
// happen to exclude the same two fields today, for a different reason.
export const COMPARISON_EXCLUDED_FIELDS = new Set(["Best Week Rating", "Worst Week Rating"]);

export const DEEMPHASIZED_FIELDS = new Set([
  "Championship Years",
  "Finals Years",
  "Playoff Years",
  "MVP Years",
  "RS 1st Years",
  "Best RS Rating Years",
  "Best RS Finish Years",
  "Best Draft Season",
  "Worst Draft Season",
]);

// Every non-"Team" key on the exported team_summary rows, in export order.
export function comparableFields(rows: TeamSummary[]): string[] {
  return rows.length ? Object.keys(rows[0]).filter((k) => k !== "Team") : [];
}

// Standard competition ranking (ties share a rank, e.g. 1,1,3) among teams
// with a numeric value for this field. Undefined for non-comparable fields
// or teams missing data for it.
export function rankFor(field: string, rows: TeamSummary[], team: string): number | undefined {
  const direction = directionFor(field);
  if (direction === "skip") return undefined;

  const numeric = rows
    .map((r) => ({ team: r.Team, value: r[field] }))
    .filter((r): r is { team: string; value: number } => typeof r.value === "number");
  const target = numeric.find((r) => r.team === team);
  if (!target) return undefined;

  const better =
    direction === "higher"
      ? numeric.filter((r) => r.value > target.value).length
      : numeric.filter((r) => r.value < target.value).length;
  return better + 1;
}

export function formatValue(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(3);
  }
  return String(value);
}

export function ordinal(n: number): string {
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 13) return `${n}th`;
  switch (n % 10) {
    case 1:
      return `${n}st`;
    case 2:
      return `${n}nd`;
    case 3:
      return `${n}rd`;
    default:
      return `${n}th`;
  }
}
