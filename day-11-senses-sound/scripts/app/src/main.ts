import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { MapboxOverlay } from '@deck.gl/mapbox';
import { ScatterplotLayer, TextLayer } from '@deck.gl/layers';
import type { PickingInfo } from '@deck.gl/core';

// CARTO Dark Matter basemap (same style URL as BASEMAP.DARK_MATTER in @deck.gl/carto).
const BASEMAP = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json';

type Pic = { src: string; pos?: string; credit: string; href?: string };
type Clip = { id: string; start?: number; label: string; short?: string; poster?: Pic };
type Show = {
  step: number; venue: string; venueName: string; address: string;
  date: string; dateLabel: string; bands: string; title: string;
  text: string; why: string; note?: string; video?: Clip; listen?: Clip; image?: Pic;
  coordinates: [number, number];
};
type Venue = { key: string; name: string; coordinates: [number, number]; steps: number[] };

const ACCENT: [number, number, number] = [208, 96, 63];
const INK: [number, number, number] = [236, 230, 218];
const QUIET: [number, number, number] = [154, 146, 132];

const LEFT = new Set(['vogue', 'okhotel', 'crocodile', 'magnuson']);

// ?capture: a fixed-size, text-forward layout for rendering the scroll-through video.
const CAPTURE = new URLSearchParams(location.search).has('capture');
if (CAPTURE) document.body.classList.add('capture');

const isMobile = () => window.matchMedia('(max-width: 700px)').matches;

async function main() {
  const fc = await (await fetch('shows.geojson')).json();
  const shows: Show[] = fc.features.map((f: any) => ({ ...f.properties, coordinates: f.geometry.coordinates }));

  const venues: Venue[] = [];
  for (const s of shows) {
    let v = venues.find((x) => x.key === s.venue);
    if (!v) venues.push((v = { key: s.venue, name: s.venueName, coordinates: s.coordinates, steps: [] }));
    v.steps.push(s.step);
  }

  renderChapters(shows);
  // ?capture&only=5,6,9: a highlight reel keeps only those chapters (plus intro and outro).
  const only = new URLSearchParams(location.search).get('only');
  if (CAPTURE && only) {
    const keep = new Set(only.split(',').map(Number));
    document.querySelectorAll<HTMLElement>('.step').forEach((el) => {
      const n = Number(el.dataset.step);
      if (n !== 0 && n !== 99 && !keep.has(n)) el.remove();
    });
    document.body.classList.add('reel');
  }

  const map = new maplibregl.Map({
    container: 'map',
    style: BASEMAP,
    center: [-122.31, 47.625],
    zoom: 11.5,
    attributionControl: { compact: true },
    scrollZoom: false,
    dragRotate: false,
    pitchWithRotate: false,
  });
  if (!CAPTURE) map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');
  (window as any).__map = map;

  const overlay = new MapboxOverlay({ interleaved: false, layers: [] });
  map.addControl(overlay as unknown as maplibregl.IControl);

  const bounds = new maplibregl.LngLatBounds();
  shows.forEach((s) => bounds.extend(s.coordinates));

  let current = 0; // 0 = intro, 1..n = shows, 99 = outro
  let pulseT0 = performance.now();

  const padding = () =>
    CAPTURE
      ? { top: 30, bottom: Math.round(window.innerHeight * 0.5), left: 250, right: 16 }
      : isMobile()
      ? { top: 40, bottom: Math.round(window.innerHeight * 0.5), left: 20, right: 20 }
      : { top: 60, bottom: 60, left: 480, right: 60 };

  function fly(step: number) {
    const opts = { padding: padding(), duration: CAPTURE ? 1900 : 2200, essential: true, curve: 1.2 };
    if (step === 0 || step === 99) {
      const pad = CAPTURE ? { top: 40, bottom: Math.round(window.innerHeight * 0.48), left: 24, right: 24 } : padding();
      // flyTo leaves its padding on the map, and fitBounds adds its own on top: reset first.
      map.setPadding({ top: 0, bottom: 0, left: 0, right: 0 });
      map.fitBounds(bounds, { padding: { ...pad, top: pad.top + 30, right: pad.right + 90 }, duration: 2200, pitch: 0, bearing: 0, maxZoom: 13 });
      return;
    }
    const s = shows[step - 1];
    const far = s.venue === 'magnuson';
    map.flyTo({ ...opts, center: s.coordinates, zoom: far ? 14.2 : 15.6, pitch: 45, bearing: -20 + (step % 3) * 12 });
  }

  function layers(now: number) {
    const active = current >= 1 && current <= shows.length ? shows[current - 1] : null;
    const reached = current === 99 ? shows.length : current;

    const visited = (v: Venue) => v.steps.some((st) => st <= reached);

    // Expanding rings from the active venue: three waves, one every 0.8 s.
    const waves = active
      ? [0, 1, 2].map((k) => {
          const t = (((now - pulseT0) / 2400 + k / 3) % 1);
          return { coordinates: active.coordinates, r: 10 + t * 70, a: Math.round(200 * (1 - t)) };
        })
      : [];

    return [
      new ScatterplotLayer({
        id: 'waves',
        data: waves,
        getPosition: (d: any) => d.coordinates,
        getRadius: (d: any) => d.r,
        radiusUnits: 'pixels',
        stroked: true,
        filled: false,
        getLineColor: (d: any) => [...ACCENT, d.a],
        lineWidthUnits: 'pixels',
        getLineWidth: 2,
        updateTriggers: { getRadius: now, getLineColor: now },
      }),
      new ScatterplotLayer<Venue>({
        id: 'venues',
        data: venues,
        pickable: true,
        getPosition: (v) => v.coordinates,
        getRadius: (v) => (active && v.key === active.venue ? 11 : 7),
        radiusUnits: 'pixels',
        stroked: true,
        lineWidthUnits: 'pixels',
        getLineWidth: 1.5,
        getFillColor: (v) =>
          active && v.key === active.venue ? [...ACCENT, 255] : visited(v) || current === 0 ? [...INK, 220] : [...QUIET, 110],
        getLineColor: [13, 12, 11, 255],
        updateTriggers: { getRadius: current, getFillColor: current },
        onClick: (info: PickingInfo<Venue>) => {
          if (!info.object) return;
          const next = info.object.steps.find((st) => st > current) ?? info.object.steps[0];
          document.querySelector(`[data-step="${next}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        },
      }),
      new TextLayer<Venue>({
        id: 'labels',
        data: venues.filter((v) => (active ? v.key === active.venue : true)),
        getPosition: (v: Venue) => v.coordinates,
        getText: (v: Venue) => v.name,
        getSize: active ? 15 : 12,
        getColor: active ? [...INK, 255] : [...INK, 200],
        // Downtown venues sit a block apart, so neighbours label to opposite sides.
        getPixelOffset: (v: Venue) => (LEFT.has(v.key) && !active ? [-12, 0] : [12, 0]),
        getTextAnchor: (v: Venue) => (LEFT.has(v.key) && !active ? 'end' : 'start'),
        getAlignmentBaseline: 'center',
        fontFamily: '"IBM Plex Sans", system-ui, sans-serif',
        fontWeight: 600,
        outlineWidth: 3,
        outlineColor: [13, 12, 11, 255],
        fontSettings: { sdf: true },
        characterSet: 'auto',
        updateTriggers: { getSize: current, getColor: current, getPixelOffset: current, getTextAnchor: current },
      } as any),
    ];
  }

  function tick() {
    overlay.setProps({ layers: layers(performance.now()) });
    requestAnimationFrame(tick);
  }

  map.on('load', () => {
    fly(0);
    requestAnimationFrame(tick);
  });

  overlay.setProps({ getCursor: ({ isHovering }: { isHovering: boolean }) => (isHovering ? 'pointer' : 'grab') });

  // Scroll: the step whose box crosses the middle of the viewport is the active one.
  const progress = document.getElementById('progress')!;
  const steps = Array.from(document.querySelectorAll<HTMLElement>('.step'));
  const io = new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        if (!e.isIntersecting) continue;
        const step = Number(e.target.getAttribute('data-step'));
        if (step === current) continue;
        current = step;
        pulseT0 = performance.now();
        steps.forEach((el) => el.classList.toggle('active', el === e.target));
        const pct = step === 99 ? 100 : (step / shows.length) * 100;
        progress.style.width = `${pct}%`;
        if (map.loaded()) fly(step);
        if (CAPTURE) showInset(step === 0 || step === 99 ? null : shows[step - 1]);
      }
    },
    { rootMargin: '-50% 0px -50% 0px', threshold: 0 },
  );
  steps.forEach((el) => io.observe(el));
  steps[0].classList.add('active');

  window.addEventListener('resize', () => fly(current));
}

function esc(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function renderChapters(shows: Show[]) {
  const outro = document.querySelector('.outro')!;
  for (const s of shows) {
    const sec = document.createElement('section');
    sec.className = 'step';
    sec.dataset.step = String(s.step);
    const media = s.video ? videoHtml(s.video) : s.image ? imageHtml(s.image) : '';
    const listen = s.listen
      ? `<p class="listen">${s.video ? 'Also' : 'Listen'}: <a href="https://www.youtube.com/watch?v=${esc(s.listen.id)}" target="_blank" rel="noopener">${s.listen.label} ↗</a></p>`
      : '';
    sec.innerHTML = `
      <article class="card">
        <div class="meta"><span class="date">${s.dateLabel}</span><span class="num">${s.step} / ${shows.length}${s.video ? ' <span class="play-dot"></span>' : ''}</span></div>
        <h2>${s.title}</h2>
        <div class="venue"><b>${esc(s.venueName)}</b> · ${esc(s.address)}</div>
        <div class="bill"><span>On stage:</span> ${esc(s.bands)}</div>
        <p>${s.text}</p>
        ${media}
        <p class="why"><span class="label">Why it matters</span>${s.why}</p>
        ${listen}
        ${s.note ? `<p class="note">${s.note}</p>` : ''}
      </article>`;
    outro.before(sec);
  }

  // Click-to-load: the YouTube player only exists once someone asks to hear it. One plays at a time.
  document.addEventListener('click', (ev) => {
    const btn = (ev.target as HTMLElement).closest('.facade');
    if (!btn) return;
    const player = btn.parentElement as HTMLElement;
    document.querySelectorAll<HTMLElement>('.player.playing').forEach(resetPlayer);
    const { id, start } = player.dataset;
    const iframe = document.createElement('iframe');
    iframe.src = `https://www.youtube-nocookie.com/embed/${id}?autoplay=1&rel=0&start=${start}`;
    iframe.allow = 'autoplay; encrypted-media; picture-in-picture';
    iframe.allowFullscreen = true;
    iframe.title = btn.getAttribute('aria-label') ?? 'YouTube';
    player.dataset.facade = btn.outerHTML;
    btn.replaceWith(iframe);
    player.classList.add('playing');
  });
}

function stillFor(c: Clip) {
  return c.poster ?? { src: `https://i.ytimg.com/vi/${c.id}/hqdefault.jpg`, pos: 'center', credit: '' };
}

function videoHtml(c: Clip) {
  const still = stillFor(c);
  return `<div class="player" data-id="${esc(c.id)}" data-start="${c.start ?? 0}">
      <button class="facade" aria-label="Play: ${esc(c.label.replace(/<[^>]+>/g, ''))}">
        <img src="${esc(still.src)}" alt="" loading="lazy" style="object-position:${still.pos ?? 'center'}">
        <span class="btn"></span>
      </button>
      <div class="caption">▶ ${c.label} · YouTube${c.poster ? `<br>Still: ${credit(c.poster)}` : ''}</div>
    </div>`;
}

function imageHtml(p: Pic) {
  return `<figure class="pic"><img src="${esc(p.src)}" alt="" loading="lazy" style="object-position:${p.pos ?? 'center'}">
      <figcaption class="caption">${credit(p)}</figcaption></figure>`;
}

function credit(p: Pic) {
  return p.href ? `<a href="${esc(p.href)}" target="_blank" rel="noopener">${p.credit}</a>` : p.credit;
}

// Capture mode only: the active show's picture, pinned over the map like a print. Only our own
// pictures (venue photo, poster) go into the video; YouTube stills of the performers stay on the page.
function showInset(s: Show | null) {
  const el = document.getElementById('inset')!;
  el.classList.remove('on', 'tape');
  if (!s || (!s.video && !s.image)) return;
  const pic = s.image ?? s.video?.poster;
  if (pic) {
    el.innerHTML = `<img src="${pic.src}" style="object-position:${pic.pos ?? 'center'}" alt="">${s.video ? '<span class="btn"></span>' : ''}
      <div class="tag">${s.video ? '▶ recording on the page' : 'the room'}</div>`;
  } else {
    el.classList.add('tape');
    const label = s.video!.short ?? s.video!.label.replace(/<[^>]+>/g, '').split(' (')[0];
    el.innerHTML = `<div class="reel"><span class="btn"></span><div class="wave">${'<i></i>'.repeat(22)}</div></div>
      <div class="tag">▶ ${label.length > 46 ? label.slice(0, 44) + '…' : label}</div>`;
  }
  requestAnimationFrame(() => el.classList.add('on'));
}

function resetPlayer(p: HTMLElement) {
  const iframe = p.querySelector('iframe');
  if (iframe && p.dataset.facade) iframe.outerHTML = p.dataset.facade;
  p.classList.remove('playing');
}

main();
