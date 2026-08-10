"use client";

import { useState } from "react";
import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";
import { Award } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogPortal, DialogTrigger } from "@/components/ui/dialog";
import { TeamBadges } from "@/components/team-badges";
import { POSITIVE_BADGE_TYPES, type BadgeInstance } from "@/lib/badges";

interface BadgeDrawerProps {
  positive: BadgeInstance[];
  negative: BadgeInstance[];
}

// Mobile-only bottom sheet for the badge list -- same Dialog primitive and
// slide-up-from-bottom treatment as FilterDrawer (web/src/components/
// filter-drawer.tsx), just displaying badges instead of filter controls.
export function BadgeDrawer({ positive, negative }: BadgeDrawerProps) {
  const [open, setOpen] = useState(false);
  const uniquePositiveTypes = new Set(positive.map((b) => b.type)).size;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button variant="outline" size="sm" />}>
        <Award className="size-3.5" />
        Show Badges
      </DialogTrigger>
      <DialogPortal>
        <DialogPrimitive.Backdrop className="fixed inset-0 z-50 bg-black/40 duration-150 data-open:animate-in data-open:fade-in-0 data-closed:animate-out data-closed:fade-out-0" />
        <DialogPrimitive.Popup className="fixed inset-x-0 bottom-0 z-50 flex max-h-[80vh] flex-col gap-3 rounded-t-xl border-t border-border bg-popover p-4 outline-none duration-200 data-open:animate-in data-open:slide-in-from-bottom data-closed:animate-out data-closed:slide-out-to-bottom">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold tracking-wider uppercase">Badges</span>
            <DialogClose render={<Button variant="ghost" size="sm" />}>Close</DialogClose>
          </div>
          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            <span>
              Total: <span className="font-mono font-extrabold text-foreground">{positive.length}</span>
            </span>
            <span>
              Unique:{" "}
              <span className="font-mono font-extrabold text-foreground">
                {uniquePositiveTypes}/{POSITIVE_BADGE_TYPES.length}
              </span>
            </span>
          </div>
          <div className="flex-1 overflow-y-auto">
            <TeamBadges positive={positive} negative={negative} />
          </div>
        </DialogPrimitive.Popup>
      </DialogPortal>
    </Dialog>
  );
}
