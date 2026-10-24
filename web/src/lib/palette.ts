// Fixed-order categorical palette for team/series lines, stepped for the
// app's dark card surface (#141e2b). Replaces the old evenly-rotated hues,
// which put three neighbouring teams in near-identical greens.
//
// Validated with the dataviz skill's validate_palette.js (--mode dark
// --surface #141e2b): every slot inside the lightness band and chroma floor,
// >= 3:1 against the surface, worst adjacent CVD dE 8.4 / normal-vision dE
// 19.1. Slots 1-8 are the skill's reference dark palette; 9-11 were added
// for the league's 10-11 teams and re-validated as a whole. Order matters --
// assign in sequence, never cycle or regenerate.
const CATEGORICAL = [
  "#3987e5", // blue
  "#d95926", // orange
  "#199e70", // aqua
  "#c98500", // yellow
  "#d55181", // magenta
  "#008300", // green
  "#9085e9", // violet
  "#e66767", // red
  "#1fa0be", // cyan
  "#8f9a2c", // olive
  "#c06fd0", // orchid
];

export function categoricalPalette(n: number): string[] {
  // Past the validated set, fall back to muted grey rather than inventing
  // hues that can't be told apart.
  return Array.from({ length: n }, (_, i) => CATEGORICAL[i] ?? "#8d9db2");
}
