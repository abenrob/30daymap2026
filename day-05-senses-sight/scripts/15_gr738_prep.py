"""GR 738, Haute Traversée de Belledonne (Aiguebelle to Vizille): the trail as one line, resampled
one point per video frame, and an IGN DEM around it.

Input : work/data/day-05-sight/raw/gr738.json
        Overpass: the 11 stage relations (route=hiking, ref GR 738, "La Haute Traversée de
        Belledonne - Etape 1..11"), their bodies and member ways with geometry; query in README.
Output: work/data/day-05-sight/gr738/
          trail.csv      frame, x, y (EPSG:2154), km
          trail_full.csv the chained OSM line (for drawing)
          dem_25m.tif    IGN RGE ALTI (Géoplateforme WMS-R, float32), trail bbox + PAD
          dem_50m.tif    2 x 2 average, the grid gdal_viewshed runs on
"""
import csv, json, math, os, re, time, urllib.request
import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.windows import Window
from pyproj import Transformer

D = "work/data/day-05-sight"
OUT = f"{D}/gr738"
FRAMES = 900                      # 30 s at 30 fps
PAD = 35_000
URL = ("https://data.geopf.fr/wms-r?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap"
       "&LAYERS=ELEVATION.ELEVATIONGRIDCOVERAGE&STYLES=&CRS=EPSG:2154&FORMAT=image/geotiff"
       "&BBOX={x0},{y0},{x1},{y1}&WIDTH={w}&HEIGHT={h}")
os.makedirs(OUT, exist_ok=True)

# --- trail: stages in order, ways chained, flipped where needed ------------------------------
els = json.load(open(f"{D}/raw/gr738.json"))["elements"]
rels = sorted([e for e in els if e["type"] == "relation"],
              key=lambda e: int(re.search(r"Etape (\d+)", e["tags"]["name"]).group(1)))
ways = {e["id"]: e for e in els if e["type"] == "way"}
line = []
for r in rels:
    for m in r["members"]:
        if m["type"] != "way":
            continue
        pts = [(p["lon"], p["lat"]) for p in ways[m["ref"]]["geometry"]]
        if line:                                   # flip the way if its far end touches the line
            d2 = lambda a, b: (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
            if d2(line[-1], pts[-1]) < d2(line[-1], pts[0]):
                pts = pts[::-1]
            if d2(line[-1], pts[0]) < 1e-12:
                pts = pts[1:]
        line += pts
to93 = Transformer.from_crs(4326, 2154, always_xy=True)
xy = np.array([to93.transform(*p) for p in line])
km = np.r_[0, np.cumsum(np.hypot(*np.diff(xy, axis=0).T))] / 1e3
s = np.linspace(0, km[-1], FRAMES)
fx, fy = np.interp(s, km, xy[:, 0]), np.interp(s, km, xy[:, 1])
with open(f"{OUT}/trail.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["frame", "x", "y", "km"])
    for i, (a, b, k) in enumerate(zip(fx, fy, s)):
        w.writerow([i, round(a, 1), round(b, 1), round(k, 3)])
with open(f"{OUT}/trail_full.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["x", "y", "km"])
    for (a, b), k in zip(xy, km):
        w.writerow([round(a, 1), round(b, 1), round(k, 3)])
print(f"{len(rels)} stages, {len(line)} vertices, {km[-1]:.1f} km, {FRAMES} frames ({1000 * km[-1] / FRAMES:.0f} m each)")

# --- DEM: trail bbox + PAD, 25 m from IGN, then 50 m ------------------------------------------
RES, CH = 25, 2000
snap = lambda v, f: f(v / 100) * 100
xmin, ymin = snap(xy[:, 0].min() - PAD, math.floor), snap(xy[:, 1].min() - PAD, math.floor)
xmax, ymax = snap(xy[:, 0].max() + PAD, math.ceil), snap(xy[:, 1].max() + PAD, math.ceil)
W, H = int((xmax - xmin) / RES), int((ymax - ymin) / RES)
W, H = W - W % 2, H - H % 2                        # even, for the 2 x 2 average to 50 m
prof = dict(driver="GTiff", width=W, height=H, count=1, dtype="float32", crs="EPSG:2154",
            transform=from_origin(xmin, ymax, RES, RES), nodata=-99999, compress="deflate",
            predictor=3, tiled=True, blockxsize=512, blockysize=512)
t0 = time.time()
with rasterio.open(f"{OUT}/dem_25m.tif", "w", **prof) as dst:
    for row in range(0, H, CH):
        for col in range(0, W, CH):
            w_, h_ = min(CH, W - col), min(CH, H - row)
            x0, y1 = xmin + col * RES, ymax - row * RES
            url = URL.format(x0=x0, y0=y1 - h_ * RES, x1=x0 + w_ * RES, y1=y1, w=w_, h=h_)
            for attempt in range(4):
                try:
                    data = urllib.request.urlopen(url, timeout=120).read()
                    break
                except Exception as e:
                    print("retry", e); time.sleep(5)    # the WMS times out now and then
            with rasterio.MemoryFile(data) as mf, mf.open() as src:
                dst.write(src.read(1), 1, window=Window(col, row, w_, h_))
print(f"DEM {W} x {H} at 25 m ({W * RES / 1e3:.0f} x {H * RES / 1e3:.0f} km), {time.time() - t0:.0f} s")
with rasterio.open(f"{OUT}/dem_25m.tif") as src:
    a = src.read(1)
    assert (a > -1000).all(), "nodata in DEM (outside France?)"
    b = a.reshape(H // 2, 2, W // 2, 2).mean(axis=(1, 3)).astype("float32")
    with rasterio.open(f"{OUT}/dem_50m.tif", "w", **(src.profile | dict(width=W // 2, height=H // 2,
                       transform=from_origin(xmin, ymax, 50, 50)))) as dst:
        dst.write(b, 1)
print(f"dem_50m {W // 2} x {H // 2}, z {b.min():.0f} to {b.max():.0f} m")
