// Day 22 · Projections, step 2: build the geometry the page animates.
//
// From Natural Earth (world-atlas 2.0.2):
//   main        Greenland's main island outline (1:50m), densified to 0.25° steps
//   glIslands   Greenland's larger offshore islands
//   neighbours  nearby land for context: Canada's Arctic and the mainland north of 55 N, Iceland, Svalbard
//   grat        a graticule around Greenland (meridians every 10°, parallels every 10°)
//   land        all land (1:110m), for the vector globe in the finale
//   centroid    Greenland's spherical centroid [lon, lat]
//
// Every ring is densified along great circles so curved projections bend it
// smoothly; the page projects the same points in every projection and morphs
// between them point by point.
//
// Output: $D22_WORK/data.json (default ../../../work/day-22-projections)

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import * as topojson from 'topojson-client';
import * as d3 from 'd3';

const here = path.dirname(fileURLToPath(import.meta.url));
const WORK = process.env.D22_WORK || path.join(here, '../../../work/day-22-projections');
fs.mkdirSync(WORK, { recursive: true });

const atlas = (f) => JSON.parse(fs.readFileSync(path.join(here, 'node_modules/world-atlas', f)));
const c50 = atlas('countries-50m.json');
const land110 = atlas('land-110m.json');
const countries = topojson.feature(c50, c50.objects.countries).features;
const byId = (id) => countries.find((f) => f.id === id);   // ISO 3166-1 numeric

const round = (p) => [Math.round(p[0] * 1e3) / 1e3, Math.round(p[1] * 1e3) / 1e3];
const areaOf = (ring) => d3.geoArea({ type: 'Polygon', coordinates: [ring] }); // steradians

// Insert points along each edge so no step is longer than maxDeg of arc.
function densify(ring, maxDeg = 0.5) {
  const out = [];
  for (let i = 0; i < ring.length - 1; i++) {
    const a = ring[i], b = ring[i + 1];
    const n = Math.max(1, Math.ceil((d3.geoDistance(a, b) * 180 / Math.PI) / maxDeg));
    const interp = d3.geoInterpolate(a, b);
    for (let k = 0; k < n; k++) out.push(round(interp(k / n)));
  }
  out.push(round(ring[ring.length - 1]));
  return out;
}

// Outer rings of a Polygon or MultiPolygon feature (holes are not needed here).
function outerRings(feature) {
  const g = feature.geometry;
  return (g.type === 'Polygon' ? [g.coordinates] : g.coordinates).map((p) => p[0]);
}

// Greenland (304): the largest ring is the main island. Islands keep a size
// floor; areas above 1 sr would be a ring with inverted winding.
const glRings = outerRings(byId('304')).sort((a, b) => b.length - a.length);
const main = densify(glRings[0], 0.25);
const glIslands = glRings.slice(1)
  .filter((r) => { const a = areaOf(r); return a > 2e-5 && a < 1; })
  .map((r) => densify(r, 0.5));
const centroid = d3.geoCentroid({ type: 'Polygon', coordinates: [glRings[0]] });

// Neighbours: Canada (124), Iceland (352), Norway (578, Svalbard only), USA (840,
// only rings north of 55 N, which in practice selects nothing in the window).
// A ring is kept if any of its points falls in the window 105 W to 30 E, north of 55 N.
const inWindow = (r) => r.some(([x, y]) => x > -105 && x < 30 && y > 55);
const neighbours = [];
for (const id of ['124', '352', '578', '840']) {
  for (const r of outerRings(byId(id))) {
    const a = areaOf(r);
    if (a > 1 || a < 3e-5 || !inWindow(r)) continue;
    if (id === '840' && !r.some(([, y]) => y > 55)) continue;
    if (id === '578' && !r.some(([, y]) => y > 74)) continue;
    neighbours.push(densify(r, 0.6));
  }
}

// Graticule around Greenland, as plain point lists (1° steps).
const grat = [];
for (let lon = -90; lon <= 10; lon += 10) {
  const line = []; for (let lat = 50; lat <= 88; lat += 1) line.push([lon, lat]); grat.push(line);
}
for (let lat = 50; lat <= 80; lat += 10) {
  const line = []; for (let lon = -100; lon <= 20; lon += 1) line.push([lon, lat]); grat.push(line);
}

const land = topojson.feature(land110, land110.objects.land);

const data = { centroid: round(centroid), main, glIslands, neighbours, grat, land };
const out = path.join(WORK, 'data.json');
fs.writeFileSync(out, JSON.stringify(data));
console.log(`wrote ${out}: centroid ${data.centroid}, main ${main.length} pts, ${glIslands.length} islands, ` +
  `${neighbours.length} neighbour rings (${neighbours.reduce((s, r) => s + r.length, 0)} pts)`);
