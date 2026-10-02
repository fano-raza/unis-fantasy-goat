import { getStandingsBootstrap, type StandingsBootstrap } from "@/lib/api";
import { LeagueWinsView } from "@/components/league-wins-view";

// See app/page.tsx for the full rationale on this pattern.
export const revalidate = 30;

export default async function LeagueWinsPage() {
  let initialBootstrap: StandingsBootstrap | null = null;
  try {
    initialBootstrap = await getStandingsBootstrap({ next: { revalidate: 30 } });
  } catch {
    // Backend unreachable at render time -- LeagueWinsView falls back to
    // its own client-side fetch.
  }
  return <LeagueWinsView initialBootstrap={initialBootstrap} />;
}
