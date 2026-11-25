"""Radial viewshed on the mid25 ring (+-30 km) from the observer's eye. Writes derived/viewshed_mid25.npy
(1 = ground visible) and renders/check_viewshed.png (hillshade, visible ground tinted)."""
import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates
from common import *

name, half, cell = RINGS[1]
a = np.load(DERIVED / f"{name}.npy"); n = a.shape[0]
inner = np.load(DERIVED / "inner5.npy")
eye = GROUND + EYE
vis = np.zeros_like(a, np.uint8)
d = np.arange(2.0, half * 1.0, 6.0)
for az in np.radians(np.arange(0, 360, 0.03)):
    x, y = d * np.sin(az), d * np.cos(az)
    h = np.empty_like(d)
    m = d < 1950
    h[m] = map_coordinates(inner, [(2000 - y[m]) / 5 - .5, (x[m] + 2000) / 5 - .5], order=1)
    row, col = (half - y[~m]) / cell - .5, (x[~m] + half) / cell - .5
    h[~m] = map_coordinates(a, [row, col], order=1)
    e = (h - drop(d) - eye) / d
    v = e >= np.maximum.accumulate(np.r_[-1e9, e[:-1]])
    r, c = np.round((half - y) / cell - .5).astype(int), np.round((x + half) / cell - .5).astype(int)
    ok = (r >= 0) & (r < n) & (c >= 0) & (c < n)
    vis[r[ok & v], c[ok & v]] = 1
np.save(DERIVED / "viewshed_mid25.npy", vis)
gy, gx = np.gradient(a, cell)
hs = np.clip(0.5 + (-gx * 0.7 + gy * 0.7) / np.sqrt(1 + gx**2 + gy**2) * 0.6, 0, 1)
low = a < 600
rgb = np.stack([hs, hs, hs], -1) * 200 + 30
rgb[vis == 1] = rgb[vis == 1] * 0.4 + np.array([255, 170, 40]) * 0.6
rgb[low & (vis == 0)] = rgb[low & (vis == 0)] * 0.6 + np.array([40, 60, 160]) * 0.4
Image.fromarray(rgb.astype(np.uint8)).resize((1200, 1200), Image.LANCZOS).save(RENDERS / "check_viewshed.png")
print("visible cells", vis.mean(), "valley (<600 m) visible share", vis[low].mean())
