"""
5-slide 4:5 carousel (1080x1350): pourquoi « l'Hexagone » ?

  python carousel.py   ->  carousel_1.png … carousel_5.png   (needs story.json)
"""
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPoly
from shapely.geometry import Polygon
from design import BG, LAND, EDGE, TXT, TXT2, MUTED, ACC, SERIF, SANS

SEA, GROUND = "#5fb3e8", "#e07a5f"
S = json.load(open("story.json"))
FR = np.array(S["country"])
CL = np.array(S["classic"])                # Pointe Saint-Mathieu, Dunkerque, Lauterbourg, Menton, Cerbère, Hendaye
BEST = np.array(S["best6"])
MINH = np.array(S["min_hex"])
NAMES = S["classic_names"]
# side i goes from corner i to corner i+1
SIDES = [("Manche", SEA), ("Plaines du Nord", GROUND), ("Rhin, Jura, Alpes", GROUND),
         ("Méditerranée", SEA), ("Pyrénées", GROUND), ("Atlantique", SEA)]
country = Polygon(FR)


def stats(P):
    p = Polygon(P); i = country.intersection(p).area
    return 100 * i / country.area, 100 * (p.area - i) / p.area


def slide(n, kicker, title, body, draw, foot=None):
    fig = plt.figure(figsize=(8, 10), facecolor=BG)
    T = lambda x, y, s, **kw: fig.text(x, y, s, **{"family": SANS, "color": TXT, **kw})
    T(0.06, 0.952, kicker, fontsize=10, color=ACC, weight="bold")
    T(0.94, 0.952, f"{n}/5", fontsize=10, color=MUTED, ha="right")
    T(0.06, 0.935, title, fontsize=29, family=SERIF, weight="bold", va="top", linespacing=1.05)
    T(0.06, 0.815, body, fontsize=11.2, color=TXT2, va="top", linespacing=1.5)
    ax = fig.add_axes([0.05, 0.06, 0.90, 0.57], facecolor=BG)
    ax.set_aspect("equal"); ax.axis("off")
    allp = np.vstack([FR, CL, MINH])
    lo, hi = allp.min(0), allp.max(0); pad = 0.10 * (hi - lo).max()
    ax.set_xlim(lo[0] - pad * 1.6, hi[0] + pad * 1.6); ax.set_ylim(lo[1] - pad, hi[1] + pad)
    draw(ax, T)
    T(0.06, 0.03, foot or "France métropolitaine sans la Corse · Natural Earth 1:110m",
      fontsize=7.5, color=MUTED)
    if n < 5:
        T(0.94, 0.03, "→", fontsize=14, color=ACC, ha="right")
    fig.savefig(f"carousel_{n}.png", dpi=135, facecolor=BG)
    plt.close(fig)


def land(ax, alpha=1):
    ax.add_patch(MplPoly(FR, closed=True, fc=LAND, ec=EDGE, lw=0.9, alpha=alpha))


def hexagon(ax, P, colours=None, lw=3.2, ls="-", dots=True, c=ACC):
    for i in range(len(P)):
        a, b = P[i], P[(i + 1) % len(P)]
        ax.plot([a[0], b[0]], [a[1], b[1]], color=colours[i] if colours else c, lw=lw,
                ls=ls, solid_capstyle="round", zorder=3)
    if dots:
        ax.scatter(P[:, 0], P[:, 1], s=70, c=TXT, edgecolors=BG, linewidths=1.6, zorder=4)


def side_labels(ax, P, fs=11):
    cen = P.mean(0)
    for i, (name, col) in enumerate(SIDES):
        a, b = P[i], P[(i + 1) % len(P)]
        mid = (a + b) / 2
        d = b - a; nrm = np.array([d[1], -d[0]]); nrm /= np.linalg.norm(nrm)
        if np.dot(nrm, mid - cen) < 0:
            nrm = -nrm
        q = mid + nrm * 0.075
        ang = np.degrees(np.arctan2(d[1], d[0]))
        if ang > 90: ang -= 180
        if ang < -90: ang += 180
        ax.text(q[0], q[1], name, ha="center", va="center", rotation=ang, rotation_mode="anchor",
                fontsize=fs, color=col, family=SANS, weight="bold")


def corner_labels(ax, P, names, fs=8.5):
    cen = P.mean(0)
    for p, nm in zip(P, names):
        v = p - cen; v /= np.linalg.norm(v)
        q = p + v * 0.06
        ax.text(q[0], q[1], nm, ha="left" if v[0] > 0.3 else "right" if v[0] < -0.3 else "center",
                va="bottom" if v[1] > 0 else "top", fontsize=fs, color=TXT2, family=SANS)


# ---------------------------------------------------------------- slide 1
def s1(ax, T):
    land(ax)
    hexagon(ax, CL, [c for _, c in SIDES])
    side_labels(ax, CL)
slide(1, "POURQUOI « L'HEXAGONE » ?", "Six côtés,\nsix frontières.",
      "Trois façades maritimes, trois frontières terrestres.\n"
      "Chaque côté de l'Hexagone suit une frontière différente.", s1)


# ---------------------------------------------------------------- slide 2
SWITCH = {"Dunkerque": "mer → terre", "Menton": "terre → mer", "Cerbère": "mer → terre",
          "Hendaye": "terre → mer"}
BENDS = {"Pointe Saint-Mathieu": "Manche → Atlantique", "Lauterbourg": "plaine → Rhin"}


def s2(ax, T):
    ax.add_patch(MplPoly(FR, closed=True, fc=LAND, ec="none"))
    for t, pts in S["runs"]:
        P = np.array(pts)
        ax.plot(P[:, 0], P[:, 1], color=SEA if t == "sea" else GROUND, lw=4,
                solid_capstyle="round", solid_joinstyle="round", zorder=3)
    cen = CL.mean(0)
    for p, nm in zip(CL, NAMES):
        sw = nm in SWITCH
        ax.scatter([p[0]], [p[1]], s=150 if sw else 130, marker="o" if sw else "D",
                   facecolors=TXT if sw else ACC, edgecolors=BG, linewidths=2, zorder=5)
        v = p - cen; v /= np.linalg.norm(v); q = p + v * 0.075
        ha = "left" if v[0] > 0.3 else "right" if v[0] < -0.3 else "center"
        if nm == "Pointe Saint-Mathieu":
            q = p + np.array([0.01, -0.06]); ha = "right"
        ax.text(q[0], q[1], f"{nm}\n{SWITCH.get(nm) or BENDS[nm]}", ha=ha,
                va="top" if nm == "Pointe Saint-Mathieu" else ("bottom" if v[1] > 0 else "top"),
                fontsize=9, color=TXT if sw else ACC,
                family=SANS, linespacing=1.3)
    T(0.06, 0.665, "●  la côte devient frontière (ou l'inverse)", fontsize=9.5, color=TXT)
    T(0.52, 0.665, "◆  la frontière tourne franchement", fontsize=9.5, color=ACC)
slide(2, "D'OÙ VIENNENT LES SIX COINS ?", "4 + 2 = 6.",
      "En faisant le tour de la France, on passe de la mer à la terre\n"
      "4 fois. Ajoutez les 2 grands angles, la pointe bretonne et l'Alsace,\n"
      "et on obtient les six sommets de l'Hexagone.", s2)


# ---------------------------------------------------------------- slide 3
cin, cout = stats(CL)
area_ratio = Polygon(MINH).area / Polygon(CL).area


def s3(ax, T):
    ax.add_patch(MplPoly(CL, closed=True, fc=ACC, alpha=0.16, ec="none", zorder=1))
    land(ax)
    hexagon(ax, CL, [c for _, c in SIDES], lw=2.6)
    hexagon(ax, MINH, lw=1.3, ls=(0, (4, 3)), dots=False, c=TXT2)
    T(0.06, 0.655, f"{cin:.0f} %", fontsize=34, family=SERIF, weight="bold", color=TXT)
    T(0.06, 0.633, "de la France tient\ndans l'hexagone", fontsize=10, color=TXT2, va="top")
    T(0.55, 0.655, f"{cout:.0f} %", fontsize=34, family=SERIF, weight="bold", color=ACC)
    T(0.55, 0.633, "de l'hexagone, c'est de la mer\nou un peu des voisins", fontsize=10,
      color=TXT2, va="top")
slide(3, "UN CADRE, PAS UN MOULE", "Il encadre la France.",
      "L'Hexagone englobe presque tout le pays, au prix d'un peu de mer.\n"
      f"En pointillés : le plus petit hexagone qui contient toute la France.\n"
      f"Il n'est que {100 * (area_ratio - 1):.0f} % plus grand.", s3)


# ---------------------------------------------------------------- slide 4
bin_, bout = stats(BEST)


def s4(ax, T):
    land(ax)
    hexagon(ax, CL, lw=1.4, ls=(0, (4, 3)), dots=False, c=TXT2)
    hexagon(ax, BEST, lw=3.2)
    tip = FR[np.argmin(FR[:, 0])]  # westernmost point: Brittany
    ax.annotate("adieu, la pointe\nbretonne", xy=(tip[0] + 0.02, tip[1]),
                xytext=(tip[0] - 0.02, tip[1] + 0.24), fontsize=9.5, color=ACC,
                family=SANS, ha="center", va="bottom",
                arrowprops=dict(arrowstyle="-", color=ACC, lw=1))
    T(0.06, 0.655, f"{bin_:.0f} %", fontsize=34, family=SERIF, weight="bold", color=TXT)
    T(0.06, 0.633, "de la France\ndedans", fontsize=10, color=TXT2, va="top")
    T(0.36, 0.655, f"{bout:.0f} %", fontsize=34, family=SERIF, weight="bold", color=ACC)
    T(0.36, 0.633, "du tracé\ndehors", fontsize=10, color=TXT2, va="top")
    T(0.64, 0.655, "4 / 6", fontsize=34, family=SERIF, weight="bold", color=GROUND)
    T(0.64, 0.633, "côtés qui mélangent\nmer et terre", fontsize=10, color=TXT2, va="top")
slide(4, "ET L'HEXAGONE LE PLUS FIDÈLE ?", "Mieux ajusté,\nmoins parlant.",
      "Cherché par ordinateur, il colle davantage à la forme de la France.\n"
      "Mais il coupe la Bretagne, et ses côtés mélangent mer et terre :\n"
      "ils ne correspondent plus à une seule frontière.", s4)


# ---------------------------------------------------------------- slide 5
def s5(ax, T):
    land(ax, alpha=0.55)
    hexagon(ax, CL, [c for _, c in SIDES])
    side_labels(ax, CL)
    corner_labels(ax, CL, NAMES)
slide(5, "VERDICT", "Pas la forme la\nplus fidèle. La plus juste.",
      "L'Hexagone ne décrit pas la silhouette de la France, il décrit ses\n"
      "frontières : 100 % de chaque côté suit une seule frontière,\n"
      "mer ou terre. Les manuels de géographie avaient vu juste.", s5)
print("ok", round(cin, 1), round(cout, 1), round(bin_, 1), round(bout, 1), round(area_ratio, 3))


# ---------------------------------------------------------------- 16:9 card / social preview
def preview(out="preview.png"):
    fig = plt.figure(figsize=(8, 4.5), facecolor=BG)
    T = lambda x, y, s, **kw: fig.text(x, y, s, **{"family": SANS, "color": TXT, **kw})
    T(0.06, 0.86, "POURQUOI « L'HEXAGONE » ?", fontsize=9, color=ACC, weight="bold")
    T(0.06, 0.80, "Six côtés,\nsix frontières.", fontsize=27, family=SERIF, weight="bold",
      va="top", linespacing=1.05)
    T(0.06, 0.40, "Trois mers, trois frontières terrestres :\nchaque côté suit une seule frontière.",
      fontsize=10, color=TXT2, va="top", linespacing=1.5)
    T(0.06, 0.10, "#30DayMapChallenge · Jour 20 · Hexagones", fontsize=8, color=MUTED)
    ax = fig.add_axes([0.47, 0.03, 0.50, 0.94], facecolor=BG)
    ax.set_aspect("equal"); ax.axis("off")
    land(ax)
    hexagon(ax, CL, [c for _, c in SIDES], lw=2.6)
    side_labels(ax, CL, fs=8.5)
    lo, hi = CL.min(0), CL.max(0); pad = 0.20 * (hi - lo).max()
    ax.set_xlim(lo[0] - pad, hi[0] + pad); ax.set_ylim(lo[1] - pad * 0.6, hi[1] + pad * 0.6)
    fig.savefig(out, dpi=200, facecolor=BG)
    plt.close(fig)


preview()
