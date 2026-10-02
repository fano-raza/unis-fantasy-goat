import { getRatingsBootstrap, type RatingsBootstrap } from "@/lib/api";
import { RatingsView } from "@/components/ratings-view";

// See app/page.tsx for the full rationale on this pattern.
export const revalidate = 30;

export default async function RatingsPage() {
  let initialBootstrap: RatingsBootstrap | null = null;
  try {
    initialBootstrap = await getRatingsBootstrap({ next: { revalidate: 30 } });
  } catch {
    // Backend unreachable at render time -- RatingsView falls back to its
    // own client-side fetch.
  }
  return <RatingsView initialBootstrap={initialBootstrap} />;
}
