"""Arrival time for each building: earliest water arrival within one 50 m pixel of its centroid."""
import numpy as np, geopandas as gpd
from scipy import ndimage
z=np.load("timing_ab.npz"); arr=z["arr"]
amin=ndimage.minimum_filter(np.where(np.isfinite(arr),arr,np.inf),size=3)
b=gpd.read_file("buildings_ab.gpkg"); c=b.geometry.centroid
col=np.round((c.x.values-403975)/50).astype(int); row=np.round((6434725-c.y.values)/50).astype(int)
ok=(row>=0)&(row<arr.shape[0])&(col>=0)&(col<arr.shape[1])
t=np.full(len(b),np.inf); t[ok]=amin[row[ok],col[ok]]
hit=np.isfinite(t)
np.savez_compressed("bld_first.npz",col=col[hit],row=row[hit],t=t[hit])
e=b[hit].copy(); e["arrival_day"]=t[hit]; e.to_file("buildings_exposed_ab.gpkg")
print("buildings within ~50 m of flood water:",hit.sum())
print(e.usage_1.value_counts().head(6).to_string()); print("dwellings:",int(e.nombre_de_logements.fillna(0).sum()))
