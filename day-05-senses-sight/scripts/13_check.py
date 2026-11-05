"""Check the walking viewshed against gdal_viewshed at a few frames, curvature on in both.

1. blender -b -P site/day-05-senses-sight/scripts/11_walk_blender.py -- --check 60 300 540 [--step 2]
   (top-down orthographic, one pixel per DEM post, white = lit = visible)
2. python3 site/day-05-senses-sight/scripts/13_check.py --frames 60 300 540 [--step 2] [--gdal PATH]
   writes the same DEM posts as a GeoTIFF, runs
   gdal_viewshed -ox -oy (walker) -oz 1.7 -tz 0 -cc 0.85714 (no max distance), compares.
Ground cells only (-tz 0: can the eye see the ground itself), within 30 km of the walker so the
crop edge does not count. Output: work/data/day-05-sight/derived/walk_check.json
"""
import argparse, json, subprocess, time
import numpy as np
import rasterio
from rasterio.transform import from_origin
from PIL import Image

p = argparse.ArgumentParser()
p.add_argument("--frames", type=int, nargs="+", default=[60, 300, 540])
p.add_argument("--step", type=int, default=1)
p.add_argument("--gdal", default="gdal_viewshed")
a = p.parse_args()

D = "work/data/day-05-sight"
B = f"{D}/blender/walk"
meta = json.load(open(f"{B}/meta.json"))
trail = json.load(open(f"{B}/trail.json"))
z = np.load(f"{B}/dem.npy")[::a.step, ::a.step]
H, W = z.shape
res = meta["res"] * a.step
# grid whose cell centres are the mesh vertices
xmin = meta["xmin"] + meta["res"] / 2 - res / 2
ymax = meta["ymax"] - meta["res"] / 2 + res / 2
dem = f"{D}/renders/walk_check/dem_step{a.step}.tif"
with rasterio.open(dem, "w", driver="GTiff", width=W, height=H, count=1, dtype="float32",
                   crs="EPSG:2154", transform=from_origin(xmin, ymax, res, res)) as dst:
    dst.write(z, 1)

out = {}
for f in a.frames:
    fr = trail[f]
    g = f"{D}/renders/walk_check/gdal_{f:04d}.tif"
    t0 = time.time()
    subprocess.run([a.gdal, "-q", "-ox", str(fr["x93"]), "-oy", str(fr["y93"]), "-oz", str(meta["eye_m"]),
                    "-tz", "0", "-cc", "0.85714", "-vv", "255", "-iv", "0", "-ov", "0", dem, g], check=True)
    tg = time.time() - t0
    gg = rasterio.open(g).read(1) == 255
    bb = np.array(Image.open(f"{D}/renders/walk_check/blender_{f:04d}.png").convert("L"))
    # the ortho camera frames max(W, H) on the long side; crop the render to the grid
    bb = bb[(bb.shape[0] - H) // 2:(bb.shape[0] - H) // 2 + H, (bb.shape[1] - W) // 2:(bb.shape[1] - W) // 2 + W] > 127
    yy, xx = np.mgrid[0:H, 0:W]
    cx, cy = (fr["x93"] - xmin) / res - 0.5, (ymax - fr["y93"]) / res - 0.5
    disc = np.hypot(xx - cx, yy - cy) * res <= 30_000
    disc &= np.hypot(xx - cx, yy - cy) > 2             # skip the walker's own cells
    both, bo, go = (bb & gg & disc).sum(), (bb & ~gg & disc).sum(), (~bb & gg & disc).sum()
    out[f] = dict(km=fr["km"], gdal_s=round(tg, 2), visible_km2_blender=round((both + bo) * res ** 2 / 1e6, 1),
                  visible_km2_gdal=round((both + go) * res ** 2 / 1e6, 1),
                  agree_pct=round(100 * (1 - (bo + go) / disc.sum()), 2),
                  iou_visible=round(both / (both + bo + go), 3))
    print(f, out[f])
json.dump(dict(step=a.step, res_m=res, frames=out), open(f"{D}/derived/walk_check.json", "w"), indent=1)
