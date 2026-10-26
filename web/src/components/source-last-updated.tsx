"use client";

import type { RefreshSource } from "@/lib/api";
import { useRefreshSources } from "@/lib/live-data";

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
  // Polled app-wide by LiveDataProvider (lib/live-data.tsx), which also
  // drives the pages' background re-fetches.
  const sources = useRefreshSources();
  const value = sources?.[source];
  const date = value ? new Date(value) : null;

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
