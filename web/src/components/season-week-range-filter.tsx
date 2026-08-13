"use client";

import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { SourceLastUpdated } from "@/components/source-last-updated";

// Week-range Slider + Show Graph switch, shared by all 3 Standings sub-pages
// (Season Standings, League Wins, Ratings) -- purely presentational, no
// shared state (each page owns its own year/weekRange/showGraph
// independently, per the user's explicit "no filter carryover between
// sub-views" decision).
export function SeasonWeekRangeFilter({
  weekRange,
  onWeekRangeChange,
  maxWeek,
  showGraph,
  onShowGraphChange,
}: {
  weekRange: [number, number];
  onWeekRangeChange: (value: [number, number]) => void;
  maxWeek: number;
  showGraph: boolean;
  onShowGraphChange: (value: boolean) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Standings</CardTitle>
        <CardDescription>Regular-season standings for any week range</CardDescription>
        <CardAction>
          <SourceLastUpdated source="live" />
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <div className="flex flex-col gap-3">
          <span className="text-[11px] font-bold tracking-wider text-muted-foreground uppercase">
            Week {weekRange[0]} &ndash; Week {weekRange[1]}
          </span>
          <Slider
            min={1}
            max={maxWeek}
            step={1}
            minStepsBetweenValues={1}
            value={weekRange}
            onValueChange={(v) => onWeekRangeChange(v as [number, number])}
            thumbLabels={[`Week ${weekRange[0]}`, `Week ${weekRange[1]}`]}
          />
        </div>
        <label className="flex items-center gap-2 self-start text-[11px] font-bold tracking-wider uppercase">
          <span className="text-muted-foreground">Hide Graph</span>
          <Switch checked={showGraph} onCheckedChange={onShowGraphChange} />
          <span className="text-muted-foreground">Show Graph</span>
        </label>
      </CardContent>
    </Card>
  );
}
