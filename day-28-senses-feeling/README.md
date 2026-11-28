# Day 28 · Senses: Feeling: where Grenoble cyclists are scared, and where it's getting better

A 50-second animation (1080 x 1350, in French). Eight comments left by cyclists in the FUB's Baromètre des villes cyclables 2025 are typed out, stamped with the feeling they express, and dropped onto a 3D relief of the Grenoble basin. Then the rest of the 13,510 points rain down, and the result resolves into H3 hexagons coloured by a bivariate scheme: whether people there were mostly negative, split or mostly positive (hue), and how many of them said so (strength).

[Video](https://abenrob.github.io/30daymap2026/day-28-senses-feeling/) · the same scene runs live in the browser at [web/](web/).

## Data

- **FUB Baromètre vélo 2025, Grenoble-Alpes-Métropole (EPCI 200040715)**, Open Database Licence. Two map layers from the survey: `points-rouges` (9,769 "points to improve as a priority") and `points-verts` (3,741 "improvements noticed in the last 2 years"). 8,359 of the 13,510 points carry a free-text comment. The bike-parking layer is not used.
- **Relief:** IGN RGE ALTI (`ELEVATION.ELEVATIONGRIDCOVERAGE.HIGHRES`) from the Géoplateforme WMS-R, 40 m, Lambert-93 (Licence Ouverte 2.0).
- **Base map:** main roads, rivers and lakes from OpenStreetMap via Overpass (© OpenStreetMap contributors, ODbL).

## Method

1. **One pool, layer as the prior.** Red and green points are merged. A point's starting valence is its layer: red = negative, green = positive.
2. **Read every comment.** The 8,359 comments were read by Claude sub-agents in 10 batches of about 836, each comment given one feeling (PEUR, COLÈRE, AGACEMENT, INQUIÉTUDE, LASSITUDE, INCOMPRÉHENSION, CONSTAT, SOUHAIT, SOULAGEMENT, SATISFACTION, JOIE, GRATITUDE) and a valence (negative, positive or mixed). The text overrides the layer when it says something different. Points without a comment keep their layer. Instructions: `scripts/classify_instructions.md`.
3. **Hexagons.** H3 resolution 9 (about 400 m across). Hexagons with fewer than 3 points are left blank (766 of 1,261 are coloured; they hold 95% of the points).
   - **Lean** = (positive + ½ mixed) / total: under 35% "surtout négatif", 35 to 65% "partagé", over 65% "surtout positif".
   - **Volume**: 3 to 5, 6 to 14, 15 or more points.
   - Colours: negative `#e04e2a`, mixed `#a2479b`, positive `#2f6fd0` (checked for colour-vision deficiency against the base map), mixed toward the paper colour at 36%, 66% and 100% for the three volume steps.
4. **Animation.** Three.js scene: a 100 m terrain mesh (×1.25 vertical) draped with a baked hillshade + OSM texture, camera south of the city looking north. Points are instanced discs that fall and splat; quotes and stamps are HTML over the canvas. Frames are rendered deterministically (`window.renderAt(t)`) in headless Chrome with Puppeteer and encoded with ffmpeg.

## Numbers

| | Points |
| --- | ---: |
| All points | 13,510 |
| With a comment | 8,359 |
| Final valence: negative / mixed / positive | 9,784 / 177 / 3,549 |
| Text disagrees with the layer | 238 |
| Green "improved" points that read as negative or mixed | 193 of 1,608 commented (12%) |
| Red "to improve" points that read as positive or mixed | 45 of 6,751 commented (0.7%) |

Feelings across the 8,359 comments: CONSTAT (a flat statement of fact) 3,906; PEUR 1,845; AGACEMENT 986; INCOMPRÉHENSION 385; SATISFACTION 312; SOUHAIT 233; COLÈRE 189; JOIE 169; INQUIÉTUDE 161; LASSITUDE 91; SOULAGEMENT 57; GRATITUDE 25.

Coloured hexagons by class (lean × volume):

| | 3–5 pts | 6–14 pts | 15+ pts |
| --- | ---: | ---: | ---: |
| Surtout négatif | 229 | 208 | 135 |
| Partagé | 23 | 33 | 38 |
| Surtout positif | 36 | 43 | 21 |

The most positive busy hexagon is in Fontaine (71 points, 97% positive), where the comments describe the new two-way cycle track and Chronovélo on avenue Ambroise Croizat.

## Scripts

| Script | What it does |
| --- | --- |
| `01_pool.py` | Merges the red and green layers, writes `pool.csv` and the 10 classification batches |
| `classify_instructions.md` | The instructions each sub-agent followed |
| `02_dem.py` | Downloads the IGN elevation for the basin (Lambert-93, 40 m) |
| `fetch_osm.txt` | Overpass query for roads, rivers and lakes |
| `03_basemap.py` | Bakes the hillshade + OSM texture |
| `04_merge.py` | Joins the classifications back to the points, flags points where text and layer disagree |
| `05_animdata.py` | Terrain heights, drop timing, opening quotes, H3 hexagons and classes → `anim.json` |
| `web/index.html` | The Three.js scene (live playback, or `?capture` for frame-by-frame rendering) |
| `capture.mjs` | Puppeteer frame capture: `node capture.mjs <outdir> 30 0 -1` |

Encode: `ffmpeg -framerate 30 -i frames/%05d.png -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p day-28-feeling.mp4`

## Limitations

- The survey is a self-selected sample of people who cycle or want to. A red point means someone wanted it fixed, not that it is objectively worse than an unmarked street.
- Volume partly tracks traffic: busy streets collect more points of every kind. That is why the lean axis is a share and not a count.
- The feeling labels are one model's reading of short, often ironic texts. A spot check of 25 random comments and 15 of the 238 disagreements looked right, but borderline cases (PEUR vs CONSTAT for "rond-point dangereux") are a judgment call. CONSTAT is the most common label because many comments only describe the problem ("pas de piste cyclable").
- The points have no dates, so the order they fall in is random (seed 28). The opening eight were chosen by hand among comments the classifier flagged as vivid.
