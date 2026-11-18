"""Static plotting helpers (kept apart from the model)."""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def map_plot(path, arr, grid, tx, ty, threshold, label, title, cmap="YlOrRd"):
    ext = [grid.xmin - tx, grid.xmin + grid.ncols * grid.res - tx,
           grid.ymax - grid.nrows * grid.res - ty, grid.ymax - ty]
    fig, ax = plt.subplots(figsize=(8, 7.2), dpi=130)
    m = np.ma.masked_where(arr <= 0, arr)
    im = ax.imshow(m, extent=ext, origin="upper", cmap=cmap)
    X, Y = grid.centres()
    ax.contour(X - tx, Y - ty, arr, levels=[threshold], colors="k", linewidths=1.2)
    ax.plot(0, 0, "k^", ms=8)
    ax.set_aspect("equal"); ax.set_xlabel("East of turbine (m)"); ax.set_ylabel("North of turbine (m)")
    ax.set_title(title + f"\n(black contour = {threshold:g})")
    fig.colorbar(im, ax=ax, shrink=0.8, label=label)
    fig.tight_layout(); fig.savefig(path); plt.close(fig)
