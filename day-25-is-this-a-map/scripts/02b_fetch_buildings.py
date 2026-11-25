"""BD TOPO buildings and roads for the lit, visible 2 km tiles (derived/light_tiles.json, from 03's viewshed and
the VIIRS crop), within MAX_KM. IGN BD TOPO V3 via the Geoplateforme WFS (Licence Ouverte Etalab 2.0).

buildings.npz: AEQD centroid x, y, footprint area (m2), height (m), usage_1 (string)
roads.npz:     lamp candidates every LAMP_SPACING m along each segment: x, y, importance (1-6, 9 = NC),
               urbain (bool), paved (bool); tunnels skipped
"""
import json, sys, importlib, concurrent.futures as cf
import numpy as np, requests
from pyproj import Transformer
from common import *

MAX_KM = float(sys.argv[1]) if len(sys.argv) > 1 else 45
LAMP_SPACING = 30.0
WFS = "https://data.geopf.fr/wfs/ows"
PAVED = {"Route à 1 chaussée", "Route à 2 chaussées", "Rond-point", "Bretelle", "Quasi-autoroute", "Type autoroutier"}
to_ll = Transformer.from_crs(AEQD, 4326, always_xy=True)
to_aeqd = Transformer.from_crs(4326, AEQD, always_xy=True)


def tiles():
    f = DERIVED / "light_tiles.json"
    if not f.exists():
        bs = importlib.import_module("03_build_scene")
        v = bs.visibility_masks()["t100"]
        L = np.load(DERIVED / "lights100.npy"); c0 = 700; Lc = L[c0:c0 + 1200, c0:c0 + 1200]
        T = (v & (Lc > 0.5)).reshape(60, 20, 60, 20).any((1, 3))
        t = [(int(-60000 + j * 2000), int(60000 - (i + 1) * 2000)) for i, j in zip(*np.nonzero(T))]
        json.dump(dict(tiles=t, size=2000), open(f, "w"))
    t = json.load(open(f))["tiles"]
    return [(x, y) for x, y in t if np.hypot(x + 1000, y + 1000) < MAX_KM * 1000]


def get_all(typename, props, tile):
    x, y = tile
    lo0, la0 = to_ll.transform(x, y); lo1, la1 = to_ll.transform(x + 2000, y + 2000)
    out, start = [], 0
    while True:
        p = dict(SERVICE="WFS", VERSION="2.0.0", REQUEST="GetFeature", TYPENAMES=typename, OUTPUTFORMAT="application/json",
                 SRSNAME="EPSG:4326", COUNT=5000, STARTINDEX=start, PROPERTYNAME=props,
                 BBOX=f"{min(la0,la1)},{min(lo0,lo1)},{max(la0,la1)},{max(lo0,lo1)},urn:ogc:def:crs:EPSG::4326")
        for attempt in range(4):
            try:
                r = requests.get(WFS, params=p, timeout=120); r.raise_for_status(); fs = r.json()["features"]; break
            except Exception as e:
                err = e
        else:
            raise err
        out += fs
        if len(fs) < 5000:
            return out
        start += 5000


def buildings(tile):
    x, y = tile; rows = []
    for f in get_all("BDTOPO_V3:batiment", "geometrie,hauteur,usage_1", tile):
        g = f["geometry"]
        if not g:
            continue
        ring = np.array(g["coordinates"][0][0] if g["type"] == "MultiPolygon" else g["coordinates"][0])[:, :2]
        px, py = to_aeqd.transform(ring[:, 0], ring[:, 1])
        a = 0.5 * abs(np.dot(px[:-1], py[1:]) - np.dot(px[1:], py[:-1]))
        cx, cy = px.mean(), py.mean()
        if x <= cx < x + 2000 and y <= cy < y + 2000:
            h = f["properties"].get("hauteur")
            rows.append((cx, cy, a, np.nan if h is None else h, f["properties"].get("usage_1") or ""))
    return rows


def roads(tile):
    x, y = tile; rows = []
    for f in get_all("BDTOPO_V3:troncon_de_route", "geometrie,importance,nature,urbain,position_par_rapport_au_sol", tile):
        g, pr = f["geometry"], f["properties"]
        if not g or str(pr.get("position_par_rapport_au_sol")) == "-1":
            continue                                     # tunnels
        lines = g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]
        imp = int(pr["importance"]) if str(pr.get("importance")).isdigit() else 9
        for ln in lines:
            ln = np.array(ln)[:, :2]
            px, py = to_aeqd.transform(ln[:, 0], ln[:, 1])
            seg = np.hypot(np.diff(px), np.diff(py)); s = np.r_[0, np.cumsum(seg)]
            if s[-1] < 1:
                continue
            q = np.arange(LAMP_SPACING / 2, s[-1], LAMP_SPACING)
            lx, ly = np.interp(q, s, px), np.interp(q, s, py)
            keep = (lx >= x) & (lx < x + 2000) & (ly >= y) & (ly < y + 2000)
            for a_, b_ in zip(lx[keep], ly[keep]):
                rows.append((a_, b_, imp, bool(pr.get("urbain")), pr.get("nature") in PAVED))
    return rows


if __name__ == "__main__":
    T = tiles(); print(len(T), "tiles within", MAX_KM, "km", flush=True)
    B, R = [], []
    with cf.ThreadPoolExecutor(8) as ex:
        for k, (b, r) in enumerate(zip(ex.map(buildings, T), ex.map(roads, T))):
            B += b; R += r
            if k % 50 == 0:
                print(f"  {k}/{len(T)} tiles, {len(B):,} buildings, {len(R):,} lamp candidates", flush=True)
    b = np.array([r[:4] for r in B], np.float64)
    np.savez_compressed(DERIVED / "buildings.npz", x=b[:, 0], y=b[:, 1], area=b[:, 2], height=b[:, 3], usage=np.array([r[4] for r in B]))
    r = np.array(R, np.float64)
    np.savez_compressed(DERIVED / "roads.npz", x=r[:, 0], y=r[:, 1], importance=r[:, 2].astype(int), urbain=r[:, 3].astype(bool), paved=r[:, 4].astype(bool))
    us = np.array([r[4] for r in B]); u, c = np.unique(us, return_counts=True)
    print(f"{len(b):,} buildings; usage: " + ", ".join(f"{a} {n:,}" for a, n in sorted(zip(u, c), key=lambda z: -z[1])[:6]))
    print(f"{len(r):,} lamp candidates; urban paved {np.mean(r[:,3].astype(bool) & r[:,4].astype(bool)):.0%}, importance<=3 & urban {np.mean((r[:,2] <= 3) & r[:,3].astype(bool)):.0%}")
