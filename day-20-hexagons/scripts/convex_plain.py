"""Plain-IoU convex fits (k = 3..8, corners anywhere) for the app's records."""
import json
from concurrent.futures import ProcessPoolExecutor
from shapely.geometry import Polygon
import convex
convex.MISS_W = 1.0

def work(r):
    return r["name"], convex.sweep(Polygon(r["country"]))

if __name__ == "__main__":
    rs = json.load(open("world.json"))
    with ProcessPoolExecutor(2) as ex:
        out = dict(ex.map(work, rs))
    json.dump(out, open("convex_plain.json", "w"), separators=(",", ":"))
    print("done", len(out))
