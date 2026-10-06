"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";

export interface ChecklistGroupProps<T extends string | number> {
  label: string;
  options: T[];
  selected: T[];
  onChange: (next: T[]) => void;
  scrollable?: boolean;
}

export function ChecklistGroup<T extends string | number>({
  label,
  options,
  selected,
  onChange,
  scrollable,
}: ChecklistGroupProps<T>) {
  const [open, setOpen] = useState(true);
  const selectedSet = new Set(selected);

  function toggle(value: T) {
    onChange(
      selectedSet.has(value)
        ? selected.filter((v) => v !== value)
        : [...selected, value],
    );
  }

  return (
    // No width class here deliberately (feature request, 2026-10-06) -- this
    // box's width comes from the caller's wrapper being sized to fit-content
    // (see e.g. ultra-view.tsx), with this div's default flex-stretch filling
    // that resolved width. That's what makes every box on a given page end
    // up the SAME width: the page wrapper's fit-content computation already
    // takes the max over every sibling box's natural content width, so the
    // narrower boxes stretch up to match the page's widest one instead of
    // each shrink-wrapping independently.
    <div className="rounded-sm border border-border p-3">
      {/* All/None on their own line below the label, each a bordered/filled
          button (not plain ghost text) so they read as pressable controls.
          whitespace-nowrap here and below keeps the natural-width
          measurement honest (no accidental wraps shrinking it). */}
      <div className="flex flex-col gap-2 border-b border-border pb-2">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="self-start text-[11px] font-bold tracking-wider text-muted-foreground uppercase whitespace-nowrap"
        >
          {label}
        </button>
        <div className="flex gap-1.5">
          <Button
            variant="outline"
            size="xs"
            className="bg-muted whitespace-nowrap"
            onClick={() => onChange(options)}
          >
            All
          </Button>
          <Button
            variant="outline"
            size="xs"
            className="bg-muted whitespace-nowrap"
            onClick={() => onChange([])}
          >
            None
          </Button>
        </div>
      </div>
      {open && (
        <div
          className={cn(
            "mt-2 flex flex-col gap-1.5",
            scrollable && "max-h-48 overflow-y-auto",
          )}
        >
          {options.map((option) => (
            <label
              key={option}
              className="flex items-center gap-2 text-sm whitespace-nowrap"
            >
              <Checkbox
                checked={selectedSet.has(option)}
                onCheckedChange={() => toggle(option)}
              />
              {option}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

export interface FilterPanelValue {
  years: number[];
  weeks: number[];
  teams: string[];
  rs: boolean;
  po: boolean;
}

interface FilterPanelProps {
  allYears: number[];
  allWeeks: number[];
  allTeams: string[];
  value: FilterPanelValue;
  onChange: (value: FilterPanelValue) => void;
}

export function FilterPanel({
  allYears,
  allWeeks,
  allTeams,
  value,
  onChange,
}: FilterPanelProps) {
  return (
    <div className="flex flex-col gap-3">
      <ChecklistGroup
        label="Season"
        options={allYears}
        selected={value.years}
        onChange={(years) => onChange({ ...value, years })}
      />
      <ChecklistGroup
        label="Team"
        options={allTeams}
        selected={value.teams}
        onChange={(teams) => onChange({ ...value, teams })}
        scrollable
      />
      <ChecklistGroup
        label="Week"
        options={allWeeks}
        selected={value.weeks}
        onChange={(weeks) => onChange({ ...value, weeks })}
        scrollable
      />
      <div className="rounded-sm border border-border p-3">
        <div className="mb-2 border-b border-border pb-2 text-[11px] font-bold tracking-wider text-muted-foreground uppercase whitespace-nowrap">
          Season Type
        </div>
        <div className="flex flex-col gap-1.5">
          <label className="flex items-center gap-2 text-sm whitespace-nowrap">
            <Checkbox
              checked={value.rs}
              onCheckedChange={() => onChange({ ...value, rs: !value.rs })}
            />
            Regular Season
          </label>
          <label className="flex items-center gap-2 text-sm whitespace-nowrap">
            <Checkbox
              checked={value.po}
              onCheckedChange={() => onChange({ ...value, po: !value.po })}
            />
            Playoffs
          </label>
        </div>
      </div>
    </div>
  );
}
