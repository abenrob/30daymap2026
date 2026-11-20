"""
Convex-only k-gon sweep (k = 3..8), added to world.json.

Free-form 6-gons reward L-shapes and zigzags, which naturally have six
corners. Restricting to convex polygons makes "six corners" mean
"hexagon-like". Each k is seeded from the (k-1) fit (a vertex inserted
on every edge midpoint is tried) and from a decimated convex hull, then
refined vertex-by-vertex. Monotone by construction.

  python convex.py world.json
"""
import json, sys
from concurrent.futures import ProcessPoolExecutor
import numpy as np
from scipy.optimize import minimize
from shapely.geometry import Polygon
from hexagonity import iou, decimation_seeds, coords

KS = range(3, 9)


def as_convex(P):
    p = Polygon(P)
    if not p.is_valid or p.area <= 0:
        return None
    if p.convex_hull.area - p.area > 1e-9:
        return None
    return p


MISS_W = 2.0  # missed land counts double vs. extra sea/neighbour


def wiou(country, p):
    """Weighted Jaccard: I / (I + MISS_W * missed land + extra area).
    Equals IoU when MISS_W = 1; >1 pushes fits to keep chunks of land."""
    try:
        i = country.intersection(p).area
    except Exception:
        return 0.0
    missed, extra = country.area - i, p.area - i
    return i / (i + MISS_W * missed + extra)


def score(country, P):
    p = as_convex(P)
    return -1.0 if p is None else wiou(country, p)


def refine(country, P, cycles=4):
    P = np.array(P, float)
    best = score(country, P)
    for _ in range(cycles):
        improved = False
        for i in range(len(P)):
            def f(xy):
                Q = P.copy(); Q[i] = xy
                return -score(country, Q)
            res = minimize(f, P[i], method="Nelder-Mead",
                           options=dict(xatol=1e-4, fatol=1e-7, maxiter=60,
                                        initial_simplex=[P[i], P[i] + [0.03, 0], P[i] + [0, 0.03]]))
            if -res.fun > best + 1e-7:
                P[i] = res.x; best = -res.fun; improved = True
        if not improved:
            break
    return P, best


def sweep(country):
    hull = Polygon(country.convex_hull.exterior)
    dec = decimation_seeds(hull)
    out, prev = {}, None
    for k in KS:
        seeds = []
        if prev is not None:
            n = len(prev)
            for i in range(n):  # insert on each edge midpoint (IoU unchanged)
                mid = (prev[i] + prev[(i + 1) % n]) / 2
                seeds.append(np.insert(prev, i + 1, mid, axis=0))
            # keep only the 3 most promising after a quick refine
            quick = sorted(((refine(country, s, 1)) for s in seeds), key=lambda t: -t[1])[:3]
            seeds = [q[0] for q in quick]
        if k in dec:
            seeds.append(dec[k].reshape(-1, 2))
        if not seeds:  # hull smaller than k: regular-ish fallback
            seeds.append(np.array(hull.exterior.coords[:-1]))
        best = max((refine(country, s) for s in seeds), key=lambda t: t[1])
        if prev is not None and best[1] < out[k - 1]["iou"]:
            best = (np.insert(prev, 1, (prev[0] + prev[1]) / 2, axis=0), out[k - 1]["iou"])
        prev = best[0]
        out[k] = dict(k=k, iou=round(best[1], 5), poly=[[round(x, 4), round(y, 4)] for x, y in prev])
    return out


def work(r):
    country = Polygon(r["country"])
    fits = sweep(country)
    for f in fits.values():  # also report plain IoU and land coverage
        p = Polygon(f["poly"])
        f["wiou"] = f.pop("iou")
        f["iou"] = round(iou(country, p), 5)
        f["coverage"] = round(country.intersection(p).area / country.area, 4)
    e = {k: 1 - f["wiou"] for k, f in fits.items()}
    elb = {k: round((e[k - 1] - e[k]) / max(e[k] - e[k + 1], 0.005), 3) for k in range(4, 8)}
    return r["name"], {str(k): f for k, f in fits.items()}, {str(k): v for k, v in elb.items()}


if __name__ == "__main__":
    path = sys.argv[1]
    only = sys.argv[2:]
    rs = json.load(open(path))
    todo = [r for r in rs if not only or r["name"] in only]
    with ProcessPoolExecutor(2) as ex:
        out = {n: (f, e) for n, f, e in ex.map(work, todo)}
    for r in todo:
        r["convex"], r["convex_elbow"] = out[r["name"]]
        r["convex_elbow6"] = r["convex_elbow"]["6"]
        r["convex6_iou"] = r["convex"]["6"]["iou"]
        r["convex6_wiou"] = r["convex"]["6"]["wiou"]
        r["convex6_coverage"] = r["convex"]["6"]["coverage"]
        if only:
            print(r["name"], {k: (v["wiou"], v["coverage"]) for k, v in r["convex"].items()})
    if not only:
        json.dump(rs, open(path, "w"), separators=(",", ":"))
    print("done", len(todo))
