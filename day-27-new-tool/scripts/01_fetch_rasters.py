"""Fetch every input of the Aiguille Dibona scene into one folder (DIBONA_DATA).

IGN rasters come from the Géoplateforme WMS-R (https://data.geopf.fr/wms-r/wms), requested in
Lambert-93 (EPSG:2154) in tiles of at most 2,000 x 2,000 px and assembled into tiled GeoTIFFs:
    dem_2m_dibona.tif     LiDAR HD ground model (MNT), 2 m, 6.19-6.30 E 44.915-44.995 N  (whole scene)
    dem_1m_dibona.tif     LiDAR HD ground model (MNT), 1 m, 6.230-6.256 E 44.950-44.975 N (the needle)
    ortho_0.5m_dibona.tif IGN orthophoto, 0.5 m, 6.2265-6.2595 E 44.945-44.977 N           (opening shot)
Elevations come as raw little-endian float32 (FORMAT image/x-bil;bits=32), photos as PNG.
Licence: IGN, Licence Ouverte 2.0.

The title font is downloaded from the google/fonts repository and pinned to its Bold weight:
    Antonio-Bold.ttf      Antonio variable font instanced at wght 700 (SIL Open Font License)

usage:
    python3 01_fetch_rasters.py                       # everything above
    python3 01_fetch_rasters.py dem 2 6.19 44.915 6.30 44.995 _dibona   # one raster: kind res box tag
kinds: dem (LiDAR HD MNT), mnh (LiDAR HD canopy height), ortho (IGN orthophoto)
"""
import os, sys, urllib.parse, urllib.request
import numpy as np, rasterio
from rasterio.transform import from_origin
from pyproj import Transformer

OUT = os.environ.get("DIBONA_DATA", "/home/claude/d27/dibona")
os.makedirs(OUT, exist_ok=True)

LAYERS = {   # kind: (WMS-R layer, format, bands, dtype)
    "dem":   ("IGNF_LIDAR-HD_MNT_ELEVATION.ELEVATIONGRIDCOVERAGE.LAMB93", "image/x-bil;bits=32", 1, "float32"),
    "mnh":   ("IGNF_LIDAR-HD_MNH_ELEVATION.ELEVATIONGRIDCOVERAGE.LAMB93", "image/x-bil;bits=32", 1, "float32"),
    "ortho": ("ORTHOIMAGERY.ORTHOPHOTOS", "image/png", 3, "uint8"),
}

def fetch(kind, res, lon0, lat0, lon1, lat1, tag="", tile=2000):
    """Download one raster covering the lon/lat box at `res` metres per pixel, in Lambert-93."""
    layer, fmt, bands, dtype = LAYERS[kind]
    t = Transformer.from_crs(4326, 2154, always_xy=True)
    xs, ys = zip(*[t.transform(x, y) for x in (lon0, lon1) for y in (lat0, lat1)])
    # snap the Lambert-93 box outwards to 10 m so neighbouring rasters share a grid
    X0, Y0, X1, Y1 = (int(v // 10 * 10) for v in (min(xs), min(ys), max(xs) + 10, max(ys) + 10))
    W, H = round((X1 - X0) / res), round((Y1 - Y0) / res)
    path = f"{OUT}/{kind}_{res:g}m{tag}.tif"
    prof = dict(driver="GTiff", width=W, height=H, count=bands, dtype=dtype, crs="EPSG:2154",
                transform=from_origin(X0, Y1, res, res), tiled=True, compress="deflate",
                nodata=-99999 if dtype == "float32" else None, BIGTIFF="IF_SAFER")
    with rasterio.open(path, "w", **prof) as dst:
        for r0 in range(0, H, tile):
            for c0 in range(0, W, tile):
                w, h = min(tile, W - c0), min(tile, H - r0)
                bx0, by1 = X0 + c0 * res, Y1 - r0 * res          # top-left corner of this tile
                q = dict(SERVICE="WMS", VERSION="1.3.0", REQUEST="GetMap", LAYERS=layer, STYLES="",
                         CRS="EPSG:2154", BBOX=f"{bx0},{by1 - h * res},{bx0 + w * res},{by1}",
                         WIDTH=w, HEIGHT=h, FORMAT=fmt)
                data = urllib.request.urlopen("https://data.geopf.fr/wms-r/wms?" + urllib.parse.urlencode(q), timeout=170).read()
                if dtype == "float32":
                    a = np.frombuffer(data, "<f4")
                    if a.size != w * h:   # the server answers errors as XML, not as an HTTP error
                        raise SystemExit(f"bad tile {r0},{c0}: {data[:300]}")
                    dst.write(a.reshape(h, w), 1, window=((r0, r0 + h), (c0, c0 + w)))
                else:
                    with rasterio.MemoryFile(data) as m, m.open() as src:
                        dst.write(src.read()[:3], window=((r0, r0 + h), (c0, c0 + w)))
                print(kind, "tile", r0, c0, flush=True)
    print("wrote", path, W, "x", H)

def fetch_font():
    """Antonio (OFL) from google/fonts, instanced at weight 700 so Blender gets a static Bold."""
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer
    src = f"{OUT}/Antonio-variable.ttf"
    urllib.request.urlretrieve("https://raw.githubusercontent.com/google/fonts/main/ofl/antonio/Antonio%5Bwght%5D.ttf", src)
    instancer.instantiateVariableFont(TTFont(src), {"wght": 700}).save(f"{OUT}/Antonio-Bold.ttf")
    print("wrote", f"{OUT}/Antonio-Bold.ttf")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        kind, res = sys.argv[1], float(sys.argv[2])
        fetch(kind, res, *map(float, sys.argv[3:7]), tag=sys.argv[7] if len(sys.argv) > 7 else "")
    else:
        fetch("dem", 2, 6.19, 44.915, 6.30, 44.995, "_dibona")
        fetch("dem", 1, 6.230, 44.950, 6.256, 44.975, "_dibona")
        fetch("ortho", 0.5, 6.2265, 44.9450, 6.2595, 44.9770, "_dibona")
        fetch_font()
