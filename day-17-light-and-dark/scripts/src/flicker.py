"""Receptor-centric shadow-flicker model (BallTree over sun unit vectors).

Method
------
Every daylight minute i has a sun unit vector s_i (ENU, grid frame). For a receptor p
and a turbine with hub h, minute i flickers when the ray p + t*s_i (t>0) passes within R
of the hub (sphere rotor model), and |h-p| <= max_dist.

The hub depends on the sun azimuth (rotor yawed to face the sun):
    h_i = base + (0,0,Hhub) + overhang*(sin az_i, cos az_i, 0)
so |h_i - h_nom| <= overhang (h_nom = tower axis at hub height). Hence if the ray passes
within R of h_i it passes within R+overhang of h_nom, i.e. the angle between s_i and
(h_nom - p) is <= asin((R+overhang)/|h_nom-p|). Step 1 (BallTree, euclidean on unit
vectors with chord = 2 sin(theta/2)) returns those *candidates* with this enlarged
radius; step 2 does the exact ray/sphere test with the yaw-dependent hub h_i.
Correct for any yaw geometry; candidate overshoot is only ~overhang/R (~9%).

Per cell: indices -> per-day counts (bincount) -> uint16 stack (days, rows, cols).
Multiple turbines: the (cell, minute) hits are unioned (np.unique), so a minute counts once.

Terrain occlusion hook: pass occlusion=callable(cell_flat_ids, sun_idx, turbine_index)
-> bool array (True = sun visible from the cell). It is applied to the exact hits only.
Default None = flat/unobstructed.
"""
from dataclasses import dataclass
import time
import numpy as np
from sklearn.neighbors import BallTree
from .geometry import rotor_hit


@dataclass
class Grid:
    xmin: float            # left edge
    ymax: float            # top edge
    res: float
    nrows: int
    ncols: int
    crs: str = "EPSG:2154"
    z: np.ndarray = None   # (nrows,ncols) ground elevation, None -> 0

    @property
    def transform(self):
        from rasterio.transform import Affine
        return Affine(self.res, 0, self.xmin, 0, -self.res, self.ymax)

    def centres(self):
        xs = self.xmin + (np.arange(self.ncols) + 0.5) * self.res
        ys = self.ymax - (np.arange(self.nrows) + 0.5) * self.res
        X, Y = np.meshgrid(xs, ys)
        return X, Y


@dataclass
class FlickerParams:
    max_distance_diameters: float = 10.0
    observer_height: float = 1.5
    chunk_cells: int = 250   # keep small: near-tower cells have huge candidate caps


def compute_points(P, turbines, sun, params=None, occlusion=None, want_unoccluded=False,
                   per_turbine=False, verbose=True, flags=False, far_m=500.0, collect_pairs=False):
    """Core engine over arbitrary receptor points P (N,3) (x, y, z incl. observer height).

    Returns dict: 'stack' (ndays,N) uint16 minutes/day (with occlusion if given),
    'stack_free' (same without occlusion; only if want_unoccluded), 'turb_minutes' (N,nturb) annual minutes
    per turbine (after occlusion, not unioned; only if per_turbine)."""
    params = params or FlickerParams()
    t0 = time.perf_counter()
    N = P.shape[0]
    nsun = sun.vec.shape[0]
    step = sun.step_minutes
    tree = BallTree(sun.vec, metric="euclidean", leaf_size=40)
    hub_nom = [t.nominal_hub for t in turbines]
    maxd = [params.max_distance_diameters * t.rotor_diameter for t in turbines]
    inrange = [np.linalg.norm(P - h, axis=1) <= md + t.overhang for t, h, md in zip(turbines, hub_nom, maxd)]
    any_range = np.nonzero(np.any(inrange, axis=0))[0]
    if verbose:
        print(f"[flicker] points={N}, in range of any turbine={any_range.size}, turbines={len(turbines)}, daylight samples={nsun}")
    both = occlusion is not None and want_unoccluded
    stack = np.zeros((sun.ndays, N), dtype=np.uint16)
    stack_free = np.zeros((sun.ndays, N), dtype=np.uint16) if both else None
    tmin = np.zeros((N, len(turbines)), dtype=np.float32) if per_turbine else None
    total_hits = 0
    flag_any = np.zeros(nsun, bool); flag_far = np.zeros(nsun, bool); pairs = []

    def to_stack(dst, ids, keys):
        k = np.concatenate(keys)
        if len(turbines) > 1:
            k = np.unique(k)                            # union across turbines: a minute counts once
        gl, j = np.divmod(k, nsun)
        cnt = np.bincount(gl * sun.ndays + sun.day[j], minlength=ids.size * sun.ndays)
        dst[:, ids] = (cnt.reshape(ids.size, sun.ndays).T * step).astype(np.uint16)

    tstart = time.perf_counter()
    for n_done, c0 in enumerate(range(0, any_range.size, params.chunk_cells)):
        ids = any_range[c0:c0 + params.chunk_cells]
        keys, keys_free = [], []
        for ti, t in enumerate(turbines):
            sub = ids[inrange[ti][ids]]
            if sub.size == 0:
                continue
            p = P[sub]
            w = hub_nom[ti] - p
            d = np.linalg.norm(w, axis=1)
            u = w / d[:, None]
            ratio = (t.R + t.overhang) / d
            theta = np.where(ratio >= 1, np.pi, np.arcsin(np.minimum(ratio, 1.0)))
            res = tree.query_radius(u, r=2 * np.sin(theta / 2))
            lens = np.fromiter((len(a) for a in res), dtype=np.int64, count=len(res))
            if lens.sum() == 0:
                continue
            j = np.concatenate(res)
            li = np.repeat(np.arange(sub.size), lens)
            total_hits += j.size
            ok = rotor_hit(p[li], sun.vec[j], t.hub_xyz(sun.az_grid[j]), t.R, maxd[ti])
            j, li = j[ok], li[ok]
            if both and j.size:
                keys_free.append(np.searchsorted(ids, sub[li]).astype(np.int64) * nsun + j)
            if occlusion is not None and j.size:
                vis = occlusion(sub[li], j, ti)
                j, li = j[vis], li[vis]
            if flags and j.size:
                flag_any[j] = True
                far = np.hypot(p[li, 0] - t.x, p[li, 1] - t.y) > far_m
                flag_far[j[far]] = True
            if collect_pairs and j.size:
                pairs.append(np.column_stack([sub[li], j]))
            gl = np.searchsorted(ids, sub[li])
            if per_turbine and j.size:
                tmin[ids, ti] += np.bincount(gl, minlength=ids.size) * step
            keys.append(gl.astype(np.int64) * nsun + j)
        if keys:
            to_stack(stack, ids, keys)
        if keys_free:
            to_stack(stack_free, ids, keys_free)
        if verbose and n_done % 100 == 0:
            frac = min(1.0, (c0 + ids.size) / any_range.size)
            print(f"[flicker] {100*frac:.0f}%  elapsed {time.perf_counter()-tstart:.0f}s", flush=True)
    if verbose:
        print(f"[flicker] candidate hits={total_hits:.3e}, time={time.perf_counter() - t0:.1f}s")
    out = {"stack": stack}
    if both:
        out["stack_free"] = stack_free
    if per_turbine:
        out["turb_minutes"] = tmin
    if flags:
        out["flag_any"], out["flag_far"] = flag_any, flag_far
    if collect_pairs:
        out["pairs"] = np.unique(np.concatenate(pairs), axis=0) if pairs else np.zeros((0, 2), np.int64)
    return out


def compute_flicker(grid, turbines, sun, params=None, occlusion=None, verbose=True,
                    want_unoccluded=False, per_turbine=False):
    """Grid wrapper. Returns stack (ndays,rows,cols) uint16, or a dict of reshaped stacks if
    want_unoccluded/per_turbine are used."""
    params = params or FlickerParams()
    X, Y = grid.centres()
    Z = (grid.z if grid.z is not None else np.zeros_like(X)) + params.observer_height
    P = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])
    res = compute_points(P, turbines, sun, params, occlusion, want_unoccluded, per_turbine, verbose)
    shp = (sun.ndays, grid.nrows, grid.ncols)
    if not (want_unoccluded or per_turbine):
        return res["stack"].reshape(shp)
    for k in ("stack", "stack_free"):
        if k in res:
            res[k] = res[k].reshape(shp)
    return res


def annual_hours(stack):
    return stack.sum(axis=0, dtype=np.uint32).astype(np.float32) / 60.0


def max_daily_minutes(stack):
    return stack.max(axis=0)


def days_over(stack, minutes=30):
    """Days with MORE than `minutes` of flicker."""
    return (stack > minutes).sum(axis=0).astype(np.uint16)
