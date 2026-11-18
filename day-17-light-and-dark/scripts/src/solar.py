"""Solar position per time step (UTC) and sun unit vectors in the grid ENU frame."""
from dataclasses import dataclass
import numpy as np
import pandas as pd
import pvlib
from pyproj import CRS, Proj


def grid_convergence_deg(lat, lon, crs="EPSG:2154"):
    """Meridian convergence (deg) of the projected CRS at (lat, lon).
    grid bearing = true azimuth - convergence."""
    p = Proj(CRS.from_user_input(crs))
    return float(p.get_factors(lon, lat).meridian_convergence)


@dataclass
class SunData:
    """Daylight sun samples (elevation >= min). All arrays length N."""
    vec: np.ndarray          # (N,3) unit vectors in grid ENU (x=E, y=N, z=up)
    az_grid: np.ndarray      # (N,) azimuth rad, clockwise from grid north
    az_true_deg: np.ndarray
    el_deg: np.ndarray
    day: np.ndarray          # (N,) 0-based UTC day of year
    minute_of_year: np.ndarray
    ndays: int
    step_minutes: int
    year: int


def compute_sun(lat, lon, year=2025, step_minutes=1, min_elevation_deg=3.0,
                crs="EPSG:2154", altitude=0.0):
    times = pd.date_range(f"{year}-01-01", f"{year + 1}-01-01",
                          freq=f"{step_minutes}min", tz="UTC", inclusive="left")
    sp = pvlib.solarposition.get_solarposition(times, lat, lon, altitude=altitude)
    el = sp["apparent_elevation"].to_numpy()
    az = sp["azimuth"].to_numpy()
    keep = el >= min_elevation_deg
    conv = grid_convergence_deg(lat, lon, crs)
    azg = np.deg2rad(az[keep] - conv)
    elr = np.deg2rad(el[keep])
    vec = np.column_stack([np.cos(elr) * np.sin(azg), np.cos(elr) * np.cos(azg), np.sin(elr)])
    day = (times.dayofyear.to_numpy() - 1)[keep]
    return SunData(vec=vec, az_grid=azg, az_true_deg=az[keep], el_deg=el[keep], day=day,
                   minute_of_year=np.nonzero(keep)[0], ndays=int(times.dayofyear.max()),
                   step_minutes=step_minutes, year=year)
