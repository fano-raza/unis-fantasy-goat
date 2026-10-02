import { getLeagueMeta, type LeagueMeta } from "@/lib/api";
import { RosterPageView } from "@/components/roster-page-view";

// See app/page.tsx for the full rationale on this pattern.
export const revalidate = 30;

export default async function RosterPage() {
  let initialMeta: LeagueMeta | null = null;
  try {
    initialMeta = await getLeagueMeta({ next: { revalidate: 30 } });
  } catch {
    // Backend unreachable at render time -- RosterPageView falls back to
    // its own client-side fetch.
  }
  return <RosterPageView initialMeta={initialMeta} />;
}
