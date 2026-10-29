import { getLeagueMeta, getPlayerStats, type LeagueMeta, type PlayerStat } from "@/lib/api";
import { RoutedViewSwitcher } from "@/components/routed-view-switcher";
import { TradeHub } from "@/components/trade-hub";
import { TEAM_VIEW_OPTIONS, TEAM_VIEW_PATHS } from "@/lib/section-nav";

// See app/weekly-stats/page.tsx for the full rationale on this pattern.
export const revalidate = 30;

export default async function TradeHubPage() {
  let initialPlayers: PlayerStat[] | null = null;
  let meta: LeagueMeta | null = null;
  try {
    // Teams + current season for the trade sides' team pickers.
    meta = await getLeagueMeta({ next: { revalidate: 30 } });
  } catch {
    // Backend unreachable at render time -- the team pickers stay empty.
  }
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
      <div className="sticky top-0 z-30 -mx-4 flex items-center gap-3 border-b border-border bg-background/95 px-4 py-2.5 backdrop-blur sm:mx-0 sm:px-0">
        <RoutedViewSwitcher options={TEAM_VIEW_OPTIONS} current="trade" paths={TEAM_VIEW_PATHS} />
      </div>
      <TradeHub initialPlayers={initialPlayers} meta={meta} />
    </div>
  );
}
