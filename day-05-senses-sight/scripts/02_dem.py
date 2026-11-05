"""Bare-earth DEM for the turbines' 20 km surroundings, from IGN (Geoplateforme WMS-R, RGE ALTI based).

Output (work/data/day-05-sight/derived/):
  dem_25m.tif   25 m, EPSG:2154, float32 (source grid for the 50 m version and close-ups)
  dem_50m.tif   50 m, average of 2 x 2 (the grid both Blender and gdal_viewshed use)
  aoi.json      extent, resolution, range

Extent = bbox of all turbines + RANGE_M, snapped to 100 m.
IGN serves ELEVATION.ELEVATIONGRIDCOVERAGE as float32 GeoTIFF straight from GetMap,
so no tile download or mosaicking: 2,000 x 2,000 px requests, written into one file.
Bare earth (DTM) on purpose: forests and buildings do not block the view, which is the
convention for a zone of theoretical visibility (ZTV) and keeps it comparable with gdal_viewshed.
"""
import csv, json, math, time, io, urllib.request
import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.windows import Window
from rasterio.enums import Resampling

D = "work/data/day-05-sight"
RANGE_M = 20_000
RES = 25
CHUNK = 2000
URL = ("https://data.geopf.fr/wms-r?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap"
       "&LAYERS=ELEVATION.ELEVATIONGRIDCOVERAGE&STYLES=&CRS=EPSG:2154&FORMAT=image/geotiff"
       "&BBOX={x0},{y0},{x1},{y1}&WIDTH={w}&HEIGHT={h}")

t = list(csv.DictReader(open(f"{D}/derived/turbines.csv")))
xs, ys = [float(r["x"]) for r in t], [float(r["y"]) for r in t]
snap = lambda v, f: f(v / 100) * 100
xmin, ymin = snap(min(xs) - RANGE_M, math.floor), snap(min(ys) - RANGE_M, math.floor)
xmax, ymax = snap(max(xs) + RANGE_M, math.ceil), snap(max(ys) + RANGE_M, math.ceil)
W, H = int((xmax - xmin) / RES), int((ymax - ymin) / RES)
print(f"extent {xmin:.0f},{ymin:.0f} to {xmax:.0f},{ymax:.0f}: {W} x {H} px at {RES} m")

prof = dict(driver="GTiff", width=W, height=H, count=1, dtype="float32", crs="EPSG:2154",
            transform=from_origin(xmin, ymax, RES, RES), nodata=-99999, compress="deflate",
            predictor=3, tiled=True, blockxsize=512, blockysize=512)
t0 = time.time()
with rasterio.open(f"{D}/derived/dem_25m.tif", "w", **prof) as dst:
    for row in range(0, H, CHUNK):
        for col in range(0, W, CHUNK):
            w, h = min(CHUNK, W - col), min(CHUNK, H - row)
            x0, y1 = xmin + col * RES, ymax - row * RES
            url = URL.format(x0=x0, y0=y1 - h * RES, x1=x0 + w * RES, y1=y1, w=w, h=h)
            for attempt in range(4):
                try:
                    data = urllib.request.urlopen(url, timeout=120).read()
                    break
                except Exception as e:
                    print("retry", e); time.sleep(5)
            with rasterio.MemoryFile(data) as mf, mf.open() as src:
                a = src.read(1)
            dst.write(a, 1, window=Window(col, row, w, h))
            print(f"  tile {row},{col} {a.min():.0f} to {a.max():.0f} m")
print(f"download {time.time() - t0:.0f} s")

with rasterio.open(f"{D}/derived/dem_25m.tif") as src:
    a = src.read(1)
    assert (a > -1000).all(), "nodata in DEM"
    b = a.reshape(H // 2, 2, W // 2, 2).mean(axis=(1, 3)).astype("float32")
    p = src.profile | dict(width=W // 2, height=H // 2, transform=from_origin(xmin, ymax, 50, 50))
    with rasterio.open(f"{D}/derived/dem_50m.tif", "w", **p) as dst:
        dst.write(b, 1)
print(f"dem_50m: {W // 2} x {H // 2}, z {b.min():.0f} to {b.max():.0f} m")
json.dump(dict(crs="EPSG:2154", xmin=xmin, ymin=ymin, xmax=xmax, ymax=ymax, range_m=RANGE_M,
               eye_m=1.7, z_min=float(b.min()), z_max=float(b.max())),
          open(f"{D}/derived/aoi.json", "w"), indent=1)
