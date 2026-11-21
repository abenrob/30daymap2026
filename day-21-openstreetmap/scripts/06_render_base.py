"""Static basemap for the map panel -> base_map.png (1080 x 841).

Soft multidirectional hillshade of SRTM3 on a paper tint, Natural Earth lakes and rivers, OSM canton / Land lines,
and country borders (Switzerland and Liechtenstein from OSM, the rest from Natural Earth). Drawn at 2x, then
downsampled.
"""
import geopandas as gpd
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from shapely.ops import unary_union

from config import BASE_MAP, DATA, K, LAT0, LAT1, LON0, LON1, MAP_H, MAP_W, xy
from osm_polygons import load_boundaries

S = 2                                      # supersampling
BM = f'{DATA}/basemap'

# ---- DEM: mosaic the four tiles (north row on top) and resample onto the map grid
tile = {(i, j): np.fromfile(f'{BM}/srtm3_{i}_{j}.bil', '<f4').reshape(1300, 1600) for i in range(2) for j in range(2)}
dem = np.vstack([np.hstack([tile[0, 1], tile[1, 1]]), np.hstack([tile[0, 0], tile[1, 0]])])
DLON0, DLON1, DLAT0, DLAT1 = 5.3, 10.5, 45.2, 48.1
mw, mh = MAP_W * S, MAP_H * S
lons = LON0 + (np.arange(mw) + .5) / mw * (LON1 - LON0)
lats = LAT1 - (np.arange(mh) + .5) / mh * (LAT1 - LAT0)
rows, cols = np.meshgrid((DLAT1 - lats) / (DLAT1 - DLAT0) * dem.shape[0] - .5,
                         (lons - DLON0) / (DLON1 - DLON0) * dem.shape[1] - .5, indexing='ij')
z = ndimage.gaussian_filter(ndimage.map_coordinates(dem, [rows, cols], order=1).astype('f4'), 1.0)

# ---- hillshade: NW key light plus W and N fill, slope exaggerated 1.6x
cell = (LON1 - LON0) / mw * 111320 * K     # metres per pixel
dy, dx = np.gradient(z, cell)
slope = np.arctan(np.hypot(dx, dy) * 1.6)
aspect = np.arctan2(-dx, dy)


def hillshade(azimuth, altitude=40):
    az, alt = np.radians(azimuth), np.radians(altitude)
    return np.clip(np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect), 0, 1)


shade = 0.55 * hillshade(315) + 0.25 * hillshade(270) + 0.20 * hillshade(360)

# ---- colour: paper, a faint green-to-white elevation tint, darker warm shadows and lighter highlights
paper = np.array([0xf4, 0xee, 0xdf], 'f4') / 255
valley = np.array([0xdf, 0xe2, 0xc8], 'f4') / 255
summit = np.array([0xfb, 0xf8, 0xf1], 'f4') / 255
e = np.clip((z - 200) / 3200, 0, 1)[..., None] ** 0.7
tint = paper * 0.35 + (valley * (1 - e) + summit * e) * 0.65
light = shade[..., None] - 0.70
rgb = tint + np.where(light < 0, light * np.array([0.62, 0.58, 0.52]), light * 0.35)
img = Image.fromarray((np.clip(rgb, 0, 1) * 255).astype('uint8'), 'RGB')
draw = ImageDraw.Draw(img, 'RGBA')


# ---- vector helpers (all coordinates through config.xy at the supersampled scale)
def polygons(geom):
    if geom.geom_type == 'Polygon':
        yield geom
    elif hasattr(geom, 'geoms'):
        for g in geom.geoms:
            yield from polygons(g)


def line(geom, fill, width):
    parts = [geom] if geom.geom_type in ('LineString', 'LinearRing') else list(getattr(geom, 'geoms', []))
    for g in parts:
        if g.geom_type == 'Polygon':
            g = g.exterior
        draw.line([xy(*c[:2], s=S) for c in g.coords], fill=fill, width=width, joint='curve')


def area(geom, fill, outline, width):
    for p in polygons(geom):
        ring = [xy(*c, s=S) for c in p.exterior.coords]
        draw.polygon(ring, fill=fill)
        draw.line(ring, fill=outline, width=width, joint='curve')


def ne(name):
    return gpd.read_file(f'{BM}/{name}.geojson', bbox=(LON0 - 1, LAT0 - 1, LON1 + 1, LAT1 + 1)).geometry.dropna()


units = load_boundaries(f'{DATA}/bnd_cantons.json')
for g in units.geometry:                                              # cantons, Vorarlberg, Tirol
    for p in polygons(g):
        line(p.exterior, (120, 105, 85, 55), 2)
for name, width in [('ne_10m_rivers_europe', 3), ('ne_10m_rivers_lake_centerlines', 4)]:
    for g in ne(name):
        line(g, (127, 169, 191, 230), width)
for name in ['ne_10m_lakes', 'ne_10m_lakes_europe']:
    for g in ne(name):
        area(g, (169, 201, 216, 255), (127, 169, 191, 255), 2)

# Natural Earth's Swiss border does not line up with OSM cantons, so draw CH + LI from OSM and mask NE there.
ch_li = unary_union(list(units[~units.name.isin(['Vorarlberg', 'Tirol'])].geometry)).buffer(0)
mask = ch_li.buffer(0.03)
for g in ne('ne_10m_admin_0_countries'):
    for p in polygons(g):
        rest = p.exterior.difference(mask)
        if not rest.is_empty:
            line(rest, (90, 80, 69, 200), 4)
for p in polygons(ch_li):
    line(p.exterior, (90, 80, 69, 210), 4)
for g in units[units.name == 'Liechtenstein'].geometry:
    for p in polygons(g):
        line(p.exterior, (90, 80, 69, 170), 3)

img = img.resize((MAP_W, MAP_H), Image.LANCZOS)
img.save(BASE_MAP)
print('basemap', img.size, '->', BASE_MAP)
