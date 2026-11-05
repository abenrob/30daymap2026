"""Post images, 1080 x 1350 (4:5), one file each:
  fig_count.png     turbines visible per 50 m cell (Blender), over a hillshade, turbines as dots
  fig_compare.png   one turbine: Blender vs gdal_viewshed, agreement classes
  fig_curvature.png turbines lost per cell once curvature + refraction are applied (gdal, cc 0 vs 0.85714)
Run from the workspace root after 04 to 07.
"""
import json
import numpy as np
import rasterio
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource, ListedColormap
from PIL import Image

D = "work/data/day-05-sight"
OUT = f"{D}/renders"
meta = json.load(open(f"{D}/blender/meta.json"))
T = json.load(open(f"{D}/blender/turbines.json"))
z = np.load(f"{D}/blender/dem_50m.npy")
H, W = z.shape
RES, half = meta["res"], int(meta["range_m"] / meta["res"])
cmp0 = json.load(open(f"{D}/derived/compare_cc0.json"))
BG, FG, MUTED = "#0d0f14", "#e8e6e1", "#8a8f99"
plt.rcParams.update({"font.family": "DejaVu Sans", "text.color": FG, "axes.labelcolor": FG,
                     "xtick.color": MUTED, "ytick.color": MUTED})
hs = LightSource(315, 40).hillshade(z, vert_exag=1.5, dx=RES, dy=RES)

def frame(title, sub):
    fig = plt.figure(figsize=(10.8, 13.5), dpi=100, facecolor=BG)
    fig.text(0.05, 0.955, title, fontsize=25, weight="bold", va="top")
    fig.text(0.05, 0.915, sub, fontsize=14.5, color=MUTED, va="top", linespacing=1.4)
    return fig

def foot(fig, txt):
    fig.text(0.05, 0.025, txt, fontsize=10.5, color=MUTED, va="bottom", linespacing=1.4)

# 1. count map ---------------------------------------------------------------------------
cb = rasterio.open(f"{D}/derived/count_blender.tif").read(1).astype(float)
fig = frame("How many wind turbines can you see from here?",
            f"Ardèche and Drôme, {len(T)} turbines, blade tips seen from eye height (1.7 m),\n"
            f"up to 20 km away, bare-earth terrain. One Cycles ray-traced render per turbine.")
ax = fig.add_axes([0.03, 0.15, 0.94, 0.73])
ax.imshow(hs, cmap="gray", vmin=-0.1, vmax=1.6, interpolation="lanczos")
cm = plt.get_cmap("magma")
m = np.ma.masked_equal(cb, 0)
im = ax.imshow(m, cmap=cm, vmin=1, vmax=45, alpha=0.85, interpolation="nearest")
ax.scatter([t["col"] for t in T], [t["row"] for t in T], s=6, c="#5ee6ff", lw=0)
ax.set_axis_off()
cax = fig.add_axes([0.25, 0.115, 0.5, 0.012])
cbar = fig.colorbar(im, cax=cax, orientation="horizontal", extend="max")
cbar.set_label("turbines visible (cyan dots: turbines)", color=MUTED, fontsize=12)
cbar.outline.set_visible(False)
foot(fig, "Terrain: IGN RGE ALTI via Géoplateforme, 50 m. Turbines: © OpenStreetMap contributors (ODbL).\n"
          "Earth curvature not modelled. #30DayMapChallenge day 5, Senses: sight. Adam Roberts")
fig.savefig(f"{OUT}/fig_count.png", facecolor=BG)
plt.close(fig)

# 2. Blender vs GDAL for one turbine --------------------------------------------------------
pick = next(r for r in sorted(cmp0["turbines"], key=lambda r: r["agree_pct"])
            if r["agree_pct"] >= cmp0["summary"]["total"]["agree_pct"])
t = next(t for t in T if t["id"] == pick["id"])
b = np.array(Image.open(f"{D}/renders/blender/{t['id']}.png")) > 127
with rasterio.open(f"{D}/renders/gdal_cc0/{t['id']}.tif") as g:
    gg = g.read(1)[:2 * half, :2 * half] == 255
yy, xx = np.mgrid[-half:half, -half:half]
disc = (xx ** 2 + yy ** 2) * RES ** 2 <= meta["range_m"] ** 2
cls = np.zeros(b.shape, np.uint8)                     # 0 out of range
cls[disc] = 1                                         # hidden in both
cls[disc & b & gg] = 2
cls[disc & b & ~gg] = 3
cls[disc & ~b & gg] = 4
r0, c0 = t["row"] - half, t["col"] - half
hsw = hs[r0:r0 + 2 * half, c0:c0 + 2 * half]
los = json.load(open(f"{D}/derived/los_check.json"))
tot = cmp0["summary"]["total"]
fig = frame("Same answer from a renderer and from GDAL",
            f"One {t['tip_m']:.0f} m turbine, 20 km radius, flat earth in both. Blender Cycles and\n"
            f"gdal_viewshed agree on {pick['agree_pct']:.1f}% of cells here, "
            f"{tot['agree_pct']:.1f}% over all {cmp0['summary']['n']} turbines.")
ax = fig.add_axes([0.06, 0.15, 0.88, 0.70])
ax.imshow(hsw, cmap="gray", vmin=-0.1, vmax=1.6)
cols = ListedColormap([(0, 0, 0, 0), (0, 0, 0, 0.35), (0.99, 0.75, 0.35, 0.75),
                       (0.2, 0.85, 1.0, 1), (1.0, 0.25, 0.45, 1)])
ax.imshow(cls, cmap=cols, vmin=0, vmax=4, interpolation="nearest")
ax.plot(half, half, marker="^", ms=12, color="white", mec="black")
ax.set_axis_off()
for i, (lab, col) in enumerate([("visible in both", (0.99, 0.75, 0.35)),
                                ("Blender only", (0.2, 0.85, 1.0)),
                                ("GDAL only", (1.0, 0.25, 0.45))]):
    fig.patches.append(plt.Rectangle((0.06 + i * 0.3, 0.1), 0.02, 0.016, color=col,
                                     transform=fig.transFigure))
    fig.text(0.09 + i * 0.3, 0.108, lab, fontsize=13, va="center")
foot(fig, f"Where they disagree, an exact line-of-sight check on a bilinear surface sides with Blender in "
          f"{los['blender_only']['exact_says_visible_pct']:.0f}% of Blender-only cells\n"
          f"and with GDAL in {los['gdal_only']['exact_says_visible_pct']:.0f}% of GDAL-only cells: "
          f"edge cells, decided by how the surface is drawn between 50 m posts.")
fig.savefig(f"{OUT}/fig_compare.png", facecolor=BG)
plt.close(fig)

# 3. curvature ---------------------------------------------------------------------------
c0g = rasterio.open(f"{D}/derived/count_gdal_cc0.tif").read(1).astype(int)
c8g = rasterio.open(f"{D}/derived/count_gdal_cc0.85714.tif").read(1).astype(int)
drop = c0g - c8g
lost = 100 * (1 - c8g.sum() / c0g.sum())
fig = frame("What a flat scene gets wrong",
            f"Turbines that drop out of sight once Earth curvature and refraction are applied\n"
            f"(gdal_viewshed -cc 0.85714 vs 0). {lost:.1f}% of all sightings, "
            f"up to {drop.max()} turbines in one cell.")
ax = fig.add_axes([0.03, 0.15, 0.94, 0.73])
ax.imshow(hs, cmap="gray", vmin=-0.1, vmax=1.6, interpolation="lanczos")
im = ax.imshow(np.ma.masked_less_equal(drop, 0), cmap="viridis", vmin=1, vmax=10, interpolation="nearest")
ax.scatter([t["col"] for t in T], [t["row"] for t in T], s=6, c="white", lw=0)
ax.set_axis_off()
cax = fig.add_axes([0.25, 0.115, 0.5, 0.012])
cbar = fig.colorbar(im, cax=cax, orientation="horizontal", extend="max")
cbar.set_label("turbines lost per cell", color=MUTED, fontsize=12)
cbar.outline.set_visible(False)
foot(fig, "At 20 km a flat model is about 27 m too generous (d² / 2R, less 1/7 for refraction).\n"
          "Blender renders a flat scene, so this is the gap in the ray-traced version.")
fig.savefig(f"{OUT}/fig_curvature.png", facecolor=BG)
plt.close(fig)
print("turbine for fig_compare:", t["id"], pick)
