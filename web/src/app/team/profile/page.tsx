import {
  getAverages,
  getCategoryHistory,
  getLeagueMeta,
  getQuery,
  getTeamSummary,
  getTotals,
} from "@/lib/api";
import { ProfileView, QUERY_TOTAL_FIELDS, type ProfileBootstrap } from "@/components/profile-view";

// See app/page.tsx for the full rationale on this pattern.
export const revalidate = 30;

export default async function ProfilePage() {
  let initialBootstrap: ProfileBootstrap | null = null;
  try {
    const next = { revalidate: 30 };
    const [meta, allTeams, totals, averages, categoryHistory, queryEntries] = await Promise.all([
      getLeagueMeta({ next }),
      getTeamSummary({}, { next }),
      getTotals({}, { next }),
      getAverages({}, { next }),
      getCategoryHistory({ next }),
      Promise.all(
        QUERY_TOTAL_FIELDS.map((f) =>
          getQuery(
            { metric: f.metric, aggregation: "sum", group_by: ["Team"], seasons: f.seasons, limit: 50 },
            { next },
          ).then((res) => [f.label, res.rows] as const),
        ),
      ),
    ]);
    initialBootstrap = {
      meta,
      allTeams,
      totals,
      averages,
      categoryHistory,
      queryTotals: Object.fromEntries(queryEntries),
    };
  } catch {
    // Backend unreachable at render time -- ProfileView falls back to its
    // own client-side fetch.
  }
  return <ProfileView initialBootstrap={initialBootstrap} />;
}
