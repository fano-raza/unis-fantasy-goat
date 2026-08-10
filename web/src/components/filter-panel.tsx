"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";

interface ChecklistGroupProps<T extends string | number> {
  label: string;
  options: T[];
  selected: T[];
  onChange: (next: T[]) => void;
  scrollable?: boolean;
}

function ChecklistGroup<T extends string | number>({
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
    <div className="rounded-sm border border-border p-3">
      <div className="flex items-center justify-between gap-2 border-b border-border pb-2">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="text-[11px] font-bold tracking-wider text-muted-foreground uppercase"
        >
          {label}
        </button>
        <div className="flex gap-1">
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-xs"
            onClick={() => onChange(options)}
          >
            All
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-xs"
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
              className="flex items-center gap-2 text-sm"
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
        <div className="mb-2 border-b border-border pb-2 text-[11px] font-bold tracking-wider text-muted-foreground uppercase">
          Season Type
        </div>
        <div className="flex flex-col gap-1.5">
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={value.rs}
              onCheckedChange={() => onChange({ ...value, rs: !value.rs })}
            />
            Regular Season
          </label>
          <label className="flex items-center gap-2 text-sm">
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
