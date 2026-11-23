# Day 23 · Senses: Taste: Saint-Joseph vs Gigondas

Two Rhône crus compared on terrain, parent rock, soil and climate, measured only where the vines actually grow. Five 4:5 slides; no live page.

## Method

- **Where the wine may come from.** INAO *aire parcellaire* (parcel-level delimitation of the wine AOCs), WFS layer `AOC-VITICOLES:aire_parcellaire` on the IGN Géoplateforme, filtered `denom ILIKE '%name%'`. Saint-Joseph: 984 polygons, 3,437 ha. Gigondas: 1,237 polygons, 1,736 ha. The usual appellation maps (*aire géographique*) are whole communes; this is much tighter.
- **Where vines actually grow.** BD TOPO `zone_de_vegetation` with `nature = 'Vigne'` (mapped from orthophotos), unioned with RPG 2023 vine parcels (`code_group = '21'`), clipped to the aire parcellaire. RPG alone gives about half the area (not every grower declares to the CAP).
- **Terrain.** IGN RGE ALTI 5 m from the Géoplateforme WMS-R (float32 BIL). Slope and aspect by finite differences; aspect is the direction the slope faces. Roses and mean aspect use slopes of 3° or more.
- **Parent rock and soil.** INRAE Info&Sols / Gis Sol, *Les sols dominants de France métropolitaine – carte harmonisée* (the national merge of the 1:250,000 regional soil databases, RRP), WFS `INRAE_CARTE-SOLS:sols_dominants_france_metropolitaine`, metadata dated 2026-09-01. Its map-unit descriptions name the parent material, grouped by keyword into six rock classes (`04_soil.py`). No vector geology was reachable (BRGM maps are only on the WMTS as scans).
- **Climate.** Daily ERA5-Land temperature from the Open-Meteo historical API at the vines' median elevation (Saint-Joseph 289 m, Gigondas 196 m), precipitation from ERA5. Saint-Joseph = mean of three points, one per third of its vines from north to south. Huglin index (April to September, k = 1.04 for 44 to 46°N); classes after Tonietto & Carbonneau (2004).

## Results

| | Saint-Joseph | Gigondas |
| --- | --- | --- |
| Allowed (aire parcellaire) | 3,437 ha | 1,736 ha |
| Vines inside it | 1,550 ha (45%) | 1,176 ha (68%) |
| Mean facing (slopes ≥ 3°) | 118° (E–SE) | 275° (W–NW) |
| Median slope, vines | 12° | 4° |
| Median slope, allowed but unplanted | 24° | 18° |
| Vines on slopes ≥ 15° | 40% | 13% |
| Vines on near-flat ground (< 3°) | 8% | 40% |
| Median altitude, vines | 289 m | 196 m |
| Parent rock | 65% granite & gneiss, 16% schist | 39% river terraces, 31% Miocene sandy marl, 30% Triassic–Jurassic limestone & marl |
| Dominant soil | 77% alocrisol (acid, sandy) | 58% calcosol, 30% fersialsol, 11% lithosol |
| Huglin index 1991–2020 | 1,861 | 2,261 |
| Huglin index 2015–2024 | 2,056 | 2,455 |
| Rain per year 1991–2020 | 948 mm | 740 mm |
| July mean daily max 1991–2020 | 26.4 °C | 29.4 °C |
| Summer days ≥ 35 °C, 2015–2024 | 3 | 8 |

Gigondas is warmer than Saint-Joseph in every year from 1991 to 2024, by 225 (2018) to 536 (2012) Huglin points, 400 on average. Both trend upward: +121 (Saint-Joseph) and +130 (Gigondas) points per decade, about +400 over the period. Saint-Joseph's 2015–2024 mean (2,056) is close to Gigondas's 1991–2000 mean (2,109).

## Scripts

| Script | Does |
| --- | --- |
| `01_fetch_vectors.py` | Aire parcellaire, BD TOPO vines, RPG 2023 vines and soil map units from the Géoplateforme WFS |
| `02_fetch_dem.py` | RGE ALTI tiles from the WMS-R into a GeoTIFF (5 m per appellation, 100 m for the valley) |
| `03_terrain.py` | Slope, aspect, altitude for planted vs allowed-but-unplanted → `terrain_stats.json` |
| `04_soil.py` | Rock classes and soils under the vines → `soil_stats.json` |
| `05_climate.js` | Browser-console snippet for Open-Meteo (the shells could not reach the API) |
| `05_climate_values.py` | The values it returned, and the Saint-Joseph average → `climate_stats.json` |
| `06_slides.py` | The five slides (matplotlib; Lora + Inter). Rivers on slide 1 from Natural Earth 10m |

Data and intermediate files live in `work/day-23-senses-taste`.

## Limitations

- BD TOPO vineyards come from photo interpretation and lag replanting and grubbing-up; the union with RPG slightly overshoots Saint-Joseph's published planted area (about 1,300 to 1,415 ha) because some parcels inside the aire are claimed as Condrieu or Côtes du Rhône.
- The soil map is 1:250,000: a map unit is a landscape type, not a parcel, and INRAE advises against reading it at cadastral scale without field checks. Read the rock shares as the dominant setting.
- Climate is about 9 km (ERA5-Land) and about 30 km (ERA5 rain): the valley-wide difference, not slope-scale microclimate. An east-facing granite terrace and a west-facing terrace in the same cell get the same numbers.
- "Allowed but unplanted" mixes woods that were never planted with abandoned terraces; the data can't tell them apart.

## Data and licences

INAO délimitation parcellaire des AOC viticoles; IGN BD TOPO, RGE ALTI and RPG 2023 (ASP/IGN), Licence Ouverte Etalab 2.0, via the IGN Géoplateforme. INRAE Info&Sols / Gis Sol, sols dominants de France métropolitaine (RRP 1:250,000, 2026-09-01), via the Géoplateforme; its metadata declares no licence, so this repo publishes only aggregate shares, not the polygons. ERA5-Land and ERA5, Copernicus Climate Change Service, via Open-Meteo (CC BY 4.0). Natural Earth rivers, public domain.
