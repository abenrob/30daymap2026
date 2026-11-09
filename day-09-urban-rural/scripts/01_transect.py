"""Straight transect from Paris (Notre-Dame, point zero) to Chartres cathedral, in Lambert-93.

One sample every 1 km. Each sample owns a window 1 km along the line and 3 km across it
(03_sample.py averages every layer over that window). Writes transect.json.
"""
import json, numpy as np
from pyproj import Transformer

A = (2.3488, 48.8534)   # Paris, point zéro des routes de France (lon, lat)
B = (1.4875, 48.4478)   # Chartres cathedral
STEP, HALF_W = 1000.0, 1500.0   # metres: sample spacing, half the window width

to93 = Transformer.from_crs(4326, 2154, always_xy=True)
to84 = Transformer.from_crs(2154, 4326, always_xy=True)
ax, ay = to93.transform(*A); bx, by = to93.transform(*B)

# unit vector along the line (u) and perpendicular to it (n)
L = np.hypot(bx - ax, by - ay)
ux, uy = (bx - ax) / L, (by - ay) / L
nx, ny = -uy, ux

n = int(L // STEP) + 1
samples = []
for i in range(n):
    d = min(i * STEP, L); cx, cy = ax + ux * d, ay + uy * d
    lon, lat = to84.transform(cx, cy)
    samples.append(dict(i=i, km=round(d / 1000, 3), x=round(cx, 1), y=round(cy, 1), lon=round(lon, 6), lat=round(lat, 6)))

json.dump(dict(a=A, b=B, length_m=round(L, 1), step_m=STEP, half_width_m=HALF_W,
               u=[ux, uy], n=[nx, ny], samples=samples), open('transect.json', 'w'), indent=1)
print(f"{L/1000:.1f} km, {n} samples")
