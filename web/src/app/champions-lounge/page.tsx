"use client";

import { useState, type FormEvent } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Lock } from "lucide-react";
import { ChampionsDuelArena } from "@/components/champions-duel-arena";

const PASSWORD = "whogotnext";

// Purely a joke gate for a private friend-group app, not real security --
// exact client-side string match. Deliberately NOT persisted anywhere
// (no localStorage) -- the password is required on every single visit,
// per the user's explicit ask.

export default function ChampionsLoungePage() {
  const [unlocked, setUnlocked] = useState(false);
  const [input, setInput] = useState("");
  const [wrong, setWrong] = useState(false);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (input === PASSWORD) {
      setUnlocked(true);
      setWrong(false);
    } else {
      setWrong(true);
    }
  }

  if (!unlocked) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-24">
        <Lock className="size-8 text-muted-foreground" />
        <Card className="w-full max-w-xs">
          <CardContent>
            <form onSubmit={handleSubmit} className="flex flex-col gap-3">
              <label className="flex flex-col gap-1.5">
                <span className="text-[11px] font-bold tracking-wider text-muted-foreground uppercase">
                  Password
                </span>
                <input
                  type="password"
                  value={input}
                  onChange={(e) => {
                    setInput(e.target.value);
                    setWrong(false);
                  }}
                  autoFocus
                  className="rounded-sm border border-border bg-card px-3 py-2 text-sm outline-none focus:border-ring"
                />
              </label>
              {wrong && <p className="text-xs text-loss">Wrong password.</p>}
              <Button type="submit">Enter</Button>
            </form>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center gap-6 px-4 py-10 select-none">
      <div className="text-center">
        <h1 className="font-mono text-lg font-extrabold tracking-wide uppercase">Champions Lounge</h1>
        <p className="text-sm text-muted-foreground">
          Six titles, six egos. Let them wander -- when two collide, a random stat settles it.
        </p>
      </div>
      <ChampionsDuelArena />
    </div>
  );
}
