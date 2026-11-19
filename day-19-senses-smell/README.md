# Day 19 · Senses: Smell: France's stinkiest AOP cheeses

A scrolling story map of the eight French AOP cheeses that turn up most often on published "smelliest cheese" lists, each shown on its official INAO production area, stinkiest first. It ends with the cheese that won the only measured test, Vieux-Boulogne, which has no AOP and so is just a dot.

Page: https://abenrob.github.io/30daymap2026/day-19-senses-smell/

## Method

- **Ranking.** Share of 24 published smelliest-cheese lists that name the cheese, then the position score (0 to 100) from the 5 lists that order by smell, then the Cranfield University 2004 measured rank (electronic nose plus 19 human sniffers, 15 cheeses), re-ranked among the 11 AOP cheeses it tested so every comparison stays AOP against AOP. AOP only: IGP and unprotected cheeses are left out. Top 8 = every AOP cheese on at least 4 lists.
- **Areas.** INAO's SIQO delimitation shapefile (9 Nov 2026 release, Lambert-93, one row per appellation). The 8 rows are made valid, reprojected to EPSG:4326 and kept as published (Camembert has 130 parts; holes are excluded communes). Web copy simplified to 0.002° (about 200 m), 164 KB.
- **Facts.** Milk, rind, washing, AOC year and the story text come from INAO product pages and the AOP specifications.
- **At the table.** Each chapter has taste, drink, bread and (where the sources give one) food pairings, paraphrased from the French AOP dairy council's product pages (CNAOL, produits-laitiers-aop.fr) and the INAO pages and specifications.
- **Style.** Translucent fills with solid outlines in a darker shade of each area's colour, so the nested Normandy areas stay readable.

| # | Cheese | Lists (of 24) | Position score | Cranfield, AOP only (of 11) | Cranfield, all (of 15) | Area km² |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Époisses | 21 | 73 | 9 | 10 | 7,135 |
| 2 | Pont-l'Évêque | 15 | 60 | 1 | 2 | 13,477 |
| 3 | Munster | 14 | 55 | 3 | 4 | 12,955 |
| 4 | Camembert de Normandie | 10 | 78 | 2 | 3 | 15,540 |
| 5 | Roquefort | 10 | 45 | 5 | 6 | 14,292 |
| 6 | Maroilles | 8 | 38 | – | – | 2,118 |
| 7 | Brie de Meaux | 5 | 39 | 4 | 5 | 16,326 |
| 8 | Livarot | 4 | 50 | 7 | 8 | 2,466 |

The 9 Nov 2026 INAO file holds 47 cheese AOPs; all 7 washed-rind ones are in the top 11 of the full ranking.

## How it works

MapLibre with the CARTO Positron basemap, deck.gl layers through `MapboxOverlay`: the AOP polygons in one fixed draw order (largest first, so Livarot sits on top of the nested Normandy areas), an outline layer for the active cheese, and rings drifting out from its centre. An `IntersectionObserver` picks the active chapter and the map fits to that area's bounding box. `?capture&step=N` renders a single chapter with a caption for the post stills, and `?poster` renders the 4:5 hero image (both 540 x 675 at 2x). `?poster&wide` renders the 16:9 card and social preview, `images/preview.png` (800 x 450 at 2x).

Scaffolded with the CARTO for Agents app-building skill (`carto-develop-app`, storymap pattern).

## Limitations

- The ranking is a consensus of opinion. Only Cranfield measured smell, and it tested 15 cheeses, one of them not French.
- INAO publishes the polygons for information only; the legal area is the commune list in each specification.

## Sources

| What | Source |
| --- | --- |
| AOP areas | INAO, [Délimitation des aires géographiques des SIQO](https://www.data.gouv.fr/datasets/5d7fb2856f444171a5f2780b), Licence Ouverte |
| Cheese facts | INAO product pages, AOP cahiers des charges |
| Tasting notes, pairings | CNAOL, [produits-laitiers-aop.fr](https://www.produits-laitiers-aop.fr/en/) |
| Measured ranks | Cranfield University, [Scientists name world's whiffiest cheese](https://www.eurekalert.org/news-releases/637544), Nov 2004 |
| Basemap | © CARTO, © OpenStreetMap contributors |

## Layout

```
index.html, assets/, aop.geojson   the built page
images/preview.png                 card and social preview (?poster&wide)
scripts/01_aop_areas.py            INAO shapefile -> 8 areas (work/day-19-senses-smell/data)
scripts/02_cheeses.py              cheeses.csv (chapter facts and text)
scripts/03_export_web.py           join + simplify -> scripts/app/public/aop.geojson
scripts/app/                       source (npm install, npm run dev, npm run build)
```
