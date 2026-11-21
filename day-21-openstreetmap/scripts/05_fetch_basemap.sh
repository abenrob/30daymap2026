#!/bin/bash
# Basemap inputs:
#   - SRTM3 elevation from IGN Géoplateforme (WMS-R layer ELEVATION.ELEVATIONGRIDCOVERAGE.SRTM3, raw float32 BIL),
#     4 tiles of 1600 x 1300 px over lon 5.3–10.5, lat 45.2–48.1
#   - Natural Earth 10m lakes, rivers and countries (GeoJSON from the natural-earth-vector repo)
#   - DM Serif Display and Inter from the google/fonts repo
set -euo pipefail
DATA="${OSC_WORK:-$(cd "$(dirname "$0")/../../../work/day-21-openstreetmap" && pwd)}/data"
mkdir -p "$DATA/basemap" "$DATA/fonts"; cd "$DATA"

LONS=(5.3 7.9 10.5); LATS=(45.2 46.65 48.1)    # tile i = west->east, j = south->north
for i in 0 1; do for j in 0 1; do
  BBOX="${LATS[$j]},${LONS[$i]},${LATS[$((j+1))]},${LONS[$((i+1))]}"   # WMS 1.3.0 + EPSG:4326 = lat,lon order
  curl -sS -m 170 -o "basemap/srtm3_${i}_${j}.bil" \
    "https://data.geopf.fr/wms-r/wms?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=ELEVATION.ELEVATIONGRIDCOVERAGE.SRTM3&STYLES=&CRS=EPSG:4326&BBOX=${BBOX}&WIDTH=1600&HEIGHT=1300&FORMAT=image/x-bil;bits=32"
  echo "dem tile $i $j"
done; done

NE=https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson
for f in ne_10m_admin_0_countries ne_10m_lakes ne_10m_lakes_europe ne_10m_rivers_lake_centerlines ne_10m_rivers_europe; do
  curl -sS -m 170 -o "basemap/$f.geojson" "$NE/$f.geojson"; echo "$f"
done

GF=https://raw.githubusercontent.com/google/fonts/main/ofl
curl -sS -m 60 -o fonts/DMSerifDisplay-Regular.ttf "$GF/dmserifdisplay/DMSerifDisplay-Regular.ttf"
curl -sS -m 60 -o fonts/DMSerifDisplay-Italic.ttf "$GF/dmserifdisplay/DMSerifDisplay-Italic.ttf"
curl -sS -m 60 -o fonts/Inter.ttf "$GF/inter/Inter%5Bopsz,wght%5D.ttf"
