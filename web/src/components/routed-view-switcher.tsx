"use client";

import { useRouter } from "next/navigation";
import { ArrowToggle, type ArrowToggleOption } from "@/components/arrow-toggle";
import { ViewTabs, type ViewTabOption } from "@/components/view-tabs";

// Same ArrowToggle(mobile)/ViewTabs(desktop) pair used elsewhere, but each
// option navigates to its own real route instead of flipping local state --
// for pages split into sibling sub-page routes (e.g. /profile,
// /profile/comparison, /profile/roster) that still want one shared toggle
// UI to move between them.
export function RoutedViewSwitcher({
  options,
  current,
  paths,
}: {
  options: (ArrowToggleOption | ViewTabOption)[];
  current: string;
  paths: Record<string, string>;
}) {
  const router = useRouter();

  function go(value: string) {
    const path = paths[value];
    if (path) router.push(path);
  }

  return (
    <>
      <div className="sm:hidden">
        <ArrowToggle options={options} value={current} onChange={go} />
      </div>
      <div className="hidden sm:flex">
        <ViewTabs options={options} value={current} onChange={go} />
      </div>
    </>
  );
}
