# 30DayMapChallenge 2026

Maps, code and write-ups for [#30DayMapChallenge](https://30daymapchallenge.com/) 2026 by Adam Roberts.

This year's thread: the tools geospatial is moving to. 3D and digital twins in Blender, cloud-native Earth observation (STAC, COG, Zarr, Raquet), analytics in the browser with DuckDB, and open table formats. Each day is a map plus what I measured and learned along the way.

Site: https://abenrob.github.io/30daymap2026/

## Days

In day order. A row is added when the day is published.

| Day | Theme | Map |
| --- | --- | --- |
| 1 | Points | [103 million places, one box over Paris: what three formats had to download](day-01-points/) |
| 2 | Lines | [26,297 km of lines that all end in one place: the Rhône, traced upstream from the sea](day-02-lines/) |
| 3 | Polygons | [The 2,696 buildings of Paris's 4e, lifted off the map and sorted by use and size](day-03-polygons/) ([live page](https://abenrob.github.io/30daymap2026/day-03-polygons/)) |
| 4 | Clusters | [Every building in Denmark grouped into settlements at 10 m: 4.16 million footprints in 5.3 minutes, inside Snowflake](day-04-clusters/) ([map](https://clausa.app.carto.com/map/c5aa833e-6180-4c49-891c-ba54a64e8455)) |
| 5 | Senses: Sight | [What you can see from every point of the GR 738 across Belledonne](day-05-senses-sight/) ([video](https://abenrob.github.io/30daymap2026/day-05-senses-sight/)) |
| 6 | Vintage | [Sixty years of the wine trade, on the borders of each year](day-06-vintage/) ([live page](https://abenrob.github.io/30daymap2026/day-06-vintage/)) |
| 7 | 10 minute map | [177,614 Florida homes in the wildland-urban interface and more than ten minutes from a fire station](day-07-10-minute-map/) ([story map](https://abenrob.github.io/30daymap2026/day-07-10-minute-map/)) |
| 8 | Utopia | [283 places in the UK have "Utopia" in the name: adjusted for population, the Highlands beat London](day-08-utopia/) ([page](https://abenrob.github.io/30daymap2026/day-08-utopia/)) |
| 9 | Urban-rural | [Same density, different class: two towns 8 km apart on the line from Paris to Chartres](day-09-urban-rural/) ([video](https://abenrob.github.io/30daymap2026/day-09-urban-rural/)) |
| 10 | Prompting only | [Dinner in Paris: a 1980s-style text adventure over 16,384 restaurants, built by prompting only](day-10-prompting-only/) ([live page](https://abenrob.github.io/30daymap2026/day-10-prompting-only/)) |
| 11 | Senses: Sound | [About 20 people at the Vogue, 30,000 at Magnuson Park: Seattle's grunge years, mapped show by show](day-11-senses-sound/) ([story map](https://abenrob.github.io/30daymap2026/day-11-senses-sound/)) |
| 12 | Power | [Spain's demand fell from 25.4 GW to 518 MW in one hour: the Iberian blackout on 3,346 transmission lines](day-12-power/) ([live page](https://abenrob.github.io/30daymap2026/day-12-power/)) |
| 13 | Interactions | [Nice's biggest workplace outside Nice is another country: 10,495 residents commute to Monaco](day-13-interactions/) ([live page](https://abenrob.github.io/30daymap2026/day-13-interactions/)) |
| 14 | Borgesian map | [Barcelona at 1:1: sheet 1 of approximately 105 million](day-14-borgesian-map/) |
| 15 | Inside out | [Monterey Bay with elevation multiplied by -1: California under the sea, the canyon a ridge](day-15-inside-out/) |
| 16 | Collaborative map | [Velographs: how far you can cycle in an hour from anywhere on Earth, built with Ryan Morris](day-16-collaborative-map/) ([page](https://abenrob.github.io/30daymap2026/day-16-collaborative-map/)) |
| 17 | Light & dark | [Every minute of 2025, eight wind turbines, one ridge: the worst-case shadow flicker zone on the Marsanne ridge in the Drôme](day-17-light-and-dark/) |
| 18 | Null | [Field notes on an animal that cannot turn around: the seasonal circuits of the dahu around Grenoble](day-18-null/) ([live page](https://abenrob.github.io/30daymap2026/day-18-null/)) |
| 19 | Senses: Smell | [Époisses is on 21 of 24 smelliest-cheese lists; the only measured test put it 9th of 11 AOP cheeses: France's stinkiest AOP cheeses](day-19-senses-smell/) ([live page](https://abenrob.github.io/30daymap2026/day-19-senses-smell/)) |
| 20 | Hexagons | [Six sides, six frontiers: every side of France's textbook hexagon follows exactly one border](day-20-hexagons/) |
| 21 | OpenStreetMap | [Open Street Cheese: 166 cheese vending machines in OpenStreetMap, and the AOP cheese each one is likely to stock](day-21-openstreetmap/) |
| 22 | Projections | [One Greenland, many Greenlands: 15 map projections at one scale, scored on area and shape](day-22-projections/) ([live page](https://abenrob.github.io/30daymap2026/day-22-projections/)) |
| 23 | Senses: Taste | [Saint-Joseph vs Gigondas: same river, opposite slopes, 400 heat-index points apart](day-23-senses-taste/) |
| 24 | Network | [Dropped at Alexanderplatz at 08:00: everywhere you can be by 08:40](day-24-network/) |
| 25 | Is this a map? | [The whole sky above Charmant Som in one fisheye, with the Alps and the valley lights around the rim](day-25-is-this-a-map/) |
| 26 | Water | [The Garonne flood moving downriver, seen through the clouds: Tonneins on 12 February, Langon on the 17th](day-26-water/) ([video](https://abenrob.github.io/30daymap2026/day-26-water/)) |
| 27 | New tool | [The Aiguille Dibona, from IGN orthophoto to ink drawing, rendered in Blender](day-27-new-tool/) ([video](https://abenrob.github.io/30daymap2026/day-27-new-tool/)) |

## Layout

Each day lives in its own folder:

```
day-NN-theme/
  README.md     what the map shows, data, method, numbers
  images/       the figures
  scripts/      everything needed to reproduce them
  index.html    the live page, on days that have one
```

`index.html` at the root is the gallery; `shared/` holds common styles.

## Running the scripts

Python 3.10 or later:

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Scripts write their intermediate files (Parquet extracts, PMTiles archives) to the current directory. Run them from a working folder outside the repo; `.gitignore` keeps data files out of git either way. Each day's README lists the order to run them in.

## Data

Every day credits its sources and their licences in its README. Data is read from public sources (Source Cooperative, STAC APIs, Overture, IGN and others) and not redistributed here unless the licence allows it and the files are small.
