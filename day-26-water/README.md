# Day 26 · Water: the Garonne flood moving downriver, seen through the clouds

The February 2026 Garonne flood from Aiguillon to Langon, from Sentinel-1 radar read out of ESA's EOPF Sentinel Zarr. Every flooded 50 m cell is coloured by the day open water first appeared there. Aiguillon and Tonneins were first seen flooded on 12 February, Le Mas-d'Agenais to Couthures on the 13th; La Réole and Langon were imaged dry on 12 and 13 February and wet on the morning of the 17th, so the crest travelling about 50 km downriver is observed, not modelled.

Video: `images/day-26-garonne.mp4` (1080 x 1350, 4:5). Live page: `index.html`.

## Numbers

| | |
| --- | --- |
| Sentinel-1 GRD items read | 76 (57 flood window 25 Jan to 10 Mar 2026, 19 dry reference Aug to Oct 2025), 5 relative orbits |
| Grid | 50 m, Lambert-93, 2,326 x 1,929 cells (Agen to Bordeaux), from IGN RGE ALTI |
| Flooded (water on >= 2 passes) | 83 km² in the whole box, 76 km² in the frame (Aiguillon to Langon) |
| Peak single pass | 79 km² of open water (17 Feb, 06:08 UTC, orbit 8) |
| Buildings within ~50 m of flood water | 1,622 in the box (1,569 in frame): 1,103 undifferentiated, 310 residential (343 dwellings), 133 agricultural, 51 annexes |
| First seen wet (share of flooded area within 3 km) | Aiguillon 12 Feb (70 %), Tonneins 12 Feb (78 %), Le Mas-d'Agenais 13 Feb (82 %), Marmande 13 Feb (58 %), Couthures 13 Feb (63 %), La Réole 17 Feb (74 %), Langon 17 Feb (72 %) |

Nothing floods near Agen or Bordeaux in this window (the tidal Garonne below Langon barely spills), hence the frame.

## Method

1. `10_download_agen_bordeaux.py` (run on the Mac, conda env `environment.yml`): STAC search of `sentinel-1-l1-grd` on stac.core.eopf.eodc.eu; each item opened with xarray-eopf 0.3.1 in analysis mode (calibration + terrain correction onto the RGE ALTI grid, RTC off on a flat floodplain), cropped to its own footprint, VV kept as int16 dB x 100. Resumable, with retries.
2. `11_cube.py`: slices of a pass mosaicked; 3x3 boxcar in linear power; per-orbit dry reference = median of 4 autumn 2025 dates. Water = VV < -13 dB **and** at least 5 dB darker than the reference. Permanent water (dark in the reference) kept apart. Output: one array, pass x y x, with 0 dry, 1 water, 255 not observed.
3. `14_timing_ab.py`: flooded = water on >= 2 passes, >= 60 % of the passes in between, < 15 m above the nearest permanent river cell. Each cell uses its own observations (orbits cover different parts): arrival lies between its last dry pass and its first wet pass; within that window, lower ground wets first (height above the river), and drains last. **The motion between passes is interpolated; the dates in the final map are observed.**
4. `13_buildings_ab.py`, `16_buildings_first.py`: BD TOPO `batiment` for the 126 5-km tiles that hold flood water (491,667 buildings), arrival per building = earliest water within one cell of its centroid.
5. `17_rivers.py`, `18_render_v4.py`, `19_preview.py`: BD TOPO rivers as reference; frames with PIL in the Day 24 layout (IBM Plex). During the animation water is pale blue when it arrives and deepens to dark blue the longer it stays, with a dark stain once it drains; buildings turn amber when reached. The closing map colours each cell by arrival date (matplotlib plasma); ffmpeg.

## Limits

- Open water at pass times only. No depth.
- Radar misses water between buildings (walls bounce the signal back bright) and under trees: Tonneins itself reads dry. Building counts are a floor, and "within 50 m of open water" is exposure, not damage.
- The 19 Feb 17:46 UTC pass (orbit 132) is dropped: storm wind roughened the water and it shows no contrast.
- Passes are 1 to 4 days apart (none 14 to 16 Feb), so arrival dates are "first pass that saw water".

## What broke

- A fixed -18 dB threshold (the usual rule of thumb) caught under half the flood: flooded fields measured -12 to -22 dB depending on orbit and wind.
- xarray-eopf 0.3.1 needs zarr < 3, which needs xarray < 2025.10.
- Opening several products in one process collides on the reader's temp files (ContainsGroupError): one process per worker, each in its own temp dir.
- Slices that clip only a corner of the area crash the reader (IndexError in `_sample_array_at_indices`): slices under 5 % overlap are dropped.
- netCDF writes must use `engine="netcdf4"` (the scipy backend cannot compress).

## Data and licences

Copernicus Sentinel-1 data (2025-2026), ESA/Copernicus, via the EOPF Sentinel Zarr samples service. IGN RGE ALTI, BD TOPO (bâtiments, cours d'eau) via the Géoplateforme, Licence Ouverte 2.0.
