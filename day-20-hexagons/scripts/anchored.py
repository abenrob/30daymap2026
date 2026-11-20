"""
"Points of the star" test: the best convex k-gon whose corners must lie
ON the country's border (k = 3..9). This is how the French hexagon is
drawn - by joining six salient border points - rather than an area fit
whose corners can float out at sea.

Score per k: plain IoU. Gains g_k = IoU_k - IoU_(k-1).
A country is "k-pointed" when the k-th point still pays and the (k+1)-th
doesn't: drop_k = g_k - g_(k+1), compared with the world median drop_k.

  python anchored.py world.json [Country ...]   # names = test, no write
"""
import json, sys
from concurrent.futures import ProcessPoolExecutor
import numpy as np
from scipy.optimize import minimize_scalar
from shapely.geometry import Polygon, Point
from hexagonity import iou, decimation_seeds

KS = range(3, 10)


class Border:
    def __init__(self, country):
        self.country = country
        self.ring = country.exterior
        self.L = self.ring.length

    def pt(self, t):
        p = self.ring.interpolate((t % 1.0) * self.L)
        return (p.x, p.y)

    def t_of(self, xy):
        return self.ring.project(Point(xy)) / self.L

    def poly(self, ts):
        ts = np.sort(np.mod(ts, 1.0))
        p = Polygon([self.pt(t) for t in ts])
        if not p.is_valid or p.area <= 0 or p.convex_hull.area - p.area > 1e-9:
            return None
        return p

    def score(self, ts):
        p = self.poly(ts)
        return -1.0 if p is None else iou(self.country, p)


def refine(B, ts, cycles=4):
    ts = np.sort(np.mod(np.array(ts, float), 1.0))
    best = B.score(ts)
    n = len(ts)
    for _ in range(cycles):
        improved = False
        for i in range(n):
            lo = ts[i - 1] if i > 0 else ts[-1] - 1
            hi = ts[i + 1] if i < n - 1 else ts[0] + 1
            def f(t):
                q = ts.copy(); q[i] = t % 1.0
                return -B.score(q)
            grid = np.linspace(lo, hi, 42)[1:-1]
            vals = [f(t) for t in grid]
            j = int(np.argmin(vals))
            a, b = grid[max(j - 1, 0)], grid[min(j + 1, len(grid) - 1)]
            res = minimize_scalar(f, bounds=(a, b), method="bounded",
                                  options=dict(xatol=1e-5))
            t_new, v_new = (res.x, -res.fun) if res.fun <= vals[j] else (grid[j], -vals[j])
            if v_new > best + 1e-7:
                ts[i] = t_new % 1.0; ts = np.sort(ts); best = v_new; improved = True
        if not improved:
            break
    return ts, best


def sweep(country):
    B = Border(country)
    hull = Polygon(country.convex_hull.exterior)
    dec = decimation_seeds(hull)  # hull vertices are border points
    out, prev = {}, None
    for k in KS:
        seeds = []
        if k in dec:
            seeds.append([B.t_of(xy) for xy in dec[k].reshape(-1, 2)])
        if prev is not None:  # insert a point in each gap
            n = len(prev)
            for i in range(n):
                a, b = prev[i], prev[(i + 1) % n] + (1 if i == n - 1 else 0)
                seeds.append(np.append(prev, ((a + b) / 2) % 1.0))
            seeds = sorted(seeds, key=lambda s: -B.score(s))[:4]
        if not seeds:
            seeds.append(np.linspace(0, 1, k, endpoint=False))
        ts, v = max((refine(B, s) for s in seeds), key=lambda t: t[1])
        if prev is not None and v < out[k - 1]["iou"]:  # monotone envelope
            ts, v = prev, out[k - 1]["iou"]
        prev = ts
        p = B.poly(ts) or B.poly(np.sort(ts))
        out[k] = dict(k=k, iou=round(v, 5), n=len(ts),
                      poly=[[round(x, 4), round(y, 4)] for x, y in p.exterior.coords[:-1]])
    return out


def work(r):
    return r["name"], sweep(Polygon(r["country"]))


if __name__ == "__main__":
    path, only = sys.argv[1], sys.argv[2:]
    rs = json.load(open(path))
    todo = [r for r in rs if not only or r["name"] in only]
    with ProcessPoolExecutor(2) as ex:
        out = dict(ex.map(work, todo))
    for r in todo:
        r["anchored"] = {str(k): v for k, v in out[r["name"]].items()}
        if only:
            ious = {k: v["iou"] for k, v in out[r["name"]].items()}
            g = {k: round(ious[k] - ious[k - 1], 4) for k in range(4, 10)}
            print(r["name"], ious, "gains", g)
    if not only:
        json.dump(rs, open(path, "w"), separators=(",", ":"))
    print("done", len(todo))
