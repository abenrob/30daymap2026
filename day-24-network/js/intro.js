// The landing: a white streak falls onto the drop point, a ring spreads out
// when it hits, and a softly pulsing dot marks the origin from then on.
// Everything here is a function of the loop position in ms (0 .. introMs).

const LAND = 0.55;          // fraction of the intro when the streak hits
const FALL_FROM = 9000;     // metres above the ground at the start
const STREAK = 1600;        // streak length, metres

const easeIn = x => x * x * x;
const easeOut = x => 1 - Math.pow(1 - x, 3);

export function introLayers(ms, introMs, origin, blend) {
  const p = Math.min(1, ms / introMs);
  const [lng, lat] = origin;

  if (p < LAND) {
    const z = FALL_FROM * (1 - easeIn(p / LAND));
    return [new deck.LineLayer({
      id: "streak", data: [0],
      getSourcePosition: () => [lng, lat, z + STREAK],
      getTargetPosition: () => [lng, lat, z],
      getColor: [255, 255, 255, 230], getWidth: 3, widthUnits: "pixels",
      parameters: blend, updateTriggers: { getSourcePosition: z, getTargetPosition: z },
    })];
  }

  const layers = [];
  const settled = Math.min(1, (p - LAND) / (1 - LAND) * 0.9);   // 0 at impact, ~1 later

  // The ring: grows and fades over 1.4 s; gone shortly after the run starts.
  if (ms < introMs + 900) {
    const r = easeOut(Math.min(1, (ms - LAND * introMs) / 1400));
    layers.push(new deck.ScatterplotLayer({
      id: "shock", data: [0], getPosition: () => origin,
      radiusUnits: "pixels", getRadius: 6 + 90 * r, stroked: true, filled: false,
      lineWidthUnits: "pixels", getLineWidth: 2, getLineColor: [255, 255, 255, 255 * (1 - r)],
      parameters: blend, updateTriggers: { getRadius: r, getLineColor: r },
    }));
  }

  // The origin: a pulsing glow under a solid white dot.
  const pulse = 0.5 + 0.5 * Math.sin(ms / 380);
  layers.push(new deck.ScatterplotLayer({
    id: "dot-glow", data: [0], getPosition: () => origin, radiusUnits: "pixels",
    getRadius: 16 + 4 * pulse, getFillColor: [255, 255, 255, 40 + 20 * settled],
    parameters: blend, updateTriggers: { getRadius: pulse, getFillColor: settled },
  }));
  layers.push(new deck.ScatterplotLayer({
    id: "dot", data: [0], getPosition: () => origin, radiusUnits: "pixels",
    getRadius: 5, getFillColor: [255, 255, 255, 255], parameters: blend,
  }));
  return layers;
}
