"""Day 6 Vintage: read the volcanic core of the Massif Central from Copernicus GLO-30 COGs.

Only the window needed is read (HTTP range requests via /vsicurl), then warped
to Lambert-93 at a fixed resolution in a 4:5 portrait frame.

Usage: python 01_fetch_dem.py OUT.tif [--res 40]
"""
import argparse
import rasterio
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.merge import merge
from pyproj import Transformer

# Frame centre between Puy de Dome (north) and Plomb du Cantal (south)
CENTER_LONLAT = (2.80, 45.45)
HEIGHT_M = 118_000          # north-south extent
WIDTH_M = HEIGHT_M * 4 / 5  # 4:5 portrait

TILES = [f"Copernicus_DSM_COG_10_N{lat:02d}_00_E{lon:03d}_00_DEM"
         for lat in (44, 45) for lon in (2, 3)]
URL = "https://copernicus-dem-30m.s3.amazonaws.com/{t}/{t}.tif"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--res", type=float, default=40.0)
    a = ap.parse_args()

    to_l93 = Transformer.from_crs(4326, 2154, always_xy=True)
    cx, cy = to_l93.transform(*CENTER_LONLAT)
    left, top = cx - WIDTH_M / 2, cy + HEIGHT_M / 2
    w, h = int(round(WIDTH_M / a.res)), int(round(HEIGHT_M / a.res))
    dst_transform = from_origin(left, top, a.res, a.res)

    env = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif")
    with rasterio.Env(**env):
        srcs = [rasterio.open("/vsicurl/" + URL.format(t=t)) for t in TILES]
        # Mosaic in geographic coords (only the bounds we need, plus margin)
        to_ll = Transformer.from_crs(2154, 4326, always_xy=True)
        xs, ys = zip(*[to_ll.transform(x, y) for x in (left, left + WIDTH_M) for y in (top, top - HEIGHT_M)])
        bounds = (min(xs) - 0.02, min(ys) - 0.02, max(xs) + 0.02, max(ys) + 0.02)
        mosaic, mtrans = merge(srcs, bounds=bounds)
        profile = srcs[0].profile
        profile.update(height=mosaic.shape[1], width=mosaic.shape[2], transform=mtrans, driver="GTiff")
        tmp = a.out + ".ll.tif"
        with rasterio.open(tmp, "w", **profile) as d:
            d.write(mosaic)
    with rasterio.open(tmp) as src, WarpedVRT(src, crs="EPSG:2154", transform=dst_transform,
                                               width=w, height=h, resampling=Resampling.cubic) as vrt:
        data = vrt.read(1)
        prof = dict(driver="GTiff", dtype="float32", count=1, width=w, height=h,
                    crs="EPSG:2154", transform=dst_transform, compress="deflate", tiled=True)
        with rasterio.open(a.out, "w", **prof) as d:
            d.write(data.astype("float32"), 1)
    # Sidecars for Blender's Python, which has no GDAL
    import numpy as np
    np.save(a.out.replace(".tif", ".npy"), data.astype("float32"))
    open(a.out.replace(".tif", ".res"), "w").write(str(a.res))
    print(f"{a.out}: {w} x {h} px at {a.res} m, z {data.min():.0f} to {data.max():.0f} m")


if __name__ == "__main__":
    main()
