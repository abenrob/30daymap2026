"""A walker on the GR 7 over the Mézenc massif: the trail, cut and resampled one point per frame,
and a 25 m DEM crop around it, ready for Blender.

Input : work/data/day-05-sight/raw/gr7_rel.json, gr7_ways.json  (Overpass, relation 11866788,
        "GR 7 Des Vosges aux Pyrénées 03", ways clipped to 44.6,3.9,45.1,4.5; see README)
        work/data/day-05-sight/derived/dem_25m.tif               (from 02_dem.py)
Output: work/data/day-05-sight/blender/walk/
          dem.npy        float32 heights of the crop, row 0 = north
          trail.json     per frame: x, y (scene m), ground z, eye z, km along the GR
          meta.json      crop extent, origin, resolution, frames

Section: KM_FROM to KM_TO along the relation as OSM orders it (north to south here):
the climb from the Loire valley side onto the Mézenc ridge (about 1,550 m) and down towards
the Gerbier de Jonc. Ground z is the height of the SAME triangle Blender renders (the mesh is
triangulated here, not by Blender), so the eye is exactly 1.7 m above the rendered surface.
"""
import json, os
import numpy as np
import rasterio
from pyproj import Transformer

D = "work/data/day-05-sight"
OUT = f"{D}/blender/walk"
KM_FROM, KM_TO = 34.0, 60.0
FRAMES = 600                      # 20 s at 30 fps
PAD = 40_000                      # terrain kept around the section, m (clipped to the DEM)
EYE = 1.7

rel = json.load(open(f"{D}/raw/gr7_rel.json"))["elements"][0]
ways = {e["id"]: e for e in json.load(open(f"{D}/raw/gr7_ways.json"))["elements"]}
line = []
for m in rel["members"]:
    if m["type"] != "way" or m["ref"] not in ways:
        continue
    pts = [(p["lon"], p["lat"]) for p in ways[m["ref"]]["geometry"]]
    if line:
        d2 = lambda a, b: (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
        if d2(line[-1], pts[-1]) < d2(line[-1], pts[0]):
            pts = pts[::-1]
        pts = pts[1:] if d2(line[-1], pts[0]) < 1e-10 else pts
    line += pts
to93 = Transformer.from_crs(4326, 2154, always_xy=True)
xy = np.array([to93.transform(*p) for p in line])
km = np.r_[0, np.cumsum(np.hypot(*np.diff(xy, axis=0).T))] / 1e3
s = np.linspace(KM_FROM, KM_TO, FRAMES)
fx, fy = np.interp(s, km, xy[:, 0]), np.interp(s, km, xy[:, 1])
# light smoothing so the walker does not jitter on OSM zigzags (moving average over ~150 m)
k = 5
fx = np.convolve(np.pad(fx, k, mode="edge"), np.ones(2 * k + 1) / (2 * k + 1), "valid")
fy = np.convolve(np.pad(fy, k, mode="edge"), np.ones(2 * k + 1) / (2 * k + 1), "valid")

with rasterio.open(f"{D}/derived/dem_25m.tif") as src:
    RES = src.res[0]
    T = src.transform
    c0, r0 = ~T * (fx.min() - PAD, fy.max() + PAD)
    c1, r1 = ~T * (fx.max() + PAD, fy.min() - PAD)
    c0, r0 = max(int(c0), 0), max(int(r0), 0)
    c1, r1 = min(int(c1), src.width), min(int(r1), src.height)
    z = src.read(1, window=((r0, r1), (c0, c1))).astype("float32")
    xmin, ymax = T * (c0, r0)
H, W = z.shape
ox, oy = xmin + W * RES / 2, ymax - H * RES / 2

def ground(x, y):
    """Height of the rendered triangle under (x, y). Vertices sit at pixel centres; each quad
    (a top-left, b top-right, c bottom-right, d bottom-left) is split along a-c."""
    cf = (x - xmin) / RES - 0.5
    rf = (ymax - y) / RES - 0.5
    j, i = int(np.floor(cf)), int(np.floor(rf))
    u, v = cf - j, rf - i                     # u east, v south, 0..1 inside the quad
    za, zb, zc, zd = z[i, j], z[i, j + 1], z[i + 1, j + 1], z[i + 1, j]
    if u >= v:                                # triangle a, b, c
        return za + u * (zb - za) + v * (zc - zb)
    return za + v * (zd - za) + u * (zc - zd)   # triangle a, c, d

frames = []
for f, (x, y, kk) in enumerate(zip(fx, fy, s)):
    g = float(ground(x, y))
    frames.append(dict(f=f, x=float(x - ox), y=float(y - oy), ground=g, eye=g + EYE,
                       km=round(float(kk), 3), x93=float(x), y93=float(y)))
os.makedirs(OUT, exist_ok=True)
np.save(f"{OUT}/dem.npy", z)
json.dump(frames, open(f"{OUT}/trail.json", "w"))
json.dump(dict(crs="EPSG:2154", xmin=xmin, ymax=ymax, res=RES, width=W, height=H, origin=[ox, oy],
               km_from=KM_FROM, km_to=KM_TO, frames=FRAMES, eye_m=EYE, gr_relation=rel["id"],
               gr_name=rel["tags"].get("name")), open(f"{OUT}/meta.json", "w"), indent=1)
zz = [fr["ground"] for fr in frames]
print(f"section {KM_TO - KM_FROM:.1f} km, {FRAMES} frames ({1000 * (KM_TO - KM_FROM) / FRAMES:.0f} m each), "
      f"ground {min(zz):.0f} to {max(zz):.0f} m; crop {W} x {H} at {RES:.0f} m "
      f"({W * RES / 1e3:.0f} x {H * RES / 1e3:.0f} km)")
