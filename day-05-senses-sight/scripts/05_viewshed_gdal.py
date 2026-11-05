"""Baseline: gdal_viewshed once per turbine on the same 50 m DEM, same observer, same eye height.

  gdal_viewshed -ox X -oy Y -oz TIP -tz 1.7 -md 20000 -cc CC dem_50m.tif out.tif

-cc is GDAL's curvature coefficient (1 - refraction coefficient), applied as d^2 / D * cc:
  --cc 0        flat earth, no curvature: like for like with the flat Blender scene
  --cc 0.85714  GDAL's default, curvature with standard 1/7 refraction: what flat-earth costs
  --cc 1        curvature, no refraction

Run from the workspace root:  python3 05_viewshed_gdal.py [--cc 0] [--limit N] [--gdal /path/to/gdal_viewshed]
On a Mac with QGIS: --gdal /Applications/QGIS.app/Contents/MacOS/bin/gdal_viewshed (or brew install gdal).
Output: work/data/day-05-sight/renders/gdal_cc<CC>/<turbine id>.tif and timings.json
"""
import argparse, json, os, subprocess, time

p = argparse.ArgumentParser()
p.add_argument("--cc", default="0")
p.add_argument("--limit", type=int)
p.add_argument("--gdal", default="gdal_viewshed")
a = p.parse_args()

D = "work/data/day-05-sight"
OUT = f"{D}/renders/gdal_cc{a.cc}"
os.makedirs(OUT, exist_ok=True)
meta = json.load(open(f"{D}/blender/meta.json"))
turbines = json.load(open(f"{D}/blender/turbines.json"))[:a.limit]

times = []
for i, t in enumerate(turbines):
    cmd = [a.gdal, "-q", "-ox", str(t["x"]), "-oy", str(t["y"]), "-oz", str(t["tip_m"]),
           "-tz", str(meta["eye_m"]), "-md", str(meta["range_m"]), "-cc", a.cc,
           "-vv", "255", "-iv", "0", "-ov", "0",
           f"{D}/derived/dem_50m.tif", f"{OUT}/{t['id']}.tif"]
    t0 = time.time()
    subprocess.run(cmd, check=True)
    times.append(time.time() - t0)
    print(f"{i + 1}/{len(turbines)} {t['id']} {times[-1]:.2f} s")

v = subprocess.run([a.gdal, "--version"], capture_output=True, text=True).stdout.strip()
json.dump(dict(gdal=v, cc=a.cc, n=len(turbines), times_s=times, total_s=sum(times)),
          open(f"{OUT}/timings.json", "w"), indent=1)
print(f"{v}: {len(times)} runs, total {sum(times):.1f} s, median {sorted(times)[len(times) // 2]:.2f} s")
