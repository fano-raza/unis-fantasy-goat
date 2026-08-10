// A plain, normal-flow legend row instead of recharts' built-in <Legend>.
// Recharts positions its Legend with `bottom: <margin.bottom>px` inside the
// chart's own fixed-height container -- that ties it to the same offset the
// X-axis title uses, so no combination of chart margin or container height
// can separate them (confirmed empirically: identical overlap at every
// value tried). Rendering the legend as a normal sibling below the chart
// container sidesteps the whole class of bug.
export function ChartLegend({ items }: { items: { key: string; color: string }[] }) {
  if (items.length <= 1) return null;
  return (
    <div className="flex flex-wrap justify-center gap-x-4 gap-y-1 px-2 pt-1 text-xs text-muted-foreground">
      {items.map((item) => (
        <span key={item.key} className="flex items-center gap-1.5">
          <span className="size-2.5 shrink-0 rounded-full" style={{ background: item.color }} />
          {item.key}
        </span>
      ))}
    </div>
  );
}
