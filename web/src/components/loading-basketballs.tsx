"use client";

import { useEffect, useState } from "react";
import { LOADING_PHRASES } from "@/lib/loading-phrases";

const PHRASE_INTERVAL_MS = 2500;

// Reusable loading state: three basketballs bouncing in sequence, like a
// loading bar filling one ball at a time. Used anywhere a page previously
// rendered nothing at all while waiting on its first fetch (meta, initial
// data, etc.) -- that blank gap read as "the page is broken" on the
// droplet's slower/more variable response times, not just "still loading."
//
// Visible text rotates through LOADING_PHRASES every 2.5s (feature
// request, 2026-10-06) instead of a static "Loading X" string -- `label`
// is kept as the stable accessible name (role="status" aria-label) so
// screen readers announce once rather than fighting the rotation.
//
// SSR-safe two-phase init (same pattern as web/src/lib/use-media-query.ts):
// index starts at a fixed 0 so server and client's first render match,
// then an effect randomizes the start and begins rotating -- avoids a
// hydration mismatch from Math.random() running during SSR.
export function LoadingBasketballs({ label }: { label?: string }) {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    setIndex(Math.floor(Math.random() * LOADING_PHRASES.length));
    const id = setInterval(() => {
      setIndex((i) => (i + 1) % LOADING_PHRASES.length);
    }, PHRASE_INTERVAL_MS);
    return () => clearInterval(id);
  }, []);

  return (
    <div
      role="status"
      aria-label={label ?? "Loading"}
      className="flex flex-col items-center justify-center gap-3 py-16"
    >
      <div className="flex items-center gap-2">
        <span className="loading-basketball text-3xl" style={{ animationDelay: "0s" }}>
          🏀
        </span>
        <span className="loading-basketball text-3xl" style={{ animationDelay: "0.2s" }}>
          🏀
        </span>
        <span className="loading-basketball text-3xl" style={{ animationDelay: "0.4s" }}>
          🏀
        </span>
      </div>
      <p
        aria-hidden="true"
        className="text-[11px] font-bold tracking-wider text-muted-foreground uppercase"
      >
        {LOADING_PHRASES[index]}
      </p>
      <style>{`
        .loading-basketball {
          display: inline-block;
          opacity: 0.25;
          animation: loading-basketball-bounce 1.2s ease-in-out infinite;
        }
        @keyframes loading-basketball-bounce {
          0%, 80%, 100% { opacity: 0.25; transform: translateY(0) scale(0.85); }
          40% { opacity: 1; transform: translateY(-8px) scale(1); }
        }
      `}</style>
    </div>
  );
}
