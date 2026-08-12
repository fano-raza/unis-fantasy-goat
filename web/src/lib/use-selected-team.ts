"use client";

import { useEffect, useState } from "react";
import { NO_FOCUS_TEAM } from "@/components/labeled-select";

// Exported for pages with bespoke init logic (e.g. Profile's URL-param
// override) that can't use the hook below directly but still need to
// read/write the same shared value.
export const SELECTED_TEAM_STORAGE_KEY = "app-selected-team";
const STORAGE_KEY = SELECTED_TEAM_STORAGE_KEY;

// Single team selection shared across every page that has a team-select
// dropdown (Focus team selectors, Profile's Team selector, Roster's Team
// selector) via localStorage, so picking a team on one page carries over
// to the next page you land on.
//
// Returns [team, setTeam, hydrated]. `hydrated` flips true once the
// localStorage read has happened. Callers with their own "auto-default to
// something sensible" effect (e.g. "default to whoever's #1 this week")
// must gate that effect on `hydrated` being true first, or it races the
// hydration read and clobbers the shared value on first load.
export function useSelectedTeam(fallback: string): [string, (team: string) => void, boolean] {
  const [team, setTeamState] = useState(fallback);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) setTeamState(saved);
    } catch {
      // ignore
    }
    setHydrated(true);
  }, []);

  function setTeam(next: string) {
    setTeamState(next);
    // Don't persist NO_FOCUS_TEAM globally -- pages without a "None"
    // concept (Profile/Roster) always need a concrete team, so the shared
    // value should always be the last real team chosen.
    if (next !== NO_FOCUS_TEAM) {
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch {
        // ignore
      }
    }
  }

  return [team, setTeam, hydrated];
}
