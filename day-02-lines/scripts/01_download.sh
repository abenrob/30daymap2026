#!/usr/bin/env bash
# Day 2 raw downloads. Run from the workspace root; writes to work/data/day-02-lines/raw/.
# HydroSHEDS products: Lehner & Grill 2013 (HydroRIVERS, HydroBASINS), Messager et al. 2016 (HydroLAKES).
set -euo pipefail
RAW="${RAW:-work/data/day-02-lines/raw}"
mkdir -p "$RAW"
get() { [ -s "$RAW/$(basename "$1")" ] || curl -fL --retry 3 -o "$RAW/$(basename "$1")" "$1"; }
get https://data.hydrosheds.org/file/HydroRIVERS/HydroRIVERS_v10_eu_shp.zip
get https://data.hydrosheds.org/file/HydroBASINS/standard/hybas_eu_lev12_v1c.zip
get https://data.hydrosheds.org/file/hydrolakes/HydroLAKES_polys_v10_shp.zip
get https://naciscdn.org/naturalearth/10m/physical/ne_10m_ocean.zip
