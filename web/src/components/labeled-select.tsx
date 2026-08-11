"use client";

import { cn } from "@/lib/utils";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export const NO_FOCUS_TEAM = "__none__";

export function LabeledSelect({
  label,
  value,
  onValueChange,
  options,
  className,
}: {
  label: string;
  value: string;
  onValueChange: (value: string) => void;
  options: { value: string; label: string }[];
  // Applied to the outer tile -- lets a specific page call out this
  // selector (e.g. a highlighted border) without changing every other
  // page's LabeledSelect usage.
  className?: string;
}) {
  return (
    <label className={cn("flex items-center gap-2", className)}>
      <span className="text-[11px] font-bold tracking-wider text-muted-foreground uppercase">
        {label}
      </span>
      <Select value={value} onValueChange={(v) => v !== null && onValueChange(v)}>
        <SelectTrigger size="sm">
          <SelectValue>
            {(v: string) => options.find((o) => o.value === v)?.label ?? v}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          {options.map((o) => (
            <SelectItem key={o.value} value={o.value}>
              {o.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </label>
  );
}
