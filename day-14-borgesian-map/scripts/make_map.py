"""Day 14 Borgesian map: Barcelona, 1:1. 4:5 portrait sheet, square map frame."""
import sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps, ImageEnhance

SRC, OUT = sys.argv[1], sys.argv[2]
F = sys.argv[3] if len(sys.argv) > 3 else 'fonts/'

def font(name, size):
    return ImageFont.truetype(F + name, size)

PX_PER_TILE_SRC = 83.0          # measured by autocorrelation on the photo
TILE_CM = 20.0

# square crop of the photo, centred vertically
src = Image.open(SRC).convert('RGB')
w, h = src.size
side = min(w, h)
top = (h - side) // 2
src = src.crop((0, top, side, top + side))
map_cm = side / PX_PER_TILE_SRC * TILE_CM

W, H = 2400, 3000
PAPER = (244, 240, 230)
INK = (28, 28, 28)
GREY = (110, 106, 98)
canvas = Image.new('RGB', (W, H), PAPER)
d = ImageDraw.Draw(canvas)

def tint(im):
    return Image.blend(im, ImageOps.colorize(ImageOps.grayscale(im), (30, 30, 34), (236, 232, 222)), 0.55)

MS = 1840
MX = (W - MS) // 2
MY = 480
B = 24
px_cm = MS / map_cm
L = MX - B - 4                    # left edge of the outer neatline
R = MX + MS + B + 3               # right edge

img = src.resize((MS, MS), Image.LANCZOS)
img = img.filter(ImageFilter.UnsharpMask(radius=3, percent=60, threshold=2))
img = tint(ImageEnhance.Contrast(img).enhance(1.08))
canvas.paste(img, (MX, MY))

# ---------- title band
small = font('Barlow-Medium.ttf', 30)
d.text((L, 110), 'INSTITUT CARTOGRÀFIC IMAGINARI   ·   TOPOGRAPHIC SERIES 1:1', font=small, fill=GREY)
title = font('BarlowCondensed-SemiBold.ttf', 210)
d.text((L - 6, 140), 'BARCELONA', font=title, fill=INK)
sub = font('Barlow-Regular.ttf', 36)
tx = L + d.textlength('BARCELONA', font=title) + 50
d.text((tx, 232), 'Complete survey', font=sub, fill=INK)
d.text((tx, 280), 'Sheet 1 of approx. 105 000 000', font=sub, fill=INK)

# north arrow, top right of the band
na_cx, na_top, na_h = R - 70, 170, 170
nf = font('BarlowCondensed-SemiBold.ttf', 64)
tw = d.textlength('N', font=nf)
d.text((na_cx - tw / 2, 92), 'N', font=nf, fill=INK)
d.polygon([(na_cx, na_top), (na_cx - 40, na_top + na_h), (na_cx, na_top + na_h - 45)], fill=INK)
d.line([(na_cx, na_top), (na_cx + 40, na_top + na_h), (na_cx, na_top + na_h - 45)], fill=INK, width=3)
d.line([L, 380, R, 380], fill=INK, width=3)

# ---------- neatline + graduated border
d.rectangle([MX - 1, MY - 1, MX + MS, MY + MS], outline=INK, width=3)
d.rectangle([L, MY - B - 4, R, MY + MS + B + 3], outline=INK, width=3)
step_cm = 10
i = 0
while i * step_cm * px_cm < MS:
    a = i * step_cm * px_cm
    b = min((i + 1) * step_cm * px_cm, MS)
    if i % 2 == 0:
        d.rectangle([MX + a, MY - B - 2, MX + b, MY - 3], fill=INK)
        d.rectangle([MX + a, MY + MS + 2, MX + b, MY + MS + B + 1], fill=INK)
        d.rectangle([MX - B - 2, MY + MS - b, MX - 3, MY + MS - a], fill=INK)
        d.rectangle([MX + MS + 2, MY + MS - b, MX + MS + B + 1, MY + MS - a], fill=INK)
    i += 1

lab = font('Barlow-Regular.ttf', 28)
for c in range(0, int(map_cm) + 1, 20):
    p = c * px_cm
    t = f'{c/100:.2f} m'
    tw = d.textlength(t, font=lab)
    d.text((MX + p - tw / 2, MY - B - 46), t, font=lab, fill=INK)
    d.text((MX + p - tw / 2, MY + MS + B + 12), t, font=lab, fill=INK)
    ti = Image.new('RGBA', (int(tw) + 4, 36), (0, 0, 0, 0))
    ImageDraw.Draw(ti).text((2, 0), t, font=lab, fill=INK)
    r = ti.rotate(90, expand=True)
    canvas.paste(r, (MX - B - 48, int(MY + MS - p - r.size[1] / 2)), r)
    r2 = ti.rotate(-90, expand=True)
    canvas.paste(r2, (MX + MS + B + 14, int(MY + MS - p - r2.size[1] / 2)), r2)
    for c2 in range(20, int(map_cm), 20):
        if 0 < c < map_cm:
            x, y = MX + p, MY + MS - c2 * px_cm
            d.line([x - 15, y, x + 15, y], fill=(250, 248, 240), width=3)
            d.line([x, y - 15, x, y + 15], fill=(250, 248, 240), width=3)

# ---------- scale bar, true map scale, centred under the map
u = px_cm
sb_y = MY + MS + B + 115
sb_x = MX + (MS - 80 * u) / 2 + 20 * u
for k in range(3):
    x0 = sb_x + k * 20 * u
    d.rectangle([x0, sb_y, x0 + 20 * u, sb_y + 20], fill=INK if k % 2 == 0 else PAPER, outline=INK, width=2)
for k in range(4):
    x0 = sb_x - 20 * u + k * 5 * u
    d.rectangle([x0, sb_y, x0 + 5 * u, sb_y + 20], fill=INK if k % 2 == 1 else PAPER, outline=INK, width=2)
sbf = font('Barlow-Regular.ttf', 28)
for v, xv in ((20, sb_x - 20 * u), (0, sb_x), (20, sb_x + 20 * u), (40, sb_x + 40 * u), (60, sb_x + 60 * u)):
    tw = d.textlength(str(v), font=sbf)
    d.text((xv - tw / 2, sb_y - 42), str(v), font=sbf, fill=INK)
d.text((sb_x + 60 * u + 16, sb_y - 42), 'cm', font=sbf, fill=INK)
sf = font('Barlow-Medium.ttf', 34)
t = 'Scale 1:1 when printed 98 cm wide'
tw = d.textlength(t, font=sf)
d.text((MX + MS / 2 - tw / 2, sb_y + 42), t, font=sf, fill=INK)

# ---------- bottom band: legend (2 x 2) left, notes right
by = sb_y + 105
d.line([L, by, R, by], fill=INK, width=2)
by += 34
hd = font('BarlowCondensed-SemiBold.ttf', 42)
d.text((L, by), 'LEGEND', font=hd, fill=INK)
ly = by + 70
lf = font('Barlow-Regular.ttf', 29)
lfi = font('Barlow-Italic.ttf', 25)
LEGEND_TILE = sys.argv[4] if len(sys.argv) > 4 else 'legend_panot.png'
tile = tint(Image.open(LEGEND_TILE).convert('RGB').resize((84, 84), Image.LANCZOS))

def sw_tile(x, y):
    canvas.paste(tile, (x, y)); d.rectangle([x, y, x + 84, y + 84], outline=INK, width=2)
def sw_petal(x, y):
    d.ellipse([x + 20, y + 20, x + 64, y + 64], outline=INK, width=3)
def sw_joint(x, y):
    d.line([x, y + 42, x + 84, y + 42], fill=INK, width=3)
def sw_cross(x, y):
    d.line([x + 26, y + 42, x + 58, y + 42], fill=INK, width=3); d.line([x + 42, y + 26, x + 42, y + 58], fill=INK, width=3)

items = [
    (sw_tile, 'Panot de flor, 20 × 20 cm', 'Puig i Cadafalch pattern, 1906'),
    (sw_petal, 'Petal', 'four per panot, no exceptions found'),
    (sw_joint, 'Joint', 'mortar, width variable'),
    (sw_cross, 'Grid intersection, 20 cm', 'local grid, origin at lower left'),
]
colw = 620
for n, (sw, a, b) in enumerate(items):
    x = L + (n % 2) * colw
    y = ly + (n // 2) * 120
    sw(x, y)
    d.text((x + 110, y + 6), a, font=lf, fill=INK)
    d.text((x + 110, y + 46), b, font=lfi, fill=GREY)

NX = L + 2 * colw + 40
d.line([NX - 40, by, NX - 40, ly + 210], fill=INK, width=2)
notes = [
    'Survey: one photograph.',
    'Contour interval: not applicable.',
    'Generalisation: none. Projection: unnecessary.',
    'After J. L. Borges, "On Exactitude in Science" (1946).',
    '#30DayMapChallenge  ·  Day 14  ·  A Borgesian map',
    'Adam Roberts  ·  November 2026',
]
nfs = 26
while max(d.textlength(t, font=font('Barlow-Regular.ttf', nfs)) for t in notes) > R - NX:
    nfs -= 1
nf2 = font('Barlow-Regular.ttf', nfs)
ny = by + 6
for t in notes:
    d.text((NX, ny), t, font=nf2, fill=INK if t.startswith('#') else GREY)
    ny += int(nfs * 1.5)

canvas.save(OUT)
print('map_cm', round(map_cm, 1), 'px_cm', round(px_cm, 2), 'legend bottom', ly + 210, 'notes bottom', ny, 'H', H)
