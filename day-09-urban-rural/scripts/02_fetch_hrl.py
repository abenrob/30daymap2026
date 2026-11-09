"""Copernicus HRL Imperviousness Density 2018 (10 m) for the transect, from the EEA ImageServer.

The server reprojects to Lambert-93 and returns raw values (0 to 100 % sealed), so no account
or bulk download is needed. Requests are capped at 4,100 px high, hence the strips.
Writes raw/hrl_imd_2018_l93.tif.
"""
import json, urllib.parse, urllib.request, numpy as np, rasterio
from rasterio.merge import merge

T = json.load(open('transect.json'))
xs = [s['x'] for s in T['samples']]; ys = [s['y'] for s in T['samples']]

# bounding box of the line plus 3 km, snapped to the 10 m grid
pad = 3000
x0, x1 = int(min(xs) - pad) // 10 * 10, int(max(xs) + pad) // 10 * 10 + 10
y0, y1 = int(min(ys) - pad) // 10 * 10, int(max(ys) + pad) // 10 * 10 + 10

SVC = "https://image.discomap.eea.europa.eu/arcgis/rest/services/GioLandPublic/HRL_ImperviousnessDensity_2018/ImageServer/exportImage"
STRIP = 4000 * 10   # 4,000 rows of 10 m per request
parts = []
for k, ys0 in enumerate(range(y0, y1, STRIP)):
    ys1 = min(ys0 + STRIP, y1)
    q = dict(bbox=f"{x0},{ys0},{x1},{ys1}", bboxSR=2154, imageSR=2154,
             size=f"{(x1-x0)//10},{(ys1-ys0)//10}", format="tiff", pixelType="U8",
             interpolation="RSP_NearestNeighbor", noData="", f="image")
    fn = f"raw/hrl_{k}.tif"
    urllib.request.urlretrieve(SVC + "?" + urllib.parse.urlencode(q), fn)
    parts.append(fn); print(fn)

srcs = [rasterio.open(p) for p in parts]
mosaic, tr = merge(srcs)
prof = srcs[0].profile; prof.update(height=mosaic.shape[1], width=mosaic.shape[2], transform=tr, compress='deflate')
with rasterio.open('raw/hrl_imd_2018_l93.tif', 'w', **prof) as d: d.write(mosaic)
v = mosaic[0]; print(prof['crs'], mosaic.shape, 'values', np.unique(v)[:5], '...', np.unique(v)[-5:])
