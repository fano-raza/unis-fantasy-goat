import { getPlayerStats, type PlayerStat } from "@/lib/api";
import { RoutedViewSwitcher } from "@/components/routed-view-switcher";
import { TradeHub } from "@/components/trade-hub";
import { TEAM_PLAYERS_VIEW_OPTIONS, TEAM_PLAYERS_VIEW_PATHS } from "@/lib/team-players-nav";

// See app/page.tsx for the full rationale on this pattern.
export const revalidate = 30;

export default async function PlayersPage() {
  let initialPlayers: PlayerStat[] | null = null;
  try {
    // Deliberately no `next: { revalidate }` here unlike the other SSR
    // fetches on this page's siblings -- this payload is ~2.9MB, always
    // over Next's 2MB Data Cache per-item limit, so opting into that cache
    // throws an unhandled rejection from Next's own cache-write internals
    // (observed crashing the whole lambda in production, 2026-10-16)
    // instead of just skipping the cache. Omitting `next.revalidate`
    // keeps this a plain per-request fetch, same as trade-hub.tsx's own
    // client-side call to the same endpoint.
    initialPlayers = await getPlayerStats();
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
