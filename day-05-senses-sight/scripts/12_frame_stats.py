"""Ground in sight per frame, for the video's caption: gdal_viewshed at every walker position
(eye 1.7 m, target = the ground, curvature + refraction 0.85714, no max distance), on the same
DEM posts Blender renders. Also the cumulative footprint: every cell seen at least once.

Run from the workspace root (after 13_check.py has written the DEM, or it is written here):
  python3 site/day-05-senses-sight/scripts/12_frame_stats.py [--step 2] [--gdal PATH]
Output: work/data/day-05-sight/derived/walk_stats.json, walk_cumulative.tif (frames seeing each cell)
"""
import argparse, json, os, subprocess, tempfile, time
import numpy as np
import rasterio
from rasterio.transform import from_origin

p = argparse.ArgumentParser()
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
xmin = meta["xmin"] + meta["res"] / 2 - res / 2
ymax = meta["ymax"] - meta["res"] / 2 + res / 2
prof = dict(driver="GTiff", width=W, height=H, count=1, crs="EPSG:2154",
            transform=from_origin(xmin, ymax, res, res))
os.makedirs(f"{D}/renders/walk_check", exist_ok=True)
dem = f"{D}/renders/walk_check/dem_step{a.step}.tif"
with rasterio.open(dem, "w", dtype="float32", **prof) as dst:
    dst.write(z, 1)

cum = np.zeros((H, W), np.uint16)
stats, t0 = [], time.time()
with tempfile.TemporaryDirectory() as tmp:
    for fr in trail:
        out = f"{tmp}/v.tif"
        subprocess.run([a.gdal, "-q", "-ox", str(fr["x93"]), "-oy", str(fr["y93"]), "-oz", str(meta["eye_m"]),
                        "-tz", "0", "-cc", "0.85714", "-vv", "1", "-iv", "0", "-ov", "0", dem, out], check=True)
        with rasterio.open(out) as src:
            v = src.read(1).astype(bool)
            # gdal writes only the window it computed; place it on the grid
            c0 = round((src.transform.c - xmin) / res)
            r0 = round((ymax - src.transform.f) / res)
        cum[r0:r0 + v.shape[0], c0:c0 + v.shape[1]] += v
        stats.append(dict(f=fr["f"], km=fr["km"], ground=round(fr["ground"]),
                          visible_km2=round(float(v.sum()) * res ** 2 / 1e6, 2),
                          seen_so_far_km2=round(float((cum > 0).sum()) * res ** 2 / 1e6, 1)))
        if fr["f"] % 100 == 0:
            print(stats[-1])
el = time.time() - t0
with rasterio.open(f"{D}/derived/walk_cumulative.tif", "w", dtype="uint16", **prof) as dst:
    dst.write(cum, 1)
vk = [s["visible_km2"] for s in stats]
summary = dict(step=a.step, res_m=res, frames=len(stats), gdal_total_s=round(el, 1),
               visible_km2_min=min(vk), visible_km2_max=max(vk),
               max_at_km=stats[int(np.argmax(vk))]["km"], min_at_km=stats[int(np.argmin(vk))]["km"],
               seen_at_least_once_km2=stats[-1]["seen_so_far_km2"])
json.dump(dict(summary=summary, frames=stats), open(f"{D}/derived/walk_stats.json", "w"), indent=1)
print(json.dumps(summary, indent=1))
