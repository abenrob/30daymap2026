"""Rivers to map kilometres (relative to Grenoble) and the 300 m movement grid for the page."""
import json, base64, numpy as np
from scipy.ndimage import gaussian_filter, zoom
from shapely.geometry import shape, box
from shapely.ops import linemerge

LAT_G, LON_G = 45.1885, 5.7245
KMLAT = 111.2
KMLON = 111.2 * np.cos(np.deg2rad(45.29))
want = {"l'Isère": "Isère", "l'Arc": "Arc", "le Drac": "Drac", "la Romanche": "Romanche"}
B = box(5.12, 44.88, 6.58, 45.70)
out = {}
for f in json.load(open("named.json"))["features"]:
    if f["properties"]["importance"] != "5":
        continue
    g = shape(f["geometry"]).intersection(B)
    g = linemerge(g) if g.geom_type == "MultiLineString" else g
    g = g.simplify(0.0007)
    for L in ([g] if g.geom_type == "LineString" else list(g.geoms)):
        if L.length < 0.03:
            continue
        out.setdefault(want[f["properties"]["toponyme"]], []).append(
            [[round((lo - LON_G) * KMLON, 2), round((la - LAT_G) * KMLAT, 2)] for lo, la in L.coords])
json.dump(out, open("rivers_km.json", "w"), separators=(",", ":"))

a = gaussian_filter(np.load("dem_sim.npy"), 1.0)
a = zoom(a, (370 / a.shape[0], 440 / a.shape[1]), order=1)
q = np.clip(np.round(a), 0, 65535).astype("<u2")
open("sim_grid.b64", "w").write(base64.b64encode(q.tobytes()).decode())
print({k: len(v) for k, v in out.items()}, q.shape)
