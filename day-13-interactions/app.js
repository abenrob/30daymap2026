// Day 13 · Interactions: where France commutes.
//
// Commuting as spatial interaction. Pick a commune and the page shows both directions of its
// flows: where its residents work (dir 0) and where its workers live (dir 1).
//
// Data (built by scripts/03_web_data.py, all static files read straight from the page):
//   web/places.parquet    one row per place: name, centroid, residents, jobs, and the row range
//                         [flow_start, flow_start + flow_len) holding its flows in flows.parquet.
//                         Loaded whole at start (~0.8 MB).
//   web/communes.parquet  commune and arrondissement outlines, GeoArrow-native geometry (~2.9 MB).
//   web/flows.parquet     every INSEE flow written twice, once under each end, sorted by commune.
//                         A click reads only that commune's rows with one HTTP range request
//                         (hyparquet), typically 50 to 100 KB out of 10 MB. On the live site it is
//                         read from raw.githubusercontent.com (see FLOWS_URL below).
//
// Drawing (deck.gl 9, no basemap): faint commune outlines, nodes at centroids, and flat curved
// arcs whose pulses run from home to workplace (FlowArcLayer, a small shader injection).
//
// URL: #<INSEE code> or #<code>/in. ?capture is video mode: no animation loop, the capture
// script calls renderAt(t) and setDirection(d) for deterministic frames (scripts/04_render_video.cjs).

import { asyncBufferFromUrl, parquetReadObjects, parquetMetadataAsync } from 'https://cdn.jsdelivr.net/npm/hyparquet@1.33.0/+esm';
import { compressors } from 'https://cdn.jsdelivr.net/npm/hyparquet-compressors@1.1.3/+esm';

const { Deck, MapView, WebMercatorViewport, FlyToInterpolator, PolygonLayer, ArcLayer, ScatterplotLayer, TextLayer } = deck;

const DIR_COLOR = { 0: [255, 179, 71], 1: [79, 209, 197] };
const ARC_MIN = 200;   // INSEE: flows under 200 are orders of magnitude only, so they get ≈ and no arc
const ARC_TOP = 10;    // always draw the largest few, even under 200
const params = new URLSearchParams(location.search);
const CAPTURE = params.has('capture');
const LABELS = CAPTURE ? 4 : 6;
const FIT_SHARE = CAPTURE ? 0.7 : 0.85;
const fmt = (n) => Math.round(n).toLocaleString('en-GB');
const $ = (id) => document.getElementById(id);
if (CAPTURE) document.body.classList.add('capture');

// ---------- flowing arcs: pulses travel from home to workplace ----------
// geometry.uv.x is the position along the arc (0 at source, 1 at target).
const flowUniforms = {
  name: 'flow',
  fs: 'uniform flowUniforms { float time; } flow;',
  uniformTypes: { time: 'f32' },
};
class FlowArcLayer extends deck.ArcLayer {
  getShaders() {
    const s = super.getShaders();
    return {
      ...s,
      modules: [...s.modules, flowUniforms],
      inject: {
        ...(s.inject || {}),
        'fs:DECKGL_FILTER_COLOR': `
          float d = fract(geometry.uv.x * 2.0 - flow.time);
          float pulse = smoothstep(0.55, 0.97, d) * (1.0 - smoothstep(0.97, 1.0, d));
          color.rgb = mix(color.rgb, vec3(1.0), pulse * 0.55);
          color.a *= 0.22 + 0.78 * pulse;
        `,
      },
    };
  }
  draw(opts) {
    this.state.model?.shaderInputs.setProps({ flow: { time: this.props.time } });
    super.draw(opts);
  }
}
FlowArcLayer.layerName = 'FlowArcLayer';
FlowArcLayer.defaultProps = { time: 0 };

// ---------- state ----------
const state = { code: null, dir: 0, rows: [], max: 1, time: 0 };
let places, placeByCode, polygons, flowsFile, flowsMeta, searchList;
let viewState = { longitude: 2.4, latitude: 46.6, zoom: 5, pitch: 0, bearing: 0 };

const deckgl = new Deck({
  parent: $('map'),
  views: new MapView({ repeat: false }),
  initialViewState: viewState,
  controller: { dragRotate: false, touchRotate: false },
  onViewStateChange: ({ viewState: v }) => { viewState = v; return v; },
  getCursor: ({ isHovering }) => (isHovering ? 'pointer' : 'grab'),
  layers: [],
});

// ---------- data ----------
// GitHub Pages gzips application/octet-stream on the fly whenever the browser accepts gzip (it always
// does), and byte ranges then apply to the gzipped stream, which breaks range reads. So:
//  - places and communes are downloaded whole (the browser undoes the gzip) and parsed in memory;
//  - flows, the only file read by range, comes from raw.githubusercontent.com on the live site,
//    which serves the same file from the repo uncompressed, with ranges and CORS.
const FLOWS_URL = location.hostname.endsWith('github.io')
  ? 'https://raw.githubusercontent.com/abenrob/30daymap2026/main/day-13-interactions/web/flows.parquet'
  : 'web/flows.parquet';
const wholeFile = (url) => fetch(url).then((r) => { if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`); return r.arrayBuffer(); });
// Wraps an async buffer to count the range requests and bytes a read makes (shown under the chart).
function counting(buf, stats) {
  return { byteLength: buf.byteLength, slice(s, e) { stats.reqs++; stats.bytes += (e ?? buf.byteLength) - s; return buf.slice(s, e); } };
}

async function load() {
  const [pFile, cFile] = await Promise.all([wholeFile('web/places.parquet'), wholeFile('web/communes.parquet')]);
  const [pRows, cRows] = await Promise.all([
    parquetReadObjects({ file: pFile, compressors }),
    parquetReadObjects({ file: cFile, compressors }),
  ]);
  places = pRows;
  placeByCode = new Map(places.map((p) => [p.code, p]));
  polygons = [];
  for (const c of cRows) {
    if (c.code.startsWith('97') || c.code.startsWith('98')) continue;   // overseas: off the mainland view
    for (const poly of c.geometry) {
      const polygon = poly.map((ring) => ring.map((pt) => [pt.x, pt.y]));
      const xs = polygon[0].map((q) => q[0]), ys = polygon[0].map((q) => q[1]);
      polygons.push({ code: c.code, polygon, bbox: [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)] });
    }
  }
  const norm = (s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  searchList = places.filter((p) => p.country === 'FR' && p.flow_len && p.residents > 0)
    .map((p) => ({ p, k: norm(p.name) })).sort((a, b) => b.p.residents - a.p.residents);
  searchList.norm = norm;
  flowsFile = await asyncBufferFromUrl({ url: FLOWS_URL });
  flowsMeta = await parquetMetadataAsync(flowsFile);
  const [code, d] = location.hash.slice(1).split('/');
  await select(placeByCode.has(code) ? code : '38185', d === 'in' ? 1 : 0, false);
  if (CAPTURE) {
    // Deterministic frames for video: the page only moves when the capture script says so.
    window.renderAt = (t) => { state.time = t; renderLayers(); deckgl.redraw('capture'); };
    window.setDirection = (d) => setDir(d, false);
    window.ready = true;
  }
  else requestAnimationFrame(tick);
}

let last = performance.now();
function tick(now) {
  state.time += Math.min(0.05, (now - last) / 1000) * 0.45;
  last = now;
  renderLayers();
  requestAnimationFrame(tick);
}

// Read one commune's flows: its row range comes from places.parquet, so hyparquet fetches only
// the pages that hold those rows (metadata, i.e. the footer, is read once at start).
async function select(code, dir = state.dir, animate = true) {
  const p = placeByCode.get(code);
  if (!p || !p.flow_len) return;
  const stats = { reqs: 0, bytes: 0 };
  const t0 = performance.now();
  state.rows = await parquetReadObjects({
    file: counting(flowsFile, stats), metadata: flowsMeta, compressors,
    columns: ['other', 'dir', 'n', 'km'], rowStart: p.flow_start, rowEnd: p.flow_start + p.flow_len,
  });
  state.query = { ms: performance.now() - t0, ...stats, start: p.flow_start, len: p.flow_len };
  state.code = code;
  setDir(dir, animate);
}

function setDir(dir, animate = true) {
  state.dir = dir;
  state.view = state.rows.filter((r) => r.dir === dir);
  state.max = state.view.length ? state.view[0].n : 1;
  document.body.classList.toggle('dir-in', dir === 1);
  history.replaceState(null, '', `${location.search}#${state.code}${dir ? '/in' : ''}`);
  fit(animate);
  renderLayers();
  renderText();
}

// Fit the commune plus every place within the distance that covers 85% of the workers.
function fit(animate) {
  const p = placeByCode.get(state.code);
  const rows = state.view.filter((r) => r.km != null).sort((a, b) => a.km - b.km);
  const total = rows.reduce((s, r) => s + r.n, 0);
  let acc = 0, dmax = 0;
  for (const r of rows) { acc += r.n; dmax = r.km; if (acc >= FIT_SHARE * total) break; }
  let lo = [p.lon, p.lat], hi = [p.lon, p.lat];
  for (const r of rows) {
    if (r.km > dmax) break;
    const o = placeByCode.get(r.other);
    lo = [Math.min(lo[0], o.lon), Math.min(lo[1], o.lat)]; hi = [Math.max(hi[0], o.lon), Math.max(hi[1], o.lat)];
  }
  const pad = Math.max(0.05, (hi[0] - lo[0]) * 0.06);
  const el = $('map');
  const vp = new WebMercatorViewport({ width: el.clientWidth, height: el.clientHeight });
  const { longitude, latitude, zoom } = vp.fitBounds([[lo[0] - pad, lo[1] - pad], [hi[0] + pad, hi[1] + pad]], { padding: 30 });
  // Video mode renders in software, so only draw the outlines that can be on screen.
  if (CAPTURE) {
    const span = 1.2 * Math.max(hi[0] - lo[0], hi[1] - lo[1]) + 0.3;
    const box = [longitude - span, latitude - span, longitude + span, latitude + span];
    state.visible = polygons.filter((d) => d.bbox[2] > box[0] && d.bbox[0] < box[2] && d.bbox[3] > box[1] && d.bbox[1] < box[3]);
  }
  viewState = { ...viewState, longitude, latitude, zoom: Math.min(zoom, 11),
    ...(animate ? { transitionDuration: 900, transitionInterpolator: new FlyToInterpolator() } : { transitionDuration: 0 }) };
  deckgl.setProps({ initialViewState: viewState });
}

// ---------- layers ----------
function renderLayers() {
  if (!state.code) return;
  const sel = state.code;
  const col = DIR_COLOR[state.dir];
  const at = (code) => { const p = placeByCode.get(code); return [p.lon, p.lat]; };
  const rows = state.view.filter((r) => placeByCode.get(r.other)?.lon != null);
  const arcs = rows.filter((r, i) => r.n >= ARC_MIN || i < ARC_TOP);
  state.drawn = arcs.length; state.total = rows.length;
  const w = (n) => 0.8 + 7 * Math.sqrt(n / state.max);
  const key = `${sel}/${state.dir}`;
  deckgl.setProps({
    layers: [
      new PolygonLayer({
        id: 'outlines', data: CAPTURE ? state.visible : polygons, getPolygon: (d) => d.polygon,
        filled: true, stroked: true, getFillColor: [0, 0, 0, 0],
        getLineColor: (d) => (d.code === sel ? [255, 255, 255, 200] : [120, 135, 160, 34]),
        getLineWidth: (d) => (d.code === sel ? 1.5 : 0.5), lineWidthUnits: 'pixels',
        pickable: true, autoHighlight: true, highlightColor: [255, 255, 255, 18],
        updateTriggers: { getLineColor: sel, getLineWidth: sel },
        onHover: hover, onClick: ({ object }) => object && select(object.code),
      }),
      new FlowArcLayer({
        id: 'flows', data: arcs, time: state.time,
        getSourcePosition: (r) => (state.dir === 0 ? at(sel) : at(r.other)),
        getTargetPosition: (r) => (state.dir === 0 ? at(r.other) : at(sel)),
        getSourceColor: [...col, 255], getTargetColor: [...col, 255],
        getWidth: (r) => w(r.n), widthUnits: 'pixels', getHeight: 0.22, getTilt: 90,
        parameters: { depthTest: false },
        updateTriggers: { getSourcePosition: key, getTargetPosition: key, getSourceColor: key, getTargetColor: key, getWidth: key },
      }),
      new ScatterplotLayer({
        id: 'nodes', data: arcs, getPosition: (r) => at(r.other),
        getRadius: (r) => 1.5 + 9 * Math.sqrt(r.n / state.max), radiusUnits: 'pixels',
        filled: true, getFillColor: [10, 12, 18, 230], stroked: true, getLineColor: [...col, 230], lineWidthMinPixels: 1.2,
        pickable: true, onHover: (i) => hover({ ...i, object: i.object && { code: i.object.other } }),
        onClick: ({ object }) => object && placeByCode.get(object.other)?.country === 'FR' && select(object.other),
        parameters: { depthTest: false },
        updateTriggers: { getRadius: key, getLineColor: key },
      }),
      new ScatterplotLayer({
        id: 'focus', data: [sel], getPosition: at, getRadius: 9, radiusUnits: 'pixels',
        getFillColor: [255, 255, 255, 255], stroked: true, getLineColor: [...col, 120], lineWidthMinPixels: 6,
        parameters: { depthTest: false }, updateTriggers: { getPosition: sel, getLineColor: key },
      }),
      new TextLayer({
        id: 'labels', data: [{ code: sel, focus: true }, ...arcs.slice(0, LABELS).map((r) => ({ code: r.other }))],
        getPosition: (d) => at(d.code), getText: (d) => placeByCode.get(d.code).name,
        getSize: (d) => (d.focus ? 14 : 11), getColor: (d) => (d.focus ? [255, 255, 255, 255] : [200, 207, 218, 230]),
        getPixelOffset: [10, -10], getTextAnchor: 'start', getAlignmentBaseline: 'bottom',
        fontFamily: 'IBM Plex Sans, system-ui, sans-serif', fontWeight: 500, characterSet: 'auto',
        fontSettings: { sdf: true }, outlineWidth: 4, outlineColor: [10, 12, 18, 255],
        parameters: { depthTest: false }, updateTriggers: { getPosition: key, getText: key },
      }),
    ],
  });
}

// ---------- text ----------
// Distance that half of the workers travel less than (each flow weighted by its count).
function weightedMedian(rows) {
  const v = rows.filter((r) => r.km != null).sort((a, b) => a.km - b.km);
  const total = v.reduce((s, r) => s + r.n, 0);
  let acc = 0;
  for (const r of v) { acc += r.n; if (acc >= total / 2) return r.km; }
  return null;
}

function renderText() {
  const p = placeByCode.get(state.code);
  const out = state.rows.filter((r) => r.dir === 0).reduce((s, r) => s + r.n, 0);
  const inn = state.rows.filter((r) => r.dir === 1).reduce((s, r) => s + r.n, 0);
  $('title').textContent = p.name;
  $('dek').innerHTML = `<b class="o">${fmt(out)}</b> of its ${fmt(p.residents)} employed residents work somewhere else. `
    + `<b class="i">${fmt(inn)}</b> of its ${fmt(p.jobs)} jobs are held by people who live somewhere else.`;
  for (const b of document.querySelectorAll('.toggle button')) b.classList.toggle('on', +b.dataset.dir === state.dir);

  $('c-title').innerHTML = state.dir === 0
    ? `Where <span>${p.name}</span>'s residents work`
    : `Where <span>${p.name}</span>'s workers live`;
  $('s-res').textContent = fmt(p.residents);
  $('s-jobs').textContent = fmt(p.jobs);
  $('s-ratio').textContent = p.job_ratio == null ? '–' : p.job_ratio.toFixed(2);
  $('s-stay').textContent = fmt(p.stay);

  const top = state.view.slice(0, 10);
  $('bars').innerHTML = top.map((r) => {
    const o = placeByCode.get(r.other);
    const tag = o?.country === 'FR' ? r.other.slice(0, 2) : o?.country ?? '';
    const n = r.n < ARC_MIN ? `<span class="approx">≈${fmt(r.n)}</span>` : fmt(r.n);
    return `<li data-code="${r.other}"><div class="lab"><span class="nm">${o?.name ?? r.other}<small>${tag}</small></span>`
      + `<span class="v">${n}<small>${r.km == null ? '' : `${Math.round(r.km)} km`}</small></span></div>`
      + `<div class="track"><div class="fill" style="width:${(100 * r.n) / state.max}%"></div></div></li>`;
  }).join('');

  const total = state.dir === 0 ? out : inn;
  const med = weightedMedian(state.view);
  $('foot').innerHTML = `Half ${state.dir === 0 ? 'travel' : 'come from'} under <b>${med == null ? '–' : med.toFixed(med < 10 ? 1 : 0)} km</b> (straight line). `
    + `Arcs: ${state.drawn} of ${state.total} flows (${ARC_MIN}+ workers, or top ${ARC_TOP}). Counts marked ≈ are under ${ARC_MIN}, which INSEE treats as orders of magnitude.`;
  const q = state.query;
  $('query').textContent = `rows ${fmt(q.start)}–${fmt(q.start + q.len)} of 1,940,843 · ${q.reqs} range request${q.reqs === 1 ? '' : 's'} · ${(q.bytes / 1024).toFixed(0)} KB · ${q.ms.toFixed(0)} ms`;
}

function hover({ object, x, y }) {
  const tip = $('tip');
  const p = object && placeByCode.get(object.code);
  if (!p) { tip.hidden = true; return; }
  const r = state.view.find((v) => v.other === object.code);
  const line = object.code === state.code ? 'Selected'
    : r ? `${r.n < ARC_MIN ? '≈' : ''}${fmt(r.n)} ${state.dir === 0 ? 'work here' : 'live here'}` : 'No recorded flow';
  tip.innerHTML = `<b>${p.name}</b> <span class="m">${p.code}</span><div class="m">${line}</div>`;
  tip.style.left = `${x + 14}px`; tip.style.top = `${y + 14}px`;
  tip.hidden = false;
}

// ---------- events ----------
for (const b of document.querySelectorAll('.toggle button')) b.addEventListener('click', () => setDir(+b.dataset.dir));
$('bars').addEventListener('click', (e) => {
  const li = e.target.closest('li'); if (!li) return;
  const p = placeByCode.get(li.dataset.code);
  if (p?.country === 'FR') select(p.code);
});
const q = $('q'), hits = $('hits');
q.addEventListener('input', () => {
  const k = searchList.norm(q.value.trim());
  if (k.length < 2) { hits.hidden = true; return; }
  const found = searchList.filter((s) => s.k.startsWith(k)).slice(0, 8);
  for (const s of searchList) { if (found.length >= 12) break; if (!s.k.startsWith(k) && s.k.includes(k)) found.push(s); }
  hits.innerHTML = found.map(({ p }) => `<li data-code="${p.code}">${p.name}<small>${p.code.slice(0, 2)}</small></li>`).join('');
  hits.hidden = !found.length;
});
hits.addEventListener('click', (e) => {
  const li = e.target.closest('li'); if (!li) return;
  hits.hidden = true; q.value = ''; select(li.dataset.code);
});
q.addEventListener('keydown', (e) => { if (e.key === 'Enter') hits.querySelector('li')?.click(); if (e.key === 'Escape') { hits.hidden = true; q.blur(); } });
window.addEventListener('hashchange', () => {
  const [code, d] = location.hash.slice(1).split('/');
  if (places && (code !== state.code || (d === 'in') !== (state.dir === 1))) select(code, d === 'in' ? 1 : 0);
});
window.addEventListener('resize', () => state.code && fit(false));
load();
