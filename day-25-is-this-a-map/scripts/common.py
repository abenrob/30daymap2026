"""Shared constants for day 25 (Charmant Som, Perseid night 2026)."""
import os
from pathlib import Path

WORK = Path(os.environ.get("D25_WORK", Path(__file__).resolve().parents[3] / "work" / "day-25-is-this-a-map"))
RAW, DERIVED, RENDERS = WORK / "raw", WORK / "derived", WORK / "renders"
for d in (RAW, DERIVED, RENDERS):
    d.mkdir(parents=True, exist_ok=True)

# Observer: highest 5 m RGE ALTI cell within 300 m of the BD TOPO 'Charmant Som' summit point
# (BD TOPO detail_orographique: 5.76414153 E, 45.32504623 N).
LON, LAT, GROUND = 5.764051, 45.325084, 1863.9
EYE = 0.3                      # lying down
R_EARTH = 6_371_000.0
K_REFR = 0.13                  # standard terrestrial refraction coefficient

# Local frame: azimuthal equidistant centred on the observer. Distance and true azimuth
# from the observer are exact; +y is true north at the observer.
AEQD = f"+proj=aeqd +lat_0={LAT} +lon_0={LON} +x_0=0 +y_0=0 +ellps=GRS80 +units=m +no_defs"

# DEM rings: (name, half-width m, cell m)
RINGS = [("inner5", 2_000, 5), ("mid25", 30_000, 25), ("outer100", 130_000, 100)]

WMSR = "https://data.geopf.fr/wms-r"
RGEALTI_LAYER = "ELEVATION.ELEVATIONGRIDCOVERAGE.HIGHRES"
GLO30_DIR = Path(__file__).resolve().parents[3] / "work" / "data" / "day-02-lines" / "raw" / "glo30"


def drop(d):
    """Apparent drop of terrain at distance d (m) from curvature with refraction."""
    return d * d / (2 * R_EARTH) * (1 - K_REFR)

# Sky brightness at the summit: lightpollutionmap.info, World Atlas 2015 layer (Falchi et al. 2016),
# read 25 Nov 2026 at 45.32518 N, 5.76461 E: SQM 20.97 mag/arcsec2 (natural + artificial),
# artificial 271 ucd/m2 = 1.58 x natural, Bortle 4.
SQM_ZENITH = 20.97
ARTIF_RATIO = 1.58
