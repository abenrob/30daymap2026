"""Re-run the Marsanne model (horizon cache reused) and save per-minute flicker flags.
Output outputs/marsanne_minute_flags.npz (arrays indexed like the daylight sun vectors of compute_sun):
  any_zone  : some grid cell flickers in that minute
  far500    : some cell > 500 m from the turbine causing it flickers
  any_dwelling : some dwelling flickers;  rec_pairs: (receptor index, minute index) pairs
"""
import sys, json, time
from pathlib import Path
import numpy as np, yaml, pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.solar import compute_sun
from src.geometry import Turbine
from src.terrain import DEM, horizon_table, HorizonOcclusion
from src.flicker import Grid, FlickerParams, compute_points
cfg = yaml.safe_load(open(ROOT / "config.yaml")); pr = cfg["params"]; pre = cfg["site_run"]["out_prefix"]; out = ROOT / "outputs"
S = json.load(open(out / f"{pre}_summary.json"))
dem = DEM(ROOT / cfg["dem"]["path"]); res = dem.res
turbines = [Turbine(**d) for d in json.load(open(out / f"{pre}_turbines_used.json"))]
st = np.load(out / f"{pre}_stack.npz"); stack_old = st["stack"]
grid = Grid(xmin=float(st["xmin"]), ymax=float(st["ymax"]), res=res, nrows=stack_old.shape[1], ncols=stack_old.shape[2], crs=cfg["site"]["crs"])
c0 = int(round((grid.xmin - dem.xmin) / res)); r0 = int(round((dem.ymax - grid.ymax) / res))
grid.z = dem.z[r0:r0 + grid.nrows, c0:c0 + grid.ncols].copy()
sun = compute_sun(S["lat"], S["lon"], cfg["time"]["year"], 1, pr["min_sun_elevation_deg"], cfg["site"]["crs"])
params = FlickerParams(pr["max_distance_diameters"], pr["observer_height_m"], pr["chunk_cells"])
X, Y = grid.centres(); P = np.column_stack([X.ravel(), Y.ravel(), (grid.z + params.observer_height).ravel()])
inr = np.zeros(len(P), bool)
for t in turbines:
    inr |= np.linalg.norm(P - t.nominal_hub, axis=1) <= params.max_distance_diameters * t.rotor_diameter + t.overhang
hid = np.nonzero(inr)[0]; hz = cfg["site_run"]["horizon"]; cache = ROOT / "data" / "cache"
tab = horizon_table(dem, P[hid, 0], P[hid, 1], P[hid, 2], hz["azimuth_bins"], hz["max_distance_m"], cache, "grid")
pmap = np.full(len(P), -1, np.int32); pmap[hid] = np.arange(hid.size)
t0 = time.time()
rg = compute_points(P, turbines, sun, params, occlusion=HorizonOcclusion(tab, pmap, sun), flags=True, far_m=500.0)
print(f"grid rerun {time.time()-t0:.0f}s; stack identical to previous: {np.array_equal(rg['stack'].reshape(stack_old.shape), stack_old)}")
rec = pd.read_csv(out / f"{pre}_receptors.csv")
PR = np.column_stack([rec.x, rec.y, rec.z]); tabr = horizon_table(dem, PR[:, 0], PR[:, 1], PR[:, 2], hz["azimuth_bins"], hz["max_distance_m"], cache, "rec")
rr = compute_points(PR, turbines, sun, params, occlusion=HorizonOcclusion(tabr, np.arange(len(PR), dtype=np.int32), sun), flags=True, collect_pairs=True, verbose=False)
np.savez_compressed(out / f"{pre}_minute_flags.npz", any_zone=rg["flag_any"], far500=rg["flag_far"], any_dwelling=rr["flag_any"], rec_pairs=rr["pairs"],
                    day=sun.day, az=sun.az_true_deg, el=sun.el_deg)
n = len(sun.day)
print(f"daylight minutes {n}: any_zone {rg['flag_any'].sum()} ({100*rg['flag_any'].mean():.1f}%), far500 {rg['flag_far'].sum()} ({100*rg['flag_far'].mean():.1f}%), "
      f"any_dwelling {rr['flag_any'].sum()} ({100*rr['flag_any'].mean():.2f}%), pairs {len(rr['pairs'])}")
