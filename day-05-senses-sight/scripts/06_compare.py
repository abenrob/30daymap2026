"""Turn per-turbine masks into "how many turbines can I see from here" rasters, and compare tools.

For each turbine: Blender PNG (800 x 800) and gdal_viewshed GeoTIFF (801 x 801) are placed on the
50 m grid, clipped to the same 20 km disc (pixel centre to observer cell centre), and summed.

Output (work/data/day-05-sight/derived/):
  count_blender.tif, count_gdal_cc<CC>.tif   uint16, turbines visible per 50 m cell (eye 1.7 m)
  compare_cc<CC>.json                         per-turbine and total agreement
Run from the workspace root:  python3 06_compare.py [--cc 0]
"""
import argparse, glob, json, os
import numpy as np
import rasterio
from PIL import Image

p = argparse.ArgumentParser()
p.add_argument("--cc", default="0")
a = p.parse_args()

D = "work/data/day-05-sight"
meta = json.load(open(f"{D}/blender/meta.json"))
turbines = json.load(open(f"{D}/blender/turbines.json"))
H, W, RES, R = meta["height"], meta["width"], meta["res"], meta["range_m"]
half = int(R / RES)

with rasterio.open(f"{D}/derived/dem_50m.tif") as src:
    prof = src.profile | dict(dtype="uint16", nodata=None, predictor=2)

cb = np.zeros((H, W), np.uint16)
cg = np.zeros((H, W), np.uint16)
yy, xx = np.mgrid[-half:half, -half:half]
disc = (xx ** 2 + yy ** 2) * RES ** 2 <= R ** 2
disc[half, half] = False                     # the observer's own cell
rows, tot = [], dict(both=0, blender_only=0, gdal_only=0, in_range=0)
for t in turbines:
    fb = f"{D}/renders/blender/{t['id']}.png"
    fg = f"{D}/renders/gdal_cc{a.cc}/{t['id']}.tif"
    if not (os.path.exists(fb) and os.path.exists(fg)):
        continue
    b = np.array(Image.open(fb)) > 127                         # rows r-400..r+399
    with rasterio.open(fg) as g:
        gg = g.read(1)
        gr = round((meta["ymax"] - g.transform.f) / RES)       # grid row of gdal's first row
        gc = round((g.transform.c - meta["xmin"]) / RES)
    r0, c0 = t["row"] - half, t["col"] - half
    g = np.zeros((2 * half, 2 * half), bool)
    # copy gdal's window onto the same 800 x 800 window as Blender's
    rs, cs = max(r0, gr), max(c0, gc)
    re, ce = min(r0 + 2 * half, gr + gg.shape[0]), min(c0 + 2 * half, gc + gg.shape[1])
    g[rs - r0:re - r0, cs - c0:ce - c0] = gg[rs - gr:re - gr, cs - gc:ce - gc] == 255
    b &= disc
    g &= disc
    # clip to the grid (windows never leave it with a 20 km margin, but be safe)
    rr0, cc0 = max(r0, 0), max(c0, 0)
    rr1, cc1 = min(r0 + 2 * half, H), min(c0 + 2 * half, W)
    sl = np.s_[rr0 - r0:rr1 - r0, cc0 - c0:cc1 - c0]
    cb[rr0:rr1, cc0:cc1] += b[sl]
    cg[rr0:rr1, cc0:cc1] += g[sl]
    s = dict(id=t["id"], both=int((b & g).sum()), blender_only=int((b & ~g).sum()),
             gdal_only=int((~b & g).sum()), in_range=int(disc.sum()))
    s["agree_pct"] = round(100 * (1 - (s["blender_only"] + s["gdal_only"]) / s["in_range"]), 2)
    s["visible_km2_blender"] = round((s["both"] + s["blender_only"]) * RES ** 2 / 1e6, 1)
    s["visible_km2_gdal"] = round((s["both"] + s["gdal_only"]) * RES ** 2 / 1e6, 1)
    rows.append(s)
    for k in tot:
        tot[k] += s[k]

with rasterio.open(f"{D}/derived/count_blender.tif", "w", **prof) as dst:
    dst.write(cb, 1)
with rasterio.open(f"{D}/derived/count_gdal_cc{a.cc}.tif", "w", **prof) as dst:
    dst.write(cg, 1)

tot["agree_pct"] = round(100 * (1 - (tot["blender_only"] + tot["gdal_only"]) / tot["in_range"]), 3)
same_count = float((cb == cg).mean() * 100)
land = (cb > 0) | (cg > 0)
summary = dict(n=len(rows), cc=a.cc, total=tot,
               count_cells_identical_pct=round(same_count, 2),
               count_cells_identical_where_any_visible_pct=round(float((cb == cg)[land].mean() * 100), 2),
               mean_abs_count_diff_where_any=round(float(np.abs(cb.astype(int) - cg)[land].mean()), 3),
               max_count_blender=int(cb.max()), max_count_gdal=int(cg.max()),
               area_any_visible_km2_blender=round(float((cb > 0).sum() * RES ** 2 / 1e6)),
               area_any_visible_km2_gdal=round(float((cg > 0).sum() * RES ** 2 / 1e6)),
               worst=sorted(rows, key=lambda s: s["agree_pct"])[:5])
json.dump(dict(summary=summary, turbines=rows), open(f"{D}/derived/compare_cc{a.cc}.json", "w"), indent=1)
print(json.dumps(summary, indent=1))
