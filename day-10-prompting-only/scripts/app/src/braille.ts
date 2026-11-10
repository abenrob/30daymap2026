// Braille canvas: a dot grid of (cols*2) x (rows*4), packed into U+2800 cells,
// with per-cell truecolor foreground/background and glyph overlays.

export type RGB = [number, number, number];

// Braille cells are U+2800 + an 8-bit mask. Dots are numbered down the left column
// (1, 2, 3, then 7 at the bottom) and down the right column (4, 5, 6, then 8), so the
// bit for dot (dx, dy) inside a 2 x 4 cell is BIT[dy][dx].
const BIT = [
  [0x01, 0x08],
  [0x02, 0x10],
  [0x04, 0x20],
  [0x40, 0x80],
];

interface Overlay { ch: string; fg: RGB; bg?: RGB; bold?: boolean }

export class BrailleCanvas {
  readonly cols: number;
  readonly rows: number;
  readonly w: number;
  readonly h: number;
  private bits: Uint8Array;
  private fg: (RGB | null)[];
  private fgPri: Int16Array;
  private bg: (RGB | null)[];
  private bgPri: Int16Array;
  private over: (Overlay | null)[];

  constructor(cols: number, rows: number) {
    this.cols = cols; this.rows = rows;
    this.w = cols * 2; this.h = rows * 4;
    const n = cols * rows;
    this.bits = new Uint8Array(n);
    this.fg = new Array(n).fill(null);
    this.fgPri = new Int16Array(n).fill(-1);
    this.bg = new Array(n).fill(null);
    this.bgPri = new Int16Array(n).fill(-1);
    this.over = new Array(n).fill(null);
  }

  /** Set one dot. A cell has one foreground colour, so the highest-priority dot wins it. */
  dot(x: number, y: number, color: RGB, pri = 0) {
    x = Math.round(x); y = Math.round(y);
    if (x < 0 || y < 0 || x >= this.w || y >= this.h) return;
    const c = (y >> 2) * this.cols + (x >> 1);
    this.bits[c] |= BIT[y & 3][x & 1];
    if (pri >= this.fgPri[c]) { this.fg[c] = color; this.fgPri[c] = pri; }
  }

  /** Bresenham line in dot coordinates. */
  line(x0: number, y0: number, x1: number, y1: number, color: RGB, pri = 0) {
    x0 = Math.round(x0); y0 = Math.round(y0); x1 = Math.round(x1); y1 = Math.round(y1);
    // skip lines entirely off-canvas
    if ((x0 < 0 && x1 < 0) || (y0 < 0 && y1 < 0) || (x0 >= this.w && x1 >= this.w) || (y0 >= this.h && y1 >= this.h)) return;
    const dx = Math.abs(x1 - x0), dy = -Math.abs(y1 - y0);
    const sx = x0 < x1 ? 1 : -1, sy = y0 < y1 ? 1 : -1;
    let err = dx + dy, guard = 0;
    for (;;) {
      this.dot(x0, y0, color, pri);
      if ((x0 === x1 && y0 === y1) || ++guard > 20000) break;
      const e2 = 2 * err;
      if (e2 >= dy) { err += dy; x0 += sx; }
      if (e2 <= dx) { err += dx; y0 += sy; }
    }
  }

  /** Tint a cell's background (used for isochrone bands, water, parks). */
  cellBg(col: number, row: number, color: RGB, pri = 0) {
    if (col < 0 || row < 0 || col >= this.cols || row >= this.rows) return;
    const c = row * this.cols + col;
    if (pri >= this.bgPri[c]) { this.bg[c] = color; this.bgPri[c] = pri; }
  }

  /** Scanline-fill polygon rings (in dot coords) into cell backgrounds. */
  fillCells(rings: [number, number][][], color: RGB, pri = 0) {
    for (let row = 0; row < this.rows; row++) {
      const y = row * 4 + 2;
      const xs: number[] = [];
      for (const ring of rings) {
        for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
          const [xi, yi] = ring[i], [xj, yj] = ring[j];
          if ((yi > y) !== (yj > y)) xs.push(xi + ((y - yi) / (yj - yi)) * (xj - xi));
        }
      }
      xs.sort((a, b) => a - b);
      for (let k = 0; k + 1 < xs.length; k += 2) {
        const c0 = Math.max(0, Math.ceil((xs[k] - 1) / 2)), c1 = Math.min(this.cols - 1, Math.floor((xs[k + 1] - 1) / 2));
        for (let col = c0; col <= c1; col++) this.cellBg(col, row, color, pri);
      }
    }
  }

  /** Put a glyph (or a short string) over cells, starting at the cell holding dot (x, y). */
  glyphAtDot(x: number, y: number, text: string, fg: RGB, bg?: RGB, bold = false) {
    const col = Math.floor(x / 2), row = Math.floor(y / 4);
    this.text(col, row, text, fg, bg, bold);
  }

  text(col: number, row: number, text: string, fg: RGB, bg?: RGB, bold = false) {
    if (row < 0 || row >= this.rows) return;
    [...text].forEach((ch, i) => {
      const cc = col + i;
      if (cc < 0 || cc >= this.cols) return;
      this.over[row * this.cols + cc] = { ch, fg, bg, bold };
    });
  }

  /** One ANSI string per row. Escapes are only emitted when the colour changes. */
  render(defaultBg: RGB): string[] {
    const out: string[] = [];
    for (let r = 0; r < this.rows; r++) {
      let s = '', lastFg = '', lastBg = '', lastBold = false;
      for (let c = 0; c < this.cols; c++) {
        const i = r * this.cols + c;
        const o = this.over[i];
        let ch: string, fg: RGB, bg: RGB, bold = false;
        if (o) {
          ch = o.ch; fg = o.fg; bg = o.bg ?? this.bg[i] ?? defaultBg; bold = !!o.bold;
        } else {
          ch = String.fromCharCode(0x2800 + this.bits[i]);
          fg = this.fg[i] ?? defaultBg; bg = this.bg[i] ?? defaultBg;
        }
        const f = `\x1b[38;2;${fg[0]};${fg[1]};${fg[2]}m`;
        const b = `\x1b[48;2;${bg[0]};${bg[1]};${bg[2]}m`;
        if (bold !== lastBold) { s += bold ? '\x1b[1m' : '\x1b[22m'; lastBold = bold; }
        if (f !== lastFg) { s += f; lastFg = f; }
        if (b !== lastBg) { s += b; lastBg = b; }
        s += ch;
      }
      out.push(s + '\x1b[0m');
    }
    return out;
  }
}
