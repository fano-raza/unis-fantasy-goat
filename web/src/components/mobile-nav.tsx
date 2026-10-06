"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";
import { ChevronDown, Lock, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogPortal } from "@/components/ui/dialog";
import { NAV_LINKS } from "@/components/nav";
import { useMobileMenu } from "@/components/mobile-menu-context";
import { STANDINGS_VIEW_OPTIONS, STANDINGS_VIEW_PATHS } from "@/lib/standings-nav";
import { TEAM_PLAYERS_VIEW_OPTIONS, TEAM_PLAYERS_VIEW_PATHS } from "@/lib/team-players-nav";

interface SubPage {
  label: string;
  href: string;
}

function subPagesFor(values: string[], options: typeof TEAM_PLAYERS_VIEW_OPTIONS, paths: Record<string, string>): SubPage[] {
  return values.map((value) => ({
    label: options.find((o) => o.value === value)!.label,
    href: paths[value],
  }));
}

// Which top-level NAV_LINKS entries have sub-pages, and which of the
// shared option lists' entries belong under each one (feature request,
// 2026-10-06). Team shows its 4 Team-ish pages, Players its 3 Players-ish
// ones -- not all 5 shared ones under both -- since this is a quick-access
// menu grouped by what a user would expect under each label, not the
// RoutedViewSwitcher's unified cycling order (a different concern, fixed
// separately -- see team-players-nav.ts).
const SUB_PAGES: Record<string, SubPage[]> = {
  "/standings": subPagesFor(["1v1", "league_wins", "ratings"], STANDINGS_VIEW_OPTIONS, STANDINGS_VIEW_PATHS),
  "/team/profile": subPagesFor(
    ["profile", "comparison", "roster", "trade"],
    TEAM_PLAYERS_VIEW_OPTIONS,
    TEAM_PLAYERS_VIEW_PATHS,
  ),
  "/players": subPagesFor(["draft", "trade", "roster"], TEAM_PLAYERS_VIEW_OPTIONS, TEAM_PLAYERS_VIEW_PATHS),
};

// Mobile-only slide-in drawer, standing in for the desktop top pill nav
// below the `sm` breakpoint. Reuses Dialog's Root/Portal/Close but builds
// its own Backdrop/Popup rather than the shared DialogContent, which is
// hardcoded to a centered modal, not a left-edge panel.
//
// open/setOpen come from MobileMenuProvider, not local state, and there's
// no DialogTrigger here -- opening is entirely driven by FloatingMenuButton
// and PageArrowNav's page-name "tab" (feature request, 2026-10-06: the
// inline hamburger-in-header trigger was replaced by the floating button
// rather than kept alongside it).
export function MobileNav() {
  const pathname = usePathname();
  const { open, setOpen } = useMobileMenu();
  const [expanded, setExpanded] = useState<string | null>(null);

  // Whenever the drawer opens (or the route changes while it's open),
  // default the expansion to whichever parent you're currently under --
  // feature request, 2026-10-06: sub-pages should be visible/selectable
  // under their parent, and that's most useful shown automatically for the
  // page you're already on, not only after an extra tap to discover it.
  useEffect(() => {
    if (!open) return;
    const activeParent = Object.keys(SUB_PAGES).find((href) => {
      const link = NAV_LINKS.find((l) => l.href === href);
      const prefix = link?.activePrefix ?? href;
      return pathname === href || pathname.startsWith(`${prefix}/`);
    });
    setExpanded(activeParent ?? null);
  }, [open, pathname]);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogPortal>
        <DialogPrimitive.Backdrop className="fixed inset-0 z-50 bg-black/40 duration-150 data-open:animate-in data-open:fade-in-0 data-closed:animate-out data-closed:fade-out-0" />
        <DialogPrimitive.Popup
          className="fixed inset-y-0 left-0 z-50 flex h-full w-64 max-w-[80vw] flex-col gap-1 border-r border-border bg-popover p-4 outline-none duration-200 data-open:animate-in data-open:slide-in-from-left data-closed:animate-out data-closed:slide-out-to-left"
        >
          <div className="mb-4 flex items-center justify-between">
            <span className="text-lg font-black tracking-tight italic">
              UNIS 2014 <span className="text-primary">FANTASY</span>
            </span>
            <DialogClose
              render={<Button variant="ghost" size="icon-sm" aria-label="Close menu" />}
            >
              <X className="size-4" />
            </DialogClose>
          </div>
          {NAV_LINKS.map((link) => {
            // Also active on a sub-page route (e.g. /team/roster,
            // /standings/ratings) -- see the matching comment in nav.tsx.
            const prefix = link.activePrefix ?? link.href;
            const active = pathname === link.href || pathname.startsWith(`${prefix}/`);
            const subPages = SUB_PAGES[link.href];

            if (!subPages) {
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  onClick={() => setOpen(false)}
                  className={cn(
                    "flex items-center gap-1.5 rounded-sm px-3 py-2.5 text-sm font-bold tracking-wide uppercase transition-colors",
                    active
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground",
                  )}
                >
                  {link.locked && <Lock className="size-3.5" />}
                  {link.label}
                </Link>
              );
            }

            const isExpanded = expanded === link.href;
            return (
              <div key={link.href}>
                <button
                  type="button"
                  onClick={() => setExpanded(isExpanded ? null : link.href)}
                  aria-expanded={isExpanded}
                  className={cn(
                    "flex w-full items-center justify-between gap-1.5 rounded-sm px-3 py-2.5 text-sm font-bold tracking-wide uppercase transition-colors",
                    active
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground",
                  )}
                >
                  <span className="flex items-center gap-1.5">
                    {link.locked && <Lock className="size-3.5" />}
                    {link.label}
                  </span>
                  <ChevronDown className={cn("size-4 transition-transform", isExpanded && "rotate-180")} />
                </button>
                {isExpanded && (
                  <div className="mt-1 ml-3 flex flex-col gap-1 border-l border-border pl-3">
                    {subPages.map((sub) => {
                      const subActive = pathname === sub.href;
                      return (
                        <Link
                          key={sub.href}
                          href={sub.href}
                          onClick={() => setOpen(false)}
                          className={cn(
                            "rounded-sm px-3 py-2 text-sm font-bold tracking-wide uppercase transition-colors",
                            subActive
                              ? "bg-primary text-primary-foreground"
                              : "text-muted-foreground hover:bg-muted hover:text-foreground",
                          )}
                        >
                          {sub.label}
                        </Link>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </DialogPrimitive.Popup>
      </DialogPortal>
    </Dialog>
  );
}
