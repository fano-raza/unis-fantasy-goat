"use client";

import { useEffect, useRef, useTransition } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { motion, animate, useMotionValue, useTransform } from "motion/react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { NAV_LINKS } from "@/components/nav";
import { useMobileMenu } from "@/components/mobile-menu-context";
import { LoadingBasketballs } from "@/components/loading-basketballs";

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
  // Tracks the actual page-load wait, entirely separate from the tab's own
  // slide -- feature request, 2026-10-06: the slide must always finish on
  // its own regardless of how long the destination page takes to load
  // (it already does -- see commitNext/commitPrev's animate().then()
  // ordering below), and a loading overlay over the still-visible old
  // page should fill the gap after that, not the slide itself stalling
  // mid-flight waiting on the network.
  const [isPending, startTransition] = useTransition();

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

  // Finishes sliding the current tab the rest of the way off-screen, THEN
  // (only once that's done) starts the actual navigation -- the slide
  // itself never waits on the network either way. `x` resets in the same
  // tick as the push call, not a later effect-driven render, so there's
  // no flash once the new page's label renders. startTransition's
  // isPending tracks the navigation separately, driving the loading
  // overlay below for however long the destination page takes.
  function commitNext() {
    animate(x, -DRAG_RANGE_PX, springTransition).then(() => {
      x.set(0);
      startTransition(() => {
        router.push(NAV_LINKS[nextIndex].href);
      });
    });
  }
  function commitPrev() {
    animate(x, DRAG_RANGE_PX, springTransition).then(() => {
      x.set(0);
      startTransition(() => {
        router.push(NAV_LINKS[prevIndex].href);
      });
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
    <>
      {/* items-end (not items-center) so the two side baselines -- each a
          flex-1 div stretching all the way to the screen edge, not just
          hugging its arrow icon -- align exactly with the tab's own
          bottom edge, closing the open-bottomed tab shape into a
          continuous line on either side (feature request, 2026-10-06).
          No gap between a baseline and the tab so the horizontal line
          visually touches the tab's vertical border rather than leaving
          a break at the corner. */}
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
        {/* z-10 so a shadow tab sliding in renders above the baseline/
            arrow row on either side while mid-transition. layout="position"
            because this wrapper's own width (and so its centered position
            between the two flex-1 arrow regions) depends on the current
            label's length -- without it, the moment the label swaps to a
            different-length one, the wrapper snaps to its new centered
            spot instantly, which (even with the shadow-anchor fix above
            landing it exactly on this wrapper's OLD position) still read
            as a jump, since the wrapper itself had already relocated out
            from under it (bug report, 2026-10-06). This smooths that
            residual reposition into a continuation of the same motion
            instead of a snap. */}
        <motion.div layout="position" className="relative z-10">
          {/* Anchored at the SAME box as the current tab below (left-0,
              not right-full) -- its transform must end (at full drag)
              exactly overlapping that box, which is where the real tab
              will sit once the data updates and `x` resets to 0. Anchoring
              it flush against the current tab's own edge instead (the
              original bug) meant it only ever travelled half the needed
              distance: it'd stop flush against the OLD tab's edge rather
              than reaching the OLD tab's full resting position, so the
              reset to the new label was a visible jump, not a
              continuation (bug report, 2026-10-06). */}
          <motion.div
            aria-hidden="true"
            style={{ x: prevShadowX, opacity: prevShadowOpacity }}
            className="pointer-events-none absolute top-0 left-0 rounded-t-md border border-b-0 border-border bg-background px-3 py-1.5 text-xs font-bold tracking-wide whitespace-nowrap text-foreground uppercase shadow-sm"
          >
            {NAV_LINKS[prevIndex].label}
          </motion.div>
          <motion.button
            type="button"
            drag="x"
            dragConstraints={{ left: -DRAG_RANGE_PX, right: DRAG_RANGE_PX }}
            dragElastic={0.1}
            // Without this, Motion's own built-in release-inertia
            // animation (based on release velocity) runs on the SAME
            // motion value at the same time as handleDragEnd's explicit
            // animate() call below -- the two fight over `x`, which is
            // exactly what read as the slide stuttering/stopping mid-way
            // (bug report, 2026-10-06). false makes handleDragEnd's
            // animate() the sole driver of post-release motion.
            dragMomentum={false}
            onDragStart={handleDragStart}
            onDragEnd={handleDragEnd}
            onTap={handleTap}
            style={{ x, opacity: currentOpacity, touchAction: "pan-y" }}
            aria-label="Open page menu"
            className="relative rounded-t-md border border-b-0 border-border bg-background px-3 py-1.5 text-xs font-bold tracking-wide whitespace-nowrap text-foreground uppercase shadow-sm transition-colors hover:bg-muted"
          >
            {NAV_LINKS[currentIndex].label}
          </motion.button>
          {/* Same anchoring fix as the prev shadow above, mirrored. */}
          <motion.div
            aria-hidden="true"
            style={{ x: nextShadowX, opacity: nextShadowOpacity }}
            className="pointer-events-none absolute top-0 left-0 rounded-t-md border border-b-0 border-border bg-background px-3 py-1.5 text-xs font-bold tracking-wide whitespace-nowrap text-foreground uppercase shadow-sm"
          >
            {NAV_LINKS[nextIndex].label}
          </motion.div>
        </motion.div>
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
      {/* Covers the still-visible old page (not the header/tab above it --
          z-30 sits below the header's own z-40) while the destination
          page loads, instead of leaving it looking frozen with no
          feedback -- feature request, 2026-10-06. bg-background/80
          matches the 20%-see-through convention used by LoadingOverlay
          elsewhere. */}
      {isPending && (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-background/80 sm:hidden">
          <LoadingBasketballs label="Loading" />
        </div>
      )}
    </>
  );
}
