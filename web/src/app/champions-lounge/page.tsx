"use client";

import { useMemo, useState, type FormEvent } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Lock } from "lucide-react";

const PASSWORD = "whogotnext";

// Purely a joke gate for a private friend-group app, not real security --
// exact client-side string match. Deliberately NOT persisted anywhere
// (no localStorage) -- the password is required on every single visit,
// per the user's explicit ask.
const RING_EMOJIS = ["🔍", "🔺", "🕵️", "👀", "🏆", "🪙", "🔫", "💥"];

// Picked fresh on every successful unlock (see handleSubmit) -- all on the
// theme of "you got lucky" / "you don't actually deserve this," even
// though they just got the password right.
const TAUNTS = [
  "YOU PROBABLY DON'T DESERVE TO BE HERE! 🤡🤡🤡",
  "CONGRATS ON THE LUCKIEST SCHEDULE IN LEAGUE HISTORY 🍀🍀🍀",
  "YOUR RING IS MADE OF PARTICIPATION TROPHY METAL 🏆❌",
  "SOMEWHERE, A REAL CHAMPION IS LAUGHING AT YOU 😂😂😂",
  "THIS TITLE HAS AN ASTERISK THE SIZE OF THE MOON 🌕*️⃣",
  "YOU BEAT BOTS, NOT MEN 🤖🤖🤖",
  "EVEN YOUR BENCH IS EMBARRASSED FOR YOU 🪑😳",
  "STATISTICALLY, THIS SHOULDN'T HAVE HAPPENED 📊🚫",
  "YOUR DRAFT BOARD WAS A DARTBOARD 🎯🍺",
  "THIS CHAMPIONSHIP WAS BROUGHT TO YOU BY LUCK, NOT SKILL 🎰🎰🎰",
  "WE CHECKED THE TAPE. IT WAS FRAUD 📼🚨",
  "SECURITY IS ON THE WAY TO ESCORT YOU OUT 🚔👋",
  "YOUR OPPONENT'S STAR PLAYER GOT HURT AT HALFTIME. SUSPICIOUS 🤕🔍",
  "IMPOSTER SYNDROME? NO, JUST AN IMPOSTER 🎭🎭🎭",
  "PLEASE ENJOY YOUR STAY UNTIL WE FIGURE OUT HOW YOU GOT IN 🕵️‍♂️🚪",
  "THIS IS WHAT WE CALL A RIGGED LOTTERY WIN 🎟️🎰",
  "EVEN YOUR TROPHY LOOKS CONFUSED 🏆❓",
  "A MONKEY WITH A DARTBOARD COULD'VE DRAFTED BETTER 🐒🎯",
  "THE COMMISSIONER IS QUIETLY INVESTIGATING YOU 🕵️‍♀️📁",
];

// Evenly spaced points around an equilateral triangle's PERIMETER (not
// just the 3 vertices) -- with 8 points that lands as 3/3/2 per edge,
// close enough to even for a decorative shape.
function trianglePerimeterPoints(n: number, r: number): { x: number; y: number }[] {
  const vertices = [0, 1, 2].map((i) => {
    const rad = ((-90 + i * 120) * Math.PI) / 180;
    return { x: r * Math.cos(rad), y: r * Math.sin(rad) };
  });
  return Array.from({ length: n }, (_, k) => {
    const edgeFloat = (k / n) * 3;
    const edgeIndex = Math.min(2, Math.floor(edgeFloat));
    const localT = edgeFloat - edgeIndex;
    const a = vertices[edgeIndex];
    const b = vertices[(edgeIndex + 1) % 3];
    return { x: a.x + (b.x - a.x) * localT, y: a.y + (b.y - a.y) * localT };
  });
}

function EmojiTriangle() {
  // Same radius that was verified overflow-free (across 320/360/390px
  // viewports, sampled over several seconds of animation) for the earlier
  // circular layout -- a triangle's vertices are exactly this far from
  // center too, so it's the same worst case.
  const points = useMemo(() => trianglePerimeterPoints(RING_EMOJIS.length, 62), []);
  return (
    <div className="relative mx-auto size-44 champions-ring">
      {RING_EMOJIS.map((emoji, i) => (
        <div
          key={i}
          className="absolute top-1/2 left-1/2"
          style={{ transform: `translate(${points[i].x}px, ${points[i].y}px)` }}
        >
          <span className="champions-ring-item inline-block text-2xl">{emoji}</span>
        </div>
      ))}
    </div>
  );
}

export default function ChampionsLoungePage() {
  const [unlocked, setUnlocked] = useState(false);
  const [input, setInput] = useState("");
  const [wrong, setWrong] = useState(false);
  const [taunt, setTaunt] = useState("");

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (input === PASSWORD) {
      setTaunt(TAUNTS[Math.floor(Math.random() * TAUNTS.length)]);
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
    <div className="flex flex-col items-center justify-center gap-10 py-20">
      <EmojiTriangle />
      <p className="max-w-lg text-center font-mono text-lg font-extrabold tracking-wide uppercase">
        {taunt}
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
