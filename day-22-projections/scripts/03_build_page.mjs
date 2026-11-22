// Day 22 · Projections, step 3: build the self-contained live page.
//
// Inlines d3, d3-geo-projection, the geometry (data.json), the Blue Marble
// texture (as a base64 data URL) and page.js into one HTML file, so the page
// works offline and on GitHub Pages with no other requests (about 2.7 MB).
//
// Inputs: $D22_WORK/data.json, $D22_WORK/bluemarble.jpg, ./page.js
// Output: ../index.html

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const here = path.dirname(fileURLToPath(import.meta.url));
const WORK = process.env.D22_WORK || path.join(here, '../../../work/day-22-projections');
const read = (p, enc = 'utf8') => fs.readFileSync(p, enc);

const d3 = read(path.join(here, 'node_modules/d3/dist/d3.min.js'));
const d3gp = read(path.join(here, 'node_modules/d3-geo-projection/dist/d3-geo-projection.min.js'));
const data = read(path.join(WORK, 'data.json'));
const bluemarble = fs.readFileSync(path.join(WORK, 'bluemarble.jpg')).toString('base64');
const page = read(path.join(here, 'page.js'));

const URL = 'https://abenrob.github.io/30daymap2026/day-22-projections/';
const DESC = 'Greenland unfolds from the Blue Marble globe into 15 map projections at one scale, its true outline fitted to each, and folds back into the globe. Day 22 of #30DayMapChallenge: Projections.';

const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>One Greenland, many Greenlands · Day 22 · Projections</title>
<meta name="description" content="${DESC}">
<meta property="og:title" content="One Greenland, many Greenlands">
<meta property="og:description" content="${DESC}">
<meta property="og:image" content="${URL}images/preview.png">
<meta property="og:image:width" content="1600">
<meta property="og:image:height" content="900">
<meta property="og:image:alt" content="The Blue Marble globe centred on Greenland with the outlines Greenland takes in 15 map projections laid over it at the same scale, Mercator's in red and far larger than the real island">
<meta property="og:url" content="${URL}">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image">
<style>
html, body { margin: 0; height: 100%; background: #e6e1d6; }
body { display: flex; align-items: center; justify-content: center; }
canvas { height: min(100vh, 125vw); width: auto; max-width: 100vw; aspect-ratio: 4 / 5; box-shadow: 0 2px 24px rgba(0,0,0,.12); cursor: pointer; }
</style>
</head>
<body>
<canvas id="c" role="img" aria-label="Animation: Greenland morphing through 15 map projections against its true outline, starting and ending on a photographic globe. Click to pause."></canvas>
<script>${d3}</script>
<script>${d3gp}</script>
<script>window.GEO = ${data}; window.BLUEMARBLE = 'data:image/jpeg;base64,${bluemarble}';</script>
<script>${page}</script>
</body>
</html>
`;

const out = path.join(here, '../index.html');
fs.writeFileSync(out, html);
console.log(`wrote ${out} (${(html.length / 1e6).toFixed(2)} MB)`);
