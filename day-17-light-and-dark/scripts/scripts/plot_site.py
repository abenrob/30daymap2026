"""Static maps for the real-site run (reads outputs/, kept separate from the model)."""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd, rasterio, yaml
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap, LightSource
from matplotlib.collections import PolyCollection
from matplotlib.lines import Line2D
ROOT = Path(__file__).resolve().parents[1]
cfg = yaml.safe_load(open(ROOT / "config.yaml")); pre = cfg["site_run"]["out_prefix"]; out = ROOT / "outputs"
thr_h, thr_m = cfg["thresholds"]["annual_hours"], cfg["thresholds"]["daily_minutes"]

def rd(name):
    with rasterio.open(out / f"{pre}_{name}.tif") as ds:
        return ds.read(1), ds.transform
H, tf = rd("annual_hours"); Hf, _ = rd("annual_hours_noocc"); M, _ = rd("max_daily_minutes")
Mf, _ = rd("max_daily_minutes_noocc"); Dr, _ = rd("annual_hours_occlusion_removed")
ny, nx = H.shape
gext = [tf.c, tf.c + nx * tf.a, tf.f + ny * tf.e, tf.f]
Xc = tf.c + (np.arange(nx) + 0.5) * tf.a; Yc = tf.f + (np.arange(ny) + 0.5) * tf.e

with rasterio.open(ROOT / cfg["dem"]["path"]) as ds:
    dz = ds.read(1); dt = ds.transform
margin = 300
win = [gext[0] - margin, gext[1] + margin, gext[2] - margin, gext[3] + margin]
c0 = int((win[0] - dt.c) / dt.a); c1 = int((win[1] - dt.c) / dt.a); r0 = int((dt.f - win[3]) / 5); r1 = int((dt.f - win[2]) / 5)
dz = dz[r0:r1, c0:c1]
ext = [dt.c + c0 * 5, dt.c + c1 * 5, dt.f - r1 * 5, dt.f - r0 * 5]
hs = LightSource(azdeg=315, altdeg=40).hillshade(dz, vert_exag=2, dx=5, dy=5)

tur = json.load(open(out / f"{pre}_turbines_used.json"))
alltur = pd.read_csv(ROOT / cfg["site_run"]["turbines_csv"])
rec = pd.read_csv(out / f"{pre}_receptors.csv")
bj = json.load(open(ROOT / cfg["site_run"]["buildings"]))
polys = []
for f in bj["features"]:
    for poly in f["geometry"]["coordinates"]:
        polys.append(np.array(poly[0])[:, :2])

def base(ax, title):
    ax.imshow(hs, extent=ext, cmap="gray", vmin=0, vmax=1.2, origin="upper", zorder=0)
    ax.add_collection(PolyCollection(polys, facecolors="#b9b2a8", edgecolors="none", alpha=0.8, zorder=2))
    ax.set_xlim(win[0], win[1]); ax.set_ylim(win[2], win[3]); ax.set_aspect("equal")
    ax.set_xlabel("Lambert-93 E (m)"); ax.set_ylabel("Lambert-93 N (m)"); ax.set_title(title, fontsize=11)
    ax.ticklabel_format(style="plain", useOffset=False); ax.tick_params(labelsize=7)

def turbines(ax):
    used = {t["id"] for t in tur}
    for _, a in alltur.iterrows():
        if a.id in used:
            ax.plot(a.x_l93, a.y_l93, "^", color="k", mfc="white", ms=8, mew=1.4, zorder=6)
            ax.annotate(a.id, (a.x_l93, a.y_l93), xytext=(4, 5), textcoords="offset points", fontsize=7, zorder=7,
                        bbox=dict(fc="white", ec="none", alpha=0.6, pad=0.5))
        elif win[0] < a.x_l93 < win[1] and win[2] < a.y_l93 < win[3]:
            ax.plot(a.x_l93, a.y_l93, "^", color="0.4", mfc="none", ms=7, zorder=6)

def receptors(ax, occ=True):
    fh = rec.flag_30h if occ else rec.flag_30h_noocc
    fm = rec.flag_30min if occ else rec.flag_30min_noocc
    h = rec.annual_hours if occ else rec.annual_hours_noocc
    cat = np.where(fh & fm, 3, np.where(fh, 1, np.where(fm, 2, np.where(h > 0, 4, 0))))
    st = {0: ("#555555", 8, 1.0), 4: ("#2b83ba", 22, 1.0), 1: ("#fd8d3c", 38, 1.0), 2: ("#7b3294", 38, 1.0), 3: ("#d7191c", 46, 1.0)}
    for k, (col, s, _) in st.items():
        m = cat == k
        if m.any():
            ax.scatter(rec.x[m], rec.y[m], s=s, c=col, edgecolors="k" if k else "none", linewidths=0.5, zorder=5)
    return [Line2D([], [], marker="o", ls="", color="#555555", ms=3, label="receptor, no flicker"),
            Line2D([], [], marker="o", ls="", color="#2b83ba", mec="k", ms=5, label="flicker, below limits"),
            Line2D([], [], marker="o", ls="", color="#fd8d3c", mec="k", ms=6, label=f"> {thr_h} h/yr"),
            Line2D([], [], marker="o", ls="", color="#7b3294", mec="k", ms=6, label=f"> {thr_m} min/day"),
            Line2D([], [], marker="o", ls="", color="#d7191c", mec="k", ms=6, label="both"),
            Line2D([], [], marker="^", ls="", color="k", mfc="white", ms=7, label="turbine (modelled)"),
            Line2D([], [], marker="^", ls="", color="0.4", mfc="none", ms=7, label="turbine (excluded)")], cat

def stepped(ax, A, bounds, cmap_name, label, fig, extra_cb=True):
    n = len(bounds) - 1
    cols = plt.get_cmap(cmap_name)(np.linspace(0.12, 1.0, n))
    cmap = ListedColormap(cols); norm = BoundaryNorm(bounds, n)
    im = ax.imshow(np.ma.masked_less_equal(A, 0), extent=gext, origin="upper", cmap=cmap, norm=norm, alpha=0.78, zorder=1,
                   interpolation="nearest")
    cb = fig.colorbar(im, ax=ax, shrink=0.7, pad=0.02, ticks=bounds[:-1] if False else bounds)
    cb.set_label(label); cb.ax.tick_params(labelsize=7)
    return im

def finish(fig, ax, path, legend):
    ax.legend(handles=legend, loc="lower left", fontsize=7, framealpha=0.9)
    fig.tight_layout(); fig.savefig(path, dpi=140); plt.close(fig)

hb = [0, 1, 5, 10, 20, 30, 50, 100, 200, 500, 2000]
mb = [0, 10, 20, 30, 45, 60, 90, 120, 180, 300, 600]

# 1) annual hours
fig, ax = plt.subplots(figsize=(9.5, 8.5)); base(ax, f"Worst-case annual shadow flicker (terrain occlusion ON), 2025\n8 turbines; black contour = {thr_h} h/yr; receptors = dwellings")
stepped(ax, H, hb, "YlOrRd", "flicker hours per year (stepped)", fig)
ax.contour(Xc, Yc, H, levels=[thr_h], colors="k", linewidths=1.1, zorder=4); turbines(ax); lg, _ = receptors(ax)
finish(fig, ax, out / f"{pre}_annual_hours.png", lg)

# 2) max daily minutes
fig, ax = plt.subplots(figsize=(9.5, 8.5)); base(ax, f"Worst-case maximum daily shadow flicker (terrain occlusion ON), 2025\nblack contour = {thr_m} min/day")
stepped(ax, M.astype(float), mb, "PuRd", "max flicker minutes in a day (stepped)", fig)
ax.contour(Xc, Yc, M, levels=[thr_m], colors="k", linewidths=1.1, zorder=4); turbines(ax); lg, _ = receptors(ax)
finish(fig, ax, out / f"{pre}_max_daily_minutes.png", lg)

# 3) occlusion effect
fig, axs = plt.subplots(1, 2, figsize=(17, 8.2))
base(axs[0], f"Annual hours: {thr_h} h contours\ndashed = no terrain occlusion, solid = with occlusion")
stepped(axs[0], Hf, hb, "YlOrRd", "annual hours, NO occlusion", fig)
axs[0].contour(Xc, Yc, Hf, levels=[thr_h], colors="k", linewidths=1.1, linestyles="--", zorder=4)
axs[0].contour(Xc, Yc, H, levels=[thr_h], colors="b", linewidths=1.3, zorder=4); turbines(axs[0]); lg, _ = receptors(axs[0], occ=False)
axs[0].legend(handles=lg, loc="lower left", fontsize=7, framealpha=0.9)
db = [0, 1, 5, 10, 20, 50, 100, 200, 400, 1000]
base(axs[1], f"Annual flicker hours removed by terrain occlusion\n(total over grid: {100*(1-H.sum()/Hf.sum()):.1f} % reduction)")
stepped(axs[1], Dr, db, "GnBu", "hours removed by terrain occlusion", fig)
axs[1].contour(Xc, Yc, Hf, levels=[thr_h], colors="k", linewidths=0.9, linestyles="--", zorder=4)
axs[1].contour(Xc, Yc, H, levels=[thr_h], colors="b", linewidths=1.0, zorder=4); turbines(axs[1])
fig.tight_layout(); fig.savefig(out / f"{pre}_occlusion_effect.png", dpi=130); plt.close(fig)
print("saved plots")
