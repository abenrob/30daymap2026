import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { MapboxOverlay } from '@deck.gl/mapbox';
import { GeoJsonLayer, ScatterplotLayer, TextLayer } from '@deck.gl/layers';

// CARTO Positron basemap (same style URL as BASEMAP.POSITRON in @deck.gl/carto).
const BASEMAP = 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json';

type RGB = [number, number, number];
type Cheese = {
  story_rank: number; cheese: string; n_lists: number; pct_lists: number;
  position_score: number | null; cranfield_rank: number | null; cranfield_aop_rank: number | null; aoc_year: number;
  region: string; milk: string; rind: string; washed_with: string;
  smell_notes: string; story_text: string; taste: string; drink: string; bread: string; food: string; area_km2: number;
  center: [number, number]; bbox: [number, number, number, number];
};

const INK: RGB = [43, 33, 24];
const RIND: RGB = [196, 100, 42];
// Sequential "stink" ramp: pale curd to a deep washed rind.
const RAMP: RGB[] = [[244, 228, 192], [232, 186, 120], [212, 132, 62], [168, 80, 30], [110, 44, 14]];
const RIND_COL: Record<string, RGB> = { washed: [196, 100, 42], bloomy: [214, 200, 160], blue: [92, 112, 128] };
const VIEUX_BOULOGNE: [number, number] = [1.6147, 50.7264];
const FRANCE: [[number, number], [number, number]] = [[-4.9, 42.3], [8.3, 51.1]];

// Intro labels for the three nested Normandy areas, stacked at one point so they don't collide.
const NORMANDY: Record<number, number> = { 8: -30, 2: -12, 4: 6 };

// ?capture&step=N: one chapter, map only, with a short caption on top. Used for the post stills.
const Q = new URLSearchParams(location.search);
const CAPTURE = Q.has('capture');
// ?poster: the 4:5 hero image for the post (render at 540 x 675, 2x).
const POSTER = Q.has('poster');
if (POSTER) document.body.classList.add('poster');
// ?poster&wide: 16:9 card / social preview (render at 800 x 450, 2x).
const WIDE = POSTER && Q.has('wide');
if (WIDE) document.body.classList.add('wide');
if (CAPTURE) document.body.classList.add('capture');

const isMobile = () => window.matchMedia('(max-width: 700px)').matches;

function ramp(pct: number): RGB {
  const t = Math.max(0, Math.min(1, (pct - 17) / (88 - 17))) * (RAMP.length - 1);
  const i = Math.min(Math.floor(t), RAMP.length - 2), f = t - i;
  return RAMP[i].map((v, k) => Math.round(v + (RAMP[i + 1][k] - v) * f)) as RGB;
}
// INAO files Pont-l'Évêque as washed rind ("bloomy, brushed or washed" in its spec), so 'washed' anywhere wins.
const rindClass = (c: Cheese) => (c.rind.includes('washed') ? 'washed' : c.rind === 'blue' ? 'blue' : 'bloomy');

async function main() {
  const fc = await (await fetch('aop.geojson')).json();
  const cheeses: Cheese[] = fc.features.map((f: any) => f.properties);
  const byRank = [...cheeses].sort((a, b) => a.story_rank - b.story_rank);
  const N = byRank.length;
  renderChapters(byRank);

  if (POSTER) { buildPoster(byRank, fc); return; }

  const map = new maplibregl.Map({
    container: 'map', style: BASEMAP, bounds: FRANCE,
    attributionControl: { compact: true }, scrollZoom: false, dragRotate: false, pitchWithRotate: false,
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');
  (window as any).__map = map;
  const overlay = new MapboxOverlay({ interleaved: true, layers: [] });
  map.addControl(overlay as unknown as maplibregl.IControl);

  let current = 0; // 0 intro, 1..N cheeses, 9 recap, 99 outro
  let t0 = performance.now();

  const padding = () =>
    CAPTURE
      ? { top: 190, bottom: 40, left: 30, right: 30 }
      : isMobile()
      ? { top: 50, bottom: Math.round(window.innerHeight * 0.52), left: 24, right: 24 }
      : { top: 70, bottom: 70, left: 520, right: 70 };

  function fly(step: number) {
    map.setPadding({ top: 0, bottom: 0, left: 0, right: 0 });
    if (step >= 1 && step <= N) {
      const b = byRank[step - 1].bbox;
      map.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: padding(), duration: 2200, maxZoom: 9, essential: true });
    } else if (step === 99) {
      map.flyTo({ center: VIEUX_BOULOGNE, zoom: 7.4, padding: padding(), duration: 2200, essential: true });
    } else {
      // Post stills crop to the eight areas; the page shows the whole country.
      const b: [[number, number], [number, number]] = CAPTURE ? [[-2.0, 43.5], [8.0, 50.35]] : FRANCE;
      map.fitBounds(b, { padding: padding(), duration: CAPTURE ? 0 : 2200, essential: true });
    }
    renderLegend(step);
  }

  const active = () => (current >= 1 && current <= N ? byRank[current - 1] : null);

  function fill(c: Cheese): [number, number, number, number] {
    const a = active();
    if (current === 9) return [...RIND_COL[rindClass(c)], 110];
    if (current === 99) return [...ramp(c.pct_lists), 50];
    if (!a) return [...ramp(c.pct_lists), 110];
    return c.story_rank === a.story_rank ? [...ramp(c.pct_lists), 130] : [...ramp(c.pct_lists), 25];
  }
  function line(c: Cheese): [number, number, number, number] {
    const a = active();
    // Solid outlines in a darker shade of each area's own colour.
    const base = current === 9 ? RIND_COL[rindClass(c)] : ramp(c.pct_lists);
    const dark = base.map((v) => Math.round(v * 0.62)) as RGB;
    if (a && c.story_rank !== a.story_rank) return [...dark, 150];
    return [...dark, 255];
  }

  function layers(now: number) {
    const a = active();
    const plume = a ? a.center : current === 99 ? VIEUX_BOULOGNE : null;
    // An odour plume: rings drifting up and out from the cheese's area, fading as they go.
    const rings = plume
      ? [0, 1, 2, 3].map((k) => {
          const t = ((now - t0) / 3200 + k / 4) % 1;
          return { p: plume, r: 14 + t * 90, a: Math.round(170 * (1 - t) ** 1.4) };
        })
      : [];
    // Features stay in one fixed order (largest area first) so deck.gl never re-tessellates; the active
    // outline gets its own layer on top of the nested Normandy areas.
    const activeF = a ? fc.features.filter((f: any) => f.properties.story_rank === a.story_rank) : [];
    return [
      new GeoJsonLayer({
        id: 'aop', data: fc.features, pickable: true, stroked: true, filled: true,
        getFillColor: (f: any) => fill(f.properties),
        getLineColor: (f: any) => line(f.properties),
        getLineWidth: (f: any) => (a && f.properties.story_rank !== a.story_rank ? 0.6 : 1),
        lineJointRounded: true, lineCapRounded: true,
        lineWidthUnits: 'pixels',
        updateTriggers: { getFillColor: current, getLineColor: current, getLineWidth: current },
        onClick: (info: any) => {
          const r = info.object?.properties.story_rank;
          if (r) document.querySelector(`[data-step="${r}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        },
      }),
      new GeoJsonLayer({
        id: 'aop-active', data: activeF, filled: false, stroked: true,
        getLineColor: (f: any) => [...(ramp(f.properties.pct_lists).map((v) => Math.round(v * 0.5)) as RGB), 255], getLineWidth: 1.5, lineWidthUnits: 'pixels', lineJointRounded: true, lineCapRounded: true,
      }),
      new ScatterplotLayer({
        id: 'plume', data: rings,
        getPosition: (d: any) => d.p, getRadius: (d: any) => d.r, radiusUnits: 'pixels',
        stroked: true, filled: false, lineWidthUnits: 'pixels', getLineWidth: 2,
        getLineColor: (d: any) => [...RIND, d.a],
        updateTriggers: { getRadius: now, getLineColor: now },
      } as any),
      new ScatterplotLayer({
        id: 'vb', data: current === 99 ? [VIEUX_BOULOGNE] : [],
        getPosition: (d: any) => d, getRadius: 7, radiusUnits: 'pixels',
        getFillColor: [...RIND, 255], stroked: true, getLineColor: [255, 250, 240], lineWidthUnits: 'pixels', getLineWidth: 2,
      }),
      new TextLayer({
        id: 'labels',
        data: current === 99 ? [{ p: VIEUX_BOULOGNE, t: 'Vieux-Boulogne (no AOP)' }]
          : a ? [{ p: a.center, t: a.cheese }]
          : byRank.map((c) => ({ p: NORMANDY[c.story_rank] ? byRank[1].center : c.center, dy: NORMANDY[c.story_rank] ?? 0, t: `${c.story_rank} ${c.cheese}` })),
        getPosition: (d: any) => d.p, getText: (d: any) => d.t,
        getSize: a || current === 99 ? 17 : 13, getColor: [...INK, 255],
        getPixelOffset: (d: any) => (current === 99 ? [12, 0] : [0, d.dy ?? 0]),
        getTextAnchor: current === 99 ? 'start' : 'middle', getAlignmentBaseline: 'center',
        fontFamily: '"IBM Plex Sans", system-ui, sans-serif', fontWeight: 600,
        outlineWidth: 4, outlineColor: [255, 250, 240, 255], fontSettings: { sdf: true }, characterSet: 'auto',
        updateTriggers: { getSize: current, getPixelOffset: current, getTextAnchor: current },
      } as any),
    ];
  }

  function tick() {
    overlay.setProps({ layers: layers(performance.now()) });
    requestAnimationFrame(tick);
  }
  if (CAPTURE) {
    current = Number(Q.get('step') ?? 0);
    document.getElementById('progress')!.remove();
    const cap = document.createElement('div');
    cap.id = 'cap';
    const c = active();
    cap.innerHTML = c
      ? `<div class="kicker">No. ${c.story_rank} of France's stinkiest AOP cheeses</div><h2>${esc(c.cheese)}</h2><p>On ${c.n_lists} of 24 smelliest-cheese lists${c.cranfield_aop_rank ? ` · measured ${c.cranfield_aop_rank} of 11 AOP` : ''} · ${esc(c.rind)} rind</p>`
      : current === 9
      ? `<div class="kicker">Day 19 · Senses: Smell</div><h2>The rind does the work</h2><p>Five of the eight stinkiest AOP cheeses have washed rinds</p>`
      : `<div class="kicker">Day 19 · Senses: Smell</div><h2>France's stinkiest AOP cheeses</h2><p>Darker = named on more of 24 published smelliest-cheese lists</p>`;
    document.body.append(cap);
    map.on('load', () => { fly(current); requestAnimationFrame(tick); });
    return;
  }
  map.on('load', () => { fly(0); requestAnimationFrame(tick); });
  overlay.setProps({ getCursor: ({ isHovering }: { isHovering: boolean }) => (isHovering ? 'pointer' : 'grab') });

  const progress = document.getElementById('progress')!;
  const steps = Array.from(document.querySelectorAll<HTMLElement>('.step'));
  const io = new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        if (!e.isIntersecting) continue;
        const step = Number(e.target.getAttribute('data-step'));
        if (step === current) continue;
        current = step; t0 = performance.now();
        steps.forEach((el) => el.classList.toggle('active', el === e.target));
        progress.style.width = `${step === 99 ? 100 : (Math.min(step, N + 1) / (N + 2)) * 100}%`;
        if (map.loaded()) fly(step);
      }
    },
    { rootMargin: '-50% 0px -50% 0px', threshold: 0 },
  );
  steps.forEach((el) => io.observe(el));
  steps[0].classList.add('active');
  window.addEventListener('resize', () => fly(current));

  function renderLegend(step: number) {
    const el = document.getElementById('legend')!;
    if (step === 9) {
      el.innerHTML = `<div class="lt">Rind</div>` + (['washed', 'bloomy', 'blue'] as const)
        .map((k) => `<div class="row"><i style="background:rgb(${RIND_COL[k]})"></i>${k}</div>`).join('');
    } else {
      const stops = [17, 35, 53, 70, 88].map((p) => `rgb(${ramp(p)})`).join(',');
      el.innerHTML = `<div class="lt">Share of 24 lists naming it</div><div class="bar" style="background:linear-gradient(90deg,${stops})"></div><div class="ticks"><span>17%</span><span>88%</span></div>`;
    }
  }
}

// ---------- Poster: 4:5 hero image ----------
const ORD = ['', '1st', '2nd', '3rd', '4th', '5th', '6th', '7th', '8th', '9th', '10th', '11th'];
// Badge nudges (px) for the three nested Normandy areas, whose centres nearly coincide.
const BADGE_NUDGE: Record<number, [number, number]> = { 2: [-6, -16], 4: [-30, 12], 8: [16, 14] };

function buildPoster(cs: Cheese[], fc: any) {
  document.getElementById('story')!.remove();
  document.querySelector('.back')!.remove();
  document.getElementById('progress')!.remove();
  document.getElementById('legend')!.remove();
  const head = document.createElement('header');
  head.id = 'phead';
  head.innerHTML = `<div class="kicker">#30DayMapChallenge · Day 19 · Smell</div>
    <h1>France's stinkiest AOP cheeses</h1>
    <p>Eight protected cheeses, ranked by how many of 24 published "smelliest cheese" lists name them, on their official INAO production areas.</p>`;
  document.body.prepend(head);

  const rows = cs.map((c) => {
    const col = `rgb(${ramp(c.pct_lists)})`;
    const meas = c.cranfield_aop_rank ? `${ORD[c.cranfield_aop_rank]}` : '–';
    return `<div class="prow"><span class="pb" style="color:${c.pct_lists >= 50 ? '#fffaf0' : '#2b2118'};background:${col};border-color:rgb(${ramp(c.pct_lists).map((v) => Math.round(v * 0.55))})">${c.story_rank}</span>
      <span class="pn">${esc(c.cheese.replace(' de Normandie', ''))}</span>
      <span class="pbar"><i style="width:${(c.n_lists / 24) * 100}%;background:${col}"></i></span>
      <span class="pv">${c.n_lists}</span><span class="pm">${meas}</span></div>`;
  }).join('');
  const panel = document.createElement('div');
  panel.id = 'ppanel';
  panel.innerHTML = `<div class="phd"><span></span><span></span><span class="ph2">On lists, of 24</span><span class="pm">Measured*</span></div>${rows}
    <div class="pnote">*Cranfield University 2004, electronic nose and 19 human sniffers, rank among the 11 AOP cheeses tested. The smelliest of all, Vieux-Boulogne, has no AOP.</div>`;
  document.body.append(panel);
  const foot = document.createElement('div');
  foot.id = 'pfoot';
  foot.innerHTML = 'AOP areas: INAO (Licence Ouverte) · Pairings: CNAOL · Basemap © CARTO © OpenStreetMap · abenrob.github.io/30daymap2026';
  document.body.append(foot);

  const map = new maplibregl.Map({
    container: 'map', style: 'https://basemaps.cartocdn.com/gl/positron-nolabels-gl-style/style.json',
    bounds: WIDE ? [[-1.9, 43.4], [8.1, 50.45]] : [[-4.8, 43.25], [8.1, 50.5]],
    fitBoundsOptions: { padding: WIDE ? { top: 26, bottom: 26, left: 330, right: 18 } : { top: 150, bottom: 18, left: 12, right: 12 } },
    attributionControl: false, interactive: false, fadeDuration: 0,
  });
  (window as any).__map = map;
  const overlay = new MapboxOverlay({ interleaved: true, layers: [
    new GeoJsonLayer({
      id: 'aop', data: fc.features, stroked: true, filled: true,
      getFillColor: (f: any) => [...ramp(f.properties.pct_lists), 150],
      getLineColor: (f: any) => [...(ramp(f.properties.pct_lists).map((v) => Math.round(v * 0.55)) as RGB), 255],
      getLineWidth: 0.75, lineWidthUnits: 'pixels', lineJointRounded: true, lineCapRounded: true,
    }),
  ] });
  map.addControl(overlay as unknown as maplibregl.IControl);

  map.on('idle', function draw() {
    map.off('idle', draw);
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.id = 'pover';
    const parts: string[] = [];
    for (const c of [...cs].reverse()) {
      const p = map.project(c.center as [number, number]);
      const [dx, dy] = BADGE_NUDGE[c.story_rank] ?? [0, 0];
      const x = p.x + dx, y = p.y + dy;
      // Stink lines: more and taller the more lists name the cheese.
      const n = c.pct_lists >= 50 ? 3 : c.pct_lists >= 25 ? 2 : 1;
      const h = 18 + (c.pct_lists / 88) * 30;
      const dark = `rgb(${ramp(c.pct_lists).map((v) => Math.round(v * 0.55))})`;
      for (let k = 0; k < n; k++) {
        const ox = x + (k - (n - 1) / 2) * 9, oy = y - 13;
        const w = 3.2;
        parts.push(`<path d="M${ox},${oy} c${w},${-h / 6} ${-w},${-h / 3} 0,${-h / 2} s${-w},${-h / 3} 0,${-h / 2}" fill="none" stroke="${dark}" stroke-width="1.6" stroke-linecap="round" opacity="0.85"/>`);
      }
      parts.push(`<circle cx="${x}" cy="${y}" r="10" fill="#fffaf0" stroke="${dark}" stroke-width="1.6"/>
        <text x="${x}" y="${y + 4.2}" text-anchor="middle" class="bn">${c.story_rank}</text>`);
    }
    svg.innerHTML = parts.join('');
    document.body.append(svg);
    document.body.classList.add('ready');
  });
}

function esc(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function renderChapters(cs: Cheese[]) {
  const recap = document.querySelector('.recap')!;
  for (const c of cs) {
    const sec = document.createElement('section');
    sec.className = 'step';
    sec.dataset.step = String(c.story_rank);
    const cran = c.cranfield_aop_rank ? `<b>${c.cranfield_aop_rank}</b><span>of 11 AOP measured</span>` : `<b>–</b><span>not measured</span>`;
    sec.innerHTML = `
      <article class="card">
        <div class="meta"><span class="rank">No. ${c.story_rank}</span><span class="num">AOC ${c.aoc_year} · ${c.area_km2.toLocaleString('en-GB')} km²</span></div>
        <h2>${esc(c.cheese)}</h2>
        <div class="region">${esc(c.region)}</div>
        <div class="stats">
          <div><b>${c.n_lists}</b><span>of 24 lists</span></div>
          <div><b>${c.position_score ?? '–'}</b><span>position score</span></div>
          <div>${cran}</div>
        </div>
        <p class="nose"><span class="label">On the nose</span>${esc(c.smell_notes)}</p>
        <p>${esc(c.story_text)}</p>
        <div class="table"><span class="label">At the table</span><dl>
          <dt>Taste</dt><dd>${esc(c.taste)}</dd><dt>Drink</dt><dd>${esc(c.drink)}</dd><dt>Bread</dt><dd>${esc(c.bread)}</dd>${c.food ? `<dt>With</dt><dd>${esc(c.food)}</dd>` : ''}
        </dl></div>
        <dl class="facts"><dt>Milk</dt><dd>${esc(c.milk)}</dd><dt>Rind</dt><dd>${esc(c.rind)}</dd><dt>Washed with</dt><dd>${esc(c.washed_with)}</dd></dl>
      </article>`;
    recap.before(sec);
  }
}

main();
