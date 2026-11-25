"""Throwaway preview: stars + Saturn + natural sky, real skyline as a black silhouette (no Blender yet).
Checks the fisheye projection (equidistant, 210 deg, zenith up, north top, east left) and the flux scale."""
import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter
import importlib
sky = importlib.import_module("05_sky")
from common import *

W, H = 1080, 1350
CX, CY, RR = 540, 1350 - 20 - 520, 520        # sky circle 1,040 px; rim = 105 deg zenith distance
FOV_HALF = 105.0
SS = 2                                          # supersample
EXPOSURE = 110.0
SIGMA = 1.2


def project(alt, az):
    r = RR * (90 - alt) / FOV_HALF
    a = np.radians(az)
    return CX - r * np.sin(a), CY - r * np.cos(a)


def render(t, out):
    w, h = W * SS, H * SS
    buf = np.zeros((h, w, 3))
    # pixel directions
    yy, xx = np.mgrid[0:h, 0:w] / SS + 0.5 / SS
    dx, dy = xx - CX, yy - CY
    r = np.hypot(dx, dy); z = r / RR * FOV_HALF
    az = (np.degrees(np.arctan2(-dx, -dy))) % 360
    alt = 90 - z
    inside = z <= FOV_HALF
    # natural sky 22.0 mag/arcsec2 at zenith, brighter with airmass; per-pixel flux
    px_arcsec = FOV_HALF / RR * 3600 / SS
    cz = np.clip(np.cos(np.radians(np.clip(z, 0, 89.5))), 1e-3, 1)
    X = 1 / (cz + 0.025 * np.exp(-11 * cz))
    bg = 10 ** (-0.4 * 22.0) * px_arcsec ** 2 * (0.45 + 0.55 * np.minimum(X, 12) ** 0.7)
    buf += bg[..., None] * np.array([0.85, 1.0, 0.95])
    # stars
    s_alt, s_az = sky.stars_altaz(t)
    m = s_alt > -2
    x, y = project(s_alt[m], s_az[m])
    flux = 10 ** (-0.4 * sky.CAT["vmag"][m])
    bv = sky.CAT["bv"][m]
    T = 4600 * (1 / (0.92 * bv + 1.7) + 1 / (0.92 * bv + 0.62))   # Ballesteros 2012
    col = np.stack([np.clip(T / 6500, 0.6, 1.4) ** -0.9, np.ones_like(T), np.clip(T / 6500, 0.6, 1.4) ** 1.1], -1)
    col = 0.6 + 0.4 * col / col.mean(1, keepdims=True)                 # ~40% saturation
    # add Saturn (V ~ 0.6 in Aug 2026; mag computed roughly)
    s_a, s_z = sky.altaz(sky.eph["saturn barycenter"], t)
    sx, sy = project(np.array([s_a]), np.array([s_z]))
    x = np.r_[x, sx]; y = np.r_[y, sy]; flux = np.r_[flux, 10 ** (-0.4 * 0.6)]; col = np.r_[col, [[1.05, 1.0, 0.85]]]
    sig = SIGMA * SS; k = int(4 * sig)
    oy, ox = np.mgrid[-k:k + 1, -k:k + 1]
    for xi, yi, f, c in zip(x * SS, y * SS, flux, col):
        ix, iy = int(xi), int(yi)
        if not (k <= ix < w - k and k <= iy < h - k):
            continue
        g = np.exp(-((ox - (xi - ix - .5)) ** 2 + (oy - (yi - iy - .5)) ** 2) / (2 * sig ** 2))
        buf[iy - k:iy + k + 1, ix - k:ix + k + 1] += (f * g / g.sum())[..., None] * c
    # skyline silhouette
    sk = np.loadtxt(DERIVED / "skyline.csv", delimiter=",", skiprows=1)
    sky_el = np.interp(az, sk[:, 0], sk[:, 1], period=360)
    ground = alt < sky_el
    buf[ground] = 10 ** (-0.4 * 22.0) * px_arcsec ** 2 * 0.15
    buf[~inside] = 0
    lin = buf * EXPOSURE
    lin += gaussian_filter(lin, (6 * SS, 6 * SS, 0)) * 0.08     # bloom
    img = lin / (1 + lin)                                       # simple Reinhard for the preview
    img = np.clip(img, 0, 1) ** (1 / 2.2)
    im = Image.fromarray((img * 255).astype(np.uint8)).resize((W, H), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    d.line([(CX, CY - RR - 8), (CX, CY - RR - 70)], fill=(255, 255, 255), width=2)
    d.text((CX - 4, CY - RR - 92), "N", fill=(255, 255, 255))
    im.save(out)
    print("saved", out)


if __name__ == "__main__":
    render(sky.ts.utc(2026, 8, 12, 21, 30), RENDERS / "preview_2330.png")
