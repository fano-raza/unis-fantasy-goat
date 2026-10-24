"use client";

import { Settings } from "lucide-react";
import { Popover, PopoverContent, PopoverTitle, PopoverTrigger } from "@/components/ui/popover";
import { LightModeSwitch } from "@/components/light-mode-switch";

// Desktop-only settings shelf: a gear at the right end of the tab row that
// drops a small panel of app settings (currently just Light mode). Mobile
// has the same setting at the bottom of the menu drawer instead.
export function SettingsMenu() {
  return (
    <Popover>
      <PopoverTrigger
        aria-label="Settings"
        className="mb-1.5 flex size-9 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground data-[popup-open]:bg-muted data-[popup-open]:text-foreground"
      >
        <Settings className="size-[18px]" />
      </PopoverTrigger>
      <PopoverContent align="end" sideOffset={6} className="w-64 gap-3 p-4">
        <PopoverTitle className="font-display text-lg leading-none font-bold [font-variation-settings:'opsz'_36]">
          Settings
        </PopoverTitle>
        <LightModeSwitch />
      </PopoverContent>
    </Popover>
  );
}
