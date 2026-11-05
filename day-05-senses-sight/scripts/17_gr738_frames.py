"""Draw the GR 738 walk, one frame per viewshed, and encode the MP4 at 30 fps.

Two layouts (--layout):
  portrait   1080 x 1350 (4:5): the map fills the frame, caption on top, profile strip below
  landscape  1920 x 1080 (16:9, LinkedIn's native video ratio): an 80 km square map on the
             right, title, live numbers, profile strip and legend in a panel on the left

Map: dark hillshade; ground seen earlier on the walk in a faint tint; ground in sight now in amber;
the trail (walked part bright); the walker. Numbers: km, ground height and area in sight; a profile
of elevation (line) over ground in sight (bars). Ends on a 3 s card of everything seen.

Points of interest: the walker pauses 1.2 s at each, and its marker and label fade in on arrival
and out after. The number on a label is the ground in sight from the trail point nearest the place,
the same value the caption shows during the pause. The Chamrousse ski area (outline and label) is
shown while the walker is inside it, with the pause at its best spot. The end card shows all of
them as numbered markers with one legend.

Run from the workspace root:
  python3 site/day-05-senses-sight/scripts/17_gr738_frames.py [--layout L] [--stride N] [--still STEP]
  --stride N    every Nth step only (quick preview)
  --still STEP  one timeline step to work/data/day-05-sight/renders/gr738_<layout>_step_STEP.png
Input : gr738/ trail.csv, trail_full.csv, stats.json, masks.npy, dem_25m.tif, dem_50m.tif
        raw/ gr738_pois.json, gr738_huts.json, gr738_ski_geom.json (Overpass, see README)
Output: renders/day-05-gr738.mp4 + gr738_final.png (portrait),
        renders/day-05-gr738-16x9.mp4 + gr738_final_16x9.png (landscape)
"""
import argparse, csv, json, math, os, shutil, subprocess
import numpy as np
import rasterio
from PIL import Image, ImageDraw, ImageFont
from pyproj import Transformer
from shapely.geometry import Point, Polygon

p = argparse.ArgumentParser()
p.add_argument("--layout", choices=["portrait", "landscape"], default="portrait")
p.add_argument("--stride", type=int, default=1)
p.add_argument("--still", type=int)
a = p.parse_args()
LAND = a.layout == "landscape"

D = "work/data/day-05-sight"
G = f"{D}/gr738"
FR = f"{G}/frames_{a.layout}"
shutil.rmtree(FR, ignore_errors=True)                 # no stale frames from a longer run
os.makedirs(FR)
if LAND:
    OW, OH = 1920, 1080
    MX0, MW, MH = 840, 1080, 1080                     # map: right-hand square
    VIEW_W = 80_000                                   # metres across the map
else:
    OW, OH = 1080, 1350
    MX0, MW, MH = 0, OW, OH                           # map: the whole frame
    VIEW_W = 80_000
VIEW_H = VIEW_W * MH / MW
AMBER = np.array([255, 178, 92], np.float32)
PANEL = (4, 6, 11)

trail = list(csv.DictReader(open(f"{G}/trail.csv")))
full = np.array([[float(r["x"]), float(r["y"]), float(r["km"])] for r in csv.DictReader(open(f"{G}/trail_full.csv"))])
st = json.load(open(f"{G}/stats.json"))
stats = st["frames"]
masks = np.load(f"{G}/masks.npy", mmap_mode="r")
with rasterio.open(f"{G}/dem_50m.tif") as src:
    z = src.read(1)
    T, res = src.transform, src.res[0]
H, W = z.shape

# map window, centred on the route, in grid pixels of the 50 m DEM
cx, cy = (full[:, 0].min() + full[:, 0].max()) / 2, (full[:, 1].min() + full[:, 1].max()) / 2
vx0, vy1 = cx - VIEW_W / 2, cy + VIEW_H / 2
c0, r0 = int(round((vx0 - T.c) / res)), int(round((T.f - vy1) / res))
cw, ch = int(VIEW_W / res), int(VIEW_H / res)
assert c0 >= 0 and r0 >= 0 and c0 + cw <= W and r0 + ch <= H, "view outside the DEM crop"
sl = np.s_[r0:r0 + ch, c0:c0 + cw]
def to_px(x, y):
    """EPSG:2154 metres to pixels on the map canvas (MW x MH)"""
    return (x - vx0) / VIEW_W * MW, (vy1 - y) / VIEW_H * MH

# base map: hillshade from the 25 m DEM (sun from the north-west, 35 degrees), dark palette
with rasterio.open(f"{G}/dem_25m.tif") as src:
    z25 = src.read(1, window=((2 * r0, 2 * (r0 + ch)), (2 * c0, 2 * (c0 + cw))))
gy, gx = np.gradient(z25, 25)
az, alt = math.radians(315), math.radians(35)
slope, aspect = np.arctan(np.hypot(gx, gy)), np.arctan2(-gx, gy)
hs = np.clip(np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect), 0, 1)
hs = np.asarray(Image.fromarray((hs * 255).astype(np.uint8)).resize((MW, MH), Image.LANCZOS), np.float32) / 255
lo, hi = np.array([6, 9, 16], np.float32), np.array([78, 90, 112], np.float32)
base = lo + (hi - lo) * hs[..., None] ** 1.2
lit = AMBER * (0.55 + 0.45 * hs[..., None])

def up(m):
    """grid mask (ch x cw, bool) to a soft MW x MH alpha"""
    return np.asarray(Image.fromarray(m.astype(np.uint8) * 255).resize((MW, MH), Image.BILINEAR), np.float32)[..., None] / 255

def font(size, bold=False):
    import matplotlib
    return ImageFont.truetype(os.path.join(matplotlib.get_data_path(), "fonts/ttf",
                                           "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"), size)
F_T, F_S, F_X, F_L = font(38, True), font(29), font(19), font(22)
F_P, F_Q, F_N = font(25, True), font(22), font(19, True)

to93 = Transformer.from_crs(4326, 2154, always_xy=True)
places = [("Grenoble", 5.7245, 45.1885), ("Chambéry", 5.9178, 45.5646),
          ("Vizille", 5.7714, 45.0778), ("Aiguebelle", 6.3064, 45.5431)]
places = [(n, *to_px(*to93.transform(lo_, la_))) for n, lo_, la_ in places]
tx, ty = to_px(full[:, 0], full[:, 1])
tkm = full[:, 2]
km = np.array([s["km"] for s in stats]); el = np.array([s["ground"] for s in stats])
vis = np.array([s["visible_km2"] for s in stats])

# --- points of interest -------------------------------------------------------------------
RAW = f"{D}/raw"
osm = {e["tags"]["name"]: e for f_ in ("gr738_pois.json", "gr738_huts.json")
       for e in json.load(open(f"{RAW}/{f_}"))["elements"] if e.get("tags", {}).get("name")}
txy = np.array([[float(r["x"]), float(r["y"])] for r in trail])
# (OSM name, symbol, which side of the marker the label goes, second line). Sides are set by
# hand so neighbouring labels (7 Laux and Col de la Vache are 4 km apart) do not collide.
POI_SPEC = [("Grand Chat", "peak", "left", "widest view on the route: {v:,.0f} km²"),
            ("Refuge des 7 Laux", "hut", "left", "sheltered basin: {v:,.0f} km²"),
            ("Col de la Vache", "peak", "right", "highest point, only {v:,.0f} km²"),
            ("Refuge de La Pra", "hut", "right", "sheltered basin: {v:,.0f} km²")]
pois = []
for name, sym, side, tpl in POI_SPEC:
    e = osm[name]
    c = e.get("center", e)
    x, y = to93.transform(c["lon"], c["lat"])
    f = int(np.hypot(*(txy - [x, y]).T).argmin())
    if name == "Grand Chat":
        # the route's widest view is on the summit ridge, 220 m before the point: pause there,
        # so "widest view on the route" is true of the number shown
        f = f - 3 + int(vis[f - 3:f + 4].argmax())
    ele = e["tags"].get("ele") or el[f]
    pois.append(dict(name=name, sym=sym, side=side, f=f, x=x, y=y,
                     title=f"{name}, {int(float(ele)):,} m", sub=tpl.format(v=vis[f])))
# Chamrousse ski area: shown while the walker is inside it, paused at its best spot
ski = next(e for e in json.load(open(f"{RAW}/gr738_ski_geom.json"))["elements"]
           if e.get("tags", {}).get("name") == "Domaine Skiable Chamrousse")
cham = Polygon([to93.transform(p_["lon"], p_["lat"]) for p_ in ski["geometry"]])
inside = np.array([cham.contains(Point(*xy_)) for xy_ in txy])
ins = np.nonzero(inside)[0]
cbest = int(ins[vis[ins].argmax()])
cham_px = [to_px(*xy_) for xy_ in cham.exterior.coords]
pois.append(dict(name="Chamrousse", sym="area", side="right", f=cbest, x=txy[cbest][0], y=txy[cbest][1],
                 title="What's visible from Chamrousse",
                 sub=f"best spot in the ski area: {vis[cbest]:,.0f} km²"))
order = sorted(pois, key=lambda q: q["f"])            # numbering on the end card
for q in pois:
    print(f"POI {q['title']} | {q['sub']} | frame {q['f']}, km {km[q['f']]:.1f}")

# timeline: one step per trail frame (30 fps), plus HOLD repeats of the frame at each POI.
# In steps: pause 36 = 1.2 s, label stays 20 more after the walker moves on, fades 8 in, 12 out.
HOLD, LINGER, FADE_IN, FADE_OUT = 36, 20, 8, 12
timeline, t0 = [], {}
pf = {q["f"]: q["name"] for q in pois}
for f in range(len(trail)):
    timeline.append(f)
    if f in pf:
        t0[pf[f]] = len(timeline) - 1
        timeline += [f] * HOLD
print("POI pause steps:", {k: v + HOLD // 2 for k, v in t0.items()}, "of", len(timeline))

def poi_alpha(q, t):
    """opacity 0..1 of a POI at timeline step t"""
    if q["sym"] == "area":                                  # follows the walker in and out
        on = [inside[timeline[tt]] for tt in range(max(0, t - FADE_IN + 1), t + 1)]
        was = [inside[timeline[tt]] for tt in range(max(0, t - FADE_OUT + 1), t + 1)]
        if inside[timeline[t]]:
            return sum(on) / FADE_IN
        return sum(was) / FADE_OUT
    s_ = t0[q["name"]]
    if t < s_:
        return 0.0
    if t < s_ + FADE_IN:
        return (t - s_ + 1) / FADE_IN
    end = s_ + HOLD + LINGER
    if t < end:
        return 1.0
    return max(0.0, 1 - (t - end + 1) / FADE_OUT)

def draw_poi(base_im, q, a_):
    """marker + label box on its own layer, then faded by a_"""
    if a_ <= 0:
        return base_im
    lay = Image.new("RGBA", base_im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    mx, my = to_px(q["x"], q["y"])
    if q["sym"] == "area":
        d.polygon(cham_px, fill=(120, 200, 255, 55), outline=(150, 215, 255, 255), width=3)
    elif q["sym"] == "peak":
        d.polygon([(mx, my - 11), (mx - 10, my + 7), (mx + 10, my + 7)], fill=(150, 215, 255, 255), outline=(10, 14, 22, 255))
    else:
        d.rectangle([mx - 8, my - 8, mx + 8, my + 8], fill=(150, 215, 255, 255), outline=(10, 14, 22, 255))
    w_ = max(d.textlength(q["title"], font=F_P), d.textlength(q["sub"], font=F_Q)) + 30
    bx = mx + 30 if q["side"] == "right" else mx - 30 - w_
    bx = min(max(bx, 12), MW - 12 - w_)                     # keep the box on the map
    by = my - 36
    d.line([(mx, my), (bx if q["side"] == "right" else bx + w_, by + 36)], fill=(150, 215, 255, 200), width=2)
    d.rectangle([bx, by, bx + w_, by + 72], fill=(*PANEL, 215))
    d.rectangle([bx, by, bx + 5, by + 72], fill=(150, 215, 255, 255))
    d.text((bx + 16, by + 7), q["title"], font=F_P, fill=(238, 235, 228, 255))
    d.text((bx + 16, by + 40), q["sub"], font=F_Q, fill=(255, 196, 120, 255))
    al = np.asarray(lay, np.float32)
    al[..., 3] *= a_
    return Image.alpha_composite(base_im, Image.fromarray(al.astype(np.uint8), "RGBA"))

def draw_map(f, seen, now, final, alphas):
    """the map canvas (MW x MH, RGBA): terrain, viewsheds, trail, walker, places, POIs"""
    img = base.copy()
    if seen is not None:                          # faint during the walk, full on the end card
        w_ = 0.75 if final else 0.30
        tint = lit if final else AMBER * 0.45
        img = img * (1 - w_ * seen) + tint * w_ * seen
    if now is not None:
        img = img * (1 - 0.88 * now) + lit * 0.88 * now
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert("RGBA")
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    walked = tkm <= km[f]
    d.line(list(zip(tx, ty)), fill=(150, 160, 180, 150), width=2)
    if walked.sum() > 1:
        d.line(list(zip(tx[walked], ty[walked])), fill=(255, 255, 255, 235), width=3)
    if not final:
        wx, wy = to_px(float(trail[f]["x"]), float(trail[f]["y"]))
        d.ellipse([wx - 9, wy - 9, wx + 9, wy + 9], fill=(255, 255, 255, 255), outline=(20, 20, 20, 255), width=2)
    for n, x, y in places:
        d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=(220, 225, 235, 220))
        d.text((x + 8, y - 13), n, font=F_L, fill=(220, 225, 235, 220))
    im = Image.alpha_composite(im, ov)
    if not final:
        for q in pois:
            im = draw_poi(im, q, alphas.get(q["name"], 0.0))
        return im
    # end card: numbered markers (the legend is drawn with the rest of the text)
    lay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    d.polygon(cham_px, fill=(120, 200, 255, 55), outline=(150, 215, 255, 255), width=3)
    for i, q in enumerate(order, 1):
        mx, my = to_px(q["x"], q["y"])
        d.ellipse([mx - 13, my - 13, mx + 13, my + 13], fill=(150, 215, 255, 255), outline=(10, 14, 22, 255), width=2)
        d.text((mx, my), str(i), font=F_N, fill=(10, 14, 22, 255), anchor="mm")
    return Image.alpha_composite(im, lay)

def profile(d, f, final, x0, x1, top, bot, lab_font):
    """elevation (line) over ground in sight (bars), walker position marked"""
    X = x0 + km / km[-1] * (x1 - x0)
    vb = vis / vis.max() * (bot - top) * 0.92
    for i in range(0, len(X), 2):
        on = i <= f or final
        d.line([(X[i], bot), (X[i], bot - vb[i])], fill=(255, 176, 90, 170 if on else 60), width=2)
    ey = bot - (el - el.min()) / (el.max() - el.min()) * (bot - top) * 0.92
    d.line(list(zip(X, ey)), fill=(228, 233, 242, 235), width=3)
    if not final:
        d.line([(X[f], top), (X[f], bot)], fill=(255, 255, 255, 130), width=2)
        d.ellipse([X[f] - 8, ey[f] - 8, X[f] + 8, ey[f] + 8], fill=(255, 255, 255, 255))
    d.text((x0, bot + 10), f"elevation {el.min():,} to {el.max():,} m · ground in sight", font=lab_font, fill=(150, 156, 170, 255))

def legend(d, x0, y0, lh, f_title, f_sub):
    """the end card's numbered list of places"""
    for i, q in enumerate(order, 1):
        y_ = y0 + (i - 1) * lh
        d.ellipse([x0, y_ + 4, x0 + 26, y_ + 30], fill=(150, 215, 255, 255))
        d.text((x0 + 13, y_ + 17), str(i), font=F_N, fill=(10, 14, 22, 255), anchor="mm")
        d.text((x0 + 40, y_), q["title"].replace("What's visible from ", ""), font=f_title, fill=(238, 235, 228, 255))
        d.text((x0 + 40, y_ + 30), q["sub"], font=f_sub, fill=(255, 196, 120, 255))

CREDIT = "IGN RGE ALTI · © OpenStreetMap contributors"
TITLE = "GR 738, Haute Traversée de Belledonne"
SEEN = st["summary"]["seen_at_least_once_km2"]

def draw_portrait(f, seen, now, final=False, alphas=None):
    im = draw_map(f, seen, now, final, alphas or {})
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    d.rectangle([0, 0, OW, 140], fill=(*PANEL, 185))
    d.text((44, 26), TITLE, font=F_T, fill=(238, 235, 228, 255))
    txt = (f"{km[-1]:.0f} km, Aiguebelle to Vizille  ·  {SEEN:,.0f} km² seen along the way" if final else
           f"km {km[f]:5.1f}   ·   {el[f]:,} m   ·   {vis[f]:,.0f} km² of ground in sight")
    d.text((44, 84), txt, font=F_S, fill=(255, 196, 120, 255))
    top, bot, x0, x1 = OH - 225, OH - 58, 44, OW - 44
    d.rectangle([0, top - 22, OW, OH], fill=(*PANEL, 185))
    profile(d, f, final, x0, x1, top, bot, F_X)
    d.text((x1 - d.textlength(CREDIT, font=F_X), bot + 10), CREDIT, font=F_X, fill=(150, 156, 170, 255))
    if final:
        lines_w = max(max(d.textlength(q["title"], font=F_Q), d.textlength(q["sub"], font=F_X)) for q in order) + 70
        bx0, by0 = OW - 24 - lines_w, 830
        d.rectangle([bx0, by0, OW - 24, by0 + 50 * len(order) + 16], fill=(*PANEL, 215))
        legend(d, bx0 + 14, by0 + 10, 50, F_Q, F_X)
    return Image.alpha_composite(im, ov).convert("RGB")

L_T, L_T2, L_K, L_V, L_S, L_X = font(60, True), font(34), font(36), font(88, True), font(26), font(21)

def draw_landscape(f, seen, now, final=False, alphas=None):
    im = Image.new("RGBA", (OW, OH), (*PANEL, 255))
    im.paste(draw_map(f, seen, now, final, alphas or {}), (MX0, 0))
    d = ImageDraw.Draw(im)
    x0 = 64
    d.text((x0, 64), "GR 738", font=L_T, fill=(238, 235, 228, 255))
    d.text((x0, 140), "Haute Traversée de Belledonne", font=L_T2, fill=(238, 235, 228, 255))
    d.text((x0, 190), "Aiguebelle to Vizille · 131 km · what you can see from the trail", font=L_X, fill=(150, 156, 170, 255))
    if final:
        d.text((x0, 250), f"{SEEN:,.0f} km²", font=L_V, fill=(255, 196, 120, 255))
        d.text((x0, 350), "of ground seen at least once along the way", font=L_S, fill=(200, 204, 214, 255))
        legend(d, x0, 410, 56, F_Q, F_X)
    else:
        d.text((x0, 250), f"{vis[f]:,.0f} km²", font=L_V, fill=(255, 196, 120, 255))
        d.text((x0, 350), "of ground in sight from here", font=L_S, fill=(200, 204, 214, 255))
        d.text((x0, 420), f"km {km[f]:.1f}", font=L_K, fill=(238, 235, 228, 255))
        d.text((x0 + 300, 420), f"{el[f]:,} m", font=L_K, fill=(238, 235, 228, 255))
    profile(d, f, final, x0, MX0 - 64, 730, 960, L_X)
    d.text((x0, OH - 50), CREDIT, font=L_X, fill=(150, 156, 170, 255))
    return im.convert("RGB")

draw = draw_landscape if LAND else draw_portrait
suffix = "-16x9" if LAND else ""

steps = list(range(len(timeline)))
if a.still is not None:                                   # timeline step to check by eye
    steps = [a.still]
elif a.stride > 1:
    steps = steps[::a.stride]
step_set = set(steps)
# walk the whole timeline even for a still, so "seen so far" is right at that step
seen = np.zeros((ch, cw), bool)
last_f, m, done = -1, None, 0
for t in range(steps[-1] + 1):
    f = timeline[t]
    if f != last_f:
        if m is not None:
            seen |= m
        m = np.unpackbits(masks[f], axis=1, count=W).astype(bool)[sl]
        last_f = f
    if t in step_set:
        al = {q["name"]: poi_alpha(q, t) for q in pois}
        draw(f, up(seen) if seen.any() else None, up(m), alphas=al).save(f"{FR}/{done:04d}.png", compress_level=1)
        done += 1
seen |= m
if a.still is not None:
    shutil.copy(f"{FR}/0000.png", f"{D}/renders/gr738_{a.layout}_step_{a.still:04d}.png")
    raise SystemExit
fin = draw(len(trail) - 1, up(seen), None, final=True)
fps = 30 / a.stride
for j in range(int(3 * fps)):
    fin.save(f"{FR}/{done + j:04d}.png", compress_level=1)
fin.save(f"{D}/renders/gr738_final{suffix.replace('-', '_')}.png")
out = f"{D}/renders/day-05-gr738{suffix}{'' if a.stride == 1 else '_preview'}.mp4"
ff = shutil.which("ffmpeg")
if not ff:
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
subprocess.run([ff, "-y", "-loglevel", "error", "-framerate", str(fps), "-i", f"{FR}/%04d.png",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-movflags", "+faststart", out], check=True)
print(f"{out}: {done} frames ({len(pois)} POI pauses) + 3 s end card at {fps:g} fps")
