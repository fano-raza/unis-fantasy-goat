"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";

export interface ArrowToggleOption {
  value: string;
  label: string;
}

// Cycles through a fixed set of views with chevron buttons on either side of
// the active label -- wraps in both directions. Used for Standings' 1v1 /
// League Wins / Ratings views and Profile's Profile / Comparison views.
export function ArrowToggle({
  options,
  value,
  onChange,
}: {
  options: ArrowToggleOption[];
  value: string;
  onChange: (value: string) => void;
}) {
  const index = options.findIndex((o) => o.value === value);
  const step = (delta: number) => {
    const next = (index + delta + options.length) % options.length;
    onChange(options[next].value);
  };

  return (
    <div className="flex items-center gap-1">
      <Button
        variant="ghost"
        size="icon-sm"
        onClick={() => step(-1)}
        aria-label="Previous view"
      >
        <ChevronLeft className="size-4" />
      </Button>
      <span className="min-w-28 text-center text-sm font-bold tracking-wide uppercase">
        {options[index]?.label}
      </span>
      <Button
        variant="ghost"
        size="icon-sm"
        onClick={() => step(1)}
        aria-label="Next view"
      >
        <ChevronRight className="size-4" />
      </Button>
    </div>
  );
}
