"""Output writers (GeoTIFF, npz stack)."""
import numpy as np
import rasterio


def write_geotiff(path, arr, grid, nodata=None, dtype=None):
    arr = np.asarray(arr)
    dtype = dtype or arr.dtype
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1,
                       dtype=dtype, crs=grid.crs, transform=grid.transform, nodata=nodata,
                       compress="deflate") as dst:
        dst.write(arr.astype(dtype), 1)


def save_stack(path, stack, grid, year, step_minutes):
    np.savez_compressed(path, stack=stack, xmin=grid.xmin, ymax=grid.ymax, res=grid.res,
                        crs=str(grid.crs), year=year, step_minutes=step_minutes)
