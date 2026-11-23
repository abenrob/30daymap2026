"""
Day 23 · Senses: Taste. Five 4:5 slides (1080 x 1350): Saint-Joseph vs Gigondas.

  python slides.py   ->  slide_1.png … slide_5.png
Needs: ap_*.geojson, topo_*.geojson, rpg_*.geojson, dem_*.tif, slope_*.tif, aspect_*.tif,
       mask_*.npy, dem_corridor.tif, rivers.geojson, terrain_stats.json, soil_stats.json,
       climate_stats.json (all written by the 0x scripts).
"""
import json
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.enums import Resampling
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from shapely.geometry import box, Point

BG, LAND, EDGE = "#12182b", "#27304d", "#3a4569"
TXT, TXT2, MUTED = "#f5f1e8", "#aab1c6", "#6d7697"
ACC = "#ffc857"
SERIF, SANS = "Lora", "Inter"
COL = {"Saint-Joseph": "#e0698b", "Gigondas": "#f2a541"}
NS = 5
TER = json.load(open("terrain_stats.json"))
SOIL = json.load(open("soil_stats.json"))
CLIM = json.load(open("climate_stats.json"))
from pyproj import Transformer
_TR = Transformer.from_crs(4326, 2154, always_xy=True)
L = lambda lat, lon: _TR.transform(lon, lat)
SHADE = LinearSegmentedColormap.from_list("sh", [BG, "#4a5478"])


def load(n):
    A = gpd.read_file(f"ap_{n}.geojson").set_crs(2154, allow_override=True).union_all()
    V = pd.concat([gpd.read_file(f"topo_{n}.geojson"), gpd.read_file(f"rpg_{n}.geojson")]) \
        .set_crs(2154, allow_override=True).union_all().buffer(0) & A
    return A, V


GEO = {n: load(n) for n in COL}


def hillshade(z, px, az=315, alt=40, exag=1.0):
    gy, gx = np.gradient(z * exag, px)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    a, b = np.radians(az), np.radians(alt)
    hs = np.sin(b) * np.cos(slope) + np.cos(b) * np.sin(slope) * np.cos(a - aspect)
    return np.clip(hs, 0, 1)


def raster(path, bounds=None, factor=1):
    with rasterio.open(path) as src:
        if bounds is not None:
            win = rasterio.windows.from_bounds(*bounds, transform=src.transform)
        else:
            win = None
        h = int((win.height if win else src.height) / factor)
        w = int((win.width if win else src.width) / factor)
        z = src.read(1, window=win, out_shape=(h, w), resampling=Resampling.average)
        b = rasterio.windows.bounds(win, src.transform) if win else src.bounds
        px = (b[2] - b[0]) / w
    return z, px, (b[0], b[2], b[1], b[3])


def draw_shade(ax, path, bounds=None, factor=1, exag=1.0, alpha=1.0):
    z, px, ext = raster(path, bounds, factor)
    z = np.where(np.isfinite(z), z, np.nanmin(z))
    ax.imshow(hillshade(z, px, exag=exag), cmap=SHADE, extent=ext, origin="upper",
              interpolation="bilinear", alpha=alpha, zorder=0)
    return ext


def draw_geom(ax, g, **kw):
    gpd.GeoSeries([g]).plot(ax=ax, **kw)


def frame(n, kicker, title, body, foot):
    fig = plt.figure(figsize=(8, 10), facecolor=BG)
    T = lambda x, y, s, **kw: fig.text(x, y, s, **{"family": SANS, "color": TXT, **kw})
    T(0.06, 0.952, kicker, fontsize=10, color=ACC, weight="bold")
    T(0.94, 0.952, f"{n}/{NS}", fontsize=10, color=MUTED, ha="right")
    T(0.06, 0.935, title, fontsize=29, family=SERIF, weight="bold", va="top", linespacing=1.05)
    if body:
        T(0.06, 0.815, body, fontsize=11.2, color=TXT2, va="top", linespacing=1.5)
    T(0.06, 0.022, foot, fontsize=7.2, color=MUTED, linespacing=1.4)
    if n < NS:
        T(0.94, 0.022, "→", fontsize=14, color=ACC, ha="right")
    return fig, T


def legend_keys(T, x, y, n, fs=9.5):
    c = COL[n]
    fig = plt.gcf()
    fig.patches.append(plt.Rectangle((x, y - 0.004), 0.022, 0.013, transform=fig.transFigure,
                                     fc=c, ec="none"))
    T(x + 0.03, y, "vines (BD TOPO + RPG 2023)", fontsize=fs, color=TXT2, va="bottom")
    fig.patches.append(plt.Rectangle((x, y - 0.029), 0.022, 0.013, transform=fig.transFigure,
                                     fc=c, alpha=0.30, ec=c, lw=0.8))
    T(x + 0.03, y - 0.025, "allowed by INAO, not planted", fontsize=fs, color=TXT2, va="bottom")


def stat(T, x, y, big, small, c):
    T(x, y, big, fontsize=25, family=SERIF, weight="bold", color=c, va="top")
    T(x, y - 0.042, small, fontsize=9.6, color=TXT2, va="top", linespacing=1.4)


FOOT = ("Vines: IGN BD TOPO (vigne) + RPG 2023, inside the INAO aire parcellaire. "
        "Terrain: IGN RGE ALTI 5 m.\nSoils and parent rock: INRAE Info&Sols / Gis Sol, RRP 1:250 000. "
        "Climate: ERA5-Land via Open-Meteo, 1991–2020.")


# ---------------------------------------------------------------- slide 1: where + contrast
def compass(fig, x, y, r, deg, c):
    """small compass glyph at figure coords, arrow pointing the way the slopes face"""
    ax = fig.add_axes([x - r, y - r * 0.8, 2 * r, 1.6 * r]); ax.set_aspect("equal"); ax.axis("off")
    ax.add_patch(plt.Circle((0, 0), 1, fill=False, ec=EDGE, lw=1))
    ax.text(0, 1.18, "N", ha="center", va="bottom", fontsize=6.5, color=MUTED, family=SANS)
    t = np.radians(deg)
    ax.arrow(-0.55 * np.sin(t), -0.55 * np.cos(t), 1.05 * np.sin(t), 1.05 * np.cos(t), width=0.13,
             head_width=0.5, head_length=0.45, length_includes_head=True, color=c, lw=0)
    ax.set_xlim(-1.3, 1.3); ax.set_ylim(-1.3, 1.6)


def slope_glyph(fig, x, y, w, deg, c):
    ax = fig.add_axes([x, y - 0.012, w, 0.03]); ax.axis("off")
    h = np.tan(np.radians(deg))
    ax.fill([0, 1, 1], [0, 0, h], color=c, alpha=0.9, lw=0)
    ax.plot([0, 1], [0, 0], color=EDGE, lw=1)
    ax.set_xlim(0, 1); ax.set_ylim(0, 0.3); ax.set_aspect("equal")


def slide1():
    fig, T = frame(1, "DAY 23 · SENSES: TASTE", "Same valley, same rank.\nDifferent ground.",
                   "Saint-Joseph and Gigondas are both Rhône crus known for their reds, 120 km apart\n"
                   "on the same river. Measured only where their vines grow, they differ on every count.",
                   "Relief: IGN RGE ALTI at 100 m. Rivers: Natural Earth. Vines: BD TOPO + RPG 2023 inside the INAO aires parcellaires.\n"
                   "Soils: INRAE Info&Sols / Gis Sol. Climate: ERA5-Land / ERA5 via Open-Meteo, 1991–2020. Huglin: growing-season heat index.")
    ax = fig.add_axes([0.03, 0.06, 0.36, 0.70], facecolor=BG)
    ax.set_aspect("equal"); ax.axis("off")
    bx = (805000, 6330000, 900000, 6528000)
    draw_shade(ax, "dem_corridor.tif", exag=2.5)
    r = gpd.read_file("ne_rivers.geojson").to_crs(2154)
    r = r[r.intersects(box(*bx))]
    r.plot(ax=ax, color="#5fb3e8", lw=1.4, alpha=0.85, zorder=2)
    ax.text(*L(44.75, 4.72), "Rhône", fontsize=8, color="#5fb3e8", rotation=80, family=SANS,
            style="italic", ha="center", va="center", zorder=4)
    for n, (A, V) in GEO.items():
        draw_geom(ax, A.buffer(400), fc=COL[n], ec=COL[n], lw=1.2, alpha=0.95, zorder=3)
    towns = {"Lyon": L(45.764, 4.836), "Vienne": L(45.525, 4.874), "Tournon": L(45.067, 4.833),
             "Valence": L(44.933, 4.892), "Montélimar": L(44.558, 4.751), "Orange": L(44.138, 4.807)}
    for t, (x, y) in towns.items():
        ax.plot(x, y, "o", ms=3, color=TXT, zorder=4)
        ax.text(x + 2500, y, t, fontsize=7.8, color=TXT2, family=SANS, va="center", zorder=4)
    ax.text(*L(45.30, 4.90), "Saint-Joseph", fontsize=9.5, color=COL["Saint-Joseph"], family=SANS,
            weight="bold", ha="left", va="center", zorder=5)
    ax.text(*L(44.215, 5.0), "Gigondas", fontsize=9.5, color=COL["Gigondas"], family=SANS,
            weight="bold", ha="center", va="bottom", zorder=5)
    ax.set_xlim(bx[0], bx[2]); ax.set_ylim(bx[1], bx[3])

    # comparison panel
    S, G = TER["Saint-Joseph"]["planted"], TER["Gigondas"]["planted"]
    cs, cg = COL["Saint-Joseph"], COL["Gigondas"]
    x0, xs, xg = 0.43, 0.60, 0.80          # label col, Saint-Joseph col, Gigondas col
    top = 0.735
    T(xs, top, "Saint-Joseph", fontsize=15, family=SERIF, weight="bold", color=cs)
    T(xg, top, "Gigondas", fontsize=15, family=SERIF, weight="bold", color=cg)
    T(xs, top - 0.022, "northern Rhône", fontsize=8.5, color=TXT2)
    T(xg, top - 0.022, "southern Rhône", fontsize=8.5, color=TXT2)
    rows = [0.655, 0.585, 0.505, 0.435, 0.365, 0.290, 0.215, 0.145]
    lab = ["Grape", "Vines face", "Typical slope", "Rock", "Soil", "Heat (Huglin)", "Rain per year", "Vines"]
    for yy, l in zip(rows, lab):
        T(x0, yy, l, fontsize=9.2, color=MUTED, va="center")
        fig.add_artist(plt.Line2D([x0, 0.96], [yy - 0.035, yy - 0.035], color=EDGE, lw=0.6))
    big = dict(fontsize=12, va="center", weight="bold")
    T(xs, rows[0], "Syrah", color=cs, **big); T(xg, rows[0], "Grenache-led", color=cg, **big)
    # facing
    for xc, d, c, txt in [(xs, S["mean_aspect"], cs, "east–SE"), (xg, G["mean_aspect"], cg, "west–NW")]:
        compass(fig, xc + 0.025, rows[1], 0.022, d, c)
        T(xc + 0.058, rows[1], txt, color=c, **big)
    # slope
    for xc, v, c in [(xs, S["slope_med"], cs), (xg, G["slope_med"], cg)]:
        slope_glyph(fig, xc, rows[2], 0.05, v, c)
        T(xc + 0.058, rows[2], f"{v:.0f}°", color=c, **big)
    T(xs, rows[3], "granite, gneiss", color=cs, **big); T(xg, rows[3], "limestone, marl", color=cg, **big)
    T(xs, rows[3] - 0.022, "+ schist, loess", fontsize=8.2, color=TXT2, va="center")
    T(xg, rows[3] - 0.022, "+ old river terraces", fontsize=8.2, color=TXT2, va="center")
    T(xs, rows[4], "acid, sandy", color=cs, **big); T(xg, rows[4], "calcareous", color=cg, **big)
    # bars for heat and rain
    C = CLIM
    for yy, key, unit, vmax in [(rows[5], "huglin", "", 2400), (rows[6], "rain_yr", " mm", 1000)]:
        for xc, n, c in [(xs, "Saint-Joseph", cs), (xg, "Gigondas", cg)]:
            v = C[n]["n"][key]; w = 0.075 * v / vmax
            fig.patches.append(plt.Rectangle((xc, yy - 0.006), w, 0.012, transform=fig.transFigure, fc=c, ec="none"))
            T(xc + w + 0.008, yy, f"{v:,.0f}{unit}", color=c, **big)
    T(xs, rows[7], f"{S['ha']:,} ha", color=cs, **big); T(xg, rows[7], f"{G['ha']:,} ha", color=cg, **big)
    T(xs, rows[7] - 0.022, f"{S['ha'] / GEO['Saint-Joseph'][0].area * 1e4 * 100:.0f}% of allowed", fontsize=8.2, color=TXT2, va="center")
    T(xg, rows[7] - 0.022, f"{G['ha'] / GEO['Gigondas'][0].area * 1e4 * 100:.0f}% of allowed", fontsize=8.2, color=TXT2, va="center")
    fig.savefig("slide_1.png", dpi=135, facecolor=BG); plt.close(fig)


# ---------------------------------------------------------------- slide 2: Saint-Joseph
def slide2():
    n = "Saint-Joseph"; A, V = GEO[n]; t = TER[n]; c = COL[n]
    fig, T = frame(2, "SAINT-JOSEPH", "58 km of steep granite,\nfacing the sunrise.", None, FOOT)
    # full strip
    ax = fig.add_axes([0.03, 0.06, 0.27, 0.70], facecolor=BG)
    ax.set_aspect("equal"); ax.axis("off")
    b = A.bounds; pad = 1200
    bb = (b[0] - 7000, b[1] - pad, b[2] + pad, b[3] + pad)
    draw_shade(ax, f"dem_{n}.tif", bounds=(b[0] - pad, bb[1], bb[2], bb[3]), factor=6, exag=1.5)
    draw_geom(ax, A, fc=c, ec="none", alpha=0.30, zorder=2)
    draw_geom(ax, V, fc=c, ec="none", zorder=3)
    ax.set_xlim(bb[0], bb[2]); ax.set_ylim(bb[1], bb[3])
    for t_, (x, y) in {"Chavanay": L(45.416, 4.726), "Sarras": L(45.188, 4.800),
                       "Tournon": L(45.067, 4.833), "Guilherand": L(44.933, 4.873)}.items():
        ax.text(b[0] - pad - 300, y, t_, fontsize=7.5, color=TXT2, ha="right", va="center", family=SANS)
        ax.plot([b[0] - pad - 150, x], [y, y], color=MUTED, lw=0.5)
    # zoom box around Mauves / Tournon
    cx, cy = L(45.052, 4.822); zw, zh = 4200, 5200
    zb = (cx - zw / 2, cy - zh / 2, cx + zw / 2, cy + zh / 2)
    ax.add_patch(plt.Rectangle((zb[0], zb[1]), zw, zh, fill=False, ec=ACC, lw=1.0, zorder=5))
    az = fig.add_axes([0.31, 0.33, 0.36, 0.43], facecolor=BG)
    az.set_aspect("equal"); az.axis("off")
    draw_shade(az, f"dem_{n}.tif", bounds=zb, factor=1, exag=1.2)
    clip = box(*zb)
    draw_geom(az, A & clip, fc=c, ec=c, lw=0.6, alpha=0.30, zorder=2)
    draw_geom(az, V & clip, fc=c, ec="none", alpha=0.95, zorder=3)
    az.set_xlim(zb[0], zb[2]); az.set_ylim(zb[1], zb[3])
    az.axis("on"); az.set_xticks([]); az.set_yticks([]); az.set_xlabel(""); az.set_ylabel("")
    for sp in az.spines.values():
        sp.set_visible(True); sp.set_color(ACC); sp.set_linewidth(1.4)
    az.text(zb[2] - 150, zb[1] + 250, "Rhône", fontsize=8, color="#5fb3e8", ha="right", family=SANS)
    az.text(zb[0] + 150, zb[3] - 200, "Mauves – Tournon, 4 × 5 km", fontsize=8, color=ACC,
            va="top", family=SANS)
    legend_keys(T, 0.32, 0.295, n)
    # stats
    x = 0.70
    stat(T, x, 0.76, f"{t['planted']['ha']:,} ha", f"of vines in {round(A.area/1e4):,} ha\nallowed: 45% planted", c)
    stat(T, x, 0.61, "East–SE", f"mean facing {t['planted']['mean_aspect']}°.\nThe slopes look across\nthe river at sunrise.", c)
    stat(T, x, 0.455, f"{t['planted']['slope_med']:.0f}°", f"median vine slope.\nThe unplanted half: {t['allowed_empty']['slope_med']:.0f}°,\n"
         f"{t['allowed_empty']['share_ge30']:.0f}% of it steeper than 30°.", c)
    s = SOIL[n]
    stat(T, x, 0.29, f"{s['rock']['Granite & gneiss']:.0f}%", "on granite and gneiss,\n"
         f"{s['rock']['Mica-schist & schist']:.0f}% on schist.\n{s['soil']['ALOCRISOL']:.0f}% acid, sandy soils\n(alocrisols).", c)
    fig.savefig("slide_2.png", dpi=135, facecolor=BG); plt.close(fig)


# ---------------------------------------------------------------- slide 3: Gigondas
def slide3():
    n = "Gigondas"; A, V = GEO[n]; t = TER[n]; c = COL[n]
    fig, T = frame(3, "GIGONDAS", "A gentle fan under\nthe Dentelles, facing west.", None, FOOT)
    ax = fig.add_axes([0.04, 0.33, 0.62, 0.50], facecolor=BG)
    ax.set_aspect("equal"); ax.axis("off")
    b = A.bounds; pad = 600
    bb = (b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad)
    draw_shade(ax, f"dem_{n}.tif", bounds=bb, factor=1, exag=1.2)
    draw_geom(ax, A, fc=c, ec=c, lw=0.6, alpha=0.30, zorder=2)
    draw_geom(ax, V, fc=c, ec="none", alpha=0.95, zorder=3)
    ax.set_xlim(bb[0], bb[2]); ax.set_ylim(bb[1], bb[3])
    ax.add_patch(plt.Rectangle((bb[0], bb[1]), bb[2] - bb[0], bb[3] - bb[1], fill=False, ec=EDGE, lw=1))
    lab = {"Dentelles de Montmirail": (*L(44.178, 5.052), "center"), "Gigondas": (*L(44.164, 5.008), "left"),
           "← Ouvèze": (*L(44.140, 4.968), "left")}
    for s_, (x, y, ha) in lab.items():
        ax.text(x, y, s_, fontsize=8.5, color="#5fb3e8" if "Ouv" in s_ else TXT, ha=ha, va="center",
                family=SANS, style="italic" if "Dent" in s_ else "normal", zorder=6)
    ax.plot(*L(44.164, 5.005), "o", ms=3, color=TXT, zorder=6)
    legend_keys(T, 0.06, 0.30, n)
    # stats in a 2 x 2 grid under / right
    stat(T, 0.70, 0.82, f"{t['planted']['ha']:,} ha", f"of vines in {round(A.area/1e4):,} ha\nallowed: 68% planted", c)
    stat(T, 0.70, 0.68, "West–NW", f"mean facing {t['planted']['mean_aspect']}°.\nToward the Ouvèze valley\nand the afternoon sun.", c)
    stat(T, 0.70, 0.52, f"{t['planted']['slope_med']:.0f}°", f"median vine slope;\n{t['planted']['flat_share']:.0f}% of vines on\nnear-flat ground (< 3°).", c)
    s = SOIL[n]
    stat(T, 0.70, 0.355, f"{s['calcareous_pct']:.0f}%", "on calcareous soils:\nlimestone and marl of the\nDentelles, old river terraces.", c)
    T(0.06, 0.20, "Where the slopes get steep, toward the Dentelles, the vines stop:\n"
      f"the unplanted third of the allowed area has a median slope of {t['allowed_empty']['slope_med']:.0f}°\n"
      f"and sits {t['allowed_empty']['alt_med'] - t['planted']['alt_med']} m higher than the vines.",
      fontsize=10.5, color=TXT, va="top", linespacing=1.5)
    fig.savefig("slide_3.png", dpi=135, facecolor=BG); plt.close(fig)


# ---------------------------------------------------------------- slide 4: the ground
def rose(ax, vals, c):
    th = np.radians(np.arange(0, 360, 45))
    ax.set_theta_zero_location("N"); ax.set_theta_direction(-1)
    ax.bar(th, vals, width=np.radians(40), color=c, alpha=0.95, edgecolor="none")
    ax.set_facecolor(BG); ax.set_ylim(0, 30)
    ax.set_yticks([10, 20, 30]); ax.set_yticklabels([])
    ax.set_xticks(th); ax.set_xticklabels(["N", "NE", "E", "SE", "S", "SW", "W", "NW"], color=TXT2,
                                          fontsize=8, family=SANS)
    ax.tick_params(pad=-1)
    ax.grid(color=EDGE, lw=0.6); ax.spines["polar"].set_color(EDGE)


def slide4():
    fig, T = frame(4, "THE GROUND", "Opposite slopes,\nopposite rocks.",
                   "Share of each appellation's vines, by facing direction, slope and parent rock.", FOOT)
    for i, n in enumerate(COL):
        r = TER[n]["planted"]["rose"]
        ax = fig.add_axes([0.08 + i * 0.46, 0.54, 0.36, 0.19], projection="polar")
        rose(ax, [r[k] for k in ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]], COL[n])
        T(0.26 + i * 0.46, 0.758, n, fontsize=14, family=SERIF, weight="bold", color=COL[n], ha="center")
    T(0.5, 0.495, "Facing direction of all vines on slopes ≥ 3° (rings: 10, 20, 30% of vines)", ha="center", fontsize=8.2, color=MUTED)
    # slope distribution
    ax = fig.add_axes([0.08, 0.27, 0.40, 0.18], facecolor=BG)
    bins = np.arange(0, 46, 3)
    for n in COL:
        sl = rasterio.open(f"slope_{n}.tif").read(1); m = np.load(f"mask_{n}.npy")[1]
        h, _ = np.histogram(np.clip(sl[m], 0, 44.9), bins=bins)
        ax.step(bins[:-1], np.r_[h] / h.sum() * 100, where="post", color=COL[n], lw=2)
        ax.fill_between(bins[:-1], h / h.sum() * 100, step="post", color=COL[n], alpha=0.15)
    ax.set_facecolor(BG); ax.tick_params(colors=TXT2, labelsize=8)
    for s in ax.spines.values(): s.set_color(EDGE)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_xlabel("slope (°)", color=TXT2, fontsize=8.5, family=SANS)
    ax.set_ylabel("% of vines", color=TXT2, fontsize=8.5, family=SANS)
    ax.set_xlim(0, 45)
    T(0.06, 0.475, "Slope", fontsize=12, family=SERIF, weight="bold")
    # rock bars
    T(0.54, 0.475, "Parent rock", fontsize=12, family=SERIF, weight="bold")
    rocks = [("Granite & gneiss", "#9aa7c7"), ("Mica-schist & schist", "#6f7da3"),
             ("Loess", "#d9c9a3"), ("River terraces & alluvium", "#b38b59"),
             ("Sandy marl & calcarenite (Miocene)", "#e3b778"), ("Limestone & marl (Triassic–Jurassic)", "#f2ead3")]
    ax = fig.add_axes([0.54, 0.33, 0.40, 0.12], facecolor=BG)
    for i, n in enumerate(COL):
        left = 0
        for k, cc in rocks:
            v = SOIL[n]["rock"].get(k, 0)
            ax.barh(1 - i, v, left=left, color=cc, height=0.6, edgecolor=BG, lw=1)
            left += v
        ax.text(-2, 1 - i, n, ha="right", va="center", fontsize=8.5, color=COL[n], family=SANS, weight="bold")
    ax.set_xlim(0, 100); ax.axis("off")
    for j, (k, cc) in enumerate(rocks):
        yy = 0.305 - (j % 3) * 0.022; xx = 0.54 + (j // 3) * 0.20
        fig.patches.append(plt.Rectangle((xx, yy), 0.014, 0.011, transform=fig.transFigure, fc=cc))
        T(xx + 0.02, yy, k.replace(" (Miocene)", "").replace(" (Triassic–Jurassic)", ""), fontsize=7.4, color=TXT2)
    sj, gg = TER["Saint-Joseph"]["planted"], TER["Gigondas"]["planted"]
    T(0.06, 0.20, f"Saint-Joseph's vines face east and south-east, {sj['share_ge15']:.0f}% of them on slopes of 15° or more,\n"
      f"on acid granite sand. Gigondas faces west, {gg['flat_share']:.0f}% near-flat, on limestone, marl\n"
      "and old river terraces.", fontsize=10.2, color=TXT, va="top", linespacing=1.5)
    fig.savefig("slide_4.png", dpi=135, facecolor=BG); plt.close(fig)


# ---------------------------------------------------------------- slide 5: the sky
def slide5():
    fig, T = frame(5, "THE SKY", "400 points apart,\nboth warming.",
                   "Huglin index: growing-season heat (April–September) that viticulturists\n"
                   "use to say which grapes can ripen where. Dashed: linear trend.",
                   "Huglin index from ERA5-Land daily temperature via Open-Meteo, at the vines' median elevation;\n"
                   "Saint-Joseph = mean of 3 points along the strip. Rain: ERA5. Classes: Tonietto & Carbonneau (2004).")
    H = CLIM["hi_by_year"]; y = np.array(H["years"])
    ax = fig.add_axes([0.10, 0.37, 0.74, 0.36], facecolor=BG)
    bands = [(1500, 1800, "temperate"), (1800, 2100, "warm temperate"), (2100, 2400, "warm"), (2400, 2900, "very warm")]
    for i, (lo, hi, lab) in enumerate(bands):
        ax.axhspan(lo, hi, color=EDGE if i % 2 else LAND, alpha=0.35, lw=0)
        ax.text(2025.0, (lo + min(hi, 2800)) / 2, lab, fontsize=7.8, color=MUTED, va="center", family=SANS)
    TR = {}
    for n in COL:
        v = np.array(H[n], float)
        ax.plot(y, v, color=COL[n], lw=2.2, marker="o", ms=3)
        b = np.polyfit(y, v, 1)
        ax.plot(y, np.polyval(b, y), color=COL[n], lw=1.3, ls=(0, (4, 3)), alpha=0.9)
        TR[n] = b[0] * 10
        ax.text(1991.4, 2740 if n == "Gigondas" else 1450, f"{n}  +{TR[n]:.0f} per decade", color=COL[n],
                fontsize=9, ha="left", va="center", family=SANS, weight="bold")
    ax.set_xlim(1991, 2024.6); ax.set_ylim(1400, 2800)
    ax.tick_params(colors=TXT2, labelsize=8)
    for s in ax.spines.values(): s.set_color(EDGE)
    ax.spines[["top", "right"]].set_visible(False)
    sj = np.array(H["Saint-Joseph"]); gg = np.array(H["Gigondas"])
    ax.annotate("2003", (2003, sj[y == 2003][0]), xytext=(2003.6, 2560), color=TXT2, fontsize=8,
                arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.7), family=SANS)
    S, G = CLIM["Saint-Joseph"], CLIM["Gigondas"]
    rows = [("Huglin index, 1991–2020", f"{S['n']['huglin']:,.0f}", f"{G['n']['huglin']:,}"),
            ("Huglin index, 2015–2024", f"{S['r']['huglin']:,.0f}", f"{G['r']['huglin']:,}"),
            ("Rain per year", f"{S['n']['rain_yr']:.0f} mm", f"{G['n']['rain_yr']} mm"),
            ("July mean daily max", f"{S['n']['jul_tmax']:.1f} °C", f"{G['n']['jul_tmax']} °C"),
            ("Summer days ≥ 35 °C (2015–24)", f"{S['r']['days35_summer']:.0f}", f"{G['r']['days35_summer']:.0f}")]
    y0 = 0.30
    T(0.56, y0 + 0.012, "Saint-Joseph", fontsize=9, color=COL["Saint-Joseph"], weight="bold", ha="right")
    T(0.80, y0 + 0.012, "Gigondas", fontsize=9, color=COL["Gigondas"], weight="bold", ha="right")
    for i, (k, a, b) in enumerate(rows):
        yy = y0 - 0.03 * (i + 1)
        T(0.10, yy, k, fontsize=9.6, color=TXT2)
        T(0.56, yy, a, fontsize=9.6, ha="right"); T(0.80, yy, b, fontsize=9.6, ha="right")
    T(0.06, 0.105, f"Saint-Joseph's last ten years ({S['r']['huglin']:,.0f}) are about as warm as Gigondas in the 1990s "
      f"({np.mean(gg[y <= 2000]):,.0f}).", fontsize=10.2, color=TXT, va="top")
    fig.savefig("slide_5.png", dpi=135, facecolor=BG); plt.close(fig)


if __name__ == "__main__":
    for f in (slide1, slide2, slide3, slide4, slide5):
        f(); print(f.__name__)
