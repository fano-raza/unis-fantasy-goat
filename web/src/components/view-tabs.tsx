import { cn } from "@/lib/utils";

export interface ViewTabOption {
  value: string;
  label: string;
}

// Desktop-only alternative to ArrowToggle: shows every option at once as a
// row of pills (active one filled, the rest greyed out) instead of cycling
// one label with chevrons -- same active/inactive visual language as the
// top Nav (`bg-primary` vs. `text-muted-foreground`). Standings uses this on
// desktop and ArrowToggle on mobile (arrows are more thumb-friendly in a
// cramped sticky bar); ArrowToggle itself is left untouched since Profile's
// Profile/Comparison toggle still wants the cycling behavior everywhere.
export function ViewTabs({
  options,
  value,
  onChange,
}: {
  options: ViewTabOption[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="flex items-center gap-0.5 rounded-md bg-muted p-0.5">
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={cn(
              "rounded-[calc(var(--radius)-2px)] px-3 py-1.5 text-sm font-medium transition-colors",
              active
                ? "bg-accent text-foreground shadow-[inset_0_-2px_0_var(--primary)]"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
