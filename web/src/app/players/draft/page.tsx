"use client";

import { useEffect, useState } from "react";
import { RoutedViewSwitcher } from "@/components/routed-view-switcher";
import { LoadingBasketballs } from "@/components/loading-basketballs";
import { DraftHub } from "@/components/draft-hub";
import { getLeagueMeta, type LeagueMeta } from "@/lib/api";

const VIEW_OPTIONS = [
  { value: "draft", label: "Draft Hub" },
  { value: "trade", label: "Trade Hub" },
];
const VIEW_PATHS = { trade: "/players", draft: "/players/draft" };

export default function DraftHubPage() {
  const [meta, setMeta] = useState<LeagueMeta | null>(null);

  useEffect(() => {
    getLeagueMeta().then(setMeta);
  }, []);

  if (!meta) return <LoadingBasketballs label="Loading" />;

  return (
    <div className="flex flex-col gap-4">
      <div className="sticky top-0 z-30 flex items-center gap-3 rounded-sm border border-border bg-card px-3 py-2 shadow-sm">
        <RoutedViewSwitcher options={VIEW_OPTIONS} current="draft" paths={VIEW_PATHS} />
      </div>
      <DraftHub meta={meta} />
    </div>
  );
}
