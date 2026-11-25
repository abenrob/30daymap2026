"""Star and planet positions for the frame window, plus the sky checks from the README.

Catalogue: Yale Bright Star Catalogue 5th rev. ed. (V/50), JSON mirror github.com/brettonw/YaleBrightStarCatalog.
Ephemeris: JPL DE421 (bundled by the skyfield-data package). Refraction: skyfield's altaz(temperature, pressure)
(Bennett formula) for 10 C and 813 hPa (standard atmosphere at 1,864 m).
"""
import json, re
import numpy as np
from skyfield.api import Star, wgs84, load
from skyfield_data import get_skyfield_data_path
from common import *

TEMP_C, PRESS_HPA = 10.0, 813.0
T0_UTC = (2026, 8, 12, 21, 0)      # 23:00 CEST
T1_UTC = (2026, 8, 12, 22, 0)      # 00:00 CEST

ts = load.timescale(builtin=True)
eph = load(str(Path(get_skyfield_data_path()) / "de421.bsp"))
earth = eph["earth"]
site = earth + wgs84.latlon(LAT, LON, elevation_m=GROUND + EYE)


def load_bsc5():
    cache = DERIVED / "bsc5.npz"
    if cache.exists():
        return dict(np.load(cache, allow_pickle=True))
    raw = json.load(open(RAW / "bsc5.json"))
    rows = []
    for s in raw:
        if "RA" not in s or "Vmag" not in s:
            continue  # novae / non-stellar entries without positions
        h, m, sec = map(float, re.findall(r"[\d.]+", s["RA"]))
        sign = -1 if s["Dec"].strip().startswith("-") else 1
        d, dm, ds = map(float, re.findall(r"[\d.]+", s["Dec"]))
        bv = float(s["B-V"]) if s.get("B-V", "").strip() else 0.6
        rows.append((int(s["HR"]), h + m / 60 + sec / 3600, sign * (d + dm / 60 + ds / 3600), float(s["Vmag"]), bv,
                     float(s.get("pmRA") or 0) * 1000, float(s.get("pmDE") or 0) * 1000, s.get("Name", "")))
    a = np.array(rows, dtype=object)
    out = dict(hr=a[:, 0].astype(int), ra_h=a[:, 1].astype(float), dec=a[:, 2].astype(float), vmag=a[:, 3].astype(float),
               bv=a[:, 4].astype(float), pmra_mas=a[:, 5].astype(float), pmdec_mas=a[:, 6].astype(float), name=a[:, 7].astype(str))
    np.savez(cache, **out)
    return out


CAT = load_bsc5()
STARS = Star(ra_hours=CAT["ra_h"], dec_degrees=CAT["dec"], ra_mas_per_year=CAT["pmra_mas"], dec_mas_per_year=CAT["pmdec_mas"])


def altaz(target, t):
    alt, az, _ = site.at(t).observe(target).apparent().altaz(temperature_C=TEMP_C, pressure_mbar=PRESS_HPA)
    return alt.degrees, az.degrees


def stars_altaz(t):
    return altaz(STARS, t)


def radec_to_altaz_matrix(t):
    """3x3 rotation taking ICRS unit vectors to local (east, north, up) at time t, without refraction.
    Used for the Milky Way texture and the meteor radiant, where 0.05 deg does not matter."""
    from skyfield.api import Star as S
    basis = []
    for ra_h, dec in [(0, 0), (6, 0), (0, 90)]:
        alt, az = altaz_norefr(S(ra_hours=ra_h, dec_degrees=dec), t)
        a, z = np.radians(alt), np.radians(az)
        basis.append([np.cos(a) * np.sin(z), np.cos(a) * np.cos(z), np.sin(a)])
    return np.array(basis).T          # columns = images of x, y, z ICRS axes


def altaz_norefr(target, t):
    alt, az, _ = site.at(t).observe(target).apparent().altaz()
    return alt.degrees, az.degrees


def perseid_rate(radiant_alt_deg, lm, zhr=100, r=2.2):
    return zhr * np.sin(np.radians(radiant_alt_deg)) * r ** (lm - 6.5)
