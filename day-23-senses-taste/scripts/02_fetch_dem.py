"""IGN RGE ALTI (ELEVATION.ELEVATIONGRIDCOVERAGE.HIGHRES) from the Géoplateforme WMS-R as float32 BIL, tiled 2000 px.

  python 02_fetch_dem.py Gigondas 856000 6338000 866500 6347000 5
  python 02_fetch_dem.py Saint-Joseph 832000 6424500 848000 6485000 5
  python 02_fetch_dem.py corridor 780000 6320000 910000 6530000 100   (slide 1 relief, resampled by the server)
"""
import sys,urllib.request,numpy as np,rasterio
from rasterio.transform import from_origin
name,minx,miny,maxx,maxy,res=sys.argv[1],*map(float,sys.argv[2:7])
W=int((maxx-minx)/res);H=int((maxy-miny)/res);T=2000
out=np.full((H,W),np.nan,np.float32)
for r0 in range(0,H,T):
  for c0 in range(0,W,T):
    w=min(T,W-c0);h=min(T,H-r0)
    x0=minx+c0*res;y1=maxy-r0*res;x1=x0+w*res;y0=y1-h*res
    u=("https://data.geopf.fr/wms-r/wms?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=ELEVATION.ELEVATIONGRIDCOVERAGE.HIGHRES"
       f"&STYLES=&CRS=EPSG:2154&BBOX={x0},{y0},{x1},{y1}&WIDTH={w}&HEIGHT={h}&FORMAT=image/x-bil;bits=32")
    b=urllib.request.urlopen(u,timeout=170).read()
    a=np.frombuffer(b,np.float32)
    if a.size!=w*h: print("bad",len(b),b[:200]);sys.exit(1)
    out[r0:r0+h,c0:c0+w]=a.reshape(h,w)
    print(r0,c0,flush=True)
out[out<-1000]=np.nan
with rasterio.open(f"dem_{name}.tif","w",driver="GTiff",width=W,height=H,count=1,dtype="float32",crs="EPSG:2154",transform=from_origin(minx,maxy,res,res),nodata=np.nan,compress="deflate") as d: d.write(out,1)
print(name,W,H,np.nanmin(out),np.nanmax(out))
