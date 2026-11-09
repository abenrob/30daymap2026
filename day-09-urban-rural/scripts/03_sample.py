"""Average every layer over each transect window and write profile.json for the page.

Each window (1 km along the line x 3 km across) is covered by a 10 m point lattice, 30,000
points. Every point is projected into each layer's own CRS (Mollweide for GHSL, Lambert-93
for the HRL) and reads the pixel it falls in, so nothing is resampled beforehand.
"""
import json, numpy as np, rasterio
from pyproj import Transformer

T = json.load(open('transect.json'))
ux, uy = T['u']; nx, ny = T['n']; HW = T['half_width_m']
R = 'raw/'
LAYERS = {
 'pop':  R + 'GHS_POP_E2020_GLOBE_R2023A_54009_100_V1_0_R4_C19.tif',     # people per 100 m cell
 'bv':   R + 'GHS_BUILT_V_E2020_GLOBE_R2023A_54009_100_V1_0_R4_C19.tif', # m3 of building per cell
 'bs':   R + 'GHS_BUILT_S_E2020_GLOBE_R2023A_54009_100_V1_0_R4_C19.tif', # m2 built-up per cell (kept as a fallback)
 'smod': R + 'GHS_SMOD_E2020_GLOBE_R2023A_54009_1000_V2_0_R4_C19.tif',   # Degree of Urbanisation class, 1 km
 'imd':  R + 'hrl_imd_2018_l93.tif',                                     # % sealed, 10 m
}

# lattice offsets: a along the line, c across it
STEP = 10.0
a = np.arange(-500 + STEP / 2, 500, STEP); c = np.arange(-HW + STEP / 2, HW, STEP)
A, C = np.meshgrid(a, c); A = A.ravel(); C = C.ravel()

moll = Transformer.from_crs(2154, 'ESRI:54009', always_xy=True)
ds = {k: rasterio.open(p) for k, p in LAYERS.items()}
arr = {k: d.read(1) for k, d in ds.items()}

def read(k, x, y):
    """Pixel values of layer k at points x, y (in that layer's CRS)."""
    d = ds[k]; r, cidx = rasterio.transform.rowcol(d.transform, x, y)
    r = np.asarray(r); cidx = np.asarray(cidx)
    assert ((r >= 0) & (r < d.height) & (cidx >= 0) & (cidx < d.width)).all(), k
    return arr[k][r, cidx]

# GHS-SMOD level 2 codes -> level 1: 3 urban centre, 2 urban cluster, 1 rural, 0 water
L1 = {30: 3, 23: 2, 22: 2, 21: 2, 13: 1, 12: 1, 11: 1, 10: 0}

out = []
for s in T['samples']:
    x = s['x'] + A * ux + C * nx; y = s['y'] + A * uy + C * ny
    mx, my = moll.transform(x, y)
    pop = read('pop', mx, my).astype(float); pop[pop < 0] = 0   # nodata is negative
    bv = read('bv', mx, my).astype(float); bs = read('bs', mx, my).astype(float)
    sm = read('smod', mx, my); imd = read('imd', x, y).astype(float)
    imd_valid = imd <= 100   # 254/255 are unclassifiable / outside

    # class = majority by area among land classes; also keep the shares and the centre cell
    l1 = np.vectorize(lambda v: L1.get(int(v), -1))(sm)
    share = {str(k): round(float((l1 == k).mean()), 3) for k in (0, 1, 2, 3)}
    land = {k: v for k, v in share.items() if k != '0'}
    cls = int(max(land, key=land.get))
    cmx, cmy = moll.transform(s['x'], s['y'])
    ccls = L1.get(int(read('smod', np.array([cmx]), np.array([cmy]))[0]), -1)

    out.append(dict(s,
        pop_km2=round(pop.mean() / 0.01, 1),          # a 100 m cell is 0.01 km2
        imd_pct=round(imd[imd_valid].mean(), 2),
        bs_pct=round(bs.mean() / 10000 * 100, 2),
        bv_m3m2=round(bv.mean() / 10000, 3),          # m3 of building per m2 of ground
        smod_l1=cls, smod_l1_centre=ccls, smod_share=share,
        smod_codes=sorted({int(v) for v in np.unique(sm)})))

# heights for the page: square root of the share of the line maximum, because a linear
# scale leaves everything after the Paris suburbs flat. *_n keeps the linear share.
for k in ('pop_km2', 'imd_pct', 'bv_m3m2', 'bs_pct'):
    m = max(o[k] for o in out)
    for o in out:
        o[k.split('_')[0] + '_n'] = round(o[k] / m, 4)
        o[k.split('_')[0] + '_h'] = round((o[k] / m) ** 0.5, 4)

meta = dict(route='Paris (point zero, Notre-Dame) to Chartres cathedral, straight line',
    length_km=round(T['length_m'] / 1000, 1), step_km=1,
    height='sqrt(value / transect max); *_n fields keep the linear share', window='1 km along x 3 km across, 10 m point lattice',
    classes={'3': 'Urban centre', '2': 'Urban cluster (towns, suburbs)', '1': 'Rural', '0': 'Water'},
    sources={'pop': 'GHS-POP R2023A, epoch 2020, 100 m', 'imd': 'Copernicus HRL Imperviousness Density 2018, 10 m',
             'bv': 'GHS-BUILT-V R2023A, epoch 2020, 100 m', 'bs': 'GHS-BUILT-S R2023A, epoch 2020, 100 m',
             'smod': 'GHS-SMOD R2023A (Degree of Urbanisation), epoch 2020, 1 km; class = majority by area in window'})
json.dump(dict(meta=meta, samples=out), open('profile.json', 'w'), indent=1)

print('km   pop/km2  imd%  bs%   bv   L1 ctr')
for o in out: print(f"{o['km']:5.0f} {o['pop_km2']:8.0f} {o['imd_pct']:5.1f} {o['bs_pct']:5.1f} {o['bv_m3m2']:5.2f}  {o['smod_l1']}  {o['smod_l1_centre']}")
