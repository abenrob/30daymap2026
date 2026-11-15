#!/usr/bin/env python3
"""
Step 1: fetch a seamless land + seafloor DEM, plus a data-quality mask, as metric GeoTIFFs.

Source: GMRT GridServer (https://www.gmrt.org/services/GridServer/info).
  layer=topo       land (USGS NED 10 m where available) + ocean: curated multibeam (~100 m)
                   where it exists, coarse GEBCO fill everywhere else.
  layer=topo-mask  only the high-resolution ocean cells, NaN elsewhere.  This is how we know
                   which parts of the seafloor are real survey data and which are gap-fill.

Both are warped to UTM at the working resolution (area-averaged) and written to data/.

Usage (from the project folder):
    python 01_fetch_dem.py                          # default scout area around Monterey Bay
    python 01_fetch_dem.py --bbox -123 35.95 -120.9 37.1 --res 100
    python 01_fetch_dem.py --detail my_cudem_tile.tif other.tif    # overlay higher-res tiles (close-ups)
    python 01_fetch_dem.py --local a.tif b.tif --no-mask           # skip GMRT, use your own DEMs

Outputs:
    data/dem_utm.tif       float32 metres, NaN = nodata
    data/surveyed_utm.tif  float32 0..1, fraction of each cell that is high-res multibeam (ocean only)
"""
import argparse
import math
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform

# W, S, E, N.  "Scout" area: deliberately wider than we expect to keep. 02_prepare.py
# trims it to where the seafloor data is good (--auto-crop).
DEFAULT_BBOX = (-123.0, 35.95, -120.9, 37.1)
GMRT_URL = os.environ.get("GMRT_URL", "https://www.gmrt.org/services/GridServer")


def fetch_gmrt(bbox, layer, res_m, dest):
    w, s, e, n = bbox
    q = {"north": round(n, 5), "south": round(s, 5), "east": round(e, 5), "west": round(w, 5), "layer": layer, "format": "geotiff", "mresolution": res_m}
    url = f"{GMRT_URL}?{urllib.parse.urlencode(q)}"
    print(f"  GET {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "inverted-terrain/2.0"})
    tmp = dest.with_suffix(".part")
    try:
        with urllib.request.urlopen(req, timeout=180) as r, open(tmp, "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
    except urllib.error.HTTPError as ex:
        body = ex.read()[:300].decode("utf8", "replace")
        sys.exit(f"GMRT returned HTTP {ex.code}: {body}\nTry a smaller --bbox or a coarser --res.")
    except (urllib.error.URLError, OSError) as ex:
        sys.exit(f"Could not reach GMRT ({ex}).\nIf you are offline/behind a proxy, download the same two GeoTIFFs "
                 f"from the GMRT MapTool and pass them with --local / --mask-file.")
    tmp.rename(dest)
    # GMRT reports problems as small text/JSON bodies with HTTP 200 in some cases
    if dest.stat().st_size < 2000:
        sys.exit(f"Unexpected tiny response for layer={layer}: {dest.read_bytes()[:300]!r}")
    return dest


def warp_into(path, dst, dst_transform, dst_crs, resampling, as_mask=False):
    """Reproject one raster into dst-shaped float32 array (NaN where no data). Returns the array."""
    out = np.full(dst.shape, np.nan, dtype=np.float32)
    with rasterio.open(path) as src:
        crs = src.crs or CRS.from_epsg(4326)
        a = src.read(1).astype(np.float32)
        if as_mask:
            a = np.isfinite(a).astype(np.float32)  # NaN = not surveyed
            nodata = None
        else:
            nodata = src.nodata
            a[np.abs(a) > 12000] = np.nan  # fill values / garbage
            if nodata is not None and not np.isnan(nodata):
                a[a == nodata] = np.nan
        reproject(
            source=a, destination=out, src_transform=src.transform, src_crs=crs,
            dst_transform=dst_transform, dst_crs=dst_crs, src_nodata=np.nan,
            dst_nodata=np.nan, resampling=resampling,
        )
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bbox", nargs=4, type=float, metavar=("W", "S", "E", "N"), default=DEFAULT_BBOX)
    ap.add_argument("--res", type=float, default=100.0, help="output cell size in metres (GMRT multibeam is ~100 m)")
    ap.add_argument("--crs", default="EPSG:26910", help="projected CRS in metres (default NAD83 / UTM 10N)")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--local", nargs="+", metavar="TIF", help="use these DEMs as the base instead of GMRT")
    ap.add_argument("--no-mask", action="store_true", help="do not fetch the quality mask (everything counts as good)")
    ap.add_argument("--mask-file", metavar="TIF", help="use this topo-mask GeoTIFF instead of fetching one")
    ap.add_argument("--detail", nargs="+", metavar="TIF",
                    help="higher-res DEM tiles (e.g. NOAA CUDEM 1/9 arc-second, USGS CSMP) overlaid on the base. "
                         "Beware vertical-datum offsets at the seam; best for small close-up bboxes.")
    args = ap.parse_args()

    data = Path(args.data_dir)
    raw = data / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    dst_crs = CRS.from_string(args.crs)
    w, s, e, n = args.bbox
    res = args.res

    # Largest projected rectangle INSIDE the lon/lat bbox (edges sampled densely: parallels bow in UTM).
    k = np.linspace(0, 1, 50)
    lon_k, lat_k = w + (e - w) * k, s + (n - s) * k
    xw, _ = transform("EPSG:4326", dst_crs, np.full(50, w), lat_k)
    xe, _ = transform("EPSG:4326", dst_crs, np.full(50, e), lat_k)
    _, ys_ = transform("EPSG:4326", dst_crs, lon_k, np.full(50, s))
    _, yn = transform("EPSG:4326", dst_crs, lon_k, np.full(50, n))
    l, r = math.ceil(max(xw) / res) * res, math.floor(min(xe) / res) * res
    b, t = math.ceil(max(ys_) / res) * res, math.floor(min(yn) / res) * res
    width, height = int(round((r - l) / res)), int(round((t - b) / res))
    dst_transform = from_origin(l, t, res, res)
    print(f"Output grid: {width} x {height} cells at {res:g} m  ({width * res / 1000:.0f} x {height * res / 1000:.0f} km)")

    # Slightly pad the request so edge cells are fully covered after reprojection.
    pad = 0.02
    req_bbox = (w - pad, s - pad, e + pad, n + pad)

    dem = np.full((height, width), np.nan, dtype=np.float32)
    if args.local:
        for p in args.local:
            print(f"Warping {p} ...")
            tmp = warp_into(p, dem, dst_transform, dst_crs, Resampling.average)
            dem = np.where(np.isnan(tmp), dem, tmp)
    else:
        print("Fetching GMRT topography (land + seafloor) ...")
        topo = fetch_gmrt(req_bbox, "topo", res, raw / "gmrt_topo.tif")
        dem = warp_into(topo, dem, dst_transform, dst_crs, Resampling.average)

    surveyed = np.zeros((height, width), dtype=np.float32)
    if args.mask_file or (not args.local and not args.no_mask):
        if args.mask_file:
            mask_path = Path(args.mask_file)
        else:
            print("Fetching GMRT multibeam mask ...")
            mask_path = fetch_gmrt(req_bbox, "topo-mask", res, raw / "gmrt_mask.tif")
        surveyed = warp_into(mask_path, surveyed, dst_transform, dst_crs, Resampling.average, as_mask=True)
        surveyed = np.nan_to_num(surveyed, nan=0.0)
        print(f"Multibeam-covered share of ocean cells: {surveyed[dem < 0].mean():.0%}")
    else:
        surveyed[:] = 1.0  # unknown -> assume good

    for p in args.detail or []:
        print(f"Overlaying detail {p} ...")
        tmp = warp_into(p, dem, dst_transform, dst_crs, Resampling.average)
        have = ~np.isnan(tmp)
        dem = np.where(have, tmp, dem)
        surveyed = np.where(have, 1.0, surveyed)  # detail tiles are survey-grade by definition

    nan_frac = float(np.isnan(dem).mean())
    print(f"Elevation range: {np.nanmin(dem):.0f} to {np.nanmax(dem):.0f} m   NaN: {nan_frac:.2%}")

    prof = dict(driver="GTiff", height=height, width=width, count=1, dtype="float32", crs=dst_crs,
                transform=dst_transform, nodata=np.nan, compress="deflate", tiled=True)
    with rasterio.open(data / "dem_utm.tif", "w", **prof) as ds:
        ds.write(dem, 1)
    with rasterio.open(data / "surveyed_utm.tif", "w", **prof) as ds:
        ds.write(surveyed, 1)
    print(f"Wrote {data / 'dem_utm.tif'} and {data / 'surveyed_utm.tif'}")


if __name__ == "__main__":
    main()
