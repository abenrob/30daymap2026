"""Day 3: 4e arrondissement, map <-> sorted (grouped by use, long side horizontal) as a looping 4:5 animation.

Input: buildings/arr04.json (same file the app reads). Usage: python 04_make_animation.py 4 [ss]. Writes PNG frames to frames/; encode with ffmpeg (see README).
One scale for both states, so building sizes stay true throughout.
"""
import json, math, os, sys
from PIL import Image, ImageDraw, ImageFont

ARR = int(sys.argv[1]) if len(sys.argv) > 1 else 4
W, H = 1080, 1350
SS = int(sys.argv[2]) if len(sys.argv) > 2 else 2   # supersampling: 2 for the MP4, 1 for the GIF (crisp edges keep it small)
FPS = 25
HOLD_MAP, MOVE, HOLD_SORT = 1.6, 2.2, 2.8     # seconds
BG, SUB, FOOT, FAINT = "#0f1115", "#c9ccd3", "#8a8f99", "#4a5060"
TYPES = [("Residential", "#f2b134"), ("Commercial & services", "#4fb3d9"), ("Industrial", "#b07cf0"),
         ("Religious", "#ef6f6c"), ("Sports", "#5fd38d"), ("Agricultural", "#9bc53d"), ("Annex", "#8a8f99"),
         ("Unspecified", "#5a6070")]
F = "/usr/share/fonts/opentype/inter/"
font = lambda name, px: ImageFont.truetype(F + name, px * SS)

d = json.load(open(f"buildings/arr{ARR:02d}.json"))
Hm = d["h"] / 10
B = []
for t, area, h, dw, ang, rings in d["b"]:
    rs = [[(r[i] / 10, Hm - r[i + 1] / 10) for i in range(0, len(r), 2)] for r in rings]
    xs = [p[0] for r in rs for p in r]; ys = [p[1] for r in rs for p in r]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    rs = [[(x - cx, y - cy) for x, y in r] for r in rs]
    B.append(dict(t=t, area=area, ang=-ang, rs=rs, cx=cx, cy=cy))
outline = [[(r[i] / 10, Hm - r[i + 1] / 10) for i in range(0, len(r), 2)] for r in d["outline"]]
Wm = d["w"] / 10

# drawing box (px) between the title block and the legend
BX0, BY0, BX1, BY1 = 60, 230, W - 60, H - 150
bw, bh = BX1 - BX0, BY1 - BY0

# rotated bounding boxes, long side horizontal
for b in B:
    th = -b["ang"]; c, s = math.cos(th), math.sin(th)
    pts = [(c * x - s * y, s * x + c * y) for r in b["rs"] for x, y in r]
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts); y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    if y1 - y0 > x1 - x0:
        th += math.pi / 2; x0, x1, y0, y1 = -y1, -y0, x0, x1
    b.update(th=th, bw=x1 - x0, bh=y1 - y0, bcx=(x0 + x1) / 2, bcy=(y0 + y1) / 2)

order = sorted(range(len(B)), key=lambda i: (B[i]["t"], -B[i]["area"]))
GAP = 1.5


def pack(labH, Wl):
    x = y = rowH = 0; last = -1; labels = []
    for i in order:
        b = B[i]
        if b["t"] != last:
            if x > 0: y += rowH + GAP; x = 0; rowH = 0
            y += labH + GAP * 2; labels.append((b["t"], y)); last = b["t"]
        if x > 0 and x + b["bw"] > Wl: x = 0; y += rowH + GAP; rowH = 0
        b["sx"] = x + b["bw"] / 2; b["sy"] = y + b["bh"] / 2; x += b["bw"] + GAP; rowH = max(rowH, b["bh"])
    return Wl, y + rowH, labels


# one scale, set by the map; the sorted layout uses the full box width at that scale
s = min(bw / Wm, bh / Hm)
for _ in range(20):
    Wl, Hl, labels = pack(26 / s, bw / s)
    if Hl * s <= bh: break
    s *= 0.97
mx, my = BX0 + (bw - Wm * s) / 2, BY0 + (bh - Hm * s) / 2
lx, ly = BX0 + (bw - Wl * s) / 2, BY0 + (bh - Hl * s) / 2
present = sorted({b["t"] for b in B})

ease = lambda t: 4 * t ** 3 if t < .5 else 1 - (-2 * t + 2) ** 3 / 2


def frame(e):
    im = Image.new("RGB", (W * SS, H * SS), BG); dr = ImageDraw.Draw(im)
    # outline of the arrondissement, fading out
    if e < 1:
        col = tuple(int(int(FAINT[k:k + 2], 16) * (1 - e) + int(BG[k:k + 2], 16) * e) for k in (1, 3, 5))
        for r in outline:
            pts = [((mx + x * s) * SS, (my + y * s) * SS) for x, y in r]
            for a, b2 in zip(pts[::2], pts[1::2]):
                dr.line([a, b2], fill=col, width=SS)
    for b in B:
        th = b["th"] * e; c, sn = math.cos(th), math.sin(th)
        ox0, oy0 = mx + b["cx"] * s, my + b["cy"] * s
        ox1, oy1 = lx + (b["sx"] - b["bcx"]) * s, ly + (b["sy"] - b["bcy"]) * s
        ox, oy = ox0 + (ox1 - ox0) * e, oy0 + (oy1 - oy0) * e
        for r in b["rs"]:
            pts = [((ox + (c * x - sn * y) * s) * SS, (oy + (sn * x + c * y) * s) * SS) for x, y in r]
            if len(pts) >= 3: dr.polygon(pts, fill=TYPES[b["t"]][1])
    # group labels fade in with the sorted state
    if e > 0.6:
        f = font("Inter-Medium.otf", 15); a = (e - 0.6) / 0.4
        col = tuple(int(int(SUB[k:k + 2], 16) * a + int(BG[k:k + 2], 16) * (1 - a)) for k in (1, 3, 5))
        for t, y in labels:
            dr.text((lx * SS, (ly + y * s - 6) * SS), TYPES[t][0], font=f, fill=col, anchor="ls")
    # title block
    dr.text((60 * SS, 78 * SS), f"{d['n']}e arrondissement · {len(B):,} buildings", font=font("Inter-Bold.otf", 34), fill="white", anchor="ls")
    fc = font("Inter-Regular.otf", 22)
    for txt, a in (("As built", max(0, 1 - 2 * e)), ("Sorted by use, then size", max(0, 2 * e - 1))):
        if a > 0.01:
            col = tuple(int(int(SUB[k:k + 2], 16) * a + int(BG[k:k + 2], 16) * (1 - a)) for k in (1, 3, 5))
            dr.text((60 * SS, 118 * SS), txt, font=fc, fill=col, anchor="ls")
    # legend
    fl = font("Inter-Regular.otf", 15); x = 60
    for t in present:
        name, colr = TYPES[t]
        dr.rectangle([x * SS, (H - 104) * SS, (x + 12) * SS, (H - 92) * SS], fill=colr)
        dr.text(((x + 18) * SS, (H - 92) * SS), name, font=fl, fill=SUB, anchor="ls")
        x += 18 + dr.textlength(name, font=fl) / SS + 22
        if x > W - 200: x = 60  # (not reached for the 4e)
    # scale bar
    m = next(v for v in (10, 20, 50, 100, 200, 500) if v * s >= 60)
    dr.line([(W - 60 - m * s) * SS, (H - 98) * SS, (W - 60) * SS, (H - 98) * SS], fill=FOOT, width=2 * SS)
    dr.text(((W - 60) * SS, (H - 106) * SS), f"{m} m", font=fl, fill=FOOT, anchor="rs")
    dr.text((60 * SS, (H - 52) * SS), "Same scale throughout. IGN BD TOPO buildings (Licence Ouverte 2.0), one per plot.", font=font("Inter-Regular.otf", 14), fill=FOOT, anchor="ls")
    dr.text((60 * SS, (H - 30) * SS), "Adam Roberts · #30DayMapChallenge 2026, day 3: Polygons", font=font("Inter-Regular.otf", 14), fill=FOOT, anchor="ls")
    return im.resize((W, H), Image.LANCZOS)


os.makedirs("frames", exist_ok=True)
for f in os.listdir("frames"): os.remove("frames/" + f)
seq = [0] * int(HOLD_MAP * FPS) + [ease(i / (MOVE * FPS)) for i in range(int(MOVE * FPS) + 1)] + \
      [1] * int(HOLD_SORT * FPS) + [ease(1 - i / (MOVE * FPS)) for i in range(int(MOVE * FPS) + 1)]
cache = {}
for k, e in enumerate(seq):
    key = round(e, 4)
    if key not in cache: cache[key] = frame(e)
    cache[key].save(f"frames/{k:04d}.png")
    if len(cache) > 4 and key not in (0, 1): cache.pop(key)
print(len(seq), "frames", "scale px/m", round(s, 3))
