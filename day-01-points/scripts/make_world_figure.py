"""Day 1 image 2: every row group's bounding box, worldwide. The dataset's own index drawn as a map."""
import duckdb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection

rg = duckdb.sql("select x0,x1,y0,y1 from 'rg.parquet' where x0 is not null and x1-x0<90").fetchall()
V = (2.22, 2.47, 48.80, 48.91)
hit = lambda r: r[1] >= V[0] and r[0] <= V[1] and r[3] >= V[2] and r[2] <= V[3]
box = lambda a, b, c, d: [(a, c), (b, c), (b, d), (a, d)]
bg, edge, lit = "#0f1115", "#7d8696", "#ffb000"

fig, ax = plt.subplots(figsize=(16, 9), facecolor=bg)
ax.set_facecolor(bg); ax.set_xlim(-180, 180); ax.set_ylim(-58, 78); ax.set_aspect(1.2); ax.axis("off")
ax.add_collection(PolyCollection([box(*r) for r in rg if not hit(r)], facecolors="none", edgecolors=edge, linewidths=.35))
ax.add_collection(PolyCollection([box(*r) for r in rg if hit(r)], facecolors=lit, edgecolors=lit, linewidths=1))
# inset: Ile-de-France, where the 16 row groups that touch the query box sit
Z = (1.6, 3.1, 48.45, 49.25)
ins = fig.add_axes([0.335, 0.13, 0.22, 0.30], facecolor=bg)
ins.set_xlim(Z[0], Z[1]); ins.set_ylim(Z[2], Z[3]); ins.set_aspect(1.52); ins.set_xticks([]); ins.set_yticks([])
for s_ in ins.spines.values(): s_.set_color(lit)
ins.add_collection(PolyCollection([box(*r) for r in rg if not hit(r)], facecolors="none", edgecolors=edge, linewidths=.6))
ins.add_collection(PolyCollection([box(*r) for r in rg if hit(r)], facecolors=lit, alpha=.35, edgecolors=lit, linewidths=1))
ins.add_patch(plt.Rectangle((V[0], V[2]), V[1] - V[0], V[3] - V[2], fill=False, ec="white", lw=1, ls="--"))
ins.set_title("Paris: the 16 row groups that touch the query box", color=lit, fontsize=10.5, loc="left", backgroundcolor=bg)
ax.add_patch(plt.Rectangle((Z[0], Z[2]), Z[1] - Z[0], Z[3] - Z[2], fill=False, ec=lit, lw=1.2))
from matplotlib.patches import ConnectionPatch
fig.add_artist(ConnectionPatch(xyA=(Z[1], Z[2]), coordsA=ax.transData, xyB=(1, 1), coordsB=ins.transAxes, color=lit, lw=.8))
fig.text(0.02, 0.93, "5,647 row groups, each drawn as the bounding box stored in its Parquet footer", color="white", fontsize=18)
fig.text(0.02, 0.895, "Small boxes where places are dense, large ones where they are sparse. A reader only opens the boxes that touch its query.",
         color="#c9ccd3", fontsize=11.5)
fig.text(0.02, 0.03, "Foursquare Open Source Places (Apache 2.0), Source Cooperative, release 2025-02-06. One catch-all row group spanning the globe is not drawn.",
         color="#8a8f99", fontsize=9.5)
plt.subplots_adjust(left=.01, right=.99, top=.87, bottom=.06)
plt.savefig("day01_world.png", dpi=130, facecolor=bg)
