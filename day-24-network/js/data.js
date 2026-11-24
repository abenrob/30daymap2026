// Loading graph/berlin-transit.json, written by scripts/02_build_paths.mjs.
//
// File format (kept compact so the page loads quickly):
//   origin  [lng, lat] of the drop point
//   maxTime travel time the run covers, seconds
//   date, time  departure (YYYYMMDD, seconds after midnight)
//   q       coordinate scale (1e5: integers in 1e-5 degrees)
//   view    [minLng, minLat, maxLng, maxLat] the wide view fits
//   paths   one array per street segment, running from the end reached first:
//           [t0, t1, x0, y0, dx1, dy1, dx2, dy2, ...]
//           t0, t1 = travel time at the start and end (s); x0, y0 = first
//           vertex; then deltas to each next vertex.

const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

// Decode one segment into deck.gl's shape: a path of [lng, lat] and a time at
// every vertex, spread along the segment in proportion to distance.
function decodePath(row, q, coslat) {
  const [t0, t1] = row;
  let x = row[2], y = row[3];
  const path = [[x / q, y / q]];
  const along = [0];
  let length = 0;
  for (let i = 4; i < row.length; i += 2) {
    x += row[i];
    y += row[i + 1];
    length += Math.hypot(row[i] * coslat, row[i + 1]);   // planar, fine at street scale
    path.push([x / q, y / q]);
    along.push(length);
  }
  const ts = along.map(a => (length > 0 ? t0 + (t1 - t0) * (a / length) : t0));
  return { path, ts };
}

export async function loadGraph(url) {
  const doc = await (await fetch(url)).json();
  const q = doc.q || 1e5;
  const coslat = Math.cos(doc.origin[1] * Math.PI / 180);
  return {
    origin: doc.origin,
    maxTime: doc.maxTime || 2400,
    view: doc.view || doc.bbox,
    departure: describeDeparture(doc.date, doc.time),
    paths: doc.paths.map(row => decodePath(row, q, coslat)),
  };
}

// "Tuesday 24 November, 08:00 departure", or null if the file has no date.
function describeDeparture(date, seconds = 0) {
  if (!date) return null;
  const s = String(date);
  const d = new Date(+s.slice(0, 4), +s.slice(4, 6) - 1, +s.slice(6, 8));
  const hh = String(Math.floor(seconds / 3600)).padStart(2, "0");
  const mm = String(Math.floor((seconds % 3600) / 60)).padStart(2, "0");
  const month = d.toLocaleString("en", { month: "long" });
  return `${DAYS[d.getDay()]} ${d.getDate()} ${month}, ${hh}:${mm} departure`;
}
