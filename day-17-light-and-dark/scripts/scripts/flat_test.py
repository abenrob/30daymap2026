"""Flat-terrain test: single generic turbine, +-10 D grid, full year at 1-min steps."""
import sys, time, resource
from pathlib import Path
import numpy as np, yaml
from pyproj import Transformer, Geod, CRS
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.solar import compute_sun, grid_convergence_deg
from src.geometry import Turbine, brute_force_hit
from src.flicker import Grid, FlickerParams, compute_flicker, annual_hours, max_daily_minutes, days_over
from src.io import write_geotiff, save_stack
from src.plots import map_plot

cfg = yaml.safe_load(open(ROOT / "config.yaml"))
out = ROOT / "outputs"; out.mkdir(exist_ok=True)
lat, lon, crs = cfg["site"]["lat"], cfg["site"]["lon"], cfg["site"]["crs"]
pr, dt = cfg["params"], cfg["default_turbine"]
T0 = time.perf_counter()

# --- check grid convergence sign with a geodesic walk
conv = grid_convergence_deg(lat, lon, crs)
tr = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
lo2, la2, _ = Geod(ellps="WGS84").fwd(lon, lat, 0.0, 200.0)      # 200 m due true north
x1, y1 = tr.transform(lon, lat); x2, y2 = tr.transform(lo2, la2)
grid_bearing = np.degrees(np.arctan2(x2 - x1, y2 - y1))
print(f"grid convergence {conv:.3f} deg; true-north walk has grid bearing {grid_bearing:.3f} (expect {-conv:.3f})")
assert abs(grid_bearing + conv) < 0.01

tx, ty = tr.transform(lon, lat)
tx, ty = round(tx / 5) * 5.0, round(ty / 5) * 5.0     # snap so turbine sits on a cell corner
turb = Turbine("T1", tx, ty, 0.0, dt["hub_height_m"], dt["rotor_diameter_m"], dt["overhang_m"])
D = turb.rotor_diameter; res = cfg["grid"]["resolution_m"]
half = cfg["grid"]["flat_test_extent_diameters"] * D
n = int(round(2 * half / res))
grid = Grid(xmin=tx - half, ymax=ty + half, res=res, nrows=n, ncols=n, crs=crs)

sun = compute_sun(lat, lon, cfg["time"]["year"], cfg["time"]["step_minutes"], pr["min_sun_elevation_deg"], crs)
print(f"sun: {sun.vec.shape[0]} daylight minutes, max elevation {sun.el_deg.max():.2f} deg, ndays {sun.ndays}, "
      f"solar setup {time.perf_counter()-T0:.1f}s")

params = FlickerParams(pr["max_distance_diameters"],
                       pr["observer_height_m"], pr["chunk_cells"])
t1 = time.perf_counter()
stack = compute_flicker(grid, [turb], sun, params)
t_model = time.perf_counter() - t1
hours = annual_hours(stack); mx = max_daily_minutes(stack); nd = days_over(stack, cfg["thresholds"]["daily_minutes"])

# --- outputs
write_geotiff(out / "flat_annual_hours.tif", hours, grid, nodata=-1)
write_geotiff(out / "flat_max_daily_minutes.tif", mx, grid, nodata=0, dtype="uint16")
write_geotiff(out / "flat_days_over_30min.tif", nd, grid, nodata=None, dtype="uint16")
save_stack(out / "flat_stack.npz", stack, grid, cfg["time"]["year"], cfg["time"]["step_minutes"])
map_plot(out / "flat_annual_hours.png", hours, grid, tx, ty, cfg["thresholds"]["annual_hours"],
         "Flicker hours per year", f"Worst-case annual shadow flicker, flat terrain\nHub {turb.hub_height:g} m, D {D:g} m, {cfg['time']['year']}, lat {lat}")
map_plot(out / "flat_max_daily_minutes.png", mx.astype(float), grid, tx, ty, cfg["thresholds"]["daily_minutes"],
         "Max flicker minutes in a day", "Worst-case maximum daily shadow flicker, flat terrain", cmap="PuRd")

# --- results
X, Y = grid.centres(); dx, dy = X - tx, Y - ty
rh = np.hypot(dx, dy)
i = np.unravel_index(hours.argmax(), hours.shape)
print(f"\nPEAK annual hours {hours.max():.1f} h at ({dx[i]:.0f} E, {dy[i]:.0f} N) m, dist {rh[i]:.0f} m")
print(f"PEAK daily minutes {mx.max()}")
z30 = hours >= 30
print(f"30 h/yr zone: {z30.sum()*res*res/1e4:.1f} ha, max distance {rh[z30].max():.0f} m, "
      f"N extent {dy[z30].max():.0f} / S extent {dy[z30].min():.0f}, E {dx[z30].max():.0f} / W {dx[z30].min():.0f}")
z30d = mx >= 30
print(f"30 min/day zone: {z30d.sum()*res*res/1e4:.1f} ha, max distance {rh[z30d].max():.0f} m")
print(f"any flicker: {(hours>0).sum()*res*res/1e4:.1f} ha, max dist {rh[hours>0].max():.0f} m")

# --- sanity checks
maxd = params.max_distance_diameters * D
assert hours[rh > maxd + turb.overhang].max() == 0, "flicker beyond max distance"
print(f"[ok] no flicker beyond {maxd:.0f} m (10 D)")

# cells due south of the tower: the sun (az ~180) and the hub (az 0) are on opposite sides of the cell, so the
# angular separation is 180 - alpha - el_sun (alpha = hub elevation seen from the cell). Where that exceeds the
# rotor cap the model must give zero.
south_line = (np.abs(dx) <= 15) & (dy < 0)
d3 = np.sqrt(rh**2 + (turb.hub_height - params.observer_height) ** 2)
alpha = np.degrees(np.arctan2(turb.hub_height - params.observer_height, rh))
theta = np.degrees(np.arcsin(np.minimum(1, (turb.R + turb.overhang) / d3)))
bound = south_line & ((180 - alpha - sun.el_deg.max() - theta) > 2.0)
print(f"due-south line: {south_line.sum()} cells, analytically zero-flicker: {bound.sum()}, max hours there {hours[bound].max():.2f}; "
      f"max hours on the whole line {hours[south_line].max():.1f} (only within r<{rh[south_line & (hours>0)].max():.0f} m of tower)")
assert bound.sum() > 0 and hours[bound].max() == 0
print("[ok] zero flicker where sun and hub are on opposite sides of the receptor (due south)")
# cells directly under/near tower base: only reachable by high sun; report
base = rh < 20
print(f"cells within 20 m of tower base: hours min/max {hours[base].min():.1f}/{hours[base].max():.1f} (sphere model: sun within ~40 deg of vertical)")

xm = hours[:, ::-1]
corr = np.corrcoef(hours.ravel(), xm.ravel())[0, 1]
west, east = hours[:, : n // 2].sum(), hours[:, n // 2:].sum()
north, south = hours[: n // 2].sum(), hours[n // 2:].sum()
print(f"E-W symmetry: mirror corr {corr:.4f}, west/east total {west/east:.3f}; north share {north/(north+south):.3f}, south share {south/(north+south):.3f}")
assert corr > 0.97 and 0.9 < west / east < 1.1
assert south < north
print("[ok] roughly E-W symmetric, mostly north of turbine")

# --- brute-force verification
rng = np.random.default_rng(1)
cand = np.argwhere(hours > 0)
pick = cand[rng.choice(len(cand), 10, replace=False)]
pick = np.vstack([pick, np.argwhere((hours == 0) & (rh < maxd))[rng.choice(((hours == 0) & (rh < maxd)).sum(), 3, replace=False)]])
days = [0, 79, 172, 264, 355] + list(rng.integers(0, sun.ndays, 3))
bad = 0; tot = 0
for (r, c) in pick:
    p = np.array([X[r, c], Y[r, c], params.observer_height])
    for dday in days:
        m = np.nonzero(sun.day == dday)[0]
        hubs = turb.hub_xyz(sun.az_grid[m])
        hit = brute_force_hit(np.tile(p, (m.size, 1)), sun.vec[m], hubs, turb.R, maxd)
        bt, mdl = int(hit.sum()) * sun.step_minutes, int(stack[dday, r, c])
        tot += 1; bad += bt != mdl
        if bt != mdl: print(f"MISMATCH cell {(r,c)} day {dday}: brute {bt} model {mdl}")
print(f"[brute-force] {len(pick)} cells x {len(days)} days = {tot} checks, mismatches: {bad}")
assert bad == 0

print(f"\nmodel runtime {t_model:.1f}s (total {time.perf_counter()-T0:.1f}s), stack {stack.nbytes/1e6:.0f} MB, "
      f"peak RSS {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024:.0f} MB")
