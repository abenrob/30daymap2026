# Day 2 · Lines: the Rhône, traced upstream from the sea

Every river segment that drains to the Rhône mouth, found by walking the network upstream with one recursive SQL query, then rendered on 3D terrain in Blender two ways.

![The whole network, lit](images/rhone-network.png)

- [`images/rhone-drips.gif`](images/rhone-drips.gif): the posted loop. Every line is lit and drips run downstream, faster on bigger rivers; lakes pass the flow across as bands. 4 s, loops without a seam.
- The drawing-in version (rendered by `07_build_scene.py`, not in the repo): every line draws from its upstream end at the same speed, timed so all the water reaches the sea together; lakes fill as a front at river speed, so the water leaves each lake exactly when the outflowing river starts.

## Data

| Layer | Source | Notes |
| --- | --- | --- |
| Rivers | HydroRIVERS v1.0, Europe (Lehner & Grill 2013, HydroSHEDS) | Reaches draining 10 km2 or more, with `NEXT_DOWN` topology |
| Basin outline | HydroBASINS v1c, level 12 | Units sharing the outlet's `MAIN_BAS` |
| Lakes | HydroLAKES v1.0 (Messager et al. 2016) | Lakes of 10 ha or more, with surface elevation |
| Sea | Natural Earth 10m ocean | Public domain |
| Terrain | Copernicus DEM GLO-30, AWS Open Data (COG) | 36 one-degree tiles, a surface model (includes canopy and buildings) |

Raw downloads and derived files live in `work/data/day-02-lines/` (outside git).

## Pipeline

Run from the workspace root, in order:

1. `scripts/01_download.sh`: HydroRIVERS, HydroBASINS, HydroLAKES, Natural Earth ocean.
2. `scripts/02_trace_rhone.py`: picks the outlet (the sea-draining reach with the largest upstream area at the delta), walks `NEXT_DOWN` upstream with a recursive SQL query in DuckDB, checks the result against HydroRIVERS' own `MAIN_RIV`, and computes our own accumulation (total channel length upstream of each reach) with a second recursion.
3. `scripts/03_download_dem.sh`: the GLO-30 tiles for the basin bbox.
4. `scripts/04_build_dem.py`: mosaics the tiles as a VRT and warps to Lambert-93 at 30 m (for shading and close-ups) and 150 m (the Blender mesh), block by block so it fits in a few GB of RAM.
5. `scripts/05_preview.py`: a 2D check on a hillshade.
6. `scripts/06_anim_data.py`: the clock and Blender inputs. A point lights up at `D_max - (network km to the sea)`, so all water reaches the sea together and every line draws at the same speed. Reaches are clipped at lake shores; inside each lake, a multi-source shortest path from every river point in it (each seeded with its own clock time) gives the time each lake pixel turns to water, stretched so the outlet fills exactly when the river leaves. Writes `work/data/day-02-lines/blender/`.
7. `scripts/07_build_scene.py`: run with `blender -b -P`. Builds `work/blender/day-02-rhone.blend`: terrain from `height.png` in Geometry Nodes (nothing heavy stored in the .blend), rivers as Curves drawn by a Trim Curve node and draped by raycast, lakes as a mesh whose shader reads `lake_time.png`. One driver on the frame number runs the clock. Eevee, 1080 x 1350, 30 fps, 480 frames (1 s still, 12 s of flow, 3 s hold), fog-glow bloom in the compositor.

8. `scripts/08_build_pulses.py`: run with `blender -b -P` after 07. Opens the drawing-in scene read-only and saves `work/blender/day-02-rhone-pulses.blend`: the clock frozen with everything on, and drips added in the river shader. Each piece gets a random phase and a speed tier by Strahler order (1x for orders 1 and 2, 2x for 3 to 5, 3x for 6 and 7); each tier moves a whole number of 20 km spacings in the 120-frame loop, so frame 121 equals frame 1. Lakes reuse their fill-time texture so bands cross them in step with the rivers. `MODE = "ants"` gives one global bead pattern tied to distance to the sea instead. Renders 120 PNG frames for ffmpeg.

Python: `duckdb>=1.4,<2` with the spatial extension, `rasterio`, `numpy`; 05 and 06 also need `geopandas`, `pyarrow`, `shapely>=2.1`, `scipy`, `pillow` and `matplotlib`. Blender 4.2 or later for 07.

## Numbers so far

| | |
| --- | --- |
| Outlet | HydroRIVERS reach 20537764, 4.806 E 43.381 N; 95,894 km2 upstream, 1,727 m3/s modelled mean discharge |
| Reaches upstream | 7,082 (trace and `MAIN_RIV` agree exactly) |
| Channel length | 26,297 km |
| Longest path to the sea | 916 km, 271 reaches deep |
| Strahler orders | 1 to 7 (3,578 first-order reaches) |
| Basin (HydroBASINS) | 96,638 km2 |
| Lakes in the basin | 411, 840 km2 in total; Geneva alone is 572 km2. 223 are crossed by a reach and fill as a front; the rest fade in when the nearest river passes |
| Animation pieces | 7,302 river pieces (reaches split at lake shores), 181,909 curve points at 150 m spacing |
| Clock | 0 to 916 network km; Geneva fills from 296 to 377 |
| Terrain | 30 m: 14,110 x 19,377 px; 150 m: 2,822 x 3,876 px; up to 4,808 m |
