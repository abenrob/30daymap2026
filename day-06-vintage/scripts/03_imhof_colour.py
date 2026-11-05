"""Day 6 Vintage: colour the Blender relief passes in the manner of Eduard Imhof.

Swiss-style relief rules applied (Imhof, Cartographic Relief Presentation, 1965/1982):
  - light from the upper left (north-west)
  - lit slopes warm (yellowish), shaded slopes cool (blue-violet grey)
  - aerial perspective: contrast grows with altitude, so summits are crisp and
    lowlands recede into a pale, hazy blue-green
  - hypsometric tint kept light so the shading carries the form

Usage: python 03_imhof_colour.py RENDERDIR DEM.npy OUT.png [--sun 0.75 --sky 0.45]
"""
import argparse
import numpy as np
from PIL import Image


def load(p):
    im = np.asarray(Image.open(p)).astype(np.float32)
    return im / (65535.0 if im.max() > 255 else 255.0)


def lerp(a, b, t):
    return a + (b - a) * t[..., None]


def ramp(stops, t):
    """stops: list of (pos, (r,g,b)) with pos in 0..1, t: array 0..1"""
    pos = np.array([s[0] for s in stops])
    cols = np.array([s[1] for s in stops], dtype=np.float32) / 255.0
    out = np.empty(t.shape + (3,), np.float32)
    for c in range(3):
        out[..., c] = np.interp(t, pos, cols[:, c])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("renderdir")
    ap.add_argument("dem")
    ap.add_argument("out")
    ap.add_argument("--sun", type=float, default=0.7)
    ap.add_argument("--sky", type=float, default=0.3)
    a = ap.parse_args()

    sun = load(f"{a.renderdir}/sun.png")
    sky = load(f"{a.renderdir}/sky.png")
    h, w = sun.shape

    dem = np.load(a.dem)
    # resample DEM to render size (nearest is fine for colour)
    yi = (np.arange(h) * dem.shape[0] / h).astype(int)
    xi = (np.arange(w) * dem.shape[1] / w).astype(int)
    z = dem[yi][:, xi]
    t = np.clip((z - np.percentile(z, 1)) / (np.percentile(z, 99.8) - np.percentile(z, 1)), 0, 1)

    # normalise passes so a flat plain sits near mid tone
    def stretch(x, lo=0.5, hi=99.7):
        p0, p1 = np.percentile(x, [lo, hi])
        return np.clip((x - p0) / (p1 - p0), 0, 1)
    # the sky pass varies little (open terrain), so stretch both to full range
    shade = (a.sun * stretch(sun) + a.sky * stretch(sky)) / (a.sun + a.sky)

    # aerial perspective: compress contrast around the flat-plain tone at low altitude
    flat = np.median(shade[t < 0.15]) if (t < 0.15).any() else 0.6
    k = 0.70 + 0.60 * t ** 0.8
    shade = np.clip(flat + (shade - flat) * k, 0, 1)

    # hypsometric base: pale grey-green lowland -> sage -> buff -> near-white summits
    base = ramp([(0.00, (172, 186, 170)),
                 (0.30, (190, 198, 168)),
                 (0.55, (214, 208, 172)),
                 (0.80, (232, 224, 196)),
                 (1.00, (248, 244, 230))], t)
    # light and shadow tints, also altitude dependent (haze bluer low down)
    shadow = ramp([(0.0, (92, 108, 128)), (1.0, (70, 72, 104))], t)
    light = ramp([(0.0, (236, 238, 226)), (1.0, (255, 248, 222))], t)

    # below flat tone: towards shadow colour; above: towards light colour
    s = shade
    dark = np.clip((flat - s) / flat, 0, 1)
    bright = np.clip((s - flat) / (1 - flat), 0, 1)
    rgb = base * (1 - dark[..., None]) + shadow * dark[..., None]
    rgb = rgb * (1 - bright[..., None]) + light * bright[..., None]

    # faint haze veil on the lowlands
    haze = np.array([200, 212, 216], np.float32) / 255.0
    rgb = lerp(rgb, np.broadcast_to(haze, rgb.shape), 0.25 * (1 - t) ** 2)

    Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8)).save(a.out)
    print("wrote", a.out, w, "x", h)


if __name__ == "__main__":
    main()
