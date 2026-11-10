import type { RGB } from './braille';

// Colours, as RGB triples, plus the ANSI escape helpers that turn them into
// truecolor terminal sequences. One amber 'phosphor' palette for text and map.

// Amber phosphor palette. Map colours are kept dark so text stays the brightest thing on screen.
export const C = {
  bg: [14, 10, 4] as RGB,
  text: [255, 176, 0] as RGB,
  dim: [170, 112, 20] as RGB,
  faint: [110, 72, 18] as RGB,
  bright: [255, 222, 140] as RGB,
  roadMajor: [190, 132, 46] as RGB,
  roadMinor: [104, 74, 32] as RGB,
  roadPath: [62, 46, 22] as RGB,
  water: [8, 32, 62] as RGB,
  park: [20, 38, 14] as RGB,
  route: [255, 250, 220] as RGB,
  hotel: [255, 255, 255] as RGB,
  dest: [255, 90, 60] as RGB,
  warn: [255, 110, 70] as RGB,
};

// Walk-time bands (5, 10, 15 min): FG colours restaurant markers, BG tints the H3 cells.
// Nearest is hottest.
const BAND_FG: RGB[] = [[255, 236, 120], [255, 170, 40], [215, 105, 30]];
const BAND_BG: RGB[] = [[104, 66, 0], [70, 40, 4], [46, 24, 8]];

/** Marker colour for a band edge (5, 10 or 15) within the active band list. */
export function bandColor(b: number, bands: number[]): RGB {
  const i = bands.indexOf(b);
  return BAND_FG[Math.max(0, Math.min(BAND_FG.length - 1, i))];
}
/** Background tint for H3 cells in a band. */
export function bandTint(b: number, bands: number[]): RGB {
  const i = bands.indexOf(b);
  return BAND_BG[Math.max(0, Math.min(BAND_BG.length - 1, i))];
}

// ANSI helpers: 38;2 sets the foreground, 48;2 the background (24-bit colour).
export const hex = (c: RGB) => '#' + c.map((v) => v.toString(16).padStart(2, '0')).join('');
export const fg = (c: RGB) => `\x1b[38;2;${c[0]};${c[1]};${c[2]}m`;
export const bgc = (c: RGB) => `\x1b[48;2;${c[0]};${c[1]};${c[2]}m`;
export const RESET = '\x1b[0m';
export const BOLD = '\x1b[1m';
