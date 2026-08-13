"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Lock } from "lucide-react";
import { cn } from "@/lib/utils";

export const NAV_LINKS = [
  { href: "/", label: "Weekly Stats" },
  { href: "/ultra", label: "Ultra" },
  { href: "/career", label: "Career Stats" },
  { href: "/standings", label: "Standings" },
  // Team's href points at the Profile sub-page specifically (not a bare
  // /team, which has no view of its own -- see app/team/page.tsx's
  // redirect), but the whole /team/* section (comparison, roster too)
  // should still highlight this nav item -- activePrefix covers that,
  // since it isn't derivable from href alone here the way it is for
  // Standings/Players (whose sub-pages live directly under their own href).
  { href: "/team/profile", label: "Team", activePrefix: "/team" },
  { href: "/analysis", label: "Analysis" },
  { href: "/players", label: "Players" },
  { href: "/champions-lounge", label: "Champions Lounge", locked: true },
];

export function Nav() {
  const pathname = usePathname();
  return (
    <nav className="-mx-4 flex gap-1 overflow-x-auto px-4 pb-1 sm:mx-0 sm:px-0">
      {NAV_LINKS.map((link) => {
        // Also active on a sub-page route (e.g. /team/roster,
        // /standings/ratings) -- these split off from a single-URL page
        // into their own routes but should still highlight the same top
        // nav item as their parent. Prefix defaults to href itself
        // (Standings/Players' sub-pages live directly under their own
        // href), but Team overrides it via activePrefix since its href is
        // itself a nested sub-page (see NAV_LINKS above). prefix === "/"
        // never falls into the startsWith branch (pathname.startsWith("//")
        // is never true for a real path), so Weekly Stats doesn't wrongly
        // match every route.
        const prefix = link.activePrefix ?? link.href;
        const active = pathname === link.href || pathname.startsWith(`${prefix}/`);
        return (
          <Link
            key={link.href}
            href={link.href}
            className={cn(
              "flex shrink-0 items-center gap-1.5 rounded-sm px-3 py-1.5 text-xs font-bold tracking-wide uppercase transition-colors",
              active
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            {link.locked && <Lock className="size-3" />}
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
