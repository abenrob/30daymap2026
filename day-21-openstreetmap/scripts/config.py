"""Shared paths, frame layout, projection and colours for Day 21 (Open Street Cheese).

Data and renders live outside the repo, in work/day-21-openstreetmap (override with OSC_WORK).
"""
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DAY = os.path.dirname(HERE)                                   # site/day-21-openstreetmap
WORK = os.environ.get('OSC_WORK', os.path.normpath(os.path.join(DAY, '..', '..', 'work', 'day-21-openstreetmap')))
DATA = os.path.join(WORK, 'data')                             # Overpass dumps, DEM, Natural Earth, fonts
RENDERS = os.path.join(WORK, 'renders')
FONTS = os.path.join(DATA, 'fonts')
INAO_SHP = os.path.join(WORK, '..', 'day-19-senses-smell', 'data', 'raw', '2026-11-09_delim-aire-geographique-shp.shp')

MACHINES = os.path.join(WORK, 'cheese_vending.geojson')       # 02_machines.py
ZONES = os.path.join(WORK, 'aop_cheese_zones.geojson')        # 03_build_zones.py
JOINED = os.path.join(WORK, 'cheese_vending_aop.geojson')     # 04_join.py
BASE_MAP = os.path.join(WORK, 'base_map.png')                 # 06_render_base.py

# Study box for the Overpass queries (south, west, north, east)
BBOX = (45.0, 5.5, 47.9, 10.6)

# ---- 4:5 frame (1080 x 1350): header, map, footer
W, H = 1080, 1350
HEADER = 336                                                  # title block + current cheese
LON0, LON1, LAT0, LAT1 = 5.45, 10.35, 45.33, 47.95            # map extent
K = math.cos(math.radians(46.65))                             # x scale of the equirectangular map at mid-latitude
MAP_W = W
MAP_H = round(W * (LAT1 - LAT0) / ((LON1 - LON0) * K))        # 841 px
MAP_Y = HEADER
FOOTER_Y = MAP_Y + MAP_H


def xy(lon, lat, s=1.0):
    """Lon/lat to pixels in the map panel (origin top-left); s supersamples for the basemap render."""
    x = (lon - LON0) / (LON1 - LON0) * MAP_W
    y = (LAT1 - lat) / (LAT1 - LAT0) * MAP_H
    return x * s, y * s


COL = dict(paper='#f4eedf', ink='#2b2620', muted='#7a6f60', rule='#b5a993', accent='#d9a521')
