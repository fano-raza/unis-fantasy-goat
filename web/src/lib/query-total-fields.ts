// /query-backed win/loss totals for Team Profile's League Top 3 and the
// Team Comparison table. Kept in a plain (non-"use client") module on
// purpose: the server pages (app/team/profile, app/team/comparison) map
// over these to prefetch their bootstrap, and a value imported from a
// "use client" file is only a client reference on the server -- calling
// .map on it threw, silently nulling both pages' server bootstrap so every
// visit refetched everything in the browser (found 2026-10-25).

// Win/loss career totals for the "League Top 3" table -- not present in
// team_summary.csv (that has W-L-T strings, not individually rankable
// counts), so pulled from the generic /query endpoint instead of a new
// export. "Total"/"Total Category" scope both RS+PO; the rest split by
// season. Losses rank "lower is better" (fewest losses = rank 1), the same
// convention this app already uses for "Worst Losing Streak"/"Lowest
// Rating Weeks" in web/src/lib/team-summary-fields.ts.
export interface QueryTotalField {
  label: string;
  metric: string;
  seasons?: string[];
  direction: "higher" | "lower";
}

export const PROFILE_QUERY_TOTAL_FIELDS: QueryTotalField[] = [
  // Same underlying /query data is also surfaced as its own row on the
  // Comparison page's table (app/team/comparison/page.tsx) under this
  // same field name -- keep the two in sync if either changes.
  { label: "Matchup Wins", metric: "MATCHUP_WINS", seasons: ["RS", "PO"], direction: "higher" },
  { label: "Total Losses", metric: "MATCHUP_LOSSES", seasons: ["RS", "PO"], direction: "lower" },
  { label: "Category Wins", metric: "CAT_WINS", seasons: ["RS", "PO"], direction: "higher" },
  { label: "Total Category Losses", metric: "CAT_LOSSES", seasons: ["RS", "PO"], direction: "lower" },
  { label: "Total Reg Season Wins", metric: "MATCHUP_WINS", seasons: ["RS"], direction: "higher" },
  { label: "Total Reg Season Losses", metric: "MATCHUP_LOSSES", seasons: ["RS"], direction: "lower" },
  { label: "Playoff Wins", metric: "MATCHUP_WINS", seasons: ["PO"], direction: "higher" },
  { label: "Total Playoff Losses", metric: "MATCHUP_LOSSES", seasons: ["PO"], direction: "lower" },
];


// The 3 /query-backed fields the Comparison table actually renders (Winning
// and Playoffs sections) -- a trimmed copy of Profile's own
// PROFILE_QUERY_TOTAL_FIELDS (which also fetches Losses/Reg-Season-only splits for
// League Top 3 ranking, not needed here).
export const COMPARISON_QUERY_TOTAL_FIELDS: Omit<QueryTotalField, "direction">[] = [
  { label: "Matchup Wins", metric: "MATCHUP_WINS", seasons: ["RS", "PO"] },
  { label: "Category Wins", metric: "CAT_WINS", seasons: ["RS", "PO"] },
  { label: "Playoff Wins", metric: "MATCHUP_WINS", seasons: ["PO"] },
];

