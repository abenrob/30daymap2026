"""Day 1: the three comparison maps as separate 4:5 images (1080 x 1350 px), for a multi-image post.

Inputs: rg.parquet (row-group boxes), idf_pts.parquet (all places around Paris), z12_pts.parquet (what the z12 tiles contain)
Outputs: panel-1-geoparquet.png, panel-2-shuffled.png, panel-3-pmtiles.png
"""
import math
import duckdb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection

rg = duckdb.sql("select x0,x1,y0,y1 from 'rg.parquet' where x0 is not null and x1-x0<90").fetchall()
pts = duckdb.sql("select lon,lat from 'idf_pts.parquet'").fetchnumpy()
z12 = duckdb.sql("select lon,lat from 'z12_pts.parquet'").fetchnumpy()

V = (2.22, 2.47, 48.80, 48.91)          # the query box
X = (2.02, 2.67, 48.64, 49.07)          # map extent, close to square on screen
hit = lambda r: r[1] >= V[0] and r[0] <= V[1] and r[3] >= V[2] and r[2] <= V[3]
box = lambda a, b, c, d: [(a, c), (b, c), (b, d), (a, d)]
bg, faint, lit, dot, sub, foot = "#0f1115", "#4a5060", "#ffb000", "#e8eaee", "#c9ccd3", "#8a8f99"
asp = 1 / math.cos(math.radians(48.86))

n = 2 ** 12
tx = lambda lon: int((lon + 180) / 360 * n)
ty = lambda lat: int((1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n)
tlon = lambda x: x / n * 360 - 180
tlat = lambda y: math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
tiles = lambda e: [(x, y) for x in range(tx(e[0]), tx(e[1]) + 1) for y in range(ty(e[3]), ty(e[2]) + 1)]

PANELS = [
    dict(file="panel-1-geoparquet.png", step="1 of 3", title="GeoParquet, clustered by location",
         lines=["17 of 5,647 row groups read", "36.6 MB  ·  9.7 s", "All 269,730 places in the box"]),
    dict(file="panel-2-shuffled.png", step="2 of 3", title="The same rows, shuffled",
         lines=["All 5,647 row groups read", "About 5.1 GB  ·  about 3 min (estimated)", "All 269,730 places in the box"]),
    dict(file="panel-3-pmtiles.png", step="3 of 3", title="PMTiles, zoom 12",
         lines=["12 tiles + 2 directory reads", "1.05 MB  ·  1.9 s", "42,995 places shown (16%)"]),
]

for i, p in enumerate(PANELS):
    fig = plt.figure(figsize=(8, 10), facecolor=bg)            # 4:5, saved at 135 dpi = 1080 x 1350
    fig.text(0.06, 0.945, p["step"] + "  ·  Which of 103.6 million places are in this box over Paris?", color=foot, fontsize=11)
    fig.text(0.06, 0.895, p["title"], color="white", fontsize=22, fontweight="bold")
    for k, line in enumerate(p["lines"]):
        fig.text(0.06, 0.85 - k * 0.033, line, color=lit if k == 1 else sub, fontsize=14)

    ax = fig.add_axes([0.06, 0.12, 0.88, 0.62], facecolor=bg)
    ax.set_xlim(X[0], X[1]); ax.set_ylim(X[2], X[3]); ax.set_aspect(asp, adjustable="datalim")
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color("#2a2e37")
    src = z12 if i == 2 else pts
    ax.scatter(src["lon"], src["lat"], s=.25 if i < 2 else .9, c=dot, alpha=.35 if i < 2 else .6, linewidths=0)
    if i == 0:
        ax.add_collection(PolyCollection([box(*r) for r in rg if not hit(r)], facecolors="none", edgecolors=faint, linewidths=.8))
        ax.add_collection(PolyCollection([box(*r) for r in rg if hit(r)], facecolors=lit, alpha=.28, edgecolors=lit, linewidths=1.4))
    elif i == 1:
        ax.add_collection(PolyCollection([box(X[0] - 1, X[1] + 1, X[2] - 1, X[3] + 1)], facecolors=lit, alpha=.28, edgecolors="none"))
    else:
        ax.add_collection(PolyCollection([box(tlon(x), tlon(x + 1), tlat(y + 1), tlat(y)) for x, y in tiles(X)], facecolors="none", edgecolors=faint, linewidths=.8))
        ax.add_collection(PolyCollection([box(tlon(x), tlon(x + 1), tlat(y + 1), tlat(y)) for x, y in tiles(V)], facecolors=lit, alpha=.28, edgecolors=lit, linewidths=1.4))
    ax.add_patch(plt.Rectangle((V[0], V[2]), V[1] - V[0], V[3] - V[2], fill=False, ec="white", lw=1.4, ls="--"))

    fig.text(0.06, 0.075, "Dashed box: the query.  Orange: what had to be read.", color=sub, fontsize=11)
    fig.text(0.06, 0.035, "Foursquare Open Source Places (Apache 2.0), Source Cooperative, 2025-02-06. Times: median of 5\n"
             "replays of each request pattern from a cloud machine." + ("  PMTiles: France extract." if i == 2 else ""),
             color=foot, fontsize=9, linespacing=1.4)
    fig.savefig(p["file"], dpi=135, facecolor=bg)
    plt.close(fig)
print("done")
