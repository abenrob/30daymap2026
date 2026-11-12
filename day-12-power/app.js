/* Day 12 · Power: modelled hourly flows through the Iberian blackout. */
(async function () {
  const params = new URLSearchParams(location.search);
  const CAPTURE = params.has("capture");
  if (CAPTURE) document.body.classList.add("capture");

  // ---- data ---------------------------------------------------------------
  const [meta, buf, series] = await Promise.all([
    fetch("flows/lines.json").then(r => r.json()),
    fetch("flows/flows.bin").then(r => r.arrayBuffer()),
    fetch("flows/series.json").then(r => r.json()),
  ]);
  const FLOWS = new Int16Array(buf);
  const N = meta.lines.length, H = meta.hours;
  const T0 = Date.parse(meta.start);
  const EVENT_H = 82; // 2025-04-28 10:00 UTC = 12:00 CEST hour (collapse at 12:33)

  const R = 6371;
  const lines = meta.lines.map((l, i) => {
    const ts = [0];
    for (let k = 1; k < l.path.length; k++) {
      const [x0, y0] = l.path[k - 1], [x1, y1] = l.path[k];
      const dx = (x1 - x0) * Math.cos(((y0 + y1) / 2) * Math.PI / 180) * Math.PI / 180 * R;
      const dy = (y1 - y0) * Math.PI / 180 * R;
      ts.push(ts[k - 1] + Math.hypot(dx, dy));
    }
    return { i, path: l.path, ts, dc: l.k === "dc", v: l.v, cap: Math.max(l.cap, 1) };
  });

  // ---- colour ---------------------------------------------------------------
  const RAMP = [[0, [42, 127, 158]], [0.35, [87, 196, 184]], [0.7, [255, 209, 102]], [1, [255, 107, 74]]];
  function ramp(t) {
    t = Math.max(0, Math.min(1, t));
    for (let k = 1; k < RAMP.length; k++) {
      if (t <= RAMP[k][0]) {
        const [a, ca] = RAMP[k - 1], [b, cb] = RAMP[k], u = (t - a) / (b - a);
        return ca.map((c, j) => Math.round(c + (cb[j] - c) * u));
      }
    }
    return RAMP[RAMP.length - 1][1];
  }
  const NET = [44, 52, 64, 220], HVDC = [199, 146, 255], MIN_MW = 10, LOAD_MAX = 0.5;
  const flowAt = (h, i) => FLOWS[h * N + i];
  const widthOf = l => (l.dc ? 1.6 : l.v >= 380 ? 1.4 : 0.8);
  const flowWidth = f => 0.6 + Math.sqrt(Math.abs(f)) / 11;

  // ---- animated flow layer -------------------------------------------------
  // A PathLayer with a per-vertex distance (km) and a per-path shift (km).
  // The fragment shader draws repeating dashes that fade from head to tail.
  // The shift is integrated on the CPU every frame (shift += speed * dt), so a
  // change of speed changes how fast the dashes move, never where they are.
  // getMotion returns [speed, shift]: the sign of speed sets which end is the
  // head, and 0 hides the dashes.
  class FlowLayer extends deck.PathLayer {
    getShaders() {
      const s = super.getShaders();
      s.inject = {
        "vs:#decl": `
          attribute float instanceTimestamps;
          attribute float instanceNextTimestamps;
          attribute vec2 instanceMotions;
          varying float vDist;
          varying float vSpeed;
          varying float vShift;`,
        "vs:#main-end": `
          vDist = instanceTimestamps + (instanceNextTimestamps - instanceTimestamps) * vPathPosition.y / vPathLength;
          vSpeed = instanceMotions.x;
          vShift = instanceMotions.y;`,
        "fs:#decl": `
          uniform float uSpacing;
          varying float vDist;
          varying float vSpeed;
          varying float vShift;`,
        "fs:#main-start": `
          if (vSpeed == 0.0) discard;`,
        "fs:DECKGL_FILTER_COLOR": `
          float ph = fract((vDist - vShift) / uSpacing);
          if (vSpeed < 0.0) ph = 1.0 - ph;
          float a = pow(ph, 2.2) * step(ph, 0.97) + step(0.97, ph) * (1.0 - (ph - 0.97) / 0.03);
          color.a *= a;`,
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
        // speed and shift share one vec2: WebGL allows only 16 vertex
        // attributes and PathLayer already uses most of them.
        instanceMotions: { size: 2, accessor: "getMotion" },
      });
    }
    draw(params) {
      params.uniforms = Object.assign({}, params.uniforms,
        { uSpacing: this.props.spacing });
      super.draw(params);
    }
  }
  FlowLayer.layerName = "FlowLayer";
  FlowLayer.defaultProps = {
    getTimestamps: { type: "accessor", value: d => d.ts },
    getMotion: { type: "accessor", value: [0, 0] },
    spacing: 70,
  };

  // ---- map --------------------------------------------------------------------
  const narrow = innerWidth < 760;
  const map = new maplibregl.Map({
    container: "map",
    style: "https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json",
    center: CAPTURE ? [-3.0, 40.0] : narrow ? [-4.2, 40.0] : [-2.6, 41.4],
    zoom: CAPTURE ? 4.85 : narrow ? 4.6 : 5.35,
    attributionControl: false, dragRotate: false, pitchWithRotate: false,
    preserveDrawingBuffer: CAPTURE,
  });
  const overlay = new deck.MapboxOverlay({ interleaved: false, layers: [] });
  map.addControl(overlay);

  let hour = Math.max(0, Math.min(H - 1, +(params.get("h") ?? 0)));
  let fixedTime = params.has("t") ? +params.get("t") : null;

  // Flow at a fractional hour: linear between the hourly values, so speeds,
  // widths and colours ease instead of snapping at each step.
  const flowF = (hf, i) => {
    const h0 = Math.floor(hf), a = hf - h0;
    const f0 = flowAt(h0, i);
    return a > 0 && h0 + 1 < H ? f0 + (flowAt(h0 + 1, i) - f0) * a : f0;
  };
  const SPACING = 70;
  const speedOf = f => (Math.abs(f) < MIN_MW ? 0 : Math.sign(f) * (10 + 2.4 * Math.sqrt(Math.abs(f))));
  const shift = new Float64Array(N);
  let lastT = null, tick = 0;
  function advance(hf, t) {
    const dt = lastT == null ? 0 : Math.max(0, Math.min(0.25, t - lastT));
    lastT = t;
    if (dt > 0) {
      for (let i = 0; i < N; i++) {
        const s = shift[i] + speedOf(flowF(hf, i)) * dt;
        shift[i] = s - Math.floor(s / SPACING) * SPACING;
      }
    }
    tick++;
  }

  let drawHour = hour;
  function layers(t) {
    const h = drawHour;
    const hk = Math.round(h * 100);
    advance(h, t);
    return [
      new deck.PathLayer({
        id: "base", data: lines, getPath: d => d.path, widthUnits: "pixels",
        getWidth: widthOf, capRounded: true, jointRounded: true,
        getColor: d => (d.dc ? [...HVDC, 120] : NET),
      }),
      new FlowLayer({
        id: "flow", data: lines, getPath: d => d.path, widthUnits: "pixels",
        getWidth: d => flowWidth(flowF(h, d.i)), capRounded: true, jointRounded: true,
        getColor: d => {
          const f = Math.abs(flowF(h, d.i));
          const base = d.dc ? HVDC : ramp(f / d.cap / LOAD_MAX);
          return [...base, Math.round(255 * Math.min(1, Math.pow(f / 200, 0.6)))];
        },
        getMotion: d => [speedOf(flowF(h, d.i)), shift[d.i]],
        spacing: SPACING,
        updateTriggers: { getColor: hk, getWidth: hk, getMotion: tick },
      }),
    ];
  }

  // ---- panel, chart, notes -------------------------------------------------------
  const $ = id => document.getElementById(id);
  const fmtDate = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Madrid", weekday: "short", day: "numeric", month: "short" });
  const fmtTime = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Madrid", hour: "2-digit", minute: "2-digit", hour12: false });
  const gw = v => (Math.abs(v) >= 1000 ? (v / 1000).toFixed(1) + " GW" : Math.round(v) + " MW");

  const NOTES = [
    [0, "A normal spring week. By day Spain runs largely on solar and wind and exports to France."],
    [EVENT_H, "At 12:33 the grids of Spain and Portugal collapse within seconds. This hour's average still includes the last half hour of normal operation."],
    [EVENT_H + 1, "Spanish demand falls to about 500 MW. Restart begins from hydro plants and from the lines to France and Morocco."],
    [EVENT_H + 5, "France supplies Spain through the Pyrenees, up to 2,000 MW. Portugal restarts largely on its own: its link to Spain stays near zero until the next morning."],
    [EVENT_H + 12, "By midnight Spanish demand is back to 14.6 GW and Portugal's to 4.4 GW."],
    [EVENT_H + 19, "In the 07:00 hour on 29 April Spanish demand passes 20 GW again."],
    [142, "From 1 May Spain's exports to France are back to their usual level."],
  ];
  function noteFor(h) {
    let n = "";
    for (const [h0, txt] of NOTES) if (h >= h0) n = txt;
    return n;
  }

  const svg = $("chart");
  function drawChart() {
    const W = svg.getBoundingClientRect().width || 800;
    const Hh = svg.getBoundingClientRect().height || 72, pad = 14;
    svg.setAttribute("viewBox", `0 0 ${W} ${Hh}`);
    const x = h => (h / (H - 1)) * W;
    const maxv = 38000;
    const short = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Madrid", day: "numeric", month: "short" });
    const y = v => Hh - pad - (v / maxv) * (Hh - pad - 4);
    const line = arr => arr.map((v, h) => `${h ? "L" : "M"}${x(h).toFixed(1)},${y(v).toFixed(1)}`).join("");
    let ticks = "";
    for (let d = 0; d <= 8; d++) {
      const h = d * 24 - 2; // midnight CEST
      if (h < 0 || h >= H) continue;
      const label = (W < 700 ? short : fmtDate).format(new Date(T0 + (h + 1) * 3600e3));
      ticks += `<line x1="${x(h)}" x2="${x(h)}" y1="4" y2="${Hh - pad}" stroke="#262c36"/>` +
        `<text x="${x(h) + 3}" y="${Hh - 3}">${label}</text>`;
    }
    svg.innerHTML = ticks +
      `<path d="${line(series.load_ES)} L${W},${y(0)} L0,${y(0)}Z" fill="rgba(255,200,87,.18)" stroke="#ffc857" stroke-width="1.2"/>` +
      `<path d="${line(series.load_PT)}" fill="none" stroke="#5fd3c6" stroke-width="1.2"/>` +
      `<line x1="${x(EVENT_H + 0.55)}" x2="${x(EVENT_H + 0.55)}" y1="2" y2="${Hh - pad}" stroke="#ff6b4a" stroke-dasharray="2 2"/>` +
      `<text x="${x(EVENT_H + 0.55) + 4}" y="12" style="fill:#ff6b4a">12:33</text>` +
      `<text x="${W - 150}" y="12" style="fill:#ffc857">Spain demand</text><text x="${W - 62}" y="12" style="fill:#5fd3c6">Portugal</text>` +
      `<line id="cursor" y1="2" y2="${Hh - pad}" stroke="#e8ebf0" stroke-width="1.5"/>`;
    moveCursor();
    function hFromEvent(ev) {
      const r = svg.getBoundingClientRect();
      return Math.round(((ev.clientX - r.left) / r.width) * (H - 1));
    }
    svg.onpointerdown = ev => { setHour(hFromEvent(ev)); svg.setPointerCapture(ev.pointerId); };
    svg.onpointermove = ev => { if (ev.buttons) setHour(hFromEvent(ev)); };
  }
  function moveCursor() {
    const c = document.getElementById("cursor");
    if (!c) return;
    const W = svg.getBoundingClientRect().width || 800, X = (hour / (H - 1)) * W;
    c.setAttribute("x1", X); c.setAttribute("x2", X);
  }

  function border(key, v, other) {
    $("l-" + key).textContent = v >= 0 ? `Spain → ${other}` : `${other} → Spain`;
    $("s-" + key).textContent = gw(Math.abs(v));
  }

  // h may be fractional (eased playback, video frames): the map draws the
  // interpolated flows, the panel shows the hour it is in.
  function setHour(h) {
    drawHour = Math.max(0, Math.min(H - 1, h));
    hour = Math.floor(drawHour);
    const t = new Date(T0 + hour * 3600e3);
    $("date").textContent = fmtDate.format(t);
    $("time").textContent = fmtTime.format(t);
    $("note").textContent = noteFor(hour);
    $("s-es").textContent = gw(series.load_ES[hour]);
    $("s-pt").textContent = gw(series.load_PT[hour]);
    border("fr", series.exp_ES_FR[hour], "France");
    border("ptx", series.exp_ES_PT[hour], "Portugal");
    $("slider").value = hour;
    moveCursor();
    overlay.setProps({ layers: layers(currentTime()) });
  }

  // ---- animation and controls ------------------------------------------------
  let playing = false, stepMs = 600, lastStep = 0;
  const currentTime = () => (fixedTime != null ? fixedTime : performance.now() / 1000);
  function frame(now) {
    if (playing && now - lastStep > stepMs) {
      lastStep = now;
      setHour(hour >= H - 1 ? 0 : hour + 1);
    } else {
      // Ease towards the next hour over the last 40% of each step.
      if (playing && hour < H - 1) {
        const a = Math.max(0, ((now - lastStep) / stepMs - 0.6) / 0.4);
        drawHour = hour + a * a * (3 - 2 * a);
      }
      overlay.setProps({ layers: layers(currentTime()) });
    }
    requestAnimationFrame(frame);
  }
  const playBtn = $("play");
  function setPlaying(p) { playing = p; playBtn.textContent = p ? "Pause" : "Play"; }
  playBtn.onclick = () => setPlaying(!playing);
  $("jump").onclick = () => { setPlaying(false); setHour(EVENT_H - 2); };
  $("slider").oninput = e => { setPlaying(false); setHour(+e.target.value); };
  $("speed").onclick = e => {
    const b = e.target.closest("button"); if (!b) return;
    stepMs = +b.dataset.s;
    [...$("speed").children].forEach(x => x.classList.toggle("on", x === b));
  };
  $("about-btn").onclick = () => { $("about").hidden = false; };
  $("about-close").onclick = () => { $("about").hidden = true; };
  $("about").onclick = e => { if (e.target.id === "about") $("about").hidden = true; };
  addEventListener("keydown", e => {
    if (e.key === "ArrowRight") { setPlaying(false); setHour(hour + 1); }
    if (e.key === "ArrowLeft") { setPlaying(false); setHour(hour - 1); }
    if (e.key === " " && e.target === document.body) { e.preventDefault(); setPlaying(!playing); }
  });
  addEventListener("resize", drawChart);

  // Hooks for the frame renderer (scripts/render.js)
  window.__setFrame = (h, t) => { fixedTime = t; setHour(h); };

  map.on("load", () => {
    drawChart();
    setHour(hour);
    if (!CAPTURE) {
      if (!params.has("h")) setHour(EVENT_H - 30);
      requestAnimationFrame(frame);
    }
    map.once("idle", () => { window.__ready = true; });
  });
})();
