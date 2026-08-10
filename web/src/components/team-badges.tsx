"use client";

import { useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Podium } from "lucide-react";
import { PODIUM_ICON_MARKER, type BadgeInstance } from "@/lib/badges";
import { cn } from "@/lib/utils";

interface TooltipPosition {
  top: number;
  left: number;
  placement: "above" | "below";
}

// Rendered via a portal straight onto <body>, positioned with `fixed`
// coordinates computed from the badge's own bounding rect -- this is what
// keeps it from being clipped by any ancestor's overflow (the CardAction
// header area, the mobile bottom-sheet drawer's own scroll container,
// etc.), unlike a plain CSS-absolute child of the badge would be.
function BadgeTooltip({ text, position }: { text: string; position: TooltipPosition }) {
  return createPortal(
    <div
      className="fixed z-[100] -translate-x-1/2 rounded-sm border border-border bg-card px-2 py-1 text-xs font-bold whitespace-nowrap text-foreground shadow-md"
      style={{
        top: position.placement === "below" ? position.top + 4 : undefined,
        bottom: position.placement === "above" ? window.innerHeight - position.top + 4 : undefined,
        left: position.left,
      }}
    >
      {text}
    </div>,
    document.body,
  );
}

// A single badge chip: hover shows "{label} {year}" on desktop (mouse
// enter/leave), tapping shows the same on touch (click toggles it) --
// both wired to the same open/close state so one implementation covers
// both interaction models the user asked for. Tooltip position is
// computed fresh each time it opens (not just once), and flips above/
// below based on how much viewport space is actually available, so it's
// never clipped or pushed off the bottom of the screen.
function BadgeChip({ badge, open, onOpen, onClose }: {
  badge: BadgeInstance;
  open: boolean;
  onOpen: (position: TooltipPosition) => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLButtonElement>(null);

  function computeAndOpen() {
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const TOOLTIP_HEIGHT_ESTIMATE = 32;
    // Prefer below; flip above only if there isn't room below (this is the
    // fix for negative-row badges near the bottom of the mobile drawer/
    // viewport, where "below" previously rendered off-screen).
    const placement: "above" | "below" =
      rect.bottom + TOOLTIP_HEIGHT_ESTIMATE > window.innerHeight ? "above" : "below";
    // The tooltip is centered on this x via -translate-x-1/2 -- clamp it
    // so a badge near the left/right edge (e.g. leftmost chip in a narrow
    // mobile drawer) doesn't push the tooltip half off-screen. Generous
    // width estimate (badge labels run up to ~"Championship 2021"-length)
    // since the tooltip's real width isn't known until after it renders.
    const TOOLTIP_WIDTH_ESTIMATE = 170;
    const halfWidth = TOOLTIP_WIDTH_ESTIMATE / 2;
    const rawCenter = rect.left + rect.width / 2;
    const clampedCenter = Math.min(
      Math.max(rawCenter, halfWidth + 8),
      window.innerWidth - halfWidth - 8,
    );
    onOpen({
      top: placement === "below" ? rect.bottom : rect.top,
      left: clampedCenter,
      placement,
    });
  }

  return (
    <div className="relative">
      <button
        ref={ref}
        type="button"
        className={cn(
          "flex size-9 items-center justify-center border border-border bg-card text-lg leading-none transition-transform hover:scale-110",
          badge.positive ? "rounded-full" : "rounded-sm grayscale opacity-70",
        )}
        onMouseEnter={computeAndOpen}
        onMouseLeave={onClose}
        onClick={() => (open ? onClose() : computeAndOpen())}
        aria-label={`${badge.label} ${badge.yearLabel ?? badge.year}`}
      >
        {badge.icon === "L" ? (
          <span className="font-mono text-sm font-extrabold text-muted-foreground">L</span>
        ) : badge.icon === PODIUM_ICON_MARKER ? (
          <Podium className="size-5" />
        ) : (
          badge.icon
        )}
      </button>
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
  const [open, setOpen] = useState<{ id: string; position: TooltipPosition } | null>(null);

  if (positive.length === 0 && negative.length === 0) {
    return <p className="text-sm text-muted-foreground">No badges yet.</p>;
  }

  const allBadges = [...positive, ...negative];

  return (
    <div className="flex flex-col gap-2">
      {positive.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {positive.map((b) => (
            <BadgeChip
              key={b.id}
              badge={b}
              open={open?.id === b.id}
              onOpen={(position) => setOpen({ id: b.id, position })}
              onClose={() => setOpen((cur) => (cur?.id === b.id ? null : cur))}
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
              open={open?.id === b.id}
              onOpen={(position) => setOpen({ id: b.id, position })}
              onClose={() => setOpen((cur) => (cur?.id === b.id ? null : cur))}
            />
          ))}
        </div>
      )}
      {open &&
        (() => {
          const badge = allBadges.find((b) => b.id === open.id);
          return badge ? (
            <BadgeTooltip text={`${badge.label} ${badge.yearLabel ?? badge.year}`} position={open.position} />
          ) : null;
        })()}
    </div>
  );
}
