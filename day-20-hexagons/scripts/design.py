"""
Editorial 4:5 poster: is France really l'Hexagone?

  python design.py world.json   ->  hexagone_post.png (1080x1350)
"""
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPoly
from report import analyse, leaderboard

BG, LAND, EDGE = "#12182b", "#27304d", "#3a4569"
TXT, TXT2, MUTED = "#f5f1e8", "#aab1c6", "#6d7697"
ACC, BAR = "#ffc857", "#3c4770"
SERIF, SANS = "Lora", "Inter"
SKIP = ("Somaliland", "N. Cyprus", "Kosovo", "W. Sahara")


def draw_country(ax, r, k=6, lw=2.4, dots=26, ghost=None):
    c = np.array(r["country"])
    ax.add_patch(MplPoly(c, closed=True, fc=LAND, ec=EDGE, lw=0.8))
    if ghost:  # e.g. the 5-point fit, as a faint dashed outline
        G = np.array(r["anchored"][str(ghost)]["poly"])
        ax.add_patch(MplPoly(G, closed=True, fill=False, ec=TXT2, lw=1.1, ls=(0, (3, 3))))
    P = np.array(r["anchored"][str(k)]["poly"])
    ax.add_patch(MplPoly(P, closed=True, fill=False, ec=ACC, lw=lw, joinstyle="round"))
    ax.scatter(P[:, 0], P[:, 1], s=dots, c=ACC, edgecolors=BG, linewidths=1.2, zorder=4)
    lo, hi = c.min(0), c.max(0); m = 0.07 * (hi - lo).max()
    ax.set_xlim(lo[0] - m, hi[0] + m); ax.set_ylim(lo[1] - m, hi[1] + m)
    ax.set_aspect("equal"); ax.axis("off")


def gain_bars(ax, r, ks=(5, 6, 7, 8), vmax=0.075, labels=True, fs=7.5):
    I = r["_I"]
    g = [I[k] - I[k - 1] for k in ks]
    cols = [ACC if k == 6 else BAR for k in ks]
    ax.bar(range(len(ks)), [min(v, vmax) for v in g], color=cols, width=0.72)
    ax.set_ylim(0, vmax); ax.set_xlim(-0.6, len(ks) - 0.4)
    ax.axis("off")
    if labels:
        for i, (k, v) in enumerate(zip(ks, g)):
            ax.text(i, -0.06 * vmax, f"{k}", ha="center", va="top", fontsize=fs,
                    color=ACC if k == 6 else MUTED, family=SANS)


def poster(rs, out="hexagone_post.png"):
    fr = next(r for r in rs if r["name"] == "France")
    hu = leaderboard(rs, 6)
    tops = [r for r in hu if r["name"] not in SKIP][:8]
    I = fr["_I"]

    fig = plt.figure(figsize=(8, 10), facecolor=BG)
    T = lambda x, y, s, **kw: fig.text(x, y, s, **{"family": SANS, "color": TXT, **kw})

    # header
    T(0.06, 0.952, "L'HEXAGONE?", fontsize=10, color=ACC, weight="bold")
    T(0.06, 0.935, "France isn't much\nof a hexagon.", fontsize=30, family=SERIF,
      weight="bold", va="top", linespacing=1.05)
    T(0.06, 0.815, "Join a country's border points with straight lines. A true hexagon\n"
      "needs its 6th point, and gains almost nothing from a 7th.",
      fontsize=10.5, color=TXT2, va="top", linespacing=1.45)

    # hero: France
    axf = fig.add_axes([0.03, 0.455, 0.52, 0.30], facecolor=BG)
    draw_country(axf, fr, lw=3, dots=60, ghost=5)
    T(0.60, 0.70, f"+{I[6] - I[5]:.3f}", fontsize=40, family=SERIF, weight="bold", color=ACC)
    T(0.60, 0.685, "is all France's 6th point adds\nto the fit: it just splits the\nPyrenees into two corners.",
      fontsize=11, va="top", linespacing=1.4)
    T(0.60, 0.605, f"Its 5th point adds +{I[5] - I[4]:.3f}.\nHungary's 6th adds "
      f"+{hu[0]['_I'][6] - hu[0]['_I'][5]:.3f}.", fontsize=10, color=TXT2, va="top",
      linespacing=1.45)
    axb = fig.add_axes([0.60, 0.465, 0.26, 0.07], facecolor=BG)
    gain_bars(axb, fr, fs=9)
    T(0.60, 0.545, "Fit gained by the 5th–8th point", fontsize=8.5, color=MUTED)
    T(0.06, 0.44, "— best 6-point fit    - - best 5-point fit", fontsize=8.5, color=TXT2)

    # small multiples
    fig.add_artist(plt.Line2D([0.06, 0.94], [0.418], color=EDGE, lw=0.8))
    T(0.06, 0.402, "Countries that really are six-pointed", fontsize=14, family=SERIF,
      weight="bold", va="top")
    w = 0.215
    for i, r in enumerate(tops):
        col, row = i % 4, i // 4
        x0 = 0.06 + col * 0.225
        top = 0.355 - row * 0.16          # name baseline
        T(x0, top, f"{i + 1}  {r['name']}", fontsize=9.5, weight="bold")
        ax = fig.add_axes([x0, top - 0.115, w * 0.66, 0.105], facecolor=BG)
        draw_country(ax, r, lw=1.8, dots=14)
        axg = fig.add_axes([x0 + w * 0.70, top - 0.11, w * 0.26, 0.05], facecolor=BG)
        gain_bars(axg, r, fs=6.5)

    T(0.06, 0.018, "Best convex k-gon with corners on the border, scored by area overlap (IoU). "
      "Bars: fit gained by the 5th–8th point, 6th highlighted.\nNatural Earth 110m, main landmass only. "
      "Ranked by 6th-point gain minus 7th, vs world median.",
      fontsize=6.8, color=MUTED, linespacing=1.4)
    fig.savefig(out, dpi=135, facecolor=BG)
    plt.close(fig)


if __name__ == "__main__":
    rs, _ = analyse(sys.argv[1])
    poster(rs)
    print("wrote hexagone_post.png")
