"use client";

import { useEffect, useState } from "react";
import { getRefreshStatus } from "@/lib/api";

const POLL_INTERVAL_MS = 60_000;

export function LastUpdated() {
  const [label, setLabel] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const { last_updated } = await getRefreshStatus();
        if (cancelled || !last_updated) return;
        setLabel(
          new Date(last_updated).toLocaleString(undefined, {
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
  }, []);

  if (!label) return null;

  return (
    <span className="text-[11px] font-medium whitespace-nowrap text-muted-foreground">
      Updated {label}
    </span>
  );
}
