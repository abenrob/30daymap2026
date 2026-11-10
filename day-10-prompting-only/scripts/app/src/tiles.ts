// CARTO basemap vector tiles (no API key) -> plain lon/lat line and polygon lists.
// The map is drawn from the same streets CARTO's Positron basemap uses: tiles are
// fetched for the view's bbox, decoded with @mapbox/vector-tile, and only roads,
// water and green space are kept. Tiles are cached per session.
import { VectorTile } from '@mapbox/vector-tile';
import Pbf from 'pbf';

const STYLE_URL = 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json';
const FALLBACK = 'https://tiles.basemaps.cartocdn.com/v/20261026-01/vectortiles/carto.streets/v2/{z}/{x}/{y}.mvt';

export type LonLat = [number, number];
export interface Road { kind: string; detail?: string; name?: string; coords: LonLat[] }
export interface Area { kind: string; rings: LonLat[][] }
export interface BaseFeatures { roads: Road[]; water: Area[]; parks: Area[] }

// The tile URL is versioned, so read it from the published style and fall back to a known one.
let template: Promise<string> | null = null;
function tileTemplate(): Promise<string> {
  template ??= fetch(STYLE_URL)
    .then((r) => r.json())
    .then((s) => {
      const src = Object.values(s.sources as Record<string, { tiles?: string[] }>).find((v) => v.tiles?.length);
      return src?.tiles?.[0] ?? FALLBACK;
    })
    .catch(() => FALLBACK);
  return template;
}

const cache = new Map<string, Promise<BaseFeatures>>();

/** Slippy-map tile index for a lon/lat at zoom z. */
export function lonLatToTile(lon: number, lat: number, z: number): [number, number] {
  const n = 2 ** z;
  const x = Math.floor(((lon + 180) / 360) * n);
  const y = Math.floor(((1 - Math.asinh(Math.tan((lat * Math.PI) / 180)) / Math.PI) / 2) * n);
  return [x, y];
}

// landuse kinds drawn as green space
const PARK_KINDS = new Set(['park', 'garden', 'grass', 'forest', 'wood', 'cemetery', 'golf_course', 'recreation_ground', 'pitch', 'playground']);

/** Fetch and decode one tile into lon/lat features (memoised). */
async function loadTile(z: number, x: number, y: number): Promise<BaseFeatures> {
  const key = `${z}/${x}/${y}`;
  const hit = cache.get(key);
  if (hit) return hit;
  const p = (async () => {
    const url = (await tileTemplate()).replace('{z}', String(z)).replace('{x}', String(x)).replace('{y}', String(y));
    const res = await fetch(url);
    if (!res.ok) return { roads: [], water: [], parks: [] };
    const tile = new VectorTile(new Pbf(new Uint8Array(await res.arrayBuffer())));
    const roads: Road[] = [], water: Area[] = [], parks: Area[] = [];
    const L = tile.layers;
    if (L.roads) for (let i = 0; i < L.roads.length; i++) {
      const f = L.roads.feature(i);
      const g = f.toGeoJSON(x, y, z).geometry;
      const props = f.properties as Record<string, string>;
      const lines = g.type === 'LineString' ? [g.coordinates] : g.type === 'MultiLineString' ? g.coordinates : [];
      for (const c of lines) roads.push({ kind: props.kind, detail: props.kind_detail, name: props.name, coords: c as LonLat[] });
    }
    const polys = (layer: string, keep: (k: string) => boolean, into: Area[]) => {
      const lyr = L[layer];
      if (!lyr) return;
      for (let i = 0; i < lyr.length; i++) {
        const f = lyr.feature(i);
        const kind = String((f.properties as Record<string, unknown>).kind ?? '');
        if (!keep(kind)) continue;
        const g = f.toGeoJSON(x, y, z).geometry;
        if (g.type === 'Polygon') into.push({ kind, rings: g.coordinates as LonLat[][] });
        else if (g.type === 'MultiPolygon') for (const p of g.coordinates) into.push({ kind, rings: p as LonLat[][] });
      }
    };
    polys('water', (k) => k !== 'fountain', water);
    polys('landuse', (k) => PARK_KINDS.has(k), parks);
    return { roads, water, parks };
  })();
  cache.set(key, p);
  return p;
}

/** All basemap features for a lon/lat bbox at zoom z. */
export async function loadBase(bbox: [number, number, number, number], z: number): Promise<BaseFeatures> {
  const [x0, y1] = lonLatToTile(bbox[0], bbox[1], z);
  const [x1, y0] = lonLatToTile(bbox[2], bbox[3], z);
  const jobs: Promise<BaseFeatures>[] = [];
  for (let x = x0; x <= x1; x++) for (let y = y0; y <= y1; y++) jobs.push(loadTile(z, x, y));
  const parts = await Promise.all(jobs);
  return {
    roads: parts.flatMap((p) => p.roads),
    water: parts.flatMap((p) => p.water),
    parks: parts.flatMap((p) => p.parks),
  };
}
