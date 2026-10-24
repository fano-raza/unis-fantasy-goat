"use client";

import { useEffect, useId, useState } from "react";
import { Sun } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { currentTheme, setTheme } from "@/lib/theme";

// The Light mode setting -- one row, used in both the mobile menu drawer and
// the desktop settings shelf (settings-menu.tsx). Off = the default dark
// theme. Each instance reads the stored choice when it mounts; the two never
// render at the same time (mobile drawer vs desktop-only shelf).
export function LightModeSwitch() {
  const id = useId();
  // null until mounted: the stored choice only exists client-side, and this
  // only ever renders inside a drawer/popover opened after hydration.
  const [light, setLight] = useState<boolean | null>(null);

  useEffect(() => {
    setLight(currentTheme() === "light");
  }, []);

  if (light === null) return null;

  return (
    <div className="flex items-center justify-between gap-4">
      <label htmlFor={id} className="flex items-center gap-2 text-sm font-medium">
        <Sun className="size-4 text-muted-foreground" aria-hidden />
        Light mode
      </label>
      <Switch
        id={id}
        checked={light}
        onCheckedChange={(checked) => {
          setTheme(checked ? "light" : "dark");
          setLight(checked);
        }}
      />
    </div>
  );
}
