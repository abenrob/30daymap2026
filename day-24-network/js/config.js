// Settings for the page. Every value can be overridden from the URL, which is
// how the stills and the video are tuned without touching the code.
//
//   Timing      ?d=30        seconds for the whole travel-time run
//               ?t=20        freeze at minute 20 (no playback)
//   Lines       ?w=8 ?glow=0.45        line px and halo strength, camera close
//               ?wfar=3.5 ?glowfar=0.25  the same once the camera is wide
//               ?blend=add   additive blending (bloom) instead of normal
//   Camera      ?pitch=52 ?bearing=-18
//               ?zclose=14.8 ?zfollow=13.1  zoom at the landing / end of follow
//               ?follow=17 ?wide=30  minutes: end of the follow, end of zoom-out
//               ?dir=180     bearing of the line the camera follows (180 = south)
//               ?lead=0.5    how far toward that line's tip the camera drifts
//               ?zoom=0.2    added to the zoom that fits the whole network
//               ?orbit=10    degrees the camera turns over one loop
//               ?free        no camera choreography
//   Output      ?capture     hide links and buttons (orbit on by default)
//               ?render      no clock; a frame grabber drives __renderFrame(ms)
//               ?file=...    load another graph file

const params = new URLSearchParams(location.search);
const num = (key, fallback) =>
  params.has(key) && params.get(key) !== "" ? +params.get(key) : fallback;

const capture = params.has("capture");

export const CONFIG = {
  file: params.get("file") || "graph/berlin-transit.json",
  capture,
  render: params.has("render"),

  // The loop, in milliseconds: the drop, the travel-time run, a hold at the end.
  introMs: 1800,
  runMs: num("d", 30) * 1000,
  holdMs: 4000,
  freezeSec: params.has("t") ? num("t", 0) * 60 : null,

  // Lines, close-up and wide; blended between by the current zoom.
  lineNear: num("w", 8),
  lineFar: num("wfar", 3.5),
  haloNear: num("glow", 0.45),
  haloFar: num("glowfar", 0.25),
  additive: params.get("blend") === "add",
  sparkSec: 45,  // how long freshly reached line stays hot

  // Camera.
  pitch: num("pitch", 52),
  bearing: num("bearing", -18),
  zoomClose: num("zclose", 14.8),
  zoomFollow: num("zfollow", 13.1),
  zoomPad: num("zoom", 0.2),
  followEndSec: num("follow", 17) * 60,
  wideEndSec: num("wide", 30) * 60,
  followBearing: num("dir", 180),
  followSector: 20,
  lead: num("lead", 0.5),
  orbit: num("orbit", capture ? 10 : 0),
  free: params.has("free"),
};

export const BASEMAP =
  "https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json";
