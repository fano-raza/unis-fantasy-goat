import {
  getAverages,
  getCategoryHistory,
  getLeagueMeta,
  getPlayoffBrackets,
  getQuery,
  getTeamSummary,
  getTotals,
} from "@/lib/api";
import { ProfileView, type ProfileBootstrap } from "@/components/profile-view";
import { PROFILE_QUERY_TOTAL_FIELDS as QUERY_TOTAL_FIELDS } from "@/lib/query-total-fields";

// See app/page.tsx for the full rationale on this pattern.
export const revalidate = 30;

export default async function ProfilePage() {
  let initialBootstrap: ProfileBootstrap | null = null;
  try {
    const next = { revalidate: 30 };
    const [meta, allTeams, totals, averages, categoryHistory, brackets, queryEntries] = await Promise.all([
      getLeagueMeta({ next }),
      getTeamSummary({}, { next }),
      getTotals({}, { next }),
      getAverages({}, { next }),
      getCategoryHistory({ next }),
      getPlayoffBrackets({ next }).catch(() => ({})),
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
      brackets,
      queryTotals: Object.fromEntries(queryEntries),
    };
  } catch {
    // Backend unreachable at render time -- ProfileView falls back to its
    // own client-side fetch.
  }
  return <ProfileView initialBootstrap={initialBootstrap} />;
}
