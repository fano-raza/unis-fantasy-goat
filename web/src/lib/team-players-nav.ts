import type { ArrowToggleOption } from "@/components/arrow-toggle";

// Single canonical list of every Team/Players sub-page, shared by all 5
// consumers (profile-view, comparison-view, roster-page-view,
// draft-page-view, app/players/page.tsx) so RoutedViewSwitcher's
// wraps-in-both-directions arrow cycling always sees the same sibling set
// regardless of which page you entered from.
//
// Previously these were 2 separately hand-maintained lists that silently
// drifted apart: Team's 4 (Profile/Comparison/Roster/Trade Hub) never
// included Draft Hub, Players' 3 (Draft Hub/Trade Hub/Roster) never
// included Profile/Comparison. Landing on Roster or Trade Hub from either
// group then showed a DIFFERENT sibling set than the group you arrived
// from, so cycling right from Trade Hub or Roster could never reach Draft
// Hub -- only left could, via Trade Hub's old 3-item group (bug report,
// 2026-10-06).
export const TEAM_PLAYERS_VIEW_OPTIONS: ArrowToggleOption[] = [
  { value: "profile", label: "Profile" },
  { value: "comparison", label: "Comparison" },
  { value: "draft", label: "Draft Hub" },
  { value: "trade", label: "Trade Hub" },
  { value: "roster", label: "Roster" },
];

export const TEAM_PLAYERS_VIEW_PATHS: Record<string, string> = {
  profile: "/team/profile",
  comparison: "/team/comparison",
  draft: "/players/draft",
  trade: "/players",
  roster: "/team/roster",
};
