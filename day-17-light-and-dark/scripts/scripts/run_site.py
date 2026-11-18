"""Real-site run: Marsanne DEM, 8 included turbines, terrain occlusion ON and OFF (same hits)."""
import sys, json, time, resource
from pathlib import Path
import numpy as np, pandas as pd, yaml
from shapely.geometry import shape
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.solar import compute_sun
from src.geometry import Turbine
from src.terrain import DEM, horizon_table, HorizonOcclusion
from src.flicker import Grid, FlickerParams, compute_flicker, compute_points, annual_hours, max_daily_minutes, days_over
from src.io import write_geotiff, save_stack

cfg = yaml.safe_load(open(ROOT / "config.yaml"))
sr, pr = cfg["site_run"], cfg["params"]
out = ROOT / "outputs"; cache = ROOT / "data" / "cache"; cache.mkdir(exist_ok=True)
pre = sr["out_prefix"]
T0 = time.perf_counter()
dem = DEM(ROOT / cfg["dem"]["path"])
print(f"DEM {dem.z.shape}, res {dem.res}, z {np.nanmin(dem.z):.0f}-{np.nanmax(dem.z):.0f}")

# ---- turbines
df = pd.read_csv(ROOT / sr["turbines_csv"])
rows = []
for _, r in df.iterrows():
    east = str(r["group"]).startswith("East group")
    if east and not sr["include_east_group"]:
        continue
    if not east and not any(str(r["group"]).startswith(g) for g in sr["include_groups"]):
        continue
    hub, D = r["hub_height_m"], r["rotor_diameter_m"]
    if east:
        hub, D = sr["east_group_specs"]["hub_height_m"], sr["east_group_specs"]["rotor_diameter_m"]
    assert pd.notna(hub) and pd.notna(D), f"missing specs for {r['id']}"
    rows.append((r["id"], r["x_l93"], r["y_l93"], float(hub), float(D)))
turbines = []
for tid, x, y, hub, D in rows:
    gz = float(dem.sample(x, y))
    turbines.append(Turbine(tid, x, y, gz, hub, D, pr["default_overhang_m"]))
    print(f"  {tid}: ground {gz:.1f} m, hub {hub:g}, D {D:g}")
json.dump([t.__dict__ for t in turbines], open(out / f"{pre}_turbines_used.json", "w"), indent=1)

# ---- grid: DEM cells within 10 D of any turbine (cropped bounding window of the DEM)
res = dem.res
rad = [pr["max_distance_diameters"] * t.rotor_diameter + t.overhang for t in turbines]
x0 = min(t.x - r for t, r in zip(turbines, rad)); x1 = max(t.x + r for t, r in zip(turbines, rad))
y0 = min(t.y - r for t, r in zip(turbines, rad)); y1 = max(t.y + r for t, r in zip(turbines, rad))
c0 = max(0, int(np.floor((x0 - dem.xmin) / res))); c1 = min(dem.ncols, int(np.ceil((x1 - dem.xmin) / res)))
r0 = max(0, int(np.floor((dem.ymax - y1) / res))); r1 = min(dem.nrows, int(np.ceil((dem.ymax - y0) / res)))
grid = Grid(xmin=dem.xmin + c0 * res, ymax=dem.ymax - r0 * res, res=res, nrows=r1 - r0, ncols=c1 - c0,
            crs=cfg["site"]["crs"], z=dem.z[r0:r1, c0:c1].copy())
print(f"grid {grid.nrows}x{grid.ncols} = {grid.nrows*grid.ncols} cells")

# ---- sun (single site latitude/longitude: mean of turbines)
from pyproj import Transformer
tr = Transformer.from_crs(cfg["site"]["crs"], "EPSG:4326", always_xy=True)
lon, lat = tr.transform(np.mean([t.x for t in turbines]), np.mean([t.y for t in turbines]))
sun = compute_sun(lat, lon, cfg["time"]["year"], cfg["time"]["step_minutes"], pr["min_sun_elevation_deg"], cfg["site"]["crs"])
print(f"sun at {lat:.4f},{lon:.4f}: {sun.vec.shape[0]} daylight minutes")
params = FlickerParams(pr["max_distance_diameters"], pr["observer_height_m"], pr["chunk_cells"])

# ---- receptors
bj = json.load(open(ROOT / sr["buildings"]))
rec = []
for f in bj["features"]:
    n = f["properties"].get("nombre_de_logements")
    if n is not None and n > sr["receptor_min_logements"]:
        c = shape(f["geometry"]).centroid
        rec.append((f["properties"]["cleabs"], c.x, c.y, n))
rec = pd.DataFrame(rec, columns=["id", "x", "y", "logements"])
rec["ground_z"] = dem.sample(rec.x.values, rec.y.values)
rec["z"] = rec.ground_z + pr["observer_height_m"]
rec = rec[(rec.x > dem.xmin) & (rec.x < dem.xmin + dem.ncols * res) & (rec.y < dem.ymax) & (rec.y > dem.ymax - dem.nrows * res)].reset_index(drop=True)
print(f"receptors: {len(rec)}")

# ---- horizons (grid cells in range + receptors)
X, Y = grid.centres()
P = np.column_stack([X.ravel(), Y.ravel(), (grid.z + params.observer_height).ravel()])
inr = np.zeros(len(P), bool)
for t in turbines:
    inr |= np.linalg.norm(P - t.nominal_hub, axis=1) <= params.max_distance_diameters * t.rotor_diameter + t.overhang
hid = np.nonzero(inr)[0]
t1 = time.perf_counter()
hz = cfg["site_run"]["horizon"]
tab = horizon_table(dem, P[hid, 0], P[hid, 1], P[hid, 2], hz["azimuth_bins"], hz["max_distance_m"], cache, "grid")
print(f"grid horizon table {tab.shape} ({tab.nbytes/1e6:.0f} MB) in {time.perf_counter()-t1:.0f}s")
pmap = np.full(len(P), -1, np.int32); pmap[hid] = np.arange(hid.size)
occ_grid = HorizonOcclusion(tab, pmap, sun)
PR = rec[["x", "y", "z"]].values
tabr = horizon_table(dem, PR[:, 0], PR[:, 1], PR[:, 2], hz["azimuth_bins"], hz["max_distance_m"], cache, "rec")
occ_rec = HorizonOcclusion(tabr, np.arange(len(PR), dtype=np.int32), sun)

# ---- grid run (occ + free from the same hits)
t2 = time.perf_counter()
res_g = compute_flicker(grid, turbines, sun, params, occlusion=occ_grid, want_unoccluded=True)
t_grid = time.perf_counter() - t2
st, sf = res_g["stack"], res_g["stack_free"]
del res_g
H, Hf = annual_hours(st), annual_hours(sf)
M, Mf = max_daily_minutes(st), max_daily_minutes(sf)
DO = days_over(st, cfg["thresholds"]["daily_minutes"])
write_geotiff(out / f"{pre}_annual_hours.tif", H, grid, nodata=-1)
write_geotiff(out / f"{pre}_max_daily_minutes.tif", M, grid, dtype="uint16")
write_geotiff(out / f"{pre}_days_over_30min.tif", DO, grid, dtype="uint16")
write_geotiff(out / f"{pre}_annual_hours_noocc.tif", Hf, grid, nodata=-1)
write_geotiff(out / f"{pre}_max_daily_minutes_noocc.tif", Mf, grid, dtype="uint16")
write_geotiff(out / f"{pre}_annual_hours_occlusion_removed.tif", Hf - H, grid, nodata=-9999)
save_stack(out / f"{pre}_stack.npz", st, grid, cfg["time"]["year"], cfg["time"]["step_minutes"])
np.save(out / f"{pre}_grid_inrange_mask.npy", inr.reshape(grid.nrows, grid.ncols))
del st, sf

# ---- receptors
t3 = time.perf_counter()
rr = compute_points(PR, turbines, sun, params, occlusion=occ_rec, want_unoccluded=True, per_turbine=True, verbose=False)
thr_h, thr_m = cfg["thresholds"]["annual_hours"], cfg["thresholds"]["daily_minutes"]
r = rec.copy()
r["annual_hours"] = rr["stack"].sum(0, dtype=np.uint32) / 60.0
r["max_daily_min"] = rr["stack"].max(0)
r["days_gt30min"] = (rr["stack"] > thr_m).sum(0)
r["annual_hours_noocc"] = rr["stack_free"].sum(0, dtype=np.uint32) / 60.0
r["max_daily_min_noocc"] = rr["stack_free"].max(0)
r["days_gt30min_noocc"] = (rr["stack_free"] > thr_m).sum(0)
for i, t in enumerate(turbines):
    r[f"h_{t.id}"] = rr["turb_minutes"][:, i] / 60.0
r["flag_30h"] = r.annual_hours > thr_h
r["flag_30min"] = r.max_daily_min > thr_m
r["flag_30h_noocc"] = r.annual_hours_noocc > thr_h
r["flag_30min_noocc"] = r.max_daily_min_noocc > thr_m
r.to_csv(out / f"{pre}_receptors.csv", index=False)
gj = {"type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}},
      "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [float(a.x), float(a.y)]},
                    "properties": {k: (v.item() if hasattr(v, "item") else v) for k, v in a.drop(["x", "y"]).items()}}
                   for _, a in r.iterrows()]}
json.dump(gj, open(out / f"{pre}_receptors.geojson", "w"))
np.savez_compressed(out / f"{pre}_receptor_daily.npz", ids=r.id.values, stack=rr["stack"])

# ---- summary
inrange_r = (r.annual_hours_noocc > 0).sum()
S = dict(runtime_grid_s=t_grid, runtime_total_s=time.perf_counter() - T0, peak_rss_mb=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
         n_cells=int(grid.nrows * grid.ncols), n_cells_inrange=int(inr.sum()), n_receptors=len(r), receptors_with_flicker_noocc=int(inrange_r),
         receptors_with_flicker_occ=int((r.annual_hours > 0).sum()),
         over_30h_occ=int(r.flag_30h.sum()), over_30h_noocc=int(r.flag_30h_noocc.sum()),
         over_30min_occ=int(r.flag_30min.sum()), over_30min_noocc=int(r.flag_30min_noocc.sum()),
         either_occ=int((r.flag_30h | r.flag_30min).sum()), either_noocc=int((r.flag_30h_noocc | r.flag_30min_noocc).sum()),
         grid_area_over_30h_ha_occ=float((H > thr_h).sum() * res * res / 1e4), grid_area_over_30h_ha_noocc=float((Hf > thr_h).sum() * res * res / 1e4),
         grid_total_hours_ratio_occ_over_noocc=float(H.sum() / Hf.sum()), turbines=[t.id for t in turbines], lat=lat, lon=lon)
json.dump(S, open(out / f"{pre}_summary.json", "w"), indent=1)
print(json.dumps(S, indent=1))
print(r.sort_values("annual_hours", ascending=False).head(10)[["id", "annual_hours", "max_daily_min", "days_gt30min", "annual_hours_noocc", "max_daily_min_noocc"]])
