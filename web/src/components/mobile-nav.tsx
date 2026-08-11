"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";
import { Lock, Menu, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogPortal, DialogTrigger } from "@/components/ui/dialog";
import { NAV_LINKS } from "@/components/nav";

// Mobile-only slide-in drawer, standing in for the desktop top pill nav
// below the `sm` breakpoint. Reuses Dialog's Root/Trigger/Portal/Close but
// builds its own Backdrop/Popup rather than the shared DialogContent, which
// is hardcoded to a centered modal, not a left-edge panel.
export function MobileNav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Open menu"
            className="rounded-sm border-2 border-primary bg-primary/10"
          />
        }
      >
        <Menu className="size-5 text-primary" />
      </DialogTrigger>
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
            const active = pathname === link.href;
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
          })}
        </DialogPrimitive.Popup>
      </DialogPortal>
    </Dialog>
  );
}
