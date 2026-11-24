# Day 24 · Network: 40 minutes on Berlin transit

Every street you can reach within 40 minutes of public transit from the World
Clock on Alexanderplatz (Tuesday, 08:00 departure), growing outward along each
street at the moment you could first stand on it. Two networks show at once:
the street network spreads at walking pace, and the rail network drops you at
stations where new islands of streets start growing.

deck.gl 8.9 on a CARTO Dark Matter basemap (MapLibre), pitched view.

## Files

```
index.html, style.css     the page
js/main.js                wiring: map, loop clock, controls, frame grabbing
js/config.js              every setting, each overridable from the URL
js/glow-path-layer.js     PathLayer that grows along its length, glow + colour
js/camera.js              camera path keyed to travel time
js/intro.js               the drop: streak, ring, origin dot
js/data.js                loads and decodes graph/berlin-transit.json
graph/berlin-transit.json the network, built by scripts/02
scripts/01_fetch_geojson.mjs   one Targomo request -> GeoJSON (work folder)
scripts/02_build_paths.mjs     GeoJSON -> directed, timed, packed paths
scripts/03_render_video.py     frame-by-frame MP4 and preview still
```

## Rebuilding the data

```
cd site/day-24-network
node scripts/01_fetch_geojson.mjs    # needs TGM_KEY in .env (gitignored)
node scripts/02_build_paths.mjs
```

`01` calls the Targomo Multigraph API once (transit, edge domain, routing
union, GeoJSON) and saves the response to `work/day-24-network/`. `02` packs it
for the page. Both take `D24_*` environment overrides, listed at the top of
each script (drop point, departure, limit, file names).

### Why 40 minutes

The API returns every street up to `maxEdgeWeight` 2400 s: 559,852 segments
from Alexanderplatz. From 2410 s it returns only the main road classes (about
140k), with identical times on the segments it keeps. A 60-minute request
loses the side streets you walk first, and the opening looks like islands
appearing out of nowhere.

### Direction along each segment

Targomo gives each segment one travel time. `02` gives every node the earliest
time of the segments touching it, then runs each segment from its earlier end
to its later end. Segments whose ends share a time take walking pace. One
straight walk-in line joins the drop point to the first street (31 m, 16 s),
since the drop point itself sits off the street graph.

## Look

- Colour: the Velographs "polar" ramp, d3
  `interpolateRgbBasis(["#8700A7", "#25A39D", "#FDE725"])`, reproduced in the
  shader, with travel time 0-40 min mapped to 0-1.
- Lines: a bright core and a Gaussian halo; line reached in the last few
  seconds runs whiter. Width and halo ease from 8 px close up to 3.5 px at the
  wide view, so dense side streets stay separate. Normal blending
  (`?blend=add` for an additive bloom).
- Camera: close on the drop point, drifting south toward the tip of the
  fastest southbound line until minute 17, a broad zoom out to minute 30, then
  a hold. One cubic Hermite spline in travel time, so it glides.

URL options are listed at the top of `js/config.js`. Useful ones: `?t=20`
(freeze at minute 20), `?capture` (hide controls, for recording), `?free`
(no camera choreography). The slider under the clock scrubs to any minute.

## Video

Serve `site/` on port 8765, then:

```
python3 scripts/03_render_video.py video out.mp4
python3 scripts/03_render_video.py still images/preview.png 33
```
