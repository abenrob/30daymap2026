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
