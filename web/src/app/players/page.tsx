import { getPlayerStats, type PlayerStat } from "@/lib/api";
import { RoutedViewSwitcher } from "@/components/routed-view-switcher";
import { TradeHub } from "@/components/trade-hub";
import { TEAM_PLAYERS_VIEW_OPTIONS, TEAM_PLAYERS_VIEW_PATHS } from "@/lib/team-players-nav";

// See app/page.tsx for the full rationale on this pattern.
export const revalidate = 30;

export default async function PlayersPage() {
  let initialPlayers: PlayerStat[] | null = null;
  try {
    initialPlayers = await getPlayerStats({ next: { revalidate: 30 } });
  } catch {
    // Backend unreachable at render time -- TradeHub falls back to its
    // own client-side fetch.
  }
  return (
    <div className="flex flex-col gap-4">
      <div className="sticky top-0 z-30 flex items-center gap-3 rounded-sm border border-border bg-card px-3 py-2 shadow-sm">
        <RoutedViewSwitcher options={TEAM_PLAYERS_VIEW_OPTIONS} current="trade" paths={TEAM_PLAYERS_VIEW_PATHS} />
      </div>
      <TradeHub initialPlayers={initialPlayers} />
    </div>
  );
}
