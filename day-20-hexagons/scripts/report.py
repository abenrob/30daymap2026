"""
"Points of the star" ranking from world.json (needs anchored.py run).

For each country, the best convex k-gon with corners ON the border
(k = 3..9). Gain g_k = IoU_k - IoU_(k-1); drop_k = g_k - g_(k+1) says
"the k-th point pays, the (k+1)-th doesn't". excess_k = drop_k minus the
world median drop_k (removes the universal shape of the curve).

  natural points = argmax_k excess_k            (k = 4..8)
  hexagon index  = excess_6

Leaderboards only include countries the k-gon actually describes
(IoU_k >= 0.85) and whose natural number of points is k.

  python report.py world.json
"""
import csv, json, sys
from collections import Counter
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPoly

SURF, INK, INK2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8984"
LAND, FIT = "#e4e3df", "#2a78d6"
MIN_VERTS, MIN_FIT, KS = 12, 0.85, range(4, 9)


def analyse(path):
    rs = [r for r in json.load(open(path)) if r["n_vertices"] >= MIN_VERTS]
    for r in rs:
        I = {int(k): v["iou"] for k, v in r["anchored"].items()}
        g = {k: I[k] - I[k - 1] for k in range(4, 10)}
        r["_I"], r["_drop"] = I, {k: g[k] - g[k + 1] for k in KS}
    med = {k: float(np.median([r["_drop"][k] for r in rs])) for k in KS}
    for r in rs:
        ex = {k: r["_drop"][k] - med[k] for k in KS}
        r["excess"] = ex
        r["natural_points"] = max(ex, key=ex.get)
        r["hexagon_index"] = ex[6]
    return rs, med


def leaderboard(rs, k):
    sel = [r for r in rs if r["natural_points"] == k and r["_I"][k] >= MIN_FIT]
    return sorted(sel, key=lambda r: -r["excess"][k])


def write_csv(rs, path="ranking.csv"):
    hexes = leaderboard(rs, 6)
    rank = {r["name"]: i for i, r in enumerate(hexes, 1)}
    cols = ["name", "iso", "continent", "natural_points", "hexagon_rank", "hexagon_index"] + \
           [f"iou_{k}pt" for k in range(3, 10)] + ["regular_hex_iou", "hexagonity_regular"]
    with open(path, "w", newline="") as f:
        w = csv.writer(f); w.writerow(cols)
        for r in sorted(rs, key=lambda r: -r["hexagon_index"]):
            w.writerow([r["name"], r["iso"], r["continent"], r["natural_points"],
                        rank.get(r["name"], ""), round(r["hexagon_index"], 4)] +
                       [round(r["_I"][k], 4) for k in range(3, 10)] +
                       [r["hex_iou"], r["hexagonity"]])


def grid(rs, k, title, sub, out, extra=None, cols=6):
    show = rs[: 18 - (1 if extra else 0)] + ([extra] if extra else [])
    rows = int(np.ceil(len(show) / cols))
    H = 2.6 * rows + 1.6
    fig, axs = plt.subplots(rows, cols, figsize=(13, H), facecolor=SURF)
    fig.subplots_adjust(top=1 - 1.6 / H, bottom=0.02, hspace=0.5, wspace=0.1)
    fig.text(0.02, 1 - 0.45 / H, title, fontsize=16, weight="bold", color=INK)
    fig.text(0.02, 1 - 0.8 / H, sub, fontsize=11, color=INK2)
    for ax in np.ravel(axs):
        ax.axis("off")
    for i, (ax, r) in enumerate(zip(np.ravel(axs), show)):
        c = np.array(r["country"])
        P = np.array(r["anchored"][str(k)]["poly"])
        ax.add_patch(MplPoly(c, closed=True, fc=LAND, ec="#b9b8b2", lw=0.6))
        ax.add_patch(MplPoly(P, closed=True, fill=False, ec=FIT, lw=1.6))
        ax.scatter(P[:, 0], P[:, 1], s=16, c=FIT, edgecolors=SURF, linewidths=1, zorder=3)
        lo, hi = c.min(0), c.max(0); m = 0.06 * (hi - lo).max()
        ax.set_xlim(lo[0] - m, hi[0] + m); ax.set_ylim(lo[1] - m, hi[1] + m)
        ax.set_aspect("equal")
        hl = extra is not None and r is extra
        lab = f"#{i + 1}" if not hl else "for comparison"
        ax.set_title(f"{r['name']}\n{lab} · fit {r['_I'][k]:.2f} · +{r['excess'][k]:.3f}",
                     fontsize=10, color=INK if hl else INK2, weight="bold" if hl else "normal")
    fig.savefig(out, dpi=110, facecolor=SURF)
    plt.close(fig)


if __name__ == "__main__":
    rs, med = analyse(sys.argv[1])
    write_csv(rs)
    fr = next(r for r in rs if r["name"] == "France")
    hexes, pents = leaderboard(rs, 6), leaderboard(rs, 5)
    grid(hexes, 6, "The world's six-pointed countries",
         "Best convex hexagon with its corners on the border. Ranked by how much the 6th point "
         "helps beyond the 7th (above the world median). France's natural count is 5.",
         "top_hexagons.png", extra=fr)
    pr = [r["name"] for r in pents].index("France") + 1 if fr in pents else None
    grid(pents, 5, "The world's five-pointed countries",
         f"Same test with five border points. France ranks {pr} of {len(pents)}.",
         "top_pentagons.png", extra=None if (pr and pr <= 18) else fr)
    print("median drop:", {k: round(v, 4) for k, v in med.items()})
    print("natural points:", sorted(Counter(r["natural_points"] for r in rs).items()))
    print("hexagons:", len(hexes), [r["name"] for r in hexes[:12]])
    print("pentagons:", len(pents), [r["name"] for r in pents[:12]], "France rank", pr)
    print("France", {k: round(v, 4) for k, v in fr["_I"].items()}, fr["natural_points"])


def poster(rs, fr, out="hexagone_post.png", n=8, cols=3,
           skip=("Somaliland", "N. Cyprus", "Kosovo", "W. Sahara")):
    """4:5 portrait (1080x1350) for social: top n six-pointed countries
    plus France as the comparison tile."""
    show = [r for r in rs if r["name"] not in skip][:n] + [fr]
    rows = int(np.ceil(len(show) / cols))
    W, H = 8.0, 10.0
    fig, axs = plt.subplots(rows, cols, figsize=(W, H), facecolor=SURF)
    fig.subplots_adjust(left=0.04, right=0.96, top=0.76, bottom=0.05, hspace=0.38, wspace=0.12)
    fig.text(0.05, 0.955, "Is France really l'Hexagone?", fontsize=19, weight="bold", color=INK)
    fig.text(0.05, 0.918, "Join a country's border points with straight lines. Which countries "
             "are best\ndescribed by exactly six points, where the 6th matters and a 7th doesn't?",
             fontsize=10.5, color=INK2, va="top", linespacing=1.4)
    fig.text(0.05, 0.84, f"France fits better as a pentagon: its 6th point adds only "
             f"{fr['_I'][6] - fr['_I'][5]:.3f} to the fit.", fontsize=10.5, color=INK, va="top")
    for ax in np.ravel(axs):
        ax.axis("off")
    for i, (ax, r) in enumerate(zip(np.ravel(axs), show)):
        c = np.array(r["country"]); P = np.array(r["anchored"]["6"]["poly"])
        hl = r is fr
        ax.add_patch(MplPoly(c, closed=True, fc=LAND, ec="#b9b8b2", lw=0.6))
        ax.add_patch(MplPoly(P, closed=True, fill=False, ec=FIT, lw=1.8))
        ax.scatter(P[:, 0], P[:, 1], s=18, c=FIT, edgecolors=SURF, linewidths=1, zorder=3)
        lo, hi = c.min(0), c.max(0); m = 0.06 * (hi - lo).max()
        ax.set_xlim(lo[0] - m, hi[0] + m); ax.set_ylim(lo[1] - m, hi[1] + m)
        ax.set_aspect("equal")
        head = "France (comparison)" if hl else f"{i + 1}. {r['name']}"
        ax.set_title(f"{head}\nfit {r['_I'][6]:.2f} · 6th-point bonus {r['excess'][6]:+.3f}",
                     fontsize=9.5, color=INK if hl else INK2, weight="bold" if hl else "normal",
                     linespacing=1.3)
    fig.text(0.05, 0.018, "Best convex 6-gon with corners on the border · fit = IoU · bonus = gain of "
             "6th point minus 7th, vs world median · Natural Earth 110m, main landmass",
             fontsize=7.5, color=MUTED)
    fig.savefig(out, dpi=135, facecolor=SURF)
    plt.close(fig)


if __name__ == "__main__":
    poster(hexes, fr)
