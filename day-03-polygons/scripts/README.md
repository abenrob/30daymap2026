# Day 3 scripts

Four scripts, run in order from a working folder outside the repo. Each one reads what the previous one wrote.

```
01_fetch_bdtopo.py      IGN WFS  ->  bdtopo/tiles/*.json, bdtopo/arr.json
02_prep.py              bdtopo/tiles, bdtopo/arr.json  ->  bdtopo/bat.parquet, bdtopo/arr.parquet
03_export.py            bdtopo/*.parquet  ->  buildings/index.json, buildings/arr01.json ... arr20.json
04_make_animation.py    buildings/arrNN.json  ->  frames/*.png
```

Copy `buildings/` next to `index.html` to update the live page. `bdtopo/` and `frames/` are working files and stay out of the repo.

## Setup

Python 3.10 or later:

```
pip install geopandas shapely pyarrow pillow
```

`01` needs network access to `data.geopf.fr` and nothing else; no API key.

## What each step does

1. **Fetch.** Downloads every BD TOPO building over Paris from IGN's WFS. The service returns at most 5,000 features per request, so the Paris bounding box is cut into 225 small tiles that each stay under that limit. Also downloads the 20 arrondissement outlines. Re-running only fetches tiles that are missing.
2. **Prep.** Merges the tiles, removes buildings downloaded twice (they cross a tile edge), keeps buildings in service, and tags each one with the arrondissement that contains a point inside it.
3. **Export.** Writes one compact JSON file per arrondissement for the page: use, area, height, dwellings, the angle of the building's long side, and its outline as integer decimetres. Also writes `index.json` with the totals behind the Shares tab and the outlines for the picker map.
4. **Animation.** Renders the posted loop as PNG frames. It runs the same layout as the page's Sorted view, in Python. Pass the arrondissement number, and `1` as a second argument for the small-GIF version.

## Encoding the animation

```
# MP4 (frames rendered with the default antialiasing)
python 04_make_animation.py 4
ffmpeg -framerate 25 -i frames/%04d.png -c:v libx264 -pix_fmt yuv420p -crf 18 -movflags +faststart day03-4e.mp4

# GIF under 5 MB (frames rendered without antialiasing)
python 04_make_animation.py 4 1
ffmpeg -framerate 25 -i frames/%04d.png -vf "fps=20,palettegen=max_colors=32:stats_mode=full" pal.png
ffmpeg -framerate 25 -i frames/%04d.png -i pal.png -lavfi "fps=20[x];[x][1:v]paletteuse=dither=none:diff_mode=rectangle" -loop 0 day03-4e.gif
```

Antialiased edges add hundreds of in-between colours, which GIF compresses badly: the same loop is 13 MB with them and 4.2 MB without.

## Things that must stay in step

- The order of building uses: `TYPES` in `03_export.py`, `04_make_animation.py` and `index.html`. The files store a number, and that number picks the name and colour.
- The coordinate scheme: decimetres from each arrondissement's south-west corner, y pointing north. Both the page and `04` flip y for drawing.
