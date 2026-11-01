"""Day 1 comparison figure: what had to be read to answer one viewport query.

Inputs (built by the metadata step):
  rg.parquet       one row per Parquet row group: bbox stats (x0, x1, y0, y1) and row count
  idf_pts.parquet  lon/lat of places around Paris, for the dot layer
"""
import math
import duckdb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection

rg = duckdb.sql("select x0,x1,y0,y1 from 'rg.parquet' where x0 is not null and x1-x0<90").fetchall()
pts = duckdb.sql("select lon,lat from 'idf_pts.parquet'").fetchnumpy()
z12 = duckdb.sql("select lon,lat from 'z12_pts.parquet'").fetchnumpy()  # what the z12 tiles actually contain

V = (2.22, 2.47, 48.80, 48.91)  # the query viewport
X = (1.98, 2.72, 48.70, 49.02)  # extent shown in each panel
hit = lambda r: r[1] >= V[0] and r[0] <= V[1] and r[3] >= V[2] and r[2] <= V[3]
box = lambda a, b, c, d: [(a, c), (b, c), (b, d), (a, d)]

bg, faint, lit, dot = "#0f1115", "#4a5060", "#ffb000", "#e8eaee"
asp = 1 / math.cos(math.radians(48.86))

panels = [
    ("1  GeoParquet, clustered by location", "17 of 5,647 row groups · 351k rows scanned", "36.6 MB · 9.7 s · all 269,730 places"),
    ("2  Same data, not clustered", "Every row group spans the globe: all 5,647 read", "about 5.1 GB · about 3 min (estimated) · all places"),
    ("3  PMTiles, zoom 12", "12 pre-built tiles + 2 directory reads", "1.05 MB · 1.9 s · 42,995 places (16%)"),
]

fig, axs = plt.subplots(1, 3, figsize=(18, 7.2), facecolor=bg)
for i, ax in enumerate(axs):
    ax.set_facecolor(bg)
    ax.set_xlim(X[0], X[1]); ax.set_ylim(X[2], X[3]); ax.set_aspect(asp)
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color("#2a2e37")
    src = z12 if i == 2 else pts
    ax.scatter(src["lon"], src["lat"], s=.15 if i < 2 else .5, c=dot, alpha=.35 if i < 2 else .6, linewidths=0)
    if i == 0:
        ax.add_collection(PolyCollection([box(*r) for r in rg if not hit(r)], facecolors="none", edgecolors=faint, linewidths=.6))
        ax.add_collection(PolyCollection([box(*r) for r in rg if hit(r)], facecolors=lit, alpha=.28, edgecolors=lit, linewidths=1.2))
    elif i == 1:
        ax.add_collection(PolyCollection([box(X[0] - 1, X[1] + 1, X[2] - 1, X[3] + 1)], facecolors=lit, alpha=.28, edgecolors="none"))
    else:
        n = 2 ** 12
        tx = lambda lon: int((lon + 180) / 360 * n)
        ty = lambda lat: int((1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n)
        lon = lambda x: x / n * 360 - 180
        lat = lambda y: math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
        tiles = lambda e: [(x, y) for x in range(tx(e[0]), tx(e[1]) + 1) for y in range(ty(e[3]), ty(e[2]) + 1)]
        ax.add_collection(PolyCollection([box(lon(x), lon(x + 1), lat(y + 1), lat(y)) for x, y in tiles(X)], facecolors="none", edgecolors=faint, linewidths=.6))
        ax.add_collection(PolyCollection([box(lon(x), lon(x + 1), lat(y + 1), lat(y)) for x, y in tiles(V)], facecolors=lit, alpha=.28, edgecolors=lit, linewidths=1.2))
    ax.add_patch(plt.Rectangle((V[0], V[2]), V[1] - V[0], V[3] - V[2], fill=False, ec="white", lw=1.2, ls="--"))
    ax.text(0, 1.155, panels[i][0], transform=ax.transAxes, color="white", fontsize=15, fontweight="bold", va="bottom")
    ax.text(0, 1.02, panels[i][1] + "\n" + panels[i][2], transform=ax.transAxes, color="#c9ccd3", fontsize=10.5, va="bottom", linespacing=1.4)

fig.text(0.008, 0.95, "Same question, three ways: which of 103.6 million places are in this box over Paris?", color="white", fontsize=18, ha="left")
fig.text(0.008, 0.015, "Dashed box: the query. Orange: what had to be read. Dots: Foursquare Open Source Places (Apache 2.0), Source Cooperative, release 2025-02-06.\n"
         "Times: median of 5 replays of each request pattern against Source Cooperative from a cloud machine. PMTiles: France extract, tippecanoe-style dropping.", color="#8a8f99", fontsize=9.5)
plt.subplots_adjust(left=.008, right=.992, top=.76, bottom=.09, wspace=.03)
plt.savefig("day01_draft.png", dpi=130, facecolor=bg)
