"""Neutral basemap texture: hillshade + OSM water + main roads, same extent as the DEM (Lambert-93)."""
import json, sys, numpy as np, rasterio
from scipy.ndimage import zoom, gaussian_filter
from pyproj import Transformer
from PIL import Image, ImageDraw
dem_p, osm_p, out_p = sys.argv[1:4]
d = rasterio.open(dem_p); z = d.read(1).astype('float64')
X0, Y1 = d.transform.c, d.transform.f; RES = d.transform.a
S = 3                                      # texture px per DEM px (40 m -> 13.3 m)
H, W = z.shape[0]*S, z.shape[1]*S
zz = zoom(gaussian_filter(z, 0.6), S, order=1)
px = RES / S
gy, gx = np.gradient(zz, px)
az, alt = np.radians(315), np.radians(40)  # light from the north-west
slope = np.arctan(np.hypot(gx, gy)); aspect = np.arctan2(-gx, gy)
hs = np.sin(alt)*np.cos(slope) + np.cos(alt)*np.sin(slope)*np.cos(az - aspect)
hs = np.clip(hs, 0, 1)
# colour ramp: valley paper, slopes slightly cooler/greyer with height
t = np.clip((zz - 200) / 2600, 0, 1)[..., None]
low = np.array([238, 235, 228.]); high = np.array([226, 228, 230.])
base = low*(1-t) + high*t
shade = (0.55 + 0.5*hs)[..., None]
img = np.clip(base*shade, 0, 255).astype('uint8')
im = Image.fromarray(img, 'RGB'); dr = ImageDraw.Draw(im, 'RGBA')
tr = Transformer.from_crs(4326, 2154, always_xy=True)
def pix(geom):
    xs, ys = tr.transform([p['lon'] for p in geom], [p['lat'] for p in geom])
    return [((x - X0)/px, (Y1 - y)/px) for x, y in zip(xs, ys)]
WATER = (178, 194, 208, 255)
els = json.load(open(osm_p))['elements']
for e in els:                              # water polygons
    tg = e.get('tags', {})
    if tg.get('natural') == 'water':
        rings = [e['geometry']] if e['type'] == 'way' else [m['geometry'] for m in e.get('members', []) if m.get('role') == 'outer' and 'geometry' in m]
        for r in rings:
            if len(r) > 2: dr.polygon(pix(r), fill=WATER)
for e in els:                              # rivers as lines
    if e.get('tags', {}).get('waterway') == 'river' and 'geometry' in e:
        nm = e['tags'].get('name', '')
        w = 9 if nm in ('L\'Isère', 'Isère', 'Le Drac', 'Drac', 'La Romanche', 'Romanche') else 3
        dr.line(pix(e['geometry']), fill=WATER, width=w)
RW = {'motorway': 4, 'trunk': 4, 'primary': 3, 'secondary': 2, 'tertiary': 1, 'motorway_link': 1, 'trunk_link': 1}
for cls in ['tertiary', 'secondary', 'primary', 'trunk_link', 'motorway_link', 'trunk', 'motorway']:
    for e in els:
        if e.get('tags', {}).get('highway') == cls and 'geometry' in e:
            dr.line(pix(e['geometry']), fill=(255, 255, 255, 190), width=RW[cls])
im.save(out_p, quality=92)
print(W, H, 'px', px, 'm/px')
