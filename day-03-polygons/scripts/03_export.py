"""Day 3, step 3: write the files the web page loads.

Reads:  bdtopo/bat.parquet and bdtopo/arr.parquet (from 02_prep.py)
Writes: buildings/arrNN.json, one per arrondissement: every building and its outline
        buildings/index.json: per-arrondissement totals for the Shares tab, plus the picker map

Copy the buildings/ folder next to index.html. (It is not called data/ because the repo's
.gitignore excludes data/ folders.)
"""
import json
import math
import os

import geopandas as gpd
import numpy as np

g = gpd.read_parquet("bdtopo/bat.parquet")
arr = gpd.read_parquet("bdtopo/arr.parquet").sort_values("n")

# BD TOPO's usage_1 values mapped to small integers. The order must match the TYPES
# list (names and colours) in index.html and 04_make_animation.py.
TYPES = {"Résidentiel": 0, "Commercial et services": 1, "Industriel": 2, "Religieux": 3,
         "Sportif": 4, "Agricole": 5, "Annexe": 6, "Indifférencié": 7}
g["t"] = g.usage_1.map(TYPES).fillna(7).astype(int)  # a missing use counts as Indifférencié

# Drop vertices that move the outline by less than 30 cm. Invisible on screen, and it
# shrinks the files by about a third. Areas were computed before this, on the full outlines.
g["geometry"] = g.geometry.simplify(0.3)

os.makedirs("buildings", exist_ok=True)
idx = []
for _, a in arr.iterrows():
    n = int(a.n)
    # Largest first: the page sorts again anyway, but this keeps the files in a useful order.
    s = g[g.arr == n].sort_values("area", ascending=False)
    x0, y0, x1, y1 = a.geometry.bounds

    out = []
    for r in s.itertuples():
        # Coordinates are stored as integer decimetres relative to the arrondissement's
        # south-west corner: 10 cm precision, and a flat [x, y, x, y, ...] list per outline
        # is much smaller than GeoJSON. A MultiPolygon gives one list per part.
        # Only exterior rings are kept, so inner courtyards draw filled in. The area above
        # was computed with the courtyards removed, so the numbers are unaffected.
        rings = []
        for p in getattr(r.geometry, "geoms", [r.geometry]):
            if p.is_empty:
                continue
            c = np.asarray(p.exterior.coords)[:-1]  # drop the repeated closing point
            rings.append(np.round((c - [x0, y0]) * 10).astype(int).ravel().tolist())
        if not rings:
            continue

        # Angle of the building's long axis, used by "Long side horizontal": the page rotates
        # each footprint by minus this angle. Taken from the minimum rotated rectangle: of its
        # first two edges (one long side, one short side), keep the longer.
        cc = np.asarray(r.geometry.minimum_rotated_rectangle.exterior.coords)
        e1 = cc[1] - cc[0]
        e2 = cc[2] - cc[1]
        e = e1 if np.hypot(*e1) >= np.hypot(*e2) else e2
        ang = math.atan2(e[1], e[0])

        # One compact array per building: [use, area m², height m, dwellings, angle rad, outlines].
        # (x != x is the NaN test: pandas gives NaN for missing numbers.)
        out.append([r.t, round(r.area, 1),
                    None if r.hauteur != r.hauteur or r.hauteur is None else round(r.hauteur, 1),
                    None if r.nombre_de_logements != r.nombre_de_logements or r.nombre_de_logements is None
                    else int(r.nombre_de_logements),
                    round(ang, 3), rings])

    # The arrondissement boundary, same coordinate scheme, drawn dashed on the map view.
    outline = [np.round((np.asarray(p.exterior.coords) - [x0, y0]) * 10).astype(int).ravel().tolist()
               for p in getattr(a.geometry, "geoms", [a.geometry])]
    json.dump(dict(n=n, name=a.nom_officiel, pop=int(a.population),
                   w=round((x1 - x0) * 10), h=round((y1 - y0) * 10),  # extent in decimetres
                   outline=outline, b=out),
              open(f"buildings/arr{n:02d}.json", "w"), separators=(",", ":"))

    # Totals for the Shares tab, computed here so the page can draw all 20 rows
    # without loading 20 building files.
    tc = np.bincount(s.t, minlength=8)                     # buildings per use
    ta = np.bincount(s.t, weights=s.area, minlength=8)     # footprint m² per use
    bins = [0, 50, 200, 1000, 1e12]                        # size classes in m²
    sc = np.histogram(s.area, bins)[0]                     # buildings per size class
    sa = np.histogram(s.area, bins, weights=s.area)[0]     # footprint m² per size class
    idx.append(dict(n=n, name=a.nom_officiel, pop=int(a.population), count=len(s), foot=round(s.area.sum()),
                    tc=tc.tolist(), ta=np.round(ta).tolist(), sc=sc.tolist(), sa=np.round(sa).tolist(),
                    land=round(a.geometry.area),
                    medh=None if s.hauteur.isna().all() else round(float(s.hauteur.median()), 1)))

# The clickable picker map: all 20 outlines simplified to 15 m, in whole metres relative to
# the corner of Paris as a whole (a shared frame, unlike the per-arrondissement files).
X0, Y0, X1, Y1 = arr.total_bounds
pick = [dict(n=int(a.n),
             rings=[np.round(np.asarray(p.exterior.coords) - [X0, Y0]).astype(int).ravel().tolist()
                    for p in getattr(a.geometry.simplify(15), "geoms", [a.geometry.simplify(15)])])
        for _, a in arr.iterrows()]
json.dump(dict(types=list(TYPES), w=round(X1 - X0), h=round(Y1 - Y0), arr=idx, pick=pick),
          open("buildings/index.json", "w"), separators=(",", ":"))
