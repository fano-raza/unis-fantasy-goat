import { getWeeklyStatsBootstrap, type WeeklyStatsBootstrap } from "@/lib/api";
import { WeeklyStatsView } from "@/components/weekly-stats-view";

// Matches the backend's own Cache-Control window on this endpoint (see
// dashboard_site/api/app.py's add_short_cache_header) -- data is only ever
// as fresh as the backend's 5-min refresh loop anyway, so caching the
// server-rendered page for this long costs negligible extra staleness.
// Letting Next's Data Cache serve this means most visits within the window
// never touch the droplet at all, server or client side.
export const revalidate = 30;

// Fetches the bootstrap (meta + current week's rows) during SSR/ISR, so
// the round trip to the backend happens while the page is being generated
// -- not after the client downloads, parses, and hydrates the page's JS
// and only then starts fetching. See weekly-stats-view.tsx for how this
// gets handed to the client component, and why it falls back to a client
// fetch if this is null.
export default async function WeeklyStatsPage() {
  let initialBootstrap: WeeklyStatsBootstrap | null = null;
  try {
    initialBootstrap = await getWeeklyStatsBootstrap({ next: { revalidate: 30 } });
  } catch {
    // Backend unreachable at render time -- WeeklyStatsView falls back to
    // its own client-side fetch/error UI.
  }
  return <WeeklyStatsView initialBootstrap={initialBootstrap} />;
}
