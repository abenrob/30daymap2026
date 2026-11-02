"""Timing and Blender inputs for the Rhone animation.

The clock runs in network kilometres: a point lights up at
    t = D_max - (network distance from that point to the sea)
so every source starts early enough that all the water reaches the sea at the same
moment (t = D_max), and every line draws at the same speed.

Lakes fill as a front. Every river point inside a lake is a seed carrying its own
clock time; the front spreads from all seeds at river speed, through the lake only
(multi-source shortest path on a 150 m grid). Along the river line the lake time equals
the line time, so the fill takes as long as the line would have taken to cross, and
the outlet reach starts at the shore exactly when the front gets there. Lakes no reach
touches take the clock time of the nearest river point and just fade in.

Writes to work/data/day-02-lines/blender/:
  meta.json          extents, scene origin, decode ranges, D_max
  height.png         16-bit DEM at 150 m (Lambert-93), for the terrain
  masks.png          8-bit RGB at 150 m: R = inside basin, G = sea
  lake_time.png      16-bit lake arrival time at 150 m (65535 = not a lake)
  rivers.npz         river pieces outside lakes: points (km, scene coords), times, width
  lakes.npz          lake triangles (km, scene coords) and their times
  sea_wide.png       8-bit sea mask, 3,000 km square around the scene origin, for the ground plane

Run from the workspace root after 02 and 04.
"""
import json, os
import numpy as np
import geopandas as gpd
import shapely
import rasterio
from rasterio import features
from rasterio.transform import from_origin
from scipy import sparse
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree
from PIL import Image

D = "work/data/day-02-lines/derived"
OUT = "work/data/day-02-lines/blender"
os.makedirs(OUT, exist_ok=True)
CRS = "EPSG:2154"
STEP = 150.0          # m, densify spacing for river curves
LAKE_RES = 150.0      # m, lake time grid (Blender loads it as float RGBA, so keep it small)

riv = gpd.read_parquet(f"{D}/rivers.parquet").set_crs(4326).to_crs(CRS)
lakes = gpd.read_parquet(f"{D}/lakes.parquet").set_crs(4326).to_crs(CRS)
basin = gpd.read_parquet(f"{D}/basin.parquet").set_crs(4326).to_crs(CRS)
ocean = gpd.read_parquet(f"{D}/ocean.parquet").set_crs(4326).to_crs(CRS)

D_MAX = float(riv["dist_upstream_end_km"].max())
riv["t0"] = D_MAX - riv["dist_upstream_end_km"]
riv["t1"] = D_MAX - riv["dist_to_outlet_km"]
wmax = np.sqrt(riv["up_len_km"].max())
riv["w"] = np.sqrt(riv["up_len_km"]) / wmax

# ---------------------------------------------------------------- terrain rasters
with rasterio.open(f"{D}/dem_150m_l93.tif") as src:
    z = src.read(1, masked=True).filled(0).astype("float64")
    T, (H, W) = src.transform, src.shape
    xmin, ymax = T.c, T.f
    xmax, ymin = xmin + W * T.a, ymax + H * T.e
ZMIN, ZMAX = float(z.min()), float(z.max())
Image.fromarray(np.round((z - ZMIN) / (ZMAX - ZMIN) * 65535).astype("uint16")).save(f"{OUT}/height.png")

rgb = np.zeros((H, W, 3), "uint8")
rgb[..., 0] = features.rasterize(basin.geometry, (H, W), transform=T, fill=0, default_value=255)
rgb[..., 1] = features.rasterize(ocean.geometry, (H, W), transform=T, fill=0, default_value=255)
Image.fromarray(rgb).save(f"{OUT}/masks.png")

ox, oy = (xmin + xmax) / 2, (ymin + ymax) / 2   # scene origin, scene units = km
def to_scene(xy):
    return np.column_stack([(xy[:, 0] - ox) / 1000, (xy[:, 1] - oy) / 1000]).astype("float32")

# ---------------------------------------------------------------- rivers, clipped at lakes
lake_union = shapely.union_all(lakes.geometry.values)
shapely.prepare(lake_union)

def densify_times(line, full, t0, t1):
    """Points every STEP m along `line`, with clock times from their position on `full`."""
    n = max(2, int(np.ceil(line.length / STEP)) + 1)
    pts = shapely.line_interpolate_point(line, np.linspace(0, line.length, n))
    frac = shapely.line_locate_point(full, pts) / full.length
    return shapely.get_coordinates(pts), t0 + frac * (t1 - t0)

pieces, seeds_xy, seeds_t = [], [], []
for g, t0, t1, w, s in zip(riv.geometry, riv.t0, riv.t1, riv.w, riv.strahler):
    if shapely.intersects(g, lake_union):
        outside = shapely.difference(g, lake_union)
        inside = shapely.intersection(g, lake_union)
        for part in shapely.get_parts(inside):
            if part.geom_type == "LineString" and part.length > 0:
                xy, tt = densify_times(part, g, t0, t1)
                seeds_xy.append(xy); seeds_t.append(tt)
        parts = [p for p in shapely.get_parts(outside) if p.geom_type == "LineString" and p.length > 1]
    else:
        parts = [g]
    for p in parts:
        xy, tt = densify_times(p, g, t0, t1)
        pieces.append((xy, tt, w, s))

# all river points (outside lakes) for the nearest-river fallback
all_xy = np.vstack([p[0] for p in pieces])
all_t = np.concatenate([p[1] for p in pieces])
seeds_xy = np.vstack(seeds_xy); seeds_t = np.concatenate(seeds_t)
print(f"river pieces: {len(pieces):,} from {len(riv):,} reaches, {len(all_xy):,} points; "
      f"lake seeds: {len(seeds_xy):,}")

offs = np.cumsum([0] + [len(p[0]) for p in pieces]).astype("int64")
np.savez_compressed(
    f"{OUT}/rivers.npz",
    xy=to_scene(all_xy), offsets=offs,
    t_point=all_t.astype("float32"),
    t0=np.array([p[1][0] for p in pieces], "float32"),
    t1=np.array([p[1][-1] for p in pieces], "float32"),
    w=np.array([p[2] for p in pieces], "float32"),
    strahler=np.array([p[3] for p in pieces], "int8"))

# ---------------------------------------------------------------- lake time field
LW, LH = int(round((xmax - xmin) / LAKE_RES)), int(round((ymax - ymin) / LAKE_RES))
LT = from_origin(xmin, ymax, LAKE_RES, LAKE_RES)
lake_id = features.rasterize(((geom, i + 1) for i, geom in enumerate(lakes.geometry)),
                             (LH, LW), transform=LT, fill=0, all_touched=True, dtype="int32")
mask = lake_id > 0
idx = -np.ones(mask.shape, "int64")
rr, cc = np.nonzero(mask)
idx[rr, cc] = np.arange(len(rr))
N = len(rr)

# 8-connected graph over lake pixels, edge weight in km
rows, cols, wts = [], [], []
for dr, dc in [(0, 1), (1, 0), (1, 1), (1, -1)]:
    r2, c2 = rr + dr, cc + dc
    ok = (r2 >= 0) & (r2 < LH) & (c2 >= 0) & (c2 < LW)
    ok[ok] &= mask[r2[ok], c2[ok]]
    a, b = idx[rr[ok], cc[ok]], idx[r2[ok], c2[ok]]
    rows += [a, b]; cols += [b, a]
    wts += [np.full(len(a), LAKE_RES / 1000 * np.hypot(dr, dc))] * 2

# super-source node N, linked to every seed pixel with weight = seed time - t_min
inv = ~LT
sc, sr = inv * (seeds_xy[:, 0], seeds_xy[:, 1])
sr, sc = np.floor(sr).astype(int), np.floor(sc).astype(int)
ok = (sr >= 0) & (sr < LH) & (sc >= 0) & (sc < LW)
ok[ok] &= mask[sr[ok], sc[ok]]
seed_pix = idx[sr[ok], sc[ok]]
seed_time = seeds_t[ok]
best = {}
for p, t in zip(seed_pix, seed_time):
    if t < best.get(p, np.inf):
        best[p] = t
T_MIN = min(best.values())
rows.append(np.full(len(best), N)); cols.append(np.fromiter(best.keys(), "int64"))
wts.append(np.fromiter(best.values(), "float64") - T_MIN + 1e-6)

G = sparse.csr_matrix((np.concatenate(wts), (np.concatenate(rows), np.concatenate(cols))),
                      shape=(N + 1, N + 1))
dist = dijkstra(G, directed=True, indices=N)[:N] + T_MIN

# The front cuts corners the river line can't, so it would reach the outlet before the
# line does. Per lake, stretch the field so the outlet pixel (the latest seed) fills
# exactly at the line's time; the outlet reach then starts as the front arrives.
seed_lake = lake_id[rr[seed_pix], cc[seed_pix]]
pix_lake = lake_id[rr, cc]
for lid in np.unique(seed_lake):
    s = seed_lake == lid
    j = np.argmax(seed_time[s])
    p_out, t_out = seed_pix[s][j], seed_time[s][j]
    m = (pix_lake == lid) & np.isfinite(dist)
    t_in = dist[m].min()
    if dist[p_out] > t_in and t_out > dist[p_out]:
        dist[m] = t_in + (dist[m] - t_in) * (t_out - t_in) / (dist[p_out] - t_in)

# unreached lake pixels (lakes no reach touches): clock time of the nearest river point
tree = cKDTree(all_xy)
lake_t = np.full(len(lakes), np.nan)
touched = np.zeros(len(lakes), bool)
for i in range(len(lakes)):
    m = lake_id[rr, cc] == i + 1
    if m.any() and np.isfinite(dist[m]).any():
        touched[i] = True
        lake_t[i] = np.nanmin(np.where(np.isfinite(dist[m]), dist[m], np.nan))
    c = lakes.geometry.iloc[i].representative_point()
    if not touched[i]:
        lake_t[i] = all_t[tree.query([c.x, c.y])[1]]
    if m.any():
        d = dist[m]
        d[~np.isfinite(d)] = lake_t[i]
        dist[m] = d
dist[~np.isfinite(dist)] = 0  # pixels of no lake id can't occur; guard anyway

tex = np.full((LH, LW), 65535, "uint16")
tex[rr, cc] = np.clip(np.round(dist / D_MAX * 65000), 0, 65000).astype("uint16")
Image.fromarray(tex).save(f"{OUT}/lake_time.png")
print(f"lakes: {len(lakes)}, crossed by a reach: {touched.sum()}, lake pixels: {N:,}")

# ---------------------------------------------------------------- lake triangles
tri_xy, tri_lake = [], []
for i, geom in enumerate(lakes.geometry):
    for poly in shapely.get_parts(geom):
        tris = shapely.get_parts(shapely.constrained_delaunay_triangles(poly))
        for t in tris:
            tri_xy.append(shapely.get_coordinates(t)[:3])
            tri_lake.append(i)
tri_xy = np.array(tri_xy)
np.savez_compressed(f"{OUT}/lakes.npz",
                    tri=to_scene(tri_xy.reshape(-1, 2)).reshape(-1, 3, 2),
                    lake=np.array(tri_lake, "int32"),
                    elevation=lakes["elevation_m"].to_numpy("float32"),
                    area_km2=lakes["area_km2"].to_numpy("float32"),
                    t_first=lake_t.astype("float32"), crossed=touched)

# ---------------------------------------------------------------- wide sea mask
# The terrain stops at the DEM edge. A flat ground plane carries land and sea out to
# the horizon, so the frame never shows the empty background.
WIDE_KM, WIDE_PX = 3000.0, 1500
ne = gpd.read_file(f"/vsizip/work/data/day-02-lines/raw/ne_10m_ocean.zip/ne_10m_ocean.shp")
half = WIDE_KM * 1000 / 2
WT = from_origin(ox - half, oy + half, WIDE_KM * 1000 / WIDE_PX, WIDE_KM * 1000 / WIDE_PX)
wide_box = shapely.box(ox - half, oy - half, ox + half, oy + half)
# clip in lon/lat first: the global ocean polygon can't be projected to Lambert-93 whole
lonlat = gpd.GeoSeries([wide_box], crs=CRS).to_crs(4326).total_bounds
sea_geom = ne.clip(shapely.box(*lonlat)).to_crs(CRS)
Image.fromarray(features.rasterize(sea_geom.geometry, (WIDE_PX, WIDE_PX), transform=WT, fill=0,
                                   default_value=255).astype("uint8")).save(f"{OUT}/sea_wide.png")

bb = basin.total_bounds
basin_center = [((bb[0] + bb[2]) / 2 - ox) / 1000, ((bb[1] + bb[3]) / 2 - oy) / 1000]

meta = dict(crs=CRS, xmin=xmin, ymin=ymin, xmax=xmax, ymax=ymax, origin=[ox, oy],
            width_km=(xmax - xmin) / 1000, height_km=(ymax - ymin) / 1000,
            dem_px=[W, H], z_min_m=ZMIN, z_max_m=ZMAX,
            lake_px=[LW, LH], lake_time_scale=65000, d_max_km=D_MAX,
            wide_km=WIDE_KM, basin_center_km=basin_center)
json.dump(meta, open(f"{OUT}/meta.json", "w"), indent=1)

# Geneva check: the front should leave the lake when the outlet reach starts
gen = lakes.index[lakes["name"] == "Geneva"][0]
m = lake_id[rr, cc] == gen + 1
print(f"Geneva: front from {np.min(dist[m]):.1f} to {np.max(dist[m]):.1f} km of clock "
      f"(seeds {seeds_t[shapely.contains_xy(lakes.geometry.iloc[gen], seeds_xy[:,0], seeds_xy[:,1])].min():.1f}"
      f" to {seeds_t[shapely.contains_xy(lakes.geometry.iloc[gen], seeds_xy[:,0], seeds_xy[:,1])].max():.1f}), "
      f"D_max {D_MAX:.1f}")
print(json.dumps(meta))
