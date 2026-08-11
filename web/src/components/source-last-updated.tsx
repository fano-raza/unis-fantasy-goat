"use client";

import { useEffect, useState } from "react";
import { getRefreshStatus, type RefreshSource } from "@/lib/api";

const POLL_INTERVAL_MS = 60_000;

// Per-page freshness indicator -- replaced a single global header timestamp
// that was misleading (it always showed the fast-moving "live" CompStats
// cadence, even on pages backed by once-daily data like Draft Hub or Trade
// Hub). Each page passes the one `source` it actually depends on.
export function SourceLastUpdated({ source }: { source: RefreshSource }) {
  const [label, setLabel] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const { sources } = await getRefreshStatus();
        const value = sources[source];
        if (cancelled || !value) return;
        setLabel(
          new Date(value).toLocaleString(undefined, {
            dateStyle: "medium",
            timeStyle: "short",
          }),
        );
      } catch {
        // Non-critical UI element -- leave the last known label in place.
      }
    }

    poll();
    const interval = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [source]);

  if (!label) return null;

  return (
    <span className="text-[11px] font-medium whitespace-nowrap text-muted-foreground">
      Updated {label}
    </span>
  );
}
