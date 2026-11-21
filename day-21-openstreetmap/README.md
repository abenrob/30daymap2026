# Day 21 · OpenStreetMap: Open Street Cheese

Cheese vending machines mapped in OpenStreetMap across Switzerland and its neighbours, and the protected cheese each one is likely to stock. OSM says a machine sells cheese (`vending=cheese`), never which cheese, so each machine gets the AOP / PDO cheeses whose official production zone it sits in. The animation (1080 x 1350, 53 s) goes one cheese at a time from west to east: the zone lights up and a cow drops onto every machine inside it.

No live page; the video is posted on LinkedIn.

## Numbers

- Worldwide, OSM has 407 objects whose `vending` tag mentions cheese, fondue or dairy (Overpass, 21 November 2026); 166 of them are in the Alpine area on the map, 41%.
- Overpass, box 45.0–47.9 N, 5.5–10.6 E: 172 machines with `vending` containing cheese, fondue or dairy (one `vegan_cheese` dropped). By country: Switzerland 93 (whole country), France 33, Austria 30, Italy 0 (5 in all of Italy). 166 fit in the map frame.
- 152 of the 166 sit inside at least one AOP zone, and many in several (up to five or six around the Jura, where Comté, Morbier, Mont d'Or and the IGPs overlap). 14 sit in none: Appenzell, Graubünden and Uri have no AOP cheese (Appenzeller is a trademark, not an AOP), plus a few in Germany outside the Allgäu.
- Most machines per cheese: Emmentaler 48, Vorarlberger Bergkäse & Alpkäse 30, Comté 19, Morbier 19, Gruyère 19, Berner Alpkäse 16.
- Tagging is loose: `vending=cheese;fromage`, `milk;cheese;dairy;capuns`, and 6 machines tagged `vending=fondue`.

## Method

1. **Machines** (`01_fetch_osm.sh`, `02_machines.py`). One Overpass query; ways and relations reduced to their centre.
2. **Zones** (`03_build_zones.py`). Switzerland: each zone dissolves OSM admin boundaries (cantons, districts, communes) following Art. 2 of the cheese's cahier des charges / Pflichtenheft. Austria and Germany: Vorarlberg, Tirol and the Allgäu Landkreise. France: the INAO SIQO shapefile (cheese AOPs, plus IGPs flagged in a `label` column and left out of the animation).
3. **Join** (`04_join.py`). Point in polygon; `likely_aop` lists every zone a machine falls in.
4. **Map and animation** (`05`–`08`). SRTM3 hillshade, Natural Earth water, OSM borders; frames drawn with Pillow and piped into ffmpeg (H.264, CRF 18). Each cow has a random start, drop height and fall time, then two decaying bounces.

### Zone simplifications

Several Swiss specs name units that no longer exist, so they are mapped to today's OSM units:

| Cheese | Specification | Mapped as |
| --- | --- | --- |
| Emmentaler | AG, BE without the former district of Moutier, LU, SO, SG, TG, ZG, ZH, Lac and Sense districts | BE minus today's Jura bernois |
| Berner Alpkäse | Summer pastures of the old Oberland Amtsbezirke | Four whole Verwaltungskreise (Interlaken-Oberhasli, Frutigen-Niedersimmental, Obersimmental-Saanen, Thun) |
| Gruyère | FR, VD, NE, JU, Jura bernois, six Bern communes | As written; named dairy catchments ignored |
| Sbrinz | LU, SZ, OW, NW, ZG + dairy catchments in SG and AG | Cantons only |
| Tête de Moine | Franches-Montagnes, Porrentruy, Saulcy, Jura bernois minus three communes, mountain zone | Mountain-zone limit not applied |
| Vacherin Mont-d'Or | Jura-Nord vaudois minus 28 communes, Morges minus 3, 14 named communes, alpine pastures | Pastures skipped; 2 excluded communes have since merged |
| L'Etivaz, Formaggio d'alpe ticinese, Glarner Alpkäse | Summer pastures | Whole communes / cantons |
| Bloderkäse & Sauerkäse | 12 St. Gallen communes + Liechtenstein | Today's merged commune names |
| Allgäuer Bergkäse & Emmentaler | Allgäu | Bavarian Allgäu Landkreise + Lkr Ravensburg (approximate) |

Mont d'Or (France) and Vacherin Mont-d'Or (Switzerland) share one step of the animation.

## Limitations

- "Likely" is a guess from geography only: nothing forces a machine to sell its local AOP, and many sell non-AOP farm cheese.
- Coverage is what OSM volunteers have mapped; zero machines in Italy says more about tagging than about Italy.
- Alpine-pasture cheeses are drawn as whole districts, so their zones are much larger than the real pastures.

## Sources

| What | Source |
| --- | --- |
| Vending machines, admin boundaries | © OpenStreetMap contributors, ODbL, via Overpass API |
| Swiss AOP areas | Cahiers des charges / Pflichtenhefte, Federal Office for Agriculture register and aop-igp.ch |
| French AOP / IGP areas | INAO, Délimitation des aires géographiques des SIQO, data.gouv.fr, Licence Ouverte |
| Relief | SRTM3 via IGN Géoplateforme WMS-R (`ELEVATION.ELEVATIONGRIDCOVERAGE.SRTM3`) |
| Lakes, rivers, borders | Natural Earth 1:10m, public domain |
| Fonts | DM Serif Display, Inter (SIL Open Font License) |

## Layout

```
images/preview.png          card and social preview (1600 x 900)
scripts/config.py           paths (data in work/day-21-openstreetmap, or $OSC_WORK), frame layout, projection
scripts/01_fetch_osm.sh     Overpass: machines + admin boundaries (needs a shell that can reach overpass-api.de)
scripts/02_machines.py      raw.json -> cheese_vending.geojson
scripts/03_build_zones.py   AOP zones -> aop_cheese_zones.geojson
scripts/osm_polygons.py     Overpass relations -> shapely polygons
scripts/04_join.py          machines x zones -> cheese_vending_aop.geojson
scripts/05_fetch_basemap.sh SRTM3 tiles, Natural Earth, fonts
scripts/06_render_base.py   hillshaded basemap -> base_map.png
scripts/cow.py              the cow sprite
scripts/scene.py            story order, timing and frame drawing
scripts/07_animate.py       MP4 (or --stills for review frames)
scripts/08_preview.py       preview.png
```

Run in order from `scripts/`. `03_build_zones.py` reads the INAO shapefile downloaded for Day 19 (`work/day-19-senses-smell/data/raw/`).
