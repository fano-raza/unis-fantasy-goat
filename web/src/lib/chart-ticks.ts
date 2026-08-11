// "Nice" tick generation for continuous stat/rating axes -- every tick must
// land on a multiple of 0.25 (the spec's hard floor for tick granularity),
// preferring whole-number steps when the data range is large enough to
// support them without producing too few or too many ticks.
const FRACTIONAL_STEPS = [0.25, 0.5, 1];
const INTEGER_STEP_MULTIPLES = [1, 2, 5];

export function niceTicks(min: number, max: number, targetCount = 6): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max) || min === max) {
    return [Math.round(min / 0.25) * 0.25];
  }

  const range = max - min;
  const rawStep = range / Math.max(1, targetCount);

  let step: number;
  if (rawStep <= 1) {
    step = FRACTIONAL_STEPS.find((s) => s >= rawStep) ?? 1;
  } else {
    const magnitude = 10 ** Math.floor(Math.log10(rawStep));
    step = INTEGER_STEP_MULTIPLES.map((m) => m * magnitude).find((s) => s >= rawStep) ?? 10 * magnitude;
  }

  const niceMin = Math.floor(min / step) * step;
  const ticks: number[] = [];
  for (let t = niceMin; t <= max + step * 0.001; t += step) {
    // Round off float drift (e.g. 0.1 + 0.2 !== 0.3), snapped to the 0.25 grid.
    ticks.push(Math.round(t / 0.25) * 0.25);
  }
  return ticks;
}
