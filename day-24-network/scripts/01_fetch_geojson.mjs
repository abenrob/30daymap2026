// Step 1: fetch the reachable street network once from the Targomo
// Multigraph API and save it as GeoJSON.
//
//   node scripts/01_fetch_geojson.mjs [--force]
//
// Writes ../../work/day-24-network/<name>-<minutes>min.geojson (not in git).
// Skips the call if that file exists, unless --force.
// Needs TGM_KEY in site/day-24-network/.env (gitignored).
//
// Env overrides:
//   D24_LAT, D24_LNG  drop point (default: the World Clock, Alexanderplatz)
//   D24_DATE          departure date, YYYYMMDD (default 20261124, a Tuesday)
//   D24_TIME          departure, seconds after midnight (default 08:00)
//   D24_MAX           travel-time limit in seconds (default 2400)
//   D24_NAME          file name stem (default berlin-transit)
//   D24_WORK          output folder
//
// Why 2400 s: up to 40 minutes the API returns every street. Above that it
// returns only the main road classes, which drops the side streets you walk
// first and makes the opening look like islands appearing from nowhere.
//
// Behind a proxy (as in Claude's shells), Node's fetch needs NODE_USE_ENV_PROXY=1.

import fs from "node:fs";
import path from "node:path";

const DAY = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const WORK = process.env.D24_WORK || path.resolve(DAY, "../../work/day-24-network");
const NAME = process.env.D24_NAME || "berlin-transit";

const ORIGIN = { lat: +(process.env.D24_LAT || 52.52190), lng: +(process.env.D24_LNG || 13.41320) };
const DATE = +(process.env.D24_DATE || 20261124);
const TIME = +(process.env.D24_TIME || 8 * 3600);
const MAX_TIME = +(process.env.D24_MAX || 2400);
const OUT = path.join(WORK, `${NAME}-${MAX_TIME / 60}min.geojson`);

// The multigraph request: one transit source; every street segment it can
// reach ("edge" domain, no aggregation into cells) with its travel time.
function requestBody() {
  return {
    sources: [{
      id: "origin", lat: ORIGIN.lat, lng: ORIGIN.lng,
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
}

function readKey() {
  const lines = fs.readFileSync(path.join(DAY, ".env"), "utf8").split(/\r?\n/);
  const line = lines.find(l => l.startsWith("TGM_KEY="));
  if (!line) throw new Error("TGM_KEY missing from site/day-24-network/.env");
  return line.slice("TGM_KEY=".length).trim();
}

// Targomo serves each region from its own endpoint.
async function regionEndpoint() {
  const url = `https://api.targomo.com/utility/endpoint?latitude=${ORIGIN.lat}&longitude=${ORIGIN.lng}`;
  return (await (await fetch(url)).json()).endpoint;
}

async function main() {
  if (fs.existsSync(OUT) && !process.argv.includes("--force")) {
    console.log(`Already have ${OUT}; use --force to fetch again.`);
    return;
  }
  const endpoint = await regionEndpoint();
  const started = Date.now();
  const res = await fetch(`https://api.targomo.com/${endpoint}/v1/multigraph?key=${readKey()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(requestBody()),
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`Targomo ${res.status}: ${text.slice(0, 500)}`);

  const json = JSON.parse(text);
  const fc = json.data?.type ? json.data : json;
  if (fc.type !== "FeatureCollection") throw new Error(`Unexpected response: ${text.slice(0, 500)}`);

  // Keep the request parameters with the data; step 2 reads them.
  fc.metadata = { origin: ORIGIN, maxTime: MAX_TIME, date: DATE, time: TIME, fetched: new Date().toISOString() };
  fs.mkdirSync(WORK, { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(fc));
  const secs = ((Date.now() - started) / 1000).toFixed(1);
  console.log(`${endpoint}: ${fc.features.length} segments, ${(text.length / 1e6).toFixed(1)} MB, ${secs} s -> ${OUT}`);
}

main().catch(err => { console.error(err.message); process.exit(1); });
