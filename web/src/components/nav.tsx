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
  { href: "/profile", label: "Team" },
  { href: "/analysis", label: "Analysis" },
  { href: "/players", label: "Players" },
  { href: "/champions-lounge", label: "Champions Lounge", locked: true },
];

export function Nav() {
  const pathname = usePathname();
  return (
    <nav className="-mx-4 flex gap-1 overflow-x-auto px-4 pb-1 sm:mx-0 sm:px-0">
      {NAV_LINKS.map((link) => {
        // Also active on a sub-page route (e.g. /profile/roster,
        // /standings/ratings) -- these split off from a single-URL page
        // into their own routes but should still highlight the same top
        // nav item as their parent. link.href === "/" never falls into
        // this branch (pathname.startsWith("//") is never true for a real
        // path), so Weekly Stats doesn't wrongly match every route.
        const active = pathname === link.href || pathname.startsWith(`${link.href}/`);
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
