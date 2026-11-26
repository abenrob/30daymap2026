#!/usr/bin/env python3
"""
Day 26 Water: download the Sentinel-1 stack for the Garonne from Agen to Bordeaux.

Every Sentinel-1 GRD pass over the reach (flood window + a dry reference window) is opened
from ESA's EOPF Zarr in xarray-eopf "analysis mode" (calibrated, terrain-corrected onto an
IGN RGE ALTI grid in Lambert-93) and saved as one small netCDF per item.

Resumable: rerun the same command and it skips what is already done.
Retries: each failed item is retried up to --max-attempts times, across rounds, with backoff.

Setup (once, from work/day-26-water):
    python3 -m venv .venv
    .venv/bin/pip install "xarray<2025.10" "zarr<3" xarray-eopf rioxarray pystac-client requests netCDF4 shapely pyproj

Run:
    .venv/bin/python 10_download_agen_bordeaux.py              # full run
    .venv/bin/python 10_download_agen_bordeaux.py --limit 2    # quick test on 2 items
    .venv/bin/python 10_download_agen_bordeaux.py --status     # progress summary, no downloading

Lessons from the Tonneins run that this script handles:
  - Opening several products in parallel in one process collides on xarray-eopf's temporary
    files (ContainsGroupError). Workers here are separate processes, each in its own temp dir;
    any collision that still happens is retried.
  - Some assets have broken links at EODC (FileNotFoundError). Retried, then marked failed.
  - xarray-eopf 0.3.1 needs zarr < 3, and zarr 2 needs xarray < 2025.10 (pinned above).
  - xarray-eopf leaves tmp_* folders behind; each worker cleans its own up.
  - Slices that only clip a corner of the area crash the reader (IndexError in
    _sample_array_at_indices). They are dropped, and every pass is read only over its own
    footprint (also faster). Output grids are subsets of one 50 m Lambert-93 lattice.
  - netCDF is written with engine="netcdf4" (the scipy backend cannot compress).
  - Only VV is kept (VH was never used), stored as int16 dB x 100, compressed.
"""
import argparse, json, os, shutil, sys, tempfile, time, traceback, warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone

# ---------------------------------------------------------------- settings
BBOX_LONLAT = [-0.70, 44.12, 0.72, 44.95]       # Agen (0.62E) to Bordeaux (-0.58E), Garonne corridor
FLOOD_WINDOW = "2026-01-25/2026-03-10"           # crest moved down the reach ~10-20 Feb
REF_WINDOW = "2025-08-15/2025-10-15"             # dry autumn reference
REF_DATES_PER_ORBIT = 4                          # reference passes kept per relative orbit
STAC = "https://stac.core.eopf.eodc.eu"
COLLECTION = "sentinel-1-l1-grd"
CRS = 2154
MIN_OVERLAP = 0.05          # slices covering <5% of the area crash xarray-eopf (IndexError) and add nothing
EDGE_INSET_M = 500          # grid is cropped to the slice footprint, pulled in by this much

HERE = os.path.dirname(os.path.abspath(__file__))


def log(msg):
    line = f"{datetime.now():%H:%M:%S} {msg}"
    print(line, flush=True)
    with open(os.path.join(OUT, "download.log"), "a") as f:
        f.write(line + "\n")


# ---------------------------------------------------------------- DEM / output grid
def build_dem(res):
    """IGN RGE ALTI from the Geoplateforme WMS-R, fetched in <=2000 px tiles and mosaicked.
    Its grid becomes the output grid for every pass."""
    path = os.path.join(OUT, f"dem_{res}m.tif")
    if os.path.exists(path):
        return path
    import numpy as np, requests, rasterio
    from rasterio.transform import from_origin
    from pyproj import Transformer
    t = Transformer.from_crs(4326, CRS, always_xy=True)
    xs, ys = zip(*[t.transform(x, y) for x in BBOX_LONLAT[0::2] for y in BBOX_LONLAT[1::2]])
    x0, x1 = (min(xs) // res) * res, (max(xs) // res + 1) * res
    y0, y1 = (min(ys) // res) * res, (max(ys) // res + 1) * res
    W, H = int((x1 - x0) / res), int((y1 - y0) / res)
    log(f"DEM grid {W} x {H} px at {res} m, Lambert-93 {x0:.0f},{y0:.0f},{x1:.0f},{y1:.0f}")
    dem = np.full((H, W), np.nan, dtype="float32")
    T = 2000
    for r0 in range(0, H, T):
        for c0 in range(0, W, T):
            h, w = min(T, H - r0), min(T, W - c0)
            bx0, by1 = x0 + c0 * res, y1 - r0 * res
            bbox = f"{bx0},{by1 - h * res},{bx0 + w * res},{by1}"
            for attempt in range(5):
                try:
                    r = requests.get("https://data.geopf.fr/wms-r", timeout=180, params=dict(
                        SERVICE="WMS", VERSION="1.3.0", REQUEST="GetMap",
                        LAYERS="ELEVATION.ELEVATIONGRIDCOVERAGE", STYLES="", CRS=f"EPSG:{CRS}",
                        BBOX=bbox, WIDTH=w, HEIGHT=h, FORMAT="image/geotiff"))
                    r.raise_for_status()
                    with rasterio.MemoryFile(r.content) as mf, mf.open() as src:
                        dem[r0:r0 + h, c0:c0 + w] = src.read(1)
                    break
                except Exception as e:
                    log(f"  DEM tile {r0},{c0} attempt {attempt + 1} failed: {e!r:.120}")
                    time.sleep(10 * (attempt + 1))
            else:
                sys.exit("DEM tile kept failing; rerun later.")
    dem[dem < -100] = np.nan
    with rasterio.open(path, "w", driver="GTiff", width=W, height=H, count=1, dtype="float32",
                       crs=f"EPSG:{CRS}", transform=from_origin(x0, y1, res, res),
                       compress="deflate") as dst:
        dst.write(dem, 1)
    log(f"DEM saved: {path}")
    return path


# ---------------------------------------------------------------- STAC search
def search():
    path = os.path.join(OUT, "items.json")
    if os.path.exists(path):
        return json.load(open(path))
    from pystac_client import Client
    from shapely.geometry import shape, mapping, box
    AREA = box(*BBOX_LONLAT)
    cat = Client.open(STAC)
    items = []
    for name, dt in [("flood", FLOOD_WINDOW), ("ref", REF_WINDOW)]:
        for it in cat.search(collections=[COLLECTION], bbox=BBOX_LONLAT, datetime=dt).items():
            p = it.properties
            g = shape(it.geometry)
            items.append(dict(set=name, id=it.id, datetime=p["datetime"],
                              orbit=p.get("sat:relative_orbit"), direction=p.get("sat:orbit_state"),
                              href=it.assets["product"].href, geometry=mapping(g),
                              overlap=round(g.intersection(AREA).area / AREA.area, 4)))
    # keep only REF_DATES_PER_ORBIT reference dates per orbit (all slices of those dates)
    keep = []
    by_orbit = {}
    for it in sorted(items, key=lambda i: i["datetime"]):
        if it["set"] == "ref":
            d = it["datetime"][:10]
            dates = by_orbit.setdefault(it["orbit"], [])
            if d not in dates:
                if len(dates) >= REF_DATES_PER_ORBIT:
                    continue
                dates.append(d)
        keep.append(it)
    small = [i for i in keep if i["overlap"] < MIN_OVERLAP]
    keep = [i for i in keep if i["overlap"] >= MIN_OVERLAP]
    if small:
        log(f"STAC: skipped {len(small)} slices that only clip a corner of the area (<{MIN_OVERLAP:.0%})")
    json.dump(keep, open(path, "w"), indent=1)
    from collections import Counter
    log(f"STAC: {len(keep)} items  " + str(dict(Counter((i['set'], i['orbit']) for i in keep))))
    return keep


# ---------------------------------------------------------------- one item (runs in a worker process)
def fetch_one(item, dem_path, out_dir):
    """Open one GRD product on the DEM grid and save VV as int16 dB*100. Returns (id, ok, msg)."""
    warnings.filterwarnings("ignore")
    work = tempfile.mkdtemp(prefix="eopf_", dir=out_dir)   # private cwd: xarray-eopf writes tmp_* here
    old = os.getcwd()
    try:
        os.chdir(work)
        import numpy as np, xarray as xr, rioxarray
        from shapely.geometry import shape, box
        from shapely.ops import transform as shp_transform
        from pyproj import Transformer
        tr = Transformer.from_crs(4326, CRS, always_xy=True).transform
        foot = shp_transform(tr, shape(item["geometry"]).intersection(box(*BBOX_LONLAT))).buffer(-EDGE_INSET_M)
        if foot.is_empty:
            return item["id"], True, "skipped: no overlap after inset"
        bx0, by0, bx1, by1 = foot.bounds
        dem = rioxarray.open_rasterio(dem_path).squeeze("band", drop=True)
        dem = dem.sel(x=slice(bx0, bx1), y=slice(by1, by0)).rio.write_crs(CRS)
        dem.name = "dem"
        t0 = time.time()
        ds = xr.open_dataset(item["href"], engine="eopf-zarr", dem=dem, variables=["vv"],
                             apply_rtc=False, chunks={})
        vv = ds[list(ds.data_vars)[0]].compute()
        db = 10 * np.log10(vv.where(vv > 0))
        valid = float(np.isfinite(db).mean())
        out = xr.Dataset({"vv_db100": (db * 100).round().fillna(-32768).astype("int16")},
                         coords={"x": db.x, "y": db.y})
        out.vv_db100.attrs.update(units="dB x 100 (-32768 = no data)",
                                  long_name="beta0 VV backscatter, calibrated + terrain-corrected (no RTC)")
        out.attrs.update({k: str(v) for k, v in item.items() if k != "href"})
        out.attrs["href"] = item["href"]
        out.attrs["valid_fraction"] = valid
        f = os.path.join(out_dir, "passes", item["id"] + ".nc")
        out.to_netcdf(f + ".tmp", engine="netcdf4", encoding={"vv_db100": {"zlib": True, "complevel": 4}})
        os.replace(f + ".tmp", f)
        return item["id"], True, f"{time.time() - t0:.0f}s, {valid:.0%} of grid covered"
    except Exception as e:
        tmp = os.path.join(out_dir, "passes", item["id"] + ".nc.tmp")
        if os.path.exists(tmp):
            os.remove(tmp)
        return item["id"], False, f"{type(e).__name__}: {str(e)[:300]}"
    finally:
        os.chdir(old)
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------- state
def load_state():
    p = os.path.join(OUT, "state.json")
    return json.load(open(p)) if os.path.exists(p) else {}


def save_state(s):
    p = os.path.join(OUT, "state.json")
    json.dump(s, open(p + ".tmp", "w"), indent=1)
    os.replace(p + ".tmp", p)


def status(items, state):
    done = [i for i in items if os.path.exists(os.path.join(OUT, "passes", i["id"] + ".nc"))]
    failed = [i for i in items if state.get(i["id"], {}).get("status") == "failed"]
    todo = len(items) - len(done) - len(failed)
    print(f"{len(done)} done, {len(failed)} failed for good, {todo} to do, of {len(items)} items")
    for i in failed:
        print(f"  FAILED {i['id']}: {state[i['id']].get('error', '')[:150]}")


# ---------------------------------------------------------------- main
def main():
    global OUT
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(HERE, "agen-bordeaux"))
    ap.add_argument("--res", type=int, default=50, help="output pixel size in metres (default 50)")
    ap.add_argument("--workers", type=int, default=2, help="parallel processes (default 2; use 1 if errors pile up)")
    ap.add_argument("--max-attempts", type=int, default=5, help="attempts per item before giving up")
    ap.add_argument("--limit", type=int, default=0, help="only process the first N flood items (testing)")
    ap.add_argument("--retry-failed", action="store_true", help="reset items previously marked failed")
    ap.add_argument("--status", action="store_true", help="print progress and exit")
    a = ap.parse_args()
    OUT = a.out
    os.makedirs(os.path.join(OUT, "passes"), exist_ok=True)

    items = search()
    state = load_state()
    if a.status:
        status(items, state); return
    if a.retry_failed:
        for k, v in state.items():
            if v.get("status") == "failed":
                v.update(status="pending", attempts=0)
        save_state(state)
    dem_path = build_dem(a.res)
    if a.limit:
        items = [i for i in items if i["set"] == "flood"][:a.limit]

    def todo():
        return [i for i in items
                if not os.path.exists(os.path.join(OUT, "passes", i["id"] + ".nc"))
                and state.get(i["id"], {}).get("status") != "failed"]

    started = time.time()
    rnd = 0
    while todo():
        rnd += 1
        batch = todo()
        log(f"round {rnd}: {len(batch)} items, {a.workers} worker(s)")
        n_ok = 0
        with ProcessPoolExecutor(a.workers) as ex:
            futs = {ex.submit(fetch_one, it, dem_path, OUT): it for it in batch}
            for k, fut in enumerate(as_completed(futs), 1):
                it = futs[fut]
                try:
                    iid, ok, msg = fut.result()
                except Exception as e:                       # worker crashed outright
                    iid, ok, msg = it["id"], False, f"worker crash: {e!r:.300}"
                s = state.setdefault(iid, {"attempts": 0})
                s["attempts"] = s.get("attempts", 0) + 1
                if ok:
                    s.update(status="done", error="")
                    n_ok += 1
                    log(f"  ok   [{k}/{len(batch)}] {iid[:62]}  {msg}")
                else:
                    s["error"] = msg
                    deterministic = msg.startswith("IndexError")   # reader bug on edge slivers: retrying never helps
                    s["status"] = "failed" if (s["attempts"] >= a.max_attempts or deterministic) else "pending"
                    tag = "GAVE UP" if s["status"] == "failed" else f"retry later ({s['attempts']}/{a.max_attempts})"
                    log(f"  FAIL [{k}/{len(batch)}] {iid[:62]}  {tag}: {msg[:160]}")
                save_state(state)
        left = len(todo())
        log(f"round {rnd} done: {n_ok} ok, {left} still to retry. Elapsed {(time.time() - started) / 60:.0f} min")
        if left:
            wait = min(300, 30 * rnd)
            log(f"waiting {wait}s before retrying")
            time.sleep(wait)
    for d in os.listdir(OUT):                                # leftovers from crashed workers
        if d.startswith("eopf_"):
            shutil.rmtree(os.path.join(OUT, d), ignore_errors=True)
    log("finished")
    status(items, state)


if __name__ == "__main__":
    main()
