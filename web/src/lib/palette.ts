// Fixed-order categorical palette for team/series lines. Returns CSS
// variables, not hexes, so every chart follows the viewer's light/dark mode
// with no JS -- the values live in globals.css as --series-1..11, stepped
// separately for each mode's card surface (Recharts passes these straight
// through to SVG stroke/fill, same as the existing var(--border) axes).
//
// Both steppings were validated with the dataviz skill's
// validate_palette.js against their card surface (#141e2b dark, #ffffff
// light): every slot inside the lightness band and chroma floor; worst
// adjacent CVD dE 8.4 dark / 9.1 light, normal-vision dE >= 18. Light slots
// 3-5 sit under 3:1 on white -- allowed because every chart here has a
// legend and its data is also shown in a table. Slots 1-8 are the skill's
// reference palette; 9-11 were added for the league's 10-11 teams. Order
// matters -- assign in sequence, never cycle or regenerate.
const SERIES_COUNT = 11;

export function categoricalPalette(n: number): string[] {
  // Past the validated set, fall back to muted grey rather than inventing
  // hues that can't be told apart.
  return Array.from({ length: n }, (_, i) =>
    i < SERIES_COUNT ? `var(--series-${i + 1})` : "var(--muted-foreground)",
  );
}
