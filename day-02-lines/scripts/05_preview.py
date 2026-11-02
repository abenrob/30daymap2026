"""2D preview of the traced network on a hillshade, to check the data before Blender.

Writes work/renders/day-02-preview.png. Run from the workspace root.
Line width scales with the square root of upstream channel length (our accumulation).
"""
import geopandas as gpd
import numpy as np
import rasterio
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

D = "work/data/day-02-lines/derived"
CRS = "EPSG:2154"

riv = gpd.read_parquet(f"{D}/rivers.parquet").set_crs(4326).to_crs(CRS)
basin = gpd.read_parquet(f"{D}/basin.parquet").set_crs(4326).to_crs(CRS)
lakes = gpd.read_parquet(f"{D}/lakes.parquet").set_crs(4326).to_crs(CRS)
ocean = gpd.read_parquet(f"{D}/ocean.parquet").set_crs(4326).to_crs(CRS)

with rasterio.open(f"{D}/dem_150m_l93.tif") as src:
    z = src.read(1, masked=True).filled(0).astype("float32")
    b = src.bounds
    res = src.res[0]

# hillshade, sun from the north-west
gy, gx = np.gradient(z * 2.0, res)  # 2x vertical exaggeration
slope = np.pi / 2 - np.arctan(np.hypot(gx, gy))
aspect = np.arctan2(-gx, gy)
az, alt = np.radians(315), np.radians(40)
hs = np.sin(alt) * np.sin(slope) + np.cos(alt) * np.cos(slope) * np.cos(az - aspect)
hs = np.clip(hs, 0, 1)

fig, ax = plt.subplots(figsize=(10.8, 13.5), dpi=100)
fig.patch.set_facecolor("#0b1016")
ax.set_facecolor("#0b1016")
ax.imshow(hs, extent=(b.left, b.right, b.bottom, b.top), cmap="gray", vmin=-0.3, vmax=1.6, alpha=0.55)

# dim everything outside the basin
from shapely.geometry import box
outside = gpd.GeoSeries([box(*b).difference(basin.geometry.iloc[0])], crs=CRS)
outside.plot(ax=ax, color="#0b1016", alpha=0.6, linewidth=0)
basin.boundary.plot(ax=ax, color="#3b5560", linewidth=0.6)
ocean.plot(ax=ax, color="#060a0e", linewidth=0)
lakes.plot(ax=ax, color="#1c8c8c", linewidth=0)

w = np.sqrt(riv["up_len_km"].to_numpy())
lw = 0.15 + 2.6 * (w / w.max())
segs = [np.asarray(g.coords) for g in riv.geometry]
ax.add_collection(LineCollection(segs, linewidths=lw, colors="#40e0d0", alpha=0.9, capstyle="round"))

ax.set_xlim(b.left, b.right)
ax.set_ylim(b.bottom, b.top)
ax.set_axis_off()
plt.subplots_adjust(0, 0, 1, 1)
fig.savefig("work/renders/day-02-preview.png", facecolor=fig.get_facecolor())
print("wrote work/renders/day-02-preview.png")
