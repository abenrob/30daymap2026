"""Skyline from the observer and the sanity table (replaces the table computed from the wrong point).

For each azimuth, march outwards through inner5 (to 2 km), mid25 (to 30 km), outer100 (to 130 km),
elevation angle = atan((h - drop(d) - (GROUND + EYE)) / d). The skyline is the running max.
Writes derived/skyline.csv (az, elev, dist of the skyline point) and prints the target table.
"""
import json
import numpy as np
from scipy.ndimage import map_coordinates
from pyproj import Geod, Transformer
from common import *

rings = []
for name, half, cell in RINGS:
    a = np.load(DERIVED / f"{name}.npy")
    rings.append((name, half, cell, a))


def sample(x, y):
    """Height at AEQD x, y from the finest ring that covers it."""
    h = np.full(x.shape, np.nan)
    for name, half, cell, a in rings:
        m = np.isnan(h) & (np.abs(x) < half - 2 * cell) & (np.abs(y) < half - 2 * cell)
        col = (x[m] + half) / cell - 0.5
        row = (half - y[m]) / cell - 0.5
        h[m] = map_coordinates(a, [row, col], order=1)
    return h


# distances: fine near the observer
d = np.concatenate([np.arange(1, 2000, 1.0), np.arange(2000, 30000, 10.0), np.arange(30000, 130000, 40.0)])
eye = GROUND + EYE
h0 = sample(np.array([0.0]), np.array([0.0]))[0]
print(f"ground under observer (bilinear) {h0:.2f} m, eye at {eye:.2f}")

az = np.arange(0, 360, 0.1)
sky = np.zeros_like(az); sky_d = np.zeros_like(az)
for i, a in enumerate(np.radians(az)):
    x, y = d * np.sin(a), d * np.cos(a)
    e = np.degrees(np.arctan2(sample(x, y) - drop(d) - eye, d))
    k = np.nanargmax(e); sky[i], sky_d[i] = e[k], d[k]
np.savetxt(DERIVED / "skyline.csv", np.c_[az, sky, sky_d], delimiter=",", header="az,elev_deg,dist_m", comments="", fmt="%.3f")
print(f"skyline elev range {sky.min():.2f} to {sky.max():.2f} deg")

geod = Geod(ellps="GRS80")
fwd = Transformer.from_crs(4326, AEQD, always_xy=True)
targets = {  # name: lon, lat, height (None = DEM max within search radius), search radius m
    # BD TOPO detail_orographique points where available; others approximate + DEM max search
    "Chamechaude (2,082 m)": (5.78808497, 45.28750573, None, 150),
    "Grand Som (2,026 m)": (5.81202818, 45.37034274, None, 150),
    "Dent de Crolles (2,062 m)": (5.85510227, 45.30809692, None, 150),
    "Croix de Belledonne (2,926 m)": (5.98812628, 45.16854142, None, 150),
    "Grand Pic de Belledonne (2,977 m)": (5.9915483, 45.17074022, None, 150),
    "Moucherotte (1,901 m)": (5.63946833, 45.14780574, None, 150),
    "Mont Blanc (4,806 m)": (6.86517, 45.83265, 4806, 0),
    "Grenoble centre (place Grenette)": (5.72710, 45.18990, 214, 0),
    "Saint-Égrève (mairie)": (5.6830, 45.2330, 220, 0),
    "Meylan (mairie)": (5.7780, 45.2100, 230, 0),
    "Saint-Martin-d'Hères (mairie)": (5.7640, 45.1670, 220, 0),
    "Échirolles (mairie)": (5.7230, 45.1440, 240, 0),
    "Voiron (centre)": (5.5900, 45.3640, 290, 0),
    "Chambéry (centre)": (5.9210, 45.5650, 270, 0),
    "Lyon (place Bellecour)": (4.83210, 45.75780, 170, 0),
}
print(f"\n| Target | Distance | Azimuth | Elevation | Skyline at that azimuth | Visible |")
print("| --- | --- | --- | --- | --- | --- |")
for n, (lo, la, h, rad) in targets.items():
    azi, _, dist = geod.inv(LON, LAT, lo, la); azi %= 360
    x, y = fwd.transform(lo, la)
    if h is None:  # local DEM max within 150 m (peak point uncertainty)
        g = np.linspace(-rad, rad, 2 * rad // 5 + 1); gx, gy = np.meshgrid(g, g)
        hh = sample(x + gx.ravel(), y + gy.ravel()); k = np.nanargmax(hh); h = float(hh[k])
        azi, _, dist = geod.inv(LON, LAT, *Transformer.from_crs(AEQD, 4326, always_xy=True).transform(x + gx.ravel()[k], y + gy.ravel()[k])); azi %= 360
        n += f' [DEM {h:.0f} m]'
    el = np.degrees(np.arctan2(h - drop(dist) - eye, dist))
    # skyline in front of the target only
    dd = d[d < dist - 200]; a = np.radians(azi)
    e = np.degrees(np.arctan2(sample(dd * np.sin(a), dd * np.cos(a)) - drop(dd) - eye, dd))
    front = float(np.nanmax(e))
    print(f"| {n} | {dist/1000:.1f} km | {azi:.0f}° | {el:+.1f}° | {front:+.1f}° (at {dd[np.nanargmax(e)]/1000:.2f} km) | {'yes' if el > front else 'no'} |")
