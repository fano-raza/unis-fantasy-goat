"use client";

import { useEffect, useState } from "react";
import { getRefreshStatus, type RefreshSource } from "@/lib/api";

const POLL_INTERVAL_MS = 60_000;

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

// MM/DD/YY HH:MM, local time, 24h clock -- feature request, 2026-10-06
// (compact mobile format, two lines: "Updated at" / this string).
function formatCompact(date: Date): string {
  const mm = pad(date.getMonth() + 1);
  const dd = pad(date.getDate());
  const yy = pad(date.getFullYear() % 100);
  const hh = pad(date.getHours());
  const min = pad(date.getMinutes());
  return `${mm}/${dd}/${yy} ${hh}:${min}`;
}

// Per-page freshness indicator -- replaced a single global header timestamp
// that was misleading (it always showed the fast-moving "live" CompStats
// cadence, even on pages backed by once-daily data like Draft Hub or Trade
// Hub). Each page passes the one `source` it actually depends on.
//
// Two render paths sharing one fetched Date: desktop keeps the original
// single-line "Updated <medium date>" (CardAction, top-right of the title
// header); mobile (feature request, 2026-10-06) switches to a smaller
// two-line "Updated at" / "MM/DD/YY HH:MM" so it fits the title header's
// existing height without forcing a wider card via whitespace-nowrap on a
// narrow viewport.
export function SourceLastUpdated({ source }: { source: RefreshSource }) {
  const [date, setDate] = useState<Date | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const { sources } = await getRefreshStatus();
        const value = sources[source];
        if (cancelled || !value) return;
        setDate(new Date(value));
      } catch {
        // Non-critical UI element -- leave the last known value in place.
      }
    }

    poll();
    const interval = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [source]);

  if (!date) return null;

  return (
    <>
      <span className="hidden text-[11px] font-medium whitespace-nowrap text-muted-foreground sm:inline">
        Updated {date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}
      </span>
      <span className="flex flex-col items-end text-right text-[9px] leading-tight font-medium whitespace-nowrap text-muted-foreground sm:hidden">
        <span>Updated at</span>
        <span>{formatCompact(date)}</span>
      </span>
    </>
  );
}
