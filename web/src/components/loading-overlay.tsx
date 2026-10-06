"use client";

import type { ReactNode } from "react";
import { LoadingBasketballs } from "@/components/loading-basketballs";

// Feature request, 2026-10-06: when a page that's already showing data
// re-fetches (a filter/week/year change), don't blank the screen out --
// keep the previous render visible underneath a translucent veil (20%
// transparent, i.e. bg-background/80) with the bouncing-balls indicator on
// top. Only correct where the underlying data state is known to persist
// across a refetch until the new data replaces it (confirmed per call
// site: `setIsLoading(true)`/`setLoading(true)` never clears the data
// state itself, only a caught error does) -- if there's no previous
// content yet (genuine first load), pass hasContent={false} and this falls
// back to the plain full-replacement LoadingBasketballs instead of
// overlaying blank space.
export function LoadingOverlay({
  active,
  hasContent,
  label,
  children,
}: {
  active: boolean;
  hasContent: boolean;
  label?: string;
  children: ReactNode;
}) {
  if (active && !hasContent) {
    return <LoadingBasketballs label={label} />;
  }
  return (
    <div className="relative">
      {children}
      {active && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-background/80">
          <LoadingBasketballs label={label} />
        </div>
      )}
    </div>
  );
}
