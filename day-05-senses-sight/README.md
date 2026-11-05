# Day 5 · Senses: Sight

What a walker on the GR 738, the Haute Traversée de Belledonne, can see from every point of the trail: 900 viewsheds, one about every 150 m over 131 km from Aiguebelle to Vizille, computed with `gdal_viewshed` and drawn as a video. [Watch it here](https://abenrob.github.io/30daymap2026/day-05-senses-sight/).

![End card: everything seen along the GR 738](images/gr738-end-card.png)

## Data

- **Trail:** the 11 OpenStreetMap stage relations "La Haute Traversée de Belledonne - Etape 1" to "Etape 11" (11999801, 11999979, 12000627, 12000630, 12000639, 12000790, 12000872, 12000902, 12000917, 12000916, 12000989), © OpenStreetMap contributors, ODbL. Chained in stage order: 331 ways, no gaps, 131.5 km.
- **Terrain:** IGN RGE ALTI via the Géoplateforme WMS-R (`ELEVATION.ELEVATIONGRIDCOVERAGE`, float32 GeoTIFF), 25 m, trail bounding box + 35 km (110 x 125 km), averaged to 50 m for the viewsheds. Licence Ouverte 2.0.
- **Places:** peaks, cols, refuges and ski areas from OpenStreetMap.

## Method

1. `01_gr738_prep.py` chains the stages into one line, resamples it to 900 points (one per video frame, about 150 m apart) and downloads the terrain.
2. `02_gr738_viewsheds.py` runs `gdal_viewshed -oz 1.7 -tz 0 -cc 0.85714` at every point, with no maximum distance: can an eye 1.7 m above the trail see the ground itself, with Earth curvature and standard refraction.
3. `03_gr738_frames.py` draws each frame (dark hillshade, ground in sight in amber, ground already seen as a faint tint, trail, numbers, elevation profile) and encodes the video. At five places the walker pauses 1.2 s and a label fades in; the Chamrousse ski area is shown while the walker is inside it. The end card shows everything seen, with the five places numbered.

A label's number is the ground in sight from the trail point nearest the place. The exception is the Grand Chat, where the pause is on the summit ridge 220 m before the point, where the route's widest view is.

## Results

| | |
| --- | --- |
| Ground in sight, median | 43.7 km² |
| Median above 2,000 m / below 1,500 m | 35.8 / 34.2 km² (height barely predicts the view) |
| Seen at least once | 2,225 km² (of 13,725 km² loaded) |
| Farthest visible ground | up to 93 km |

| Place | km | Altitude | Ground in sight |
| --- | --- | --- | --- |
| Grand Chat (summit ridge) | 23.1 | 1,992 m | 552 km², the widest on the route |
| Refuge des 7 Laux | 78.8 | 2,135 m | 13 km² |
| Col de la Vache, highest point | 83.1 | 2,556 m | 145 km² |
| Refuge de La Pra | 105.7 | 2,105 m | 2 km² |
| Chamrousse ski area, best trail point | 115.8 | 1,669 m | 311 km² |

Limits: bare earth, so forests and buildings do not block the view. Terrain is loaded to at least 35 km around the trail; about 2% of the ground seen touches its edge, so totals are slightly low. The observer stands on the 50 m cell holding the trail point. "In sight" means the ground itself, not summits or buildings standing above it.

## Recreate it

Requirements: Python 3.10+ with numpy, rasterio, pyproj, shapely, pillow and matplotlib; the GDAL command-line tools (`gdal_viewshed`); ffmpeg (or `pip install imageio-ffmpeg`).

Run everything from the workspace root (the folder holding `site/` and `work/`).

1. Save these four Overpass queries (https://overpass-api.de/api/interpreter) as JSON in `work/data/day-05-sight/raw/`:

   `gr738.json` (the trail)
   ```
   [out:json][timeout:170];rel(id:11999801,11999979,12000627,12000630,12000639,12000790,12000872,12000902,12000917,12000916,12000989);out body;way(r);out geom;
   ```
   `gr738_pois.json` (peaks, cols, viewpoints)
   ```
   [out:json];(node["natural"~"^(peak|saddle)$"](45.05,5.75,45.56,6.33);node["mountain_pass"="yes"](45.05,5.75,45.56,6.33);node["tourism"~"^(alpine_hut|wilderness_hut|viewpoint)$"](45.05,5.75,45.56,6.33);node["natural"="water"]["water"="lake"]["name"](45.05,5.75,45.56,6.33););out body;
   ```
   `gr738_huts.json` (refuges)
   ```
   [out:json];nwr["tourism"~"^(alpine_hut|wilderness_hut)$"](45.05,5.75,45.56,6.33);out center tags;
   ```
   `gr738_ski_geom.json` (ski areas)
   ```
   [out:json];nwr["landuse"="winter_sports"](45.0,5.7,45.6,6.4);out geom;
   ```

2. Build the trail and terrain, run the viewsheds, draw the video:

   ```
   python3 site/day-05-senses-sight/scripts/01_gr738_prep.py          # about 2 min (terrain download)
   python3 site/day-05-senses-sight/scripts/02_gr738_viewsheds.py     # about 4 min; --gdal PATH if gdal_viewshed is not on PATH
   python3 site/day-05-senses-sight/scripts/03_gr738_frames.py --layout landscape   # 16:9, about 4 min
   ```

   `03_gr738_frames.py` without `--layout` makes the 4:5 version. `--still STEP` renders a single frame to check by eye.

3. Copy the results next to this README:

   ```
   cp work/data/day-05-sight/renders/day-05-gr738-16x9.mp4 site/day-05-senses-sight/images/day-05-gr738.mp4
   cp work/data/day-05-sight/renders/gr738_final_16x9.png site/day-05-senses-sight/images/gr738-end-card.png
   ```
