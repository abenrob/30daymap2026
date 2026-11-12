# Day 12 · Power: The Day Iberia Went Dark

Hourly power flows on 3,346 transmission lines and HVDC links in Spain, Portugal and France, from 25 April to 2 May 2025, through the blackout of 28 April (12:33 CEST, 10:33 UTC). Dashes move in the direction of flow and get thicker, faster and brighter with more MW. Colour is loading against the thermal rating.

Page: https://abenrob.github.io/30daymap2026/day-12-power/

**What this is:** modelled flows on the real network topology, calibrated to measured country-level data. It is not a measurement of flow on any one line. A DC power flow ignores voltage and reactive power, and the blackout was a voltage event, so the map shows where active power went, not why the grid fell. It makes no claim about cause or responsibility; for that, see the [ENTSO-E expert panel report](https://www.entsoe.eu/publications/blackout/28-april-2025-Iberian-blackout/).

## Numbers

- Spanish peninsular demand (REE, hourly mean): 25.4 GW in the 11:00 CEST hour, 518 MW in the 13:00 hour, 14.6 GW at midnight, above 20 GW again in the 07:00 hour on 29 April.
- Portugal: 92 MW in the 13:00 hour, 4.4 GW by midnight. The Spain-Portugal link stays near zero until the morning of 29 April.
- France to Spain during the restart: up to 2,000 MW (RTE schedules). REE's measured line totals for 28 April: 25.7 GWh from Spain to France before the collapse and 12.8 GWh back into Spain after it. On 29 April, a net 5.7 GWh into Spain.
- Morocco to Spain (REE, daily): 2.1 GWh on 28 April and 1.8 GWh on 29 April. On the other days of the week Spain exported 4 to 17 GWh a day to Morocco.

## Data

| What | Source | Notes |
| --- | --- | --- |
| Demand, generation by fuel, border flows (ES, PT, FR) | [Energy-Charts API](https://api.energy-charts.info/) (Fraunhofer ISE), CC BY 4.0 | 15-min, averaged to hourly. No token. |
| Spanish demand during the blackout, per-line interconnector flows, Morocco and Andorra | [REE REData](https://www.ree.es/en/apidatos) | Demand is hourly. Exchanges are daily only (hourly requests return HTTP 400). |
| French demand, generation and border schedules | [RTE eCO2mix](https://odre.opendatasoft.com/explore/dataset/eco2mix-national-cons-def/) via ODRÉ, Licence Ouverte | Definitive data, 30-min. ODRÉ is unreachable from some cloud IPs; run from a normal connection. |
| Network | [OSM prebuilt grid for PyPSA-Eur](https://doi.org/10.5281/zenodo.14144752) v0.6, © OpenStreetMap contributors, ODbL | 220 to 750 kV lines, HVDC links, transformers, with reactance and rating. |
| Plant locations | [powerplantmatching](https://github.com/PyPSA/powerplantmatching) (PyPSA), MIT | Plants in service in April 2025. |
| Population | Natural Earth populated places, public domain | Demand proxy. |
| Basemap | © CARTO, © OpenStreetMap contributors | |

ENTSO-E's Transparency Platform holds the same underlying data but needs an API token, which did not arrive in time. REE and RTE replace it as independent cross-checks.

## Method

1. **Network** (`build_network.py`). AC buses in ES, PT and FR plus the outside buses one branch away. Lines keep the OSM-derived reactance and rating; transformers get x = 0.1 per unit (the PyPSA-Eur default); HVDC ends are moved to their AC converter buses. The model has 2,399 buses. The Bay of Biscay HVDC link is under construction and is not in the network; the France-Spain HVDC in service is Baixas to Santa Llogaia.
2. **Placing generation and demand.** Each fuel's national output is spread over the buses holding that fuel's plants, in proportion to capacity (plants snapped to the nearest 220 kV+ bus). Fuels with no plant (waste, "other") follow demand. Demand is spread by 0.7 × population (each Natural Earth place spread over nearby buses with a 30 km Gaussian kernel) + 0.3 × attached line capacity. This is the weakest assumption in the model.
3. **Data fixes**, all logged when the model runs:
   - Energy-Charts reports Spain-France flow as exactly zero from 11:00 UTC on 28 April to 21:00 UTC on 29 April, but REE's measured daily line totals show France supplying Spain. Those 35 hours are refilled from RTE's France-Spain schedules. Daily totals then match REE to 0.3 GWh on 28 April and 0.04 GWh on 29 April (before: off by 11.6 and 5.7 GWh).
   - Energy-Charts has no Spanish demand from the collapse until 21:00 UTC on 29 April, and shows about 5 GW of solar and 2 GW of wind in the hour after the collapse, when REE measured 518 MW of demand. In that window demand comes from REE and generation is rescaled to demand plus measured exports: dispatchable fuels keep their shape, and wind and solar only fill what is left.
   - France's load and generation come from RTE rather than Energy-Charts, whose French pumped-storage consumption drops to zero on 1 and 2 May and leaves a 4 to 6 GW hole.
   - Pumped-storage and battery charging are kept as negative generation at the plant. (A first version dropped them because "consumption" contains "sum", one of the words it filtered on.)
4. **Borders.** Lines leaving the model carry the measured flow to Belgium, Germany/Luxembourg, Switzerland, Italy and Great Britain. Morocco and Andorra are not in the OSM grid; their REE daily totals are injected flat over the day at Puerto de la Cruz and Adrall. The two France-Spain HVDC cables carry REE's measured daily total, with hourly swings following the border.
5. **Calibration.** Each country's net export is pinned to its measured border totals; the remainder is taken off that country's demand pro rata. Mean absolute adjustment: ES 305 MW, PT 83 MW, FR 685 MW (FR is a steady +360 MW on average, consistent with losses and definitions).
6. **Outages.** Where REE shows no flow either way on an interconnector for a whole day, the line is switched off in the model for that day: Biescas-Pragnères from 25 April to 1 May, Brovales-Alqueva from 25 to 28 April.
7. **DC power flow**, one solve per hour per topology, with our own sparse solver (no PyPSA needed).

## Validation

Hourly border totals are imposed, so the modelled ES-FR and ES-PT border flows match the measurements (mean absolute error 46 and 41 MW). That proves only the bookkeeping. The real test is how the model splits a border across parallel lines, checked against REE's daily measured flow per interconnector (`validate_lines.py`, full Madrid days 26 April to 2 May):

| Line | Measured, mean MWh/day into Spain | Modelled | Mean abs error |
| --- | ---: | ---: | ---: |
| Hernani-Argia 400 kV | -11,664 | -8,693 | 2,971 |
| Vic-Baixas 400 kV | -2,858 | -4,652 | 1,819 |
| Arkale-Argia 220 kV | -479 | -1,859 | 1,380 |
| Santa Llogaia-Baixas HVDC | -7,659 | -7,659 | 0 (set from REE) |
| Douro group (Aldeadávila, Saucelle, Lagoaça, Pocinho) | 11,480 | 17,090 | 5,610 |
| Cartelle-Lindoso 400 kV | -2,146 | -5,485 | 3,390 |
| Cedillo-Falagueira 400 kV | -2,328 | -4,842 | 2,707 |
| Puebla de Guzmán-Tavira 400 kV | -2,014 | -1,739 | 859 |

Sum of absolute errors over sum of measured flow, AC lines only: 39% on France-Spain, 64% on Spain-Portugal. The model sends too much through the western Pyrenees' smaller lines and through the Douro. Read individual lines as indicative; the border totals and the before, during and after contrast are the reliable part.

## Limitations

- Playback and the video ease between hourly values, so in-between frames are interpolation, not data. Dash positions are carried from frame to frame, so a change in flow changes their speed without making them jump.
- Hourly averages hide the collapse, which took seconds. The 12:00 CEST hour blends the last half hour of normal operation with the first minutes of the blackout.
- Demand placement is a proxy. Flows deep inside a country depend on it most.
- OSM topology is approximate: some lines are missing or simplified, and ratings are estimated. Loading uses thermal limits, not the stricter limits operators plan against.
- The part of south-west France affected by the blackout is not visible in country-level data.

## Run it

```
cd work/data/day-12-power        # data folder: cache/, network/, out/
S=../../../site/day-12-power/scripts
pip install -r $S/requirements.txt
mkdir -p osm && for f in buses lines links transformers converters; do
  curl -sSL -o osm/$f.csv https://zenodo.org/api/records/14144752/files/$f.csv/content; done
curl -sSLO https://raw.githubusercontent.com/PyPSA/powerplantmatching/master/powerplants.csv
curl -sSLO https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_populated_places_simple.geojson
python3 $S/build_network.py --osm osm/ --plants powerplants.csv \
    --places ne_10m_populated_places_simple.geojson --out network
python3 $S/crosscheck_sources.py                 # REE + RTE, writes out/
python3 $S/iberian_blackout_flows.py --network network \
    --extra-borders out/extra_borders_ma_ad.csv --out out
python3 $S/validate_lines.py
python3 $S/export_web.py --dest ../../../site/day-12-power/flows
```

Energy-Charts allows 2 requests a minute; the first run takes about 4 minutes and everything is cached. The video: serve `site/` on port 8812, `node scripts/render.js frames`, then ffmpeg (command in the script).

## Layout

```
index.html, app.js, style.css   the page (MapLibre + deck.gl 8.9, custom animated path layer)
flows/                          lines.json (geometry), flows.bin (Int16 MW, hour-major), series.json
images/preview.png              social preview
scripts/                        model, cross-checks, validation, export, frame renderer
```
