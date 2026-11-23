// Day 24 · Network: one hour on Berlin public transit from Alexanderplatz.
// Data: graph/berlin-transit.json, built once by scripts/01 + 02 from a
// Targomo multigraph. Each path runs from its earlier end to its later end,
// with a start time t0 and an end time t1 (seconds), so it can grow along
// its length.
//
// URL options: ?d=30 (seconds for the hour)  ?w=8 (line px)  ?glow=0.45
//   ?pitch=52  ?bearing=-18  ?orbit=10 (degrees per loop)  ?t=20 (freeze at
//   minute 20)  ?capture (hide buttons/links)
//   Camera: ?zclose=14.8 ?zfollow=13.1 (zoom at landing / end of follow)
//   ?follow=25 ?wide=45 (minutes: end of follow, end of wide zoom-out)
//   ?render (frame-by-frame capture via window.__renderFrame(ms))
//   ?dir=180 (bearing of the line to follow; 180 = south)  ?lead=0.5 (how far toward its tip)  ?free (no choreography)
(() => {
  const P = new URLSearchParams(location.search);
  const num = (k, v) => (P.has(k) && P.get(k) !== "" ? +P.get(k) : v);
  const CAPTURE = P.has("capture");
  if (CAPTURE) document.body.classList.add("capture");
  const RUN = num("d", 30) * 1000, INTRO = 1800, HOLD = 4000;
  const LINE_PX = num("w", 8), HALO = num("glow", 0.45);
  const PITCH = num("pitch", 52), BEARING = num("bearing", -18);
  const ORBIT = num("orbit", CAPTURE ? 10 : 0);
  const FREEZE = P.has("t") ? num("t", 0) * 60 : null;
  // camera: close on the landing, drift along the fastest line in direction
  // DIR while zooming out gently until FOLLOW_END, then a broad zoom out to
  // the whole area by WIDE_END (minutes of travel time)
  const Z_CLOSE = num("zclose", 14.8), Z_FOLLOW = num("zfollow", 13.1);
  const FOLLOW_END = num("follow", 25) * 60, WIDE_END = num("wide", 45) * 60;
  const DIR = num("dir", 180), SECTOR = 20, LEAD = num("lead", 0.5);
  const FREE = P.has("free");

  // Velographs dark-theme gradient: #8700A7 -> #25A39D -> #FDE725
  // ---- glowing, growing path layer ------------------------------------------
  // Per-vertex timestamps are interpolated along each segment, so a path is
  // drawn up to the exact point the clock has reached. The fragment shader
  // draws a bright core with a Gaussian halo across the line's width; fresh
  // line (just reached) is hotter and whiter. Additive blending makes dense
  // corridors bloom.
  class GlowPathLayer extends deck.PathLayer {
    getShaders() {
      const s = super.getShaders();
      s.inject = {
        "vs:#decl": `
          attribute float instanceTimestamps;
          attribute float instanceNextTimestamps;
          varying float vTime;`,
        "vs:#main-end": `
          vTime = mix(instanceTimestamps, instanceNextTimestamps,
                      clamp(vPathPosition.y / max(vPathLength, 1e-6), 0.0, 1.0));`,
        "fs:#decl": `
          uniform float uTime;
          uniform float uMax;
          uniform float uHalo;
          uniform float uSpark;
          varying float vTime;`,
        "fs:#main-start": `
          if (vTime > uTime) discard;`,
        "fs:DECKGL_FILTER_COLOR": `
          float k = clamp(vTime / uMax, 0.0, 1.0);
          vec3 c0 = vec3(0.529, 0.000, 0.655);
          vec3 c1 = vec3(0.145, 0.639, 0.616);
          vec3 c2 = vec3(0.992, 0.906, 0.145);
          vec3 g = k < 0.5 ? mix(c0, c1, k * 2.0) : mix(c1, c2, (k - 0.5) * 2.0);
          float d = abs(geometry.uv.x);  // uv = vPathPosition (x: -1..1 across width)
          float core = 1.0 - smoothstep(0.10, 0.26, d);
          float halo = exp(-d * d * 4.0);
          float spark = exp(-max(uTime - vTime, 0.0) / uSpark);
          vec3 rgb = mix(g, vec3(1.0), core * (0.22 + 0.68 * spark));
          float a = max(core * (0.8 + 0.2 * spark), halo * uHalo * (1.0 + 2.2 * spark));
          color = vec4(rgb, a);`,
      };
      return s;
    }
    initializeState(ctx) {
      super.initializeState(ctx);
      this.getAttributeManager().addInstanced({
        timestamps: {
          size: 1, accessor: "getTimestamps",
          shaderAttributes: {
            instanceTimestamps: { vertexOffset: 0 },
            instanceNextTimestamps: { vertexOffset: 1 },
          },
        },
      });
    }
    draw(params) {
      const p = this.props;
      params.uniforms = Object.assign({}, params.uniforms,
        { uTime: p.time, uMax: p.maxTime, uHalo: p.halo, uSpark: p.spark });
      super.draw(params);
    }
  }
  GlowPathLayer.layerName = "GlowPathLayer";
  GlowPathLayer.defaultProps = {
    getTimestamps: { type: "accessor", value: d => d.ts },
    time: 0, maxTime: 3600, halo: 0.35, spark: 45,
  };

  // additive: rgb += src.rgb * src.a ; alpha accumulates normally
  const ADDITIVE = { depthTest: false, blend: true, blendFunc: [770, 1, 1, 771], blendEquation: 32774 };

  // ---- map ---------------------------------------------------------------------
  const map = new maplibregl.Map({
    container: "map",
    style: "https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json",
    center: [13.4132, 52.5219], zoom: 10, pitch: PITCH, bearing: BEARING, maxPitch: 75,
    attributionControl: false, preserveDrawingBuffer: CAPTURE,
  });
  const overlay = new deck.MapboxOverlay({ interleaved: false, layers: [] });
  map.addControl(overlay);

  let data = [], origin = [13.4132, 52.5219], maxTime = 3600;

  // ---- clock ---------------------------------------------------------------------
  const LOOP = INTRO + RUN + HOLD;
  let clock = FREEZE != null ? INTRO + (FREEZE / 3600) * RUN : 0;
  let playing = FREEZE == null, last = null;
  const $min = document.getElementById("min"), $head = document.getElementById("ramp-head");
  const $play = document.getElementById("play");
  const setPlaying = v => { playing = v; $play.textContent = v ? "Pause" : "Play"; };
  $play.onclick = () => setPlaying(!playing);
  let userCam = FREE;  // set when the reader drags or zooms; Restart hands the camera back
  const restart = () => { clock = 0; userCam = FREE; setPlaying(true); };
  document.getElementById("restart").onclick = restart;
  addEventListener("keydown", e => {
    if (e.code === "Space") { e.preventDefault(); setPlaying(!playing); }
    if (e.key === "r") restart();
  });

  const easeIn = x => x * x * x;
  const easeOut = x => 1 - Math.pow(1 - x, 3);

  function layersAt(ms) {
    const sim = ms < INTRO ? -1 : Math.min(maxTime, ((ms - INTRO) / RUN) * maxTime);
    const p = Math.min(1, ms / INTRO);
    const LAND = 0.55;  // fraction of the intro when the point hits the ground
    const out = [
      new GlowPathLayer({
        id: "net", data, getPath: d => d.path, getTimestamps: d => d.ts,
        time: sim, maxTime, halo: HALO, spark: 45,
        getWidth: LINE_PX, widthUnits: "pixels", widthMinPixels: LINE_PX,
        jointRounded: false, capRounded: false, getColor: [255, 255, 255, 255],
        parameters: ADDITIVE, pickable: false,
      }),
    ];
    // the drop: a streak falls onto Alexanderplatz, then a shockwave
    if (p < LAND) {
      const z = 9000 * (1 - easeIn(p / LAND));
      out.push(new deck.LineLayer({
        id: "streak", data: [0],
        getSourcePosition: () => [origin[0], origin[1], z + 1600],
        getTargetPosition: () => [origin[0], origin[1], z],
        getColor: [255, 255, 255, 230], getWidth: 3, widthUnits: "pixels", parameters: ADDITIVE,
        updateTriggers: { getSourcePosition: z, getTargetPosition: z },
      }));
    } else {
      const q = Math.min(1, (ms / INTRO - LAND) / (1 - LAND) * 0.9);  // 0..1 after landing
      if (ms < INTRO + 900) {
        const r = easeOut(Math.min(1, (ms - LAND * INTRO) / 1400));
        out.push(new deck.ScatterplotLayer({
          id: "shock", data: [0], getPosition: () => origin,
          radiusUnits: "pixels", getRadius: 6 + 90 * r, stroked: true, filled: false,
          lineWidthUnits: "pixels", getLineWidth: 2,
          getLineColor: [255, 255, 255, 255 * (1 - r)], parameters: ADDITIVE,
          updateTriggers: { getRadius: r, getLineColor: r },
        }));
      }
      const pulse = 0.5 + 0.5 * Math.sin(ms / 380);
      out.push(new deck.ScatterplotLayer({
        id: "dot-glow", data: [0], getPosition: () => origin, radiusUnits: "pixels",
        getRadius: 16 + 4 * pulse, getFillColor: [255, 255, 255, 40 + 20 * q],
        parameters: ADDITIVE, updateTriggers: { getRadius: pulse, getFillColor: q },
      }));
      out.push(new deck.ScatterplotLayer({
        id: "dot", data: [0], getPosition: () => origin, radiusUnits: "pixels",
        getRadius: 5, getFillColor: [255, 255, 255, 255], parameters: ADDITIVE,
      }));
    }
    return { out, sim };
  }

  // ---- camera ----------------------------------------------------------------
  const cam = { wide: null, tip: null };
  const lerp = (a, b, k) => a + (b - a) * k;
  // Tip of the fastest line heading in direction DIR: for every 10 s of travel
  // time, the farthest reached path end within +-SECTOR degrees of DIR,
  // then a centred moving average so the camera glides rather than jumps.
  function buildTip() {
    const STEP = 10, n = Math.ceil(FOLLOW_END / STEP) + 1;
    const coslat = Math.cos(origin[1] * Math.PI / 180);
    const best = new Array(n).fill(null);
    for (const d of data) {
      const e = d.path[d.path.length - 1], t = d.ts[d.ts.length - 1];
      if (t > FOLLOW_END) continue;
      const dx = (e[0] - origin[0]) * coslat, dy = e[1] - origin[1];
      const brg = (Math.atan2(dx, dy) * 180 / Math.PI + 360) % 360;
      let off = Math.abs(brg - DIR) % 360; if (off > 180) off = 360 - off;
      if (off > SECTOR) continue;
      const k = Math.ceil(t / STEP), r = Math.hypot(dx, dy);
      if (!best[k] || r > best[k].r) best[k] = { r, p: e };
    }
    const raw = [];
    let cur = { r: 0, p: origin };
    for (let k = 0; k < n; k++) { if (best[k] && best[k].r > cur.r) cur = best[k]; raw.push(cur.p); }
    const W = 9;  // +-90 s
    cam.tip = raw.map((_, k) => {
      let x = 0, y = 0, c = 0;
      for (let j = Math.max(0, k - W); j <= Math.min(n - 1, k + W); j++) { x += raw[j][0]; y += raw[j][1]; c++; }
      return [x / c, y / c];
    });
    cam.step = STEP;
  }
  // Smoothed tip: Gaussian over the raw tip track (sigma 3 min), so the
  // keyframes below pick up the corridor's direction, not single hops.
  function tipSmooth(sim) {
    const SIG = 180 / cam.step, n = cam.tip.length, k0 = sim / cam.step;
    let x = 0, y = 0, w = 0;
    for (let j = Math.max(0, Math.floor(k0 - 3 * SIG)); j <= Math.min(n - 1, Math.ceil(k0 + 3 * SIG)); j++) {
      const g = Math.exp(-0.5 * ((j - k0) / SIG) ** 2);
      x += cam.tip[j][0] * g; y += cam.tip[j][1] * g; w += g;
    }
    return [x / w, y / w];
  }
  // One continuous camera path through three keyframes in travel time:
  // landing, end of follow (toward the smoothed tip), wide view. Cubic Hermite in time,
  // zero speed at both ends, continuous speed through the middle keys;
  // zoom uses monotone (Fritsch-Carlson) tangents so it never bounces back.
  function buildCamera() {
    const F = FOLLOW_END, lead = t => { const p = tipSmooth(t); return [lerp(origin[0], p[0], LEAD), lerp(origin[1], p[1], LEAD)]; };
    const keys = [
      { t: 0, c: origin.slice(), z: Z_CLOSE },
      { t: F, c: lead(F), z: Z_FOLLOW },
      { t: WIDE_END, c: cam.wide.center, z: cam.wide.zoom },
    ];
    // zoom gets its own keys (landing, end of follow, wide) so its speed only
    // ever builds: very light during the follow, broad after it
    const zkeys = [{ t: 0, z: Z_CLOSE }, { t: F, z: Z_FOLLOW }, { t: WIDE_END, z: cam.wide.zoom }];
    const tan = (ks, get) => ks.map((k, i) => {
      if (i === 0 || i === ks.length - 1) return 0;
      return (get(ks[i + 1]) - get(ks[i - 1])) / (ks[i + 1].t - ks[i - 1].t);
    });
    const mx = tan(keys, k => k.c[0]), my = tan(keys, k => k.c[1]), mz = tan(zkeys, k => k.z);
    for (let i = 1; i < zkeys.length - 1; i++) {  // monotone zoom (Fritsch-Carlson)
      const d0 = (zkeys[i].z - zkeys[i - 1].z) / (zkeys[i].t - zkeys[i - 1].t);
      const d1 = (zkeys[i + 1].z - zkeys[i].z) / (zkeys[i + 1].t - zkeys[i].t);
      if (d0 * d1 <= 0) mz[i] = 0;
      else mz[i] = Math.sign(mz[i]) * Math.min(Math.abs(mz[i]), 3 * Math.abs(d0), 3 * Math.abs(d1));
    }
    cam.zkeys = zkeys;
    cam.keys = keys; cam.m = { x: mx, y: my, z: mz };
  }
  function hermite(p0, p1, m0, m1, h, u) {
    const u2 = u * u, u3 = u2 * u;
    return (2 * u3 - 3 * u2 + 1) * p0 + (u3 - 2 * u2 + u) * h * m0 + (-2 * u3 + 3 * u2) * p1 + (u3 - u2) * h * m1;
  }
  function cameraAt(sim, ms) {
    const bearing = BEARING + (ORBIT ? ORBIT * (ms / LOOP - 0.5) : 0);
    const K = cam.keys, M = cam.m, t = Math.max(0, Math.min(K[K.length - 1].t, sim));
    let i = 0; while (i < K.length - 2 && t > K[i + 1].t) i++;
    const h = K[i + 1].t - K[i].t, u = (t - K[i].t) / h;
    const center = [hermite(K[i].c[0], K[i + 1].c[0], M.x[i], M.x[i + 1], h, u),
                    hermite(K[i].c[1], K[i + 1].c[1], M.y[i], M.y[i + 1], h, u)];
    const Z = cam.zkeys; let j = 0; while (j < Z.length - 2 && t > Z[j + 1].t) j++;
    const hz = Z[j + 1].t - Z[j].t, uz = (t - Z[j].t) / hz;
    const zoom = hermite(Z[j].z, Z[j + 1].z, M.z[j], M.z[j + 1], hz, uz);
    return { center, zoom, pitch: PITCH, bearing };
  }

  function draw() {
    const { out, sim } = layersAt(clock);
    overlay.setProps({ layers: out });
    const s = Math.max(0, sim);
    $min.textContent = Math.floor(s / 60);
    $head.style.left = `${(s / maxTime) * 100}%`;
    if (!userCam && cam.wide) map.jumpTo(cameraAt(sim, clock));
  }
  // ?render: no clock of its own; a frame grabber calls __renderFrame(ms)
  // and captures once the basemap has settled.
  const RENDER = P.has("render");
  window.__loop = LOOP;
  window.__renderFrame = ms => new Promise(resolve => {
    clock = ms; draw();
    const done = () => requestAnimationFrame(() => requestAnimationFrame(resolve));
    if (map.loaded() && map.areTilesLoaded()) setTimeout(done, 0);
    else { let fired = false; const f = () => { if (!fired) { fired = true; done(); } };
           map.once("idle", f); setTimeout(f, 8000); }
  });

  function frame(t) {
    if (RENDER) return;
    if (last != null && playing) clock = (clock + (t - last)) % LOOP;
    last = t;
    if (data.length) draw();
    requestAnimationFrame(frame);
  }

  // ---- data -----------------------------------------------------------------------
  const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  fetch(P.get("file") || "graph/berlin-transit.json").then(r => r.json()).then(doc => {
    origin = doc.origin; maxTime = doc.maxTime || 3600;
    const q = doc.q || 1e5, coslat = Math.cos(origin[1] * Math.PI / 180);
    data = doc.paths.map(r => {
      const t0 = r[0], t1 = r[1];
      let x = r[2], y = r[3];
      const path = [[x / q, y / q]], cum = [0];
      let L = 0;
      for (let i = 4; i < r.length; i += 2) {
        x += r[i]; y += r[i + 1];
        L += Math.hypot(r[i] * coslat, r[i + 1]);
        path.push([x / q, y / q]); cum.push(L);
      }
      const ts = cum.map(c => (L > 0 ? t0 + (t1 - t0) * (c / L) : t0));
      return { path, ts };
    });
    if (doc.date) {
      const s = String(doc.date), d = new Date(+s.slice(0, 4), +s.slice(4, 6) - 1, +s.slice(6, 8));
      const hh = String(Math.floor((doc.time || 0) / 3600)).padStart(2, "0");
      const mm = String(Math.floor(((doc.time || 0) % 3600) / 60)).padStart(2, "0");
      document.getElementById("dek").textContent =
        `From Alexanderplatz, ${DAYS[d.getDay()]} ${d.getDate()} ${d.toLocaleString("en", { month: "long" })}, ${hh}:${mm} departure`;
    }
    const [x0, y0, x1, y1] = doc.view || doc.bbox;
    const fit = () => {
      map.fitBounds([[x0, y0], [x1, y1]], { padding: 30, animate: false, pitch: 0, bearing: 0 });
      const z = map.getZoom() + num("zoom", 0.2);
      const c = [(origin[0] + (x0 + x1) / 2) / 2, (origin[1] + (y0 + y1) / 2) / 2];
      cam.wide = { center: c, zoom: z };
      buildTip();
      buildCamera();
      map.jumpTo(cameraAt(FREEZE != null ? FREEZE : -1, clock));
      // a drag, scroll or pinch by the reader hands them the camera
      map.on("movestart", e => { if (e.originalEvent) userCam = true; });
    };
    map.loaded() ? fit() : map.once("load", fit);
    document.getElementById("loading").remove();
    requestAnimationFrame(frame);
  }).catch(err => {
    document.getElementById("loading").textContent =
      "No graph yet: run scripts/01_fetch_geojson.mjs then 02_build_paths.mjs";
    console.error(err);
  });
})();
