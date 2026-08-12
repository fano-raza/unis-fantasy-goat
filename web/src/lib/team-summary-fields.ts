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
  "Worst Ratings": "lower",
  "Worst Rating Years": "skip",
  "RS 1st Place": "higher",
  "RS 1st Years": "skip",
  "RS Last Place": "lower",
  "RS Last Years": "skip",
  "Best RS Rating": "higher",
  "Best RS Rating Years": "skip",
  "Best RS Finish": "lower",
  "Best RS Finish Years": "skip",
  "Matchup Wins": "higher",
  "Category Wins": "higher",
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
  "Best Win Streak Years": "skip",
  "Worst Losing Streak": "lower",
  "Worst Losing Streak Years": "skip",
  "Best Undefeated Streak": "higher",
  "Best Undefeated Streak Years": "skip",
  "Longest 1st Place Streak": "higher",
  "Longest 1st Place Streak Years": "skip",
  "Longest Last Streak": "lower",
  "Longest Last Streak Years": "skip",
  "Longest #1 Rating Streak": "higher",
  "Longest #1 Rating Streak Years": "skip",
  "Longest Last Rating Streak": "lower",
  "Longest Last Rating Streak Years": "skip",
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

// Comparison-page only: "Best/Worst Week Rating" are single-week flukes, not
// meaningful comparison stats (separate from TOP3_EXCLUDED even though both
// happen to exclude the same two fields today, for a different reason).
// "Avg Weighted Rank" is excluded because it's effectively the same signal
// as "Avg Rating (out of 100)"/"Avg Rank", already shown -- kept in the CSV
// export itself in case some other consumer wants it later.
export const COMPARISON_EXCLUDED_FIELDS = new Set([
  "Best Week Rating",
  "Worst Week Rating",
  "Avg Weighted Rank",
]);

// Comparison table: fields with a companion "X Years"/"X Season" column
// render as one row ("value (years)") instead of two -- see
// formatValueWithYears below. Every base field that has a year/season
// companion in the team_summary export must be listed here.
export const PAIRED_YEARS_FIELD: Record<string, string> = {
  Championships: "Championship Years",
  Finals: "Finals Years",
  Playoffs: "Playoff Years",
  MVPs: "MVP Years",
  "Worst Ratings": "Worst Rating Years",
  "RS 1st Place": "RS 1st Years",
  "RS Last Place": "RS Last Years",
  "Best RS Rating": "Best RS Rating Years",
  "Best RS Finish": "Best RS Finish Years",
  "Best Draft Score": "Best Draft Season",
  "Worst Draft Score": "Worst Draft Season",
  "Best Win Streak": "Best Win Streak Years",
  "Worst Losing Streak": "Worst Losing Streak Years",
  "Best Undefeated Streak": "Best Undefeated Streak Years",
  "Longest 1st Place Streak": "Longest 1st Place Streak Years",
  "Longest Last Streak": "Longest Last Streak Years",
  "Longest #1 Rating Streak": "Longest #1 Rating Streak Years",
  "Longest Last Rating Streak": "Longest Last Rating Streak Years",
};

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

// Comparison table's row value: the base field's value, with its paired
// years/season column appended in parentheses when that field has one and
// it's non-empty (e.g. "3 (2019, 2021, 2023)" for Championships). Falls
// back to the plain value for fields with no pairing, or when the years
// value itself is empty (e.g. a streak of 0 has no year to show). Most
// pairings are comma-joined year-list strings, but "Best/Worst Draft
// Season" are single numbers (a team can only have one best-ever draft
// season, unlike the tie-able Years lists) -- accept either.
export function formatValueWithYears(row: TeamSummary, field: string): string {
  const base = formatValue(row[field]);
  const yearsField = PAIRED_YEARS_FIELD[field];
  if (!yearsField) return base;
  const years = row[yearsField];
  if (years === null || years === undefined) return base;
  if (typeof years === "string" && !years.trim()) return base;
  return `${base} (${years})`;
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
