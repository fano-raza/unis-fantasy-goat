import type { ArrowToggleOption } from "@/components/arrow-toggle";

// Canonical sub-page lists for the top-level sections that have more than
// one page. Each list is shared by every page in that section's
// RoutedViewSwitcher and by mobile-nav.tsx's drawer, so the switcher and
// the menu always show the same sibling set in the same order.
//
// Reorganized 2026-10-28 (user request): Weekly Stats (Weekly Stats,
// Ultra), Team (Roster, Trade Hub, Draft Hub), Career (Profile,
// Comparison, Career Stats). Replaces the old combined Team/Players list
// (team-players-nav.ts). Same day: Standings renamed League and Draft Hub
// moved into it from Team (League's list replaces standings-nav.ts). Old
// URLs redirect in next.config.ts.

export const WEEKLY_VIEW_OPTIONS: ArrowToggleOption[] = [
  { value: "weekly", label: "Weekly Stats" },
  { value: "ultra", label: "Ultra" },
];

export const WEEKLY_VIEW_PATHS: Record<string, string> = {
  weekly: "/weekly-stats",
  ultra: "/weekly-stats/ultra",
};

export const TEAM_VIEW_OPTIONS: ArrowToggleOption[] = [
  { value: "roster", label: "Roster" },
  { value: "trade", label: "Trade Hub" },
];

export const TEAM_VIEW_PATHS: Record<string, string> = {
  roster: "/team/roster",
  trade: "/team/trade-hub",
};

export const LEAGUE_VIEW_OPTIONS: ArrowToggleOption[] = [
  { value: "1v1", label: "Season Standings" },
  { value: "league_wins", label: "League Wins" },
  { value: "ratings", label: "Ratings" },
  { value: "draft", label: "Draft Hub" },
];

export const LEAGUE_VIEW_PATHS: Record<string, string> = {
  "1v1": "/league/standings",
  league_wins: "/league/league-wins",
  ratings: "/league/ratings",
  draft: "/league/draft-hub",
};

export const CAREER_VIEW_OPTIONS: ArrowToggleOption[] = [
  { value: "profile", label: "Profile" },
  { value: "comparison", label: "Comparison" },
  { value: "stats", label: "Career Stats" },
];

export const CAREER_VIEW_PATHS: Record<string, string> = {
  profile: "/career/profile",
  comparison: "/career/comparison",
  stats: "/career/stats",
};
