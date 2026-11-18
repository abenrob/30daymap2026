"""Brute-force per-minute check (with terrain occlusion by independent 5 m ray-march) vs model outputs."""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd, rasterio, yaml
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.solar import compute_sun
from src.geometry import Turbine, brute_force_hit
from src.terrain import DEM, ray_blocked

cfg = yaml.safe_load(open(ROOT / "config.yaml")); pr = cfg["params"]; pre = cfg["site_run"]["out_prefix"]
out = ROOT / "outputs"
S = json.load(open(out / f"{pre}_summary.json"))
dem = DEM(ROOT / cfg["dem"]["path"])
turbines = [Turbine(**d) for d in json.load(open(out / f"{pre}_turbines_used.json"))]
sun = compute_sun(S["lat"], S["lon"], cfg["time"]["year"], 1, pr["min_sun_elevation_deg"], cfg["site"]["crs"])
maxd = [pr["max_distance_diameters"] * t.rotor_diameter for t in turbines]

def brute_day(p, day):
    m = np.nonzero(sun.day == day)[0]
    hit = np.zeros(m.size, bool)
    for t, md in zip(turbines, maxd):
        hit |= brute_force_hit(np.tile(p, (m.size, 1)), sun.vec[m], t.hub_xyz(sun.az_grid[m]), t.R, md)
    mh = m[hit]
    blk = ray_blocked(dem, p, sun.az_grid[mh], np.deg2rad(sun.el_deg[mh]), step=5.0)
    return int(hit.sum()), int((~blk).sum())     # (free, occluded)

rng = np.random.default_rng(7)
rows = []
# receptors
rec = pd.read_csv(out / f"{pre}_receptors.csv")
rd = np.load(out / f"{pre}_receptor_daily.npz", allow_pickle=True)
ids = list(rd["ids"])
for _, a in rec[rec.annual_hours_noocc > 0].iterrows():
    k = ids.index(a.id); p = np.array([a.x, a.y, a.z])
    dsel = {int(np.argmax(rd["stack"][:, k]))} | set(rng.integers(0, 365, 3).tolist())
    for d in dsel:
        f, o = brute_day(p, d)
        rows.append(("receptor " + a.id[-6:], d, f, o, int(rd["stack"][d, k])))
# grid cells: biggest occlusion effect + random affected + random unaffected
with rasterio.open(out / f"{pre}_annual_hours.tif") as ds: H = ds.read(1); tf = ds.transform
with rasterio.open(out / f"{pre}_annual_hours_noocc.tif") as ds: Hf = ds.read(1)
diff = Hf - H
st = np.load(out / f"{pre}_stack.npz")["stack"]
cells = [np.unravel_index(i, diff.shape) for i in np.argsort(diff.ravel())[-4:]]
aff = np.argwhere(diff > 5); cells += [tuple(aff[i]) for i in rng.choice(len(aff), 4, replace=False)]
unaff = np.argwhere((H > 5) & (diff == 0)); cells += [tuple(unaff[i]) for i in rng.choice(len(unaff), 3, replace=False)]
for (r, c) in cells:
    x = tf.c + (c + 0.5) * tf.a; y = tf.f + (r + 0.5) * tf.e
    p = np.array([x, y, float(dem.sample(x, y)) + pr["observer_height_m"]])
    dsel = {int(np.argmax(st[:, r, c]))} | set(rng.integers(0, 365, 3).tolist())
    for d in dsel:
        f, o = brute_day(p, d)
        rows.append((f"cell r{r} c{c} (dH={diff[r,c]:.0f}h)", d, f, o, int(st[d, r, c])))
df = pd.DataFrame(rows, columns=["point", "day", "brute_no_occ", "brute_occ", "model_occ"])
df["diff"] = df.model_occ - df.brute_occ
pd.set_option("display.width", 160); pd.set_option("display.max_rows", 200)
print(df.to_string())
print(f"\n{len(df)} checks; exact matches {(df['diff']==0).sum()}; max |diff| {df['diff'].abs().max()} min; "
      f"sum model {df.model_occ.sum()} vs brute {df.brute_occ.sum()} (unoccluded brute {df.brute_no_occ.sum()})")
df.to_csv(out / f"{pre}_spotcheck.csv", index=False)
