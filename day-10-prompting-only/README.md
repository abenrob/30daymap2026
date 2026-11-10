# Day 10 · Prompting only: Dinner in Paris, a terminal adventure

Pick a Paris hotel, answer a few prompts at a blinking cursor, and walk to dinner. It plays like an early-80s graphic adventure: one scrolling terminal, with a picture printed into the scroll when there is something to see. The pictures are maps drawn in braille characters, and every answer is a SQL query against BigQuery through CARTO.

Page: https://abenrob.github.io/30daymap2026/day-10-prompting-only/

## What it does

1. Which hotel are you staying at? Eight hotels across central Paris.
2. A map is printed and the 15 minute walking isochrone grows out from the hotel door, one H3 cell at a time.
3. How far will you walk (5, 10 or 15 minutes), what are you hungry for, the budget, any dietary needs, and does it need a reputation (Travellers' Choice, Michelin Guide, Michelin stars).
4. A search report with counts per walk band. Under five results: "Slim pickings", with the number of places each relaxation would give.
5. A map with the page's five places numbered, then the list, sorted by walk time then rating.
6. Pick one: a last map, the route animates along the streets, and the turn-by-turn directions print as the line reaches each turn.

Commands at any prompt: `back`, `restart`, `help`, `quit`. The window needs at least 100 x 36 characters.

## How it was made

- **Data in the warehouse.** The TripAdvisor European restaurants table (1,083,397 rows) loaded into BigQuery with the CARTO CLI, 16,384 Paris restaurants with a rating derived from it, each tagged with an H3 resolution 10 cell.
- **H3 isochrones.** CARTO LDS (TravelTime) walking isolines from each hotel at every minute from 1 to 30, polyfilled to H3 resolution 10 with the Analytics Toolbox, keeping the smallest minute per cell. A restaurant's walk time is a join on the H3 index.
- **Routes.** A CARTO Workflow (Create Routes, pedestrian, TomTom) routed all 9,510 hotel to restaurant pairs inside 15 minutes in about 18 minutes, keeping TomTom's text instructions. Each instruction carries the index of the route vertex it applies to, which is how the directions sync with the animation. TomTom's route time and the H3 minute agree well (correlation 0.97, TomTom 0.6 min shorter on average).
- **App.** Vite, TypeScript and xterm.js. Pictures are printed into the scroll and redrawn in place with relative cursor moves while they are still on screen, which is how the isochrone and the route animate. Five constant, parameterised SQL queries through `@carto/api-client`, with a public token that grants only those five query texts. The basemap is CARTO's vector tiles (no key), decoded in the browser and rasterised into a dot grid (Bresenham lines, 2 x 4 dots per braille cell, x corrected by cos(latitude)), coloured per cell with ANSI truecolor.
- **Font.** DejaVu Sans Mono has no braille glyphs, and fallback fonts break the grid, so the build adds 256 braille glyphs drawn to the exact monospace cell.

Full method and every CARTO call: [scripts/pipeline/README.md](scripts/pipeline/README.md).

## Limitations

- TripAdvisor data is a snapshot scraped in May 2021. Some places have closed, ratings and hours have changed. Opening hours are shown as "2021 hours".
- Cuisine groups come from TripAdvisor tags, and "bistro or brasserie" is a name match (bistro, bistrot, brasserie, bouillon).
- Walk times are from the hotel's front door address as geocoded, at TravelTime's walking speed.

## Data

| What | Source | Licence |
| --- | --- | --- |
| Restaurants | [TripAdvisor European restaurants](https://www.kaggle.com/datasets/stefanoleone992/tripadvisor-european-restaurants), Stefano Leone on Kaggle, scraped from TripAdvisor May 2021 | As published on Kaggle; used here for a demo only, the raw data is not redistributed |
| Isolines | CARTO Location Data Services, TravelTime | CARTO terms |
| Routes, geocoding | CARTO Location Data Services, TomTom | CARTO terms |
| Basemap | © CARTO, © OpenStreetMap contributors | ODbL (OSM data) |
| Font | DejaVu Sans Mono, braille glyphs added | DejaVu fonts licence (Bitstream Vera derivative) |

## Layout

```
index.html, assets/   the built page
scripts/app/          the app source (npm install, npm run dev, npm run build)
scripts/pipeline/     SQL, Python and the routes workflow, in run order
```
