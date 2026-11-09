// Day 9 · Urban-rural. One line from Notre-Dame to Chartres, traced in turn by three measures,
// then coloured by the official Degree of Urbanisation class (GHS-SMOD).
//
// Every visual is a pure function of time t (seconds): renderAt(t) draws any frame, so the video
// is rendered by stepping t (scripts/06_render_frames.js) rather than recorded.
// URL options: ?t=12.5 opens on one frame, ?capture hides the controls, and the camera and
// height constants below can be overridden (?az=, ?el=, ?dist=, ?fov=, ?hmax=...) for tuning.
import * as THREE from 'three';
import { Line2 } from 'three/addons/lines/Line2.js';
import { LineMaterial } from 'three/addons/lines/LineMaterial.js';
import { LineGeometry } from 'three/addons/lines/LineGeometry.js';

const Q = new URLSearchParams(location.search);
const num = (k, d) => (Q.has(k) ? parseFloat(Q.get(k)) : d);

// ---------- look ----------
const BG = 0x0f1115;
const MEASURES = [
  { key: 'pop', name: 'Population density', unit: 'people per km² · GHS-POP 2020, 100 m', color: '#f4ecd8' },
  { key: 'imd', name: 'Sealed ground', unit: '% impervious · Copernicus HRL 2018, 10 m', color: '#6fb3ea' },
  { key: 'bv',  name: 'Built volume', unit: 'm³ of building per m² of ground · GHS-BUILT-V 2020, 100 m', color: '#b99cff' },
];
const CLASSES = { 3: { name: 'Urban centre', color: '#ff4f5e' }, 2: { name: 'Urban cluster (towns, suburbs)', color: '#ffb44a' },
                  1: { name: 'Rural', color: '#8fd16a' }, 0: { name: 'Water', color: '#4a90d9' } };
const LABELS = [ [0, 'Paris'], [11, 'Meudon'], [24, 'Magny-les-Hameaux'], [41, 'Clairefontaine'], [61, 'Gallardon'], [77.8, 'Chartres'] ];
const HMAX = num('hmax', 28);     // km of wall height for a value equal to the line maximum
const HCLASS = num('hclass', 1.6); // fixed height of the class line

// ---------- timeline (seconds) ----------
// intro, then one PHASE per measure (trace for TRAVEL, hold, sink by FALL_END), class sweep, finale
const T_INTRO = 2.5, PHASE = 8.0, TRAVEL = 3.2, HOLD_END = 6.2, FALL_END = 7.6;
const T_CLASS = T_INTRO + 3 * PHASE;          // 26.5
const T_FINALE = T_CLASS + 6.0;               // 32.5
const DURATION = T_FINALE + 8.0;              // 40.5
const clamp01 = (x) => Math.min(1, Math.max(0, x));
const ease = (x) => { x = clamp01(x); return x * x * (3 - 2 * x); };
// the travelling front: km reached at time dt after a trace starts (smooth start and arrival)
const front = (dt, dur) => LEN * (0.5 - 0.5 * Math.cos(Math.PI * clamp01(dt / dur)));
const fade = (t, a, b, c, d) => Math.min(ease((t - a) / (b - a)), 1 - ease((t - c) / (d - c)));

// ---------- geography ----------
const R = 6378137;
const merc = (lon, lat) => [R * lon * Math.PI / 180, R * Math.log(Math.tan(Math.PI / 4 + lat * Math.PI / 360))];
// Scene units are ground km, x east, z south, y up, origin at the middle of the line.
let C0, K; // scene origin (mercator) and mercator-to-ground scale (cos of the latitude)
const toScene = (lon, lat, y = 0) => { const [mx, my] = merc(lon, lat); return new THREE.Vector3((mx - C0[0]) * K / 1000, y, -(my - C0[1]) * K / 1000); };

// ---------- three setup ----------
const stage = document.getElementById('stage');
const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(window.devicePixelRatio || 1);
renderer.setClearColor(BG, 1);
stage.appendChild(renderer.domElement);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(num('fov', 14), 1, 5, 5000);
const lineMats = [];
const res = new THREE.Vector2();
function resize() {
  const w = window.innerWidth, h = window.innerHeight;
  renderer.setSize(w, h, false); renderer.domElement.style.width = w + 'px'; renderer.domElement.style.height = h + 'px';
  camera.aspect = w / h; camera.updateProjectionMatrix();
  renderer.getDrawingBufferSize(res); lineMats.forEach((m) => m.resolution.copy(res));
}
// fat lines (Line2) need the drawing-buffer size, so every material is kept for resize()
const lineMat = (color, px, opacity = 1) => {
  const m = new LineMaterial({ color, linewidth: px * (window.devicePixelRatio || 1), transparent: true, opacity, depthWrite: false });
  lineMats.push(m); return m;
};

// ---------- ground: IGN orthophoto, desaturated and darkened ----------
const groundVS = `varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.); }`;
const groundFS = `
  uniform sampler2D map; uniform vec3 bg; uniform float edge; uniform float alphaEdge; varying vec2 vUv;
  void main(){
    vec3 c = texture2D(map, vUv).rgb;
    float g = dot(c, vec3(.299,.587,.114));
    vec3 d = mix(c, vec3(g), .82) * .55 + vec3(.0,.006,.014);
    vec2 e = min(vUv, 1. - vUv);
    float k = smoothstep(0., edge, min(e.x, e.y));
    if (alphaEdge > .5) gl_FragColor = vec4(d, k);
    else gl_FragColor = vec4(mix(bg, d, k), 1.);
  }`;
// Fetch the WMTS tiles covering a lon/lat box at zoom z into one canvas; returns it with its
// mercator bounds. Resolves only when every tile has loaded or failed, so 'ready' means complete.
async function mosaic(z, w, s, e, n) {
  const N = 2 ** z, tx = (lon) => (lon + 180) / 360 * N;
  const ty = (lat) => { const r = lat * Math.PI / 180; return (1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2 * N; };
  const x0 = Math.floor(tx(w)), x1 = Math.floor(tx(e)), y0 = Math.floor(ty(n)), y1 = Math.floor(ty(s));
  const cv = document.createElement('canvas'); cv.width = (x1 - x0 + 1) * 256; cv.height = (y1 - y0 + 1) * 256;
  const ctx = cv.getContext('2d'); ctx.fillStyle = '#1a1c20'; ctx.fillRect(0, 0, cv.width, cv.height);
  const jobs = [];
  for (let x = x0; x <= x1; x++) for (let y = y0; y <= y1; y++) {
    jobs.push(new Promise((ok) => {
      const url = `https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=ORTHOIMAGERY.ORTHOPHOTOS&STYLE=normal&TILEMATRIXSET=PM&TILEMATRIX=${z}&TILEROW=${y}&TILECOL=${x}&FORMAT=image/jpeg`;
      const tryLoad = (left) => {   // the Geoplateforme occasionally drops a tile; retry before giving up
        const im = new Image(); im.crossOrigin = 'anonymous';
        im.onload = () => { ctx.drawImage(im, (x - x0) * 256, (y - y0) * 256); ok(); };
        im.onerror = () => (left > 0 ? setTimeout(() => tryLoad(left - 1), 800) : (console.warn('tile failed', z, x, y), ok()));
        im.src = left < 4 ? url + '&r=' + left : url;
      };
      tryLoad(4);
    }));
  }
  await Promise.all(jobs);
  const size = 2 * Math.PI * R / N;
  return { canvas: cv, mx0: -Math.PI * R + x0 * size, mx1: -Math.PI * R + (x1 + 1) * size,
           my1: Math.PI * R - y0 * size, my0: Math.PI * R - (y1 + 1) * size };
}
// A ground plane textured with a mosaic. Its edges fade to the background (alphaEdge false) or
// to transparent (alphaEdge true, for the sharp corridor laid over the wide underlay).
function groundPlane(m, y, edge, alphaEdge) {
  const tex = new THREE.CanvasTexture(m.canvas); tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = renderer.capabilities.getMaxAnisotropy(); tex.minFilter = THREE.LinearMipmapLinearFilter;
  const w = (m.mx1 - m.mx0) * K / 1000, h = (m.my1 - m.my0) * K / 1000;
  const mat = new THREE.ShaderMaterial({ vertexShader: groundVS, fragmentShader: groundFS, transparent: !!alphaEdge, depthWrite: !alphaEdge,
    uniforms: { map: { value: tex }, bg: { value: new THREE.Color(BG) }, edge: { value: edge }, alphaEdge: { value: alphaEdge ? 1 : 0 } } });
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(w, h), mat);
  mesh.rotation.x = -Math.PI / 2;
  mesh.position.set(((m.mx0 + m.mx1) / 2 - C0[0]) * K / 1000, y, -((m.my0 + m.my1) / 2 - C0[1]) * K / 1000);
  mesh.renderOrder = alphaEdge ? 1 : 0;
  scene.add(mesh);
}

// ---------- walls ----------
// Vertical ribbons. aT is 0 at the foot and 1 at the top, so opacity can fade towards the ground.
const wallVS = `attribute float aT; attribute vec3 aColor; varying float vT; varying vec3 vC;
  void main(){ vT = aT; vC = aColor; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.); }`;
const wallFS = `uniform float opacity; uniform float lo; uniform float hi; varying float vT; varying vec3 vC;
  void main(){ gl_FragColor = vec4(vC, opacity * mix(lo, hi, vT)); }`;
const wallMat = (lo, hi) => new THREE.ShaderMaterial({ vertexShader: wallVS, fragmentShader: wallFS, transparent: true, depthWrite: false,
  side: THREE.DoubleSide, uniforms: { opacity: { value: 1 }, lo: { value: lo }, hi: { value: hi } } });

let S, P, n, KM, D, PD, smooth, head, measureWall, measureTop, ghosts, classWall, classCells, groundLine, swath, labelEls, center, nrm, dir, LEN;

// S: samples from profile.json; P: their scene positions; KM, PD: the dense (smoothed) resampling.
// Very slight smoothing: monotone cubic (Fritsch-Carlson) through the 1 km samples, 8 steps per km.
// It passes exactly through every sample and never overshoots, so peaks and zeros stay true.
const SUB = 8;
function monotone(xs, ys) {
  const m = xs.length, d = [], t = new Array(m);
  for (let i = 0; i < m - 1; i++) d.push((ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]));
  t[0] = d[0]; t[m - 1] = d[m - 2];
  for (let i = 1; i < m - 1; i++) t[i] = d[i - 1] * d[i] <= 0 ? 0 : (d[i - 1] + d[i]) / 2;
  for (let i = 0; i < m - 1; i++) {
    if (d[i] === 0) { t[i] = t[i + 1] = 0; continue; }
    const a = t[i] / d[i], b = t[i + 1] / d[i], h = a * a + b * b;
    if (h > 9) { const k = 3 / Math.sqrt(h); t[i] = k * a * d[i]; t[i + 1] = k * b * d[i]; }
  }
  return (x) => {
    let i = Math.min(m - 2, Math.max(0, xs.findIndex((v, j) => j < m - 1 && x <= xs[j + 1])));
    const hh = xs[i + 1] - xs[i], u = (x - xs[i]) / hh, u2 = u * u, u3 = u2 * u;
    return (2 * u3 - 3 * u2 + 1) * ys[i] + (u3 - 2 * u2 + u) * hh * t[i] + (-2 * u3 + 3 * u2) * ys[i + 1] + (u3 - u2) * hh * t[i + 1];
  };
}
// resample every measure at SUB steps per km, already scaled to wall height
function buildDense() {
  KM = [];
  for (let i = 0; i < n - 1; i++) for (let j = 0; j < SUB; j++) KM.push(S[i].km + (S[i + 1].km - S[i].km) * j / SUB);
  KM.push(S[n - 1].km); D = KM.length;
  PD = KM.map((k) => along(k));
  smooth = {};
  MEASURES.forEach((m) => { const f = monotone(S.map((s) => s.km), S.map((s) => s[m.key + '_h']));
    smooth[m.key] = KM.map((k) => Math.max(0, HMAX * f(k))); });
}
// a trace drawn up to the front: full height behind it, a short ramp at the tip, nothing ahead
const traced = (key, F) => KM.map((k, i) => smooth[key][i] * ease((F - k) / 0.6 + 1));
const tracePts = (hs, F, lift = 0) => {
  const pts = [];
  for (let i = 0; i < D && KM[i] <= F; i++) pts.push(PD[i].x, hs[i] + lift, PD[i].z);
  return pts.length >= 6 ? pts : [PD[0].x, lift, PD[0].z, PD[0].x, lift + 1e-3, PD[0].z];
};

// one wall for all three measures (the same line, re-raised), its top edge, the finale outlines
// and the travelling head
function buildMeasureWall() {
  buildDense();
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(D * 2 * 3), 3));
  g.setAttribute('aT', new THREE.BufferAttribute(new Float32Array(D * 2).map((_, i) => i % 2), 1));
  g.setAttribute('aColor', new THREE.BufferAttribute(new Float32Array(D * 2 * 3), 3));
  const idx = [];
  for (let i = 0; i < D - 1; i++) { const a = 2 * i; idx.push(a, a + 2, a + 1, a + 1, a + 2, a + 3); }
  g.setIndex(idx);
  measureWall = new THREE.Mesh(g, wallMat(0.04, 0.42)); measureWall.renderOrder = 3; scene.add(measureWall);
  measureTop = new Line2(new LineGeometry(), lineMat(0xffffff, 3)); measureTop.renderOrder = 4; scene.add(measureTop);
  measureTop.geometry.setPositions(new Array(D * 3).fill(0));
  ghosts = MEASURES.map((m) => { const l = new Line2(new LineGeometry(), lineMat(m.color, 1.8, 0)); l.renderOrder = 4; scene.add(l); return l; });
  head = new THREE.Mesh(new THREE.SphereGeometry(0.42, 16, 12), new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, depthWrite: false }));
  head.renderOrder = 5; scene.add(head);
}
function buildClassWall() {
  // one quad per sample, covering the half-km either side, so class breaks are crisp
  classCells = S.map((s, i) => ({ a: Math.max(0, s.km - 0.5), b: Math.min(LEN, s.km + 0.5), cls: s.smod_l1 }));
  const pos = new Float32Array(classCells.length * 4 * 3), t = new Float32Array(classCells.length * 4), col = new Float32Array(classCells.length * 4 * 3);
  const idx = [];
  classCells.forEach((c, k) => {
    const cc = new THREE.Color(CLASSES[c.cls].color);
    for (let j = 0; j < 4; j++) { t[4 * k + j] = j % 2; col.set([cc.r, cc.g, cc.b], (4 * k + j) * 3); }
    const v = 4 * k; idx.push(v, v + 2, v + 1, v + 1, v + 2, v + 3);
  });
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3)); g.setAttribute('aT', new THREE.BufferAttribute(t, 1));
  g.setAttribute('aColor', new THREE.BufferAttribute(col, 3)); g.setIndex(idx);
  classWall = new THREE.Mesh(g, wallMat(0.55, 0.95)); classWall.renderOrder = 2; scene.add(classWall);
}
// Line2 geometry caches its instance count at first draw, so a line that grows needs a fresh geometry
const setLine = (line, pts) => { line.geometry.dispose(); line.geometry = new LineGeometry(); line.geometry.setPositions(pts); };
const along = (km) => new THREE.Vector3().copy(P[0]).addScaledVector(dir, km);

// ---------- frame ----------
const capEl = document.getElementById('cap'), footEl = document.getElementById('foot');
let capKey = '';
function caption(t) {
  let key = '', html = '', op = 0;
  for (let k = 0; k < 3; k++) {
    const t0 = T_INTRO + k * PHASE;
    if (t >= t0 - 0.3 && t < t0 + FALL_END + 0.2) {
      const m = MEASURES[k]; key = m.key; op = fade(t, t0 - 0.3, t0 + 0.4, t0 + HOLD_END, t0 + FALL_END);
      html = `<div class="name"><span class="swatch" style="background:${m.color}"></span>${m.name}</div><div class="unit">${m.unit}</div>`;
    }
  }
  const row = (c, txt) => `<div class="row"><span class="swatch" style="background:${c}"></span>${txt}</div>`;
  if (t >= T_CLASS - 0.3 && t < T_FINALE) {
    key = 'cls'; op = fade(t, T_CLASS - 0.3, T_CLASS + 0.4, T_FINALE - 0.6, T_FINALE);
    html = `<div class="name">Official class</div><div class="unit">Degree of Urbanisation · GHS-SMOD 2020, 1 km grid</div>
      <div id="legend">${[3, 2, 1].map((c) => row(CLASSES[c].color, CLASSES[c].name)).join('')}</div>`;
  }
  if (t >= T_FINALE) {
    key = 'fin'; op = ease((t - T_FINALE - 0.3) / 0.8);
    html = `<div class="name">Three measures over the official class</div>
      <div id="legend" class="two"><div>${MEASURES.map((m) => row(m.color, m.name)).join('')}</div><div>${[3, 2, 1].map((c) => row(CLASSES[c].color, CLASSES[c].name)).join('')}</div></div>`;
  }
  if (key !== capKey) { capEl.innerHTML = html; capKey = key; }
  capEl.style.opacity = op;
}

// Near side-on with a long lens: a diagonal view made distance read as height. A slow drift in
// azimuth over the whole video keeps it from feeling static.
function cameraAt(t) {
  const u = t / DURATION;
  const az = THREE.MathUtils.degToRad(num('az', 12) + num('azdrift', 4) * (u - 0.5));
  const el = THREE.MathUtils.degToRad(num('el', 22));
  const dist = num('dist', 455);
  const tgt = center.clone().addScaledVector(dir, num('tshift', 0)); tgt.y = num('ty', 9);
  // nrm points to the camera side (north-west of the line); az swings the camera towards Paris
  const h = nrm.clone().multiplyScalar(Math.cos(az)).addScaledVector(dir, -Math.sin(az));
  camera.position.copy(tgt).addScaledVector(h, dist * Math.cos(el)); camera.position.y = tgt.y + dist * Math.sin(el);
  camera.lookAt(tgt);
}

function renderAt(t) {
  t = Math.max(0, Math.min(DURATION, t));
  cameraAt(t);
  // intro: the line draws itself from Paris to Chartres
  const draw = ease(t / 1.8);
  const m = Math.max(2, Math.round(draw * (n - 1)) + 1);
  setLine(groundLine, P.slice(0, m).flatMap((p) => [p.x, 0.05, p.z]));
  groundLine.material.opacity = 0.75 * draw;
  swath.material.opacity = 0.07 * ease((t - 0.8) / 1.2);

  // each measure is traced from Paris to Chartres by a moving head, holds, then sinks
  let active = null, hgt = new Array(D).fill(0), F = 0, headOn = 0;
  for (let k = 0; k < 3; k++) {
    const t0 = T_INTRO + k * PHASE;
    if (t >= t0 && t < t0 + FALL_END) {
      active = MEASURES[k]; F = front(t - t0, TRAVEL);
      const down = 1 - ease((t - t0 - HOLD_END) / (FALL_END - HOLD_END));
      hgt = traced(active.key, F).map((h) => h * down);
      headOn = 1 - ease((t - t0 - TRAVEL) / 0.4);
    }
  }
  const pa = measureWall.geometry.attributes.position, ca = measureWall.geometry.attributes.aColor;
  const col = new THREE.Color(active ? active.color : '#ffffff');
  PD.forEach((p, i) => { pa.setXYZ(2 * i, p.x, 0, p.z); pa.setXYZ(2 * i + 1, p.x, hgt[i], p.z);
    ca.setXYZ(2 * i, col.r, col.g, col.b); ca.setXYZ(2 * i + 1, col.r, col.g, col.b); });
  pa.needsUpdate = true; ca.needsUpdate = true; measureWall.geometry.computeBoundingSphere();
  measureWall.visible = measureTop.visible = !!active;
  if (active) { setLine(measureTop, tracePts(hgt, F, 0.02)); measureTop.material.color.set(active.color); }
  // the head: a dot at the tip of the trace while it travels
  let hk = Math.max(0, KM.findIndex((k) => k > F) - 1); if (F >= LEN) hk = D - 1;
  head.visible = !!active && headOn > 0.01; head.material.opacity = headOn;
  if (head.visible) head.position.set(PD[hk].x, hgt[hk] + 0.02, PD[hk].z);

  // class line: fixed height, colour sweeps from Paris outward
  const cp = classWall.geometry.attributes.position;
  classCells.forEach((c, k) => {
    const mid = (c.a + c.b) / 2 / LEN;
    const show = t >= T_CLASS ? ease((front(t - T_CLASS, TRAVEL) - mid * LEN) / 1.5 + 0.5) : 0;
    const h = HCLASS * show, A = along(c.a), B = along(c.b);
    cp.setXYZ(4 * k, A.x, 0, A.z); cp.setXYZ(4 * k + 1, A.x, h, A.z); cp.setXYZ(4 * k + 2, B.x, 0, B.z); cp.setXYZ(4 * k + 3, B.x, h, B.z);
  });
  cp.needsUpdate = true; classWall.geometry.computeBoundingSphere();
  classWall.visible = t >= T_CLASS;

  // finale: the three traces run again together, as outlines, over the class line
  // (each lifted a hair so overlapping lines don't z-fight)
  ghosts.forEach((g, k) => {
    const g0 = T_FINALE + 0.25 * k, Fg = front(t - g0, TRAVEL);
    g.visible = t > g0; g.material.opacity = 0.95 * ease((t - g0) / 0.4);
    if (g.visible) setLine(g, tracePts(traced(MEASURES[k].key, Fg), Fg, 0.03 * k));
  });

  caption(t);
  footEl.style.opacity = ease((t - T_FINALE - 1.5) / 1.0); // credits only once the finale holds
  renderer.render(scene, camera);
  placeLabels(t);
  return t;
}

// Commune labels are HTML, pinned to points just in front of the line; each appears as the
// intro line reaches it.
function placeLabels(t) {
  const W = window.innerWidth, H = window.innerHeight, op = ease((t - 1.2) / 1.0);
  LABELS.forEach(([km], j) => {
    const v = along(Math.min(km, LEN)).addScaledVector(nrm, num('laboff', 2.6)).project(camera);
    const el = labelEls[j];
    el.style.left = ((v.x + 1) / 2 * W).toFixed(1) + 'px'; el.style.top = ((1 - v.y) / 2 * H).toFixed(1) + 'px';
    el.style.opacity = op * ease((ease(t / 1.8) * (LEN + 4) - km) / 4);
  });
}

// ---------- boot ----------
async function boot() {
  const data = await (await fetch('profile/profile.json')).json();
  S = data.samples; n = S.length; LEN = data.meta.length_km;
  const lat0 = (S[0].lat + S[n - 1].lat) / 2, lon0 = (S[0].lon + S[n - 1].lon) / 2;
  C0 = merc(lon0, lat0); K = Math.cos(lat0 * Math.PI / 180);
  P = S.map((s) => toScene(s.lon, s.lat));
  dir = new THREE.Vector3().subVectors(P[n - 1], P[0]); dir.y = 0; dir.normalize();
  nrm = new THREE.Vector3(dir.z, 0, -dir.x); if (nrm.z > 0) nrm.negate(); // perpendicular, to the north-west side
  center = P[0].clone().lerp(P[n - 1], 0.5);

  // the line on the ground and the faint 3 km swath the values are averaged over
  groundLine = new Line2(new LineGeometry(), lineMat(0xffffff, 1.4, 0.75)); groundLine.renderOrder = 2; scene.add(groundLine);
  const sw = new THREE.Mesh(new THREE.PlaneGeometry(LEN, 3), new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.07, depthWrite: false }));
  sw.rotation.x = -Math.PI / 2; sw.rotation.z = Math.atan2(-dir.z, dir.x); sw.position.copy(center).setY(0.02); sw.renderOrder = 1; scene.add(sw); swath = sw;
  buildMeasureWall(); buildClassWall();
  const lab = document.getElementById('labels');
  labelEls = LABELS.map(([, txt]) => { const d = document.createElement('div'); d.className = 'lab'; d.textContent = txt; lab.appendChild(d); return d; });
  resize(); window.addEventListener('resize', () => { resize(); renderAt(current); });

  // ground: wide z9 underlay to the horizon, sharper z12 corridor on top (edges fade into the underlay)
  const lons = S.map((s) => s.lon), lats = S.map((s) => s.lat);
  const bb = (dk) => { const dlat = dk / 111.2, dlon = dk / (111.2 * K);
    return [Math.min(...lons) - dlon, Math.min(...lats) - dlat, Math.max(...lons) + dlon, Math.max(...lats) + dlat]; };
  const [far, near] = await Promise.all([mosaic(9, ...bb(170)), mosaic(12, ...bb(14))]);
  groundPlane(far, -0.05, 0.35, false); groundPlane(near, 0, 0.12, true);
  await document.fonts.ready;
  document.body.dataset.ready = '1';
}

// Interactive playback: the clock only chooses t; drawing is still renderAt(t). Loops with a 2 s pause.
let current = 0, playing = !Q.has('t'), clock0 = performance.now();
const btn = document.getElementById('play'), scrub = document.getElementById('scrub');
if (Q.has('capture')) document.body.classList.add('capture');
window.renderAt = (t) => { current = t; return renderAt(t); };
window.DURATION = DURATION;
window.ready = boot().then(() => {
  current = num('t', 0); renderAt(current);
  scrub.max = DURATION; btn.textContent = playing ? 'Pause' : 'Play';
  btn.onclick = () => { playing = !playing; btn.textContent = playing ? 'Pause' : 'Play'; clock0 = performance.now() - current * 1000; };
  scrub.oninput = () => { playing = false; btn.textContent = 'Play'; current = parseFloat(scrub.value); renderAt(current); };
  const loop = () => {
    if (playing) { current = ((performance.now() - clock0) / 1000) % (DURATION + 2); renderAt(current); scrub.value = current; }
    requestAnimationFrame(loop);
  };
  clock0 = performance.now() - current * 1000; loop();
});
