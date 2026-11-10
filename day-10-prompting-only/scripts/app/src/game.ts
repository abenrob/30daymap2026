// The adventure: a small state machine over prompts.
//
// Flow: hotel -> walk (the H3 isochrone animates) -> cuisine -> budget -> diet ->
// reputation -> search report -> either "slim pickings" (under 5 results, offer
// relaxations with counts) or paged results with a numbered map -> pick one ->
// the route animates with turn-by-turn directions -> play again.
//
// Global words (back, restart, quit) are turned into exceptions in ask(), so any
// step can be unwound from wherever the player typed them. Redraw is thrown when
// the window becomes too small mid-prompt; the step simply asks again.
import { db, type Filters, type Hotel, type Restaurant, type Step } from './carto';
import { Term } from './term';
import { Scroll } from './screen';
import { draw, fitView, bboxAround, bboxOf, baseFor, type View, type Scene } from './map';
import { C, fg, RESET, BOLD } from './theme';
import { bandColor } from './theme';
import type { LonLat } from './tiles';

const REDRAW = '\u0000redraw';
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

class Restart extends Error {}
class Back extends Error {}
class Quit extends Error {}
class Redraw extends Error {}

/** A menu entry: the value it sets, what is shown, and words that also select it. */
interface Option<T> { key: T; label: string; words: string[]; note?: string }

const WALKS: Option<number>[] = [
  { key: 5, label: 'A quick stroll: up to 5 minutes', words: ['5', 'five', 'quick', 'stroll'] },
  { key: 10, label: 'A proper walk: up to 10 minutes', words: ['10', 'ten', 'proper'] },
  { key: 15, label: 'Make an evening of it: up to 15 minutes', words: ['15', 'fifteen', 'evening', 'far'] },
];
const CUISINES: Option<string>[] = [
  { key: 'bistro', label: 'A bistro or brasserie', words: ['bistro', 'bistrot', 'brasserie', 'bouillon'] },
  { key: 'french', label: 'French, any style', words: ['french', 'francais', 'français'] },
  { key: 'italian', label: 'Italian or pizza', words: ['italian', 'pizza', 'pasta'] },
  { key: 'japanese', label: 'Japanese or sushi', words: ['japanese', 'sushi', 'ramen'] },
  { key: 'asian', label: 'Chinese, Vietnamese, Thai, Korean', words: ['asian', 'chinese', 'vietnamese', 'thai', 'korean', 'pho'] },
  { key: 'mediterranean', label: 'Mediterranean or Middle Eastern', words: ['mediterranean', 'lebanese', 'middle', 'greek', 'moroccan', 'turkish'] },
  { key: 'quick', label: 'Fast food or street food', words: ['fast', 'street', 'burger', 'quick'] },
  { key: 'bar', label: 'A bar or wine bar that feeds you', words: ['bar', 'wine', 'pub'] },
  { key: 'any', label: 'Surprise me', words: ['any', 'surprise', 'whatever', 'anything'] },
];
const PRICES: Option<number>[] = [
  { key: 1, label: '€     Cheap eats', words: ['€', 'cheap', '1€'] },
  { key: 2, label: '€€    Mid-range', words: ['€€', 'mid', 'middle', 'moderate'] },
  { key: 3, label: '€€€€  Fine dining', words: ['€€€€', 'fine', 'expensive', 'splurge', 'fancy'] },
  { key: 0, label: 'Money is no object (or any price)', words: ['any', 'whatever', 'all'] },
];
const DIETS: Option<string>[] = [
  { key: 'none', label: 'No, I eat everything', words: ['no', 'none', 'everything', 'n'] },
  { key: 'vegetarian', label: 'Vegetarian friendly', words: ['vegetarian', 'veggie'] },
  { key: 'vegan', label: 'Vegan options', words: ['vegan'] },
  { key: 'gluten_free', label: 'Gluten-free options', words: ['gluten', 'gf', 'coeliac', 'celiac'] },
];
const ACCOLADES: Option<string>[] = [
  { key: 'any', label: "I don't need a reputation", words: ['any', 'no', 'none', 'n'] },
  { key: 'travellers', label: "A TripAdvisor Travellers' Choice", words: ['travellers', 'travelers', 'choice', 'tripadvisor'] },
  { key: 'michelin', label: 'In the Michelin Guide (Bib, Plate or stars)', words: ['michelin', 'guide', 'bib'] },
  { key: 'stars', label: 'Michelin stars, nothing less', words: ['stars', 'star', 'starred'] },
];

/** Display label for a chosen value (for the search report). */
const label = <T>(opts: Option<T>[], k: T) => opts.find((o) => o.key === k)?.label.replace(/\s+/g, ' ').trim() ?? String(k);

export class Game {
  term: Term;
  scr: Scroll;
  hotels: Hotel[] = [];
  hotel!: Hotel;
  h3 = new Map<string, number>();
  f: Filters = { hotel: '', maxmin: 15, cuisine: 'any', price: 0, diet: 'none', accolade: 'any' };
  bands: number[] = [5, 10, 15];

  constructor(el: HTMLElement) {
    this.term = new Term(el);
    this.scr = new Scroll(this.term);
    this.term.onResize = () => { if (this.term.tooSmall()) this.term.cancelPrompt(REDRAW); };
  }

  // ---------- input helpers ----------
  /** Read a line; global commands become exceptions, help prints and asks again. */
  private async ask(label = '>'): Promise<string> {
    const s = await this.scr.prompt(label);
    if (s === REDRAW) throw new Redraw();
    const l = s.toLowerCase();
    if (l === 'restart' || l === 'start over') throw new Restart();
    if (l === 'back') throw new Back();
    if (l === 'quit' || l === 'exit') throw new Quit();
    if (l === 'help' || l === '?') { this.help(); return this.ask(label); }
    return s;
  }

  private help() {
    this.scr.line('Type a number or a word from the menu. You can also type:', C.bright);
    this.scr.line('  back     the previous question', C.dim);
    this.scr.line('  restart  start over from the hotel', C.dim);
    this.scr.line('  help     this list', C.dim);
    this.scr.line('  quit     leave the game', C.dim);
  }

  /** Print a numbered menu and loop until the answer is a number or one of the option's words. */
  private async choose<T>(question: string, opts: Option<T>[]): Promise<T> {
    this.scr.gap();
    if (question) await this.scr.type(question, C.bright);
    opts.forEach((o, i) => this.scr.raw(`${fg(C.bright)}${String(i + 1).padStart(3)}${fg(C.text)}  ${o.label}${o.note ? fg(C.faint) + '  ' + o.note : ''}`));
    for (;;) {
      const a = (await this.ask()).toLowerCase().trim();
      const n = Number(a);
      if (a && Number.isInteger(n) && n >= 1 && n <= opts.length) return opts[n - 1].key;
      const hit = opts.find((o) => o.words.some((w) => a === w || a.split(/\s+/).includes(w)));
      if (hit) return hit.key;
      this.scr.line(`I don't understand that. Pick 1 to ${opts.length}, or type help.`, C.warn);
    }
  }

  // ---------- pictures ----------
  /** A view that fits a bbox into the largest picture that leaves `roomBelow` lines free. */
  private viewFor(bbox: [number, number, number, number], roomBelow = 10): View {
    const { cols, rows } = this.scr.pictureSize(roomBelow);
    return fitView(bbox, cols, rows, this.term.dotAspect());
  }
  private hotelBbox() { return bboxAround(this.hotel.lon, this.hotel.lat, 1300); }

  // ---------- flow ----------
  /** Outer loop: one play per iteration; Restart starts a new play, Quit ends. */
  async run() {
    await document.fonts.load('15px "Dinner Mono"');
    await this.waitForSize();
    this.banner();
    for (;;) {
      try {
        await this.play();
      } catch (e) {
        if (e instanceof Restart) { this.scr.gap(); this.scr.line('You go back to the lobby.', C.dim); continue; }
        if (e instanceof Quit) { this.bye(); return; }
        if (e instanceof Redraw) { await this.waitForSize(); continue; }
        throw e;
      }
    }
  }

  /** Block until the window is at least MIN_COLS x MIN_ROWS. */
  private async waitForSize() {
    if (!this.term.tooSmall()) return;
    this.term.writeln(`${fg(C.warn)}This adventure needs a bigger window: at least 100 x 36 characters (now ${this.term.cols} x ${this.term.rows}).${RESET}`);
    this.term.writeln(`${fg(C.dim)}Widen the window or zoom out (Ctrl or Cmd and minus).${RESET}`);
    while (this.term.tooSmall()) {
      await new Promise<void>((r) => { const prev = this.term.onResize; this.term.onResize = () => { this.term.onResize = prev; r(); }; });
    }
    this.term.writeln(`${fg(C.dim)}That's better.${RESET}`);
  }

  private banner() {
    const t = [
      '  ___  _                         _         ___           _    ',
      ' |   \\(_)_ _  _ _  ___ _ _      (_)_ _    | _ \\__ _ _ _ (_)___',
      ' | |) | | \' \\| \' \\/ -_) \'_|     | | \' \\   |  _/ _` | \'_|| (_-<',
      ' |___/|_|_||_|_||_\\___|_|       |_|_||_|  |_| \\__,_|_|  |_/__/',
    ];
    this.scr.gap();
    for (const l of t) this.scr.raw(`${fg(C.text)}${l}`);
    this.scr.gap();
    this.scr.line('A text adventure in one sitting. Type help at any prompt.', C.dim);
    this.scr.footer();
  }

  private bye() {
    this.scr.gap();
    this.scr.line('You head out into the evening. Bon appétit.', C.bright);
    this.scr.line('Reload the page to play again.', C.dim);
  }

  /** The questions in order (back moves one step up), then search until the player is done. */
  private async play() {
    const steps: (() => Promise<void>)[] = [
      () => this.stepHotel(),
      () => this.stepWalk(),
      () => this.stepCuisine(),
      () => this.stepPrice(),
      () => this.stepDiet(),
      () => this.stepAccolade(),
    ];
    let i = 0;
    while (i < steps.length) {
      try { await steps[i](); i++; }
      catch (e) {
        if (e instanceof Back) { i = Math.max(0, i - 1); continue; }
        if (e instanceof Redraw) { await this.waitForSize(); continue; }
        throw e;
      }
    }
    let reask = false;
    for (;;) {
      try {
        if (reask) { await this.stepAccolade(); reask = false; }
        const done = await this.searchAndPick();
        if (done) return;
      } catch (e) {
        if (e instanceof Back) { reask = true; continue; }
        if (e instanceof Redraw) { await this.waitForSize(); continue; }
        throw e;
      }
    }
  }

  /** Intro line and the hotel menu; loads the chosen hotel's H3 cells. */
  private async stepHotel() {
    if (!this.hotels.length) this.hotels = await db.hotels();
    this.scr.gap();
    await this.scr.type('Paris. Evening. Your bags are upstairs, your shoes are comfortable, and you are hungry.');
    const opts: Option<string>[] = this.hotels.map((h) => ({
      key: h.hotel_id, label: h.name, note: h.area,
      words: [h.name.toLowerCase(), h.hotel_id, ...h.name.toLowerCase().split(/[\s'"]+/).filter((w) => w.length > 3)],
    }));
    const id = await this.choose('Which hotel are you staying at?', opts);
    this.hotel = this.hotels.find((h) => h.hotel_id === id)!;
    this.f.hotel = id;
    this.h3 = await db.h3(id);
  }

  /** First picture: the hotel's H3 cells light up minute by minute, then ask how far to walk. */
  private async stepWalk() {
    this.scr.gap();
    await this.scr.type(`You step out of ${this.hotel.name} (${this.hotel.area}) and look around.`);
    const v = this.viewFor(this.hotelBbox(), 8);
    const base = await baseFor(v);
    const scene: Scene = { base, hotel: this.hotel, h3: this.h3, bands: this.bands, h3Max: 0 };
    this.scr.picture(draw(v, scene));
    // the H3 walk isochrone grows outward, minute by minute
    this.scr.raw(' ');
    for (let m = 1; m <= 15; m++) {
      scene.h3Max = m;
      this.scr.redraw(draw(v, scene));
      const b = m <= 5 ? 5 : m <= 10 ? 10 : 15;
      this.scr.rewriteLast(`${fg(C.dim)}On foot from the door: ${fg(bandColor(b, this.bands))}${'█'.repeat(m)}${fg(C.faint)}${'░'.repeat(15 - m)} ${fg(C.bright)}${String(m).padStart(2)} min`);
      await this.term.pause(110);
    }
    this.scr.line('Each tint is one H3 cell, timed by CARTO from the hotel door. Brightest is closest.', C.faint);
    this.f.maxmin = await this.choose('How far will you walk for dinner?', WALKS);
  }

  private async stepCuisine() { this.f.cuisine = await this.choose('What are you hungry for?', CUISINES); }
  private async stepPrice() { this.f.price = await this.choose("And what's the budget?", PRICES); }
  private async stepDiet() { this.f.diet = await this.choose('Anything the kitchen should know?', DIETS); }
  private async stepAccolade() { this.f.accolade = await this.choose('Does it need a reputation?', ACCOLADES); }

  /** Run the search, print the report, then branch to slim pickings or results. Returns true when the player has finished. */
  private async searchAndPick(): Promise<boolean> {
    this.scr.gap();
    this.scr.line('You ask the concierge to check...', C.faint);
    const rows = await db.search(this.f);
    const n5 = rows.filter((r) => r.minutes <= 5).length;
    const n10 = rows.filter((r) => r.minutes > 5 && r.minutes <= 10).length;
    const n15 = rows.filter((r) => r.minutes > 10).length;
    this.scr.header('search report');
    this.scr.tick('Craving', label(CUISINES, this.f.cuisine));
    this.scr.tick('Budget', label(PRICES, this.f.price).replace(/^€+\s*/, ''));
    if (this.f.diet !== 'none') this.scr.tick('Diet', label(DIETS, this.f.diet));
    if (this.f.accolade !== 'any') this.scr.tick('Reputation', label(ACCOLADES, this.f.accolade));
    this.scr.tick('Within 5 min', String(n5), bandColor(5, this.bands));
    if (this.f.maxmin >= 10) this.scr.tick('5 to 10 min', String(n10), bandColor(10, this.bands));
    if (this.f.maxmin >= 15) this.scr.tick('10 to 15 min', String(n15), bandColor(15, this.bands));
    this.scr.closeBox();
    if (rows.length < 5) return this.slim(rows.length);
    return this.results(rows);
  }

  /** Under five results: offer only the changes that would find more places, with their counts. */
  private async slim(n: number): Promise<boolean> {
    await this.scr.type(n === 0 ? 'Nothing. Not a crumb.' : `Slim pickings: ${n === 1 ? 'one place' : n + ' places'}.`, C.warn);
    const rx = await db.relax(this.f);
    const opts: Option<string>[] = [];
    if (this.f.maxmin < 15 && rx.walk > n) opts.push({ key: 'walk', label: 'Walk up to 15 minutes', note: `${rx.walk} places`, words: ['walk', 'widen', 'further', 'far'] });
    if (this.f.cuisine !== 'any') opts.push({ key: 'cuisine', label: 'Change the cuisine', note: rx.cuisine > n ? `${rx.cuisine} with any cuisine` : undefined, words: ['cuisine', 'food'] });
    if (this.f.price !== 0) opts.push({ key: 'price', label: 'Change the budget', note: rx.price > n ? `${rx.price} at any price` : undefined, words: ['price', 'budget'] });
    if (this.f.diet !== 'none' && rx.diet > n) opts.push({ key: 'diet', label: 'Drop the dietary filter', note: `${rx.diet} without it`, words: ['diet'] });
    if (this.f.accolade !== 'any' && rx.accolade > n) opts.push({ key: 'accolade', label: 'Forget the reputation', note: `${rx.accolade} without it`, words: ['reputation', 'michelin', 'stars'] });
    if (n > 0) opts.push({ key: 'show', label: `Show me the ${n === 1 ? 'one' : n} anyway`, words: ['show', 'anyway', 'list'] });
    opts.push({ key: 'restart', label: 'Start over', words: ['start', 'over'] });
    const k = await this.choose('Want to change something?', opts);
    if (k === 'walk') this.f.maxmin = 15;
    if (k === 'cuisine') await this.stepCuisine();
    if (k === 'price') await this.stepPrice();
    if (k === 'diet') this.f.diet = 'none';
    if (k === 'accolade') this.f.accolade = 'any';
    if (k === 'restart') throw new Restart();
    if (k === 'show') return this.results(await db.search(this.f));
    return false;
  }

  /** Two lines per restaurant: name, rating, reviews, price, walk; then cuisine, awards, address, hours. */
  private describe(r: Restaurant): [string, string] {
    const stars = r.michelin_stars > 0 ? ` ${fg(C.dest)}${'★'.repeat(r.michelin_stars)}` : '';
    const meta = [`${Number(r.rating).toFixed(1)}/5`, r.reviews ? `${r.reviews} reviews` : null, r.price_range || r.price_level, `${r.minutes} min walk`].filter(Boolean).join(' · ');
    const one = `${fg(C.bright)}${BOLD}${r.name}${RESET}${stars}${fg(C.text)}  ${meta}`;
    const aw = [r.michelin_stars ? `Michelin ${r.michelin_stars} star${r.michelin_stars > 1 ? 's' : ''}` : r.bib_gourmand ? 'Bib Gourmand' : r.michelin_listed ? 'Michelin Guide' : null, r.travellers_choice ? "Travellers' Choice" : null].filter(Boolean).join(', ');
    const h = hoursToday(r.open_hours);
    const two = [r.cuisines ? `${fg(C.dim)}${r.cuisines}` : null, aw ? `${fg(C.dest)}${aw}` : null, `${fg(C.faint)}${r.address.replace(/,? ?\d{5} Paris France$/, '').replace(/ France$/, '')}`, h ? `${fg(C.faint)}${h}` : null].filter(Boolean).join(`${fg(C.faint)} · `);
    return [one, two];
  }

  /** Paged results: a map fitted to the hotel and the page's five places, then the list, then a prompt. */
  private async results(rows: Restaurant[]): Promise<boolean> {
    const per = 5;
    let page = 0;
    const pages = Math.ceil(rows.length / per);
    for (;;) {
      const slice = rows.slice(page * per, page * per + per);
      const pts: LonLat[] = [[this.hotel.lon, this.hotel.lat], ...slice.map((r) => [r.lon, r.lat] as LonLat)];
      const v = this.viewFor(minBbox(padBbox(bboxOf(pts), 0.1), 280), slice.length * 2 + 9);
      const base = await baseFor(v);
      this.scr.gap();
      await this.scr.type(page === 0 ? `The concierge finds ${rows.length === 1 ? 'one place' : rows.length + ' places'} and marks the nearest on a map.` : `Page ${page + 1} of ${pages}.`);
      this.scr.picture(draw(v, {
        base, hotel: this.hotel, h3: this.h3, h3Max: this.f.maxmin, bands: this.bands,
        dots: rows.map((r) => ({ lon: r.lon, lat: r.lat, minutes: r.minutes })),
        markers: slice.map((r, j) => ({ lon: r.lon, lat: r.lat, minutes: r.minutes, label: String(page * per + j + 1) })),
      }), `◆ your hotel   • other matches   page ${page + 1} of ${pages}`);
      slice.forEach((r, j) => {
        const n = page * per + j + 1;
        const [one, two] = this.describe(r);
        this.scr.raw(`${fg(C.bg)}\x1b[48;2;${bandColor(bandFor(r.minutes), this.bands).join(';')}m${BOLD}${String(n).padStart(3)} ${RESET} ${one}`);
        this.scr.raw(`      ${two}`);
      });
      this.scr.line(`Pick a number${pages > 1 ? ', or n for the next page, p for the previous' : ''}.`, C.dim);
      for (;;) {
        const a = (await this.ask()).toLowerCase();
        if ((a === 'n' || a === 'next' || a === 'more') && page < pages - 1) { page++; break; }
        if ((a === 'p' || a === 'prev' || a === 'previous') && page > 0) { page--; break; }
        const k = Number(a);
        if (a && Number.isInteger(k) && k >= 1 && k <= rows.length) return this.walkTo(rows[k - 1]);
        this.scr.line(`Pick 1 to ${rows.length}${pages > 1 ? ', n or p' : ''}.`, C.warn);
      }
    }
  }

  /** Final picture: the route from the hotel door to the restaurant, animated, with directions and the walk summary. */
  private async walkTo(r: Restaurant): Promise<boolean> {
    this.scr.gap();
    await this.scr.type(`Great. Here's your path to ${r.name}.`, C.bright);
    const route = await db.route(this.f.hotel, r.restaurant_id);
    if (!route) {
      this.scr.line('No route was worked out for this one. Head roughly that way and follow your nose.', C.warn);
    } else {
      const line: LonLat[] = [[this.hotel.lon, this.hotel.lat], ...route.coords, [r.lon, r.lat]];
      const bb = padBbox(bboxOf(line), 0.12); // minBbox below keeps short walks in street context
      const steps = route.steps.map((st) => ({ ...st, i: st.i + 1 }));
      const roomBelow = Math.min(steps.length, 14) + 8;
      const v = this.viewFor(minBbox(bb, 260), roomBelow);
      const scene: Scene = { base: await baseFor(v), hotel: this.hotel, dest: { lon: r.lon, lat: r.lat }, route: line, routeUpTo: 1, bands: this.bands };
      this.scr.picture(draw(v, scene), '◆ your hotel   ★ dinner');
      await this.animate(v, scene, line, steps);
      this.scr.raw(`${fg(C.bright)}${route.distance_m.toLocaleString('en-GB')} m, ${Math.max(1, Math.round(route.duration_s / 60))} min on foot${fg(C.faint)}  (the H3 isochrone said ${r.minutes} min)`);
    }
    const again = await this.choose('', [
      { key: 'same', label: 'Another dinner from the same hotel', words: ['y', 'yes', 'same'] },
      { key: 'new', label: 'Start again from a different hotel', words: ['another', 'hotel', 'new'] },
      { key: 'no', label: "That's it, I'm off to eat", words: ['no', 'n', 'quit'] },
    ]);
    if (again === 'no') throw new Quit();
    if (again === 'new') throw new Restart();
    this.f.maxmin = await this.choose('How far will you walk this time?', WALKS);
    await this.stepCuisine(); await this.stepPrice(); await this.stepDiet(); await this.stepAccolade();
    return false;
  }

  /** Draw the route vertex by vertex in place; print each instruction when the line reaches its vertex. */
  private async animate(v: View, scene: Scene, coords: LonLat[], steps: Step[]) {
    // ~25 fps, 3 to 7 s depending on length; directions print as the line reaches each turn
    const frames = Math.max(60, Math.min(170, coords.length * 2));
    const say = (s: Step) => this.scr.raw(`${fg(C.faint)}${String(s.m).padStart(6)} m  ${fg(C.text)}${s.msg}`);
    let next = 0;
    for (let f = 1; f <= frames; f++) {
      const upTo = Math.ceil((f / frames) * coords.length);
      scene.routeUpTo = upTo;
      if (!this.scr.redraw(draw(v, scene))) break;
      while (next < steps.length && steps[next].i < upTo && this.scr.canRedraw(1)) say(steps[next++]);
      await sleep(this.term.fast ? 0 : 40);
    }
    while (next < steps.length) say(steps[next++]);
  }
}

/** Grow a bbox to at least +/- halfM metres around its centre. */
function minBbox(b: [number, number, number, number], halfM: number): [number, number, number, number] {
  const cx = (b[0] + b[2]) / 2, cy = (b[1] + b[3]) / 2;
  const m = bboxAround(cx, cy, halfM);
  return [Math.min(b[0], m[0]), Math.min(b[1], m[1]), Math.max(b[2], m[2]), Math.max(b[3], m[3])];
}
/** Band edge for a walk time in minutes. */
function bandFor(m: number) { return m <= 5 ? 5 : m <= 10 ? 10 : 15; }
/** Pad a bbox by a fraction of its size plus a small fixed margin. */
function padBbox(b: [number, number, number, number], p: number): [number, number, number, number] {
  const dx = (b[2] - b[0]) * p + 0.0008, dy = (b[3] - b[1]) * p + 0.0005;
  return [b[0] - dx, b[1] - dy, b[2] + dx, b[3] + dy];
}

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
/** Today's opening hours from TripAdvisor's JSON, labelled 2021 since that's when it was scraped. */
function hoursToday(json: string | null): string | null {
  if (!json) return null;
  try {
    const o = JSON.parse(json) as Record<string, string[]>;
    const d = DAYS[new Date().getDay()];
    const h = o[d];
    if (!h) return null;
    return h.length ? `${d} ${h.join(', ')} (2021)` : `closed ${d} (2021)`;
  } catch { return null; }
}
