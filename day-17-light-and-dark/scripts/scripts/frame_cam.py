"""Numpy replica of the Blender track-to camera, to choose framings (no render needed)."""
import numpy as np, rasterio
def make(root):
    with rasterio.open(root/"data/dem/rgealti_5m_marsanne_L93.tif") as ds: dem=ds.read(1).astype(float); dt=ds.transform
    return dem,dt
def ground(dem,dt,x,y):
    from scipy.ndimage import map_coordinates
    c=(np.asarray(x)-dt.c)/5-0.5; r=(dt.f-np.asarray(y))/5-0.5
    return map_coordinates(dem,[r,c],order=1,mode="nearest")
def project(P, target_xyz, bearing, elev, dist, lens, W, H, sensor=36.0):
    fb,el=np.radians(bearing),np.radians(elev)
    tgt=np.array(target_xyz,float)
    cam=tgt+dist*np.array([np.sin(fb)*np.cos(el),np.cos(fb)*np.cos(el),np.sin(el)])
    f=(tgt-cam); f/=np.linalg.norm(f); r=np.cross(f,[0,0,1.0]); r/=np.linalg.norm(r); u=np.cross(r,f)
    d=P-cam; z=d@f; x=d@r; y=d@u
    fpx=lens/sensor*W
    return np.column_stack([W/2+fpx*x/z, H/2-fpx*y/z, z])
