"use client";

import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { motion } from "motion/react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Lock } from "lucide-react";

const PASSWORD = "whogotnext";

// Purely a joke gate for a private friend-group app, not real security --
// exact client-side string match. Deliberately NOT persisted anywhere
// (no localStorage) -- the password is required on every single visit,
// per the user's explicit ask.
// 16 now (feature request, 2026-10-06, up from 8), same
// investigation/fraud/illegitimate-champion theme as TAUNTS below.
const RING_EMOJIS = [
  "🔍", "🔺", "🕵️", "👀", "🏆", "🪙", "🔫", "💥",
  "🚨", "📁", "🎭", "🐒", "🎯", "🍀", "🤡", "📼",
];

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

// Radius bumped 62 -> 90 (feature request, 2026-10-06: "make the shape...
// larger"). Still well inside the overflow-safe ceiling the original 62
// was verified against (~129px before clipping a 320px-wide viewport's
// padding, per that comment) even with the now-larger emoji set, so no
// new overflow risk. Wrapper bumped size-44 -> size-60 to match (the ring
// itself isn't overflow-hidden, so this is cosmetic spacing, not a hard
// clip boundary, but keeps gap-10 below from feeling cramped).
const RING_RADIUS_PX = 90;

// How long a click's scatter holds at its random positions before the
// slow return begins, and how long that return itself takes.
const SCATTER_HOLD_MS = 500;
const RETURN_DURATION_S = 1.8;

// Random point for the scatter animation -- a wider spread than the
// resting radius so it reads as genuinely flying outward, not just
// jittering near the ring.
function randomScatterPoint(): { x: number; y: number } {
  const angle = Math.random() * Math.PI * 2;
  const radius = 110 + Math.random() * 130;
  return { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius };
}

function EmojiTriangle({
  scattered,
  scatterPoints,
}: {
  scattered: boolean;
  scatterPoints: { x: number; y: number }[];
}) {
  // Same radius-safety reasoning as before, just against the new larger
  // RING_RADIUS_PX.
  const points = useMemo(() => trianglePerimeterPoints(RING_EMOJIS.length, RING_RADIUS_PX), []);
  return (
    <div
      className="relative mx-auto size-60 champions-ring"
      // Paused (not left running) for the whole scatter+return sequence --
      // feature request, 2026-10-06. If the orbit kept spinning while a
      // scattered emoji's own position is independently animating, the
      // scattered point would get swept around by the parent's rotation
      // too, looking chaotic instead of landing where it actually should.
      style={{ animationPlayState: scattered ? "paused" : "running" }}
    >
      {RING_EMOJIS.map((emoji, i) => {
        const target = scattered ? (scatterPoints[i] ?? points[i]) : points[i];
        return (
          <motion.div
            key={i}
            className="absolute top-1/2 left-1/2"
            animate={{ x: target.x, y: target.y }}
            // Scatter is quick (flung outward); the return is deliberately
            // slow -- feature request, 2026-10-06's own wording ("slowly
            // returning").
            transition={
              scattered
                ? { duration: 0.35, ease: "easeOut" }
                : { duration: RETURN_DURATION_S, ease: "easeInOut" }
            }
          >
            <span
              className="champions-ring-item inline-block text-2xl"
              style={{ animationPlayState: scattered ? "paused" : "running" }}
            >
              {emoji}
            </span>
          </motion.div>
        );
      })}
    </div>
  );
}

export default function ChampionsLoungePage() {
  const [unlocked, setUnlocked] = useState(false);
  const [input, setInput] = useState("");
  const [wrong, setWrong] = useState(false);
  // Starting index still randomized on unlock (same surprise-on-entry
  // feel as before); cycles sequentially through TAUNTS from there every
  // 3s once unlocked -- feature request, 2026-10-06.
  const [tauntIndex, setTauntIndex] = useState(0);
  const [scattered, setScattered] = useState(false);
  const [scatterPoints, setScatterPoints] = useState<{ x: number; y: number }[]>([]);

  useEffect(() => {
    if (!unlocked) return;
    const id = setInterval(() => {
      setTauntIndex((i) => (i + 1) % TAUNTS.length);
    }, 3000);
    return () => clearInterval(id);
  }, [unlocked]);

  // Click anywhere on the unlocked view (feature request, 2026-10-06):
  // fling every emoji to a fresh random spot, hold briefly, then glide
  // slowly back -- timeouts cleared on unmount/re-click so a rapid second
  // click cleanly restarts the sequence instead of fighting a pending one.
  const timeoutsRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  useEffect(() => {
    return () => {
      timeoutsRef.current.forEach(clearTimeout);
    };
  }, []);

  function handleScatterClick() {
    timeoutsRef.current.forEach(clearTimeout);
    timeoutsRef.current = [];
    setScatterPoints(RING_EMOJIS.map(() => randomScatterPoint()));
    setScattered(true);
    const returnTimeout = setTimeout(() => {
      setScattered(false);
    }, SCATTER_HOLD_MS);
    timeoutsRef.current.push(returnTimeout);
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (input === PASSWORD) {
      setTauntIndex(Math.floor(Math.random() * TAUNTS.length));
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
    <div
      onClick={handleScatterClick}
      className="flex cursor-pointer flex-col items-center justify-center gap-10 py-20 select-none"
    >
      <EmojiTriangle scattered={scattered} scatterPoints={scatterPoints} />
      <p className="max-w-lg text-center font-mono text-lg font-extrabold tracking-wide uppercase">
        {TAUNTS[tauntIndex]}
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
