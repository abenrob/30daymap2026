// One-time fetch: Targomo multigraph (edge domain, routing union) for public
// transit from Alexanderplatz, 60 minutes, saved as raw GeoJSON.
// Usage (from site/day-24-network):  node scripts/01_fetch_geojson.mjs
// Needs TGM_KEY in ./.env (gitignored). Writes to $D24_WORK
// (default ../../work/day-24-network). Skips the call if the file exists
// unless --force is given.
import fs from "node:fs";
import path from "node:path";

const here = path.dirname(new URL(import.meta.url).pathname);
const day = path.resolve(here, "..");
const WORK = process.env.D24_WORK || path.resolve(day, "../../work/day-24-network");
const OUT = path.join(WORK, "berlin-transit-60min.geojson");

const env = Object.fromEntries(
  fs.readFileSync(path.join(day, ".env"), "utf8").split(/\r?\n/)
    .filter(l => l.includes("=") && !l.startsWith("#"))
    .map(l => [l.slice(0, l.indexOf("=")).trim(), l.slice(l.indexOf("=") + 1).trim()])
);
const KEY = env.TGM_KEY;
if (!KEY) throw new Error("TGM_KEY missing from .env");

const ORIGIN = { lat: 52.52190, lng: 13.41320 };  // Alexanderplatz
const MAX_TIME = 3600;                              // seconds
const DATE = +(process.env.D24_DATE || 20261124);   // Tuesday
const TIME = +(process.env.D24_TIME || 8 * 3600);   // 08:00 departure

if (fs.existsSync(OUT) && !process.argv.includes("--force")) {
  console.log(`Already have ${OUT}; use --force to fetch again.`);
  process.exit(0);
}
fs.mkdirSync(WORK, { recursive: true });

const ep = await (await fetch(
  `https://api.targomo.com/utility/endpoint?latitude=${ORIGIN.lat}&longitude=${ORIGIN.lng}`)).json();
console.log("endpoint:", ep.endpoint);

const body = {
  sources: [{
    id: "alex", lat: ORIGIN.lat, lng: ORIGIN.lng,
    tm: { transit: { frame: { date: DATE, time: TIME } } },
  }],
  useClientCache: false,
  edgeWeight: "time",
  maxEdgeWeight: MAX_TIME,
  multigraph: {
    layer: { type: "identity" },
    domain: { type: "edge" },
    serialization: { format: "geojson" },
    aggregation: { type: "routing_union" },
  },
};
const t = Date.now();
const res = await fetch(`https://api.targomo.com/${ep.endpoint}/v1/multigraph?key=${KEY}`, {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});
const text = await res.text();
if (!res.ok) { console.error(res.status, text.slice(0, 2000)); process.exit(1); }
const json = JSON.parse(text);
const fc = json.data && json.data.type ? json.data : json;
if (fc.type !== "FeatureCollection") {
  console.error("Unexpected response:", text.slice(0, 2000)); process.exit(1);
}
fc.metadata = { origin: ORIGIN, maxTime: MAX_TIME, date: DATE, time: TIME, fetched: new Date().toISOString() };
fs.writeFileSync(OUT, JSON.stringify(fc));
console.log(`${fc.features.length} features, ${(text.length / 1e6).toFixed(1)} MB, ${((Date.now() - t) / 1000).toFixed(1)} s -> ${OUT}`);
