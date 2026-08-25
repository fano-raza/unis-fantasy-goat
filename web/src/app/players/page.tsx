"use client";

import { RoutedViewSwitcher } from "@/components/routed-view-switcher";
import { TradeHub } from "@/components/trade-hub";

const VIEW_OPTIONS = [
  { value: "draft", label: "Draft Hub" },
  { value: "trade", label: "Trade Hub" },
  { value: "roster", label: "Roster" },
];
const VIEW_PATHS = { trade: "/players", draft: "/players/draft", roster: "/team/roster" };

export default function PlayersPage() {
  return (
    <div className="flex flex-col gap-4">
      <div className="sticky top-0 z-30 flex items-center gap-3 rounded-sm border border-border bg-card px-3 py-2 shadow-sm">
        <RoutedViewSwitcher options={VIEW_OPTIONS} current="trade" paths={VIEW_PATHS} />
      </div>
      <TradeHub />
    </div>
  );
}
