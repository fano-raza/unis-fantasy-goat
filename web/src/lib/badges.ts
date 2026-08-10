import { MAIN_CATS, type Category, type CategoryHistoryResponse, type TeamSummary } from "./api";

export interface BadgeInstance {
  id: string;
  icon: string; // emoji glyph, or "L" for RS Last Place (no clean emoji fits)
  label: string; // e.g. "PTS Leader" or "Championship" -- shown with the year on hover/tap
  year: number;
  positive: boolean;
  type: string; // groups badges of the same kind together regardless of year -- see BADGE_TYPE_ORDER
}

// Best-effort emoji picks for the user's spec -- FT% loser has no exact
// Unicode match ("Shaquille O'Neal"), a reasonable stand-in, easy to swap
// in this one table if the wrong call.
const CATEGORY_BADGE_ICONS: Record<Category, { leader: string; loser: string }> = {
  "FG%": { leader: "🎯", loser: "🧱" },
  "FT%": { leader: "🧘", loser: "😬" },
  "3PTM": { leader: "3️⃣", loser: "👴" },
  REB: { leader: "🧲", loser: "🧈" },
  AST: { leader: "👓", loser: "🙈" },
  STL: { leader: "🥷", loser: "👮" },
  BLK: { leader: "✋", loser: "🕳️" },
  TO: { leader: "🧤", loser: "🤲" },
  PTS: { leader: "🔥", loser: "🧊" },
};

// Display order: non-stat-leader ("other") badges first, then the 9
// categories in this app's usual MAIN_CATS order. Badges of the same type
// are grouped together regardless of year (sortBadges below sorts by this
// index first, year only as the tiebreak within a type).
const BADGE_TYPE_ORDER = [
  "Championship",
  "Runner-Up",
  "MVP",
  "RS 1st Place",
  "Worst Rating",
  "RS Last Place",
  ...MAIN_CATS.flatMap((cat) => [`${cat} Leader`, `${cat} Loser`]),
];

// Every distinct positive badge *type* that can possibly exist (4 "other"
// achievements + one Leader badge per category) -- the denominator for the
// Profile page's "Unique Badges" counter, e.g. "6/13".
export const POSITIVE_BADGE_TYPES = [
  "Championship",
  "Runner-Up",
  "MVP",
  "RS 1st Place",
  ...MAIN_CATS.map((cat) => `${cat} Leader`),
];

function parseYears(value: string | number | null | undefined): number[] {
  if (typeof value !== "string" || !value.trim()) return [];
  return value
    .split(",")
    .map((s) => Number(s.trim()))
    .filter((n) => !Number.isNaN(n));
}

// Per-category league leader/lowest badges, one instance per (category,
// year) the team actually led or was lowest in -- a team with several such
// years gets several badges, not one badge with a count.
function categoryBadges(team: string, history: CategoryHistoryResponse): BadgeInstance[] {
  const badges: BadgeInstance[] = [];
  for (const [yearStr, cats] of Object.entries(history)) {
    const year = Number(yearStr);
    for (const cat of MAIN_CATS) {
      const entry = cats[cat];
      if (!entry) continue;
      const icons = CATEGORY_BADGE_ICONS[cat];
      if (entry.best.team === team) {
        const type = `${cat} Leader`;
        badges.push({ id: `${cat}-leader-${year}`, icon: icons.leader, label: type, year, positive: true, type });
      }
      if (entry.worst.team === team) {
        const type = `${cat} Loser`;
        badges.push({ id: `${cat}-loser-${year}`, icon: icons.loser, label: type, year, positive: false, type });
      }
    }
  }
  return badges;
}

// Championship/Runner-Up/MVP/Worst-Rating/RS-1st/RS-Last, one badge per
// year -- sourced from team_summary.csv fields already on the profile row.
// Runner-Up isn't its own team_summary column: "Finals Years" includes both
// the champion and the runner-up year, so it's Finals minus Championship.
function otherBadges(profile: TeamSummary): BadgeInstance[] {
  const badges: BadgeInstance[] = [];
  const champYears = new Set(parseYears(profile["Championship Years"]));
  const runnerUpYears = parseYears(profile["Finals Years"]).filter((y) => !champYears.has(y));

  for (const y of champYears) badges.push({ id: `champ-${y}`, icon: "🏆", label: "Championship", year: y, positive: true, type: "Championship" });
  for (const y of runnerUpYears) badges.push({ id: `runnerup-${y}`, icon: "🥈", label: "Runner-Up", year: y, positive: true, type: "Runner-Up" });
  for (const y of parseYears(profile["MVP Years"])) badges.push({ id: `mvp-${y}`, icon: "⭐", label: "MVP", year: y, positive: true, type: "MVP" });
  for (const y of parseYears(profile["RS 1st Years"])) badges.push({ id: `rs1st-${y}`, icon: "🥇", label: "RS 1st Place", year: y, positive: true, type: "RS 1st Place" });
  for (const y of parseYears(profile["Worst Rating Years"])) badges.push({ id: `worstrating-${y}`, icon: "🗑️", label: "Worst Rating", year: y, positive: false, type: "Worst Rating" });
  for (const y of parseYears(profile["RS Last Years"])) badges.push({ id: `rslast-${y}`, icon: "L", label: "RS Last Place", year: y, positive: false, type: "RS Last Place" });

  return badges;
}

// Grouped by type first (non-stat-leader "other" badges before the 9
// category badges, per BADGE_TYPE_ORDER), year descending within a type.
function sortBadges(badges: BadgeInstance[]): BadgeInstance[] {
  return [...badges].sort((a, b) => {
    const typeDiff = BADGE_TYPE_ORDER.indexOf(a.type) - BADGE_TYPE_ORDER.indexOf(b.type);
    return typeDiff !== 0 ? typeDiff : b.year - a.year;
  });
}

export function buildBadges(
  team: string,
  profile: TeamSummary,
  history: CategoryHistoryResponse,
): { positive: BadgeInstance[]; negative: BadgeInstance[] } {
  const all = [...categoryBadges(team, history), ...otherBadges(profile)];
  return {
    positive: sortBadges(all.filter((b) => b.positive)),
    negative: sortBadges(all.filter((b) => !b.positive)),
  };
}
