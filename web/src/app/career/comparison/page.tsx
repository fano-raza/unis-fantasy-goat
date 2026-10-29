import { getLeagueMeta, getQuery, getTeamSummary, type QueryRow } from "@/lib/api";
import { ComparisonView, type ComparisonBootstrap } from "@/components/comparison-view";
import { COMPARISON_QUERY_TOTAL_FIELDS as QUERY_TOTAL_FIELDS } from "@/lib/query-total-fields";

// See app/weekly-stats/page.tsx for the full rationale on this pattern.
export const revalidate = 30;

export default async function ComparisonPage() {
  let initialBootstrap: ComparisonBootstrap | null = null;
  try {
    const next = { revalidate: 30 };
    const [meta, allTeams, queryEntries] = await Promise.all([
      getLeagueMeta({ next }),
      getTeamSummary({}, { next }),
      Promise.all(
        QUERY_TOTAL_FIELDS.map((f) =>
          getQuery(
            { metric: f.metric, aggregation: "sum", group_by: ["Team"], seasons: f.seasons, limit: 50 },
            { next },
          ).then((res) => [f.label, res.rows] as const),
        ),
      ),
    ]);
    initialBootstrap = { meta, allTeams, queryTotals: Object.fromEntries(queryEntries) };
  } catch {
    // Backend unreachable at render time -- ComparisonView falls back to
    // its own client-side fetch.
  }
  return <ComparisonView initialBootstrap={initialBootstrap} />;
}
