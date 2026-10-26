"use client";

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { getRefreshStatus, type RefreshSource } from "@/lib/api";

// How often open pages ask the API whether it has newer data. The stat
// updater rewrites the live stats every ~2 min during game hours and the API
// reloads them every 90 s, so a minute keeps tables within ~1 min of the API.
const POLL_INTERVAL_MS = 60_000;

const SOURCES: RefreshSource[] = ["live", "draft", "player_stats", "team_summary"];
type Versions = Record<RefreshSource, number>;

interface LiveDataState {
  // File timestamps per source -- the header's "Updated ..." badge.
  sources: Record<RefreshSource, string | null> | null;
  // Bumps each time the API starts serving newer data for a source.
  versions: Versions;
}

const LiveDataContext = createContext<LiveDataState | null>(null);

/**
 * One app-wide poll of /refresh_status (every minute while the tab is
 * visible, and right away when it becomes visible again). Pages subscribe
 * with useLiveRefetch() and quietly re-fetch their tables when the API has
 * loaded new data -- before this, only Weekly Stats' current week ever
 * refreshed without a page reload (user report, 2026-10-26).
 */
export function LiveDataProvider({ children }: { children: ReactNode }) {
  const [sources, setSources] = useState<LiveDataState["sources"]>(null);
  const [versions, setVersions] = useState<Versions>({ live: 0, draft: 0, player_stats: 0, team_summary: 0 });
  // Last `loaded` timestamps seen; null until the first poll (which only
  // records a baseline -- the page just fetched its data itself).
  const loaded = useRef<Record<string, string | null> | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const status = await getRefreshStatus();
        if (cancelled) return;
        setSources(status.sources);
        // Older API without `loaded`: fall back to file timestamps.
        const next = status.loaded ?? status.sources;
        const prev = loaded.current;
        loaded.current = next;
        if (!prev) return;
        const changed = SOURCES.filter((s) => next[s] && next[s] !== prev[s]);
        if (changed.length) {
          setVersions((v) => {
            const out = { ...v };
            for (const s of changed) out[s] += 1;
            return out;
          });
        }
      } catch {
        // Non-critical -- try again on the next tick.
      }
    }

    poll();
    const interval = setInterval(() => {
      if (document.visibilityState === "visible") poll();
    }, POLL_INTERVAL_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible") poll();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  return <LiveDataContext.Provider value={{ sources, versions }}>{children}</LiveDataContext.Provider>;
}

function useLiveData(): LiveDataState {
  const ctx = useContext(LiveDataContext);
  if (!ctx) throw new Error("useLiveData must be used within LiveDataProvider");
  return ctx;
}

/** Latest file timestamps per source (the "Updated ..." badge). */
export function useRefreshSources() {
  return useLiveData().sources;
}

/**
 * For a page's data-fetching effect: add `version` to its dependencies so it
 * re-runs when the API has newer `source` data, and call `isRefetch()` at
 * the top of the effect -- true means this run is a background refresh, so
 * skip the loading veil and keep the current rows if the request fails.
 */
export function useLiveRefetch(source: RefreshSource = "live") {
  const version = useLiveData().versions[source];
  const seen = useRef(version);
  return {
    version,
    isRefetch: () => {
      const refetch = seen.current !== version;
      seen.current = version;
      return refetch;
    },
  };
}
