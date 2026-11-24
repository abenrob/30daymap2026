// The camera choreography, keyed to travel time rather than wall-clock time.
//
//   landing          close on the drop point (zoomClose)
//   0 .. followEnd   drift toward the tip of the fastest line heading
//                    followBearing (south by default), zooming out gently
//   .. wideEnd       a broad zoom out to the whole network
//   after            hold the wide view
//
// The path is one cubic Hermite spline through those keyframes: it starts and
// ends at rest and keeps a continuous speed through the middle, so it glides.

const lerp = (a, b, k) => a + (b - a) * k;

export function createCamera(cfg, graph, wide) {
  const tip = buildTipTrack(cfg, graph);
  const leadAt = t => {
    const p = tip.smoothed(t);
    return [lerp(graph.origin[0], p[0], cfg.lead), lerp(graph.origin[1], p[1], cfg.lead)];
  };

  // Centre and zoom get separate keyframes. The zoom uses monotone tangents
  // (Fritsch-Carlson) so it only ever zooms out: light during the follow,
  // broad after it, never bouncing back in.
  const centerKeys = [
    { t: 0, v: graph.origin.slice() },
    { t: cfg.followEndSec, v: leadAt(cfg.followEndSec) },
    { t: cfg.wideEndSec, v: wide.center },
  ];
  const zoomKeys = [
    { t: 0, v: cfg.zoomClose },
    { t: cfg.followEndSec, v: cfg.zoomFollow },
    { t: cfg.wideEndSec, v: wide.zoom },
  ];
  const lng = spline(centerKeys.map(k => ({ t: k.t, v: k.v[0] })));
  const lat = spline(centerKeys.map(k => ({ t: k.t, v: k.v[1] })));
  const zoom = spline(zoomKeys, { monotone: true });

  return {
    // Camera for a travel time (seconds; negative = before the landing) and
    // loop position (ms, for the optional slow orbit).
    at(sim, loopMs, loopLength) {
      const t = Math.max(0, Math.min(cfg.wideEndSec, sim));
      const orbit = cfg.orbit ? cfg.orbit * (loopMs / loopLength - 0.5) : 0;
      return { center: [lng(t), lat(t)], zoom: zoom(t), pitch: cfg.pitch, bearing: cfg.bearing + orbit };
    },
  };
}

// The tip of the fastest line heading followBearing: for every 10 s of travel
// time, the farthest reached point within +-followSector degrees of that
// bearing. Smoothed (Gaussian, sigma 3 min) so the camera follows the
// corridor's direction rather than hopping between neighbouring streets.
function buildTipTrack(cfg, graph) {
  const STEP = 10, SIGMA = 180 / STEP;
  const n = Math.ceil(cfg.followEndSec / STEP) + 1;
  const [ox, oy] = graph.origin;
  const coslat = Math.cos(oy * Math.PI / 180);

  const best = new Array(n).fill(null);
  for (const { path, ts } of graph.paths) {
    const end = path[path.length - 1], t = ts[ts.length - 1];
    if (t > cfg.followEndSec) continue;
    const dx = (end[0] - ox) * coslat, dy = end[1] - oy;
    const bearing = (Math.atan2(dx, dy) * 180 / Math.PI + 360) % 360;
    let off = Math.abs(bearing - cfg.followBearing) % 360;
    if (off > 180) off = 360 - off;
    if (off > cfg.followSector) continue;
    const k = Math.ceil(t / STEP), r = Math.hypot(dx, dy);
    if (!best[k] || r > best[k].r) best[k] = { r, p: end };
  }

  // Farthest point so far, then a +-90 s moving average.
  const raw = [];
  let cur = { r: 0, p: graph.origin };
  for (let k = 0; k < n; k++) {
    if (best[k] && best[k].r > cur.r) cur = best[k];
    raw.push(cur.p);
  }
  const track = raw.map((_, k) => average(raw, Math.max(0, k - 9), Math.min(n - 1, k + 9), () => 1));

  return {
    smoothed(sec) {
      const k0 = sec / STEP;
      return average(track, Math.max(0, Math.floor(k0 - 3 * SIGMA)), Math.min(n - 1, Math.ceil(k0 + 3 * SIGMA)),
                     j => Math.exp(-0.5 * ((j - k0) / SIGMA) ** 2));
    },
  };
}

function average(points, from, to, weight) {
  let x = 0, y = 0, w = 0;
  for (let j = from; j <= to; j++) {
    const g = weight(j);
    x += points[j][0] * g; y += points[j][1] * g; w += g;
  }
  return [x / w, y / w];
}

// Cubic Hermite spline through keys [{t, v}], zero slope at both ends.
// Inner slopes are central differences; with monotone, they are limited so
// the curve never overshoots between keys.
function spline(keys, { monotone = false } = {}) {
  const n = keys.length;
  const slope = keys.map((k, i) =>
    i === 0 || i === n - 1 ? 0 : (keys[i + 1].v - keys[i - 1].v) / (keys[i + 1].t - keys[i - 1].t));
  if (monotone) {
    for (let i = 1; i < n - 1; i++) {
      const d0 = (keys[i].v - keys[i - 1].v) / (keys[i].t - keys[i - 1].t);
      const d1 = (keys[i + 1].v - keys[i].v) / (keys[i + 1].t - keys[i].t);
      slope[i] = d0 * d1 <= 0 ? 0
        : Math.sign(slope[i]) * Math.min(Math.abs(slope[i]), 3 * Math.abs(d0), 3 * Math.abs(d1));
    }
  }
  return t => {
    let i = 0;
    while (i < n - 2 && t > keys[i + 1].t) i++;
    const a = keys[i], b = keys[i + 1], h = b.t - a.t, u = (t - a.t) / h;
    const u2 = u * u, u3 = u2 * u;
    return (2 * u3 - 3 * u2 + 1) * a.v + (u3 - 2 * u2 + u) * h * slope[i]
         + (-2 * u3 + 3 * u2) * b.v + (u3 - u2) * h * slope[i + 1];
  };
}
