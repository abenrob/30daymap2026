"""Wider, coarser DEM (about 150 m) for the movement model, so animals can leave the map frame."""
import numpy as np, urllib.request
la0, la1, lo0, lo1 = 44.80, 45.80, 5.05, 6.70
W, H = 880, 740
url = ("https://data.geopf.fr/wms-r?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=ELEVATION.ELEVATIONGRIDCOVERAGE"
       f"&STYLES=&CRS=EPSG:4326&BBOX={la0},{lo0},{la1},{lo1}&WIDTH={W}&HEIGHT={H}&FORMAT=image/x-bil;bits=32")
a = np.frombuffer(urllib.request.urlopen(url, timeout=200).read(), dtype="<f4").reshape(H, W)
np.save("dem_sim.npy", a)
print(a.min(), a.max())
