# Day 13 · Interactions: Where France Commutes

Commuting as spatial interaction. Pick any French commune and the page shows both directions of its flows: where its residents go to work, and where the people who work there live. Pulses run along each arc from home to workplace. The two directions rarely mirror each other.

Page: https://abenrob.github.io/30daymap2026/day-13-interactions/

## Numbers

- 28.4 million employed residents (15 and over). 68% work outside the commune they live in.
- 986,967 origin-destination pairs, including 1,602 foreign workplaces. 494,947 people commute abroad; 473,711 of them to a commune placed on the map (Switzerland 233,080, Luxembourg 108,016, Germany 50,393, Belgium 47,268, Monaco 34,787).
- Nice: 34,599 residents work somewhere else, 10,495 of them in Monaco (30%). 49,707 of Nice's jobs are held by people who live elsewhere, led by Cagnes-sur-Mer (5,387) and Saint-Laurent-du-Var (4,791).
- Annemasse: 12,111 residents work somewhere else, 6,431 of them in Geneva (53%).
- One click reads one commune's rows: a single HTTP range request, about 50 to 100 KB out of a 10 MB file.

## Data

| What | Source | Notes |
| --- | --- | --- |
| Commuting flows | [INSEE, Mobilités professionnelles en 2022](https://www.insee.fr/fr/statistiques/8582949), Licence Ouverte | CSV with every flow (the XLSX stops at 100). Geography as of 1 January 2025. Flows under 200 are orders of magnitude only (partly survey based, collected over several years). |
| Boundaries | [Etalab, contours administratifs 2025](https://www.data.gouv.fr/datasets/contours-administratifs/), ODbL | Built from IGN Admin Express (OSM for the overseas collectivities). Includes the 45 arrondissements of Paris, Lyon and Marseille, which INSEE uses instead of the three cities. |
| Foreign workplaces | [Nominatim](https://nominatim.org/), © OpenStreetMap contributors, ODbL | 1,604 places named by INSEE in Switzerland, Germany, Belgium, Luxembourg and Monaco. |

## Method

1. **Boundaries** (`01_boundaries.py`). Etalab's 50 m communes, the three whole-city polygons dropped (they overlap their arrondissements), simplified with mapshaper (weighted Visvalingam, 10%, shared borders kept), made valid, Hilbert-sorted, written as GeoParquet with GeoArrow-native geometry. Every French code in the flows matches a polygon. 35,011 features, 501k vertices, 2.9 MB. Parquet's default dictionary encoding inflated the coordinates to 6.1 MB, so it is off; a bbox column would add 0.8 MB and is left out.
2. **Foreign workplaces** (`02_foreign_places.py`). INSEE gives them letter-prefixed codes and upper-case names cut at 20 characters, some misspelled ("IWAREGEM" is Waregem). Nominatim, 1 request per second, cached. Names repeat (three Lichtenaus in Germany), so the pick is the candidate nearest the median of its code group: the third character of the code is a region (SU9 Vaud, BE5 Hainaut, AL3 Baden-Württemberg). 44 names corrected by hand, listed in the script. 1,600 of 1,602 placed; "SAI" codes (sans autre indication) give only a region and stay off the map, like the 21,239 people abroad with no commune.
3. **Web files** (`03_web_data.py`). Each flow is written twice, once under each end (dir 0: residents of the commune working in the other; dir 1: residents of the other working in the commune; intra-commune once as dir 2), sorted by commune in 16,384-row groups. `places.parquet` stores each commune's row range, so a click reads exactly its rows with no index lookup. Distances are straight lines between representative points.
4. **Page** (`index.html`, `app.js`). [hyparquet](https://github.com/hyparam/hyparquet) reads the Parquet files in the browser. GitHub Pages gzips `application/octet-stream` on the fly when the browser accepts gzip, and byte ranges then point into the gzipped stream, so range reads break there. The two small files are downloaded whole from Pages; `flows.parquet`, the only file read by range, comes from `raw.githubusercontent.com`, which serves the repo file uncompressed with range and CORS support; deck.gl 9 draws faint outlines, centroid nodes and flat arcs. The pulses are a shader injection on ArcLayer (`FlowArcLayer`). Arcs: flows of 200 or more, plus the top 10. No basemap.
5. **Video** (`04_render_video.cjs`). `?capture` turns off the animation loop; the script steps time frame by frame and screenshots each one at 1080 x 1350.

## Limitations

- Straight-line distances, not travel time or route length.
- Flows under 200 are shown with ≈ and are not drawn as arcs; INSEE treats them as orders of magnitude. Outflows and inflows can come from different survey years.
- Jobs counts only jobs held by residents of France; cross-border workers coming into France are not in this file.
- Two foreign places could not be placed reliably (Mülheim, 77 workers; Saint-Jean in Valais, 5).

## Run it

```
D=work/data/day-13-interactions            # raw/ holds the INSEE zip and the Etalab file
S=site/day-13-interactions/scripts
npm i -g mapshaper@0.6; pip install "geopandas>=1.0" duckdb
python3 $S/01_boundaries.py $D
python3 $S/02_foreign_places.py $D         # re-run until "remaining 0" (Nominatim, 1 per second)
python3 $S/03_web_data.py $D site/day-13-interactions/web
cd site && npx http-server -p 8013 -c-1    # needs range requests; python -m http.server does not support them
node day-13-interactions/scripts/04_render_video.cjs 06088 frames 24 12
```

## Layout

```
index.html, app.js, style.css   the page (deck.gl 9, hyparquet, no basemap)
web/                            places.parquet, communes.parquet, flows.parquet (read in the browser)
images/preview.png              social preview
scripts/                        boundaries, geocoding, web data, video renderer
```
