import { getLeagueMeta, getTrades, type LeagueMeta, type TradeRow } from "@/lib/api";
import { RoutedViewSwitcher } from "@/components/routed-view-switcher";
import { TradeLog } from "@/components/trade-log";
import { CAREER_VIEW_OPTIONS, CAREER_VIEW_PATHS } from "@/lib/section-nav";

// See app/weekly-stats/page.tsx for the full rationale on this pattern.
export const revalidate = 30;

export default async function TradeLogPage() {
  let meta: LeagueMeta | null = null;
  let trades: TradeRow[] | null = null;
  try {
    [meta, trades] = await Promise.all([
      getLeagueMeta({ next: { revalidate: 30 } }),
      getTrades({ next: { revalidate: 30 } }),
    ]);
  } catch {
    // Backend unreachable at render time -- TradeLog fetches client-side.
  }
  // A cached response from before 2026-11-04's completed-only change was an
  // object, not a list -- let the client fetch fresh instead of crashing.
  if (!Array.isArray(trades)) trades = null;
  return (
    <div className="flex flex-col gap-4">
      <div className="sticky top-0 z-30 -mx-4 flex items-center gap-3 border-b border-border bg-background/95 px-4 py-2.5 backdrop-blur sm:mx-0 sm:px-0">
        <RoutedViewSwitcher options={CAREER_VIEW_OPTIONS} current="trade-log" paths={CAREER_VIEW_PATHS} />
      </div>
      <TradeLog initialMeta={meta} initialTrades={trades} />
    </div>
  );
}
