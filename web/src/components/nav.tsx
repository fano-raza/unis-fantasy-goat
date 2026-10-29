"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Lock } from "lucide-react";
import { cn } from "@/lib/utils";
import { PremiumNavButton } from "@/components/premium";

export const NAV_LINKS = [
  { href: "/weekly-stats", label: "Weekly Stats" },
  // Team's and Career's hrefs point at their first sub-page (bare /team
  // and /career have no view of their own -- next.config.ts redirects
  // them), but the whole /team/* or /career/* section should still
  // highlight the nav item -- activePrefix covers that, since it isn't
  // derivable from href alone here the way it is for Weekly Stats/
  // Standings (whose sub-pages live directly under their own href).
  { href: "/team/roster", label: "Team", activePrefix: "/team" },
  { href: "/standings", label: "Standings" },
  { href: "/career/profile", label: "Career", activePrefix: "/career" },
  { href: "/analysis", label: "Analysis" },
  { href: "/champions-lounge", label: "Champions Lounge", locked: true },
];

export function Nav() {
  const pathname = usePathname();
  return (
    <nav className="-mx-4 flex items-end gap-1 overflow-x-auto px-4 sm:mx-0 sm:px-0">
      {NAV_LINKS.map((link) => {
        // Also active on a sub-page route (e.g. /weekly-stats/ultra,
        // /standings/ratings) -- these split off from a single-URL page
        // into their own routes but should still highlight the same top
        // nav item as their parent. Prefix defaults to href itself
        // (Weekly Stats/Standings' sub-pages live directly under their own
        // href), but Team/Career override it via activePrefix since their
        // hrefs are themselves nested sub-pages (see NAV_LINKS above).
        const prefix = link.activePrefix ?? link.href;
        const active = pathname === link.href || pathname.startsWith(`${prefix}/`);
        return (
          <Link
            key={link.href}
            href={link.href}
            className={cn(
              // Folder-style tabs: the header strip is the card surface with no
              // bottom border, so the active tab (page-background fill, no
              // bottom edge) flows straight into the page below. Blue lip on top.
              "flex shrink-0 items-center gap-1.5 rounded-t-md px-4 py-2.5 text-sm font-medium transition-colors",
              active
                ? "bg-background font-semibold text-foreground shadow-[inset_0_3px_0_var(--primary)]"
                : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
            )}
          >
            {link.locked && <Lock className="size-3" />}
            {link.label}
          </Link>
        );
      })}
      {/* Rightmost tab, after Champions Lounge (user request, 2026-10-25). */}
      <PremiumNavButton variant="tab" />
    </nav>
  );
}
