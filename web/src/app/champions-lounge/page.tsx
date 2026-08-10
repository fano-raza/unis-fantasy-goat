"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Lock } from "lucide-react";

const PASSWORD = "whogotnext";
const UNLOCKED_KEY = "champions-lounge-unlocked";

// Purely a joke gate for a private friend-group app, not real security --
// exact client-side string match, remembered in localStorage so it doesn't
// re-prompt every visit.
const RING_EMOJIS = ["🔍", "🔺", "🕵️", "👀", "🏆", "🪙", "🔫", "💥"];

function EmojiRing() {
  // Radius kept well inside the ring's own box so wide multi-codepoint
  // glyphs (e.g. the detective emoji) can't push the page into horizontal
  // scroll -- measured actual overflow at two larger radius/size values
  // before landing here; re-verified clean at the narrowest common mobile
  // width (320px) as well as 390px, across several seconds of the
  // animation (not just a single frame).
  const radius = 62;
  return (
    <div className="relative mx-auto size-44 champions-ring">
      {RING_EMOJIS.map((emoji, i) => {
        const angle = (360 / RING_EMOJIS.length) * i;
        return (
          <div
            key={i}
            className="absolute top-1/2 left-1/2"
            style={{ transform: `rotate(${angle}deg) translate(${radius}px) rotate(${-angle}deg)` }}
          >
            <span className="champions-ring-item inline-block text-2xl">{emoji}</span>
          </div>
        );
      })}
    </div>
  );
}

export default function ChampionsLoungePage() {
  const [unlocked, setUnlocked] = useState(false);
  const [checkedStorage, setCheckedStorage] = useState(false);
  const [input, setInput] = useState("");
  const [wrong, setWrong] = useState(false);

  useEffect(() => {
    try {
      if (localStorage.getItem(UNLOCKED_KEY) === "true") setUnlocked(true);
    } catch {}
    setCheckedStorage(true);
  }, []);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (input === PASSWORD) {
      setUnlocked(true);
      setWrong(false);
      try {
        localStorage.setItem(UNLOCKED_KEY, "true");
      } catch {}
    } else {
      setWrong(true);
    }
  }

  if (!checkedStorage) return null;

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
    <div className="flex flex-col items-center justify-center gap-10 py-20">
      <EmojiRing />
      <p className="max-w-lg text-center font-mono text-lg font-extrabold tracking-wide uppercase">
        You probably don&apos;t deserve to be here! 🤡🤡🤡
      </p>
      <style>{`
        .champions-ring {
          animation: champions-orbit 18s linear infinite;
        }
        .champions-ring-item {
          animation: champions-counter-orbit 18s linear infinite;
        }
        @keyframes champions-orbit {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        @keyframes champions-counter-orbit {
          from { transform: rotate(0deg); }
          to { transform: rotate(-360deg); }
        }
      `}</style>
    </div>
  );
}
