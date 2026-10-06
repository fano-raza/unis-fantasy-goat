"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { motion, animate, useMotionValue, useTransform } from "motion/react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { NAV_LINKS } from "@/components/nav";
import { useMobileMenu } from "@/components/mobile-menu-context";

// Distance (px) the tab travels for a live drag's crossfade with its
// neighbor to be fully complete, and the commit threshold (half that) for
// whether releasing mid-drag finishes the change or springs back to
// center. Also the distance an arrow-click animates through, so both
// trigger the identical visual (feature request, 2026-10-06: make the tab
// itself -- the whole shape, not just its label -- visibly slide and
// gradually disappear the further it's dragged, with the neighboring
// page's tab gradually appearing from the side being revealed).
const DRAG_RANGE_PX = 80;

const springTransition = { type: "spring" as const, stiffness: 500, damping: 40 };

// Mobile-only quick page switcher -- lets a user step to the previous/next
// page (wrapping around at either end, like a carousel) without opening the
// hamburger menu. Desktop already has the full pill nav always visible, so
// this is gated to the same `sm:hidden` breakpoint as MobileNav itself.
export function PageArrowNav() {
  const pathname = usePathname();
  const router = useRouter();
  const { setOpen } = useMobileMenu();
  // Live horizontal offset of the current tab -- driven either by a real
  // drag (via the `drag="x"` prop below) or programmatically by an arrow
  // click (animate() to the edge, then commit). The two shadow tabs on
  // either side derive their own position/opacity from this SAME value,
  // so they move in lockstep with whatever's dragging/animating the
  // current one -- a single live transform, not separately keyed/mounted
  // elements.
  const x = useMotionValue(0);
  // True for the rest of this gesture once onDragStart has actually fired
  // (which Motion itself only does past its own small movement threshold,
  // so this is a real drag, not a tap) -- checked by the tap handler
  // below to suppress opening the page menu after a drag release, since a
  // plain onClick/onTap can still fire there even though Motion's own
  // drag-vs-tap distinction didn't reliably suppress it on its own
  // (confirmed via a real drag-release test still opening the menu).
  const didDragRef = useRef(false);

  // Prefix-aware match, mirroring nav.tsx's activePrefix logic -- without
  // this, any sub-page route (/standings/ratings, /team/roster, /players/
  // draft, ...) fails an exact-href match and this whole bar (prev arrow,
  // page-name tab, next arrow) vanished entirely instead of staying on the
  // parent page's entry (feature request, 2026-10-06).
  const currentIndex = NAV_LINKS.findIndex((link) => {
    const prefix = link.activePrefix ?? link.href;
    return pathname === link.href || pathname.startsWith(`${prefix}/`);
  });

  // Snap back to center the moment the route actually lands on a new page,
  // however it got there (a completed drag/arrow-click already resets `x`
  // itself before navigating -- see commitNext/commitPrev below -- this is
  // the catch-all for any other trigger, e.g. the hamburger menu).
  useEffect(() => {
    x.set(0);
  }, [pathname, x]);

  // Current tab fades out the further it's dragged/animated either way.
  const currentOpacity = useTransform(x, [-DRAG_RANGE_PX, 0, DRAG_RANGE_PX], [0, 1, 0]);
  // Next-page shadow (revealed while dragging/animating toward negative x):
  // slides from just past the right edge into place, fading in to match.
  const nextShadowX = useTransform(x, [-DRAG_RANGE_PX, 0], [0, DRAG_RANGE_PX]);
  const nextShadowOpacity = useTransform(x, [-DRAG_RANGE_PX, 0], [1, 0]);
  // Prev-page shadow, mirrored on the left.
  const prevShadowX = useTransform(x, [0, DRAG_RANGE_PX], [-DRAG_RANGE_PX, 0]);
  const prevShadowOpacity = useTransform(x, [0, DRAG_RANGE_PX], [0, 1]);

  // Unknown route (shouldn't normally happen) -- don't render rather than
  // guess a position.
  if (currentIndex === -1) return null;

  const prevIndex = (currentIndex - 1 + NAV_LINKS.length) % NAV_LINKS.length;
  const nextIndex = (currentIndex + 1) % NAV_LINKS.length;

  // Finishes sliding the current tab the rest of the way off-screen, then
  // commits the navigation and resets `x` -- by the time the new page's
  // label renders, it's already fully centered (0) and opaque (1), so
  // there's no flash: the reset happens in the same tick as the
  // navigation call, not on a later effect-driven render.
  function commitNext() {
    animate(x, -DRAG_RANGE_PX, springTransition).then(() => {
      router.push(NAV_LINKS[nextIndex].href);
      x.set(0);
    });
  }
  function commitPrev() {
    animate(x, DRAG_RANGE_PX, springTransition).then(() => {
      router.push(NAV_LINKS[prevIndex].href);
      x.set(0);
    });
  }

  function handleDragStart() {
    didDragRef.current = true;
  }

  function handleDragEnd(_event: unknown, info: { offset: { x: number } }) {
    if (info.offset.x <= -DRAG_RANGE_PX / 2) {
      commitNext();
    } else if (info.offset.x >= DRAG_RANGE_PX / 2) {
      commitPrev();
    } else {
      animate(x, 0, springTransition);
    }
  }

  function handleTap() {
    if (didDragRef.current) {
      didDragRef.current = false;
      return;
    }
    setOpen(true);
  }

  return (
    // items-end (not items-center) so the two side baselines -- each a
    // flex-1 div stretching all the way to the screen edge, not just
    // hugging its arrow icon -- align exactly with the tab's own bottom
    // edge, closing the open-bottomed tab shape into a continuous line
    // on either side (feature request, 2026-10-06). No gap between a
    // baseline and the tab so the horizontal line visually touches the
    // tab's vertical border rather than leaving a break at the corner.
    <div className="flex items-end sm:hidden">
      <div className="flex flex-1 items-center border-b border-border">
        <Link
          href={NAV_LINKS[prevIndex].href}
          aria-label={`Go to ${NAV_LINKS[prevIndex].label}`}
          onClick={(e) => {
            e.preventDefault();
            commitPrev();
          }}
          className="flex items-center gap-1 rounded-sm px-2 py-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <ChevronLeft className="size-4" />
        </Link>
      </div>
      {/* z-10 so a shadow tab sliding in renders above the baseline/arrow
          row on either side while mid-transition. */}
      <div className="relative z-10">
        <motion.div
          aria-hidden="true"
          style={{ x: prevShadowX, opacity: prevShadowOpacity }}
          className="pointer-events-none absolute top-0 right-full rounded-t-md border border-b-0 border-border bg-background px-3 py-1.5 text-xs font-bold tracking-wide whitespace-nowrap text-foreground uppercase shadow-sm"
        >
          {NAV_LINKS[prevIndex].label}
        </motion.div>
        <motion.button
          type="button"
          drag="x"
          dragConstraints={{ left: -DRAG_RANGE_PX, right: DRAG_RANGE_PX }}
          dragElastic={0.1}
          onDragStart={handleDragStart}
          onDragEnd={handleDragEnd}
          onTap={handleTap}
          style={{ x, opacity: currentOpacity, touchAction: "pan-y" }}
          aria-label="Open page menu"
          className="relative rounded-t-md border border-b-0 border-border bg-background px-3 py-1.5 text-xs font-bold tracking-wide whitespace-nowrap text-foreground uppercase shadow-sm transition-colors hover:bg-muted"
        >
          {NAV_LINKS[currentIndex].label}
        </motion.button>
        <motion.div
          aria-hidden="true"
          style={{ x: nextShadowX, opacity: nextShadowOpacity }}
          className="pointer-events-none absolute top-0 left-full rounded-t-md border border-b-0 border-border bg-background px-3 py-1.5 text-xs font-bold tracking-wide whitespace-nowrap text-foreground uppercase shadow-sm"
        >
          {NAV_LINKS[nextIndex].label}
        </motion.div>
      </div>
      <div className="flex flex-1 items-center justify-end border-b border-border">
        <Link
          href={NAV_LINKS[nextIndex].href}
          aria-label={`Go to ${NAV_LINKS[nextIndex].label}`}
          onClick={(e) => {
            e.preventDefault();
            commitNext();
          }}
          className="flex items-center gap-1 rounded-sm px-2 py-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <ChevronRight className="size-4" />
        </Link>
      </div>
    </div>
  );
}
