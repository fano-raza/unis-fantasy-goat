"use client";

import { usePathname } from "next/navigation";
import { SourceLastUpdated } from "@/components/source-last-updated";
import type { RefreshSource } from "@/lib/api";

// Feature request, 2026-10-06: moved out of every individual page (where it
// lived either in the title CardHeader's CardAction -- squeezing
// CardDescription's available width -- or a filter bar's ml-auto slot)
// into the global site header instead, so there's exactly one freshness
// indicator on screen at a time. Still per-page-correct (not the single
// misleading global timestamp this design replaced originally, per
// source-last-updated.tsx's own long-standing comment) by mapping the
// current route to the same RefreshSource each page used to pass directly
// -- mirrors every `<SourceLastUpdated source="...">` call site this
// replaced, 1:1.
function sourceForPathname(pathname: string): RefreshSource | null {
  if (pathname.startsWith("/players/draft")) return "draft";
  if (pathname.startsWith("/players")) return "player_stats";
  if (pathname.startsWith("/team")) return "team_summary";
  if (pathname.startsWith("/standings")) return "live";
  if (pathname === "/" || pathname === "/career" || pathname === "/analysis" || pathname === "/ultra") {
    return "live";
  }
  return null; // e.g. /champions-lounge -- no backing data source
}

export function GlobalLastUpdated() {
  const pathname = usePathname();
  const source = sourceForPathname(pathname);
  if (!source) return null;
  return <SourceLastUpdated source={source} />;
}
