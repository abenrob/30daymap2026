// Step 2: turn Targomo's GeoJSON into the compact, timed paths the page draws.
//
//   node scripts/02_build_paths.mjs
//
// Reads  ../../work/day-24-network/<name>-40min.geojson   (written by step 1)
// Writes graph/<name>.json                                 (read by js/data.js)
//        ../../work/day-24-network/<name>-summary.json     (a few checks)
// Env:   D24_NAME (default berlin-transit), D24_MIN (default 40), D24_WORK
//
// The problem this solves: Targomo gives each street segment a single travel
// time, but to grow a street along its length we need a direction and a time
// at each end. So:
//   1. every node (segment end) gets the earliest time of the segments that
//      touch it: its arrival time;
//   2. every segment runs from its earlier node to its later node, t0 -> t1;
//      where both ends share a time, it takes walking pace (max 2 minutes);
//   3. one straight "walk-in" line joins the drop point to the first street,
//      because the drop point itself usually sits off the street graph.

import fs from "node:fs";
import path from "node:path";

const DAY = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const WORK = process.env.D24_WORK || path.resolve(DAY, "../../work/day-24-network");
const NAME = process.env.D24_NAME || "berlin-transit";
const MINUTES = +(process.env.D24_MIN || 40);
const FILES = {
  in: path.join(WORK, `${NAME}-${MINUTES}min.geojson`),
  out: process.env.D24_OUT || path.join(DAY, "graph", `${NAME}.json`),
  summary: path.join(WORK, `${NAME}-summary.json`),
};

const WALK_MPS = 1.25;    // pace for segments with no time difference
const WALK_MAX_S = 120;   // ...capped at two minutes per segment
const Q = 1e5;            // coordinates stored as integers of 1e-5 degrees (~1 m)
const WALK_IN = { maxSec: 300, maxMetres: 250, sameSpotMetres: 25, tieSec: 15 };

// ---- geometry helpers ----------------------------------------------------------

const RAD = Math.PI / 180, EARTH_R = 6371008.8;
// Equirectangular distance in metres: plenty at street scale.
function metres(a, b) {
  const x = (b[0] - a[0]) * RAD * Math.cos((a[1] + b[1]) / 2 * RAD);
  const y = (b[1] - a[1]) * RAD;
  return EARTH_R * Math.hypot(x, y);
}
const lineLength = c => c.slice(1).reduce((sum, p, i) => sum + metres(c[i], p), 0);
const nodeKey = p => `${p[0].toFixed(6)},${p[1].toFixed(6)}`;
const percentile = (sorted, f) => sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * f))];

// ---- 1. read the segments -------------------------------------------------------

function readSegments(fc) {
  const segments = [];
  for (const f of fc.features) {
    const w = +f.properties?.w;   // Targomo's travel time for the segment, seconds
    if (!f.geometry || !Number.isFinite(w)) continue;
    const g = f.geometry;
    const lines = g.type === "LineString" ? [g.coordinates]
      : g.type === "MultiLineString" ? g.coordinates : [];
    for (const coords of lines) if (coords.length >= 2) segments.push({ coords, w });
  }
  return segments;
}

// ---- 2. arrival time at every node --------------------------------------------------

function nodeArrivals(segments) {
  const arrival = new Map();
  const touch = (p, w) => {
    const k = nodeKey(p);
    if (!(arrival.get(k) <= w)) arrival.set(k, w);
  };
  for (const { coords, w } of segments) {
    touch(coords[0], w);
    touch(coords[coords.length - 1], w);
  }
  return arrival;
}

// ---- 3. direct, time and pack each segment -----------------------------------------
// Packed row: [t0, t1, x0, y0, dx1, dy1, dx2, dy2, ...], times to 0.1 s,
// coordinates as integers of 1e-5 degrees, deltas after the first vertex.

function packRow(t0, t1, coords) {
  const row = [Math.round(t0 * 10) / 10, Math.round(t1 * 10) / 10];
  let px = Math.round(coords[0][0] * Q), py = Math.round(coords[0][1] * Q);
  row.push(px, py);
  for (let i = 1; i < coords.length; i++) {
    const x = Math.round(coords[i][0] * Q), y = Math.round(coords[i][1] * Q);
    if (x === px && y === py) continue;   // drop vertices that round together
    row.push(x - px, y - py);
    px = x; py = y;
  }
  return row;
}

function timedRows(segments, arrival, maxTime, stats) {
  const rows = [];
  for (const seg of segments) {
    let coords = seg.coords;
    let t0 = arrival.get(nodeKey(coords[0]));
    let t1 = arrival.get(nodeKey(coords[coords.length - 1]));
    if (t0 > t1) {
      coords = coords.slice().reverse();
      [t0, t1] = [t1, t0];
      stats.flipped++;
    }
    if (t1 - t0 < 1) {
      t1 = t0 + Math.min(lineLength(coords) / WALK_MPS, WALK_MAX_S);
      stats.walkPaced++;
    }
    if (t0 > maxTime) continue;
    const row = packRow(t0, t1, coords);
    if (row.length >= 6) rows.push(row);   // at least two distinct vertices
  }
  return rows;
}

// ---- 4. the walk-in line ---------------------------------------------------------------
// The first street point reached (within 5 min and 250 m of the drop point)
// that no earlier segment already leads to, plus any reached within 15 s of
// it (a snap onto two streets at once).

function rowEnd(row) {
  let x = row[2], y = row[3];
  for (let i = 4; i < row.length; i += 2) { x += row[i]; y += row[i + 1]; }
  return { p: [x / Q, y / Q], t: row[1] };
}

function walkInRows(rows, origin) {
  const ends = rows.map(rowEnd);
  const starts = [];
  for (const row of rows) {
    const p = [row[2] / Q, row[3] / Q], t = row[0], d = metres(origin, p);
    if (t > WALK_IN.maxSec || d > WALK_IN.maxMetres) continue;
    const reachedEarlier = ends.some(e => e.t < t - 0.5 && metres(e.p, p) < WALK_IN.sameSpotMetres);
    const alreadyListed = starts.some(s => metres(s.p, p) < WALK_IN.sameSpotMetres);
    if (!reachedEarlier && !alreadyListed) starts.push({ p, t, d });
  }
  starts.sort((a, b) => a.t - b.t);
  const first = starts.filter(s => s.t <= starts[0].t + WALK_IN.tieSec);
  const ox = Math.round(origin[0] * Q), oy = Math.round(origin[1] * Q);
  return {
    rows: first.map(s => [0, s.t, ox, oy, Math.round(s.p[0] * Q) - ox, Math.round(s.p[1] * Q) - oy]),
    lines: first.map(s => ({ t: s.t, m: Math.round(s.d) })),
  };
}

// ---- 5. extent -----------------------------------------------------------------------------
// bbox: everything. view: the 2nd-98th percentile of vertices, which the page
// fits for its wide shot, so a few far rail islands don't shrink the city.

function extents(segments) {
  const xs = [], ys = [];
  for (const { coords } of segments) for (const [x, y] of coords) { xs.push(x); ys.push(y); }
  xs.sort((a, b) => a - b);
  ys.sort((a, b) => a - b);
  return {
    bbox: [xs[0], ys[0], xs[xs.length - 1], ys[ys.length - 1]],
    view: [percentile(xs, 0.02), percentile(ys, 0.02), percentile(xs, 0.98), percentile(ys, 0.98)],
  };
}

// ---- run ----------------------------------------------------------------------------------

const fc = JSON.parse(fs.readFileSync(FILES.in, "utf8"));
const meta = fc.metadata || {};
const origin = [meta.origin.lng, meta.origin.lat];
const maxTime = meta.maxTime || MINUTES * 60;

const segments = readSegments(fc);
const arrival = nodeArrivals(segments);
const stats = { flipped: 0, walkPaced: 0 };
const rows = timedRows(segments, arrival, maxTime, stats);
const walkIn = walkInRows(rows, origin);
rows.push(...walkIn.rows);
rows.sort((a, b) => a[0] - b[0]);
const { bbox, view } = extents(segments);

const doc = { origin, maxTime, date: meta.date, time: meta.time, q: Q, bbox, view, paths: rows };
fs.mkdirSync(path.dirname(FILES.out), { recursive: true });
fs.writeFileSync(FILES.out, JSON.stringify(doc));

const ws = segments.map(s => s.w).sort((a, b) => a - b);
const summary = {
  segments: segments.length, nodes: arrival.size, written: rows.length,
  travelTime: { min: ws[0], median: percentile(ws, 0.5), max: ws[ws.length - 1] },
  flipped: stats.flipped, walkPaced: stats.walkPaced, walkIn: walkIn.lines,
  bbox, view, bytes: fs.statSync(FILES.out).size,
};
fs.writeFileSync(FILES.summary, JSON.stringify(summary, null, 2));
console.log(JSON.stringify(summary, null, 2));
