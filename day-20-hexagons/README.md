# Day 20 · Hexagons: why France is « l'Hexagone »

A five-slide carousel (in French) on the nickname: the textbook hexagon has six sides because France's border has six distinct frontiers, three seas and three land borders. It compares that hexagon with the best-fitting one and with the smallest hexagon that contains the whole mainland.

No live page.

## Method

- **Outline.** Natural Earth 1:110m Admin 0 Countries (the `naturalearth_lowres` copy bundled with geopandas < 1.0). Mainland France only: the largest polygon, holes filled, so no Corsica. Each country is projected to a Lambert azimuthal equal-area centred on its own centroid and scaled to unit area, so every score is scale-free.
- **Fit.** IoU (intersection over union) between the outline and a polygon. Coverage = share of France inside the polygon; spill = share of the polygon outside France.
- **Textbook hexagon.** Corners at Pointe Saint-Mathieu, Dunkerque, Lauterbourg, Menton, Cerbère and Hendaye.
- **Best-fitting hexagon.** Convex 6-gon with its corners on the border (each corner slides along the outline), seeded from a greedily thinned convex hull and refined point by point (`anchored.py`).
- **Smallest enclosing hexagon.** Convex 6-gon of minimum area containing the outline's convex hull (Powell then Nelder-Mead from nine seeds, `story.py`).
- **Coast vs land.** A border segment is land when another Natural Earth country lies within 0.03°. Side purity = share of the border between two corners that is a single type.

| | Textbook hexagon | Best-fitting hexagon |
| --- | --- | --- |
| IoU | 0.784 | 0.863 |
| France inside | 96.8% | 91.5% |
| Polygon outside France | 19.5% | 6.2% |
| Side purity (%) | 100, 100, 100, 100, 100, 100 | 90, 79, 100, 94, 94, 100 |

The smallest hexagon that contains the whole mainland has 1.089 times the textbook hexagon's area. Going round the border, it switches between coast and land exactly 4 times.

## World index (side work)

`hexagonity.py`, `convex.py`, `anchored.py` and `report.py` score all 176 Natural Earth countries: regular n-gon fits, free and convex k-gon sweeps (k = 3 to 12), and corner sweeps with points on the border. Under the convex, border-pinned rule, 6 is the smallest number of points within 1% of the best convex fit for France, and for 55 of the 155 countries with outlines detailed enough to test. `ranking.csv` has the per-country results.

## Limitations

- 1:110m is coarse: the six towns sit 3 to 17 km from the generalised outline, and coast vs land is only as good as how well neighbouring outlines line up.
- The fits are local searches; they match each other and repeated runs, but they are not proven optima.

## Sources

| What | Source |
| --- | --- |
| Country outlines | [Natural Earth](https://www.naturalearthdata.com), 1:110m Admin 0 Countries, public domain |

## Layout

```
images/01.png … 05.png      the carousel (1080 x 1350)
images/preview.png          card and social preview (1600 x 900)
ranking.csv                 world results
scripts/hexagonity.py       regular n-gon fits + free k-gon sweep -> world.json (about 30 min on 2 cores)
scripts/convex.py           convex k-gon sweep (corners anywhere)
scripts/convex_plain.py     the same sweep scored with plain IoU
scripts/anchored.py         convex k-gons with corners on the border
scripts/report.py           ranking.csv and leaderboards
scripts/story.py            France numbers and geometry -> story.json
scripts/design.py           shared colours and helpers
scripts/carousel.py         the five slides and the preview
```

Run order: `hexagonity.py data/naturalearth_lowres.shp --out world.json`, `convex.py world.json`, `anchored.py world.json`, `report.py world.json`, `story.py`, `carousel.py`. Data (world.json, Natural Earth shapefile) lives in `work/day-20-hexagons/data`.
