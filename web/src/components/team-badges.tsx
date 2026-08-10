"use client";

import { useState } from "react";
import type { BadgeInstance } from "@/lib/badges";
import { cn } from "@/lib/utils";

// A single badge chip: hover shows "{label} {year}" on desktop (mouse
// enter/leave), tapping shows the same on touch (click toggles it) --
// both wired to the same open/close state so one implementation covers
// both interaction models the user asked for.
function BadgeChip({ badge, open, onOpen, onClose }: {
  badge: BadgeInstance;
  open: boolean;
  onOpen: () => void;
  onClose: () => void;
}) {
  return (
    <div className="relative">
      <button
        type="button"
        className={cn(
          "flex size-9 items-center justify-center rounded-full border border-border bg-card text-lg leading-none transition-transform hover:scale-110",
          !badge.positive && "grayscale opacity-70",
        )}
        onMouseEnter={onOpen}
        onMouseLeave={onClose}
        onClick={() => (open ? onClose() : onOpen())}
        aria-label={`${badge.label} ${badge.year}`}
      >
        {badge.icon === "L" ? (
          <span className="font-mono text-sm font-extrabold text-muted-foreground">L</span>
        ) : (
          badge.icon
        )}
      </button>
      {open && (
        <div className="absolute top-full left-1/2 z-20 mt-1 -translate-x-1/2 rounded-sm border border-border bg-card px-2 py-1 text-xs font-bold whitespace-nowrap text-foreground shadow-md">
          {badge.label} {badge.year}
        </div>
      )}
    </div>
  );
}

export function TeamBadges({
  positive,
  negative,
}: {
  positive: BadgeInstance[];
  negative: BadgeInstance[];
}) {
  const [openId, setOpenId] = useState<string | null>(null);

  if (positive.length === 0 && negative.length === 0) {
    return <p className="text-sm text-muted-foreground">No badges yet.</p>;
  }

  return (
    <div className="flex flex-col gap-2">
      {positive.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {positive.map((b) => (
            <BadgeChip
              key={b.id}
              badge={b}
              open={openId === b.id}
              onOpen={() => setOpenId(b.id)}
              onClose={() => setOpenId((id) => (id === b.id ? null : id))}
            />
          ))}
        </div>
      )}
      {negative.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {negative.map((b) => (
            <BadgeChip
              key={b.id}
              badge={b}
              open={openId === b.id}
              onOpen={() => setOpenId(b.id)}
              onClose={() => setOpenId((id) => (id === b.id ? null : id))}
            />
          ))}
        </div>
      )}
    </div>
  );
}
