"use client";

import { useEffect, useState } from "react";
import { RosterView } from "@/components/roster-view";
import { LoadingBasketballs } from "@/components/loading-basketballs";
import { RoutedViewSwitcher } from "@/components/routed-view-switcher";
import { getLeagueMeta, type LeagueMeta } from "@/lib/api";
import { TEAM_PLAYERS_VIEW_OPTIONS, TEAM_PLAYERS_VIEW_PATHS } from "@/lib/team-players-nav";

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
        <RoutedViewSwitcher options={TEAM_PLAYERS_VIEW_OPTIONS} current="roster" paths={TEAM_PLAYERS_VIEW_PATHS} />
      </div>

      <RosterView meta={meta} />
    </div>
  );
}
