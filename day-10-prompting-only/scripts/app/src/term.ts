// xterm.js wrapper: typewriter output, a line-editing prompt, resize handling.
// Everything the player sees goes through here. Add ?fast to the URL to skip
// typewriter delays and animations (used for testing).
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import { C, hex, fg, RESET } from './theme';

export const MIN_COLS = 100;
export const MIN_ROWS = 36;

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export class Term {
  t: Terminal;
  fit: FitAddon;
  private resolveLine: ((s: string) => void) | null = null;
  private buf = '';
  private history: string[] = [];
  private hIdx = 0;
  private skipType = false;
  onResize: (() => void) | null = null;
  fast = new URLSearchParams(location.search).has('fast');

  constructor(el: HTMLElement) {
    this.t = new Terminal({
      fontFamily: '"Dinner Mono", monospace',
      fontSize: 15,
      lineHeight: 1,
      letterSpacing: 0,
      cursorBlink: true,
      cursorStyle: 'block',
      allowProposedApi: true,
      scrollback: 2000,
      customGlyphs: true,
      theme: {
        background: hex(C.bg),
        foreground: hex(C.text),
        cursor: hex(C.text),
        cursorAccent: hex(C.bg),
        selectionBackground: '#5a3d08',
      },
    });
    this.fit = new FitAddon();
    this.t.loadAddon(this.fit);
    this.t.open(el);
    this.fit.fit();
    let tm: number | undefined;
    window.addEventListener('resize', () => {
      clearTimeout(tm);
      tm = window.setTimeout(() => { this.fit.fit(); this.onResize?.(); }, 120);
    });
    this.t.onData((d) => this.handle(d));
    this.t.focus();
  }

  get cols() { return this.t.cols; }
  get rows() { return this.t.rows; }
  tooSmall() { return this.cols < MIN_COLS || this.rows < MIN_ROWS; }

  /**
   * Dot height / dot width in pixels, from the renderer's real cell size, so maps
   * keep true proportions whatever the font metrics. Falls back to the font's own
   * cell (1233 x 2384 units) if xterm's internals are not available.
   */
  dotAspect(): number {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const core = (this.t as any)._core;
    const d = core?._renderService?.dimensions?.css?.cell;
    if (d?.width && d?.height) return (d.height / 4) / (d.width / 2);
    return (2384 / 4) / (1233 / 2);
  }

  write(s: string) { this.t.write(s.replace(/\n/g, '\r\n')); }
  writeln(s = '') { this.write(s + '\n'); }

  /** Typewriter print; any key skips to the end. */
  async type(s: string, cps = 140) {
    if (this.fast) { this.writeln(s); return; }
    this.skipType = false;
    const delay = 1000 / cps;
    let i = 0;
    while (i < s.length) {
      if (this.skipType) { this.write(s.slice(i)); break; }
      // emit escape sequences whole
      if (s[i] === '\x1b') {
        const m = /^\x1b\[[0-9;]*m/.exec(s.slice(i));
        if (m) { this.write(m[0]); i += m[0].length; continue; }
      }
      this.write(s[i]);
      i++;
      if (s[i - 1] !== ' ') await sleep(delay);
    }
    this.writeln();
  }

  async pause(ms: number) { if (!this.fast) await sleep(ms); }

  prompt(label = '>'): Promise<string> {
    this.write(`${fg(C.bright)}${label}${RESET} ${fg(C.text)}`);
    this.buf = '';
    this.hIdx = this.history.length;
    return new Promise((res) => { this.resolveLine = res; });
  }

  /**
   * Keyboard input. While a prompt is open: Enter submits, Backspace edits, up/down
   * walk the history, Ctrl+C clears the line. Outside a prompt, any key skips the
   * typewriter to the end of the current line.
   */
  private handle(d: string) {
    if (!this.resolveLine) { this.skipType = true; return; }
    if (d === '\r') {
      const line = this.buf.trim();
      this.write(RESET + '\n');
      if (line) this.history.push(line);
      const r = this.resolveLine; this.resolveLine = null; r(line);
      return;
    }
    if (d === '\x7f' || d === '\b') {
      if (this.buf.length) { this.buf = this.buf.slice(0, -1); this.t.write('\b \b'); }
      return;
    }
    if (d === '\x1b[A' || d === '\x1b[B') {
      if (!this.history.length) return;
      this.hIdx = Math.max(0, Math.min(this.history.length, this.hIdx + (d === '\x1b[A' ? -1 : 1)));
      const next = this.history[this.hIdx] ?? '';
      this.t.write('\b \b'.repeat(this.buf.length) + next);
      this.buf = next;
      return;
    }
    if (d === '\x03') { this.t.write('^C'); this.buf = ''; this.handle('\r'); return; }
    if (d.startsWith('\x1b')) return;
    const printable = [...d].filter((c) => c >= ' ').join('');
    this.buf += printable;
    this.t.write(printable);
  }

  /** Resolve a pending prompt with a sentinel (used on resize). */
  cancelPrompt(token: string) {
    if (this.resolveLine) { const r = this.resolveLine; this.resolveLine = null; r(token); }
  }

  at(row: number, col: number) { this.t.write(`\x1b[${row};${col}H`); }

  clear() { this.t.write('\x1b[2J\x1b[3J\x1b[H'); this.t.clear(); }
}
