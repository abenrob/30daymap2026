"""Hand the DEM and the turbines to Blender in a form its bundled Python can read (numpy only).

Output (work/data/day-05-sight/blender/):
  dem_50m.npy     float32 heights, row 0 = north, pixel centres on the 50 m grid
  turbines.json   per turbine: grid row/col of its cell, light position in scene metres
  meta.json       origin (scene 0,0 in EPSG:2154), resolution, grid size, range, eye height

Observer position follows gdal_viewshed so both tools answer the same question:
the light sits at the centre of the DEM cell holding the turbine, at DEM(cell) + tip height.
Scene coordinates: 1 unit = 1 m, origin at the AOI centre (keeps float32 precise to mm).
"""
import csv, json, os
import numpy as np
import rasterio

D = "work/data/day-05-sight"
OUT = f"{D}/blender"
os.makedirs(OUT, exist_ok=True)
aoi = json.load(open(f"{D}/derived/aoi.json"))

with rasterio.open(f"{D}/derived/dem_50m.tif") as src:
    z = src.read(1).astype("float32")
    T, res = src.transform, src.res[0]
H, W = z.shape
ox = (aoi["xmin"] + aoi["xmax"]) / 2
oy = (aoi["ymin"] + aoi["ymax"]) / 2
np.save(f"{OUT}/dem_50m.npy", z)

turbines = []
for r in csv.DictReader(open(f"{D}/derived/turbines.csv")):
    col, row = ~T * (float(r["x"]), float(r["y"]))
    row, col = int(row), int(col)
    cx, cy = T * (col + 0.5, row + 0.5)
    ground = float(z[row, col])
    turbines.append(dict(id=int(r["id"]), row=row, col=col, tip_m=float(r["tip_m"]),
                         x=cx, y=cy, ground=ground,
                         light=[cx - ox, cy - oy, ground + float(r["tip_m"])]))
json.dump(turbines, open(f"{OUT}/turbines.json", "w"))
json.dump(dict(origin=[ox, oy], xmin=aoi["xmin"], ymax=aoi["ymax"], res=res, width=W, height=H,
               range_m=aoi["range_m"], eye_m=aoi["eye_m"]),
          open(f"{OUT}/meta.json", "w"), indent=1)
print(f"{W} x {H} grid, {len(turbines)} turbines, origin {ox:.0f}, {oy:.0f}")
