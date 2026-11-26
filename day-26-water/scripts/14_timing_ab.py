"""Per-pixel arrival/departure across the reach. Each pixel uses ITS OWN observations (orbits cover different parts):
arrival between its last observed-dry pass and first observed-wet pass, departure between last wet and next observed-dry.
Within each window, low ground (height above the nearest permanent river pixel) wets first and drains last."""
import numpy as np, pandas as pd, xarray as xr
from scipy import ndimage
ds=xr.open_dataset("cube_ab.nc"); t=pd.to_datetime(ds.t.values)
keep=(t>="2026-01-25")&(t<="2026-03-10")&~((t.strftime("%m-%d")=="02-19")&(ds.orbit.values==132))  # wind-blind pass
w=ds.water.values[keep]; T=((t[keep]-pd.Timestamp("2026-02-01"))/pd.Timedelta("1D")).values
obs=w!=255; wet=w==1
perm=ds.permanent.values==1; dem=ds.dem.values.astype("float64")
_,(iy,ix)=ndimage.distance_transform_edt(~perm,return_indices=True)
dm=ndimage.median_filter(np.nan_to_num(dem,nan=500),3); hand=dm-dm[iy,ix]
ev=(T>=8)&(T<=28)                                   # flood event window
n=(wet&ev[:,None,None]).sum(0)
Tb=T[:,None,None]
first=np.where(wet&ev[:,None,None],Tb,np.inf).min(0); last=np.where(wet&ev[:,None,None],Tb,-np.inf).max(0)
inside=obs&(Tb>=first)&(Tb<=last)
frac=(wet&inside).sum(0)/np.maximum(inside.sum(0),1)
flooded=(n>=2)&(frac>=0.6)&(hand<15)
lab,k=ndimage.label(flooded); sz=ndimage.sum(flooded,lab,range(1,k+1)); flooded=np.isin(lab,np.where(sz>=8)[0]+1)
prev_dry=np.where(obs&~wet&(Tb<first),Tb,-np.inf).max(0); prev_dry=np.where(np.isfinite(prev_dry),prev_dry,first-3)
next_dry=np.where(obs&~wet&(Tb>last),Tb,np.inf).min(0);  next_dry=np.where(np.isfinite(next_dry),next_dry,last+3)
def rank_fill(t0,t1,key,mask,ascending):
    out=np.full(mask.shape,np.nan)
    pairs=np.stack([t0[mask],t1[mask]],1); keys=key[mask]; res=np.empty(mask.sum())
    _,inv=np.unique(pairs,axis=0,return_inverse=True); inv=inv.ravel()
    for g in np.unique(inv):
        m=inv==g; r=keys[m].argsort().argsort()/max(1,m.sum()-1)
        if not ascending: r=1-r
        res[m]=pairs[m,0]+r*(pairs[m,1]-pairs[m,0])
    out[mask]=res; return out
arr=rank_fill(prev_dry,first,hand,flooded,True)
dep=rank_fill(last,next_dry,hand,flooded,False)
np.savez_compressed("timing_ab.npz",arr=arr,dep=dep,first=np.where(flooded,first,np.nan),last=np.where(flooded,last,np.nan),
                    hand=hand,perm=perm,dem=dem,flooded=flooded)
print("flooded km2",flooded.sum()*0.0025)
print("arrival pct",np.nanpercentile(arr,[1,10,50,90,99]).round(1))
print("first-seen by day:",{float(round(d,1)):round((np.where(flooded,first,np.nan)==d).sum()*0.0025,1) for d in np.unique(first[flooded])})
