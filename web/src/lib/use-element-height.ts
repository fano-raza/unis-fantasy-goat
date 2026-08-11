"use client";

import { useEffect, useRef, useState, type RefObject } from "react";

// Measures an element's actual rendered height via ResizeObserver, for
// positioning a second sticky element (e.g. a table header) directly below
// it -- a hardcoded pixel offset is the wrong tool here, same reasoning as
// StatTable's sticky Score column (see its TEAM_COL_WIDTH comment): the
// element's real height can differ from what a className implies (padding,
// wrapping, responsive text size), and drifting out of sync leaves a gap
// that lets scrolled content show through.
export function useElementHeight<T extends HTMLElement>(): [RefObject<T | null>, number] {
  const ref = useRef<T | null>(null);
  const [height, setHeight] = useState(0);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => setHeight(el.getBoundingClientRect().height);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return [ref, height];
}
