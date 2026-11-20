"""
Numbers and geometry behind the carousel -> story.json

  python story.py   (needs world.json from hexagonity.py + anchored.py)

* coast vs land runs along France's mainland border (a border segment is
  "land" when another Natural Earth country lies within 0.03 deg)
* the textbook hexagon: Pointe Saint-Mathieu, Dunkerque, Lauterbourg,
  Menton, Cerbère, Hendaye
* the smallest convex hexagon containing the whole mainland outline
* the best-fitting convex hexagon with corners on the border (anchored.py)
* coverage, spill and per-side purity for both hexagons
"""
import json
import numpy as np
import shapefile
from pyproj import Transformer
from scipy.optimize import minimize
from shapely.geometry import shape, Polygon, Point, LineString
from shapely.ops import unary_union

CLASSIC = {"Pointe Saint-Mathieu": (-4.77, 48.33), "Dunkerque": (2.37, 51.03),
           "Lauterbourg": (8.23, 48.97), "Menton": (7.50, 43.78),
           "Cerbère": (3.17, 42.44), "Hendaye": (-1.78, 43.36)}

rd = shapefile.Reader("data/naturalearth_lowres.shp")
geoms = {rec["name"]: shape(s.__geo_interface__) for s, rec in zip(rd.shapes(), rd.records())}
fr = geoms["France"]
fr_main = max(fr.geoms, key=lambda g: g.area) if fr.geom_type == "MultiPolygon" else fr
others = unary_union([g for n, g in geoms.items() if n != "France"])

# coast / land runs
ring = list(fr_main.exterior.coords)
runs = []
for a, b in zip(ring[:-1], ring[1:]):
    t = "land" if others.distance(Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)) < 0.03 else "sea"
    if runs and runs[-1][0] == t:
        runs[-1][1].append(b)
    else:
        runs.append([t, [a, b]])
if len(runs) > 1 and runs[0][0] == runs[-1][0]:
    runs[0][1] = runs[-1][1][:-1] + runs[0][1]; runs.pop()

# same normalised frame as world.json (local LAEA, unit area)
r = next(x for x in json.load(open("world.json")) if x["name"] == "France"); m = r["meta"]
fwd = Transformer.from_crs("EPSG:4326", f"+proj=laea +lat_0={m['lat0']} +lon_0={m['lon0']} +datum=WGS84",
                           always_xy=True)
def N(lon, lat):
    x, y = fwd.transform(lon, lat)
    return [float((x - m["cx"]) * m["scale"]), float((y - m["cy"]) * m["scale"])]
country = Polygon(r["country"])
classic = [N(*v) for v in CLASSIC.values()]

# smallest convex hexagon containing the outline
hull = country.convex_hull
def obj(x):
    p = Polygon(x.reshape(-1, 2))
    if not p.is_valid or abs(p.convex_hull.area - p.area) > 1e-9:
        return 1e3
    return p.area + 400 * hull.difference(p).area
hv = np.array(hull.exterior.coords[:-1])
seeds = [np.array(classic).ravel()] + [
    (hv[np.sort(np.random.default_rng(s).choice(len(hv), 6, replace=False))] * 1.08).ravel()
    for s in range(8)]
best = None
for x0 in seeds:
    res = minimize(obj, x0, method="Powell", options=dict(maxiter=20000, xtol=1e-6, ftol=1e-9))
    res = minimize(obj, res.x, method="Nelder-Mead", options=dict(maxiter=20000, xatol=1e-6, fatol=1e-10))
    if best is None or res.fun < best.fun:
        best = res
min_hex = best.x.reshape(-1, 2)

# purity: share of each side's border arc that is one type
nruns = [[t, [N(*q) for q in pts]] for t, pts in runs]
segs = [(t, LineString([a, b])) for t, pts in nruns for a, b in zip(pts[:-1], pts[1:])]
ext = country.exterior
def purity(corners):
    ts = sorted(ext.project(Point(c), normalized=True) for c in corners)
    out = []
    for i in range(len(ts)):
        a, b = ts[i], ts[(i + 1) % len(ts)] + (1 if i == len(ts) - 1 else 0)
        tot = {"sea": 0.0, "land": 0.0}
        for t, sg in segs:
            mm = ext.project(sg.interpolate(0.5, normalized=True), normalized=True)
            if a <= mm < b or a <= mm + 1 < b:
                tot[t] += sg.length
        out.append(round(100 * max(tot.values()) / sum(tot.values())))
    return out

def stats(P):
    p = Polygon(P); i = country.intersection(p).area
    return dict(iou=round(i / (country.area + p.area - i), 3), france_in=round(100 * i / country.area, 1),
                outside=round(100 * (p.area - i) / p.area, 1))

best6 = r["anchored"]["6"]["poly"]
summary = dict(runs=len(runs), classic=stats(classic), best6=stats(best6),
               min_hex_vs_classic_area=round(Polygon(min_hex).area / Polygon(classic).area, 3),
               purity_classic=purity(classic), purity_best6=purity(best6))
json.dump(dict(runs=nruns, classic=classic, classic_names=list(CLASSIC),
               min_hex=min_hex.tolist(), country=r["country"], best6=best6, summary=summary),
          open("story.json", "w"))
print(json.dumps(summary, indent=1))
