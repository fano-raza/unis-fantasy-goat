"use client";

import { useEffect, useState } from "react";
import { RosterView } from "@/components/roster-view";
import { LoadingBasketballs } from "@/components/loading-basketballs";
import { RoutedViewSwitcher } from "@/components/routed-view-switcher";
import { getLeagueMeta, type LeagueMeta } from "@/lib/api";

const VIEW_OPTIONS = [
  { value: "profile", label: "Profile" },
  { value: "comparison", label: "Comparison" },
  { value: "roster", label: "Roster" },
  { value: "trade", label: "Trade Hub" },
];
const VIEW_PATHS = {
  profile: "/team/profile",
  comparison: "/team/comparison",
  roster: "/team/roster",
  trade: "/players",
};

export function RosterPageView({ initialMeta }: { initialMeta: LeagueMeta | null }) {
  const [meta, setMeta] = useState<LeagueMeta | null>(initialMeta);

  useEffect(() => {
    if (meta) return;
    getLeagueMeta().then(setMeta);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!meta) return <LoadingBasketballs label="Loading" />;

  return (
    <div className="flex flex-col gap-4">
      <div className="sticky top-0 z-30 flex flex-wrap items-center gap-3 rounded-sm border border-border bg-card px-3 py-2 shadow-sm">
        <RoutedViewSwitcher options={VIEW_OPTIONS} current="roster" paths={VIEW_PATHS} />
      </div>

      <RosterView meta={meta} />
    </div>
  );
}
