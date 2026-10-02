import { getCareerBootstrap, type CareerBootstrap } from "@/lib/api";
import { CareerStatsView } from "@/components/career-view";

// Matches the backend's own Cache-Control window on this endpoint (see
// dashboard_site/api/app.py's add_short_cache_header). See app/page.tsx
// for the full rationale on this pattern.
export const revalidate = 30;

export default async function CareerStatsPage() {
  let initialBootstrap: CareerBootstrap | null = null;
  try {
    initialBootstrap = await getCareerBootstrap({ next: { revalidate: 30 } });
  } catch {
    // Backend unreachable at render time -- CareerStatsView falls back to
    // its own client-side fetch.
  }
  return <CareerStatsView initialBootstrap={initialBootstrap} />;
}
