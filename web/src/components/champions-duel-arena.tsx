"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getTeamSummary, type TeamSummary } from "@/lib/api";
import { directionFor, formatValue } from "@/lib/team-summary-fields";

// One figure per team with >=1 Championship (not every league member) --
// feature request, 2026-10-07: "every champion gets their own stick
// figure." Fetched/filtered client-side rather than hardcoded so a future
// season's new champion shows up automatically.
const FACE_EMOJIS = [
  "😀", "😎", "🤓", "🥳", "😏", "🤠", "🧐", "😺",
  "🤑", "🫡", "🥸", "😇", "🙃", "🤪", "😼", "🫠",
];
const ANGRY_EMOJIS = ["😡", "🤬", "😠"];
const CRYING_EMOJIS = ["😭", "😢", "😿"];

const FIGURE_W = 72;
const FIGURE_H = 88;
const COLLISION_PX = 52;
const WANDER_SPEED_MIN = 26; // px/s per axis component
const WANDER_SPEED_MAX = 46;
const HEADING_CHANGE_MS: [number, number] = [1500, 2800];
// Every few seconds, force one random wandering pair to head straight at
// each other's current position. Pure random-walk crossings turned out to
// be rare with only 6 slow-moving points in a few hundred thousand px^2 of
// arena (confirmed empirically: zero collisions in 100s of real time) --
// this guarantees a duel happens at a pace that's actually fun to watch,
// while the normal wander/heading-bias logic still governs everything
// between matchmaking ticks.
const MATCHMAKE_INTERVAL_MS: [number, number] = [4500, 7500];
const MATCHMAKE_HOLD_MS = 8000; // how long the matched pair ignores its own random heading timer
const DUEL_FREEZE_MS = 900; // both figures stop before the result reveals
const DUEL_REVEAL_HOLD_MS = 1600; // how long the category+winner banner shows
const CORNER_PAUSE_MS = 2000; // feature request's explicit "after 2s"
const POST_DUEL_COOLDOWN_MS = 1500; // grace period before either can duel again

type FigureState = "wander" | "frozen" | "fleeing" | "resting";

interface Physics {
  team: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  speed: number;
  state: FigureState;
  nextHeadingAt: number;
  cooldownUntil: number;
  partner?: string; // the team it's dueling/fled from, cleared on resume
}

interface DuelInfo {
  teamA: string;
  teamB: string;
  category: string;
  valueA: number;
  valueB: number;
  winner: string;
}

function randomFace(): string {
  return FACE_EMOJIS[Math.floor(Math.random() * FACE_EMOJIS.length)];
}

function randomReactionFace(): string {
  const pool = Math.random() < 0.5 ? ANGRY_EMOJIS : CRYING_EMOJIS;
  return pool[Math.floor(Math.random() * pool.length)];
}

// Half the time, aim roughly at another wandering figure (wide +-35deg
// jitter so it doesn't read as a beeline) rather than a fully random
// heading -- with only 6 points drifting slowly around a few hundred
// thousand px^2 of arena, pure random-walk crossings turned out to be rare
// enough in testing that duels almost never happened. This keeps the
// wandering looking organic while making collisions (and so duels) happen
// at a pace that's actually fun to watch.
function pickHeading(f: Physics, figures: Physics[]) {
  const speed = WANDER_SPEED_MIN + Math.random() * (WANDER_SPEED_MAX - WANDER_SPEED_MIN);
  const others = figures.filter((g) => g !== f && g.state === "wander");
  let angle: number;
  if (others.length > 0 && Math.random() < 0.5) {
    const target = others[Math.floor(Math.random() * others.length)];
    const baseAngle = Math.atan2(target.y - f.y, target.x - f.x);
    angle = baseAngle + (Math.random() - 0.5) * (Math.PI / 3);
  } else {
    angle = Math.random() * Math.PI * 2;
  }
  f.vx = Math.cos(angle) * speed;
  f.vy = Math.sin(angle) * speed;
  f.speed = speed;
  f.nextHeadingAt =
    performance.now() + HEADING_CHANGE_MS[0] + Math.random() * (HEADING_CHANGE_MS[1] - HEADING_CHANGE_MS[0]);
}

function spawnFigure(team: string, w: number, h: number): Physics {
  const f: Physics = {
    team,
    x: FIGURE_W / 2 + Math.random() * Math.max(1, w - FIGURE_W),
    y: FIGURE_H / 2 + Math.random() * Math.max(1, h - FIGURE_H),
    vx: 0,
    vy: 0,
    speed: 0,
    state: "wander",
    nextHeadingAt: 0,
    cooldownUntil: 0,
  };
  pickHeading(f, []);
  return f;
}

// Pool of team_comparison fields both teams have a (different) numeric
// value for -- the exact "stat category that we track in the team
// comparison page" the feature request asks for (same direction map
// comparison-view.tsx uses for best/worst highlighting). Equal values are
// excluded up front so every triggered duel has a real winner.
function duelCategoriesFor(rowA: TeamSummary, rowB: TeamSummary): string[] {
  return Object.keys(rowA).filter((field) => {
    if (field === "Team" || directionFor(field) === "skip") return false;
    const a = rowA[field];
    const b = rowB[field];
    return typeof a === "number" && typeof b === "number" && a !== b;
  });
}

export function ChampionsDuelArena() {
  const [champions, setChampions] = useState<TeamSummary[] | null>(null);
  const [headEmoji, setHeadEmoji] = useState<Record<string, string>>({});
  const [duel, setDuel] = useState<DuelInfo | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);
  const figureElsRef = useRef<Record<string, HTMLDivElement | null>>({});
  const physicsRef = useRef<Physics[]>([]);
  const boundsRef = useRef({ w: 0, h: 0 });
  const rafRef = useRef<number>(0);
  const nextMatchmakeAtRef = useRef<number>(0);
  const lastTsRef = useRef<number>(0);

  useEffect(() => {
    getTeamSummary({}).then((rows) => {
      const champs = rows.filter((r) => typeof r.Championships === "number" && r.Championships > 0);
      setChampions(champs);
      setHeadEmoji(Object.fromEntries(champs.map((r) => [r.Team, randomFace()])));
    });
  }, []);

  useEffect(() => {
    if (!champions || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    boundsRef.current = { w: rect.width, h: rect.height };
    physicsRef.current = champions.map((r) => spawnFigure(r.Team, rect.width, rect.height));
  }, [champions]);

  useEffect(() => {
    function handleResize() {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      boundsRef.current = { w: rect.width, h: rect.height };
    }
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  // Both figures stop in place, a random comparable category decides a
  // winner, the loser's head turns angry/crying -- the resume (both back to
  // "wander") only happens once the loser finishes its corner flight +
  // CORNER_PAUSE_MS, handled inside the rAF loop below.
  const triggerDuel = useCallback(
    (a: Physics, b: Physics) => {
      if (!champions) return;
      a.state = "frozen";
      b.state = "frozen";
      a.partner = b.team;
      b.partner = a.team;
      window.setTimeout(() => {
        const rowA = champions.find((r) => r.Team === a.team);
        const rowB = champions.find((r) => r.Team === b.team);
        const pool = rowA && rowB ? duelCategoriesFor(rowA, rowB) : [];
        if (!rowA || !rowB || pool.length === 0) {
          const now = performance.now();
          [a, b].forEach((f) => {
            f.state = "wander";
            f.partner = undefined;
            f.cooldownUntil = now + POST_DUEL_COOLDOWN_MS;
            pickHeading(f, physicsRef.current);
          });
          return;
        }
        const field = pool[Math.floor(Math.random() * pool.length)];
        const valueA = rowA[field] as number;
        const valueB = rowB[field] as number;
        const aWins = directionFor(field) === "higher" ? valueA > valueB : valueA < valueB;
        const winnerTeam = aWins ? a.team : b.team;
        setDuel({ teamA: a.team, teamB: b.team, category: field, valueA, valueB, winner: winnerTeam });

        window.setTimeout(() => {
          setDuel(null);
          const loserFig = aWins ? b : a;
          const bounds = boundsRef.current;
          const targetX = bounds.w - FIGURE_W / 2 - 8;
          const targetY = bounds.h - FIGURE_H / 2 - 8;
          const dx = targetX - loserFig.x;
          const dy = targetY - loserFig.y;
          const dist = Math.hypot(dx, dy) || 1;
          const fleeSpeed = loserFig.speed * 1.5;
          loserFig.vx = (dx / dist) * fleeSpeed;
          loserFig.vy = (dy / dist) * fleeSpeed;
          loserFig.state = "fleeing";
          setHeadEmoji((prev) => ({ ...prev, [loserFig.team]: randomReactionFace() }));
        }, DUEL_REVEAL_HOLD_MS);
      }, DUEL_FREEZE_MS);
    },
    [champions],
  );

  useEffect(() => {
    if (!champions) return;

    function tick(ts: number) {
      const dt = lastTsRef.current ? Math.min((ts - lastTsRef.current) / 1000, 0.1) : 0;
      lastTsRef.current = ts;
      const bounds = boundsRef.current;
      const figures = physicsRef.current;

      for (const f of figures) {
        if (f.state === "wander") {
          if (ts >= f.nextHeadingAt) pickHeading(f, figures);
          f.x += f.vx * dt;
          f.y += f.vy * dt;
          if (f.x < FIGURE_W / 2) {
            f.x = FIGURE_W / 2;
            f.vx = Math.abs(f.vx);
          } else if (f.x > bounds.w - FIGURE_W / 2) {
            f.x = bounds.w - FIGURE_W / 2;
            f.vx = -Math.abs(f.vx);
          }
          if (f.y < FIGURE_H / 2) {
            f.y = FIGURE_H / 2;
            f.vy = Math.abs(f.vy);
          } else if (f.y > bounds.h - FIGURE_H / 2) {
            f.y = bounds.h - FIGURE_H / 2;
            f.vy = -Math.abs(f.vy);
          }
        } else if (f.state === "fleeing") {
          f.x += f.vx * dt;
          f.y += f.vy * dt;
          const targetX = bounds.w - FIGURE_W / 2 - 8;
          const targetY = bounds.h - FIGURE_H / 2 - 8;
          if (Math.hypot(targetX - f.x, targetY - f.y) < 6) {
            f.x = targetX;
            f.y = targetY;
            f.state = "resting";
            const partnerTeam = f.partner;
            window.setTimeout(() => {
              const now = performance.now();
              f.state = "wander";
              f.partner = undefined;
              f.cooldownUntil = now + POST_DUEL_COOLDOWN_MS;
              pickHeading(f, figures);
              setHeadEmoji((prev) => ({ ...prev, [f.team]: randomFace() }));
              const winnerFig = figures.find((g) => g.team === partnerTeam);
              if (winnerFig) {
                winnerFig.state = "wander";
                winnerFig.partner = undefined;
                winnerFig.cooldownUntil = now + POST_DUEL_COOLDOWN_MS;
                pickHeading(winnerFig, figures);
              }
            }, CORNER_PAUSE_MS);
          }
        }

        const el = figureElsRef.current[f.team];
        if (el) el.style.transform = `translate(${f.x - FIGURE_W / 2}px, ${f.y - FIGURE_H / 2}px)`;
      }

      if (ts >= nextMatchmakeAtRef.current) {
        const eligible = figures.filter((f) => f.state === "wander" && ts >= f.cooldownUntil);
        if (eligible.length >= 2) {
          const shuffled = [...eligible].sort(() => Math.random() - 0.5);
          const [p, q] = shuffled;
          const angle = Math.atan2(q.y - p.y, q.x - p.x);
          const speed = WANDER_SPEED_MAX;
          p.vx = Math.cos(angle) * speed;
          p.vy = Math.sin(angle) * speed;
          p.speed = speed;
          p.nextHeadingAt = ts + MATCHMAKE_HOLD_MS;
          q.vx = -Math.cos(angle) * speed;
          q.vy = -Math.sin(angle) * speed;
          q.speed = speed;
          q.nextHeadingAt = ts + MATCHMAKE_HOLD_MS;
        }
        nextMatchmakeAtRef.current =
          ts + MATCHMAKE_INTERVAL_MS[0] + Math.random() * (MATCHMAKE_INTERVAL_MS[1] - MATCHMAKE_INTERVAL_MS[0]);
      }

      for (let i = 0; i < figures.length; i++) {
        const a = figures[i];
        if (a.state !== "wander" || ts < a.cooldownUntil) continue;
        for (let j = i + 1; j < figures.length; j++) {
          const b = figures[j];
          if (b.state !== "wander" || ts < b.cooldownUntil) continue;
          if (Math.hypot(a.x - b.x, a.y - b.y) < COLLISION_PX) {
            triggerDuel(a, b);
            break;
          }
        }
      }

      rafRef.current = requestAnimationFrame(tick);
    }

    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [champions, triggerDuel]);

  if (!champions) {
    return <p className="py-10 text-center text-sm text-muted-foreground">Loading champions...</p>;
  }

  return (
    <div
      ref={containerRef}
      className="relative mx-auto h-[65vh] w-full max-w-3xl overflow-hidden rounded-sm border border-border bg-card"
    >
      {duel && (
        <div className="absolute inset-x-0 top-3 z-20 mx-auto w-fit max-w-[90%] rounded-sm border border-border bg-popover px-4 py-2 text-center shadow-md">
          <p className="text-[11px] font-bold tracking-wider text-muted-foreground uppercase">
            Duel: {duel.category}
          </p>
          <p className="text-sm">
            {duel.teamA} {formatValue(duel.valueA)} — {formatValue(duel.valueB)} {duel.teamB}
          </p>
          <p className="text-sm font-bold text-win">{duel.winner} wins</p>
        </div>
      )}
      {champions.map((row) => (
        <div
          key={row.Team}
          ref={(el) => {
            figureElsRef.current[row.Team] = el;
          }}
          className="absolute top-0 left-0 flex flex-col items-center"
          style={{ width: FIGURE_W, willChange: "transform" }}
        >
          <span className="text-3xl leading-none">{headEmoji[row.Team] ?? "🙂"}</span>
          <svg width="28" height="40" viewBox="0 0 28 40" className="text-foreground">
            <line x1="14" y1="2" x2="14" y2="24" stroke="currentColor" strokeWidth="2" />
            <line x1="4" y1="10" x2="24" y2="10" stroke="currentColor" strokeWidth="2" />
            <line x1="14" y1="24" x2="5" y2="38" stroke="currentColor" strokeWidth="2" />
            <line x1="14" y1="24" x2="23" y2="38" stroke="currentColor" strokeWidth="2" />
          </svg>
          <span className="mt-0.5 whitespace-nowrap text-[11px] font-bold tracking-wide uppercase">
            {row.Team}
          </span>
        </div>
      ))}
    </div>
  );
}
