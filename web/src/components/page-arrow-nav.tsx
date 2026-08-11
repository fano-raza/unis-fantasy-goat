"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { NAV_LINKS } from "@/components/nav";

// Mobile-only quick page switcher -- lets a user step to the previous/next
// page (wrapping around at either end, like a carousel) without opening the
// hamburger menu. Desktop already has the full pill nav always visible, so
// this is gated to the same `sm:hidden` breakpoint as MobileNav itself.
export function PageArrowNav() {
  const pathname = usePathname();
  const currentIndex = NAV_LINKS.findIndex((link) => link.href === pathname);
  // Unknown route (shouldn't normally happen) -- don't render rather than
  // guess a position.
  if (currentIndex === -1) return null;

  const prevIndex = (currentIndex - 1 + NAV_LINKS.length) % NAV_LINKS.length;
  const nextIndex = (currentIndex + 1) % NAV_LINKS.length;

  return (
    <div className="flex items-center justify-between gap-2 sm:hidden">
      <Link
        href={NAV_LINKS[prevIndex].href}
        aria-label={`Go to ${NAV_LINKS[prevIndex].label}`}
        className="flex items-center gap-1 rounded-sm px-2 py-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      >
        <ChevronLeft className="size-4" />
      </Link>
      <span className="text-xs font-bold tracking-wide text-foreground uppercase">
        {NAV_LINKS[currentIndex].label}
      </span>
      <Link
        href={NAV_LINKS[nextIndex].href}
        aria-label={`Go to ${NAV_LINKS[nextIndex].label}`}
        className="flex items-center gap-1 rounded-sm px-2 py-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      >
        <ChevronRight className="size-4" />
      </Link>
    </div>
  );
}
