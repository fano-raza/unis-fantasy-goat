"use client";

import { createContext, useContext, useState, type ReactNode } from "react";

// Shared open/close state for the mobile hamburger drawer (MobileNav), so
// PageArrowNav's page-name "tab" can also trigger it -- the two live in
// separate rows of the header (see layout.tsx), so a plain prop can't
// connect them; this Provider wraps both.
type MobileMenuState = { open: boolean; setOpen: (open: boolean) => void };

const MobileMenuContext = createContext<MobileMenuState | null>(null);

export function MobileMenuProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <MobileMenuContext.Provider value={{ open, setOpen }}>
      {children}
    </MobileMenuContext.Provider>
  );
}

export function useMobileMenu(): MobileMenuState {
  const ctx = useContext(MobileMenuContext);
  if (!ctx) throw new Error("useMobileMenu must be used within MobileMenuProvider");
  return ctx;
}
