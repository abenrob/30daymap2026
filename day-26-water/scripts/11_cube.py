"""Agen-Bordeaux: mosaic every pass onto the 50 m Lambert-93 grid, per-orbit dry reference, water per date.
water = VV < DARK dB AND >= |DROP| dB darker than the same orbit's dry reference; permanent water kept apart."""
import glob, json, sys, numpy as np, pandas as pd, xarray as xr, rioxarray
from scipy import ndimage
SRC=sys.argv[1] if len(sys.argv)>1 else "/mnt/user-data/uploads/30days2026/work/day-26-water/agen-bordeaux"
DARK,DROP,MMU=-13.0,-5.0,4
dem=rioxarray.open_rasterio(f"{SRC}/dem_50m.tif").squeeze("band",drop=True)
X=dem.x.values; Y=dem.y.values; H,W=dem.shape
def place(f):
    d=xr.open_dataset(f); v=d.vv_db100.values.astype("float32"); v[v==-32768]=np.nan; v/=100
    i0=int(round((Y[0]-float(d.y[0]))/50)); j0=int(round((float(d.x[0])-X[0])/50))
    out=np.full((H,W),np.nan,"float32"); h,w=v.shape
    out[i0:i0+h,j0:j0+w]=v[:max(0,min(h,H-i0)),:max(0,min(w,W-j0))]
    return out,d.attrs
def smooth_db(db):
    lin=np.where(np.isfinite(db),10**(db/10),0); m=np.isfinite(db).astype("float32")
    s=ndimage.uniform_filter(lin,3); n=ndimage.uniform_filter(m,3)
    return np.where(m>0,10*np.log10(np.maximum(s/np.maximum(n,1e-6),1e-6)),np.nan)
recs=[]
for f in sorted(glob.glob(f"{SRC}/passes/*.nc")):
    a=xr.open_dataset(f).attrs
    recs.append(dict(f=f,set=a["set"],orbit=int(a["orbit"]),t=pd.Timestamp(a["datetime"]),date=a["datetime"][:10]))
R=pd.DataFrame(recs)
def pass_mosaic(fs):
    out=None
    for f in fs:
        v,_=place(f); out=v if out is None else np.where(np.isfinite(out),out,v)
    return smooth_db(out)
ref={}
for o,g in R[R.set=="ref"].groupby("orbit"):
    st=np.stack([pass_mosaic(gg.f) for _,gg in g.groupby("date")])
    ref[o]=np.nanmedian(st,0); print("ref orbit",o,len(st),"dates", f"cover {np.isfinite(ref[o]).mean():.0%}",flush=True)
votes=np.stack([(r<DARK) for r in ref.values()]); valid=np.stack([np.isfinite(r) for r in ref.values()])
permanent=(votes.sum(0)>=np.maximum(1,valid.sum(0)/2))&(valid.sum(0)>0)
permanent=ndimage.binary_opening(permanent,iterations=1)
F=R[R.set=="flood"].copy(); F["key"]=F.date+"_"+F.orbit.astype(str)
layers=[];meta=[]
for key,g in F.groupby("key"):
    o=g.orbit.iloc[0]; vv=pass_mosaic(g.f)
    ob=np.isfinite(vv)&np.isfinite(ref[o])
    w=ob&(vv<DARK)&((vv-ref[o])<DROP)&~permanent
    lab,n=ndimage.label(w); sz=ndimage.sum(w,lab,range(1,n+1)); w=np.isin(lab,np.where(sz>=MMU)[0]+1)
    lay=np.full((H,W),255,"uint8"); lay[ob]=0; lay[w]=1
    layers.append(lay); meta.append(dict(key=key,orbit=int(o),t=g.t.min(),cover=float(ob.mean()),wet_km2=w.sum()*0.0025))
    print(key, f"cover {ob.mean():.0%} wet {w.sum()*0.0025:7.1f} km2",flush=True)
M=pd.DataFrame(meta).sort_values("t").reset_index(drop=True)
cube=np.stack([layers[i] for i in M.index.map(lambda k: [m['key'] for m in meta].index(M.key[k]))])
ds=xr.Dataset(dict(water=(("pass","y","x"),cube),permanent=(("y","x"),permanent.astype("uint8")),dem=(("y","x"),dem.values)),
              coords=dict(x=X,y=Y,t=("pass",M.t.values),orbit=("pass",M.orbit.values)))
ds.water.attrs.update(meaning="0 dry, 1 open water, 255 not observed",dark_db=DARK,drop_db=DROP,mmu_px=MMU)
ds.to_netcdf("cube_ab.nc",engine="netcdf4",encoding={"water":{"zlib":True}})
M.to_csv("passes_ab.csv",index=False); print("permanent km2",permanent.sum()*0.0025)
