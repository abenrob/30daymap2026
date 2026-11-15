#!/usr/bin/env python3
"""
Step 2: check the DEM, find where the seafloor data is trustworthy, crop to it, and write
terrain.npz for Blender plus a preview image.

Usage:
    python 02_prepare.py                       # report + preview only; writes terrain.npz for the full area
    python 02_prepare.py --auto-crop           # trim ocean edges that are mostly gap-fill, then write
    python 02_prepare.py --crop -122.6 36.05 -121.0 37.0     # manual crop (lon/lat W S E N)
    python 02_prepare.py --preset none         # skip the Monterey landmark checks (other regions)

What "good data" means here: land (USGS NED via GMRT) always counts as good. Ocean cells count as
good if GMRT marks them as multibeam (surveyed_utm.tif) or they are shallower than --shallow m
(GMRT's mask is patchy right at the shoreline). Everything else is coarse GEBCO gap-fill.

Outputs: data/terrain.npz (elev m, surveyed 0/1, grid metadata) and data/preview.png.
There is no inversion here: terrain.npz keeps ORIGINAL elevations; Blender negates them.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.fill import fillnodata
from rasterio.warp import transform

# --- Monterey checks -------------------------------------------------------------------------
# Junipero Serra Peak (Santa Lucia Range) is the highest point in the default area.
PEAK = ("Junipero Serra Peak", -121.4222, 36.1439, 1788, 90)
MOSS_LANDING = (-121.787, 36.804)   # canyon head
# ---------------------------------------------------------------------------------------------


def hillshade(z, cell, az_deg=315, alt_deg=35, ve=2.0):
    gy, gx = np.gradient(z * ve, cell)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    az, alt = np.radians(360 - az_deg + 90), np.radians(alt_deg)
    return np.clip(np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect), 0, 1)


def ocean_coverage(good, ocean, r0, r1, c0, c1):
    o = ocean[r0:r1, c0:c1]
    n = o.sum()
    return 1.0 if n == 0 else float((good[r0:r1, c0:c1] & o).sum() / n)


def auto_crop(good, ocean, thr, min_frac=0.5, step_frac=0.01):
    """Greedy: repeatedly trim the side whose removal raises ocean-data coverage most per area lost."""
    ny, nx = good.shape
    r0, r1, c0, c1 = 0, ny, 0, nx
    sy, sx = max(1, int(ny * step_frac)), max(1, int(nx * step_frac))
    while ocean_coverage(good, ocean, r0, r1, c0, c1) < thr:
        base = ocean_coverage(good, ocean, r0, r1, c0, c1)
        area = (r1 - r0) * (c1 - c0)
        cands = []
        if r1 - r0 - sy > min_frac * ny:
            cands += [("N", (r0 + sy, r1, c0, c1)), ("S", (r0, r1 - sy, c0, c1))]
        if c1 - c0 - sx > min_frac * nx:
            cands += [("W", (r0, r1, c0 + sx, c1)), ("E", (r0, r1, c0, c1 - sx))]
        if not cands:
            return (r0, r1, c0, c1), False
        best, best_score = None, -1.0
        for _, (a, b, c, d) in cands:
            cov = ocean_coverage(good, ocean, a, b, c, d)
            lost = 1 - (b - a) * (d - c) / area
            score = (cov - base) / max(lost, 1e-9)
            if score > best_score:
                best, best_score = (a, b, c, d), score
        if best_score <= 0:
            return (r0, r1, c0, c1), False
        r0, r1, c0, c1 = best
    return (r0, r1, c0, c1), True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dem", default="data/dem_utm.tif")
    ap.add_argument("--surveyed", default="data/surveyed_utm.tif")
    ap.add_argument("--out", default="data/terrain.npz")
    ap.add_argument("--preview", default=None)
    ap.add_argument("--auto-crop", action="store_true")
    ap.add_argument("--min-coverage", type=float, default=0.85, help="target share of ocean cells that are real data")
    ap.add_argument("--shallow", type=float, default=30.0, help="ocean shallower than this (m) counts as good")
    ap.add_argument("--crop", nargs=4, type=float, metavar=("W", "S", "E", "N"), help="lon/lat crop")
    ap.add_argument("--preset", choices=["monterey", "none"], default="monterey")
    args = ap.parse_args()

    with rasterio.open(args.dem) as src:
        z = src.read(1).astype(np.float32)
        t, crs = src.transform, src.crs
    sv = None
    if Path(args.surveyed).exists():
        with rasterio.open(args.surveyed) as src:
            sv = src.read(1)
    cell = float(t.a)
    if abs(t.a) != abs(t.e) or not crs.is_projected:
        sys.exit("DEM must be on a square metric grid (run 01_fetch_dem.py).")
    surveyed = (sv >= 0.5) if sv is not None else np.ones(z.shape, bool)

    nan = np.isnan(z)
    print(f"Grid {z.shape[1]} x {z.shape[0]} @ {cell:g} m  ({z.shape[1] * cell / 1000:.0f} x {z.shape[0] * cell / 1000:.0f} km), NaN {nan.mean():.2%}")
    if nan.all():
        sys.exit("DEM is entirely NaN.")
    if nan.any():  # small holes (e.g. cell edges after reprojection): interpolate from neighbours
        z = fillnodata(np.where(nan, 0, z), mask=(~nan).astype(np.uint8), max_search_distance=50)
        z[np.isnan(z)] = np.nanmin(z)

    # --- crop -------------------------------------------------------------------------------
    r0, r1, c0, c1 = 0, z.shape[0], 0, z.shape[1]
    ocean = z < 0
    good = (~ocean) | surveyed | (z > -args.shallow)
    cov = ocean_coverage(good, ocean, r0, r1, c0, c1)
    print(f"Ocean cells: {ocean.mean():.0%} of area; real survey data covers {cov:.0%} of them")
    if args.crop:
        w, s, e, n = args.crop
        xs, ys = transform("EPSG:4326", crs, [w, e, w, e], [s, s, n, n])
        c0 = max(0, int((min(xs) - t.c) // cell)); c1 = min(z.shape[1], int((max(xs) - t.c) // cell))
        r0 = max(0, int((t.f - max(ys)) // cell)); r1 = min(z.shape[0], int((t.f - min(ys)) // cell))
    elif args.auto_crop:
        (r0, r1, c0, c1), ok = auto_crop(good, ocean, args.min_coverage)
        print("Auto-crop " + ("reached" if ok else "could NOT reach") + f" {args.min_coverage:.0%} coverage")
    if (r0, r1, c0, c1) != (0, z.shape[0], 0, z.shape[1]):
        xs, ys = [t.c + c0 * cell, t.c + c1 * cell], [t.f - r1 * cell, t.f - r0 * cell]
        lon, lat = transform(crs, "EPSG:4326", xs, ys)
        print(f"Crop: lon {lon[0]:.3f} to {lon[1]:.3f}, lat {lat[0]:.3f} to {lat[1]:.3f}  "
              f"(--crop {lon[0]:.3f} {lat[0]:.3f} {lon[1]:.3f} {lat[1]:.3f})")
        z, good, surveyed, ocean = z[r0:r1, c0:c1], good[r0:r1, c0:c1], surveyed[r0:r1, c0:c1], ocean[r0:r1, c0:c1]
        t = t * rasterio.Affine.translation(c0, r0)
        print(f"After crop: {z.shape[1] * cell / 1000:.0f} x {z.shape[0] * cell / 1000:.0f} km, "
              f"ocean data coverage {ocean_coverage(good, ocean, 0, z.shape[0], 0, z.shape[1]):.0%}")

    zmin, zmax = float(z.min()), float(z.max())
    print(f"Elevation: min {zmin:.0f} m, max {zmax:.0f} m; ocean {ocean.mean():.0%} of the area")

    # --- checks: cheap sanity tests so a bad download fails here and not after an hour of rendering --------
    problems = []
    if zmax > 9000:
        problems.append(f"max {zmax:.0f} looks like FEET, not metres")
    if ocean.any():
        o = z[ocean]
        flat = float((np.abs(np.gradient(z)[0])[ocean] < 1e-3).mean())
        print(f"Flat (zero-gradient) ocean cells: {flat:.1%}")
        if flat > 0.05:
            problems.append(f"{flat:.0%} of ocean cells are perfectly flat: looks like a constant fill, not data")
    if args.preset == "monterey":
        if not (0.15 < ocean.mean() < 0.85):
            problems.append(f"ocean is {ocean.mean():.0%} of the area; expected a mix of land and sea")
        if zmin > -1000:
            problems.append(f"deepest point is only {zmin:.0f} m; the canyon should reach well below -1000 m in this area")
        name, lon, lat, expect, tol = PEAK
        x, y = transform("EPSG:4326", crs, [lon], [lat])
        c, r = ~t * (x[0], y[0])
        r, c = int(r), int(c)
        if 0 <= r < z.shape[0] and 0 <= c < z.shape[1]:
            win = z[max(r - 4, 0): r + 5, max(c - 4, 0): c + 5].max()
            print(f"{name}: {win:.0f} m near ({lon}, {lat}), expected ~{expect}")
            if abs(win - expect) > tol:
                problems.append(f"{name} {win:.0f} m, expected ~{expect} m (wrong units or crop?)")
            hr, hc = np.unravel_index(np.argmax(z), z.shape)
            lr, lc = np.unravel_index(np.argmin(z), z.shape)
            if not lc < hc:
                problems.append("deepest point is not west of the highest point (flipped raster?)")
        else:
            print(f"({name} is outside this crop; skipping that check)")
        x, y = transform("EPSG:4326", crs, [MOSS_LANDING[0]], [MOSS_LANDING[1]])
        c, r = ~t * (x[0], y[0])
        if 0 <= r < z.shape[0] and 0 <= c < z.shape[1]:
            k_ = int(10000 // cell)  # +-10 km window
            near = z[max(int(r) - k_, 0): int(r) + k_ + 1, max(int(c) - k_, 0): int(c) + k_ + 1]
            if not (near.min() < -50 and near.max() > 0):
                problems.append("no coastline near Moss Landing (north/south flipped, or wrong area?)")
    if problems:
        print("\nCHECKS FAILED:")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print("Checks passed.")

    # terrain.npz keeps the ORIGINAL elevations; the inversion happens in Blender as a shape key.
    # "surveyed" here means "good data" (real multibeam, land, or very shallow water).
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, elev=z, surveyed=good.astype(np.uint8), cell=np.float64(cell),
                        x0=np.float64(t.c), y0=np.float64(t.f), crs=str(crs))
    print(f"Wrote {out} ({out.stat().st_size / 1e6:.0f} MB)")

    # --- preview ----------------------------------------------------------------------------
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.colors import LinearSegmentedColormap
    except ImportError:
        print("matplotlib not installed: skipping preview.png")
        return
    k = max(1, int(max(z.shape) // 1100))
    zs, gs = z[::k, ::k], good[::k, ::k]
    land = [(0, "#c8bd8f"), (40, "#9aa862"), (400, "#b3a66c"), (1000, "#7d7f58"), (1600, "#8a7f72"), (2400, "#9a9894"), (3200, "#ffffff")]
    sea = [(0, "#8fd1c8"), (60, "#5fb3bd"), (300, "#3a86a8"), (1000, "#1f5a85"), (2000, "#123e68"), (3500, "#0a2547")]

    def cm(stops):
        lo, hi = stops[0][0], stops[-1][0]
        return LinearSegmentedColormap.from_list("c", [((v - lo) / (hi - lo), c) for v, c in stops]), lo, hi

    lc_, llo, lhi = cm(land)
    sc_, slo, shi = cm(sea)

    def color(zz):
        rgb = np.where((zz >= 0)[..., None], lc_(np.clip((zz - llo) / (lhi - llo), 0, 1))[..., :3],
                       sc_(np.clip((-zz - slo) / (shi - slo), 0, 1))[..., :3])
        return rgb

    fig, axes = plt.subplots(2, 2, figsize=(14, 14 * 2 * zs.shape[0] / zs.shape[1] / 2 + 1.0))
    for ax, sign, title in ((axes[0, 0], 1, "Original"), (axes[0, 1], -1, "Inverted (Z -> -Z): land is where the sea was")):
        zz = sign * zs
        rgb = color(zz)
        hs = hillshade(zz, cell * k)
        ax.imshow(np.clip(rgb * (0.45 + 0.75 * hs[..., None]), 0, 1))
        ax.contour(zz, levels=[0], colors="k", linewidths=0.6)
        ax.set_title(title)
        ax.axis("off")
    ax = axes[1, 0]
    q = np.where(zs < 0, np.where(gs, 1.0, 0.0), 0.5)
    ax.imshow(q, cmap=LinearSegmentedColormap.from_list("q", ["#d9534f", "#c9c9c9", "#2e8b57"]), vmin=0, vmax=1)
    ax.set_title("Data quality: green = real multibeam, red = coarse gap-fill ocean, grey = land")
    ax.axis("off")
    ax = axes[1, 1]
    lap = np.abs(zs[1:-1, 1:-1] * 4 - zs[:-2, 1:-1] - zs[2:, 1:-1] - zs[1:-1, :-2] - zs[1:-1, 2:])
    ax.imshow(np.where(zs[1:-1, 1:-1] < 0, np.log1p(lap), np.nan), cmap="magma")
    ax.set_title("Fine-scale texture in the ocean (smooth = interpolated)")
    ax.axis("off")
    prev = Path(args.preview) if args.preview else out.with_name("preview.png")
    fig.tight_layout()
    fig.savefig(prev, dpi=80)
    print(f"Wrote {prev}")


if __name__ == "__main__":
    main()
