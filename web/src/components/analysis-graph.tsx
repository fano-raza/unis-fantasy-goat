"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { AnalysisRow } from "@/lib/api";
import { ANALYSIS_FIELDS, DEFAULT_X_FIELD, getField } from "@/lib/fields";
import { categoricalPalette } from "@/lib/palette";
import { pivot, pivotScatter, type GroupBy } from "@/lib/pivot";
import { cn } from "@/lib/utils";
import { X } from "lucide-react";

interface AnalysisGraphProps {
  id: number;
  rows: AnalysisRow[];
  allYears: number[];
  onRemove?: () => void;
}

interface GraphParams {
  xKey: string;
  yKey: string;
  groupBy: GroupBy;
}

const DEFAULT_PARAMS: GraphParams = {
  xKey: DEFAULT_X_FIELD,
  yKey: "overall_rating",
  groupBy: { team: true, season: false },
};

// Above this many series with a value at a single x-tick, Recharts' built-in
// <Tooltip> becomes the perf problem documented in the plan doc's "Perf
// follow-up" session log entry -- its per-mousemove nearest-point payload
// assembly scales with series count (~90 at worst here), independent of what
// a custom `content` renderer chooses to draw. Past that threshold we don't
// mount <Tooltip> at all; see the dense-mode hotspots below instead.
const DENSE_THRESHOLD = 15;

function isValidGraphParams(value: unknown): value is GraphParams {
  if (!value || typeof value !== "object") return false;
  const v = value as Partial<GraphParams>;
  return (
    ANALYSIS_FIELDS.some((f) => f.key === v.xKey) &&
    ANALYSIS_FIELDS.some((f) => f.key === v.yKey) &&
    typeof v.groupBy === "object"
  );
}

export function AnalysisGraph({ id, rows, allYears, onRemove }: AnalysisGraphProps) {
  const storageKey = `analysis-graph-${id}`;

  // "draft" reflects the controls as the user edits them; "applied" is what
  // actually feeds the pivot/chart -- kept separate so picking a new field or
  // toggling group-by doesn't recompute/re-render on every click. With ~1,400
  // rows and up to ~90 series (11 teams x 8 seasons), that recompute is the
  // thing that was making the page feel slow.
  const [draft, setDraft] = useState<GraphParams>(DEFAULT_PARAMS);
  const [applied, setApplied] = useState<GraphParams>(DEFAULT_PARAMS);
  const [hoveredEdge, setHoveredEdge] = useState<"min" | "max" | null>(null);
  const [hydrated, setHydrated] = useState(false);

  // Synchronous hydrate + a `hydrated` flag flipped in the same effect pass
  // -- see the identical comment in comparison/page.tsx. Without this guard,
  // React's dev-mode double-effect-invocation reads localStorage a second
  // time AFTER the persist-effect below has already clobbered it with
  // DEFAULT_PARAMS, permanently losing the saved value (confirmed via a
  // debug trace, not just theorized).
  useEffect(() => {
    try {
      const raw = localStorage.getItem(storageKey);
      if (raw) {
        const saved = JSON.parse(raw);
        if (isValidGraphParams(saved)) {
          setDraft(saved);
          setApplied(saved);
        }
      }
    } catch {}
    setHydrated(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey]);

  useEffect(() => {
    if (!hydrated) return;
    localStorage.setItem(storageKey, JSON.stringify(applied));
  }, [storageKey, applied, hydrated]);

  const xField = getField(applied.xKey);
  const yField = getField(applied.yKey);

  // Season/Week is a natural progression, worth connecting with a line;
  // any other X (a stat/rating/rank) renders as an unconnected scatter --
  // see pivot.ts's pivotScatter for why bucketing/connecting those is
  // actively misleading.
  const isTimeAxis = xField.key === "year" || xField.key === "week";

  const { chartData, seriesKeys } = useMemo(
    () => (isTimeAxis ? pivot(rows, xField, yField, applied.groupBy) : { chartData: [], seriesKeys: [] }),
    [rows, xField, yField, applied.groupBy, isTimeAxis],
  );
  const scatterSeries = useMemo(
    () => (isTimeAxis ? [] : pivotScatter(rows, xField, yField, applied.groupBy)),
    [rows, xField, yField, applied.groupBy, isTimeAxis],
  );
  const activeSeriesKeys = isTimeAxis ? seriesKeys : scatterSeries.map((s) => s.key);
  const hasData = isTimeAxis ? chartData.length > 0 : scatterSeries.some((s) => s.points.length > 0);
  const colors = useMemo(() => categoricalPalette(activeSeriesKeys.length), [activeSeriesKeys.length]);

  // Precomputed once per data change, not per mousemove -- see DENSE_THRESHOLD.
  const { maxPointCount, minRow, maxRow } = useMemo(() => {
    let max = 0;
    for (const row of chartData) {
      max = Math.max(max, Object.keys(row).length - 1);
    }
    return {
      maxPointCount: max,
      minRow: chartData[0],
      maxRow: chartData[chartData.length - 1],
    };
  }, [chartData]);
  const isDense = maxPointCount > DENSE_THRESHOLD;

  const isDirty =
    draft.xKey !== applied.xKey ||
    draft.yKey !== applied.yKey ||
    draft.groupBy.team !== applied.groupBy.team ||
    draft.groupBy.season !== applied.groupBy.season;

  return (
    <Card>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-4">
          <FieldSelect
            label="X axis"
            value={draft.xKey}
            onValueChange={(xKey) => setDraft((d) => ({ ...d, xKey }))}
          />
          <FieldSelect
            label="Y axis"
            value={draft.yKey}
            onValueChange={(yKey) => setDraft((d) => ({ ...d, yKey }))}
          />
          <div className="flex items-center gap-3 text-[11px] font-bold tracking-wider uppercase">
            <span className="text-muted-foreground">Group by</span>
            <label className="flex items-center gap-1.5">
              <Checkbox
                checked={draft.groupBy.team}
                onCheckedChange={() =>
                  setDraft((d) => ({ ...d, groupBy: { ...d.groupBy, team: !d.groupBy.team } }))
                }
              />
              Team
            </label>
            <label className="flex items-center gap-1.5">
              <Checkbox
                checked={draft.groupBy.season}
                onCheckedChange={() =>
                  setDraft((d) => ({
                    ...d,
                    groupBy: { ...d.groupBy, season: !d.groupBy.season },
                  }))
                }
              />
              Season
            </label>
          </div>
          <Button size="sm" disabled={!isDirty} onClick={() => setApplied(draft)}>
            Update
          </Button>
          {onRemove && (
            <Button
              variant="ghost"
              size="icon-sm"
              className="ml-auto"
              onClick={onRemove}
              aria-label="Remove graph"
            >
              <X className="size-4" />
            </Button>
          )}
        </div>

        {!hasData ? (
          <p className="text-sm text-muted-foreground">No data for the current filters.</p>
        ) : isTimeAxis ? (
          <div className="relative h-[440px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ left: 8, right: 16, top: 8, bottom: 24 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis
                  dataKey="x"
                  name={xField.label}
                  type="number"
                  domain={["dataMin", "dataMax"]}
                  ticks={xField.key === "year" ? allYears : undefined}
                  tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
                  stroke="var(--border)"
                  label={{
                    value: xField.label,
                    position: "insideBottom",
                    offset: -4,
                    fill: "var(--muted-foreground)",
                    fontSize: 12,
                  }}
                />
                <YAxis
                  name={yField.label}
                  width={56}
                  tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
                  stroke="var(--border)"
                  label={{
                    value: yField.label,
                    angle: -90,
                    position: "insideLeft",
                    fill: "var(--muted-foreground)",
                    fontSize: 12,
                  }}
                />
                {seriesKeys.length > 1 && !(applied.groupBy.team && applied.groupBy.season) && (
                  <Legend wrapperStyle={{ color: "var(--muted-foreground)", fontSize: 12 }} />
                )}
                {!isDense && (
                  <Tooltip
                    isAnimationActive={false}
                    cursor={{ stroke: "var(--border)" }}
                    contentStyle={{
                      background: "var(--card)",
                      border: "1px solid var(--border)",
                      fontSize: 12,
                    }}
                    labelFormatter={(x) => `${xField.label}: ${x}`}
                    formatter={(value, name) => [
                      typeof value === "number" ? value.toFixed(2) : String(value),
                      name,
                    ]}
                  />
                )}
                {seriesKeys.map((key, i) => (
                  <Line
                    key={key}
                    dataKey={key}
                    name={key}
                    stroke={colors[i]}
                    connectNulls={false}
                    dot={{ r: 2 }}
                    activeDot={false}
                    isAnimationActive={false}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>

            {isDense && minRow && maxRow && (
              <>
                <div
                  className="absolute top-2 bottom-8 left-14 w-6"
                  onMouseEnter={() => setHoveredEdge("min")}
                  onMouseLeave={() => setHoveredEdge(null)}
                />
                <div
                  className="absolute top-2 right-4 bottom-8 w-6"
                  onMouseEnter={() => setHoveredEdge("max")}
                  onMouseLeave={() => setHoveredEdge(null)}
                />
                {hoveredEdge && (
                  <EdgeTooltip
                    className={hoveredEdge === "min" ? "left-16" : "right-8"}
                    xLabel={xField.label}
                    row={hoveredEdge === "min" ? minRow : maxRow}
                    seriesKeys={seriesKeys}
                  />
                )}
              </>
            )}
          </div>
        ) : (
          // Continuous X (a stat/rating/rank): unconnected scatter, every
          // row plotted individually (see pivotScatter). Tooltip
          // intentionally omitted here -- up to ~150 points x up to 88
          // series in the worst case (Team+Season on a continuous field),
          // and re-deriving the dense-hover system built for the line case
          // above is real additional perf-risk surface out of scope for
          // this fix (see the plan doc).
          <div className="h-[440px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ left: 8, right: 16, top: 8, bottom: 24 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis
                  dataKey="x"
                  name={xField.label}
                  type="number"
                  domain={["dataMin", "dataMax"]}
                  tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
                  stroke="var(--border)"
                  label={{
                    value: xField.label,
                    position: "insideBottom",
                    offset: -4,
                    fill: "var(--muted-foreground)",
                    fontSize: 12,
                  }}
                />
                <YAxis
                  dataKey="y"
                  name={yField.label}
                  width={56}
                  tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
                  stroke="var(--border)"
                  label={{
                    value: yField.label,
                    angle: -90,
                    position: "insideLeft",
                    fill: "var(--muted-foreground)",
                    fontSize: 12,
                  }}
                />
                {activeSeriesKeys.length > 1 && !(applied.groupBy.team && applied.groupBy.season) && (
                  <Legend wrapperStyle={{ color: "var(--muted-foreground)", fontSize: 12 }} />
                )}
                {scatterSeries.map((s, i) => (
                  <Scatter
                    key={s.key}
                    name={s.key}
                    data={s.points}
                    fill={colors[i]}
                    isAnimationActive={false}
                  />
                ))}
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// Dense-chart hover content -- reads straight off the precomputed chartData
// row (already averaged/sorted by pivot()), no work happens on hover itself.
function EdgeTooltip({
  xLabel,
  row,
  seriesKeys,
  className,
}: {
  xLabel: string;
  row: Record<string, number>;
  seriesKeys: string[];
  className?: string;
}) {
  return (
    <div
      className={cn(
        "absolute top-2 z-10 min-w-36 rounded-sm border border-border bg-card p-2 text-xs shadow-md",
        className,
      )}
    >
      <div className="mb-1 font-bold tracking-wide text-muted-foreground uppercase">
        {xLabel}: {row.x}
      </div>
      <div className="flex flex-col gap-0.5">
        {seriesKeys
          .filter((key) => row[key] !== undefined)
          .map((key) => (
            <div key={key} className="flex items-center justify-between gap-3">
              <span className="text-muted-foreground">{key}</span>
              <span className="font-mono tabular-nums">{row[key].toFixed(2)}</span>
            </div>
          ))}
      </div>
    </div>
  );
}

function FieldSelect({
  label,
  value,
  onValueChange,
}: {
  label: string;
  value: string;
  onValueChange: (value: string) => void;
}) {
  const groups = ["General", "Stats", "Ratings", "Ranks"] as const;
  return (
    <label className="flex items-center gap-2">
      <span className="text-[11px] font-bold tracking-wider text-muted-foreground uppercase">
        {label}
      </span>
      <Select value={value} onValueChange={(v) => v !== null && onValueChange(v)}>
        <SelectTrigger size="sm">
          <SelectValue>{(v: string) => getField(v).label}</SelectValue>
        </SelectTrigger>
        <SelectContent>
          {groups.map((group) => (
            <SelectGroup key={group}>
              <SelectLabel>{group}</SelectLabel>
              {ANALYSIS_FIELDS.filter((f) => f.group === group).map((f) => (
                <SelectItem key={f.key} value={f.key}>
                  {f.label}
                </SelectItem>
              ))}
            </SelectGroup>
          ))}
        </SelectContent>
      </Select>
    </label>
  );
}
