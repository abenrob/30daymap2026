"""Put VIIRS light where the lights are: street lamps and commercial buildings.

VIIRS (Suomi NPP, night pass ~01:30 local solar time, ~2-3 a.m. clock time) sees mostly public, commercial and
road lighting, not houses. Per native VIIRS pixel (15", ~330 x 460 m here), its intensity I = L x pixel area
(cd, L = radiance x LUM_PER_RAD) goes to the emitters inside it:

Settlements = 8-connected VIIRS pixels >= SETTLE_NW; a town is one over TOWN_KM2 (here Grenoble-Voiron 355 km2,
Chambery-Aix 167 km2); everything else is a village (Saint-Laurent-du-Pont 10 km2, Pont-de-Beauvoisin 19 km2).

  town pixel:                   lamps every 30 m on every paved urban road (BD TOPO urbain), plus commercial and
                                industrial buildings (usage_1), COMMERCIAL_SHARE of the light by footprint
  village (whole settlement):   its total light is shared by the lamps on its main roads inside the built-up area: importance <= 3 and urbain
                                (in Saint-Laurent-du-Pont: avenues Victor Hugo, Jules Ferry, Jean Jaures, de la
                                Gare, route des Echelles, D520, place Gambetta); villages light only their main
                                roads and centre at night, the rest is switched off or never lit

Pixels with no eligible emitter hand their light to the nearest eligible pixel within REASSIGN_PX if that pixel
is a town core (VIIRS blur around bright towns); otherwise their light is dropped inside the fetched tiles
(averaged over 500 m and draped on the terrain it renders as glowing snowfields) and stays on the terrain outside.
Emission direction: Garstang (1986), F = 0.15, scaled to the observer's direction (~0.31 here).

Output: derived/light_points.npz (visible emitters: x, y, z eye-relative with curvature, intensity cd towards the
summit, rgb, area for the emitter size, kind 0 = lamp, 1 = commercial) and derived/lights100_residual.npy.
"""
import importlib, sys, json
import numpy as np, rasterio
from rasterio.warp import reproject, Resampling
from rasterio.crs import CRS
from rasterio.transform import from_origin
from pyproj import Transformer, Geod
from scipy.ndimage import map_coordinates, distance_transform_edt
from common import *

sys.argv = sys.argv[:1]
bs = importlib.import_module("03_build_scene")
LUM_PER_RAD = bs.LUM_PER_RAD
SETTLE_NW, TOWN_KM2 = 1.0, 30.0
COMMERCIAL_SHARE = 0.3
REASSIGN_PX = 4
LAMP_HEIGHT = 6.0
F_UP = 0.15

src = rasterio.open(RAW / "vnl_2025_crop.tif")
R = src.read(1).astype(np.float64); R[~np.isfinite(R)] = 0
to_ll = Transformer.from_crs(AEQD, 4326, always_xy=True)


def pixel_of(x, y):
    lon, lat = to_ll.transform(x, y)
    r, c = rasterio.transform.rowcol(src.transform, lon, lat)
    r, c = np.asarray(r), np.asarray(c)
    ok = (r >= 0) & (r < R.shape[0]) & (c >= 0) & (c < R.shape[1])
    return r * R.shape[1] + c, ok


# pixel areas (m2) on the ellipsoid, intensity per pixel (cd)
geod = Geod(ellps="GRS80")
rx, ry = src.transform.a, -src.transform.e
lat_rows = src.transform.f - (np.arange(R.shape[0]) + 0.5) * ry
row_area = np.array([abs(geod.polygon_area_perimeter([0, rx, rx, 0], [la - ry / 2, la - ry / 2, la + ry / 2, la + ry / 2])[0]) for la in lat_rows])
I_pix = (R * LUM_PER_RAD).ravel() * np.repeat(row_area, R.shape[1])
from scipy.ndimage import label
lab, nlab = label(R >= SETTLE_NW, structure=np.ones((3, 3)))
pix_area = np.repeat(row_area, R.shape[1]).reshape(R.shape)
comp_km2 = np.bincount(lab.ravel(), weights=pix_area.ravel() / 1e6)
town = (lab.ravel() > 0) & (comp_km2[lab.ravel()] >= TOWN_KM2)
group = np.where(lab.ravel() > 0, lab.ravel(), nlab + 1 + np.arange(R.size))      # village group: settlement, or the pixel itself
print(f"{nlab} settlements, {np.sum(comp_km2[1:] >= TOWN_KM2)} towns")

# candidates
Ro = np.load(DERIVED / "roads.npz")
lx, ly, imp, urb, paved = Ro["x"], Ro["y"], Ro["importance"], Ro["urbain"], Ro["paved"]
lp, ok = pixel_of(lx, ly); lx, ly, imp, urb, paved, lp = lx[ok], ly[ok], imp[ok], urb[ok], paved[ok], lp[ok]
lamp = np.where(town[lp], urb & paved, urb & paved & (imp <= 3))
lx, ly, lp = lx[lamp], ly[lamp], lp[lamp]

B = np.load(DERIVED / "buildings.npz")
bx, by, ba, bh, use = B["x"], B["y"], B["area"], B["height"], B["usage"]
com = np.isin(use, ["Commercial et services", "Industriel"]) & (ba >= 50)
bx, by, ba, bh = bx[com], by[com], ba[com], bh[com]
bp, ok = pixel_of(bx, by); bx, by, ba, bh, bp = bx[ok], by[ok], ba[ok], bh[ok], bp[ok]
keepc = town[bp]                                   # commercial lights only in town pixels
bx, by, ba, bh, bp = bx[keepc], by[keepc], ba[keepc], bh[keepc], bp[keepc]

n_lamp = np.bincount(lp, minlength=R.size); a_com = np.bincount(bp, weights=ba, minlength=R.size)
has = (n_lamp > 0) | (a_com > 0)

# blur around town cores; drop the rest inside the fetched tiles
rr, cc = np.mgrid[0:R.shape[0], 0:R.shape[1]]
plon, plat = rasterio.transform.xy(src.transform, rr.ravel(), cc.ravel())
px_, py_ = Transformer.from_crs(4326, AEQD, always_xy=True).transform(np.asarray(plon), np.asarray(plat))
tiles = set(map(tuple, json.load(open(DERIVED / "light_tiles.json"))["tiles"]))
tx = (np.floor(px_ / 2000) * 2000).astype(int); ty = (np.floor(py_ / 2000) * 2000).astype(int)
in_tiles = np.array([(a_, b_) in tiles for a_, b_ in zip(tx, ty)])
dist, (ir, ic) = distance_transform_edt(~has.reshape(R.shape), return_indices=True)
near = (ir * R.shape[1] + ic).ravel()
move = in_tiles & town & ~has & (dist.ravel() <= REASSIGN_PX) & (I_pix > 0) & town[near]
I2 = I_pix.copy(); np.add.at(I2, near[move], I2[move]); I2[move] = 0
dropped = in_tiles & town & ~has & ~move & (I_pix > 0)
tot = I_pix[in_tiles].sum()
print(f"in the fetched tiles: towns {I_pix[in_tiles & town].sum() / tot:.0%} of the light "
      f"({I_pix[move].sum() / tot:.0%} moved from blur, {I_pix[dropped].sum() / tot:.0%} dropped), villages {I_pix[in_tiles & ~town].sum() / tot:.0%}")

# village settlements: total light shared by all their main-road lamps
gid = np.unique(group, return_inverse=True)[1]
vill_pix = in_tiles & ~town
I_vgroup = np.bincount(gid[vill_pix], weights=I_pix[vill_pix], minlength=gid.max() + 1)
n_vlamp = np.bincount(gid[lp], minlength=gid.max() + 1)
v_ok = (n_vlamp > 0)
print(f"villages: {I_vgroup[v_ok].sum() / max(I_vgroup.sum(), 1e-9):.0%} of village light lands on main-road lamps, the rest is dropped")
# share per emitter (town pixels by pixel, villages by settlement)
share_com = np.where(n_lamp > 0, COMMERCIAL_SHARE, 1.0) * (a_com > 0)
I_lamp = np.where(town[lp], I2[lp] * (1 - share_com[lp]) / np.maximum(n_lamp[lp], 1),
                  I_vgroup[gid[lp]] / np.maximum(n_vlamp[gid[lp]], 1))
I_com = I2[bp] * share_com[bp] * ba / np.maximum(a_com[bp], 1e-9)
print(f"{len(lx):,} lamps ({np.sum(~town[lp]):,} in village pixels), {len(bx):,} commercial buildings")

# residual for the terrain (outside the tiles only)
res = R.copy().ravel(); res[in_tiles] = 0; res = res.reshape(R.shape)
name, half, cell = RINGS[2]; n = int(2 * half / cell)
dst = np.zeros((n, n), np.float32)
reproject(res.astype(np.float32), dst, src_transform=src.transform, src_crs=src.crs,
          dst_transform=from_origin(-half, half, cell, cell), dst_crs=CRS.from_proj4(AEQD), resampling=Resampling.average)
np.save(DERIVED / "lights100_residual.npy", dst)

# emitters, visibility
x = np.r_[lx, bx]; y = np.r_[ly, by]; I = np.r_[I_lamp, I_com]
kind = np.r_[np.zeros(len(lx), int), np.ones(len(bx), int)]
area = np.r_[np.full(len(lx), np.pi * 2.0 ** 2), ba]
hgt = np.r_[np.full(len(lx), LAMP_HEIGHT), np.where(np.isfinite(bh), np.clip(bh, 3, 30), 8.0)]
vis = bs.visibility_masks()
seen = np.zeros(len(x), bool); done = np.zeros(len(x), bool)
for lname, srcr, f, keepw, hole in bs.LEVELS:
    lcell = next(r for r in RINGS if r[0] == srcr)[2] * f
    m = ~done & (np.abs(x) < keepw) & (np.abs(y) < keepw)
    c = np.clip(((x[m] + keepw) / lcell).astype(int), 0, vis[lname].shape[1] - 1)
    r = np.clip(((keepw - y[m]) / lcell).astype(int), 0, vis[lname].shape[0] - 1)
    seen[m] = vis[lname][r, c]; done |= m
sel = seen & (I > 0)
x, y, I, kind, area, hgt = x[sel], y[sel], I[sel], kind[sel], area[sel], hgt[sel]
print(f"{sel.sum():,} visible emitters ({np.sum(kind == 0):,} lamps, {np.sum(kind == 1):,} commercial)")

g = np.full(len(x), np.nan)
for rname, half_r, cell_r in RINGS:
    arr = np.load(DERIVED / f"{rname}.npy")
    m = np.isnan(g) & (np.abs(x) < half_r - 2 * cell_r) & (np.abs(y) < half_r - 2 * cell_r)
    g[m] = map_coordinates(arr, [(half_r - y[m]) / cell_r - .5, (x[m] + half_r) / cell_r - .5], order=1)
d = np.hypot(x, y)
z = g + np.where(kind == 0, hgt, 0.5 * hgt) - drop(d) - (GROUND + EYE)
u = np.arctan2(-z, d) + d / R_EARTH
theta = np.pi / 2 - u
pf = (2 * (1 - F_UP) * np.cos(theta) + 0.554 * F_UP * theta ** 4) / (2 * (1 - F_UP))
I = I * pf
rng = np.random.default_rng(25)
led = rng.random(len(x)) < 0.55                       # assumed mix: 55% LED (~3,500 K), 45% sodium (~2,000 K)
rgb = np.where(led[:, None], [1.0, 0.86, 0.72], [1.0, 0.62, 0.30])
rgb = np.where((kind == 1)[:, None], [1.0, 0.95, 0.88], rgb) * rng.uniform(0.85, 1.15, (len(x), 1))
np.savez_compressed(DERIVED / "light_points.npz", x=x, y=y, z=z, intensity=I, rgb=rgb, area=area, height=hgt,
                    kind=kind, emission_factor=pf)
print("saved light_points.npz")
