"use client";

import { useLiveRefetch } from "@/lib/live-data";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { StatTable } from "@/components/stat-table";
import { LabeledSelect, NO_FOCUS_TEAM } from "@/components/labeled-select";
import { SteppableSelect } from "@/components/steppable-select";
import { useSelectedTeam } from "@/lib/use-selected-team";
import {
  API_BASE_URL,
  getNBASchedule,
  getRosterRanks,
  getWeekCalendar,
  getWeeklyLeaderboard,
  getWeeklyLeaderboardSeason,
  getWeeklyRecap,
  getWeeklyStatsBootstrap,
  type LeagueMeta,
  type NBAScheduleGame,
  type RosterRankRow,
  type SeasonWeeks,
  type WeekRow,
  type WeeklyRecap,
  type WeeklyStatsBootstrap,
} from "@/lib/api";
import type { GamesProgress } from "@/components/stat-table";
import { LoadingBasketballs } from "@/components/loading-basketballs";
import { LoadingOverlay } from "@/components/loading-overlay";
import { cn } from "@/lib/utils";

// Standard competition ranking (ties share a rank) over just the rows
// actually shown, using each row's rating -- NOT the backend's raw `rank`.
// On playoff weeks the backend's rank is relative to a broader hidden pool
// (bracket + consolation, kept that way deliberately to match GDoc/Discord
// bot parity -- see dashboard_site/api/league_store.py::_ensure_rated_df),
// so the visible rows alone can show gaps like 3, 4, 5, 7. Re-ranking just
// what's on screen gives a clean 1..N sequence without touching that shared
// backend math. BYE rows (rating: null) are excluded, same as they are from
// the rating pool itself.
function computeDisplayRanks(rows: WeekRow[]): Map<string, number> {
  const ranked = rows.filter((r): r is WeekRow & { rating: number } => r.rating != null);
  const ranks = new Map<string, number>();
  for (const row of ranked) {
    const better = ranked.filter((r) => r.rating > row.rating).length;
    ranks.set(row.team, better + 1);
  }
  return ranks;
}

// Pickups land once per day, guaranteed after 4 AM ET -- confirmed with the
// user (2026-10-28) -- so a team's roster is guaranteed unchanged from one
// day's 4 AM ET through the next's. The Games column's roster+schedule
// fetch is cached in localStorage keyed by this day, so repeat page loads
// within that same window reuse it instead of re-hitting the backend; a
// day boundary (or the current week rolling over) naturally invalidates it.
// Distinct from roster-view.tsx's leagueTodayKey() (2 AM ET, for week
// boundaries) -- same shape, different real-world cutoff.
const GAMES_CACHE_EASTERN_TZ = "America/New_York";
const GAMES_CACHE_CUTOFF = "04:00";

function gamesCacheDayKey(): string {
  const hourMinute = new Date().toLocaleTimeString("en-GB", {
    timeZone: GAMES_CACHE_EASTERN_TZ,
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
  });
  const beforeCutoff = hourMinute < GAMES_CACHE_CUTOFF;
  return new Date(Date.now() - (beforeCutoff ? 24 * 60 * 60 * 1000 : 0)).toLocaleDateString("en-CA", {
    timeZone: GAMES_CACHE_EASTERN_TZ,
  });
}

// Bumped if the cached shape ever changes -- a stale entry from an old
// version is just a cache miss, not a crash.
const GAMES_CACHE_VERSION = 1;

interface GamesCacheEntry {
  version: number;
  dayKey: string;
  year: number;
  week: number;
  roster: RosterRankRow[];
  games: NBAScheduleGame[];
}

function gamesCacheStorageKey(year: number): string {
  return `weeklyStatsGamesCache:${year}`;
}

function readGamesCache(year: number, week: number, dayKey: string): GamesCacheEntry | null {
  try {
    const raw = localStorage.getItem(gamesCacheStorageKey(year));
    if (!raw) return null;
    const entry = JSON.parse(raw) as GamesCacheEntry;
    if (entry.version !== GAMES_CACHE_VERSION || entry.dayKey !== dayKey || entry.year !== year || entry.week !== week) {
      return null;
    }
    return entry;
  } catch {
    // Corrupt JSON, private-browsing storage block, etc. -- just a cache
    // miss, caching is an optimization here, not a correctness requirement.
    return null;
  }
}

function writeGamesCache(entry: GamesCacheEntry) {
  try {
    localStorage.setItem(gamesCacheStorageKey(entry.year), JSON.stringify(entry));
  } catch {
    // Quota exceeded / storage blocked -- fine to drop, next load just
    // re-fetches.
  }
}

interface WeeklyStatsViewProps {
  // Fetched server-side (see app/page.tsx) so the bootstrap round-trip to
  // the backend happens during SSR/ISR instead of after the client
  // downloads, parses, and hydrates the page's JS -- null if the server
  // fetch failed (backend unreachable at render time), in which case this
  // falls back to the client-side fetch exactly as before.
  initialBootstrap: WeeklyStatsBootstrap | null;
}

export function WeeklyStatsView({ initialBootstrap }: WeeklyStatsViewProps) {
  return (
    <Suspense fallback={<LoadingBasketballs label="Loading" />}>
      <WeeklyStatsPageInner initialBootstrap={initialBootstrap} />
    </Suspense>
  );
}

// useSearchParams() (for the ?year=&week= deep link -- StatBot's Monday
// "Week N Rankings" post links here) requires a Suspense boundary around
// whatever calls it, per Next.js.
function WeeklyStatsPageInner({ initialBootstrap }: WeeklyStatsViewProps) {
  const [meta, setMeta] = useState<LeagueMeta | null>(initialBootstrap?.meta ?? null);
  const [metaError, setMetaError] = useState<unknown>(null);
  const [year, setYear] = useState<number | null>(null);
  const [week, setWeek] = useState<number | null>(null);
  const [focusTeam, setFocusTeam, focusTeamHydrated] = useSelectedTeam(NO_FOCUS_TEAM);
  const [mode, setMode] = useState<"stat" | "rating">("stat");
  const [rows, setRows] = useState<WeekRow[]>([]);
  const [rowsError, setRowsError] = useState<string | null>(null);
  const [rowsLoading, setRowsLoading] = useState(true);
  const [recap, setRecap] = useState<WeeklyRecap | null>(null);
  const [recapLoading, setRecapLoading] = useState(true);
  // Current-week "games played / scheduled" per team (see gamesProgress
  // memo below) -- fetched once per current-week rollover, not per
  // year/week navigation, since it's always anchored to meta.current_week
  // regardless of which week the user is browsing.
  const [gamesRoster, setGamesRoster] = useState<RosterRankRow[]>([]);
  const [gamesSchedule, setGamesSchedule] = useState<NBAScheduleGame[]>([]);
  const [gamesDataLoading, setGamesDataLoading] = useState(true);
  // Bootstrap fetches meta + the current week's rows in one round-trip; this
  // flags that the next [year, week] effect run is that same initial pair,
  // so it doesn't re-fetch what bootstrap already delivered.
  const skipNextLeaderboardFetch = useRef(false);
  // Every year's weeks fetched so far, keyed by year -- seeded from the
  // bootstrap's current-year season slice, then grown on demand whenever
  // the user switches to a year not yet in here (see the [year, week]
  // effect below). Switching weeks WITHIN an already-cached year is then a
  // synchronous lookup, not a fetch -- the whole point of this cache.
  const seasonCacheRef = useRef<Map<number, SeasonWeeks>>(new Map());

  const searchParams = useSearchParams();

  useEffect(() => {
    const yearFromUrl = Number(searchParams.get("year"));
    const weekFromUrl = Number(searchParams.get("week"));

    // Resolves the fetched-from-wherever bootstrap payload (server-provided
    // prop, or -- if that failed -- the client's own fetch below) the same
    // way regardless of source.
    function applyBootstrap(m: LeagueMeta, r: WeekRow[], season: SeasonWeeks) {
      setMeta(m);
      seasonCacheRef.current.set(m.current_year, season);
      // A deep link (e.g. StatBot's weekly rankings post) always names a
      // real, already-completed week -- fall through to the normal
      // [year, week] fetch effect below instead of using bootstrap's
      // current-week rows.
      const hasOverride = m.years.includes(yearFromUrl) && weekFromUrl >= 1;
      if (hasOverride) {
        setYear(yearFromUrl);
        setWeek(weekFromUrl);
        setRowsError(null);
        return;
      }
      skipNextLeaderboardFetch.current = true;
      setRows(r);
      setRowsError(null);
      setRowsLoading(false);
      setYear(m.current_year);
      setWeek(m.current_week);
    }

    if (initialBootstrap) {
      applyBootstrap(initialBootstrap.meta, initialBootstrap.rows, initialBootstrap.season);
      return;
    }

    getWeeklyStatsBootstrap()
      .then(({ meta: m, rows: r, season }) => applyBootstrap(m, r, season))
      .catch(setMetaError);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (year == null || week == null) return;
    setRecapLoading(true);
    getWeeklyRecap({ year, week })
      .then(setRecap)
      .catch(() => setRecap(null))
      .finally(() => setRecapLoading(false));
  }, [year, week]);

  // Current-week "Games" column data: every team's live roster (for the
  // games-by-NBA-team join below) plus the real NBA schedule for the
  // current fantasy week's exact date range. Anchored to meta's current
  // year/week, not the year/week state the user is browsing -- showing
  // this against a past week would pair today's roster (roster_ranks.csv
  // is a same-day snapshot, not tracked historically) with a schedule it
  // didn't necessarily apply to back then, same reasoning as the Team
  // page's Roster sub-view (roster-view.tsx::weekOptions).
  //
  // Cached in localStorage per gamesCacheDayKey() (4 AM ET -- pickups land
  // once per day, guaranteed after that cutoff, confirmed with the user) so
  // a page reload within the same day reuses it instead of re-fetching.
  useEffect(() => {
    if (!meta) return;
    const year = meta.current_year;
    const week = meta.current_week;
    const dayKey = gamesCacheDayKey();

    const cached = readGamesCache(year, week, dayKey);
    if (cached) {
      setGamesRoster(cached.roster);
      setGamesSchedule(cached.games);
      setGamesDataLoading(false);
      return;
    }

    let cancelled = false;
    setGamesDataLoading(true);
    (async () => {
      try {
        const [roster, weeks] = await Promise.all([getRosterRanks({ year }), getWeekCalendar({ year })]);
        if (cancelled) return;
        const currentWeekRow = weeks.find((w) => w.Week === week);
        const games = currentWeekRow
          ? await getNBASchedule({ start_date: currentWeekRow.StartDate, end_date: currentWeekRow.EndDate })
          : [];
        if (cancelled) return;
        setGamesRoster(roster);
        setGamesSchedule(games);
        writeGamesCache({ version: GAMES_CACHE_VERSION, dayKey, year, week, roster, games });
      } catch {
        if (!cancelled) {
          setGamesRoster([]);
          setGamesSchedule([]);
        }
      } finally {
        if (!cancelled) setGamesDataLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meta?.current_year, meta?.current_week]);

  useEffect(() => {
    if (year == null || week == null) return;
    if (skipNextLeaderboardFetch.current) {
      skipNextLeaderboardFetch.current = false;
      return;
    }

    // Fast path: this year's weeks are already cached (from bootstrap, or
    // from a previous switch to this year) -- synchronous, no fetch, no
    // loading flicker.
    const cachedWeek = seasonCacheRef.current.get(year)?.[String(week)];
    if (cachedWeek) {
      setRows(cachedWeek);
      setRowsError(null);
      setRowsLoading(false);
      return;
    }

    let cancelled = false;
    setRowsLoading(true);

    async function load() {
      try {
        let season = seasonCacheRef.current.get(year as number);
        if (!season) {
          season = await getWeeklyLeaderboardSeason(year as number);
          seasonCacheRef.current.set(year as number, season);
        }
        if (cancelled) return;
        const weekRows = season[String(week)];
        if (weekRows) {
          setRows(weekRows);
          setRowsError(null);
          return;
        }
        // Defensive fallback -- the season endpoint covers every real week,
        // so this shouldn't normally trigger, but a single-week fetch still
        // works standalone if it ever does.
        const r = await getWeeklyLeaderboard({ year: year as number, week: week as number });
        if (cancelled) return;
        setRows(r);
        setRowsError(null);
      } catch (err) {
        if (cancelled) return;
        setRows([]);
        setRowsError(err instanceof Error ? err.message : String(err));
      } finally {
        if (!cancelled) setRowsLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [year, week]);

  // Live updates: when the API loads newer stats (LiveDataProvider polls
  // /refresh_status every minute), quietly re-fetch the week on screen --
  // for any week of the current season, since late games can still land in
  // last week until the 2 AM cutoff. Past seasons never change. Keeps the
  // last good rows on a transient failure, and drops a response if the
  // selection changed while it was in flight.
  const live = useLiveRefetch();
  const selectionRef = useRef<[number | null, number | null]>([year, week]);
  useEffect(() => {
    selectionRef.current = [year, week];
  }, [year, week]);
  useEffect(() => {
    if (!live.isRefetch()) return;
    if (!meta || year == null || week == null || year !== meta.current_year) return;
    getWeeklyLeaderboard({ year, week })
      .then((r) => {
        const season = seasonCacheRef.current.get(year);
        if (season) season[String(week)] = r;
        const [y, w] = selectionRef.current;
        if (y === year && w === week) setRows(r);
      })
      .catch(() => {});
    // Only on a data update -- selection changes are handled by the fetch above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live.version]);

  const displayRanks = useMemo(() => computeDisplayRanks(rows), [rows]);
  const displayRows = useMemo(
    () => rows.map((r) => ({ ...r, rank: displayRanks.get(r.team) ?? null })),
    [rows, displayRanks],
  );

  // Per fantasy team: how many of this week's scheduled games (across every
  // active, non-IR rostered player's real NBA team) have already tipped off.
  // A player on an NBA team playing twice this week counts twice -- this is
  // "total possible games across the roster," the same convention already
  // used per-player on the Team page's Roster sub-view (roster-view.tsx's
  // gamesLeftLabel), not a starting-lineup-capped count.
  const gamesProgress = useMemo(() => {
    const gamesByNBATeam = new Map<string, NBAScheduleGame[]>();
    for (const game of gamesSchedule) {
      for (const abbr of [game.HomeTeam, game.AwayTeam]) {
        if (!gamesByNBATeam.has(abbr)) gamesByNBATeam.set(abbr, []);
        gamesByNBATeam.get(abbr)!.push(game);
      }
    }
    const now = Date.now();
    const progress: Record<string, GamesProgress> = {};
    for (const row of gamesRoster) {
      if (!row.FantasyTeam || row.LineupSlot === "IR") continue;
      const games = gamesByNBATeam.get(row.NBATeam) ?? [];
      const entry = progress[row.FantasyTeam] ?? { played: 0, total: 0 };
      entry.total += games.length;
      entry.played += games.filter((g) => new Date(g.Date).getTime() <= now).length;
      progress[row.FantasyTeam] = entry;
    }
    return progress;
  }, [gamesRoster, gamesSchedule]);
  const isCurrentWeek = meta != null && year === meta.current_year && week === meta.current_week;

  // Default (and re-default, if the current focus team disappears from a
  // new week's table) to whichever team displays as #1. Left alone once the
  // user manually picks a team that's still shown.
  useEffect(() => {
    if (!focusTeamHydrated || rows.length === 0) return;
    const teamsShown = new Set(rows.map((r) => r.team));
    if (focusTeam !== NO_FOCUS_TEAM && teamsShown.has(focusTeam)) return;
    const topTeam = rows.find((r) => displayRanks.get(r.team) === 1);
    setFocusTeam(topTeam?.team ?? NO_FOCUS_TEAM);
  }, [rows, displayRanks, focusTeam, focusTeamHydrated]);

  const weekOptions = useMemo(() => {
    if (!meta || year == null) return [];
    const max = meta.total_matchup_count[String(year)] ?? 1;
    return Array.from({ length: max }, (_, i) => i + 1);
  }, [meta, year]);

  // Only teams actually shown this week (now includes BYE teams), not the
  // full league roster.
  const focusOptions = useMemo(() => [...rows.map((r) => r.team)].sort(), [rows]);

  if (metaError) return <BackendUnreachable error={metaError} />;
  if (!meta || year == null || week == null) return <LoadingBasketballs label="Loading" />;

  // Clamp week to the new year's last real week if the current week doesn't
  // exist there (e.g. 2019 week 22 -> a year with only 18 weeks) -- feature
  // request, 2026-10-06. Done here, in the same handler as setYear, rather
  // than a separate effect watching `year`, so both state updates land in
  // one batch and the [year, week] fetch effect never runs with a
  // momentarily-invalid (year, week) pair in between.
  function handleYearChange(newYear: number) {
    setYear(newYear);
    // Non-null: this function is only ever invoked from the JSX below,
    // which only renders past the `!meta || week == null` guard above.
    const maxWeek = meta!.total_matchup_count[String(newYear)] ?? 1;
    if (week! > maxWeek) setWeek(maxWeek);
  }

  const isPlayoffWeek = week > (meta.rs_week_count[String(year)] ?? Infinity);

  return (
    <div className="flex flex-col gap-4">
      <Card variant="plain">
        <CardContent
          className={cn(
            "flex flex-wrap items-center gap-4",
            isPlayoffWeek && "rounded-md border border-gold/50 bg-gold/[0.06] p-3",
          )}
        >
          <SteppableSelect label="Season" value={year} onValueChange={handleYearChange} options={meta.years} />
          <div className="flex items-center gap-1">
            <SteppableSelect label="Week" value={week} onValueChange={setWeek} options={weekOptions} />
            {isPlayoffWeek && (
              <span className="rounded-sm bg-gold/15 px-1.5 py-0.5 text-xs font-semibold text-gold">
                Playoffs
              </span>
            )}
          </div>
          <Button
            variant="secondary"
            size="sm"
            disabled={year === meta.current_year && week === meta.current_week}
            onClick={() => {
              setYear(meta.current_year);
              setWeek(meta.current_week);
            }}
          >
            Current Week
          </Button>
          <LabeledSelect
            label="Focus team"
            value={focusTeam}
            onValueChange={setFocusTeam}
            options={[
              { value: NO_FOCUS_TEAM, label: "None" },
              ...focusOptions.map((m) => ({ value: m, label: m })),
            ]}
          />
          <label className="flex items-center gap-2 label text-foreground">
            <span className="text-muted-foreground">Stat</span>
            <Switch
              checked={mode === "rating"}
              onCheckedChange={(checked) => setMode(checked ? "rating" : "stat")}
            />
            <span className="text-muted-foreground">Rating</span>
          </label>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <LoadingOverlay active={rowsLoading} hasContent={rows.length > 0} label="Loading week">
            {rowsError ? (
              <p className="text-sm text-muted-foreground">
                No data for {year} week {week} ({rowsError}).
              </p>
            ) : (
              <StatTable
                rows={displayRows}
                mode={mode}
                focusTeam={focusTeam === NO_FOCUS_TEAM ? undefined : focusTeam}
                showFocusScore
                gamesProgress={isCurrentWeek ? gamesProgress : undefined}
                gamesLoading={isCurrentWeek && gamesDataLoading}
              />
            )}
          </LoadingOverlay>
        </CardContent>
      </Card>

      {(recapLoading || recap) && (
        <Card>
          <CardHeader>
            <CardTitle>
              {recap?.kind === "playoff"
                ? `${recap.round_label} Recap`
                : recap
                  ? `Week ${recap.week} Recap`
                  : "Week Recap"}
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <LoadingOverlay active={recapLoading} hasContent={false} label="Loading recap">
              {recap?.kind === "playoff" && (
                <div className="flex flex-col gap-4">
                  {recap.champion && (
                    <div className="flex flex-col gap-1 rounded-sm border border-border bg-secondary/40 px-3 py-2">
                      <span className="label">
                        Champion
                      </span>
                      <p className="text-base font-bold text-gold">🏆 {recap.champion}</p>
                      {recap.final_standings && (
                        <p className="text-sm text-muted-foreground">
                          {Object.entries(recap.final_standings)
                            .sort(([a], [b]) => Number(a) - Number(b))
                            .map(([place, team]) => `${place}. ${team}`)
                            .join("  •  ")}
                        </p>
                      )}
                    </div>
                  )}
                  <div className="flex flex-col gap-1">
                    <span className="label">
                      Results
                    </span>
                    <ul className="flex flex-col gap-1">
                      {recap.matchups.map((m, i) => {
                        // m.wins/m.losses are team1's perspective (matches
                        // playoff_brackets.json directly) -- flip to the
                        // WINNER's perspective so the score reads correctly
                        // next to the (backend-computed) narrative sentence.
                        const team1Won = m.winner === m.team1;
                        const [winnerScore, loserScore] = team1Won
                          ? [m.wins, m.losses]
                          : [m.losses, m.wins];
                        return (
                          <li key={i} className="text-sm">
                            {m.slot ? <span className="text-muted-foreground">{m.slot}: </span> : null}
                            <span className="font-bold">{m.winner}</span> {m.verb_phrase} {m.loser} to{" "}
                            {m.advancement}{" "}
                            <span className="text-muted-foreground">
                              ({winnerScore}-{loserScore}
                              {m.ties > 0 ? `-${m.ties}` : ""})
                            </span>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                  {recap.byes.length > 0 && (
                    <div className="flex flex-col gap-1">
                      <span className="label">
                        Byes
                      </span>
                      <p className="text-sm text-muted-foreground">{recap.byes.join(", ")}</p>
                    </div>
                  )}
                </div>
              )}
              {recap && recap.kind !== "playoff" && (
                <div className="flex flex-col gap-4">
                  {recap.beatdowns.length > 0 && (
                    <div className="flex flex-col gap-1">
                      <span className="label">
                        Beatdowns
                      </span>
                      <ul className="flex flex-col gap-1">
                        {recap.beatdowns.map((s, i) => (
                          <li key={i} className="text-sm">
                            • {s}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {recap.upsets.length > 0 && (
                    <div className="flex flex-col gap-1">
                      <span className="label">
                        Upsets
                      </span>
                      <ul className="flex flex-col gap-1">
                        {recap.upsets.map((s, i) => (
                          <li key={i} className="text-sm">
                            • {s}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {recap.milestones.length > 0 && (
                    <div className="flex flex-col gap-1">
                      <span className="label">
                        Milestones
                      </span>
                      <ul className="flex flex-col gap-1">
                        {recap.milestones.map((s, i) => (
                          <li key={i} className="text-sm">
                            • {s}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {recap.playoff_race && (
                    <div className="flex flex-col gap-1">
                      <span className="label">
                        Playoff Race
                      </span>
                      <p className="text-sm text-muted-foreground">{recap.playoff_race}</p>
                    </div>
                  )}
                </div>
              )}
            </LoadingOverlay>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function BackendUnreachable({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Backend unreachable</CardTitle>
        <CardDescription>
          Couldn&apos;t reach {API_BASE_URL}. Start it with:
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        <code className="rounded bg-muted px-2 py-1 text-xs">
          .venv-dashboard/bin/uvicorn dashboard_site.api.app:app --port 8090
        </code>
        <p className="text-sm text-muted-foreground">{message}</p>
      </CardContent>
    </Card>
  );
}
