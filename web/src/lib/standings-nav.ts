import type { ArrowToggleOption } from "@/components/arrow-toggle";

// Single canonical list of Standings' 3 sub-pages, shared by standings-view,
// league-wins-view, and ratings-view (previously 3 separately hand-typed
// copies -- same drift risk as the Team/Players lists fixed earlier this
// session, extracted proactively here since mobile-nav.tsx also needs one
// canonical source to build the mobile menu's sub-page disclosure from).
export const STANDINGS_VIEW_OPTIONS: ArrowToggleOption[] = [
  { value: "1v1", label: "Season Standings" },
  { value: "league_wins", label: "League Wins" },
  { value: "ratings", label: "Ratings" },
];

export const STANDINGS_VIEW_PATHS: Record<string, string> = {
  "1v1": "/standings",
  league_wins: "/standings/league-wins",
  ratings: "/standings/ratings",
};
