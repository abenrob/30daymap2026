"""Day 1: build a PMTiles archive of French places with a small, transparent point tiler.

Mirrors tippecanoe's default behaviour for points:
  - base zoom = max zoom (14): every point is kept at z14
  - drop rate 2.5: each zoom down keeps 1/2.5 of the points, chosen by a stable random rank
  - tile cap 500 KB compressed: if a tile is still too big, the lowest-ranked points are dropped

Input:  fr.parquet (lon, lat, name, cat)
Output: fr_places.pmtiles, plus tile_stats.parquet (points kept and bytes per tile)
"""
import gzip, math, time, json
import numpy as np
import duckdb
import mapbox_vector_tile as mvt
from pmtiles.writer import Writer
from pmtiles.tile import zxy_to_tileid, TileType, Compression

MAXZ, DROP, CAP, EXTENT = 14, 2.5, 500_000, 4096

d = duckdb.sql("select lon, lat, coalesce(name,'') name, coalesce(cat,'') cat from 'fr.parquet'").fetchnumpy()
lon, lat, name, cat = d["lon"], d["lat"], d["name"], d["cat"]
n = len(lon)
rank = np.random.default_rng(42).random(n)          # stable random priority, lower = kept longer
mx = (lon + 180) / 360                                # Web Mercator in 0..1
s = np.sin(np.radians(np.clip(lat, -85.05, 85.05)))
my = 0.5 - np.log((1 + s) / (1 - s)) / (4 * np.pi)

def encode(idx, z, x, y):
    scale = 2 ** z
    px = ((mx[idx] * scale - x) * EXTENT).astype(int)
    py = ((my[idx] * scale - y) * EXTENT).astype(int)
    feats = [{"geometry": {"type": "Point", "coordinates": [int(a), int(b)]},
              "properties": {"name": name[i], "cat": cat[i]}} for a, b, i in zip(px, py, idx)]
    raw = mvt.encode([{"name": "places", "features": feats}],
                     default_options={"extents": EXTENT, "y_coord_down": True})
    return gzip.compress(raw)

tiles, stats = {}, []
t0 = time.time()
for z in range(0, MAXZ + 1):
    keep = np.where(rank < DROP ** -(MAXZ - z))[0]
    scale = 2 ** z
    tx = np.floor(mx[keep] * scale).astype(np.int64)
    ty = np.floor(my[keep] * scale).astype(np.int64)
    key = tx * scale + ty
    order = np.argsort(key, kind="stable")
    keep, key, tx, ty = keep[order], key[order], tx[order], ty[order]
    bounds = np.flatnonzero(np.diff(key)) + 1
    for g in np.split(np.arange(len(keep)), bounds):
        if len(g) == 0:
            continue
        x, y = int(tx[g[0]]), int(ty[g[0]])
        idx = keep[g]
        in_tile = len(idx)
        idx = idx[np.argsort(rank[idx])]               # best-ranked first
        data = encode(idx, z, x, y)
        while len(data) > CAP:                          # tippecanoe-style size cap: drop lowest ranks
            idx = idx[: int(len(idx) * CAP / len(data) * 0.9)]
            data = encode(idx, z, x, y)
        tiles[zxy_to_tileid(z, x, y)] = data
        stats.append((z, x, y, in_tile, len(idx), len(data)))
    print(f"z{z}: {len(bounds)+1} tiles, {len(keep)} points, {time.time()-t0:.0f}s", flush=True)

with open("fr_places.pmtiles", "wb") as f:
    w = Writer(f)
    for tid in sorted(tiles):
        w.write_tile(tid, tiles[tid])
    e7 = lambda v: int(v * 1e7)
    w.finalize(
        {"tile_type": TileType.MVT, "tile_compression": Compression.GZIP,
         "min_zoom": 0, "max_zoom": MAXZ,
         "min_lon_e7": e7(lon.min()), "min_lat_e7": e7(lat.min()),
         "max_lon_e7": e7(lon.max()), "max_lat_e7": e7(lat.max()),
         "center_zoom": 12, "center_lon_e7": e7(2.345), "center_lat_e7": e7(48.855)},
        {"name": "Foursquare Open Source Places, France",
         "attribution": "Foursquare Open Source Places (Apache 2.0), via Source Cooperative",
         "vector_layers": [{"id": "places", "fields": {"name": "String", "cat": "String"},
                            "minzoom": 0, "maxzoom": MAXZ}]})

con = duckdb.connect()
con.execute("create table s(z int, x int, y int, in_tile int, kept int, bytes int)")
con.executemany("insert into s values (?,?,?,?,?,?)", stats)
con.execute("copy s to 'tile_stats.parquet'")
print("done", round(time.time() - t0), "s")
