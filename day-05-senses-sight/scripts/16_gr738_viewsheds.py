"""gdal_viewshed at every frame position along the GR 738.

Eye 1.7 m above the 50 m DEM cell, target = the ground itself (-tz 0), Earth curvature with
standard refraction (-cc 0.85714), no maximum distance (the DEM crop is the limit).
Masks are kept bit-packed in one file so the frame step can add them up as it draws.

Run from the workspace root:  python3 site/day-05-senses-sight/scripts/16_gr738_viewsheds.py [--gdal PATH]
Output: work/data/day-05-sight/gr738/masks.npy (frames x rows x cols/8, uint8), stats.json
"""
import argparse, csv, json, os, subprocess, tempfile, time
import numpy as np
import rasterio

p = argparse.ArgumentParser()
p.add_argument("--gdal", default="gdal_viewshed")
a = p.parse_args()

G = "work/data/day-05-sight/gr738"
trail = list(csv.DictReader(open(f"{G}/trail.csv")))
with rasterio.open(f"{G}/dem_50m.tif") as src:
    z = src.read(1)
    T, res = src.transform, src.res[0]
H, W = z.shape
masks = np.lib.format.open_memmap(f"{G}/masks.npy", mode="w+", dtype=np.uint8,
                                  shape=(len(trail), H, (W + 7) // 8))
seen = np.zeros((H, W), bool)
stats, t0 = [], time.time()
with tempfile.TemporaryDirectory() as tmp:
    for r in trail:
        f = int(r["frame"])
        out = f"{tmp}/v.tif"
        subprocess.run([a.gdal, "-q", "-ox", r["x"], "-oy", r["y"], "-oz", "1.7", "-tz", "0",
                        "-cc", "0.85714", "-vv", "1", "-iv", "0", "-ov", "0",
                        f"{G}/dem_50m.tif", out], check=True)
        with rasterio.open(out) as v:
            # gdal writes only the window it computed; place it on the full grid
            m = np.zeros((H, W), bool)
            c0 = round((v.transform.c - T.c) / res)
            r0 = round((T.f - v.transform.f) / res)
            vv = v.read(1).astype(bool)
            m[r0:r0 + vv.shape[0], c0:c0 + vv.shape[1]] = vv
        masks[f] = np.packbits(m, axis=1)                   # 1 bit per cell: 900 frames in ~600 MB
        seen |= m
        col, row = ~T * (float(r["x"]), float(r["y"]))
        # ground = the 50 m cell gdal puts the observer on
        stats.append(dict(f=f, km=float(r["km"]), ground=round(float(z[int(row), int(col)])),
                          visible_km2=round(float(m.sum()) * res ** 2 / 1e6, 1),
                          seen_so_far_km2=round(float(seen.sum()) * res ** 2 / 1e6, 1)))
        if f % 100 == 0:
            print(stats[-1], f"{time.time() - t0:.0f} s")
masks.flush()
el = time.time() - t0
vk = [s["visible_km2"] for s in stats]
i_max, i_min = int(np.argmax(vk)), int(np.argmin(vk))
summary = dict(frames=len(stats), res_m=res, gdal_total_s=round(el, 1), per_frame_s=round(el / len(stats), 2),
               visible_km2_max=vk[i_max], max_at_km=stats[i_max]["km"], max_ground=stats[i_max]["ground"],
               visible_km2_min=vk[i_min], min_at_km=stats[i_min]["km"],
               visible_km2_median=float(np.median(vk)),
               seen_at_least_once_km2=stats[-1]["seen_so_far_km2"],
               crop_km2=round(H * W * res ** 2 / 1e6))
json.dump(dict(summary=summary, frames=stats), open(f"{G}/stats.json", "w"), indent=1)
print(json.dumps(summary, indent=1))
