"""Where Blender and gdal_viewshed disagree, who is right? Brute-force line of sight as referee.

For a random sample of cells in each class (both visible, both hidden, Blender only, GDAL only),
walk the straight line from the turbine tip to the eye (1.7 m) in 1/10-pixel steps (5 m) over the
DEM interpolated bilinearly between pixel centres, and call it visible if nothing pokes above the
line. Bilinear is one reasonable surface between DEM posts; Blender's quads (split into two
triangles) and GDAL's algorithm are two others, so "right" means "agrees with exact LOS on a
bilinear surface", no more.
Output: work/data/day-05-sight/derived/los_check.json
"""
import json
import numpy as np
import rasterio
from PIL import Image

D = "work/data/day-05-sight"
meta = json.load(open(f"{D}/blender/meta.json"))
T = json.load(open(f"{D}/blender/turbines.json"))
z = np.load(f"{D}/blender/dem_50m.npy")
RES, R = meta["res"], meta["range_m"]
half = int(R / RES)
N_TURB, N_PX, STEP = 40, 150, 0.1
rng = np.random.default_rng(0)

def zb(r, c):
    r0, c0 = np.floor(r).astype(int), np.floor(c).astype(int)
    fr, fc = r - r0, c - c0
    return (z[r0, c0] * (1 - fr) * (1 - fc) + z[r0, c0 + 1] * (1 - fr) * fc
            + z[r0 + 1, c0] * fr * (1 - fc) + z[r0 + 1, c0 + 1] * fr * fc)

def los(t, R_, C_):
    zo = z[t["row"], t["col"]] + t["tip_m"]
    zt = z[R_, C_] + meta["eye_m"]
    n = int(max(abs(R_ - t["row"]), abs(C_ - t["col"])) / STEP)
    s = np.linspace(0, 1, n)[1:-1]
    rr, cc = t["row"] + (R_ - t["row"]) * s, t["col"] + (C_ - t["col"]) * s
    return not np.any(zb(rr, cc) > zo + (zt - zo) * s)

yy, xx = np.mgrid[-half:half, -half:half]
disc = (xx ** 2 + yy ** 2) * RES ** 2 <= R ** 2
disc[half, half] = False
res = {k: [0, 0] for k in ("both_visible", "both_hidden", "blender_only", "gdal_only")}
for t in rng.choice(T, N_TURB, replace=False):
    b = np.array(Image.open(f"{D}/renders/blender/{t['id']}.png")) > 127
    with rasterio.open(f"{D}/renders/gdal_cc0/{t['id']}.tif") as g:
        gg = g.read(1)[:2 * half, :2 * half] == 255   # gdal window starts at the same corner
    for k, m in (("both_visible", b & gg), ("both_hidden", ~b & ~gg),
                 ("blender_only", b & ~gg), ("gdal_only", ~b & gg)):
        idx = np.argwhere(m & disc)
        if not len(idx):
            continue
        idx = idx[rng.choice(len(idx), min(N_PX, len(idx)), replace=False)]
        v = [los(t, t["row"] - half + i, t["col"] - half + j) for i, j in idx]
        res[k][0] += len(v)
        res[k][1] += sum(v)
out = {k: dict(sampled=n, exact_says_visible_pct=round(100 * v / n, 1)) for k, (n, v) in res.items()}
json.dump(out, open(f"{D}/derived/los_check.json", "w"), indent=1)
print(json.dumps(out, indent=1))
