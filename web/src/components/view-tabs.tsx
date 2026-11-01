import { cn } from "@/lib/utils";

export interface ViewTabOption {
  value: string;
  label: string;
}

// Every option at once as a row of pills (active one filled, the rest greyed
// out) -- same active/inactive visual language as the top Nav. Used for
// every section's sub-pages, desktop and mobile alike.
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
    // Below `sm` the strip spans the full width and the tabs share it evenly,
    // so a 4-tab section (League) still fits a phone without scrolling.
    <div className="flex w-full items-center gap-0.5 rounded-md bg-muted p-0.5 sm:w-auto">
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={cn(
              "flex-1 rounded-[calc(var(--radius)-2px)] px-1.5 py-1.5 text-xs font-medium whitespace-nowrap transition-colors sm:flex-none sm:px-3 sm:text-sm",
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
