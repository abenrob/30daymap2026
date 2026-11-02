"""Mosaic the GLO-30 tiles and reproject to Lambert-93 (EPSG:2154), in windows.

Writes to work/data/day-02-lines/derived/:
  dem_30m_l93.tif   30 m, for baking normals/hillshade and any close-up shot (~800 MB)
  dem_150m_l93.tif  150 m, for the Blender terrain mesh (2,822 x 3,876 vertices)
  _glo30_mosaic.vrt the source tiles as one virtual raster (kept, a few KB)
Extent: the basin bbox plus a 0.15 degree margin, so the frame has context outside the basin.
Memory stays under ~1 GB: the tiles are mosaicked as a VRT and both outputs are warped block by block.

Run from the workspace root after 03_download_dem.sh and 02_trace_rhone.py.
"""
import glob, os
import duckdb
import numpy as np
import rasterio
from rasterio.vrt import WarpedVRT
from rasterio.warp import Resampling, transform_bounds
from rasterio.transform import from_origin
from rasterio.windows import Window

RAW = "work/data/day-02-lines/raw/glo30"
OUT = "work/data/day-02-lines/derived"
TMP = f"{OUT}/_glo30_mosaic.vrt"
DST = "EPSG:2154"
MARGIN = 0.15
BLOCK = 2048
NODATA = -9999

c = duckdb.connect()
c.sql("INSTALL spatial; LOAD spatial;")
b = c.execute(f"SELECT ST_Extent(geometry) FROM '{OUT}/basin.parquet'").fetchone()[0]
lon0, lat0, lon1, lat1 = b["min_x"] - MARGIN, b["min_y"] - MARGIN, b["max_x"] + MARGIN, b["max_y"] + MARGIN

# Mosaic as a GDAL VRT (no pixels copied). Every GLO-30 tile between 0 and 50 N
# is 3600 x 3600 px on a 1 arc-second grid, so tiles sit on one regular grid.
tiles = sorted(glob.glob(f"{RAW}/*.tif"))
lats = [int(os.path.basename(f).split("_N")[1][:2]) for f in tiles]
lons = [int(os.path.basename(f).split("_E")[1][:3]) for f in tiles]
west, north = min(lons), max(lats) + 1
with rasterio.open(tiles[0]) as t0:  # origin offset taken from a real tile
    px, n = t0.res[0], t0.width
    ox = t0.transform.c - (lons[0] - west)
    oy = t0.transform.f + (north - 1 - lats[0])
W, H = (max(lons) - west + 1) * n, (north - min(lats)) * n
srcs_xml = "".join(
    f'''<ComplexSource><SourceFilename relativeToVRT="0">{os.path.abspath(f)}</SourceFilename>
<SourceBand>1</SourceBand><SrcRect xOff="0" yOff="0" xSize="{n}" ySize="{n}"/>
<DstRect xOff="{(lo - west) * n}" yOff="{(north - la - 1) * n}" xSize="{n}" ySize="{n}"/></ComplexSource>'''
    for f, la, lo in zip(tiles, lats, lons))
open(TMP, "w").write(f'''<VRTDataset rasterXSize="{W}" rasterYSize="{H}">
<SRS>EPSG:4326</SRS><GeoTransform>{ox}, {px}, 0, {oy}, 0, {-px}</GeoTransform>
<VRTRasterBand dataType="Float32" band="1"><NoDataValue>{NODATA}</NoDataValue>{srcs_xml}</VRTRasterBand>
</VRTDataset>''')

xmin, ymin, xmax, ymax = transform_bounds("EPSG:4326", DST, lon0, lat0, lon1, lat1)

def warp(src_path, res, path, resampling):
    w, h = int(np.ceil((xmax - xmin) / res)), int(np.ceil((ymax - ymin) / res))
    t = from_origin(xmin, ymax, res, res)
    prof = dict(driver="GTiff", width=w, height=h, count=1, dtype="float32", crs=DST,
                transform=t, nodata=NODATA, compress="deflate", predictor=3,
                tiled=True, blockxsize=512, blockysize=512, BIGTIFF="IF_SAFER")
    zmin, zmax = np.inf, -np.inf
    with rasterio.open(src_path) as src, \
         WarpedVRT(src, crs=DST, transform=t, width=w, height=h, nodata=NODATA,
                   resampling=resampling) as vrt, \
         rasterio.open(path, "w", **prof) as dst:
        for row in range(0, h, BLOCK):
            for col in range(0, w, BLOCK):
                win = Window(col, row, min(BLOCK, w - col), min(BLOCK, h - row))
                a = vrt.read(1, window=win).astype("float32")
                dst.write(a, 1, window=win)
                v = a[a != NODATA]
                if v.size:
                    zmin, zmax = min(zmin, v.min()), max(zmax, v.max())
        dst.build_overviews([2, 4, 8, 16], Resampling.average)
    print(f"{path}: {w} x {h}, z {zmin:.0f} to {zmax:.0f} m")

warp(TMP, 30, f"{OUT}/dem_30m_l93.tif", Resampling.bilinear)
warp(f"{OUT}/dem_30m_l93.tif", 150, f"{OUT}/dem_150m_l93.tif", Resampling.average)
