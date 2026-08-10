"use client";

import { useEffect, useState } from "react";
import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";
import { Filter } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogPortal, DialogTrigger } from "@/components/ui/dialog";
import { FilterPanel, type FilterPanelValue } from "@/components/filter-panel";

interface FilterDrawerProps {
  allYears: number[];
  allWeeks: number[];
  allTeams: string[];
  value: FilterPanelValue;
  onChange: (value: FilterPanelValue) => void;
}

// Mobile-only bottom sheet wrapping FilterPanel, standing in for the
// always-visible sidebar shown at `sm` and up on Career Stats/Analysis.
// Slides up from the bottom (vs. MobileNav's slide-in-from-left) so it
// reads as a filter sheet, not a nav drawer -- different gesture, same
// Dialog primitive underneath (web/src/components/ui/dialog.tsx).
// Holds its own draft state, same draft/applied split as AnalysisGraph's
// X/Y/group-by controls, so toggling checkboxes doesn't refetch data until
// the user taps Apply.
export function FilterDrawer({ allYears, allWeeks, allTeams, value, onChange }: FilterDrawerProps) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<FilterPanelValue>(value);

  // Re-sync draft to the applied value whenever the drawer opens, so a
  // previously-cancelled edit doesn't linger.
  useEffect(() => {
    if (open) setDraft(value);
  }, [open, value]);

  function apply() {
    onChange(draft);
    setOpen(false);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button variant="outline" size="sm" />}>
        <Filter className="size-3.5" />
        Filter
      </DialogTrigger>
      <DialogPortal>
        <DialogPrimitive.Backdrop className="fixed inset-0 z-50 bg-black/40 duration-150 data-open:animate-in data-open:fade-in-0 data-closed:animate-out data-closed:fade-out-0" />
        <DialogPrimitive.Popup className="fixed inset-x-0 bottom-0 z-50 flex max-h-[80vh] flex-col gap-3 rounded-t-xl border-t border-border bg-popover p-4 outline-none duration-200 data-open:animate-in data-open:slide-in-from-bottom data-closed:animate-out data-closed:slide-out-to-bottom">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold tracking-wider uppercase">Filters</span>
            <DialogClose render={<Button variant="ghost" size="sm" />}>Cancel</DialogClose>
          </div>
          <div className="flex-1 overflow-y-auto">
            <FilterPanel
              allYears={allYears}
              allWeeks={allWeeks}
              allTeams={allTeams}
              value={draft}
              onChange={setDraft}
            />
          </div>
          <Button onClick={apply}>Apply</Button>
        </DialogPrimitive.Popup>
      </DialogPortal>
    </Dialog>
  );
}
