"""Render scene_markers.blend at low quality and check the camera against the Python fisheye projection.

Python projection (same as 05_sky / 07_compose): r = (N/2) * z / 105 deg, x = c - r sin(az), y = c - r cos(az)
(zenith at centre, north up, east LEFT as seen lying on your back).
Reports, per marker: predicted vs rendered centroid (px), and the skyline check along azimuths.
Usage: python3 check_lens.py [res] [samples]
"""
import json, math, sys
import numpy as np
import bpy
from scipy import ndimage
from common import *

RES = int(sys.argv[1]) if len(sys.argv) > 1 else 1080
SPP = int(sys.argv[2]) if len(sys.argv) > 2 else 16
FOV_HALF = 105.0

bpy.ops.wm.open_mainfile(filepath=str(DERIVED / "scene_markers.blend"))
sc = bpy.context.scene
sc.render.resolution_x = sc.render.resolution_y = RES
sc.cycles.samples = SPP
out = RENDERS / f"check_lens_{RES}.exr"
sc.render.filepath = str(out)
bpy.ops.render.render(write_still=True)

img = bpy.data.images.load(str(out))
px = np.array(img.pixels[:], np.float32).reshape(RES, RES, 4)[::-1]   # row 0 = top
np.save(RENDERS / f"check_lens_{RES}.npy", px)


def project(alt, az, n=RES):
    r = n / 2 * (90 - alt) / FOV_HALF
    a = np.radians(az)
    return n / 2 - r * np.sin(a), n / 2 - r * np.cos(a)


mk = json.load(open(DERIVED / "markers.json"))
rgb = px[..., :3]
mask = rgb.max(-1) > 5.0                     # markers emit 50, everything else is far below 1
lab, nlab = ndimage.label(mask)
cents = np.array(ndimage.center_of_mass(mask, lab, range(1, nlab + 1)))[:, ::-1] + 0.5   # (x, y)
colour = np.array([rgb[lab == i + 1].mean(0) for i in range(nlab)])
print(f"{nlab} marker blobs found")
pred = np.array([project(m["alt"], m["az"]) for m in mk])
rows = []
for m, (px_, py_) in zip(mk, pred):
    if len(cents) == 0:
        break
    d = np.hypot(cents[:, 0] - px_, cents[:, 1] - py_); k = int(d.argmin())
    rows.append((m["name"], m["alt"], m["az"], px_, py_, *cents[k], d[k], "green" if colour[k, 1] > colour[k, 2] * 2 else ""))
deg_per_px = FOV_HALF / (RES / 2)
print("| marker | alt | az | predicted px | rendered px | off (px) | off (deg) |")
for r in rows:
    print(f"| {r[0]} {r[8]} | {r[1]:.2f} | {r[2]:.1f} | {r[3]:.1f},{r[4]:.1f} | {r[5]:.1f},{r[6]:.1f} | {r[7]:.2f} | {r[7]*deg_per_px:.3f} |")

# skyline: along each azimuth, highest ground (alpha) pixel -> elevation; compare with skyline.csv
alpha = px[..., 3]
sk = np.loadtxt(DERIVED / "skyline.csv", delimiter=",", skiprows=1)
errs = []
for az in np.arange(0, 360, 1.0):
    zs = np.linspace(80, FOV_HALF - 0.5, 600)        # from 10 deg up down to the rim
    xs, ys = project(90 - zs, np.full_like(zs, az))
    a = ndimage.map_coordinates(alpha, [ys - 0.5, xs - 0.5], order=1)
    k = np.argmax(a > 0.5)
    if a[k] <= 0.5:
        continue
    el_r = 90 - zs[k]
    el_p = np.interp(az, sk[:, 0], sk[:, 1])
    errs.append((az, el_p, el_r, el_r - el_p))
e = np.array(errs)
print(f"skyline: {len(e)} azimuths, rendered minus profile: median {np.median(e[:,3]):+.3f} deg, "
      f"p95 |err| {np.percentile(np.abs(e[:,3]),95):.3f}, max |err| {np.abs(e[:,3]).max():.3f} (render px = {deg_per_px:.3f} deg)")
np.savetxt(RENDERS / f"check_lens_skyline_{RES}.csv", e, delimiter=",", header="az,profile,render,diff", comments="", fmt="%.3f")
