"""Crop the EOG annual VNL V2 (2025, average_masked) to the 130 km window, without unzipping 11.6 GB.

Source: Earth Observation Group, Payne Institute, Colorado School of Mines. Annual VNL V2, 2025,
VNL_npp_2025_global_vcmslcfg_v2_c202604011200.average_masked.dat.tif.gz (15 arc-second, nW/cm2/sr), public domain.
Read through GDAL's /vsigzip/ (sequential decode down to ~46.5 N only).
Output: raw/vnl_2025_crop.tif (EPSG:4326, same grid as the source) and derived/lights100.npy on the outer100 AEQD grid.
"""
import sys, json
import numpy as np, rasterio
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds, reproject, Resampling
from rasterio.crs import CRS
from rasterio.transform import from_origin
from common import *

SRC = sys.argv[1] if len(sys.argv) > 1 else str(RAW / "VNL_npp_2025_global_vcmslcfg_v2_c202604011200.average_masked.dat.tif.gz")
name, half, cell = RINGS[2]
l, b, r, t = transform_bounds(CRS.from_proj4(AEQD), "EPSG:4326", -half, -half, half, half, densify_pts=50)
l, b, r, t = l - 0.05, b - 0.05, r + 0.05, t + 0.05
crop = RAW / "vnl_2025_crop.tif"
with rasterio.open("/vsigzip/" + SRC) as s:
    w = from_bounds(l, b, r, t, s.transform).round_offsets().round_lengths()
    a = s.read(1, window=w)
    prof = s.profile | dict(width=a.shape[1], height=a.shape[0], transform=s.window_transform(w), compress="deflate", tiled=True, blockxsize=256, blockysize=256, driver="GTiff")
    print("source", s.width, s.height, s.dtypes, s.nodata, "window", w)
tmp = Path("/tmp/vnl_2025_crop.tif")  # the Mac folder refuses deletes: write elsewhere, then copy bytes over
with rasterio.open(tmp, "w", **prof) as d:
    d.write(a, 1)
open(crop, "wb").write(tmp.read_bytes())
print("crop", a.shape, float(np.nanmin(a)), float(np.nanmax(a)))
n = int(2 * half / cell)
dst = np.zeros((n, n), np.float32)
with rasterio.open(crop) as s:
    reproject(rasterio.band(s, 1), dst, dst_transform=from_origin(-half, half, cell, cell), dst_crs=CRS.from_proj4(AEQD),
              resampling=Resampling.average)
np.save(DERIVED / "lights100.npy", dst)
json.dump(dict(source="EOG VNL V2 2025 average_masked", units="nW/cm2/sr", grid=name, cell=cell), open(DERIVED / "lights100.json", "w"))
print("lights100", dst.shape, float(dst.max()), "sum", float(dst.sum()))
