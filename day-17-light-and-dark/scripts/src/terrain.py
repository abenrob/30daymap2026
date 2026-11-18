"""DEM access, horizon angles and the terrain-occlusion callable.

Horizon table: for each point and each grid-azimuth bin (default 1 deg, bin k centred on k deg clockwise
from GRID north) the maximum elevation angle of the terrain along that azimuth, ray-marched on the DEM
(bilinear, step = max(res, 2.5 % of distance), up to max_dist or the DEM edge), relative to the observer
(ground + observer height). Stored as int16 in 0.01 deg.  The sun is visible if sun elevation > horizon
(linear interpolation between bins).  Earth curvature/refraction ignored (<2 m at 5 km).

Approximation: only the sun direction is tested.  The cell->hub sightline is not tested separately: the sun lies
within the rotor cap of the cell->hub direction, so terrain hiding the hub also hides (nearly) the same sky
patch.  Terrain/DEM limits: terrain beyond the DEM edge is ignored (distant mountains not included).
"""
import hashlib
from pathlib import Path
import numpy as np
import rasterio
from numba import njit, prange
from scipy.ndimage import map_coordinates


class DEM:
    def __init__(self, path):
        with rasterio.open(path) as r:
            self.z = r.read(1).astype(np.float32)
            self.res = r.transform.a
            self.xmin, self.ymax = r.transform.c, r.transform.f
            self.crs = r.crs
            nd = r.nodata
        if nd is not None:
            self.z[self.z == nd] = np.nan
        self.nrows, self.ncols = self.z.shape

    def sample(self, x, y):
        """Bilinear ground elevation at coordinates (cell centres at +0.5)."""
        c = (np.atleast_1d(x).astype(float) - self.xmin) / self.res - 0.5
        r = (self.ymax - np.atleast_1d(y).astype(float)) / self.res - 0.5
        v = map_coordinates(self.z, [r, c], order=1, mode="nearest")
        return v if np.ndim(x) else v[0]

    def digest(self):
        return hashlib.md5(self.z.tobytes()).hexdigest()[:12]


@njit(parallel=True, cache=True)
def _horizon(z, xmin, ymax, res, px, py, pz, naz, maxdist, out):
    nrows, ncols = z.shape
    for i in prange(px.size):
        for a in range(naz):
            az = 2.0 * np.pi * a / naz
            dx = np.sin(az)
            dy = np.cos(az)
            best = -1e9
            d = res
            while d <= maxdist:
                fc = (px[i] + dx * d - xmin) / res - 0.5
                fr = (ymax - (py[i] + dy * d)) / res - 0.5
                if fc < 0 or fr < 0 or fc > ncols - 1 or fr > nrows - 1:
                    break
                c0 = int(fc); r0 = int(fr)
                c1 = min(c0 + 1, ncols - 1); r1 = min(r0 + 1, nrows - 1)
                wc = fc - c0; wr = fr - r0
                h = (z[r0, c0] * (1 - wc) * (1 - wr) + z[r0, c1] * wc * (1 - wr) +
                     z[r1, c0] * (1 - wc) * wr + z[r1, c1] * wc * wr)
                s = (h - pz[i]) / d
                if s > best:
                    best = s
                d += max(res, 0.025 * d)
            if best < -1e8:
                out[i, a] = -9000
            else:
                out[i, a] = np.int16(np.arctan(best) * 180.0 / np.pi * 100.0)


def horizon_table(dem, px, py, pz, naz=360, max_dist=5000.0, cache_dir=None, tag=""):
    """int16 (n, naz) horizon angles in 0.01 deg. Cached in cache_dir (.npy) keyed on inputs."""
    px, py, pz = (np.ascontiguousarray(a, dtype=np.float64) for a in (px, py, pz))
    key = hashlib.md5(np.concatenate([px, py, pz]).tobytes() + dem.digest().encode() +
                      f"{naz}{max_dist}{dem.res}{dem.xmin}{dem.ymax}".encode()).hexdigest()[:12]
    f = Path(cache_dir) / f"horizon_{tag}_{key}.npy" if cache_dir else None
    if f is not None and f.exists():
        print(f"[terrain] horizon table loaded from cache {f.name}")
        return np.load(f)
    out = np.empty((px.size, naz), dtype=np.int16)
    _horizon(dem.z, dem.xmin, dem.ymax, dem.res, px, py, pz, naz, float(max_dist), out)
    if f is not None:
        np.save(f, out)
    return out


class HorizonOcclusion:
    """Callable for flicker core: occlusion(point_ids, sun_idx, turbine_idx) -> bool visible."""

    def __init__(self, table, point_to_row, sun):
        self.t = table
        self.map = point_to_row
        self.naz = table.shape[1]
        self.f = (np.rad2deg(sun.az_grid) % 360.0) * (self.naz / 360.0)
        self.el = sun.el_deg

    def __call__(self, ids, j, ti):
        rows = self.map[ids]
        f = self.f[j]
        i0 = np.floor(f).astype(np.int64)
        w = f - i0
        i0 %= self.naz
        i1 = (i0 + 1) % self.naz
        hz = (self.t[rows, i0] * (1 - w) + self.t[rows, i1] * w) / 100.0
        return self.el[j] > hz


def ray_blocked(dem, p, az_rad, el_rad, step=None, max_dist=5000.0):
    """Independent brute force: is the sun ray from p=(x,y,z) blocked by terrain? Arrays az/el (M,)."""
    step = step or dem.res
    d = np.arange(step, max_dist + step, step)
    az = np.atleast_1d(az_rad); el = np.atleast_1d(el_rad)
    blocked = np.zeros(az.size, bool)
    for k in range(az.size):
        x = p[0] + np.sin(az[k]) * d
        y = p[1] + np.cos(az[k]) * d
        ok = (x > dem.xmin) & (x < dem.xmin + dem.ncols * dem.res) & (y < dem.ymax) & (y > dem.ymax - dem.nrows * dem.res)
        if not ok.any():
            continue
        zt = dem.sample(x[ok], y[ok])
        blocked[k] = np.any(zt > p[2] + d[ok] * np.tan(el[k]))
    return blocked


@njit(parallel=True, cache=True)
def _landing(z, xmin, ymax, res, hubs, s, maxd, out):
    nrows, ncols = z.shape
    for i in prange(hubs.shape[0]):
        out[i, 0] = np.nan
        out[i, 1] = np.nan
        t = res
        while t <= maxd:
            x = hubs[i, 0] - s[i, 0] * t
            y = hubs[i, 1] - s[i, 1] * t
            zr = hubs[i, 2] - s[i, 2] * t
            c = int((x - xmin) / res)
            r = int((ymax - y) / res)
            if c < 0 or r < 0 or c >= ncols or r >= nrows:
                break
            if z[r, c] >= zr:
                out[i, 0] = x
                out[i, 1] = y
                break
            t += res * 0.5


def shadow_landing(dem, hubs, svec, max_dist=3000.0):
    """Ground point (x, y) where the ray from each hub along -sun vector first meets the DEM (nan if none)."""
    out = np.empty((hubs.shape[0], 2), dtype=np.float64)
    _landing(dem.z, dem.xmin, dem.ymax, dem.res, np.ascontiguousarray(hubs), np.ascontiguousarray(svec), float(max_dist), out)
    return out
