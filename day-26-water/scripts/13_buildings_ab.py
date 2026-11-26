"""BD TOPO buildings, only in 5 km tiles that contain water seen on >=2 flood passes."""
import io, numpy as np, pandas as pd, xarray as xr, geopandas as gpd, requests, time
ds=xr.open_dataset("cube_ab.nc"); t=pd.to_datetime(ds.t.values)
sel=(t>="2026-02-08")&(t<="2026-03-01")
n=(ds.water.values[sel]==1).sum(0)
X=ds.x.values; Y=ds.y.values
tiles=set()
for i,j in zip(*np.where(n>=2)): tiles.add((int(X[j]//5000),int(Y[i]//5000)))
print(len(tiles),"tiles",flush=True)
parts=[]
for k,(tx,ty) in enumerate(sorted(tiles)):
    x0,y0=tx*5000,ty*5000; start=0
    while True:
        for a in range(5):
            try:
                r=requests.get("https://data.geopf.fr/wfs/ows",timeout=300,params=dict(SERVICE="WFS",VERSION="2.0.0",REQUEST="GetFeature",
                  TYPENAMES="BDTOPO_V3:batiment",SRSNAME="EPSG:2154",BBOX=f"{x0},{y0},{x0+5000},{y0+5000},urn:ogc:def:crs:EPSG::2154",
                  OUTPUTFORMAT="application/json",COUNT=5000,STARTINDEX=start,PROPERTYNAME="cleabs,usage_1,nombre_de_logements,geometrie")); r.raise_for_status(); break
            except Exception as e: print("retry",tx,ty,e,flush=True); time.sleep(10)
        g=gpd.read_file(io.BytesIO(r.content))
        if len(g): parts.append(g)
        start+=len(g)
        if len(g)<5000: break
    if k%10==0: print(k,len(tiles),sum(map(len,parts)),flush=True)
b=pd.concat(parts).drop_duplicates("cleabs").set_crs(2154,allow_override=True)
b.to_file("buildings_ab.gpkg"); print("buildings",len(b))
