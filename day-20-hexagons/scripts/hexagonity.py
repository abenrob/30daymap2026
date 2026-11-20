"""
Hexagonity index for countries.

For each country (main landmass, holes filled, projected to a local
Lambert Azimuthal Equal-Area and normalised to unit area):

  1. Regular n-gon fits (n = 3..8 and a circle): best IoU over centre,
     size and rotation.  hexagonity = IoU_6 - max(IoU_other).
  2. Free-form k-gon sweep (k = 3..12): best IoU for any simple k-gon,
     each k seeded from the (k-1) solution.  Elbow strength at k =
     (e[k-1] - e[k]) / (e[k] - e[k+1]) with e = 1 - IoU.  natural_k is
     the k with the strongest elbow.

Usage:
  python hexagonity.py countries.shp --only France      # test one
  python hexagonity.py countries.shp --out results.json # whole world
"""
import argparse, json, math, sys, time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import shapefile  # pyshp
from pyproj import Transformer
from scipy.optimize import minimize
from shapely import affinity, make_valid
from shapely.geometry import Polygon, MultiPolygon, shape
from shapely.ops import unary_union

K_RANGE = range(3, 13)
REG_NS = [3, 4, 5, 6, 7, 8]
MAX_FRAMES = 60


# ---------------------------------------------------------------- prep
def main_landmass(geom):
    polys = list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]
    return max(polys, key=lambda p: p.area)


def prepare(geom_lonlat, simplify_tol=0.002):
    """Largest part, holes filled, LAEA around its centroid, unit area."""
    poly = Polygon(main_landmass(geom_lonlat).exterior)
    c = poly.centroid
    tr = Transformer.from_crs(
        "EPSG:4326",
        f"+proj=laea +lat_0={c.y} +lon_0={c.x} +datum=WGS84 +units=m",
        always_xy=True)
    xs, ys = tr.transform(*np.array(poly.exterior.coords).T)
    p = Polygon(zip(xs, ys))
    pc = p.centroid
    s = 1 / math.sqrt(p.area)
    p = affinity.scale(affinity.translate(p, -pc.x, -pc.y), s, s, origin=(0, 0))
    q, tol = p.simplify(simplify_tol, preserve_topology=True), simplify_tol
    while len(q.exterior.coords) - 1 > 200:  # cap outline size for speed
        tol *= 1.5
        q = p.simplify(tol, preserve_topology=True)
    p = q
    if not p.is_valid:
        p = max(make_valid(p).geoms, key=lambda g: g.area) if hasattr(make_valid(p), "geoms") else make_valid(p)
    meta = dict(lon0=c.x, lat0=c.y, cx=pc.x, cy=pc.y, scale=s)
    return p, meta


def iou(a, b):
    try:
        i = a.intersection(b).area
    except Exception:
        return 0.0
    return i / (a.area + b.area - i)


class Recorder:
    """Wraps an objective; keeps every improving polygon as a frame."""
    def __init__(self, country, to_poly):
        self.country, self.to_poly = country, to_poly
        self.best, self.frames, self.evals = -1.0, [], 0

    def __call__(self, x):
        self.evals += 1
        poly = self.to_poly(x)
        if poly is None or not poly.is_valid:
            return 2.0
        v = iou(self.country, poly)
        if v > self.best:
            self.best = v
            self.frames.append((v, x.copy()))
        return 1.0 - v

    def sampled_frames(self):
        fr = self.frames
        if len(fr) > MAX_FRAMES:
            idx = np.unique(np.round(np.linspace(0, len(fr) - 1, MAX_FRAMES)).astype(int))
            fr = [fr[i] for i in idx]
        return [(round(v, 5), coords(self.to_poly(x))) for v, x in fr]


def coords(poly, nd=4):
    return [[round(x, nd), round(y, nd)] for x, y in list(poly.exterior.coords)[:-1]]


# ------------------------------------------------------ regular n-gons
def regular(n, cx, cy, r, theta):
    if n == 0:  # circle
        return Polygon([(cx + r * math.cos(t), cy + r * math.sin(t))
                        for t in np.linspace(0, 2 * math.pi, 96, endpoint=False)])
    return Polygon([(cx + r * math.cos(theta + 2 * math.pi * i / n),
                     cy + r * math.sin(theta + 2 * math.pi * i / n)) for i in range(n)])


def fit_regular(country, n):
    # area-matched circumradius for unit area
    r0 = math.sqrt(1 / math.pi) if n == 0 else math.sqrt(2 / (n * math.sin(2 * math.pi / n)))
    to_poly = lambda x: regular(n, x[0], x[1], r0 * math.exp(x[2]), x[3])
    best = None
    thetas = [0.0] if n == 0 else np.linspace(0, 2 * math.pi / n, 12, endpoint=False)
    for th in thetas:  # coarse rotation grid, then refine the best few
        x0 = np.array([0, 0, 0, th])
        v = 1 - iou(country, to_poly(x0))
        if best is None or v < best[0]:
            best = (v, x0)
    rec = Recorder(country, to_poly)
    res = minimize(rec, best[1], method="Nelder-Mead",
                   options=dict(xatol=1e-4, fatol=1e-6, maxiter=800,
                                initial_simplex=None))
    poly = to_poly(res.x)
    return dict(n=n, iou=round(iou(country, poly), 5), poly=coords(poly))


# --------------------------------------------------- free-form k-gons
def flat_to_poly(x):
    pts = x.reshape(-1, 2)
    p = Polygon(pts)
    return p if p.is_valid and p.area > 0 else None


def insert_vertex(country, poly):
    """Add a vertex where the fit is worst: at the point of the largest
    error piece farthest from the current boundary, on its nearest edge."""
    pts = list(poly.exterior.coords)[:-1]
    diff = country.symmetric_difference(poly)
    pieces = list(diff.geoms) if hasattr(diff, "geoms") else [diff]
    pieces = [g for g in pieces if g.area > 0]
    if not pieces:
        target = None
    else:
        big = max(pieces, key=lambda g: g.area)
        ring = big.exterior if hasattr(big, "exterior") else big.boundary
        cand = np.array(ring.coords)
        d = [poly.exterior.distance(type(poly.centroid)(c)) for c in cand]
        target = cand[int(np.argmax(d))]
    candidates = []
    for i in range(len(pts)):
        a, b = np.array(pts[i]), np.array(pts[(i + 1) % len(pts)])
        for q in ([target] if target is not None else []) + [(a + b) / 2]:
            new = pts[:i + 1] + [tuple(q)] + pts[i + 1:]
            p = Polygon(new)
            if p.is_valid:
                candidates.append((iou(country, p), new))
    # midpoint insertion keeps IoU unchanged, so this never goes backwards
    return np.array(max(candidates, key=lambda c: c[0])[1]).ravel()


def optimise(country, x0, maxiter):
    rec = Recorder(country, flat_to_poly)
    rec(x0)
    res = minimize(rec, x0, method="Powell",
                   options=dict(xtol=1e-4, ftol=1e-6, maxiter=maxiter))
    x = res.x if flat_to_poly(res.x) is not None else x0
    return x, rec


def decimation_seeds(country):
    """Greedy decimation of the outline: repeatedly drop the vertex whose
    removal costs least IoU. Gives a sensible seed for every k."""
    base, tol = country, 0.002
    while len(base.exterior.coords) - 1 > 60:  # keep the O(n^2) loop cheap
        tol *= 1.5
        base = country.simplify(tol, preserve_topology=True)
    pts = list(base.exterior.coords)[:-1]
    seeds = {}
    while len(pts) > 3:
        best = None
        for i in range(len(pts)):
            p = Polygon(pts[:i] + pts[i + 1:])
            if not p.is_valid:
                continue
            v = iou(country, p)
            if best is None or v > best[0]:
                best = (v, i)
        if best is None:
            break
        pts.pop(best[1])
        if len(pts) in K_RANGE:
            seeds[len(pts)] = np.array(pts).ravel()
    return seeds


def fit_convex(country, reg_seed, k=6):
    """Best convex k-gon, seeded from a decimated convex hull
    (or the best regular k-gon when the hull has too few vertices)."""
    hull = Polygon(country.convex_hull.exterior)
    seed = decimation_seeds(hull).get(k)
    if seed is None:
        seed = np.array(reg_seed).ravel()
    def to_poly(x):
        p = flat_to_poly(x)
        if p is None or abs(p.convex_hull.area - p.area) > 1e-9:
            return None
        return p
    rec = Recorder(country, to_poly)
    rec(seed)
    res = minimize(rec, seed, method="Powell",
                   options=dict(xtol=1e-4, ftol=1e-6, maxiter=60))
    x = res.x if to_poly(res.x) is not None else seed
    return dict(k=k, iou=round(iou(country, to_poly(x)), 5), poly=coords(to_poly(x)))


def fit_sweep(country, tri_seed):
    """For each k, optimise from (a) the previous best with an inserted
    vertex and (b) the greedy-decimation seed; keep the better result."""
    dec = decimation_seeds(country)
    out, prev = [], None
    for k in K_RANGE:
        seeds = []
        if prev is None:
            seeds.append(np.array(tri_seed).ravel())
        else:
            seeds.append(insert_vertex(country, flat_to_poly(prev)))
        if k in dec:
            seeds.append(dec[k])
        best = None
        for s in seeds:
            x, rec = optimise(country, s, maxiter=30 + 4 * k)
            v = iou(country, flat_to_poly(x))
            if best is None or v > best[0]:
                best = (v, x, rec)
        v, x, rec = best
        # monotonic guard: a k-gon can always reproduce the (k-1) fit
        if prev is not None and v < out[-1]["iou"]:
            x = insert_vertex(country, flat_to_poly(prev))
            v = iou(country, flat_to_poly(x))
        prev = x
        out.append(dict(k=k, iou=round(v, 5), poly=coords(flat_to_poly(x)),
                        frames=rec.sampled_frames(), evals=rec.evals))
    return out


ELBOW_FLOOR = 0.005  # ignore gains under 0.5 % IoU in the denominator


def elbows(sweep):
    e = {s["k"]: 1 - s["iou"] for s in sweep}
    res = {}
    for k in list(K_RANGE)[1:-1]:
        num, den = e[k - 1] - e[k], e[k] - e[k + 1]
        res[k] = round(num / max(den, ELBOW_FLOOR), 3)
    return res


# --------------------------------------------------------------- main
def run_country(item):
    import os, traceback
    name = item[0]
    path = os.path.join("cache", f"{name.replace('/', '_')}.json")
    if os.path.exists(path):
        return json.load(open(path))
    try:
        r = _run_country(item)
    except Exception:
        return dict(name=name, error=traceback.format_exc(limit=2))
    json.dump(r, open(path, "w"), separators=(",", ":"))
    return r


def _run_country(item):
    name, iso, cont, geom = item
    t = time.time()
    country, meta = prepare(geom)
    regs = [fit_regular(country, n) for n in REG_NS + [0]]
    reg_iou = {("circle" if r["n"] == 0 else r["n"]): r["iou"] for r in regs}
    others = max(v for k, v in reg_iou.items() if k != 6)
    tri = next(r for r in regs if r["n"] == 3)["poly"]
    sweep = fit_sweep(country, tri)
    elb = elbows(sweep)
    nat = max(elb, key=elb.get)
    hex6 = next(s for s in sweep if s["k"] == 6)
    convex6 = fit_convex(country, next(r for r in regs if r["n"] == 6)["poly"])
    pts = np.array(hex6["poly"] + [hex6["poly"][0]])
    edges = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    return dict(
        name=name, iso=iso, continent=cont, meta=meta,
        country=coords(country), n_vertices=len(country.exterior.coords) - 1,
        regular=regs, regular_iou=reg_iou,
        hex_iou=reg_iou[6], hexagonity=round(reg_iou[6] - others, 5),
        best_regular=max(reg_iou, key=reg_iou.get),
        sweep=sweep, elbow=elb, natural_k=nat, elbow6=elb[6],
        convex6=convex6, convex6_iou=convex6["iou"],
        freehex_edge_cv=round(float(edges.std() / edges.mean()), 4),
        seconds=round(time.time() - t, 1))


def load(path):
    r = shapefile.Reader(path)
    fields = [f[0] for f in r.fields[1:]]
    for sr in r.iterShapeRecords():
        rec = dict(zip(fields, sr.record))
        g = make_valid(shape(sr.shape.__geo_interface__))
        if g.is_empty or g.area == 0:
            continue
        if g.geom_type == "GeometryCollection":
            g = unary_union([p for p in g.geoms if p.geom_type in ("Polygon", "MultiPolygon")])
        name = rec.get("name") or rec.get("NAME") or rec.get("ADMIN")
        iso = rec.get("iso_a3") or rec.get("ISO_A3") or rec.get("ADM0_A3")
        cont = rec.get("continent") or rec.get("CONTINENT")
        yield name, iso, cont, g


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("shp")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--out", default="hexagonity.json")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--skip", nargs="*", default=["Antarctica"])
    a = ap.parse_args()
    items = [i for i in load(a.shp)
             if (not a.only or i[0] in a.only) and i[0] not in a.skip]
    import os
    os.makedirs("cache", exist_ok=True)
    with ProcessPoolExecutor(a.workers) as ex:
        results = []
        for r in ex.map(run_country, items):
            if "error" in r:
                print(f"{r['name']:<28} FAILED: {r['error'].splitlines()[-1]}", file=sys.stderr, flush=True)
                continue
            results.append(r)
            print(f"{r['name']:<28} H6={r['hex_iou']:.3f} hexagonity={r['hexagonity']:+.3f} "
                  f"natural_k={r['natural_k']} elbow6={r['elbow6']:.2f} ({r['seconds']}s)",
                  file=sys.stderr, flush=True)
    results.sort(key=lambda r: -r["hexagonity"])
    json.dump(results, open(a.out, "w"), separators=(",", ":"))
    print(f"wrote {len(results)} countries to {a.out}", file=sys.stderr)
