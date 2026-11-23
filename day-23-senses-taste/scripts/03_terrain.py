"""Slope, aspect and altitude on the 5 m DEM, for planted vines vs the allowed-but-unplanted rest of the aire parcellaire.

  python 03_terrain.py  ->  terrain_stats.json, slope_*.tif, aspect_*.tif, mask_*.npy
Vines = (BD TOPO Vigne ∪ RPG 2023 vines) ∩ aire parcellaire. Aspect = direction the slope faces (0 = N, 90 = E); rose and mean aspect use slopes >= 3°.
"""
import numpy as np, rasterio, geopandas as gpd, pandas as pd, json
from rasterio.features import rasterize
res={}
for n in ["Saint-Joseph","Gigondas"]:
    src=rasterio.open(f"dem_{n}.tif"); z=src.read(1); tr=src.transform; px=tr.a
    gy,gx=np.gradient(z,px)            # rows go south: gy = dz/d(row) ; north component = -gy
    dzdx=gx; dzdn=-gy
    slope=np.degrees(np.arctan(np.hypot(dzdx,dzdn)))
    aspect=(np.degrees(np.arctan2(-dzdx,-dzdn))+360)%360   # direction downslope faces: 0=N,90=E
    A=gpd.read_file(f"ap_{n}.geojson").set_crs(2154,allow_override=True).union_all()
    V=pd.concat([gpd.read_file(f"topo_{n}.geojson"),gpd.read_file(f"rpg_{n}.geojson")]).set_crs(2154,allow_override=True).union_all().buffer(0)&A
    mA=rasterize([A],z.shape,transform=tr).astype(bool); mV=rasterize([V],z.shape,transform=tr).astype(bool)
    np.save(f"mask_{n}.npy",np.stack([mA,mV])); 
    with rasterio.open(f"slope_{n}.tif","w",**src.profile) as d: d.write(slope.astype("float32"),1)
    with rasterio.open(f"aspect_{n}.tif","w",**src.profile) as d: d.write(aspect.astype("float32"),1)
    out={}
    for lab,m in [("planted",mV),("allowed_empty",mA&~mV)]:
        m=m&np.isfinite(z)
        zz,ss,aa=z[m],slope[m],aspect[m]
        steep=ss>=3
        sect=((aa[steep]+22.5)//45%8).astype(int)
        rose=np.bincount(sect,minlength=8)/m.sum()
        mean_dir=(np.degrees(np.arctan2(np.sin(np.radians(aa[steep])).mean(),np.cos(np.radians(aa[steep])).mean()))+360)%360
        out[lab]=dict(ha=round(m.sum()*px*px/1e4),alt_p10=round(float(np.percentile(zz,10))),alt_med=round(float(np.median(zz))),alt_p90=round(float(np.percentile(zz,90))),
            slope_med=round(float(np.median(ss)),1),slope_mean=round(float(ss.mean()),1),share_ge15=round(float((ss>=15).mean()*100),1),share_ge30=round(float((ss>=30).mean()*100),1),
            flat_share=round(float((~steep).mean()*100),1),mean_aspect=round(float(mean_dir)),
            rose={k:round(float(v)*100,1) for k,v in zip("N NE E SE S SW W NW".split(),rose)},
            sunward=round(float(((aa>=90)&(aa<=270)&steep).mean()*100),1))
    res[n]=out
    print(n,json.dumps(out,indent=1))
json.dump(res,open("terrain_stats.json","w"),indent=1)
