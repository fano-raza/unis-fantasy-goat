// App-wide number display rule (user request, 2026-10-25; refined
// 2026-10-30): any non-integer strictly between -1 and 1 (FG%/FT%, 0-1
// ratings, ...) shows exactly 3 decimal places; anything larger shows 2,
// unless the caller asks for a specific `decimalsAbove1`. Integers render
// as integers.
export function formatNumber(value: number, decimalsAbove1 = 2): string {
  if (Number.isInteger(value)) return String(value);
  if (Math.abs(value) < 1) return value.toFixed(3);
  return value.toFixed(decimalsAbove1);
}
