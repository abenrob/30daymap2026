"""Build three DEM rings on one azimuthal-equidistant grid centred on the summit.

inner5   : RGE ALTI 5 m, +-2 km      (IGN Geoplateforme WMS-R, float32 x-bil)
mid25    : RGE ALTI 25 m, +-30 km    (same, fetched in 1,000 px tiles)
outer100 : Copernicus GLO-30 -> 100 m, +-130 km (tiles already downloaded for day 2)

Output: derived/<ring>.npy (float32, row 0 = north) + derived/<ring>.json (grid transform).
"""
import json, sys
import numpy as np, requests, rasterio
from rasterio.transform import from_origin
from rasterio.warp import reproject, Resampling, transform_bounds
from rasterio.crs import CRS
from common import *

AEQD_CRS = CRS.from_proj4(AEQD)


def grid(half, cell):
    n = int(2 * half / cell)
    return n, from_origin(-half, half, cell, cell)


def wmsr(bbox, w, h):
    p = dict(SERVICE="WMS", VERSION="1.3.0", REQUEST="GetMap", LAYERS=RGEALTI_LAYER, STYLES="",
             CRS="EPSG:2154", BBOX=",".join(f"{v:.2f}" for v in bbox), WIDTH=w, HEIGHT=h,
             FORMAT="image/x-bil;bits=32")
    r = requests.get(WMSR, params=p, timeout=180)
    r.raise_for_status()
    a = np.frombuffer(r.content, dtype="<f4").reshape(h, w).copy()
    a[a < -1000] = np.nan
    return a


def rgealti_ring(half, cell, src_cell, tile=1000):
    n, dst_tr = grid(half, cell)
    dst = np.full((n, n), np.nan, np.float32)
    # source window in Lambert-93 covering the AEQD square, with margin
    l, b, r, t = transform_bounds(AEQD_CRS, "EPSG:2154", -half, -half, half, half, densify_pts=50)
    l, b, r, t = (np.floor(l / src_cell) * src_cell - 4 * src_cell, np.floor(b / src_cell) * src_cell - 4 * src_cell,
                  np.ceil(r / src_cell) * src_cell + 4 * src_cell, np.ceil(t / src_cell) * src_cell + 4 * src_cell)
    W, H = int((r - l) / src_cell), int((t - b) / src_cell)
    src = np.full((H, W), np.nan, np.float32)
    for i0 in range(0, H, tile):
        for j0 in range(0, W, tile):
            h, w = min(tile, H - i0), min(tile, W - j0)
            bb = (l + j0 * src_cell, t - (i0 + h) * src_cell, l + (j0 + w) * src_cell, t - i0 * src_cell)
            src[i0:i0 + h, j0:j0 + w] = wmsr(bb, w, h)
            print(f"  tile {i0},{j0} ok", flush=True)
    reproject(src, dst, src_transform=from_origin(l, t, src_cell, src_cell), src_crs="EPSG:2154",
              src_nodata=np.nan, dst_transform=dst_tr, dst_crs=AEQD_CRS, dst_nodata=np.nan,
              resampling=Resampling.bilinear if cell <= src_cell else Resampling.average)
    return dst, dst_tr


def glo30_ring(half, cell):
    n, dst_tr = grid(half, cell)
    dst = np.full((n, n), np.nan, np.float32)
    l, b, r, t = transform_bounds(AEQD_CRS, "EPSG:4326", -half, -half, half, half, densify_pts=50)
    for lat in range(int(np.floor(b)), int(np.floor(t)) + 1):
        for lon in range(int(np.floor(l)), int(np.floor(r)) + 1):
            f = GLO30_DIR / f"Copernicus_DSM_COG_10_N{lat:02d}_00_E{lon:03d}_00_DEM.tif"
            if not f.exists():
                print("  missing", f.name); continue
            with rasterio.open(f) as s:
                tmp = np.full_like(dst, np.nan)
                reproject(rasterio.band(s, 1), tmp, dst_transform=dst_tr, dst_crs=AEQD_CRS,
                          dst_nodata=np.nan, resampling=Resampling.average)
            m = np.isnan(dst) & ~np.isnan(tmp)
            dst[m] = tmp[m]
            print("  ", f.name, int(m.sum()), flush=True)
    return dst, dst_tr


def save(name, a, tr, cell, source):
    np.save(DERIVED / f"{name}.npy", a.astype(np.float32))
    json.dump(dict(transform=list(tr)[:6], cell=cell, crs=AEQD, source=source,
                   nan=int(np.isnan(a).sum()), min=float(np.nanmin(a)), max=float(np.nanmax(a))),
              open(DERIVED / f"{name}.json", "w"), indent=1)
    print(name, a.shape, float(np.nanmin(a)), float(np.nanmax(a)), "nan", int(np.isnan(a).sum()))


if __name__ == "__main__":
    which = sys.argv[1:] or [r[0] for r in RINGS]
    for name, half, cell in RINGS:
        if name not in which:
            continue
        print(name, flush=True)
        if name == "outer100":
            a, tr = glo30_ring(half, cell); src = "Copernicus GLO-30"
        else:
            a, tr = rgealti_ring(half, cell, src_cell=cell); src = f"RGE ALTI via WMS-R {RGEALTI_LAYER}"
        save(name, a, tr, cell, src)
