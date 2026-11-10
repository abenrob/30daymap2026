// Compose braille map scenes: basemap from CARTO vector tiles, H3 walk-time tint,
// restaurants, route and pins.
import { latLngToCell } from 'h3-js';
import { BrailleCanvas, type RGB } from './braille';
import { loadBase, type BaseFeatures, type LonLat } from './tiles';
import { C, bandColor, bandTint } from './theme';

/** A map view: cell size, centre, and metres per braille dot on each axis. */
export interface View {
  cols: number; rows: number;
  lon0: number; lat0: number;
  mx: number; my: number; // meters per dot, x and y
}

// Local equirectangular projection: metres per degree, x corrected by cos(latitude).
// Over a few kilometres of Paris the error is negligible.
const M_LAT = 110540;
const mLon = (lat: number) => 111320 * Math.cos((lat * Math.PI) / 180);

/** Fit a lon/lat bbox into cols x rows cells; dotAspect = dot height / dot width in pixels. */
export function fitView(bbox: [number, number, number, number], cols: number, rows: number, dotAspect: number, pad = 0.06): View {
  const lon0 = (bbox[0] + bbox[2]) / 2, lat0 = (bbox[1] + bbox[3]) / 2;
  const wm = (bbox[2] - bbox[0]) * mLon(lat0) * (1 + pad * 2);
  const hm = (bbox[3] - bbox[1]) * M_LAT * (1 + pad * 2);
  const w = cols * 2, h = rows * 4;
  const mx = Math.max(wm / w, hm / (h * dotAspect));
  return { cols, rows, lon0, lat0, mx, my: mx * dotAspect };
}

/** lon/lat -> dot coordinates (origin top left). */
export function project(v: View, lon: number, lat: number): [number, number] {
  return [
    v.cols + ((lon - v.lon0) * mLon(v.lat0)) / v.mx,
    v.rows * 2 + ((v.lat0 - lat) * M_LAT) / v.my,
  ];
}

/** Dot coordinates -> lon/lat. */
export function unproject(v: View, x: number, y: number): LonLat {
  return [v.lon0 + ((x - v.cols) * v.mx) / mLon(v.lat0), v.lat0 - ((y - v.rows * 2) * v.my) / M_LAT];
}

/** lon/lat bbox covered by a view. */
export function viewBbox(v: View): [number, number, number, number] {
  const [w, n] = unproject(v, 0, 0);
  const [e, s] = unproject(v, v.cols * 2, v.rows * 4);
  return [w, s, e, n];
}

/** bbox of +/- meters around a point. */
export function bboxAround(lon: number, lat: number, meters: number): [number, number, number, number] {
  const dx = meters / mLon(lat), dy = meters / M_LAT;
  return [lon - dx, lat - dy, lon + dx, lat + dy];
}

export function bboxOf(pts: LonLat[]): [number, number, number, number] {
  let a = Infinity, b = Infinity, c = -Infinity, d = -Infinity;
  for (const [x, y] of pts) { a = Math.min(a, x); b = Math.min(b, y); c = Math.max(c, x); d = Math.max(d, y); }
  return [a, b, c, d];
}

/** Basemap features for a view, at a tile zoom that matches its scale. */
export async function baseFor(v: View): Promise<BaseFeatures> {
  // ~20 m per dot or finer gets z15 detail; wider views use z14
  const z = v.mx < 9 ? 15 : 14;
  return loadBase(viewBbox(v), z);
}

// Road colour and dot priority by tile 'kind'. Higher priority wins a shared cell.
const ROAD_STYLE: Record<string, [RGB, number] | undefined> = {
  highway: [C.roadMajor, 3],
  major_road: [C.roadMajor, 3],
  minor_road: [C.roadMinor, 2],
  path: [C.roadPath, 1],
  other: [C.roadPath, 1],
};

/** Everything a picture can show. Layers are optional; draw() paints them in a fixed order. */
export interface Scene {
  base?: BaseFeatures;
  h3?: Map<string, number>;      // h3 cell -> minutes
  h3Max?: number;                 // reveal threshold (minutes)
  bands?: number[];               // band edges, e.g. [5,10,15]
  dots?: { lon: number; lat: number; minutes: number }[];
  markers?: { lon: number; lat: number; label: string; minutes: number }[];
  route?: LonLat[];
  routeUpTo?: number;             // number of route vertices to draw
  hotel?: { lon: number; lat: number };
  labels?: { lon: number; lat: number; text: string }[];
  dest?: { lon: number; lat: number };
}

/** Smallest band edge that contains a walk time (Infinity if outside every band). */
export function bandOf(minutes: number, bands: number[]): number {
  for (const b of bands) if (minutes <= b) return b;
  return Infinity;
}

/**
 * Rasterise a scene into ANSI lines, bottom layer first:
 * parks and water (cell backgrounds), streets (dots), H3 walk-time tint (cell
 * backgrounds, looked up per cell centre with h3-js), restaurant dots, the route
 * (two dots wide), numbered markers, labels, then the destination and hotel pins.
 */
export function draw(v: View, s: Scene): string[] {
  const cv = new BrailleCanvas(v.cols, v.rows);
  const P = (ll: LonLat) => project(v, ll[0], ll[1]);

  if (s.base) {
    for (const a of s.base.parks) cv.fillCells(a.rings.map((r) => r.map(P)), C.park, 1);
    for (const a of s.base.water) {
      const rings = a.rings.map((r) => r.map(P));
      cv.fillCells(rings, C.water, 5);
    }
    const overview = v.mx > 14;
    for (const r of s.base.roads) {
      // pedestrian streets and living streets are real streets in Paris: draw them as minor roads
      const street = (r.kind === 'path' && r.detail === 'pedestrian') || (r.kind === 'other' && r.detail === 'living_street');
      const st = street ? ROAD_STYLE.minor_road : ROAD_STYLE[r.kind];
      if (!st) continue;
      if (overview && r.kind !== 'major_road' && r.kind !== 'highway') continue;
      if (!street && (r.kind === 'path' || r.kind === 'other') && v.mx > 4) continue;
      for (let i = 1; i < r.coords.length; i++) {
        const [x0, y0] = P(r.coords[i - 1]), [x1, y1] = P(r.coords[i]);
        cv.line(x0, y0, x1, y1, st[0], st[1]);
      }
    }
  }

  if (s.h3 && s.bands) {
    const max = s.h3Max ?? Infinity;
    for (let row = 0; row < v.rows; row++) for (let col = 0; col < v.cols; col++) {
      const [lon, lat] = unproject(v, col * 2 + 1, row * 4 + 2);
      const m = s.h3.get(latLngToCell(lat, lon, 10));
      if (m === undefined || m > max) continue;
      const b = bandOf(m, s.bands);
      if (b === Infinity) continue;
      cv.cellBg(col, row, bandTint(b, s.bands), 3);
    }
  }

  if (s.dots && s.bands) for (const d of s.dots) {
    const [x, y] = project(v, d.lon, d.lat);
    cv.glyphAtDot(x, y, '•', bandColor(bandOf(d.minutes, s.bands), s.bands));
  }

  if (s.route) {
    const n = Math.min(s.route.length, s.routeUpTo ?? s.route.length);
    for (let i = 1; i < n; i++) {
      const [x0, y0] = P(s.route[i - 1]), [x1, y1] = P(s.route[i]);
      cv.line(x0, y0, x1, y1, C.route, 9);
      cv.line(x0 + 1, y0, x1 + 1, y1, C.route, 9);
    }
  }

  if (s.markers && s.bands) for (const m of s.markers) {
    const [x, y] = project(v, m.lon, m.lat);
    cv.glyphAtDot(x, y, m.label, C.bg, bandColor(bandOf(m.minutes, s.bands), s.bands), true);
  }

  if (s.labels) for (const l of s.labels) {
    const [x, y] = project(v, l.lon, l.lat);
    cv.glyphAtDot(x, y, l.text, C.bg, C.bright, true);
  }

  if (s.dest) { const [x, y] = project(v, s.dest.lon, s.dest.lat); cv.glyphAtDot(x, y, '★', C.dest, undefined, true); }
  if (s.hotel) { const [x, y] = project(v, s.hotel.lon, s.hotel.lat); cv.glyphAtDot(x, y, '◆', C.hotel, undefined, true); }

  return cv.render(C.bg);
}
