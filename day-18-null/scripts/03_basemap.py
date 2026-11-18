import numpy as np, json, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from scipy.ndimage import gaussian_filter, zoom
dem=np.load('dem.npy')
OW,OH=1904,1440
d=zoom(dem,(OH/dem.shape[0],OW/dem.shape[1]),order=1)
ds=gaussian_filter(d,1.2)
# hillshade (cell sizes in metres)
cx=104.3e3/OW; cy=78.9e3/OH
gy,gx=np.gradient(gaussian_filter(d,0.8),cy,cx)
slope=np.arctan(np.hypot(gx,gy)*1.3); aspect=np.arctan2(-gy,gx)   # row axis points south
az=np.deg2rad(315); alt=np.deg2rad(42)
hs=np.clip(np.sin(alt)*np.cos(slope)+np.cos(alt)*np.sin(slope)*np.cos(az-np.pi/2-aspect),0,1)
stops=[(200,'#ebe2c8'),(700,'#e3d8b6'),(1200,'#d6c79f'),(1800,'#c7b085'),(2400,'#b89b72'),(2900,'#d9cdb6'),(3600,'#ece5d6')]
zs=np.array([s[0] for s in stops],float)
cols=np.array([matplotlib.colors.to_rgb(s[1]) for s in stops])
rgb=np.stack([np.interp(d,zs,cols[:,k]) for k in range(3)],-1)
rgb=np.clip(rgb*(0.83+0.21*hs[...,None]),0,1)
fig=plt.figure(figsize=(OW/100,OH/100),dpi=100); ax=fig.add_axes([0,0,1,1]); ax.axis('off')
ax.imshow(rgb,origin='upper',extent=(0,OW,OH,0),interpolation='bilinear')
minor=[l for l in range(300,4000,100) if l%500]
major=list(range(500,4000,500))
ax.contour(np.arange(OW),np.arange(OH),ds,levels=minor,colors=[(0.38,0.26,0.15,0.26)],linewidths=0.5)
ax.contour(np.arange(OW),np.arange(OH),ds,levels=major,colors=[(0.38,0.26,0.15,0.55)],linewidths=0.9)
ax.set_xlim(0,OW); ax.set_ylim(OH,0)
fig.savefig('basemap.png',dpi=100); plt.close(fig)
print('saved')
