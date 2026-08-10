// Generates N visually-distinct qualitative colors by rotating hue -- enough
// for up to ~11 teams (the league's roster size) without repeats.
export function categoricalPalette(n: number): string[] {
  return Array.from({ length: n }, (_, i) => {
    const hue = Math.round((360 / Math.max(n, 1)) * i);
    return `hsl(${hue} 70% 62%)`;
  });
}
