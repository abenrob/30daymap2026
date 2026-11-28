"""Fetch IGN RGE ALTI elevation (Géoplateforme WMS-R, BIL float32) for the Grenoble basin, Lambert-93, 40 m."""
import urllib.request, numpy as np, rasterio, sys
from rasterio.transform import from_origin
X0, Y0, X1, Y1, RES = 890000, 6428000, 946000, 6490000, 40
W, H = (X1-X0)//RES, (Y1-Y0)//RES
url = ("https://data.geopf.fr/wms-r?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=ELEVATION.ELEVATIONGRIDCOVERAGE.HIGHRES"
       f"&STYLES=&CRS=EPSG:2154&BBOX={X0},{Y0},{X1},{Y1}&WIDTH={W}&HEIGHT={H}&FORMAT=image/x-bil;bits=32")
raw = urllib.request.urlopen(url, timeout=120).read()
z = np.frombuffer(raw, dtype='<f4').reshape(H, W).copy()
z[z < -100] = np.nan
print(W, H, np.nanmin(z), np.nanmax(z), np.isnan(z).sum())
with rasterio.open(sys.argv[1], 'w', driver='GTiff', width=W, height=H, count=1, dtype='float32', crs='EPSG:2154',
                   transform=from_origin(X0, Y1, RES, RES), compress='deflate') as d:
    d.write(z, 1)
