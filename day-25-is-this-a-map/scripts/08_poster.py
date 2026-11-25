"""Poster: the sky circle from 07_compose.py with white callouts, title, subtitle and sources (1080 x 1350).

python3 08_poster.py [seconds_after_2300]  -> renders/poster_<s>.png
python3 08_poster.py [seconds] --preview  -> renders/preview.png (1600 x 900, landing-page card)
Targets are computed, not placed by hand: stars and the radiant from skyfield at the poster's time, peaks and
towns from the same geometry as the terrain render (azimuth / elevation from the summit). Only the label
positions (offsets from the targets) are chosen by hand.
"""
import sys, json, math, importlib
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from common import *

c = importlib.import_module("07_compose")
sky = c.sky
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
S = float(ARGS[0]) if ARGS else 3044
t = sky.ts.utc(2026, 8, 12, 21, 0, S)

W, H, D = 1080, 1350, c.D
CX, CY = W / 2, 182 + D / 2                       # circle placement on the poster
WHITE, DIM = (255, 255, 255), (200, 200, 200)


def font(size, weight):
    f = ImageFont.truetype(str(RAW / "Inter.ttf"), size)
    try:
        f.set_variation_by_axes([min(max(size, 14), 32), weight])
    except Exception:
        pass
    return f


F_TITLE, F_SUB, F_NAME, F_DET, F_SRC = font(54, 700), font(21, 400), font(19, 600), font(15, 400), font(13, 400)


def to_px(alt, az):
    x, y = c.project(np.array([alt]), np.array([az]))
    return CX - D / 2 + float(x[0]), CY - D / 2 + float(y[0])


def star(hr):
    i = np.where(sky.CAT["hr"] == hr)[0][0]
    alt, az = sky.stars_altaz(t)
    return float(alt[i]), float(az[i])


from skyfield.api import Star
gc = sky.altaz_norefr(Star(ra_hours=17.761, dec_degrees=-29.008), t)          # Galactic centre (Sgr A*)
sat = sky.altaz(sky.eph["saturn barycenter"], t)

# (name, detail, (alt, az), label offset dx, dy, anchor)  ; anchor: 'l' text starts at the label point, 'r' ends there
CALLOUTS = [
    ("Zenith", "straight up, at the center of the view", (90, 0), 120, 120, "l"),
    ("Polaris", "45° up, due north", star(424), 150, -60, "l"),
    ("Deneb", "in Cygnus", star(7924), -150, -110, "r"),
    ("Milky Way", "toward the galactic center in Sagittarius", (max(float(gc[0]), 4.0), float(gc[1])), -40, -125, "r"),
    ("Saturn", "rising in the east", (float(sat[0]), float(sat[1])), 30, -85, "l"),
    ("Mont Blanc", "4,806 m, 103 km away", (1.38, 56.3), 60, -125, "l"),
    ("Aix-les-Bains", "42 km, a glow on the horizon", (-2.2, 16.0), -110, -70, "r"),
    ("Chamechaude", "2,082 m, 4.5 km", (2.72, 155.5), -60, 80, "r"),
    ("Échirolles, Drac valley", "downtown Grenoble is hidden behind the ridge", (-4.6, 189.0), 40, 75, "l"),
]



def poster():
    circ = np.load(RENDERS / f"sky_{int(S)}_circle.npy")
    img = Image.new("RGB", (W, H), (0, 0, 0))
    mask = Image.fromarray((c.INSIDE * 255).astype(np.uint8))
    img.paste(Image.fromarray((circ * 255 + 0.5).astype(np.uint8)), (int(CX - D / 2), int(CY - D / 2)), mask)
    over = Image.new("RGBA", (W * 2, H * 2), (0, 0, 0, 0)); d = ImageDraw.Draw(over)   # 2x for smooth lines
    for name, det, (alt, az), dx, dy, anc in CALLOUTS:
        x, y = to_px(alt, az)
        lx, ly = x + dx, y + dy
        d.ellipse([2 * x - 9, 2 * y - 9, 2 * x + 9, 2 * y + 9], outline=WHITE + (235,), width=3)
        # leader: from the ring to the label, then a short horizontal tick under the text
        ang = math.atan2(ly - y, lx - x)
        d.line([(2 * x + 9 * math.cos(ang), 2 * y + 9 * math.sin(ang)), (2 * lx, 2 * ly)], fill=WHITE + (210,), width=3)
        tick = 16 if anc == "l" else -16
        d.line([(2 * lx, 2 * ly), (2 * (lx + tick), 2 * ly)], fill=WHITE + (210,), width=3)
    img = Image.alpha_composite(img.convert("RGBA"), over.resize((W, H), Image.LANCZOS))
    d = ImageDraw.Draw(img)
    for name, det, (alt, az), dx, dy, anc in CALLOUTS:
        x, y = to_px(alt, az); lx, ly = x + dx, y + dy
        tx = lx + (22 if anc == "l" else -22)
        a = "l" if anc == "l" else "r"
        d.text((tx, ly - 3), name, font=F_NAME, fill=WHITE, anchor=a + "s")
        d.text((tx, ly + 3), det, font=F_DET, fill=DIM, anchor=a + "t")
    # north
    top = CY - D / 2
    d.line([(CX, top - 6), (CX, top - 40)], fill=(255, 255, 255), width=2)
    d.text((CX + 8, top - 30), "N", font=F_NAME, fill=WHITE, anchor="lm")
    d.text((CX - 8, top - 30), "E ←", font=F_DET, fill=DIM, anchor="rm")
    # title block
    d.text((48, 52), "Is this a map?", font=F_TITLE, fill=WHITE, anchor="ls")
    sub = ["A fisheye view looking straight up from the summit of Charmant Som (1,867 m, Chartreuse),",
           "August 12, 2026, 11:50 p.m."]
    for i, line in enumerate(sub):
        d.text((48, 84 + 26 * i), line, font=F_SUB, fill=DIM, anchor="ls")
    # sources
    src = ["Simulated, not photographed. Stars: Yale Bright Star Catalogue (BSC5). Milky Way: ESA/Gaia/DPAC, CC BY-SA 3.0 IGO.",
           "Terrain: IGN RGE ALTI, Copernicus GLO-30. Lights: EOG VIIRS VNL 2025, IGN BD TOPO. Sky brightness: Falchi et al. 2016.",
           "Constellation lines: d3-celestial. Adam Roberts · #30DayMapChallenge Day 25"]
    for i, line in enumerate(src):
        d.text((48, H - 58 + 18 * i), line, font=F_SRC, fill=(150, 150, 150), anchor="ls")
    out = RENDERS / f"poster_{int(S)}.png"
    img.convert("RGB").save(out)
    print("saved", out)


def preview():
    circ = np.load(RENDERS / f"sky_{int(S)}_circle.npy")
    Wp, Hp, Dp = 1600, 900, 840
    img = Image.new("RGB", (Wp, Hp), (0, 0, 0))
    ci = Image.fromarray((circ * 255 + 0.5).astype(np.uint8)).resize((Dp, Dp), Image.LANCZOS)
    m = Image.fromarray((c.INSIDE * 255).astype(np.uint8)).resize((Dp, Dp), Image.LANCZOS)
    img.paste(ci, (40, 30), m)
    d = ImageDraw.Draw(img); x0 = 930
    d.text((x0, 300), "Is this a map?", font=font(64, 700), fill=WHITE, anchor="ls")
    lines = ["A fisheye view looking straight up from", "the summit of Charmant Som (1,867 m, Chartreuse),",
             "August 12, 2026, 11:50 p.m.", "", "The Milky Way overhead, Mont Blanc on the rim,",
             "and the street lights of the valleys below."]
    for i, l in enumerate(lines):
        d.text((x0, 360 + 34 * i), l, font=font(24, 400), fill=DIM, anchor="ls")
    d.text((x0, 840), "#30DayMapChallenge · Day 25", font=font(18, 400), fill=(150, 150, 150), anchor="ls")
    img.save(RENDERS / "preview.png"); print("saved", RENDERS / "preview.png")


if __name__ == "__main__":
    preview() if "--preview" in sys.argv else poster()
