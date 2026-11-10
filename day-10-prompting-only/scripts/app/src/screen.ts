// One scrolling terminal, the way the 80s did it: text runs down the screen,
// and when there is something to see, a picture is printed into the scroll.
// A picture can be redrawn in place (for animation) while it is still on screen.
import type { Term } from './term';
import { C, fg, RESET } from './theme';

export const FOOTER = 'Restaurants: TripAdvisor, scraped May 2021, so some will have closed. Walk times and routes: CARTO Location Data Services (TravelTime, TomTom). Map: © OpenStreetMap contributors, © CARTO.';

const visLen = (s: string) => [...s.replace(/\x1b\[[0-9;]*m/g, '')].length;

/** Truncate a styled string to n visible characters. */
export function clip(s: string, n: number): string {
  if (visLen(s) <= n) return s;
  let out = '', vis = 0;
  for (let i = 0; i < s.length; ) {
    const m = /^\x1b\[[0-9;]*m/.exec(s.slice(i));
    if (m) { out += m[0]; i += m[0].length; continue; }
    const ch = String.fromCodePoint(s.codePointAt(i)!);
    if (vis === n - 1) { out += '…'; break; }
    out += ch; vis++; i += ch.length;
  }
  return out;
}

export function wrap(text: string, width: number): string[] {
  const out: string[] = [];
  for (const para of text.split('\n')) {
    let line = '';
    for (const word of para.split(' ')) {
      if (!line) line = word;
      else if (visLen(line) + 1 + visLen(word) <= width) line += ' ' + word;
      else { out.push(line); line = word; }
    }
    out.push(line);
  }
  return out;
}

export interface Picture { rows: number; top: number }

export class Scroll {
  term: Term;
  /** lines printed since the last picture's bottom edge */
  private below = 0;
  private pic: Picture | null = null;

  constructor(term: Term) { this.term = term; }

  /** Width of running text. */
  get width() { return Math.min(this.term.cols - 2, 88); }
  /** Picture size in cells (inside the frame). */
  pictureSize(roomBelow = 10): { cols: number; rows: number } {
    return { cols: Math.min(this.term.cols - 4, 104), rows: Math.max(16, Math.min(30, this.term.rows - roomBelow)) };
  }

  private nl(n = 1) { this.below += n; }

  line(s = '', color = C.text) {
    for (const l of wrap(s, this.width)) { this.term.write(`${fg(color)}${l}${RESET}\n`); this.nl(); }
  }

  raw(s: string) { this.term.write(clip(s, this.term.cols - 1) + RESET + '\n'); this.nl(); }

  async type(s: string, color = C.text) {
    for (const l of wrap(s, this.width)) {
      this.term.write(fg(color));
      await this.term.type(l.length ? l : ' ');
      this.term.write(RESET);
      this.nl();
    }
  }

  gap() { this.term.write('\n'); this.nl(); }

  header(label: string) {
    const head = `┌─ ${label.toUpperCase()} `;
    this.raw(`${fg(C.dim)}${head}${'─'.repeat(Math.max(0, this.width - visLen(head) - 1))}┐`);
  }
  tick(label: string, value: string, color = C.text) {
    const dots = Math.max(1, this.width - 4 - visLen(label) - visLen(value) - 2);
    this.raw(`${fg(C.dim)}├ ${fg(color)}${label} ${fg(C.faint)}${'·'.repeat(dots)} ${fg(C.bright)}${value}`);
  }
  closeBox() { this.raw(`${fg(C.dim)}└${'─'.repeat(this.width - 2)}┘`); }

  /** Print a framed picture into the scroll. */
  picture(lines: string[], caption?: string) {
    const w = visLen(lines[0] ?? '');
    const edge = fg(C.faint);
    this.term.write(`${edge}┌${'─'.repeat(w)}┐${RESET}\n`);
    for (const l of lines) this.term.write(`${edge}│${l}${edge}│${RESET}\n`);
    this.term.write(`${edge}└${'─'.repeat(w)}┘${RESET}\n`);
    this.pic = { rows: lines.length, top: 0 };
    this.below = 0;
    if (caption) this.line(caption, C.faint);
  }

  /** Can the last picture still be redrawn in place? */
  canRedraw(extraLines = 0) {
    return !!this.pic && this.pic.rows + 1 + this.below + extraLines < this.term.rows;
  }

  /** Redraw the last picture in place; the cursor must be at the start of a line. */
  redraw(lines: string[]) {
    if (!this.pic || !this.canRedraw()) return false;
    const edge = fg(C.faint);
    let s = `\x1b[?25l\x1b[${this.below + 1 + this.pic.rows}F`;
    lines.forEach((l, i) => { s += `${edge}│${l}${edge}│${RESET}`; if (i < lines.length - 1) s += '\x1b[1E'; });
    s += `\x1b[${this.below + 2}E\x1b[?25h`;
    this.term.t.write(s);
    return true;
  }

  /** Overwrite the line just printed (cursor at start of the next line). */
  rewriteLast(s: string) {
    this.term.t.write(`\x1b[1F\x1b[2K${clip(s, this.term.cols - 1)}${RESET}\x1b[1E`);
  }

  async prompt(label = '>'): Promise<string> {
    const s = await this.term.prompt(label);
    this.nl();
    return s;
  }

  footer() { this.line(FOOTER, C.faint); }
}
