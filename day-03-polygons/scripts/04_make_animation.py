"""Day 3, step 4: the posted animation. One arrondissement goes from the map to the sorted
rows (grouped by use, long side horizontal) and back, as a looping 4:5 video.

Reads:  buildings/arrNN.json (the same file the page loads)
Writes: frames/0000.png ... (encode them with ffmpeg, see README)

    python 04_make_animation.py 4      # 4e arrondissement, antialiased frames for the MP4
    python 04_make_animation.py 4 1    # no antialiasing: crisp edges keep the GIF under 5 MB

Map and sorted views use one scale, so building sizes stay true throughout. This is a
Python port of the Sorted view in index.html; the layout logic is the same.
"""
import json
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

ARR = int(sys.argv[1]) if len(sys.argv) > 1 else 4
W, H = 1080, 1350                                    # 4:5 portrait, LinkedIn's best fit
SS = int(sys.argv[2]) if len(sys.argv) > 2 else 2    # supersampling: draw at SS x size, then shrink
FPS = 25
HOLD_MAP, MOVE, HOLD_SORT = 1.6, 2.2, 2.8            # seconds for each phase of the loop
BG, SUB, FOOT, FAINT = "#0f1115", "#c9ccd3", "#8a8f99", "#4a5060"
# Same order as TYPES in 03_export.py and index.html.
TYPES = [("Residential", "#f2b134"), ("Commercial & services", "#4fb3d9"), ("Industrial", "#b07cf0"),
         ("Religious", "#ef6f6c"), ("Sports", "#5fd38d"), ("Agricultural", "#9bc53d"), ("Annex", "#8a8f99"),
         ("Unspecified", "#5a6070")]
F = "/usr/share/fonts/opentype/inter/"  # Inter; change this path to wherever your fonts live
font = lambda name, px: ImageFont.truetype(F + name, px * SS)

# ---- Load the buildings ------------------------------------------------------------------
# The file stores integer decimetres with y pointing north. Convert to metres with y pointing
# down (image coordinates), then store each outline relative to the centre of its own
# bounding box, so a building can be rotated about its centre and moved as one piece.
d = json.load(open(f"buildings/arr{ARR:02d}.json"))
Hm = d["h"] / 10  # arrondissement height in metres, used to flip y
B = []
for t, area, h, dw, ang, rings in d["b"]:
    rs = [[(r[i] / 10, Hm - r[i + 1] / 10) for i in range(0, len(r), 2)] for r in rings]
    xs = [p[0] for r in rs for p in r]
    ys = [p[1] for r in rs for p in r]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    rs = [[(x - cx, y - cy) for x, y in r] for r in rs]
    # Flipping y mirrors angles too, hence -ang.
    B.append(dict(t=t, area=area, ang=-ang, rs=rs, cx=cx, cy=cy))
outline = [[(r[i] / 10, Hm - r[i + 1] / 10) for i in range(0, len(r), 2)] for r in d["outline"]]
Wm = d["w"] / 10

# Drawing area in pixels, between the title block (top) and the legend (bottom).
BX0, BY0, BX1, BY1 = 60, 230, W - 60, H - 150
bw, bh = BX1 - BX0, BY1 - BY0

# ---- Size of each building once rotated ----------------------------------------------------
# Rotate the outline so its long axis lies along x, then measure its bounding box: that box
# is the slot the building needs in a row. The minimum rotated rectangle can report the axis
# either way round, so if the result is taller than wide, turn it a further 90 degrees.
for b in B:
    th = -b["ang"]
    c, s = math.cos(th), math.sin(th)
    pts = [(c * x - s * y, s * x + c * y) for r in b["rs"] for x, y in r]
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    if y1 - y0 > x1 - x0:
        th += math.pi / 2
        x0, x1, y0, y1 = -y1, -y0, x0, x1  # the same box, rotated 90 degrees
    # th: final rotation; bw x bh: slot size in metres; (bcx, bcy): box centre after rotation,
    # which is not exactly the building's own centre once it is turned.
    b.update(th=th, bw=x1 - x0, bh=y1 - y0, bcx=(x0 + x1) / 2, bcy=(y0 + y1) / 2)

# Sort by use first (that is what "grouped by use" means), then largest first within each use.
order = sorted(range(len(B)), key=lambda i: (B[i]["t"], -B[i]["area"]))
GAP = 1.5  # metres between neighbouring buildings


def pack(labH, Wl):
    """Shelf packing: place buildings left to right; when the next one does not fit in the row
    width Wl, start a new row below. A row is as tall as its tallest building, which is
    usually the first, since sizes go down along the row. Each use starts a new block with
    labH metres of space above it for its label. Sets each building's slot centre (sx, sy)
    in metres and returns the layout's width, height and the label positions."""
    x = y = rowH = 0
    last = -1
    labels = []
    for i in order:
        b = B[i]
        if b["t"] != last:                      # first building of a new use
            if x > 0:                           # close the current row
                y += rowH + GAP
                x = 0
                rowH = 0
            y += labH + GAP * 2                 # room for the label
            labels.append((b["t"], y))
            last = b["t"]
        if x > 0 and x + b["bw"] > Wl:          # row full: wrap
            x = 0
            y += rowH + GAP
            rowH = 0
        b["sx"] = x + b["bw"] / 2
        b["sy"] = y + b["bh"] / 2
        x += b["bw"] + GAP
        rowH = max(rowH, b["bh"])
    return Wl, y + rowH, labels


# ---- One scale for both views -----------------------------------------------------------
# Start from the scale that fits the map in the drawing area. Pack the rows at the full
# drawing width for that scale. If the rows end up too tall, shrink the scale by 3% and
# pack again (a smaller scale means more metres per row, so fewer rows). Label space is
# given in metres (26 px / scale), so it is recomputed on each pass.
s = min(bw / Wm, bh / Hm)  # pixels per metre
for _ in range(20):
    Wl, Hl, labels = pack(26 / s, bw / s)
    if Hl * s <= bh:
        break
    s *= 0.97
# Top-left corners that centre the map and the rows in the drawing area.
mx, my = BX0 + (bw - Wm * s) / 2, BY0 + (bh - Hm * s) / 2
lx, ly = BX0 + (bw - Wl * s) / 2, BY0 + (bh - Hl * s) / 2
present = sorted({b["t"] for b in B})  # legend lists only the uses this arrondissement has

# Ease in and out (cubic), so buildings start and stop gently.
ease = lambda t: 4 * t ** 3 if t < .5 else 1 - (-2 * t + 2) ** 3 / 2


def mix(fg, a):
    """Colour fg faded towards the background by alpha a (0 = background, 1 = fg).
    PIL draws opaque colours, so fades are done by blending with the background."""
    return tuple(int(int(fg[k:k + 2], 16) * a + int(BG[k:k + 2], 16) * (1 - a)) for k in (1, 3, 5))


def frame(e):
    """Draw one frame. e is the progress from map (0) to sorted rows (1), already eased."""
    im = Image.new("RGB", (W * SS, H * SS), BG)
    dr = ImageDraw.Draw(im)

    # Arrondissement boundary, dashed (every other segment) and fading out as buildings leave.
    if e < 1:
        col = mix(FAINT, 1 - e)
        for r in outline:
            pts = [((mx + x * s) * SS, (my + y * s) * SS) for x, y in r]
            for a, b2 in zip(pts[::2], pts[1::2]):
                dr.line([a, b2], fill=col, width=SS)

    # Each building: interpolate the rotation (0 on the map, th in the rows) and the position
    # of its centre, from where it stands on the map to its slot. In the rows, the slot centre
    # is the centre of the rotated box, so the building's own centre sits (bcx, bcy) away from it.
    for b in B:
        th = b["th"] * e
        c, sn = math.cos(th), math.sin(th)
        ox0, oy0 = mx + b["cx"] * s, my + b["cy"] * s                              # on the map
        ox1, oy1 = lx + (b["sx"] - b["bcx"]) * s, ly + (b["sy"] - b["bcy"]) * s    # in its slot
        ox, oy = ox0 + (ox1 - ox0) * e, oy0 + (oy1 - oy0) * e
        for r in b["rs"]:
            pts = [((ox + (c * x - sn * y) * s) * SS, (oy + (sn * x + c * y) * s) * SS) for x, y in r]
            if len(pts) >= 3:
                dr.polygon(pts, fill=TYPES[b["t"]][1])

    # Group labels appear only once the buildings have nearly settled (last 40% of the move).
    if e > 0.6:
        f = font("Inter-Medium.otf", 15)
        col = mix(SUB, (e - 0.6) / 0.4)
        for t, y in labels:
            dr.text((lx * SS, (ly + y * s - 6) * SS), TYPES[t][0], font=f, fill=col, anchor="ls")

    # Title, then the caption: "As built" fades out over the first half of the move and
    # "Sorted by use, then size" fades in over the second half, so they never overlap.
    dr.text((60 * SS, 78 * SS), f"{d['n']}e arrondissement · {len(B):,} buildings",
            font=font("Inter-Bold.otf", 34), fill="white", anchor="ls")
    fc = font("Inter-Regular.otf", 22)
    for txt, a in (("As built", max(0, 1 - 2 * e)), ("Sorted by use, then size", max(0, 2 * e - 1))):
        if a > 0.01:
            dr.text((60 * SS, 118 * SS), txt, font=fc, fill=mix(SUB, a), anchor="ls")

    # Legend: swatch + name, laid out left to right.
    fl = font("Inter-Regular.otf", 15)
    x = 60
    for t in present:
        name, colr = TYPES[t]
        dr.rectangle([x * SS, (H - 104) * SS, (x + 12) * SS, (H - 92) * SS], fill=colr)
        dr.text(((x + 18) * SS, (H - 92) * SS), name, font=fl, fill=SUB, anchor="ls")
        x += 18 + dr.textlength(name, font=fl) / SS + 22

    # Scale bar: the first round length that is at least 60 px long.
    m = next(v for v in (10, 20, 50, 100, 200, 500) if v * s >= 60)
    dr.line([(W - 60 - m * s) * SS, (H - 98) * SS, (W - 60) * SS, (H - 98) * SS], fill=FOOT, width=2 * SS)
    dr.text(((W - 60) * SS, (H - 106) * SS), f"{m} m", font=fl, fill=FOOT, anchor="rs")

    dr.text((60 * SS, (H - 52) * SS),
            "Same scale throughout. IGN BD TOPO buildings (Licence Ouverte 2.0), one per plot.",
            font=font("Inter-Regular.otf", 14), fill=FOOT, anchor="ls")
    dr.text((60 * SS, (H - 30) * SS), "Adam Roberts · #30DayMapChallenge 2026, day 3: Polygons",
            font=font("Inter-Regular.otf", 14), fill=FOOT, anchor="ls")
    # Shrinking the supersampled image is what gives smooth (antialiased) edges.
    return im.resize((W, H), Image.LANCZOS)


# ---- The loop ---------------------------------------------------------------------------
# Progress value for every frame: hold on the map, move to the rows, hold, move back.
# The last frame is the map again, so the video loops without a jump.
os.makedirs("frames", exist_ok=True)
for f in os.listdir("frames"):
    os.remove("frames/" + f)
seq = ([0] * int(HOLD_MAP * FPS)
       + [ease(i / (MOVE * FPS)) for i in range(int(MOVE * FPS) + 1)]
       + [1] * int(HOLD_SORT * FPS)
       + [ease(1 - i / (MOVE * FPS)) for i in range(int(MOVE * FPS) + 1)])

# Hold frames repeat the same image, so each distinct progress value is drawn once and the
# PNG is written for every frame. The two end states (0 and 1) stay cached for the whole run.
cache = {}
for k, e in enumerate(seq):
    key = round(e, 4)
    if key not in cache:
        cache[key] = frame(e)
    cache[key].save(f"frames/{k:04d}.png")
    if len(cache) > 4 and key not in (0, 1):
        cache.pop(key)
print(len(seq), "frames, scale", round(s, 3), "px per metre")
