"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { currentTheme, setTheme, storedTheme, type Theme } from "@/lib/theme";

// Light/Dark switch for the mobile menu, same "Label [switch] Label" pattern
// as the app's other toggles (Stat/Rating, Totals/Averages). Starts in
// whatever is on screen -- the device setting until the viewer flips it,
// their stored choice after.
export function ThemeSwitch() {
  // null until mounted: the real value only exists client-side, and this
  // only ever renders inside the menu drawer (opened after hydration).
  const [theme, setThemeState] = useState<Theme | null>(null);

  useEffect(() => {
    setThemeState(currentTheme());
    // While still following the device (nothing stored), track it live so
    // the switch never shows a stale position after an OS-level change.
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    function handleChange() {
      if (!storedTheme()) setThemeState(media.matches ? "dark" : "light");
    }
    media.addEventListener("change", handleChange);
    return () => media.removeEventListener("change", handleChange);
  }, []);

  if (theme === null) return null;

  return (
    <label className="label flex items-center gap-2 text-foreground">
      <Sun className="size-4 text-muted-foreground" aria-hidden />
      <span className="text-muted-foreground">Light</span>
      <Switch
        checked={theme === "dark"}
        onCheckedChange={(checked) => {
          const next: Theme = checked ? "dark" : "light";
          setTheme(next);
          setThemeState(next);
        }}
        aria-label="Dark mode"
      />
      <span className="text-muted-foreground">Dark</span>
      <Moon className="size-4 text-muted-foreground" aria-hidden />
    </label>
  );
}
