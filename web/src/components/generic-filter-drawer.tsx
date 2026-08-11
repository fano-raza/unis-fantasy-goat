"use client";

import { useEffect, useState, type ReactNode } from "react";
import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";
import { Filter } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogPortal, DialogTrigger } from "@/components/ui/dialog";

// Content-agnostic sibling of FilterDrawer (which is hardcoded to
// FilterPanelValue) -- same mobile bottom-sheet chrome and draft/applied
// state split, but takes whatever filter shape/controls the caller needs
// via a render prop, so pages with a different filter shape (Ultra's
// week-only checklist, Players' year+team checklists) don't need their own
// bespoke Dialog wiring just to get the same mobile drawer pattern.
export function GenericFilterDrawer<T>({
  value,
  onChange,
  renderContent,
  title = "Filters",
}: {
  value: T;
  onChange: (value: T) => void;
  renderContent: (draft: T, setDraft: (value: T) => void) => ReactNode;
  title?: string;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<T>(value);

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
            <span className="text-[11px] font-bold tracking-wider uppercase">{title}</span>
            <DialogClose render={<Button variant="ghost" size="sm" />}>Cancel</DialogClose>
          </div>
          <div className="flex-1 overflow-y-auto">{renderContent(draft, setDraft)}</div>
          <Button onClick={apply}>Apply</Button>
        </DialogPrimitive.Popup>
      </DialogPortal>
    </Dialog>
  );
}
