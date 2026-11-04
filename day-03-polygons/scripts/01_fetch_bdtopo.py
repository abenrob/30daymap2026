"""Day 3, step 1: download IGN BD TOPO buildings over Paris, plus the arrondissement outlines.

Source: IGN's Géoplateforme WFS (https://data.geopf.fr/wfs/ows), no key needed.
Writes: bdtopo/tiles/<lon>_<lat>.json (one GeoJSON per tile) and bdtopo/arr.json.
Run from a working folder outside the repo. Safe to re-run: tiles already on disk are skipped.
"""
import concurrent.futures as cf
import json
import os
import time
import urllib.parse
import urllib.request

WFS = "https://data.geopf.fr/wfs/ows?"

# Bounding box of Paris intra-muros (lon/lat). It also catches the inner suburbs;
# 02_prep.py keeps only buildings that fall inside an arrondissement.
x0, y0, x1, y1 = 2.224, 48.815, 2.470, 48.903

# Why tiles: the WFS returns at most 5,000 features per request. Paging with
# STARTINDEX works but needs a stable sort and is slow, so instead we cut the box
# into 0.01 degree tiles (about 0.7 x 1.1 km). The densest tile holds about 3,500
# buildings, comfortably under the limit. A building crossing a tile edge comes
# back in both tiles; 02_prep.py removes those duplicates by id (cleabs).
step = 0.01

# Only the attributes the page uses, to keep the downloads small.
props = ("cleabs,usage_1,usage_2,nature,hauteur,nombre_d_etages,nombre_de_logements,"
         "date_d_apparition,etat_de_l_objet,construction_legere,geometrie")

os.makedirs("bdtopo/tiles", exist_ok=True)

# South-west corner of every tile in the grid.
tiles = [(round(x0 + i * step, 4), round(y0 + j * step, 4))
         for i in range(int((x1 - x0) / step) + 1)
         for j in range(int((y1 - y0) / step) + 1)]


def get(t):
    """Download one tile. Returns (file, feature count), 0 if cached, -1 if it failed."""
    fn = f"bdtopo/tiles/{t[0]}_{t[1]}.json"
    if os.path.exists(fn):
        return fn, 0
    # WFS 2.0 with an EPSG:4326 URN expects the bbox as lat,lon (axis order), hence the swap.
    bb = f"{t[1]},{t[0]},{t[1] + step},{t[0] + step},urn:ogc:def:crs:EPSG::4326"
    q = dict(SERVICE="WFS", VERSION="2.0.0", REQUEST="GetFeature", TYPENAMES="BDTOPO_V3:batiment",
             OUTPUTFORMAT="application/json",
             SRSNAME="EPSG:2154",  # ask for Lambert-93 so areas and lengths come out in metres
             BBOX=bb, COUNT="5000", PROPERTYNAME=props)
    url = WFS + urllib.parse.urlencode(q)
    # The service occasionally times out under load; retry with a growing pause.
    for attempt in range(4):
        try:
            d = urllib.request.urlopen(url, timeout=120).read()
            n = len(json.loads(d)["features"])  # parse before saving, so a broken response is retried
            open(fn, "wb").write(d)
            return fn, n
        except Exception:
            time.sleep(2 + attempt * 3)
    return fn, -1


t = time.time()
# 8 parallel requests: about 5 minutes for the 225 tiles, without hammering the service.
with cf.ThreadPoolExecutor(8) as ex:
    res = list(ex.map(get, tiles))
print(len(tiles), "tiles,", sum(1 for r in res if r[1] < 0), "failed,",
      max(r[1] for r in res), "max per tile,", round(time.time() - t), "s")
# If any tile failed, run the script again: only the missing tiles are fetched.

# The 20 arrondissements from IGN ADMIN EXPRESS (75056 is the INSEE code of Paris).
q = dict(SERVICE="WFS", VERSION="2.0.0", REQUEST="GetFeature",
         TYPENAMES="ADMINEXPRESS-COG.LATEST:arrondissement_municipal",
         OUTPUTFORMAT="application/json", SRSNAME="EPSG:4326",
         CQL_FILTER="code_insee_de_la_commune_de_rattach='75056'")
open("bdtopo/arr.json", "wb").write(urllib.request.urlopen(WFS + urllib.parse.urlencode(q), timeout=120).read())
print("arrondissements saved")
