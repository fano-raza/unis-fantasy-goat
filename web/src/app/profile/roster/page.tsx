"use client";

import { useEffect, useState } from "react";
import { SourceLastUpdated } from "@/components/source-last-updated";
import { RosterView } from "@/components/roster-view";
import { LoadingBasketballs } from "@/components/loading-basketballs";
import { RoutedViewSwitcher } from "@/components/routed-view-switcher";
import { getLeagueMeta, type LeagueMeta } from "@/lib/api";

const VIEW_OPTIONS = [
  { value: "profile", label: "Profile" },
  { value: "comparison", label: "Comparison" },
  { value: "roster", label: "Roster" },
];
const VIEW_PATHS = { profile: "/profile", comparison: "/profile/comparison", roster: "/profile/roster" };

export default function RosterPage() {
  const [meta, setMeta] = useState<LeagueMeta | null>(null);

  useEffect(() => {
    getLeagueMeta().then(setMeta);
  }, []);

  if (!meta) return <LoadingBasketballs label="Loading" />;

  return (
    <div className="flex flex-col gap-4">
      <div className="sticky top-0 z-30 flex flex-wrap items-center gap-3 rounded-sm border border-border bg-card px-3 py-2 shadow-sm">
        <RoutedViewSwitcher options={VIEW_OPTIONS} current="roster" paths={VIEW_PATHS} />
        <div className="ml-auto">
          <SourceLastUpdated source="team_summary" />
        </div>
      </div>

      <RosterView meta={meta} />
    </div>
  );
}
