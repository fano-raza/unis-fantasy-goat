"use client";

import { useEffect, useState } from "react";
import { RoutedViewSwitcher } from "@/components/routed-view-switcher";
import { LoadingBasketballs } from "@/components/loading-basketballs";
import { DraftHub } from "@/components/draft-hub";
import { getLeagueMeta, type DraftPick, type LeagueMeta } from "@/lib/api";
import { TEAM_PLAYERS_VIEW_OPTIONS, TEAM_PLAYERS_VIEW_PATHS } from "@/lib/team-players-nav";

interface DraftPageViewProps {
  // Both fetched server-side (see app/players/draft/page.tsx); null if
  // that fetch failed, in which case this falls back to the original
  // client-side meta fetch (DraftHub itself falls back to its own fetch
  // for initialPicks -- see that component).
  initialMeta: LeagueMeta | null;
  initialPicks: DraftPick[] | null;
}

export function DraftPageView({ initialMeta, initialPicks }: DraftPageViewProps) {
  const [meta, setMeta] = useState<LeagueMeta | null>(initialMeta);

  useEffect(() => {
    if (meta) return;
    getLeagueMeta().then(setMeta);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!meta) return <LoadingBasketballs label="Loading" />;

  return (
    <div className="flex flex-col gap-4">
      <div className="sticky top-0 z-30 -mx-4 flex items-center gap-3 border-b border-border bg-background/95 px-4 py-2.5 backdrop-blur sm:mx-0 sm:px-0">
        <RoutedViewSwitcher options={TEAM_PLAYERS_VIEW_OPTIONS} current="draft" paths={TEAM_PLAYERS_VIEW_PATHS} />
      </div>
      <DraftHub meta={meta} initialPicks={initialPicks} />
    </div>
  );
}
