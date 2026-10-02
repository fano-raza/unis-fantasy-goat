import { getDraftPicks, getLeagueMeta, type DraftPick, type LeagueMeta } from "@/lib/api";
import { DraftPageView } from "@/components/draft-page-view";

// See app/page.tsx for the full rationale on this pattern.
export const revalidate = 30;

export default async function DraftHubPage() {
  let initialMeta: LeagueMeta | null = null;
  let initialPicks: DraftPick[] | null = null;
  try {
    initialMeta = await getLeagueMeta({ next: { revalidate: 30 } });
    // The default filter (every year, every team) -- exactly what
    // DraftHub itself defaults to on first render.
    initialPicks = await getDraftPicks(
      { years: initialMeta.years, teams: initialMeta.members },
      { next: { revalidate: 30 } },
    );
  } catch {
    // Backend unreachable at render time -- DraftPageView/DraftHub fall
    // back to their own client-side fetches.
  }
  return <DraftPageView initialMeta={initialMeta} initialPicks={initialPicks} />;
}
