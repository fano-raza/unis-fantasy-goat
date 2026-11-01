"use client";

import { useRouter } from "next/navigation";
import { ViewTabs, type ViewTabOption } from "@/components/view-tabs";

// The section's sub-page tabs (ViewTabs), where each option navigates to its
// own real route instead of flipping local state -- for pages split into
// sibling sub-page routes (e.g. /career/profile, /career/comparison,
// /career/stats). Same tabs on mobile and desktop (user spec 2026-11-01;
// mobile used to show a one-label ArrowToggle).
export function RoutedViewSwitcher({
  options,
  current,
  paths,
}: {
  options: ViewTabOption[];
  current: string;
  paths: Record<string, string>;
}) {
  const router = useRouter();

  function go(value: string) {
    const path = paths[value];
    if (path) router.push(path);
  }

  return <ViewTabs options={options} value={current} onChange={go} />;
}
