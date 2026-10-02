import { getLeagueMeta, type LeagueMeta } from "@/lib/api";
import { AnalysisView } from "@/components/analysis-view";

// See app/page.tsx for the full rationale on this pattern. Only meta is
// SSR'd here -- the actual filter (and thus the rows fetch) depends on a
// localStorage-persisted value, which only exists client-side, so that
// part stays a client fetch same as before.
export const revalidate = 30;

export default async function AnalysisPage() {
  let initialMeta: LeagueMeta | null = null;
  try {
    initialMeta = await getLeagueMeta({ next: { revalidate: 30 } });
  } catch {
    // Backend unreachable at render time -- AnalysisView falls back to
    // its own client-side fetch.
  }
  return <AnalysisView initialMeta={initialMeta} />;
}
