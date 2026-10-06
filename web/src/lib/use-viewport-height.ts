"use client";

import { useEffect, useState } from "react";

// SSR-safe: starts at 0 (matches use-media-query.ts's established "static/
// server-safe initial value, update once mounted" pattern in this
// codebase), then tracks the real window height live via a resize
// listener. Used by ChecklistGroup's adaptiveHeight mode (feature request,
// 2026-10-06) to cap a filter box's height at whichever is shorter: the
// window's own height, or the content's natural height.
export function useViewportHeight(): number {
  const [height, setHeight] = useState(0);

  useEffect(() => {
    function update() {
      setHeight(window.innerHeight);
    }
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);

  return height;
}
