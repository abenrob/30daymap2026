"""v2 compositor: render-once Blender passes (oversized) + model rasters -> 16:9 and 4:5 animations.

  python scripts/compose_v2.py --format 16x9 [--stills] [--days N]
  python scripts/compose_v2.py --format 4x5
Overlays are computed on the oversized frame (registered through the terrain-XY pass), then the frame is cropped with an
eased pan/zoom; pins, labels and HUD are drawn afterwards in final-frame coordinates (HUD fixed).
"""
import sys, json, time, subprocess, datetime as dtm
from pathlib import Path
import numpy as np, yaml, rasterio, OpenEXR, pandas as pd, pvlib
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from scipy.ndimage import gaussian_filter
from scipy.spatial import cKDTree
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
cfg = yaml.safe_load(open(ROOT / "config.yaml")); pre = cfg["site_run"]["out_prefix"]
out = ROOT / "outputs"
FMT = sys.argv[sys.argv.index("--format") + 1] if "--format" in sys.argv else "16x9"
STILLS_ONLY = "--stills" in sys.argv
LIMIT = int(sys.argv[sys.argv.index("--days") + 1]) if "--days" in sys.argv else None
PORT = FMT == "4x5"
TAG = sys.argv[sys.argv.index("--tag") + 1] if "--tag" in sys.argv else "v3"
bl = ROOT / sys.argv[sys.argv.index("--bl") + 1] if "--bl" in sys.argv else out / ("blender_v3" if (PORT and TAG == "v3") else "blender_v2") / FMT
FPS, YEAR = 30, cfg["time"]["year"]
FONT = "/usr/share/fonts/opentype/inter/Inter-{}.otf"
def font(size, w="Regular"): return ImageFont.truetype(FONT.format(w), int(size))

# ---------------------------------------------------------------- inputs
meta = json.load(open(bl / "scene_meta.json")); ox, oy = meta["origin"]
scr = json.load(open(bl / "screen_coords.json"))
Wb, Hb = scr["width"], scr["height"]; W, H = scr["final"]; OS = scr["oversize"]
beauty = np.asarray(Image.open(bl / "beauty.png").convert("RGB"), dtype=np.float32) / 255.0
ex = OpenEXR.File(str(bl / "passes.exr")); parts = {p.name(): p for p in ex.parts}
txy = parts["ViewLayer.terrainxy"].channels["ViewLayer.terrainxy"].pixels
depth = parts["ViewLayer.Depth"].channels["ViewLayer.Depth.Z"].pixels
bcov = parts["ViewLayer.bldcov"].channels["ViewLayer.bldcov.X"].pixels
tcov = parts["ViewLayer.turcov"].channels["ViewLayer.turcov.X"].pixels
cov = np.clip(txy[..., 2], 0, 1)
st = np.load(out / f"{pre}_stack.npz"); stack = st["stack"]; gx0, gy0, res = float(st["xmin"]), float(st["ymax"]), float(st["res"])
nd, nr, nc = stack.shape
rd = np.load(out / f"{pre}_receptor_daily.npz", allow_pickle=True)
rec = pd.read_csv(out / f"{pre}_receptors.csv"); assert list(rd["ids"]) == list(rec.id)
rstack = rd["stack"].astype(np.float32)
summ = json.load(open(out / f"{pre}_summary.json")); turb = json.load(open(out / f"{pre}_turbines_used.json"))
fl = np.load(out / f"{pre}_minute_flags.npz")
thr_h, thr_m = cfg["thresholds"]["annual_hours"], cfg["thresholds"]["daily_minutes"]; N_REC = len(rec)

# ---------------------------------------------------------------- pixel -> grid lookup (base frame)
valid = cov > 0.05
X = ox + txy[..., 0] / np.maximum(cov, 1e-6); Y = oy + txy[..., 1] / np.maximum(cov, 1e-6)
fx = (X - gx0) / res - 0.5; fy = (gy0 - Y) / res - 0.5
inside = valid & (fx >= 0) & (fx < nc - 1) & (fy >= 0) & (fy < nr - 1)
yy, xx = np.nonzero(inside)
by0, by1, bx0, bx1 = yy.min(), yy.max() + 1, xx.min(), xx.max() + 1
pfx, pfy = fx[yy, xx], fy[yy, xx]
c0, r0 = np.floor(pfx).astype(np.int64), np.floor(pfy).astype(np.int64)
wx, wy = (pfx - c0).astype(np.float32), (pfy - r0).astype(np.float32)
i00 = r0 * nc + c0
W00, W10, W01, W11 = (1 - wx) * (1 - wy), wx * (1 - wy), (1 - wx) * wy, wx * wy
pcov = cov[yy, xx]
def interp(flat): return flat[i00] * W00 + flat[i00 + 1] * W10 + flat[i00 + nc] * W01 + flat[i00 + nc + 1] * W11
# distance to nearest dwelling -> emphasis weight (1 within ~60 m, 0 beyond 300 m)
gxc = gx0 + (np.arange(nc) + 0.5) * res; gyc = gy0 - (np.arange(nr) + 0.5) * res
GX, GY = np.meshgrid(gxc, gyc)
dist_rec = cKDTree(np.column_stack([rec.x, rec.y])).query(np.column_stack([GX.ravel(), GY.ravel()]))[0].astype(np.float32)
t_ = np.clip((dist_rec - 60) / (300 - 60), 0, 1); EMPH = (1 - t_ * t_ * (3 - 2 * t_)).astype(np.float32)
pemph = interp(EMPH)
print(f"[{FMT}] base {Wb}x{Hb}, final {W}x{H}; {inside.sum()} terrain pixels in grid; bbox x{bx0}-{bx1} y{by0}-{by1}")

# ---------------------------------------------------------------- palettes
HBINS = [1, 5, 10, 20, 30, 50, 100, 200, 500]
HCOL = np.array([[253, 233, 162], [252, 205, 112], [249, 168, 66], [243, 117, 46], [221, 56, 48], [176, 22, 62], [120, 16, 78], [78, 14, 82], [46, 10, 66]], np.float32) / 255.0
MBINS = [1, 10, 20, 30, 45, 60, 90, 120]
MCOL = np.array([[253, 233, 162], [250, 190, 96], [245, 140, 60], [221, 56, 48], [176, 22, 62], [130, 18, 84], [90, 14, 90], [50, 10, 70]], np.float32) / 255.0
ICE = np.array([0.62, 0.96, 1.0], np.float32)
COL = dict(grey=(165, 168, 172), blue=(70, 170, 255), red=(255, 70, 60))
DWELL = (255, 60, 210); DWELL_B = (255, 110, 230); CYAN_SOFT = (150, 205, 222)
LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)

# ---------------------------------------------------------------- background prep: shadow lift (fill) + warm grade, haze factor
lum0 = beauty @ LUMA
warm = np.clip((lum0 - 0.22) / 0.4, 0, 1)[..., None]
bg = beauty * (1 + warm * np.array([0.10, 0.03, -0.08], np.float32))
bg = bg + (0.085 * np.exp(-lum0 / 0.13))[..., None] * np.array([0.80, 0.93, 1.0], np.float32) + 0.012   # lifted, cool-tinted shadows
bgl = (bg @ LUMA)[..., None]
bg = bgl + (bg - bgl) * 1.16                                   # restore some saturation
bg = np.clip((bg - 0.5) * 1.07 + 0.5 - 0.01, 0, 1)             # mild contrast
solid = np.clip(cov + bcov + tcov, 0, 1)
dm = depth[solid > 0.5]; d_lo, d_hi = np.percentile(dm, 2), np.percentile(dm, 99.5)
hz = np.clip((depth - d_lo) / (d_hi - d_lo), 0, 1)
HAZE = (0.28 * (1 - np.exp(-2.6 * hz)) / (1 - np.exp(-2.6)) * solid).astype(np.float32)[..., None]
HAZECOL = np.array([0.70, 0.76, 0.84], np.float32)

ZONE_ALPHA = 0.60
def overlay(cum_h_flat, foot_flat):
    img = bg.copy()
    v = interp(cum_h_flat); f = np.clip(interp(foot_flat), 0, 1)
    base = img[yy, xx]
    lum = np.clip(base @ LUMA / 0.30, 0.45, 1.35) ** 0.75
    k = np.digitize(v, HBINS)
    col = HCOL[np.clip(k - 1, 0, len(HCOL) - 1)]
    colr = (col * 0.80 + (col @ LUMA)[:, None] * 0.20) * lum[:, None]  # slightly muted, uniform over the zone
    a = np.where(k > 0, ZONE_ALPHA, 0.0).astype(np.float32) * pcov
    img[yy, xx] = base * (1 - a[:, None]) + colr * a[:, None]
    core = np.zeros((by1 - by0, bx1 - bx0), np.float32); core[yy - by0, xx - bx0] = f * pcov
    glow = gaussian_filter(core, 9) * 0.55 + gaussian_filter(core, 2.5) * 0.25
    blk = img[by0:by1, bx0:bx1]
    ca = np.clip(core * 0.36, 0, 1)[..., None]
    blk[:] = blk * (1 - ca) + ICE * ca
    rim = np.clip(gaussian_filter(core, 1.2) - gaussian_filter(core, 3.0), 0, 1)[..., None]
    blk[:] = np.clip(blk + glow[..., None] * ICE * 0.42 + rim * 0.9 * ICE, 0, 1)
    vi = np.full((by1 - by0, bx1 - bx0), np.nan, np.float32); vi[yy - by0, xx - bx0] = v
    vs = np.nan_to_num(vi, nan=0.0); gyv, gxv = np.gradient(vs); gm = np.hypot(gxv, gyv)
    dist = np.abs(vs - thr_h) / np.maximum(gm, 1e-4)
    ok = (gm > 1e-4) & np.isfinite(vi) & (vs > 0.5)
    la = np.where(ok, np.clip(1.3 - dist, 0, 1), 0)[..., None] * 0.97
    halo = np.where(ok, np.clip(2.7 - dist, 0, 1), 0)[..., None] * 0.34
    blk[:] = blk * (1 - halo); blk[:] = blk * (1 - la) + np.array([1.0, 0.98, 0.92], np.float32) * la
    img = img * (1 - HAZE) + HAZECOL * HAZE                                  # depth-based haze (after overlays)
    return img

# ---------------------------------------------------------------- camera drift
if PORT: PAN0, PAN1, Z1 = (45, 30), (-45, -25), 1.07
else:    PAN0, PAN1, Z1 = (-60, 25), (70, -20), 1.08
def crop_params(t):
    e = t * t * t * (t * (6 * t - 15) + 10)           # smootherstep
    z = 1 + (Z1 - 1) * e
    cx = Wb / 2 + PAN0[0] + (PAN1[0] - PAN0[0]) * e; cy = Hb / 2 + PAN0[1] + (PAN1[1] - PAN0[1]) * e
    assert cx - W / (2 * z) >= 0 and cx + W / (2 * z) <= Wb and cy - H / (2 * z) >= 0 and cy + H / (2 * z) <= Hb
    return z, cx, cy
def to_final(px, py, cp):
    z, cx, cy = cp
    return (px - cx) * z + W / 2, (py - cy) * z + H / 2
def crop_img(arr_f32, cp):
    z, cx, cy = cp
    im = Image.fromarray((np.clip(arr_f32, 0, 1) * 255 + 0.5).astype(np.uint8))
    return im.transform((W, H), Image.AFFINE, (1 / z, 0, cx - W / (2 * z), 0, 1 / z, cy - H / (2 * z)), resample=Image.BICUBIC)

# ---------------------------------------------------------------- HUD helpers
def panel(img, box, radius=14, alpha=150, blur=10):
    box = tuple(int(v) for v in box)
    crop = img.crop(box).filter(ImageFilter.GaussianBlur(blur))
    crop = Image.alpha_composite(crop.convert("RGBA"), Image.new("RGBA", crop.size, (10, 14, 22, alpha)))
    m = Image.new("L", crop.size, 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, crop.size[0] - 1, crop.size[1] - 1), radius, fill=255)
    img.paste(crop, box[:2], m); ImageDraw.Draw(img).rounded_rectangle(box, radius, outline=(255, 255, 255, 38), width=1)

def sprite(color, r, halo=0, k=1.0):
    r *= k; halo = int(halo * k); S = 8; size = int((r + halo + 3) * 2 * S); im = Image.new("RGBA", (size, size), (0, 0, 0, 0)); d = ImageDraw.Draw(im); c = size / 2
    for q in range(halo * S, 0, -1):
        d.ellipse((c - (r * S + q), c - (r * S + q), c + (r * S + q), c + (r * S + q)), fill=(*color, int(70 * (1 - q / (halo * S + 1)) ** 2)))
    d.ellipse((c - (r + 1.3) * S, c - (r + 1.3) * S, c + (r + 1.3) * S, c + (r + 1.3) * S), fill=(12, 16, 24, 235))
    d.ellipse((c - r * S, c - r * S, c + r * S, c + r * S), fill=(*color, 255))
    return im.resize((size // S, size // S), Image.LANCZOS)
KS = 1.35 if PORT else 1.0
SPR = {"grey": sprite(COL["grey"], 2.2, 0, KS), "blue": sprite(COL["blue"], 4.2, 3, KS), "red": sprite(COL["red"], 5.0, 5, KS)}
SPR["grey"].putalpha(SPR["grey"].getchannel("A").point(lambda v: int(v * 0.65)))

# sun path data
tt = pd.date_range(f"{YEAR}-01-01", f"{YEAR+1}-01-01", freq="5min", tz="UTC", inclusive="left")
sp = pvlib.solarposition.get_solarposition(tt, summ["lat"], summ["lon"])
sp_az, sp_el, sp_day = sp["azimuth"].to_numpy(), sp["apparent_elevation"].to_numpy(), tt.dayofyear.to_numpy() - 1
m_day, m_az, m_el = fl["day"], fl["az"], fl["el"]; _ff = ROOT / "outputs" / "marsanne_minute_flags_far800.npz"
FAR_M = 800 if _ff.exists() else 500
far = np.load(_ff)["far"] if _ff.exists() else fl["far500"]
day_start = np.searchsorted(m_day, np.arange(nd + 1))

def sunpath_img(day, size):
    S = 3; n = size * S; im = Image.new("RGBA", (n, n), (0, 0, 0, 0)); d = ImageDraw.Draw(im); c = n / 2; R = n * 0.39; fs = size * 0.058
    def pt(az, el): r = R * (90 - el) / 90; a = np.deg2rad(az); return (c + r * np.sin(a), c - r * np.cos(a))
    for el, a in ((0, 150), (30, 60), (60, 60)):
        rr = R * (90 - el) / 90; d.ellipse((c - rr, c - rr, c + rr, c + rr), outline=(255, 255, 255, a), width=S)
    rr = R * 87 / 90; d.ellipse((c - rr, c - rr, c + rr, c + rr), outline=(255, 200, 120, 120), width=S)
    d.line((c, c - R, c, c + R), fill=(255, 255, 255, 40), width=S); d.line((c - R, c, c + R, c), fill=(255, 255, 255, 40), width=S)
    for lab, az in (("N", 0), ("E", 90), ("S", 180), ("W", 270)):
        x, y = pt(az, -13); d.text((x, y), lab, font=font(fs * S, "SemiBold"), fill=(230, 235, 240, 235), anchor="mm")
    j0, j1 = day_start[day], day_start[day + 1]
    P = [pt(a, e) for a, e in zip(m_az[j0:j1], m_el[j0:j1])]
    lw = max(3, size / 40) * S
    for i in range(len(P) - 1):                       # path above 3 deg in grey
        d.line((P[i], P[i + 1]), fill=(190, 196, 206, 255), width=int(lw * 1.5))
    for i in range(len(P) - 1):                       # minutes with flicker reaching > 500 m: thin, soft cyan core on the grey path
        if far[j0 + i] and far[j0 + i + 1]: d.line((P[i], P[i + 1]), fill=CYAN_SOFT + (255,), width=max(3, int(lw * 1.0)))
    return im.resize((size, size), Image.LANCZOS)

def make_minimap(width):
    with rasterio.open(ROOT / cfg["dem"]["path"]) as ds: dem = ds.read(1); tf = ds.transform
    r0_ = int((tf.f - gy0) / 5); c0_ = int((gx0 - tf.c) / 5)
    z = dem[r0_:r0_ + nr, c0_:c0_ + nc].astype(np.float32)
    from matplotlib.colors import LightSource
    hs = LightSource(azdeg=300, altdeg=40).hillshade(z, vert_exag=2, dx=5, dy=5)
    base = np.dstack([hs * 0.85 + 0.1] * 3).astype(np.float32); base[..., 2] += 0.05
    Mx = stack.max(axis=0).astype(np.float32); k = np.digitize(Mx, MBINS)
    rgb = base.copy(); m = k > 0; col = MCOL[np.clip(k - 1, 0, len(MCOL) - 1)]
    rgb[m] = 0.35 * base[m] + 0.65 * col[m] * (0.5 + 0.6 * base[m, :1])
    sm = gaussian_filter(Mx, 0.7); gm = np.hypot(*np.gradient(sm))
    line = np.clip(1.2 - np.abs(sm - thr_m) / np.maximum(gm, 1e-3), 0, 1)
    rgb = rgb * (1 - line[..., None]) + line[..., None]
    im = Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8)).resize((width, int(width * nr / nc)), Image.LANCZOS)
    d = ImageDraw.Draw(im); sx = width / nc
    for t in turb:
        px, py = (t["x"] - gx0) / res * sx, (gy0 - t["y"]) / res * sx
        d.polygon([(px, py - 5), (px - 4, py + 3), (px + 4, py + 3)], fill=(255, 255, 255), outline=(10, 14, 22))
    return im

# ---------------------------------------------------------------- labels (BD TOPO toponyms, real names only)
rpx = np.array([r["roof"] for r in scr["receptors"]])
ix_, iy_ = np.clip(rpx[:, 0].astype(int), 0, Wb - 1), np.clip(rpx[:, 1].astype(int), 0, Hb - 1)
rvis_pre = (rpx[:, 0] > 2) & (rpx[:, 0] < Wb - 2) & (rpx[:, 1] > 2) & (rpx[:, 1] < Hb - 2)
rvis = rvis_pre & (depth[iy_, ix_] >= rpx[:, 2] - 40)
tx_, ty_ = np.array([t["x"] for t in turb]), np.array([t["y"] for t in turb])
recxy = np.column_stack([rec.x, rec.y]); flick_rec = rec.annual_hours.values > 0
if PORT:
    _mh = int(204 * nr / nc)
    HUDR = [(24, 24, 1056, 150), (24, 162, 1056, 246), (24, 934, 1056, 1326), (24, 262, 260, 262 + _mh + 84), (220, 862, 860, 926)]   # last two: final-hold minimap + result box
    LF, LFB, TF = 22, 24, 17
else:
    _mh = int(250 * nr / nc)
    HUDR = [(36, 32, 936, 118), (1480, 32, 1884, 126), (36, 944, 1560, 1048), (1596, 560, 1884, 1048), (1596, 140, 1884, 140 + _mh + 78), (560, 870, 1360, 926)]   # last two: final-hold minimap + result box
    LF, LFB, TF = 17, 19, 13
cp_mid = crop_params(0.5)
def lbox(qx, qy, w, sd, pad=0):
    if sd == 1: return (qx - 6, qy - LF - 6, qx + 14 + w, qy + 8)
    if sd == -1: return (qx - 14 - w, qy - LF - 6, qx + 6, qy + 8)
    if sd == 4: return (qx + 20 - w, qy + 8, qx + 20, qy + LF + 20)
    if sd == 3: return (qx - w / 2 - 8, qy + 14, qx + w / 2 + 8, qy + LF + 38)
    if sd == 2: return (qx - 14 - w, qy + 10, qx + 6, qy + LF + 22)
    return (qx - w / 2 - 8, qy + 2, qx + w / 2 + 8, qy + LF + 14)
PRIORITY = ["les Grands Rigauds", "Fernet", "Poise", "la Teissonnière", "Chapouzes"]
cands = []
_dm = ImageDraw.Draw(Image.new("RGB", (1, 1)))
for n in scr["labels"]:
    nm = n["name"]; px, py = to_final(n["px"][0], n["px"][1], cp_mid)
    tw0 = _dm.textlength(nm, font=font(LFB, "SemiBold")); sides = []
    for sd in ((1, -1, 0, 2, 3, 4) if nm in PRIORITY else (1,)):
        okk = True
        for tq in (0.0, 0.5, 1.0):                   # must stay clear of HUD panels / frame edges for the whole drift
            qx, qy = to_final(n["px"][0], n["px"][1], crop_params(tq)); bq = lbox(qx, qy, tw0, sd)
            if bq[0] < 24 or bq[2] > W - 24 or bq[1] < 24 or bq[3] > H - 24 or any(not (bq[2] < a_ - (14 if sd != 4 else 7) or bq[0] > c_ + 14 or bq[3] < b_ - 14 or bq[1] > d_ + 14) for a_, b_, c_, d_ in HUDR): okk = False
        if okk: sides.append(sd)
    if nm == "Chapouzes": print("CHAP", sides)
    if not sides: continue
    dT = np.hypot(n["x"] - tx_, n["y"] - ty_).min()
    if nm in PRIORITY:
        if any(c_[1] == nm for c_ in cands): continue
        print('priority', nm, n['kind'], [tuple(round(v) for v in to_final(n['px'][0], n['px'][1], crop_params(q))) for q in (0, .5, 1)]); cands.append((-1e6 + PRIORITY.index(nm), nm, n["x"], n["y"], n["px"], n["kind"], nm in ("Fernet", "les Grands Rigauds", "Poise"), sides)); continue
    nrec = int((np.hypot(recxy[:, 0] - n["x"], recxy[:, 1] - n["y"]) < 250).sum())
    nfl = int((np.hypot(recxy[flick_rec, 0] - n["x"], recxy[flick_rec, 1] - n["y"]) < 250).sum())
    if n["kind"] == "habitation":
        if nrec == 0: continue
        score = (-nfl * 1000) + dT - nrec * 20
    elif n["kind"] == "lieu_dit_non_habite" and dT < 1500: score = 3000 + dT
    elif n["kind"] == "orographie" and dT < 1800 and n["nature"] in ("Crête", "Sommet", "Col"): score = 4000 + dT
    else: continue
    cands.append((score, nm, n["x"], n["y"], n["px"], n["kind"], False, [1]))
cands.sort(); chosen = []; boxes = []; tboxes = []
for t in scr["turbines"]:                              # keep labels off the turbine IDs
    if t["modelled"]:
        qx, qy = to_final(t["hub_px"][0], t["hub_px"][1], cp_mid); boxes.append((qx - 20, qy - 40, qx + 70, qy + 10)); tboxes.append((qx + 12 * KS - 4, qy - 18 * KS - TF - 4, qx + 12 * KS + 54, qy - 14 * KS + 4))
KMAX = 8 if not PORT else 6
for sc_, nm, x, y, p, kind, hot, sides in cands:
    px, py = to_final(p[0], p[1], cp_mid); f_ = font(LFB if hot else LF, "SemiBold" if hot else "Medium")
    tw = ImageDraw.Draw(Image.new("RGB", (1, 1))).textlength(nm, font=f_)
    bx = None
    for side in sides:
        bb = {1: (px + 6, py - LF - 2, px + 10 + tw, py + 4), -1: (px - 10 - tw, py - LF - 2, px - 6, py + 4), 0: (px - tw / 2, py + 4, px + tw / 2, py + LF + 10), 2: (px - 10 - tw, py + 12, px, py + LF + 18), 3: (px - tw / 2, py + 22, px + tw / 2, py + LF + 30), 4: (px + 20 - tw, py + 8, px + 20, py + LF + 16)}[side]
        if not any(not (bb[2] < b[0] - (20 if nm not in PRIORITY else 0) or bb[0] > b[2] + (20 if nm not in PRIORITY else 0) or bb[3] < b[1] - 8 or bb[1] > b[3] + 8) for b in (boxes if nm not in PRIORITY else tboxes + boxes[len(tboxes):])): bx = bb; break
    if bx is None:
        if nm == "Chapouzes": print("CHAPFAIL", sides, px, py, tw, [(round(b[0]),round(b[1]),round(b[2]),round(b[3])) for b in tboxes + boxes[len(tboxes):] if abs(b[1]-py)<80 and abs(b[0]-px)<200], KS, TF)
        continue
    boxes.append(bx); chosen.append(dict(name=nm, p=p, hot=hot, kind=kind, side=side))
    if len(chosen) >= KMAX: break
print("labels:", [(c["name"], c["kind"]) for c in chosen])
_viol = 0
for tq in np.linspace(0, 1, 41):
    cpq = crop_params(tq)
    for c in chosen:
        qx, qy = to_final(c["p"][0], c["p"][1], cpq); f_ = font(LFB if c["hot"] else LF, "SemiBold" if c["hot"] else "Medium")
        bq = lbox(qx, qy, _dm.textlength(c["name"], font=f_), c["side"])
        if any(not (bq[2] < a_ - 6 or bq[0] > c_ + 6 or bq[3] < b_ - 6 or bq[1] > d_ + 6) for a_, b_, c_, d_ in HUDR): _viol += 1; print("VIOLATION", c["name"], round(tq, 2))
    for t in scr["turbines"]:
        if not t["modelled"]: continue
        qx, qy = to_final(t["hub_px"][0], t["hub_px"][1], cpq); bq = (qx + 12 * KS, qy - 18 * KS - TF, qx + 12 * KS + 46, qy - 14 * KS)
        if any(not (bq[2] < a_ - 4 or bq[0] > c_ + 4 or bq[3] < b_ - 4 or bq[1] > d_ + 4) for a_, b_, c_, d_ in HUDR): _viol += 1; print("TURBINE-ID VIOLATION", t["id"], round(tq, 2))
print("label/HUD check over the whole drift: violations =", _viol); assert _viol == 0

def draw_labels(img, cp):
    d = ImageDraw.Draw(img)
    for c in chosen:
        px, py = to_final(c["p"][0], c["p"][1], cp)
        if not (20 < px < W - 20 and 20 < py < H - 20): continue
        f_ = font(LFB if c["hot"] else LF, "SemiBold" if c["hot"] else "Medium")
        r_ = 3.2 if not PORT else 4
        d.ellipse((px - r_, py - r_, px + r_, py + r_), fill=(255, 235, 170, 255) if c["hot"] else (235, 240, 245, 230), outline=(10, 14, 22, 255))
        d.text((px + 8 if c["side"] == 1 else px - 8 if c["side"] == -1 else px if c["side"] in (0, 3) else px + 20 if c["side"] == 4 else px + 2, py - 3 if c["side"] in (1, -1) else py + LF + 6 + (18 if c["side"] == 3 else 8 if c["side"] in (2, 4) else 0)), c["name"], font=f_, fill=(255, 245, 215, 255) if c["hot"] else (236, 241, 246, 235), anchor={1: "ls", -1: "rs", 0: "ms", 2: "rs", 3: "ms", 4: "rs"}[c["side"]], stroke_width=3 if not PORT else 4, stroke_fill=(8, 12, 20, 210))
    ft = font(TF, "SemiBold")
    for t in scr["turbines"]:
        if not t["modelled"]: continue
        px, py = to_final(t["hub_px"][0], t["hub_px"][1], cp)
        if 20 < px < W - 20 and 20 < py < H - 20:
            d.text((px + 14 * KS, py - 18 * KS), t["id"], font=ft, fill=(255, 255, 255, 235), anchor="ls", stroke_width=2, stroke_fill=(8, 12, 20, 200))

def fmt_date(d): return (dtm.date(YEAR, 1, 1) + dtm.timedelta(days=int(d))).strftime("%-d %B %Y")
LABS = ["1–5", "5–10", "10–20", "20–30", "30–50", "50–100", "100–200", "200–500", "500+"]
def rgb255(c): return tuple(int(v * 255) for v in c)

def hud(base_rgb, cp, day, zst, final=False, result_alpha=0.0, minimap=None):
    img = base_rgb.convert("RGBA")
    draw_labels(img, cp)
    d = ImageDraw.Draw(img)
    zarea, zarea30, zmax = zst
    dd = min(day, nd - 1); dtxt = fmt_date(dd if not final else nd - 1)
    prog = (min(day, nd - 1) + 1) / nd
    if PORT:
        panel(img, HUDR[0]); d.text((52, 44), "Shadow flicker, Marsanne ridge (Drôme)", font=font(40, "SemiBold"), fill=(246, 248, 250))
        d.text((52, 100), "Worst case 2025 · clear sky · rotor faces the sun · terrain-occluded", font=font(21), fill=(172, 184, 198))
        panel(img, HUDR[1]); d.text((52, 204), dtxt, font=font(42, "SemiBold"), fill=(246, 248, 250), anchor="lm")
        d.rounded_rectangle((590, 198, 1026, 210), 6, fill=(255, 255, 255, 45)); d.rounded_rectangle((590, 198, 590 + int(436 * prog), 210), 6, fill=(255, 190, 90, 255))
        # bottom stack: legend then stats
        panel(img, (24, 934, 1056, 1130)); x0 = 46
        d.text((x0, 948), "Cumulative flicker hours per year", font=font(23, "SemiBold"), fill=(246, 248, 250))
        for i, (lab, cl) in enumerate(zip(LABS, HCOL)):
            col_, row_ = i % 5, i // 5; xx_, yy_ = x0 + col_ * 200, 990 + row_ * 34
            d.rounded_rectangle((xx_, yy_, xx_ + 36, yy_ + 22), 4, fill=rgb255(cl) + (240,)); d.text((xx_ + 46, yy_ + 11), lab + " h", font=font(21), fill=(224, 231, 238), anchor="lm")
        xx_, yy_ = x0 + 4 * 200, 990 + 34
        d.line((xx_, yy_ + 11, xx_ + 36, yy_ + 11), fill=(255, 250, 235), width=4); d.text((xx_ + 46, yy_ + 11), "30 h/yr", font=font(21), fill=(224, 231, 238), anchor="lm")
        yb = 1074
        d.rounded_rectangle((x0, yb - 11, x0 + 36, yb + 11), 4, fill=rgb255(ICE) + (255,)); d.text((x0 + 46, yb), "flicker today (fades over ~4 days)", font=font(21), fill=(224, 231, 238), anchor="lm")
        panel(img, (24, 1142, 1056, 1326)); d.text((52, 1160), "Zone statistics so far", font=font(24, "SemiBold"), fill=(246, 248, 250))
        for i, (lab, val) in enumerate((("Flicker area so far", f"{zarea:,.0f} ha"), ("Area over 30 h/yr", f"{zarea30:,.0f} ha"), ("Max hours anywhere", f"{zmax:.0f} h"))):
            y_ = 1204 + i * 38
            d.text((52, y_), lab, font=font(22), fill=(172, 184, 198)); d.text((600, y_ - 2), val, font=font(30, "SemiBold"), fill=(246, 248, 250), anchor="ra")
        if final and minimap is not None:
            panel(img, (24, 262, 260, 262 + minimap.size[1] + 84)); d.text((40, 276), "Max flicker min/day", font=font(20, "SemiBold"), fill=(246, 248, 250))
            img.paste(minimap, (40, 312)); ImageDraw.Draw(img).text((40, 312 + minimap.size[1] + 8), "white line: 30 min/day", font=font(17), fill=(190, 200, 212))
        else:
            img.alpha_composite(sunpath_img(dd, 172), (866, 1148))
            d.text((650, 1170), "Sun path today (UTC)", font=font(20, "SemiBold"), fill=(246, 248, 250))
            d.line((650, 1222, 682, 1222), fill=CYAN_SOFT, width=5); d.text((692, 1222), f"flicker > {FAR_M} m", font=font(18), fill=(200, 210, 220), anchor="lm")
            d.line((650, 1260, 682, 1260), fill=(190, 196, 206), width=6); d.text((692, 1260), "sun above 3°", font=font(18), fill=(200, 210, 220), anchor="lm")
    else:
        panel(img, HUDR[0]); d.text((60, 52), "Shadow flicker, Marsanne ridge (Drôme) — worst case 2025", font=font(29, "SemiBold"), fill=(246, 248, 250))
        d.text((60, 90), "Clear sky · turbines always running · rotor always facing the sun · terrain-occluded", font=font(16), fill=(170, 182, 196))
        panel(img, HUDR[1]); d.text((1872, 62), dtxt, font=font(36, "SemiBold"), fill=(246, 248, 250), anchor="rm")
        d.rounded_rectangle((1504, 100, 1860, 106), 3, fill=(255, 255, 255, 45)); d.rounded_rectangle((1504, 100, 1504 + int(356 * prog), 106), 3, fill=(255, 190, 90, 255))
        panel(img, HUDR[2]); x0, y0 = 58, 960
        d.text((x0 - 20 + 20, y0 + 2), "Flicker hours per year", font=font(15, "SemiBold"), fill=(246, 248, 250))
        for i, (lab, cl) in enumerate(zip(LABS, HCOL)):
            xx_ = x0 + 190 + i * 86; d.rounded_rectangle((xx_, y0 + 3, xx_ + 22, y0 + 17), 3, fill=rgb255(cl) + (240,)); d.text((xx_ + 28, y0 + 10), lab, font=font(13), fill=(220, 228, 236), anchor="lm")
        d.line((x0 + 970, y0 + 10, x0 + 1000, y0 + 10), fill=(255, 250, 235), width=3); d.text((x0 + 1008, y0 + 10), "30 h/yr", font=font(13), fill=(220, 228, 236), anchor="lm")
        yb = y0 + 54
        d.rounded_rectangle((x0, yb - 8, x0 + 28, yb + 8), 4, fill=rgb255(ICE) + (255,)); d.text((x0 + 36, yb), "flicker today (fades over ~4 days)", font=font(14), fill=(220, 228, 236), anchor="lm")
        cx0, cy0, cx1, cy1 = HUDR[3]
        if final: cy1 = 760
        panel(img, (cx0, cy0, cx1, cy1)); d.text((cx0 + 20, cy0 + 16), "Zone statistics so far", font=font(17, "SemiBold"), fill=(246, 248, 250))
        for i, (lab, val) in enumerate((("Flicker area so far", f"{zarea:,.0f} ha"), ("Area over 30 h/yr", f"{zarea30:,.0f} ha"), ("Max hours anywhere", f"{zmax:.0f} h"))):
            y_ = cy0 + 50 + i * 30
            d.text((cx0 + 20, y_), lab, font=font(13), fill=(170, 182, 196)); d.text((cx1 - 20, y_ - 2), val, font=font(18, "SemiBold"), fill=(246, 248, 250), anchor="ra")
        if final and minimap is not None:
            panel(img, (cx0, 140, cx1, 140 + minimap.size[1] + 78)); d.text((cx0 + 20, 156), "Max flicker min/day", font=font(16, "SemiBold"), fill=(246, 248, 250))
            img.paste(minimap, (cx0 + 20, 186)); ImageDraw.Draw(img).text((cx0 + 20, 186 + minimap.size[1] + 8), "white line = 30 min/day", font=font(12), fill=(170, 182, 196))
        else:
            d.text((cx0 + 20, cy0 + 150), "Sun path today (UTC)", font=font(14), fill=(170, 182, 196)); img.alpha_composite(sunpath_img(dd, 236), (cx0 + 24, cy0 + 168))
            d.line((cx0 + 20, cy0 + 428, cx0 + 44, cy0 + 428), fill=CYAN_SOFT, width=3); d.text((cx0 + 52, cy0 + 428), f"flicker > {FAR_M} m", font=font(12), fill=(190, 200, 212), anchor="lm")
            d.line((cx0 + 20, cy0 + 448, cx0 + 44, cy0 + 448), fill=(190, 196, 206), width=5); d.text((cx0 + 52, cy0 + 448), "sun above 3°", font=font(12), fill=(190, 200, 212), anchor="lm")
    if result_alpha > 0:
        txt = "Worst-case shadow flicker zone, 2025"
        txt2 = ""
        f2 = font(26 if not PORT else 33, "SemiBold"); f3 = font(18 if not PORT else 23)
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); dl = ImageDraw.Draw(lay)
        tw = dl.textlength(txt, font=f2); bw = int(tw + 70); bh = 56 if not PORT else 64
        bx = (W - bw) // 2; by = (HUDR[2][1] - bh - 14) if not PORT else 862
        panel(lay, (bx, by, bx + bw, by + bh), alpha=205)
        dl.text((W / 2, by + bh * 0.5), txt, font=f2, fill=(255, 255, 255, 255), anchor="mm")
        if result_alpha < 1: lay.putalpha(lay.getchannel("A").point(lambda v: int(v * result_alpha)))
        img.alpha_composite(lay)
    return np.asarray(img.convert("RGB"))

# ---------------------------------------------------------------- main loop
STILL_DAYS = {79: "21mar", 171: "21jun", 354: "21dec"}
ndays = LIMIT or nd; NF = 2 * nd
tag = f"v2_{FMT.replace('x', 'x')}"
cum = np.zeros(nr * nc, np.float32); foot = np.zeros(nr * nc, np.float32); rcum = np.zeros(N_REC, np.float32); rmax = np.zeros(N_REC, np.float32)
proc = None
def zstats(h): return (float((h > 0).sum()) * res * res / 1e4, float((h > thr_h).sum()) * res * res / 1e4, float(h.max()))
if not STILLS_ONLY:
    proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                             "-vf", "scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                             "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv", "-movflags", "+faststart", str(out / f"marsanne_year_{TAG}_{FMT}.mp4")], stdin=subprocess.PIPE)
FADE = 20; t0 = time.time(); nframes = 0
def emit(fr):
    global nframes
    if nframes < FADE: fr = (fr.astype(np.float32) * (nframes + 1) / FADE).astype(np.uint8)
    if proc is not None: proc.stdin.write(fr.tobytes())
    nframes += 1
for d in range(ndays):
    today = stack[d].ravel().astype(np.float32); tbin = gaussian_filter((stack[d] > 0).astype(np.float32), 0.8).ravel(); rtoday = rstack[d]
    for s in (0, 1):
        frac = 0.5 if s == 0 else 1.0
        foot *= 0.72; foot = np.maximum(foot, tbin * (0.9 if s == 0 else 1.0))
        want = (d in STILL_DAYS and s == 1) or not STILLS_ONLY
        if want:
            cp = crop_params((2 * d + s) / (NF - 1))
            fr = hud(crop_img(overlay((cum + frac * today) / 60.0, foot), cp), cp, d, zstats((cum + frac * today) / 60.0))
            if d in STILL_DAYS and s == 1: Image.fromarray(fr).save(out / f"marsanne_still_{TAG}_{FMT}_{STILL_DAYS[d]}.png")
            if not STILLS_ONLY: emit(fr)
    cum += today; rcum += rtoday / 60.0; rmax = np.maximum(rmax, rtoday)
    if d % 20 == 0: print(f"day {d}/{ndays} frames {nframes} elapsed {time.time()-t0:.0f}s", flush=True)
foot[:] = 0
mini = make_minimap(250 if not PORT else 204); cp = crop_params(1.0)
final_base = crop_img(overlay(cum / 60.0, foot), cp)
Image.fromarray(hud(final_base, cp, nd - 1, zstats(cum / 60.0), final=True, result_alpha=1.0, minimap=mini)).save(out / f"marsanne_still_{TAG}_{FMT}_final.png")
if not STILLS_ONLY:
    last = None
    for k in range(4 * FPS):
        a = min(1.0, k / 15.0)
        if k <= 15: last = hud(final_base, cp, nd - 1, zstats(cum / 60.0), final=True, result_alpha=a, minimap=mini)
        emit(last)
    proc.stdin.close(); proc.wait()
print(f"done {FMT}: {nframes} frames in {time.time()-t0:.0f}s")
