import { getUltraBootstrap, type UltraBootstrap } from "@/lib/api";
import { UltraView } from "@/components/ultra-view";

// See app/page.tsx for the full rationale on this pattern.
export const revalidate = 30;

export default async function UltraPage() {
  let initialBootstrap: UltraBootstrap | null = null;
  try {
    initialBootstrap = await getUltraBootstrap({ next: { revalidate: 30 } });
  } catch {
    // Backend unreachable at render time -- UltraView falls back to its
    // own client-side fetch.
  }
  return <UltraView initialBootstrap={initialBootstrap} />;
}
