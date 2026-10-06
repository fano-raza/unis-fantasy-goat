"use client";

import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { Menu } from "lucide-react";
import { useMobileMenu } from "@/components/mobile-menu-context";

// Mobile-only menu trigger (feature request, 2026-10-06): a floating button
// pinned to the left edge, draggable in Y only, that stays wherever it's
// placed (persisted across visits) until dragged again. Replaces the old
// inline hamburger-in-header trigger entirely -- see mobile-nav.tsx.
const STORAGE_KEY = "floating-menu-button-top";
// 80% of the original 44px (feature request, 2026-10-06).
const BUTTON_SIZE_PX = 35;
const EDGE_MARGIN_PX = 8;
// Pointer movement (px) below which a press counts as a tap (open the menu)
// rather than a drag (reposition) -- real drags on touch easily clear this.
const TAP_MOVE_THRESHOLD_PX = 6;

function clampTop(top: number): number {
  if (typeof window === "undefined") return top;
  const max = Math.max(EDGE_MARGIN_PX, window.innerHeight - BUTTON_SIZE_PX - EDGE_MARGIN_PX);
  return Math.min(Math.max(top, EDGE_MARGIN_PX), max);
}

export function FloatingMenuButton() {
  const { setOpen } = useMobileMenu();
  const [top, setTop] = useState<number | null>(null);
  const draggingRef = useRef(false);
  const startClientYRef = useRef(0);
  const startTopRef = useRef(0);
  const maxMovedRef = useRef(0);

  useEffect(() => {
    const stored = Number(window.localStorage.getItem(STORAGE_KEY));
    const initial = Number.isFinite(stored) && stored > 0 ? stored : window.innerHeight * 0.5;
    setTop(clampTop(initial));
  }, []);

  // Re-clamp on rotation/resize so it can never end up stranded off-screen.
  useEffect(() => {
    function handleResize() {
      setTop((current) => (current === null ? current : clampTop(current)));
    }
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  function handlePointerDown(e: ReactPointerEvent<HTMLButtonElement>) {
    draggingRef.current = true;
    maxMovedRef.current = 0;
    startClientYRef.current = e.clientY;
    startTopRef.current = top ?? clampTop(window.innerHeight * 0.5);
    e.currentTarget.setPointerCapture(e.pointerId);
  }

  function handlePointerMove(e: ReactPointerEvent<HTMLButtonElement>) {
    if (!draggingRef.current) return;
    const deltaY = e.clientY - startClientYRef.current;
    maxMovedRef.current = Math.max(maxMovedRef.current, Math.abs(deltaY));
    setTop(clampTop(startTopRef.current + deltaY));
  }

  function handlePointerUp(e: ReactPointerEvent<HTMLButtonElement>) {
    if (!draggingRef.current) return;
    draggingRef.current = false;
    e.currentTarget.releasePointerCapture(e.pointerId);
    if (maxMovedRef.current < TAP_MOVE_THRESHOLD_PX) {
      setOpen(true);
      return;
    }
    setTop((current) => {
      const resolved = current ?? clampTop(window.innerHeight * 0.5);
      window.localStorage.setItem(STORAGE_KEY, String(resolved));
      return resolved;
    });
  }

  // Avoids a flash at the default position before the persisted Y loads.
  if (top === null) return null;

  return (
    <button
      type="button"
      aria-label="Open menu"
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerUp}
      style={{ top }}
      // Square w/ rounded corners (not a circle), 75% transparent overall
      // (opacity-25, so the page behind it stays visible), sized to 80% of
      // the original button -- all per feature request, 2026-10-06.
      className="fixed left-2 z-40 flex size-[35px] touch-none items-center justify-center rounded-xl border-2 border-primary bg-primary/10 text-primary opacity-25 shadow-md backdrop-blur-sm sm:hidden"
    >
      <Menu className="size-4" />
    </button>
  );
}
