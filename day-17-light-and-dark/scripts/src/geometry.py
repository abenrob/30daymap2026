"""Turbine and rotor geometry.

Rotor model: sphere of radius R = rotor_diameter/2 centred on the hub.
Yaw worst case: rotor faces the sun, so hub = tower base + overhang horizontally
toward the sun azimuth, at hub height (recomputed for every time step).
"""
from dataclasses import dataclass
import numpy as np


@dataclass
class Turbine:
    id: str
    x: float                 # grid CRS metres (tower base)
    y: float
    ground_z: float = 0.0    # ground elevation at tower base
    hub_height: float = 110.0
    rotor_diameter: float = 130.0
    overhang: float = 6.0

    @property
    def R(self):
        return self.rotor_diameter / 2.0

    @property
    def nominal_hub(self):
        """Hub with zero overhang (tower axis)."""
        return np.array([self.x, self.y, self.ground_z + self.hub_height])

    def hub_xyz(self, az_grid_rad):
        """Hub positions (N,3) for sun grid-azimuths (rad, clockwise from grid north)."""
        az = np.atleast_1d(az_grid_rad)
        h = np.empty((az.size, 3))
        h[:, 0] = self.x + self.overhang * np.sin(az)
        h[:, 1] = self.y + self.overhang * np.cos(az)
        h[:, 2] = self.ground_z + self.hub_height
        return h


def rotor_hit(p, s, hub, R, max_dist):
    """Exact test (vectorised): does the ray p + t*s (t>0) intersect the sphere
    (hub, R), with |hub-p| <= max_dist?  p, s, hub: (N,3). Returns bool (N,)."""
    w = hub - p
    w2 = np.einsum("ij,ij->i", w, w)
    t = np.einsum("ij,ij->i", w, s)
    disc = t * t - (w2 - R * R)
    return (disc >= 0) & (t > 0) & (w2 <= max_dist * max_dist)


def brute_force_hit(p, s, hub, R, max_dist):
    """Independent check by perpendicular distance from hub to the sun ray (cross product)."""
    w = hub - p
    d = np.linalg.norm(w, axis=1)
    perp = np.linalg.norm(np.cross(w, s), axis=1)
    return (np.einsum("ij,ij->i", w, s) > 0) & (perp <= R) & (d <= max_dist)
