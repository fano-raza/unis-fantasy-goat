"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { LabeledSelect } from "@/components/labeled-select";

// Steps to the previous/next value in an ordered option list, clamped at
// either end (no wraparound).
export function step<T>(options: T[], current: T, delta: 1 | -1): T {
  const idx = options.indexOf(current);
  if (idx === -1) return current;
  const next = idx + delta;
  return next >= 0 && next < options.length ? options[next] : current;
}

export function StepButton({
  direction,
  onClick,
  disabled,
  label,
}: {
  direction: "prev" | "next";
  onClick: () => void;
  disabled: boolean;
  label: string;
}) {
  const Icon = direction === "prev" ? ChevronLeft : ChevronRight;
  return (
    <Button
      variant="secondary"
      size="icon-sm"
      disabled={disabled}
      onClick={onClick}
      aria-label={label}
    >
      <Icon className="size-4" />
    </Button>
  );
}

// A LabeledSelect for a numeric option list (years/weeks) with prev/next
// step arrows on either side -- extracted from Weekly Stats (the first page
// to need this) so every other year/week dropdown in the app can share it
// instead of re-implementing the same stepping logic.
export function SteppableSelect({
  label,
  value,
  onValueChange,
  options,
}: {
  label: string;
  value: number;
  onValueChange: (value: number) => void;
  options: number[];
}) {
  const idx = options.indexOf(value);
  return (
    <div className="flex items-center gap-1">
      <LabeledSelect
        label={label}
        value={String(value)}
        onValueChange={(v) => onValueChange(Number(v))}
        options={options.map((o) => ({ value: String(o), label: String(o) }))}
      />
      <StepButton
        direction="prev"
        label={`Previous ${label.toLowerCase()}`}
        disabled={idx <= 0}
        onClick={() => onValueChange(step(options, value, -1))}
      />
      <StepButton
        direction="next"
        label={`Next ${label.toLowerCase()}`}
        disabled={idx === -1 || idx >= options.length - 1}
        onClick={() => onValueChange(step(options, value, 1))}
      />
    </div>
  );
}
