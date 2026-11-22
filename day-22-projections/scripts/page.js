// Day 22 · Projections: one Greenland, many Greenlands.
//
// It opens on NASA's Blue Marble, centred on Greenland, which unfolds into
// Mercator. Greenland then morphs through 15 map projections at one shared scale. A red dashed
// outline of its true shape is fitted onto each frame by rotation and translation
// only, and two readouts score each projection: area relative to the truth, and
// shape error once size is ignored. The finale pulls back to the whole globe,
// the page goes from paper to black, and the flat globe becomes the Blue Marble
// again, so the last frame matches the first and the video loops.
//
// The page is one 1080 x 1350 canvas. render(t) draws the frame at time t in
// seconds and keeps no state between frames, so the recorder (04_record.py) can
// step it frame by frame and the live page can loop it.
//
// Inputs, inlined by 03_build_page.mjs:
//   window.GEO         geometry from 02_prep_geometry.mjs (lon/lat degrees)
//   window.BLUEMARBLE  equirectangular Blue Marble JPEG as a data URL
// Globals set for the recorder: window.renderAt, window.TOTAL, window.READY.
// Set window.__RECORD before load to stop the live loop, window.__DPR to fix the pixel ratio.

(function () {
  const D = window.GEO;
  const W = 1080, H = 1350;                 // 4:5 frame, CSS pixels
  const C = D.centroid;                     // Greenland's centroid [lon, lat], about 41.8 W, 73.1 N

  const canvas = document.getElementById('c');
  const ctx = canvas.getContext('2d');
  const DPR = window.__DPR || Math.min(2, window.devicePixelRatio || 1);
  canvas.width = W * DPR; canvas.height = H * DPR;
  ctx.setTransform(DPR, 0, 0, DPR, 0, 0);

  // ---------------------------------------------------------------------------
  // Projections, in playing order (roughly worst to best for Greenland).
  // [name, subtitle, factory]. World projections keep their default central
  // meridian (0) on purpose: that is how Greenland appears on the world maps
  // people actually see. The local projections at the end are centred on it.
  // ---------------------------------------------------------------------------
  const P = [
    ['Mercator', 'Conformal · 1569', () => d3.geoMercator()],
    ['Miller', 'Compromise · 1942', () => d3.geoMiller()],
    ['Plate Carrée', 'Equidistant · c. 100 AD', () => d3.geoEquirectangular()],
    ['Gall–Peters', 'Equal-area · 1855 / 1973', () => d3.geoCylindricalEqualArea().parallel(45)],
    ['Van der Grinten', 'Compromise · 1904', () => d3.geoVanDerGrinten()],
    ['Sinusoidal', 'Equal-area · 16th century', () => d3.geoSinusoidal()],
    ['Mollweide', 'Equal-area · 1805', () => d3.geoMollweide()],
    ['Eckert IV', 'Equal-area · 1906', () => d3.geoEckert4()],
    ['Robinson', 'Compromise · 1963', () => d3.geoRobinson()],
    ['Winkel tripel', 'Compromise · 1921', () => d3.geoWinkel3()],
    ['Natural Earth', 'Compromise · 2007', () => d3.geoNaturalEarth1()],
    ['Equal Earth', 'Equal-area · 2018', () => d3.geoEqualEarth()],
    // d3's Peirce quincuncial is centred on the North Pole (rotate [-90, -90, 45]).
    ['Peirce quincuncial', 'Conformal · 1879 · centred on the North Pole', () => d3.geoPeirceQuincuncial()],
    ['Lambert azimuthal equal-area', 'Equal-area · centred on Greenland', () => d3.geoAzimuthalEqualArea().rotate([-C[0], -C[1]])],
    ['Orthographic', 'The globe · seen from above Greenland', () => d3.geoOrthographic().rotate([-C[0], -C[1]])],
  ];
  const N = P.length;

  // ---------------------------------------------------------------------------
  // Project every layer once per projection, in pixels relative to the projected
  // centroid. Every layer keeps the same points in the same order in every
  // projection, so a morph is a straight point-by-point interpolation.
  // ---------------------------------------------------------------------------
  const layers = { main: [D.main], isl: D.glIslands, nb: D.neighbours, grat: D.grat };

  function projectAll(make, R) {
    const p = make().scale(R).translate([0, 0]).precision(0);
    const pc = p(C);
    const toXY = (ring) => {
      const o = new Float32Array(ring.length * 2);
      ring.forEach((q, i) => { const s = p(q); o[2 * i] = s[0] - pc[0]; o[2 * i + 1] = s[1] - pc[1]; });
      return o;
    };
    const out = {};
    for (const name in layers) out[name] = layers[name].map(toXY);
    return out;
  }

  // One globe radius R (px) for every projection, so sizes are comparable.
  // R is the largest that fits every Greenland in the stage except Mercator's,
  // which is allowed to burst out of the frame.
  const CX = W / 2, CY = 770;               // stage centre: Greenland's centroid sits here
  const halfW = W / 2 - 40, halfH = 450;    // stage half-extents
  let ext = 0;
  for (const [name, , make] of P) {
    if (name === 'Mercator') continue;
    const a = projectAll(make, 1).main[0];
    for (let i = 0; i < a.length; i += 2) ext = Math.max(ext, Math.abs(a[i]) / halfW, Math.abs(a[i + 1]) / halfH);
  }
  const R = 1 / ext;
  const proj = P.map(([, , make]) => projectAll(make, R));

  // The globe the video opens and closes on: orthographic centred on Greenland
  // at radius RG_END. The cold open unfolds these points into Mercator.
  const RG = 440, RG_END = RG + 32;         // globe radius after the pull-back, and after the final push-in
  const globeOpen = projectAll(() => d3.geoOrthographic().rotate([-C[0], -C[1]]), RG_END);

  // ---------------------------------------------------------------------------
  // The reference ("ghost"): Greenland in Lambert azimuthal equal-area centred on
  // its own centroid, at the same R. Over an area Greenland's size that is the
  // true shape and the true area to within a fraction of a percent.
  // ---------------------------------------------------------------------------
  const ghost = projectAll(() => d3.geoAzimuthalEqualArea().rotate([-C[0], -C[1]]), R);
  const gm = ghost.main[0];

  // Polygon area from interleaved x,y pixel coordinates (shoelace formula).
  const shoelace = (a) => {
    let s = 0; const n = a.length / 2;
    for (let i = 0; i < n; i++) { const j = (i + 1) % n; s += a[2 * i] * a[2 * j + 1] - a[2 * j] * a[2 * i + 1]; }
    return Math.abs(s / 2);
  };
  const trueArea = shoelace(gm);

  // Fit the ghost onto a projected outline by orthogonal Procrustes. Point i of
  // both rings is the same place on Earth, so the best rotation has a closed form:
  // theta = atan2(sum of cross products, sum of dot products) after centring both.
  // Returns the rotation and centres to draw the ghost with (no scaling, so its
  // size stays true), and the shape error: the residual left after the best
  // rotate + shift + scale fit, normalised to 0 (same shape) .. 1.
  function fitGhost(a) {
    const n = a.length / 2;
    let mx = 0, my = 0, gx = 0, gy = 0;
    for (let i = 0; i < n; i++) { mx += a[2 * i]; my += a[2 * i + 1]; gx += gm[2 * i]; gy += gm[2 * i + 1]; }
    mx /= n; my /= n; gx /= n; gy /= n;
    let dot = 0, cross = 0, gg = 0, aa = 0;
    for (let i = 0; i < n; i++) {
      const px = gm[2 * i] - gx, py = gm[2 * i + 1] - gy;  // ghost, centred
      const qx = a[2 * i] - mx, qy = a[2 * i + 1] - my;    // projected, centred
      dot += px * qx + py * qy; cross += px * qy - py * qx;
      gg += px * px + py * py; aa += qx * qx + qy * qy;
    }
    const r = Math.hypot(dot, cross);
    const shapeErr = Math.sqrt(Math.max(0, 1 - (r * r) / (gg * aa)));
    return { th: Math.atan2(cross, dot), mx, my, gx, gy, shapeErr };
  }

  // ---------------------------------------------------------------------------
  // Timeline (seconds)
  //   OPEN    the Blue Marble on black, Greenland centred (same as the last frame)
  //   UNFOLD  the globe unfolds into Mercator: the imagery and the outlines are
  //           reprojected from orthographic to Mercator together, then the imagery
  //           fades out to the flat map and the background turns to paper
  //   FIRST   extra time on Mercator while the true outline and the scores appear
  //   then for each projection: HOLD on it, MORPH to the next (the last one only holds)
  //   GLOBE   pull back to the whole globe, lights down, Blue Marble
  //   OUTRO   hold on the final frame
  // ---------------------------------------------------------------------------
  const OPEN = 1.5, UNFOLD = 3.0, FIRST = 0.8;
  const HOLD = 1.0, MORPH = 0.8, STEP = HOLD + MORPH;
  const GLOBE = 6.5, OUTRO = 1.8;
  const INTRO = OPEN + UNFOLD;                    // Mercator is fully on screen
  const T_SEQ = INTRO + FIRST + (N - 1) * STEP + HOLD;   // end of the projection sequence
  const TOTAL = T_SEQ + GLOBE + OUTRO;
  const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2); // cubic in-out
  const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));

  const COL = {
    paper: '#f3efe6', ink: '#1f2a33', muted: '#6b7680',
    land: '#dcd6c8', landStroke: '#bdb5a3', grat: '#cfc8b8', sea: '#e9f0f2',
    gl: '#bcd6e6', glStroke: '#1f4e6e',     // Greenland fill and outline
    ghost: '#c8432b',                       // true shape, dashed
    remnant: '#2f6f94',                     // outlines left by earlier projections
  };
  const LIGHT_INK = '#e9edf2', LIGHT_MUTED = '#8d97a3';   // text colours on black
  const FONT = '"Inter", "Helvetica Neue", Helvetica, Arial, sans-serif';

  // Blend two #rrggbb colours.
  const mix = (a, b, t) => {
    const p = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
    const A = p(a), B = p(b);
    return `rgb(${A.map((v, i) => Math.round(v + (B[i] - v) * t)).join(',')})`;
  };
  const SERIF = 'Georgia, "Times New Roman", serif';

  // ---------------------------------------------------------------------------
  // Geometry helpers
  // ---------------------------------------------------------------------------

  // Append an interleaved x,y array to the current canvas path, offset by (ox, oy).
  function pathArr(a, ox, oy, close) {
    ctx.moveTo(ox + a[0], oy + a[1]);
    for (let i = 2; i < a.length; i += 2) ctx.lineTo(ox + a[i], oy + a[i + 1]);
    if (close) ctx.closePath();
  }
  function lerpArr(a, b, t) {
    if (t <= 0) return a;
    if (t >= 1) return b;
    const o = new Float32Array(a.length);
    for (let i = 0; i < a.length; i++) o[i] = a[i] + (b[i] - a[i]) * t;
    return o;
  }
  // Two sets of projected layers blended by t.
  function blendSets(A, B, t) {
    const o = {};
    for (const name in A) o[name] = A[name].map((a, n) => lerpArr(a, B[name][n], t));
    return o;
  }
  const blend = (i, j, t) => blendSets(proj[i], proj[j], t);

  // ---------------------------------------------------------------------------
  // Flat-map drawing (G = one set of projected layers)
  // ---------------------------------------------------------------------------

  // Graticule and the neighbouring land (Canada, Iceland, Svalbard).
  function drawStage(G, alpha) {
    ctx.save(); ctx.globalAlpha = alpha;
    ctx.beginPath(); for (const a of G.grat) pathArr(a, CX, CY, false);
    ctx.strokeStyle = COL.grat; ctx.lineWidth = 1; ctx.stroke();
    ctx.beginPath(); for (const a of G.nb) pathArr(a, CX, CY, true);
    ctx.fillStyle = COL.land; ctx.fill(); ctx.strokeStyle = COL.landStroke; ctx.lineWidth = 0.8; ctx.stroke();
    ctx.restore();
  }

  function drawGreenland(G, alpha) {
    ctx.save(); ctx.globalAlpha = alpha;
    ctx.beginPath();
    for (const a of G.main) pathArr(a, CX, CY, true);
    for (const a of G.isl) pathArr(a, CX, CY, true);
    ctx.fillStyle = COL.gl; ctx.fill();
    ctx.strokeStyle = COL.glStroke; ctx.lineWidth = 2; ctx.lineJoin = 'round'; ctx.stroke();
    ctx.restore();
  }

  // Thin outlines of the projections already shown. The most recent ones are
  // strongest; older ones decay to a light trace that still builds up visibly.
  function drawRemnants(upto, alpha) {
    if (upto <= 0) return;
    ctx.save(); ctx.lineJoin = 'round';
    for (let k = 0; k < upto; k++) {
      const age = upto - k;
      ctx.globalAlpha = alpha * (0.2 + 0.4 * Math.exp(-(age - 1) / 2.5));
      ctx.beginPath(); pathArr(proj[k].main[0], CX, CY, true);
      ctx.strokeStyle = COL.remnant; ctx.lineWidth = 1.1; ctx.stroke();
    }
    ctx.restore();
  }

  // The true outline, rotated and moved onto the current shape by the fit f.
  function drawGhost(alpha, f) {
    if (alpha <= 0) return;
    ctx.save(); ctx.globalAlpha = alpha;
    ctx.translate(CX + f.mx, CY + f.my); ctx.rotate(f.th);
    ctx.beginPath(); pathArr(gm, -f.gx, -f.gy, true);
    ctx.setLineDash([7, 6]); ctx.strokeStyle = COL.ghost; ctx.lineWidth = 2.2; ctx.lineJoin = 'round'; ctx.stroke();
    ctx.restore();
  }

  // ---------------------------------------------------------------------------
  // Text
  // ---------------------------------------------------------------------------
  function text(s, x, y, font, color, align = 'left', alpha = 1) {
    ctx.save(); ctx.globalAlpha = alpha; ctx.font = font; ctx.fillStyle = color;
    ctx.textAlign = align; ctx.textBaseline = 'alphabetic'; ctx.fillText(s, x, y);
    ctx.restore();
  }

  // Title block, projection name, counter and the two scores. A paper-coloured
  // fade behind it keeps it readable when Mercator's Greenland runs underneath.
  // dark (0..1) blends the text toward light-on-black for the globe scenes.
  function header(idx, labelAlpha, area, shapeErr, scoreAlpha, dark = 0) {
    if (dark < 1) {
      ctx.save(); ctx.globalAlpha = Math.pow(1 - dark, 3);   // only once the room is light
      const g = ctx.createLinearGradient(0, 0, 0, 320);
      g.addColorStop(0, 'rgba(243,239,230,0.94)'); g.addColorStop(0.82, 'rgba(243,239,230,0.88)'); g.addColorStop(1, 'rgba(243,239,230,0)');
      ctx.fillStyle = g; ctx.fillRect(0, 0, W, 320);
      ctx.restore();
    }
    const ink = mix(COL.ink, LIGHT_INK, dark), muted = mix(COL.muted, LIGHT_MUTED, dark);
    text('#30DayMapChallenge · Day 22 · Projections', 60, 78, `500 24px ${FONT}`, muted);
    text('One Greenland, many Greenlands', 60, 130, `700 46px ${SERIF}`, ink);
    if (labelAlpha <= 0 && scoreAlpha <= 0) return;
    const [name, sub] = P[idx];
    text(name, 60, 212, `700 40px ${FONT}`, ink, 'left', labelAlpha);
    text(sub, 60, 252, `400 25px ${FONT}`, muted, 'left', labelAlpha);
    text(String(idx + 1).padStart(2, '0') + ' / ' + N, W - 60, 212, `500 26px ${FONT}`, muted, 'right', labelAlpha);
    // Scores go red when they are off by more than about 15% (area) or 8% (shape).
    const a = area >= 9.95 ? area.toFixed(0) : area.toFixed(area >= 1.995 ? 1 : 2);
    text('area ×' + a, W - 60, 254, `700 32px ${FONT}`, area > 1.15 || area < 0.87 ? COL.ghost : COL.glStroke, 'right', scoreAlpha);
    const pct = shapeErr * 100;
    text('shape off ' + (pct < 1 ? pct.toFixed(1) : pct.toFixed(0)) + '%', W - 60, 292, `500 25px ${FONT}`, pct > 8 ? COL.ghost : COL.glStroke, 'right', scoreAlpha);
  }

  function legend(alpha) {
    if (alpha <= 0) return;
    const y = H - 92;
    ctx.save(); ctx.globalAlpha = alpha;
    const g = ctx.createLinearGradient(0, H - 170, 0, H);
    g.addColorStop(0, 'rgba(243,239,230,0)'); g.addColorStop(0.3, 'rgba(243,239,230,0.9)'); g.addColorStop(1, 'rgba(243,239,230,0.94)');
    ctx.fillStyle = g; ctx.fillRect(0, H - 170, W, 170);
    ctx.beginPath(); ctx.moveTo(60, y - 8); ctx.lineTo(108, y - 8);
    ctx.setLineDash([7, 6]); ctx.strokeStyle = COL.ghost; ctx.lineWidth = 2.2; ctx.stroke();
    ctx.setLineDash([]); ctx.beginPath(); ctx.moveTo(60, y + 34); ctx.lineTo(108, y + 34);
    ctx.strokeStyle = COL.remnant; ctx.globalAlpha = alpha * 0.5; ctx.lineWidth = 1.2; ctx.stroke();
    ctx.restore();
    text('true size & shape, rotated + shifted to best fit', 124, y, `400 23px ${FONT}`, COL.ink, 'left', alpha);
    text('outlines left by earlier projections', 124, y + 42, `400 23px ${FONT}`, COL.ink, 'left', alpha);
    text('Natural Earth · d3-geo', W - 60, y + 42, `400 19px ${FONT}`, COL.muted, 'right', alpha);
  }

  // ---------------------------------------------------------------------------
  // Finale, part 1: the flat vector globe (orthographic, Greenland at the centre)
  // ---------------------------------------------------------------------------
  const greenlandGeo = { type: 'MultiPolygon', coordinates: [[D.main], ...D.glIslands.map((r) => [r])] };
  const graticule10 = d3.geoGraticule10();
  const ROT = [-C[0], -C[1]];

  function drawGlobe(scale, alpha) {
    if (alpha <= 0) return;
    const p = d3.geoOrthographic().scale(scale).rotate(ROT).translate([CX, CY]).clipAngle(90).precision(0.3);
    const path = d3.geoPath(p, ctx);
    ctx.save(); ctx.globalAlpha = alpha;
    ctx.beginPath(); path({ type: 'Sphere' }); ctx.fillStyle = COL.sea; ctx.fill();
    ctx.beginPath(); path(graticule10); ctx.strokeStyle = COL.grat; ctx.lineWidth = 0.8; ctx.stroke();
    ctx.beginPath(); path(D.land); ctx.fillStyle = COL.land; ctx.fill(); ctx.strokeStyle = COL.landStroke; ctx.lineWidth = 0.7; ctx.stroke();
    ctx.beginPath(); path(greenlandGeo); ctx.fillStyle = COL.gl; ctx.fill(); ctx.strokeStyle = COL.glStroke; ctx.lineWidth = 1.6; ctx.stroke();
    ctx.beginPath(); path({ type: 'Sphere' }); ctx.strokeStyle = COL.ink; ctx.lineWidth = 1.4; ctx.stroke();
    ctx.restore();
  }

  // ---------------------------------------------------------------------------
  // Finale, part 2: the Blue Marble globe, drawn pixel by pixel.
  // For each pixel in the disc, invert the orthographic projection to lon/lat
  // and sample the equirectangular texture bilinearly. Then: soft light from the
  // upper left, limb darkening, a blue haze toward the rim, and a glow behind.
  // ---------------------------------------------------------------------------
  let TEX = null, TW = 0, TH = 0, IMG = null;
  const READY = new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      TW = img.width; TH = img.height;
      const c = document.createElement('canvas'); c.width = TW; c.height = TH;
      const cc = c.getContext('2d'); cc.drawImage(img, 0, 0);
      TEX = cc.getImageData(0, 0, TW, TH).data;
      IMG = img;
      initUnfold();
      resolve();
    };
    img.src = window.BLUEMARBLE;
  });

  const off = document.createElement('canvas');   // the rendered disc, reused while the radius is unchanged
  const offCtx = off.getContext('2d');
  const lam0 = C[0] * Math.PI / 180, phi0 = C[1] * Math.PI / 180;
  const sinPhi0 = Math.sin(phi0), cosPhi0 = Math.cos(phi0);
  const LIGHT = [-0.35, 0.45, 0.82];               // unit vector toward the light: left, up, toward the viewer
  const HAZE = [110, 170, 255];                    // rim haze colour
  let cache = { r: -1 };

  function rasterGlobe(r) {
    r = Math.round(r * 2) / 2;                     // half-pixel steps: smooth zoom, cache hits on holds
    if (cache.r === r) return cache;
    const pad = Math.ceil(r * 0.12), size = Math.ceil(2 * r + 2 * pad), c0 = size / 2;
    off.width = size; off.height = size;
    const im = offCtx.createImageData(size, size), o = im.data;
    for (let py = 0; py < size; py++) {
      const y = -(py + 0.5 - c0) / r;              // unit-disc coordinates, y up
      for (let px = 0; px < size; px++) {
        const x = (px + 0.5 - c0) / r;
        const rho2 = x * x + y * y, rho = Math.sqrt(rho2);
        if (rho > 1 + 1.5 / r) continue;           // outside the disc (plus an antialiasing margin)
        const z = Math.sqrt(1 - Math.min(rho2, 1)); // height of the sphere toward the viewer
        // Inverse orthographic projection about (lam0, phi0).
        const lat = Math.asin(clamp(z * sinPhi0 + y * cosPhi0, -1, 1));
        const lon = lam0 + Math.atan2(x, z * cosPhi0 - y * sinPhi0);
        // Texture coordinates, wrapping in longitude.
        const u = ((lon / (2 * Math.PI) + 0.5) % 1 + 1) % 1 * TW - 0.5;
        const v = clamp((0.5 - lat / Math.PI) * TH - 0.5, 0, TH - 1.001);
        const u0 = Math.floor(u), v0 = Math.floor(v), fu = u - u0, fv = v - v0;
        const ua = (u0 + TW) % TW, ub = (u0 + 1) % TW;
        const t00 = 4 * (v0 * TW + ua), t01 = 4 * (v0 * TW + ub), t10 = 4 * ((v0 + 1) * TW + ua), t11 = 4 * ((v0 + 1) * TW + ub);
        // Shading.
        const lit = 0.72 + 0.38 * Math.max(0, x * LIGHT[0] + y * LIGHT[1] + z * LIGHT[2]);
        const limb = 0.55 + 0.45 * Math.pow(z, 0.6);
        const haze = Math.pow(1 - z, 2.4) * 0.75;
        const i = 4 * (py * size + px);
        for (let k = 0; k < 3; k++) {
          const val = (TEX[t00 + k] * (1 - fu) + TEX[t01 + k] * fu) * (1 - fv) + (TEX[t10 + k] * (1 - fu) + TEX[t11 + k] * fu) * fv;
          o[i + k] = Math.min(255, val * lit * limb * (1 - haze) + HAZE[k] * haze);
        }
        o[i + 3] = 255 * clamp((1 - rho) * r + 0.5); // antialiased edge
      }
    }
    offCtx.putImageData(im, 0, 0);
    cache = { r, size };
    return cache;
  }

  // Atmosphere glow behind the disc.
  function drawGlow(r, alpha) {
    if (alpha <= 0) return;
    ctx.save(); ctx.globalAlpha = alpha;
    const g = ctx.createRadialGradient(CX, CY, r * 0.96, CX, CY, r * 1.12);
    g.addColorStop(0, 'rgba(120,175,255,0.55)'); g.addColorStop(0.35, 'rgba(80,140,255,0.18)'); g.addColorStop(1, 'rgba(40,90,200,0)');
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(CX, CY, r * 1.12, 0, 2 * Math.PI); ctx.fill();
    ctx.restore();
  }

  function drawEarth(r, alpha) {
    if (alpha <= 0 || !TEX) return;
    const rc = rasterGlobe(r);
    drawGlow(r, alpha);
    ctx.save(); ctx.globalAlpha = alpha;
    ctx.drawImage(off, CX - rc.size / 2, CY - rc.size / 2);
    ctx.beginPath(); ctx.arc(CX, CY, r - 0.5, 0, 2 * Math.PI);                 // thin bright rim
    ctx.strokeStyle = 'rgba(170,205,255,0.35)'; ctx.lineWidth = 1.5; ctx.stroke();
    ctx.restore();
  }

  // ---------------------------------------------------------------------------
  // Cold open: the Blue Marble reprojected from the globe into Mercator.
  // The imagery is laid on a 1.5° lon/lat mesh covering the visible hemisphere.
  // Every mesh vertex has two screen positions, orthographic (the globe, radius
  // RG_END) and Mercator (the first frame of the sequence, same transform as
  // proj[0]); the vertex shader blends them by m, so the photo stretches with the
  // outlines. The fragment shader repeats the globe's light, limb darkening and
  // haze, scaled by `shade`, so m = 0 matches the per-pixel globe above.
  // Two fixes keep the unfold clean: Mercator's polar cap (above 84 N, off the
  // top of the frame anyway) is squashed linearly instead of running to infinity,
  // and the cut Mercator must make through the pole is put on the meridian
  // directly behind Greenland (Mercator centred on 41.8 W, same shape as proj[0]
  // since it only shifts sideways), so it opens symmetrically upward. Cells more
  // than 120° of longitude from Greenland, and those above 80 N, fade out softly
  // as they head for the cut, so the tear dissolves into the dark instead of
  // opening as a hard gap.
  // Drawn with WebGL on its own canvas, then composited onto the 2D canvas.
  // If WebGL is unavailable, the unfold falls back to a plain crossfade.
  // ---------------------------------------------------------------------------
  let GL = null;
  function initUnfold() {
    const cv = document.createElement('canvas');
    cv.width = W * DPR; cv.height = H * DPR;
    const gl = cv.getContext('webgl', { premultipliedAlpha: true, preserveDrawingBuffer: true, antialias: true });
    if (!gl) return;

    const vs = `
      attribute vec2 aOrtho, aMerc, aUV; attribute vec3 aNorm; attribute float aKeep;
      uniform float uM; uniform vec2 uSize;
      varying vec2 vUV; varying vec3 vNorm; varying float vKeep;
      void main() {
        vec2 p = mix(aOrtho, aMerc, uM);                       // screen px, y down
        gl_Position = vec4(p.x / uSize.x * 2.0 - 1.0, 1.0 - p.y / uSize.y * 2.0, 0.0, 1.0);
        vUV = aUV; vNorm = aNorm; vKeep = mix(1.0, aKeep, smoothstep(0.0, 0.15, uM));
      }`;
    const fs = `
      precision mediump float;
      uniform sampler2D uTex; uniform float uShade, uAlpha;
      varying vec2 vUV; varying vec3 vNorm; varying float vKeep;
      void main() {
        vec3 c = texture2D(uTex, vUV).rgb;
        vec3 n = normalize(vNorm);                             // x right, y up, z toward the viewer
        float lit = 0.72 + 0.38 * max(0.0, dot(n, vec3(${LIGHT.join(', ')})));
        float limb = 0.55 + 0.45 * pow(max(n.z, 0.0), 0.6);
        float haze = pow(1.0 - max(n.z, 0.0), 2.4) * 0.75;
        vec3 shaded = c * lit * limb * (1.0 - haze) + vec3(${HAZE.map((v) => (v / 255).toFixed(4)).join(', ')}) * haze;
        float a = uAlpha * vKeep;
        gl_FragColor = vec4(mix(c, shaded, uShade) * a, a);   // premultiplied
      }`;
    const sh = (type, src) => { const o = gl.createShader(type); gl.shaderSource(o, src); gl.compileShader(o); return o; };
    const prog = gl.createProgram();
    gl.attachShader(prog, sh(gl.VERTEX_SHADER, vs)); gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, fs));
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return;
    gl.useProgram(prog);

    // Mesh: cells whose four corners are all on the visible hemisphere.
    const ortho = d3.geoOrthographic().scale(RG_END).rotate(ROT).translate([CX, CY]).precision(0);
    const merc = d3.geoMercator().rotate([-C[0], 0]).scale(R).translate([0, 0]).precision(0);
    const mc = merc(C);
    const lam0 = C[0] * Math.PI / 180, phi0 = C[1] * Math.PI / 180;
    const STEP_DEG = 1.5, LAT_MAX = 90;
    const CAP = 84;
    const mercXY = (lon, lat) => {
      if (lat <= CAP) return merc([lon, lat]);
      const a = merc([lon, CAP]), b = merc([lon, CAP - 1]);
      return [a[0], a[1] - (lat - CAP) * (b[1] - a[1])];      // continue at the slope it has at 84 N
    };
    const vert = (lon, lat) => {
      const o = ortho([lon, lat]), m = mercXY(lon, lat);
      const l = lon * Math.PI / 180 - lam0, p = lat * Math.PI / 180;
      const dLon = Math.abs(((lon - C[0] + 540) % 360) - 180);
      const keep = clamp((180 - dLon) / 60) * clamp((88 - lat) / 8);   // soft fade toward the cut and the pole
      return [o[0], o[1], m[0] - mc[0] + CX, m[1] - mc[1] + CY, (lon + 180) / 360, (90 - lat) / 180,  // u may leave 0..1: REPEAT wraps it
        Math.cos(p) * Math.sin(l),
        Math.cos(phi0) * Math.sin(p) - Math.sin(phi0) * Math.cos(p) * Math.cos(l),
        Math.sin(phi0) * Math.sin(p) + Math.cos(phi0) * Math.cos(p) * Math.cos(l), keep];
    };
    const visible = (lon, lat) => d3.geoDistance([lon, lat], C) < Math.PI / 2 - 1e-3;
    const data = [];
    for (let lon = C[0] - 180; lon < C[0] + 180 - 1e-9; lon += STEP_DEG) {
      for (let lat = -90 + STEP_DEG; lat < LAT_MAX; lat += STEP_DEG) {
        const lat1 = Math.min(lat + STEP_DEG, LAT_MAX), lon1 = lon + STEP_DEG;
        if (!(visible(lon, lat) && visible(lon1, lat) && visible(lon, lat1) && visible(lon1, lat1))) continue;
        const a = vert(lon, lat), b = vert(lon1, lat), c = vert(lon1, lat1), d = vert(lon, lat1);
        data.push(...a, ...b, ...c, ...a, ...c, ...d);
      }
    }
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(data), gl.STATIC_DRAW);
    const F = 4, STRIDE = 10 * F;
    [['aOrtho', 2, 0], ['aMerc', 2, 2], ['aUV', 2, 4], ['aNorm', 3, 6], ['aKeep', 1, 9]].forEach(([name, n, off]) => {
      const loc = gl.getAttribLocation(prog, name);
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, n, gl.FLOAT, false, STRIDE, off * F);
    });

    const tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, gl.RGB, gl.UNSIGNED_BYTE, IMG);
    gl.generateMipmap(gl.TEXTURE_2D);                         // 4096 x 2048 is a power of two
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.REPEAT);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);

    GL = {
      gl, cv, n: data.length / 10,
      uM: gl.getUniformLocation(prog, 'uM'), uShade: gl.getUniformLocation(prog, 'uShade'),
      uAlpha: gl.getUniformLocation(prog, 'uAlpha'),
    };
    gl.uniform2f(gl.getUniformLocation(prog, 'uSize'), W, H);
    gl.uniform1i(gl.getUniformLocation(prog, 'uTex'), 0);
    gl.viewport(0, 0, cv.width, cv.height);
  }

  // Draw the reprojected Blue Marble: m = 0 globe .. 1 Mercator.
  function drawUnfold(m, shade, alpha) {
    if (!GL || alpha <= 0) return false;
    const { gl } = GL;
    gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT);
    gl.uniform1f(GL.uM, m); gl.uniform1f(GL.uShade, shade); gl.uniform1f(GL.uAlpha, alpha);
    gl.drawArrays(gl.TRIANGLES, 0, GL.n);
    ctx.drawImage(GL.cv, 0, 0, W, H);
    return true;
  }

  // Closing (and opening) caption under the globe.
  function caption(alpha, dark) {
    if (alpha <= 0) return;
    const ink = mix(COL.ink, LIGHT_INK, dark), muted = mix(COL.muted, LIGHT_MUTED, dark);
    text('Greenland', CX, H - 118, `700 34px ${SERIF}`, ink, 'center', alpha);
    text('2.17 million km²  ·  seen from above 73°N 42°W', CX, H - 78, `400 23px ${FONT}`, muted, 'center', alpha);
    text('Natural Earth · NASA Blue Marble · d3-geo', W - 60, H - 30, `400 17px ${FONT}`, muted, 'right', alpha);
  }

  // ---------------------------------------------------------------------------
  // render(t): draw the frame at time t (seconds)
  // ---------------------------------------------------------------------------
  function render(t) {
    ctx.save();
    ctx.fillStyle = COL.paper; ctx.fillRect(0, 0, W, H);

    if (t < OPEN) {
      // Cold open: the same frame the video ends on.
      ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H);
      drawEarth(RG_END, 1);
      header(0, 0, 0, 0, 0, 1);
      caption(1, 1);

    } else if (t < INTRO) {
      // Unfold: the Blue Marble is reprojected from the globe into Mercator,
      // zooming to Mercator's extent, while it fades out to reveal the flat map
      // underneath and the room goes from black to paper.
      const u = (t - OPEN) / UNFOLD;
      const m = ease(u);
      const G = blendSets(globeOpen, proj[0], m);   // the vector layers move in step with the imagery
      const dark = 1 - ease(clamp((u - 0.3) / 0.5));
      ctx.fillStyle = mix(COL.paper, '#000000', dark); ctx.fillRect(0, 0, W, H);
      drawGlow(RG_END, 1 - clamp(u / 0.2));
      const imgA = 1 - ease(clamp((u - 0.45) / 0.45));
      const landA = ease(clamp((u - 0.35) / 0.45));
      drawStage(G, landA);
      if (!drawUnfold(m, 1 - ease(clamp(u / 0.4)), imgA)) drawEarth(RG_END, 1 - ease(clamp(u / 0.45)));
      drawGreenland(G, landA * 0.92);
      const labelA = ease(clamp((u - 0.6) / 0.4));
      header(0, labelA, 1, 0, 0, dark);
      caption(1 - clamp(u / 0.2), dark);

    } else if (t < T_SEQ) {
      // The projection sequence: hold, then morph to the next. Mercator gets
      // FIRST extra seconds while the true outline and the scores fade in.
      const s = Math.max(0, t - INTRO - FIRST), k = Math.floor(s / STEP), u = s - k * STEP;
      const introA = ease(clamp((t - INTRO) / (FIRST * 0.8)));
      let G, idx, labelA = 1, remnants;
      if (k >= N - 1) { G = proj[N - 1]; idx = N - 1; remnants = N - 1; }
      else if (u < HOLD) { G = proj[k]; idx = k; remnants = k; }
      else {
        const m = ease((u - HOLD) / MORPH);
        G = blend(k, k + 1, m); remnants = k + 1;
        idx = m < 0.5 ? k : k + 1;           // name swaps halfway, fading out and back in
        labelA = Math.abs(m - 0.5) * 2;
      }
      const fit = fitGhost(G.main[0]);      // scores follow the in-between shapes too
      drawStage(G, 1);
      drawRemnants(remnants, 1);
      drawGreenland(G, 0.92);
      drawGhost(introA, fit);
      header(idx, labelA, shoelace(G.main[0]) / trueArea, fit.shapeErr, introA);
      legend(introA);

    } else {
      // Finale: pull back to the whole globe (Greenland stays centred), the room
      // goes from paper to black, and the vector globe crossfades to Blue Marble.
      const g = clamp((t - T_SEQ) / GLOBE);  // 0..1 over the finale; holds at 1 through the outro
      const z = ease(clamp(g / 0.3));
      const pushIn = ease(clamp((g - 0.5) / 0.5));
      const scale = R + (RG - R) * z + (RG_END - RG) * pushIn;
      const fadeOld = 1 - clamp(g / 0.15);   // flat map, remnants, legend
      const dark = ease(clamp((g - 0.3) / 0.2));
      const earthA = ease(clamp((g - 0.36) / 0.18));

      ctx.fillStyle = mix(COL.paper, '#000000', dark); ctx.fillRect(0, 0, W, H);
      drawStage(proj[N - 1], fadeOld); drawRemnants(N - 1, fadeOld); drawGreenland(proj[N - 1], fadeOld);
      drawGlobe(scale, ease(clamp(g / 0.15)) * (1 - earthA));
      drawEarth(scale, earthA);
      drawGhost(1 - clamp(g / 0.05), fitGhost(proj[N - 1].main[0])); // leave before the globe shrinks

      // Header, inverting from ink-on-paper to light-on-black.
      const ink = mix(COL.ink, LIGHT_INK, dark), muted = mix(COL.muted, LIGHT_MUTED, dark);
      const nameA = 1 - clamp(g / 0.12);
      text('#30DayMapChallenge · Day 22 · Projections', 60, 78, `500 24px ${FONT}`, muted);
      text('One Greenland, many Greenlands', 60, 130, `700 46px ${SERIF}`, ink);
      text(P[N - 1][0], 60, 212, `700 40px ${FONT}`, ink, 'left', nameA);
      text(P[N - 1][1], 60, 252, `400 25px ${FONT}`, muted, 'left', nameA);

      caption(clamp((g - 0.55) / 0.15), dark);
      legend(fadeOld);
    }
    ctx.restore();
  }

  // For the gallery card (05_preview.py): the final globe with no text, and every
  // projection's Greenland outline at the globe's scale, centred where Greenland sits on the globe, so the
  // photo shows the true shape and the outlines show what each projection makes of it.
  window.drawCardFrame = function () {
    ctx.save();
    ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H);
    drawEarth(RG_END, 1);
    ctx.lineJoin = 'round';
    P.forEach(([name, , make]) => {
      const a = projectAll(make, RG_END).main[0];
      const merc = name === 'Mercator';
      ctx.beginPath(); pathArr(a, CX, CY, true);
      ctx.strokeStyle = merc ? 'rgba(255,120,95,0.95)' : 'rgba(225,238,255,0.6)';
      ctx.lineWidth = merc ? 2.2 : 1.3; ctx.stroke();
    });
    ctx.restore();
  };

  window.renderAt = render;
  window.TOTAL = TOTAL;
  window.READY = READY;

  // Live page: loop with a short pause at the end; click or tap to pause.
  if (!window.__RECORD) {
    let t0 = null, paused = false, tp = 0;
    const loop = (ts) => {
      if (t0 == null) t0 = ts;
      if (!paused) tp = ((ts - t0) / 1000) % (TOTAL + 0.8);
      render(Math.min(tp, TOTAL));
      requestAnimationFrame(loop);
    };
    canvas.addEventListener('click', () => {
      paused = !paused;
      if (!paused) t0 = performance.now() - tp * 1000;
    });
    READY.then(() => requestAnimationFrame(loop));
  }
})();
