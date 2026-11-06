# Day 6 · Vintage: The Vintages

Wine as vintage, and every year since 1962 as a vintage of the wine trade. A world map of who sold wine to whom, on the borders of each year, with a Sankey chart of the same flows underneath. Pick a country to see only its suppliers and buyers, and play the years from 1962 to 2023.

Live page: https://abenrob.github.io/30daymap2026/day-06-vintage/

## Data

| What | Source | Licence |
| --- | --- | --- |
| Bilateral wine trade, 1962 to 2023 | UN Comtrade, wine of fresh grapes: SITC 1121 (Rev. 1, 2, 3) and HS 2204 | UN Comtrade terms. Only transformed data is published here |
| Country borders by year | CShapes 2.0, Schvitz, Rüegger, Girardin, Cederman, Weidmann and Gleditsch (2022), "Mapping The International System, 1886-2017: The CShapes 2.0 Dataset", *Journal of Conflict Resolution* 66(1): 144-61 | CC BY-NC-SA 4.0. The simplified geometry in `assets/countries.topo.json` is shared under the same licence |
| Land outline, points for territories | Natural Earth 1:50m | Public domain |

Borders are taken exactly as CShapes publishes them, for 1 July of each year. No border has been edited. CShapes ends in 2019, so its 2019 borders are carried forward to 2023. CShapes covers independent states only. Territories (Réunion, Hong Kong, ...) and colonies before independence show as land without a border, and their arcs start or end at a Natural Earth point.

## Method

1. `scripts/01_pull_comtrade.py` pulls annual imports and exports for every reporter and partner, in each classification for the years it covers (SITC Rev. 1 1962 to 1999, Rev. 2 1976 to 2005, Rev. 3 1988 to 2005, HS 1988 to 2023). It needs a free Comtrade Plus API key in the environment variable `COMTRADE_API_KEY` or in a `.env` file passed with `--env`. The key is never committed. Raw pulls stay out of the repo.
2. `scripts/02_geometry.py` keeps every CShapes polygon in force on 1 July of any year from 1962 to 2023, and gives each one a valid year range and an anchor point (the pole of inaccessibility of its largest part). The result is simplified with mapshaper into TopoJSON.
3. `scripts/03_flows.py` builds the flows:
   - For each reporter and year, it uses the classification with the largest total value, so the most complete submission wins.
   - Each flow is the importer's report where one exists. Otherwise it is the exporter's report (mirror fill).
   - Where both sides report, the exporter's report replaces the importer's in three cases: the importer gave no volume, the two volumes differ by more than 3x and the exporter's price per litre is closer to that pair's usual price, or the importer's value is more than 5x the exporter's. For example, France's 2018 import report gives 10.9 m litres from Spain for $385 m, while Spain reports 480 m litres.
   - A volume whose implied price is more than 15x away from that year's world median is re-estimated from its value. This catches Kazakhstan's 1990s import quantities, which are about 1,000x too high.
   - Every flow's price per litre is then checked against the same pair's median price over the surrounding nine years. Beyond 3.5x either way, the volume is re-estimated from the value at that pair price. This catches broken single reports such as Spain to Denmark in 1999 (3.2 m litres for $74 m). About 9% of flows are adjusted this way, under 1% of the volume.
   - Volume is litres as reported. Kilograms are taken as litres, since wine is about 0.99 kg per litre. Where only value was reported, volume is estimated at the median USD per litre of that reporter and year, and these estimates are flagged.
   - Comtrade codes become countries and are joined to CShapes through Gleditsch-Ward codes. Historical codes are mapped by hand: USSR 810, Czechoslovakia 200, East and West Germany 278 and 280, Yugoslavia 890, Serbia and Montenegro 891, Belgium-Luxembourg 58, and others. Belgium-Luxembourg uses both CShapes polygons.
   - Successor states get their own slot, grouped with their predecessor in a fixed order: Old World, New World, then elsewhere, by total volume. "Other Asia, nes" keeps Comtrade's label and has no geometry.
4. `scripts/04_basemap.py` writes the land layer and the fallback points.

The page is plain D3 v7 (`index.html`, `app.js`, `style.css`) reading the files in `assets/`.

## Reading it

- Arcs follow the shortest great circle, so flows across the Pacific leave one edge of the map and come back on the other.
- Each arc bows to the left of its direction of travel, so a flow and its reverse never overlap. Width is volume. With no country selected, the 80 largest flows of the year are drawn.
- In the Sankey, every country keeps its place for the whole period, so only the ribbons move from year to year. Heights are shares of that year's trade.
- `?capture` switches to a fixed 1080 x 1350 layout for sharing (no controls, larger type, the 40 largest arcs). The images in `images/` are screenshots of it, for example `?capture#c=FRA&y=1962`.
- Link a view with the URL hash, for example `#c=FRA&y=1985`. Add `?play` to the URL to start the animation on load.

## Rebuild

```
pip install -r requirements.txt
npm install -g mapshaper
python scripts/01_pull_comtrade.py raw --env ../../.env
python scripts/02_geometry.py CShapes-2.0.shp build/cshapes_1962_2023.geojson
mapshaper build/cshapes_1962_2023.geojson -simplify 6% keep-shapes planar -filter-islands min-area=100km2 -o format=topojson quantization=1e5 assets/countries.topo.json
python scripts/03_flows.py raw comtrade_partnerAreas.json build/cshapes_1962_2023.geojson build
python scripts/04_basemap.py ne_50m_land.zip ne_50m_admin_0_countries.zip build/wine_flows.json build
```
