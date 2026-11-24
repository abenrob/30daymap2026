// GeoJSON edges (one travel time each) -> directed, timed paths for the page.
// Usage: node scripts/02_build_paths.mjs   (reads the file 01 wrote)
//
// Each edge carries one weight w. To animate it along its length we need a
// direction and a start/end time. Every node gets the smallest w of the
// edges that touch it (its arrival time). An edge runs from its earlier end
// to its later end: t0 = T(earlier node), t1 = T(later node). When both ends
// share a time (no ordering), fall back to walking speed for the duration.
import fs from "node:fs";
import path from "node:path";

const here = path.dirname(new URL(import.meta.url).pathname);
const day = path.resolve(here, "..");
const WORK = process.env.D24_WORK || path.resolve(day, "../../work/day-24-network");
const IN = path.join(WORK, "berlin-transit-60min.geojson");
const OUT = path.join(day, "graph", "berlin-transit.json");
const SUMMARY = path.join(WORK, "summary.json");

const WALK = 1.25;          // m/s fallback when an edge has no time gradient
const Q = 1e5;              // coordinate quantisation (~1 m)

const fc = JSON.parse(fs.readFileSync(IN, "utf8"));
const meta = fc.metadata || {};
const origin = meta.origin ? [meta.origin.lng, meta.origin.lat] : [13.4132, 52.5219];
const maxTime = meta.maxTime || 3600;

const weightOf = p => {
  for (const k of ["w", "weight", "time", "travelTime", "edgeWeight"]) if (Number.isFinite(+p?.[k])) return +p[k];
  return NaN;
};
const key = c => `${c[0].toFixed(6)},${c[1].toFixed(6)}`;
const R = 6371008.8, rad = Math.PI / 180;
const dist = (a, b) => {
  const x = (b[0] - a[0]) * rad * Math.cos((a[1] + b[1]) / 2 * rad), y = (b[1] - a[1]) * rad;
  return R * Math.hypot(x, y);
};

// 1. explode into simple lines with a weight
const edges = [];
const propKeys = new Map(), geomTypes = new Map();
for (const f of fc.features) {
  const g = f.geometry; if (!g) continue;
  geomTypes.set(g.type, (geomTypes.get(g.type) || 0) + 1);
  for (const k of Object.keys(f.properties || {})) propKeys.set(k, (propKeys.get(k) || 0) + 1);
  const w = weightOf(f.properties);
  if (!Number.isFinite(w)) continue;
  const parts = g.type === "LineString" ? [g.coordinates] : g.type === "MultiLineString" ? g.coordinates : [];
  for (const c of parts) if (c.length >= 2) edges.push({ c, w });
}

// 2. node arrival times
const T = new Map();
const touch = (c, w) => { const k = key(c); const v = T.get(k); if (v === undefined || w < v) T.set(k, w); };
for (const e of edges) { touch(e.c[0], e.w); touch(e.c[e.c.length - 1], e.w); }

// 3. direct and time each edge
let flat = 0, flipped = 0, wInside = 0, wAtEnd = 0, wAtStart = 0;
const out = [];
for (const e of edges) {
  let c = e.c;
  let ta = T.get(key(c[0])), tb = T.get(key(c[c.length - 1]));
  if (ta > tb) { c = c.slice().reverse(); [ta, tb] = [tb, ta]; flipped++; }
  let len = 0; for (let i = 1; i < c.length; i++) len += dist(c[i - 1], c[i]);
  let t0 = ta, t1 = tb;
  if (t1 - t0 < 1) { t1 = t0 + Math.min(len / WALK, 120); flat++; }
  if (e.w >= t0 - 1 && e.w <= t1 + 1) wInside++;
  if (Math.abs(e.w - tb) < 1) wAtEnd++;
  if (Math.abs(e.w - ta) < 1) wAtStart++;
  if (t0 > maxTime) continue;
  // [t0, t1, x0, y0, dx1, dy1, ...] as integers (1e-5 deg), deltas after the first
  const row = [Math.round(t0 * 10) / 10, Math.round(t1 * 10) / 10];
  let px = Math.round(c[0][0] * Q), py = Math.round(c[0][1] * Q);
  row.push(px, py);
  for (let i = 1; i < c.length; i++) {
    const x = Math.round(c[i][0] * Q), y = Math.round(c[i][1] * Q);
    if (x === px && y === py) continue;
    row.push(x - px, y - py); px = x; py = y;
  }
  if (row.length >= 6) out.push(row);
}
// 4. walk-in connectors. The drop point usually sits off the street graph
// (the middle of Alexanderplatz is not in it), so Targomo charges a straight
// walk to the nearest street and the first edges start ~150 m away. Draw that
// walk: a straight line from the origin to the first point within 5 min
// that is reachable at walking pace (<= 1.4 m/s from the origin) and that no
// earlier edge already reaches. Faster first points are transit hops (the
// next U-Bahn station) and stay as islands.
const SNAP_MAX_T = 300, SNAP_MAX_V = 1.4, SNAP_DEDUPE = 25;
const ends = out.map(r => { let x = r[2], y = r[3]; for (let i = 4; i < r.length; i += 2) { x += r[i]; y += r[i + 1]; } return [x / Q, y / Q, r[1]]; });
const snaps = [];
for (const r of out) {
  if (r[0] > SNAP_MAX_T) continue;
  const s0 = [r[2] / Q, r[3] / Q], dm = dist(origin, s0);
  if (dm / Math.max(r[0], 1) > SNAP_MAX_V) continue;
  if (ends.some(e => e[2] < r[0] - 0.5 && dist([e[0], e[1]], s0) < SNAP_DEDUPE)) continue;
  if (snaps.some(sn => dist(sn.p, s0) < SNAP_DEDUPE)) continue;
  snaps.push({ p: s0, t: r[0], dm });
}
// Targomo snaps the source to one spot: keep the earliest walk-in, plus any
// reached within 15 s of it (a snap onto two streets); later ones are reached
// along the street graph from there.
snaps.sort((a, b) => a.t - b.t);
const keep = snaps.filter(sn => sn.t <= snaps[0].t + 15);
snaps.length = 0; snaps.push(...keep);
for (const sn of snaps) {
  const ox = Math.round(origin[0] * Q), oy = Math.round(origin[1] * Q);
  out.push([0, sn.t, ox, oy, Math.round(sn.p[0] * Q) - ox, Math.round(sn.p[1] * Q) - oy]);
}
out.sort((a, b) => a[0] - b[0]);

let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
for (const e of edges) for (const p of e.c) {
  if (p[0] < minX) minX = p[0]; if (p[0] > maxX) maxX = p[0];
  if (p[1] < minY) minY = p[1]; if (p[1] > maxY) maxY = p[1];
}
// view box: 2nd-98th percentile of vertices, so far-flung regional-rail
// islands don't shrink the city in the frame
const xs = [], ys = [];
for (const e of edges) for (const p of e.c) { xs.push(p[0]); ys.push(p[1]); }
xs.sort((a, b) => a - b); ys.sort((a, b) => a - b);
const pc = (a, f) => a[Math.min(a.length - 1, Math.floor(a.length * f))];
const view = [pc(xs, 0.02), pc(ys, 0.02), pc(xs, 0.98), pc(ys, 0.98)];
const doc = { origin, maxTime, date: meta.date, time: meta.time, q: Q,
  bbox: [minX, minY, maxX, maxY], view, paths: out };
fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, JSON.stringify(doc));

const ws = edges.map(e => e.w).sort((a, b) => a - b);
const summary = {
  features: fc.features.length, edges: edges.length, written: out.length, nodes: T.size,
  geomTypes: Object.fromEntries(geomTypes), propKeys: Object.fromEntries(propKeys),
  sampleProps: fc.features.slice(0, 5).map(f => f.properties),
  w: { min: ws[0], p50: ws[ws.length >> 1], max: ws[ws.length - 1] },
  flatEdges: flat, flipped, wInsideSpan: wInside, wEqualsLaterEnd: wAtEnd, wEqualsEarlierEnd: wAtStart,
  bbox: doc.bbox, view, snaps: snaps.map(x => ({ t: x.t, m: Math.round(x.dm) })), bytes: fs.statSync(OUT).size,
};
fs.writeFileSync(SUMMARY, JSON.stringify(summary, null, 2));
console.log(JSON.stringify(summary, null, 2));
