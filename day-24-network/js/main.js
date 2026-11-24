// Day 24 · Network: 40 minutes on Berlin public transit from Alexanderplatz.
//
// Every street reachable within 40 minutes lights up at the moment you could
// first stand on it, growing outward along its length. The data is a Targomo
// multigraph fetched once by scripts/01 and packed by scripts/02.
//
// The page runs one loop: the drop (introMs), the travel-time run (runMs,
// 0..maxTime of travel), then a hold (holdMs). Everything visible, including
// the camera, is a function of the position in that loop.

import { CONFIG as cfg, BASEMAP } from "./config.js";
import { GlowPathLayer, BLEND } from "./glow-path-layer.js";
import { introLayers } from "./intro.js";
import { createCamera } from "./camera.js";
import { loadGraph } from "./data.js";

const LOOP_MS = cfg.introMs + cfg.runMs + cfg.holdMs;
const lerp = (a, b, k) => a + (b - a) * k;
const $ = id => document.getElementById(id);

if (cfg.capture) document.body.classList.add("capture");

// ---- map ----------------------------------------------------------------------

const map = new maplibregl.Map({
  container: "map",
  style: BASEMAP,
  center: [13.4132, 52.5219], zoom: 10, pitch: cfg.pitch, bearing: cfg.bearing, maxPitch: 75,
  attributionControl: false,
  preserveDrawingBuffer: cfg.capture,   // so screenshots of the canvas work
});
const overlay = new deck.MapboxOverlay({ interleaved: false, layers: [] });
map.addControl(overlay);

// ---- state ----------------------------------------------------------------------

let graph = null;            // from loadGraph()
let camera = null;           // from createCamera(), once the map has loaded
let wideZoom = cfg.zoomFollow;
let loopMs = 0;              // position in the loop
let playing = cfg.freezeSec == null;
let lastFrame = null;
let scrubbing = false;
let userCamera = cfg.free;   // true once the reader drags or zooms

// Loop position <-> travel time (seconds; -1 during the drop).
const simAt = ms => (ms < cfg.introMs ? -1
  : Math.min(graph.maxTime, ((ms - cfg.introMs) / cfg.runMs) * graph.maxTime));
const msAt = sec => cfg.introMs + Math.min(1, sec / graph.maxTime) * cfg.runMs;

// 0 at the wide view's zoom, 1 at the landing zoom (smoothstep between).
// Lines thin out and the halo softens as the camera pulls back, so dense side
// streets stay separate at the wide view.
function closeness() {
  const x = Math.max(0, Math.min(1, (map.getZoom() - wideZoom) / (cfg.zoomClose - wideZoom)));
  return x * x * (3 - 2 * x);
}

// ---- drawing ----------------------------------------------------------------------

function networkLayer(sim) {
  const k = closeness();
  return new GlowPathLayer({
    id: "network", data: graph.paths,
    getPath: d => d.path, getTimestamps: d => d.ts,
    time: sim, maxTime: graph.maxTime, spark: cfg.sparkSec,
    halo: lerp(cfg.haloFar, cfg.haloNear, k),
    getWidth: 1, widthScale: lerp(cfg.lineFar, cfg.lineNear, k), widthUnits: "pixels", widthMinPixels: 1,
    jointRounded: false, capRounded: false,
    parameters: cfg.additive ? BLEND.ADDITIVE : BLEND.OVER, pickable: false,
  });
}

function draw() {
  const sim = simAt(loopMs);
  // Camera first, so the zoom-dependent line width matches this frame.
  if (camera && !userCamera) map.jumpTo(camera.at(sim, loopMs, LOOP_MS));
  overlay.setProps({ layers: [
    networkLayer(sim),
    ...introLayers(loopMs, cfg.introMs, graph.origin, BLEND.ADDITIVE),
  ] });
  updateClock(Math.max(0, sim));
}

function frame(now) {
  if (lastFrame != null && playing) loopMs = (loopMs + (now - lastFrame)) % LOOP_MS;
  lastFrame = now;
  draw();
  requestAnimationFrame(frame);
}

// ---- clock and controls ----------------------------------------------------------

const $play = $("play"), $scrub = $("scrub");

function updateClock(sec) {
  $("min").textContent = Math.floor(sec / 60);
  $("ramp-head").style.left = `${(sec / graph.maxTime) * 100}%`;
  if (!scrubbing) $scrub.value = (sec / 60).toFixed(1);
}

function setPlaying(value) {
  playing = value;
  $play.textContent = value ? "Pause" : "Play";
}

function restart() {
  loopMs = 0;
  userCamera = cfg.free;   // hand the camera back
  setPlaying(true);
}

function bindControls() {
  $play.onclick = () => setPlaying(!playing);
  $("restart").onclick = restart;
  addEventListener("keydown", e => {
    if (e.code === "Space") { e.preventDefault(); setPlaying(!playing); }
    if (e.key === "r") restart();
  });
  // Dragging the slider pauses and jumps to that minute of travel.
  $scrub.max = graph.maxTime / 60;
  $scrub.addEventListener("input", () => {
    scrubbing = true;
    setPlaying(false);
    loopMs = msAt(+$scrub.value * 60);
  });
  $scrub.addEventListener("change", () => { scrubbing = false; });
  // A drag, scroll or pinch by the reader hands them the camera.
  map.on("movestart", e => { if (e.originalEvent) userCamera = true; });
}

// ---- frame grabbing (?render) ------------------------------------------------------
// scripts/03_render_video.py calls __renderFrame(ms) for each frame and takes
// the screenshot once the basemap tiles have settled.

window.__loop = LOOP_MS;
window.__renderFrame = ms => new Promise(resolve => {
  loopMs = ms;
  draw();
  const done = () => requestAnimationFrame(() => requestAnimationFrame(resolve));
  if (map.loaded() && map.areTilesLoaded()) { setTimeout(done, 0); return; }
  let fired = false;
  const once = () => { if (!fired) { fired = true; done(); } };
  map.once("idle", once);
  setTimeout(once, 8000);   // never wait forever on a tile
});

// ---- start ------------------------------------------------------------------------

// The wide view: fit the network, nudge in, centre halfway between the drop
// point and the network's middle so the origin stays in frame.
function fitWideView() {
  const [x0, y0, x1, y1] = graph.view;
  map.fitBounds([[x0, y0], [x1, y1]], { padding: 30, animate: false, pitch: 0, bearing: 0 });
  const [ox, oy] = graph.origin;
  return {
    center: [(ox + (x0 + x1) / 2) / 2, (oy + (y0 + y1) / 2) / 2],
    zoom: map.getZoom() + cfg.zoomPad,
  };
}

async function start() {
  try {
    graph = await loadGraph(cfg.file);
  } catch (err) {
    $("loading").textContent = "No graph yet: run scripts/01_fetch_geojson.mjs then 02_build_paths.mjs";
    console.error(err);
    return;
  }
  if (graph.departure) $("dek").textContent = `From Alexanderplatz, ${graph.departure}`;
  if (cfg.freezeSec != null) loopMs = msAt(cfg.freezeSec);

  const onMapReady = () => {
    const wide = fitWideView();
    wideZoom = wide.zoom;
    camera = createCamera(cfg, graph, wide);
    map.jumpTo(camera.at(cfg.freezeSec ?? -1, loopMs, LOOP_MS));
    bindControls();
  };
  map.loaded() ? onMapReady() : map.once("load", onMapReady);

  $("loading").remove();
  if (!cfg.render) requestAnimationFrame(frame);
}

start();
