# Day 24 · Network: one hour on Berlin transit

Every street reachable within 60 minutes of public transit from Alexanderplatz
(Tuesday 08:00 departure), growing outward along each line as the clock runs.
deck.gl 8.9 on a CARTO Dark Matter basemap, pitched view.

## Data (one-time fetch)

```
cd site/day-24-network
node scripts/01_fetch_geojson.mjs   # Targomo multigraph -> ../../work/day-24-network/berlin-transit-60min.geojson
node scripts/02_build_paths.mjs     # GeoJSON -> graph/berlin-transit.json (+ work/.../summary.json)
```

`01` needs `TGM_KEY` in `site/day-24-network/.env` (gitignored). It skips the
call if the GeoJSON already exists (`--force` to refetch). `D24_DATE` (YYYYMMDD)
and `D24_TIME` (seconds after midnight) override the departure.

Same request as Velographs (`multigraph`, identity layer, edge domain,
routing union, GeoJSON) with `tm: { transit: { frame: { date, time } } }`
instead of bike, `maxEdgeWeight: 3600`.

## Direction along each edge

Targomo gives one travel time `w` per edge. To grow a line along its length,
`02` gives every node the smallest `w` of the edges touching it (its arrival
time), then runs each edge from its earlier end to its later end, t0 to t1.
Edges whose two ends share a time fall back to walking speed (1.25 m/s, max
2 min). The page interpolates per-vertex times along each edge's length, and
the shader cuts each segment at the exact point the clock has reached.

## Styling

Custom PathLayer (`GlowPathLayer` in app.js): bright core plus a Gaussian
halo across the line width, colour by arrival time (Velographs dark gradient
#8700A7 → #25A39D → #FDE725), freshly reached line runs hotter and whiter,
additive blending so dense corridors bloom.

URL options: `?d=30` seconds for the hour, `?w=8` line width px, `?glow=0.45`
halo strength, `?pitch=52`, `?bearing=-18`, `?zoom=0.2` (added to the fitted
zoom), `?orbit=10` degrees of camera turn per loop, `?t=20` freeze at minute
20, `?capture` hide links and buttons (orbit on by default).

Camera, keyed to travel time: close on Alexanderplatz at the landing
(`?zclose=14.8`), then a gentle zoom out to `?zfollow=13.1` while drifting
toward the tip of the fastest line heading `?dir=180` (south; the farthest
reached point within 20 degrees of that bearing, smoothed over 3 minutes),
`?lead=0.5` of the way to it, until minute `?follow=25`; then a broad eased
zoom out to the whole area by minute `?wide=45`. Dragging or zooming hands
the camera to the reader until Restart; `?free` turns the choreography off.
