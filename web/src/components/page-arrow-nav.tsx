"use client";

import { useRef, useState } from "react";
import type { TouchEvent } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { NAV_LINKS } from "@/components/nav";
import { useMobileMenu } from "@/components/mobile-menu-context";

// Horizontal distance (px) a touch has to travel before it counts as a
// swipe rather than a tap/scroll jitter.
const SWIPE_THRESHOLD_PX = 50;

// Mobile-only quick page switcher -- lets a user step to the previous/next
// page (wrapping around at either end, like a carousel) without opening the
// hamburger menu. Desktop already has the full pill nav always visible, so
// this is gated to the same `sm:hidden` breakpoint as MobileNav itself.
export function PageArrowNav() {
  const pathname = usePathname();
  const router = useRouter();
  const { setOpen } = useMobileMenu();
  const touchStartX = useRef<number | null>(null);
  // 1 = moving to the next page (old tab exits left, new one enters from
  // the right); -1 = previous (mirrored). Drives the slide direction below
  // -- feature request, 2026-10-06: make the tab itself visibly move with
  // a swipe/arrow change, a new tab sliding in from the trailing edge,
  // instead of the label just instantly swapping in place.
  const [direction, setDirection] = useState<1 | -1>(1);

  // Prefix-aware match, mirroring nav.tsx's activePrefix logic -- without
  // this, any sub-page route (/standings/ratings, /team/roster, /players/
  // draft, ...) fails an exact-href match and this whole bar (prev arrow,
  // page-name tab, next arrow) vanished entirely instead of staying on the
  // parent page's entry (feature request, 2026-10-06).
  const currentIndex = NAV_LINKS.findIndex((link) => {
    const prefix = link.activePrefix ?? link.href;
    return pathname === link.href || pathname.startsWith(`${prefix}/`);
  });
  // Unknown route (shouldn't normally happen) -- don't render rather than
  // guess a position.
  if (currentIndex === -1) return null;

  const prevIndex = (currentIndex - 1 + NAV_LINKS.length) % NAV_LINKS.length;
  const nextIndex = (currentIndex + 1) % NAV_LINKS.length;

  function handleTouchStart(e: TouchEvent<HTMLDivElement>) {
    touchStartX.current = e.touches[0].clientX;
  }

  function handleTouchEnd(e: TouchEvent<HTMLDivElement>) {
    const startX = touchStartX.current;
    touchStartX.current = null;
    if (startX === null) return;
    const deltaX = e.changedTouches[0].clientX - startX;
    if (Math.abs(deltaX) < SWIPE_THRESHOLD_PX) return;
    // A real swipe, not a tap -- suppress any click some browsers
    // synthesize from a touch sequence that ends on the tab button itself,
    // which would otherwise also pop the page menu open alongside the
    // navigation this triggers below.
    e.preventDefault();
    // Swipe left -> next page (same direction as the right arrow); swipe
    // right -> previous page -- mirrors a horizontally-scrolling carousel.
    setDirection(deltaX < 0 ? 1 : -1);
    router.push(deltaX < 0 ? NAV_LINKS[nextIndex].href : NAV_LINKS[prevIndex].href);
  }

  return (
    // items-end (not items-center) so the two side baselines -- each a
    // flex-1 div stretching all the way to the screen edge, not just
    // hugging its arrow icon -- align exactly with the tab's own bottom
    // edge, closing the open-bottomed tab shape into a continuous line
    // on either side (feature request, 2026-10-06). No gap between a
    // baseline and the tab so the horizontal line visually touches the
    // tab's vertical border rather than leaving a break at the corner.
    <div
      className="flex items-end sm:hidden"
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
    >
      <div className="flex flex-1 items-center border-b border-border">
        <Link
          href={NAV_LINKS[prevIndex].href}
          aria-label={`Go to ${NAV_LINKS[prevIndex].label}`}
          onClick={() => setDirection(-1)}
          className="flex items-center gap-1 rounded-sm px-2 py-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <ChevronLeft className="size-4" />
        </Link>
      </div>
      {/* overflow-hidden clips the sliding tab to this box; mode="popLayout"
          takes the exiting label out of flow (absolute, pinned to its last
          position) so the box can immediately resize to the entering
          label's own width while the old one slides out on top of it. */}
      <div className="relative overflow-hidden rounded-t-md border border-b-0 border-border bg-background shadow-sm">
        <AnimatePresence mode="popLayout" initial={false}>
          <motion.button
            key={NAV_LINKS[currentIndex].href}
            type="button"
            onClick={() => setOpen(true)}
            aria-label="Open page menu"
            initial={{ x: direction === 1 ? "100%" : "-100%" }}
            animate={{ x: 0 }}
            exit={{ x: direction === 1 ? "-100%" : "100%" }}
            transition={{ type: "spring", stiffness: 420, damping: 38 }}
            className="block px-3 py-1.5 text-xs font-bold tracking-wide text-foreground uppercase transition-colors hover:bg-muted"
          >
            {NAV_LINKS[currentIndex].label}
          </motion.button>
        </AnimatePresence>
      </div>
      <div className="flex flex-1 items-center justify-end border-b border-border">
        <Link
          href={NAV_LINKS[nextIndex].href}
          aria-label={`Go to ${NAV_LINKS[nextIndex].label}`}
          onClick={() => setDirection(1)}
          className="flex items-center gap-1 rounded-sm px-2 py-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <ChevronRight className="size-4" />
        </Link>
      </div>
    </div>
  );
}
