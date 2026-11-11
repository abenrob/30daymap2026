# Pipeline: Dinner in Paris

Everything the game reads lives in BigQuery, in `cartodb-on-gcp-cs-team.paris_restaurants`, reached through the CARTO connection `cs_bigquery` (CARTO CS team org). The app never touches anything else: it runs five fixed, parameterised SQL queries through the CARTO SQL API with a token that grants exactly those five queries.

All steps use the CARTO CLI (`npm i -g @carto/carto-cli`, then `carto auth login`).

| Step | File | What it does | CARTO piece |
| --- | --- | --- | --- |
| 0 | `00_dataset.sql` | Creates the dataset | SQL API (`carto sql job`) |
| 1 | `01_hotels.py` | Geocodes 8 hotels from their street addresses, imports `hotels` | LDS geocoding (TomTom), Imports API |
| 2 | `02_isolines.py` | Walking isolines from each hotel at every minute from 1 to 30 (240 requests, one range each), imports `isolines` | LDS isolines (TravelTime) |
| 3 | `03_h3_walk.sql` | Polyfills every isoline to H3 resolution 10 and keeps the smallest minute per cell: `hotel_h3_walk`, the H3 isochrone | Analytics Toolbox `H3_POLYFILL` |
| 4 | `04_restaurants.sql` | Loads the full TripAdvisor table (1,083,397 rows, clustered by `geom`), derives `restaurants` for Paris with H3 cell, price tier, Michelin stars, Bib Gourmand, Travellers' Choice, diets and cuisine groups | Imports API, `H3_FROMGEOGPOINT` |
| 5 | `05_od_pairs.sql` | Every hotel x restaurant pair inside 15 minutes, by joining on the H3 cell | SQL |
| 6 | `06_routes_workflow.json` | CARTO Workflow: Read Table `od_pairs` -> Create Routes (Pedestrian, TomTom text instructions) -> Save as Table `routes` | Workflows, LDS routing |

Run the SQL files with `carto sql job cs_bigquery --file <file>`. Create and run the workflow with `carto workflows create --file 06_routes_workflow.json` and `carto workflows run <id>`.

## Why these choices

- Walk time comes from H3, not from distance. A restaurant's walk time is the minute of the H3 cell it sits in, so filtering is a join on an H3 index, no geometry at query time.
- One isoline per minute rather than five bands: TravelTime accepts a single range per request, and per-minute cells let the game animate the isochrone growing outward.
- H3 resolution 10 (about 66 m edge). Resolution 9 (about 174 m) is coarser than a 1 minute walk.
- Routes are precomputed. Routing on demand would mean shipping a token with LDS access in a public page. The workflow routes only the pairs inside 15 minutes (the game's maximum), so 9,510 routes instead of 36,839 for 30 minutes.
- `routes.carto_routing_metadata` keeps TomTom's guidance; each instruction's `pointIndex` points into the route geometry, so the app prints "Turn left onto ..." as the animated line reaches that vertex.

## Tables

| Table | Rows | Notes |
| --- | --- | --- |
| `tripadvisor_european_restaurants_raw` | 1,083,397 | Kaggle dataset as published, clustered by `geom` |
| `restaurants` | 16,384 | Paris, with a rating; clustered by `h3` |
| `hotels` | 8 | |
| `isolines` | 240 | 8 hotels x 30 minutes |
| `hotel_h3_walk` | 8,518 | `hotel_id, h3, minutes`, clustered by `hotel_id, h3` |
| `od_pairs` | 9,510 | inside 15 minutes |
| `routes` | 9,510 | route line, distance, duration, instructions |

## The app token

```
carto credentials create token --name paris-restaurants --apis sql \
  --connection cs_bigquery --source "<hotels query>" \
  --connection cs_bigquery --source "<h3 query>" \
  ... one --connection/--source pair per query in src/carto.ts ...
  --referers 'http://localhost:5173*,https://abenrob.github.io/*'
```

A query grant matches the SQL text exactly (whitespace and case aside), so the queries in `src/carto.ts` are constants and every input is a named parameter (`@hotel`, `@cuisine`, ...). Change a query and the token needs a new grant.

## Font

`font/build_font.py` takes DejaVu Sans Mono and adds 256 braille glyphs drawn to the exact monospace cell (2 x 4 square dots), because DejaVu Sans Mono has no braille and fallback fonts break the grid.
