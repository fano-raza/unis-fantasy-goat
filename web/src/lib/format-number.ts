// App-wide number display rule (user request, 2026-10-25): any non-integer
// strictly between -1 and 1 (FG%/FT%, 0-1 ratings, ...) always shows exactly
// 3 decimal places. Larger values use `decimalsAbove1`, or are left as-is
// when it's omitted. Integers render as integers.
export function formatNumber(value: number, decimalsAbove1?: number): string {
  if (Number.isInteger(value)) return String(value);
  if (Math.abs(value) < 1) return value.toFixed(3);
  return decimalsAbove1 === undefined ? String(value) : value.toFixed(decimalsAbove1);
}
