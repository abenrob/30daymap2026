# Day 27 · New tool: the Aiguille Dibona, from IGN orthophoto to ink drawing

Built 27 Nov. A 12 s animation (288 frames, 24 fps, 1080 x 1350) rendered in Blender 5.3: the IGN orthophoto of the Aiguille Dibona (Écrins) seen from straight above with elevation contours, turning into a flat-colour comic-book drawing as the relief rises, ending on a 135 mm view from the floor of the Vallon du Soreiller with the title "AIGUILLE DIBONA / ALTITUDE 3 131". An homage to the drawings of Jean-Marc Rochette in *Ailefroide, Altitude 3 954* (Olivier Bocquet and Jean-Marc Rochette, Casterman).

The new tool is Blender used as a drawing machine: Grease Pencil Line Art for the ink and an EEVEE "toon" shader for the colour. Earlier days this month only used Blender for quick 3D renders.

## Pipeline

| Script | What it does |
| --- | --- |
| `scripts/01_fetch_rasters.py` | Downloads the inputs from the IGN Géoplateforme WMS-R (LiDAR HD ground model at 2 m for the scene and 1 m around the needle, orthophoto at 0.5 m) and the Antonio font, pinned to weight 700 |
| `scripts/02_still.py` | Builds the scene and renders one still: terrain meshes, flat-colour shader, Line Art ink, sun, sky, valley camera |
| `scripts/03_animation.py` | Runs `02_still.py`'s scene builder, then adds the orthophoto, contours, rising relief, labels, camera path and fades; renders frames or saves a packed `.blend` |
| `scripts/04_preview.py` | The 1600 x 900 site card from the opening frame and the final frame |

```
export DIBONA_DATA=/path/to/data
python3 scripts/01_fetch_rasters.py
python3 scripts/03_animation.py -- --res 1080 --samples 32 --norender --blend dibona_anim.blend
blender -b dibona_anim.blend -a                       # frames/f0001.png ... f0288.png
ffmpeg -framerate 24 -i frames/f%04d.png -c:v libx264 -crf 18 -pix_fmt yuv420p dibona.mp4
```

The Python scripts use Blender as a module (`pip install bpy`, Blender 5.3) plus numpy, scipy, rasterio and pyproj. A `.blend` saved by 5.3 needs Blender 5.3 or newer to open without losing the Grease Pencil data.

## The view

| Setting | Value |
| --- | --- |
| Summit | Aiguille Dibona, 6.24306 E 44.9629 N (BD TOPO), 3,131 m on the IGN map |
| Camera | Floor of the Vallon du Soreiller, 6.24089 E 44.94903 N, 2,230 m, eye height 1.7 m, 1.55 km south of the summit, heading 4°, 135 mm lens, aimed 120 m below the summit to leave sky for the title |
| Why there | A line-of-sight search over the DEM: from Les Étages and from the Refuge du Soreiller the summit is hidden by terrain; the valley floor 1.2 to 1.8 km south is the lowest ground that sees it |
| Sun | Azimuth 235° (south-west), elevation 30°, point source (hard shadow edges): the west face lit, the east face in shadow |

## How the drawing is made

**Terrain.** Only what the camera sees is meshed, so Line Art stays fast: a 1.5 m grid in a wedge 500 m to 2.4 km from the camera and ±8.5° wide (363k faces), an 8 m grid for the far ridges, and for the animation a 4 m square around the needle for the top-down shot. Elevation is sampled bilinearly from the 1 m LiDAR where it exists and the 2 m LiDAR elsewhere. Where meshes overlap, the coarser one is lowered so the finer one wins. Each mesh stores the real relief normals (`n0`), so slope and lighting stay right while the animation scales the terrain flat.

**Colour.** EEVEE's Shader to RGB turns Blender's lighting into one brightness value, which constant colour ramps cut into flat bands: navy shadow, mid grey and light grey on steep rock, navy, sand and pale sand on gentle ground. A slope mask (normal z < 0.62, about 52°) picks the palette, low-detail noise jitters both thresholds so the edges are ragged but crisp, vertically stretched noise paints fall-line streaks on the rock, and ridges beyond 2.3 km fade towards a pale blue-grey. The sky is a screen-space gradient from ultramarine to cerulean.

**Ink.** Grease Pencil Line Art traces the silhouettes. It runs twice, split by the sun's shadow: bold black lines on lit rock, thin pale lines inside the shadows. Noise, smooth, a tapered thickness curve, a small overshoot and simplify make the lines look hand-drawn.

**Animation.** Frames 1-62 straight down on the orthophoto with 40 m contours (200 m index contours) and the label; 62-112 the photo cross-fades into the drawing while the map is still flat, so the photo is never stretched over the steep faces; 70-140 the relief rises; 100-145 the ink fades in; 140-240 the camera swings down to the valley view; 165-200 the contours fade out; 244-264 the title fades in. The contours are painted by the terrain shader, so ridges hide the contours behind them.

## What broke

- **The first attempt, a photoreal view across Lac du Crozet (Belledonne)**, with every tree from the LiDAR canopy model and Megascans rock, still looked stitched together after hours of work. Those scripts are kept in `scripts/crozet_abandoned/`.
- **Line Art crease lines came back empty** in Blender 5.3 for this terrain at any threshold; only contour lines work. The rock detail is painted by the shader instead.
- **Several Line Art modifiers on one Grease Pencil object share one cache**: the later ones return no strokes. Each pass lives on its own object.
- **Seams between meshes drew lines.** Faces along every mesh border are tagged (`freestyle_face`) and excluded from Line Art.
- **Grease Pencil contours showed through the ridges** once the relief stood up, whatever the depth settings. The contours moved into the terrain shader.
- **A copied fading material shared its animation** with the original, so the end title appeared during the opening. Every fading material now has its own keyframed value.
- **Soft band edges** came from the sun's angular size and from high-detail noise on the thresholds; a point sun and 2-octave noise fixed them.

## Data and credits

- IGN LiDAR HD ground model (MNT), IGN orthophotos, BD TOPO (summit name and position), via the Géoplateforme, Licence Ouverte 2.0.
- Antonio by Vernon Adams, SIL Open Font License.
- Homage to *Ailefroide, Altitude 3 954*, Olivier Bocquet and Jean-Marc Rochette, Casterman.
