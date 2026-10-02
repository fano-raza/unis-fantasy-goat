import { getStandingsBootstrap, type StandingsBootstrap } from "@/lib/api";
import { StandingsView } from "@/components/standings-view";

// See app/page.tsx for the full rationale on this pattern.
export const revalidate = 30;

export default async function StandingsPage() {
  let initialBootstrap: StandingsBootstrap | null = null;
  try {
    initialBootstrap = await getStandingsBootstrap({ next: { revalidate: 30 } });
  } catch {
    // Backend unreachable at render time -- StandingsView falls back to
    // its own client-side fetch.
  }
  return <StandingsView initialBootstrap={initialBootstrap} />;
}
