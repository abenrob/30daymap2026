#!/usr/bin/env bash
# Copernicus DEM GLO-30 tiles (1 x 1 degree COGs, public AWS bucket, no credentials)
# covering the Rhone basin bbox (lon 3.6 to 8.5, lat 43.4 to 48.2).
# Writes to work/data/day-02-lines/raw/glo30/. Tiles that are all sea do not exist; 404s are skipped.
set -uo pipefail
OUT="${OUT:-work/data/day-02-lines/raw/glo30}"
mkdir -p "$OUT"
for lat in 43 44 45 46 47 48; do
  for lon in 003 004 005 006 007 008; do
    n="Copernicus_DSM_COG_10_N${lat}_00_E${lon}_00_DEM"
    echo "https://copernicus-dem-30m.s3.amazonaws.com/${n}/${n}.tif"
  done
done | xargs -P 8 -I{} sh -c 'f="$0/$(basename {})"; [ -s "$f" ] || curl -sf --retry 3 -o "$f" {} || echo "missing {}"' "$OUT"
ls "$OUT" | wc -l
