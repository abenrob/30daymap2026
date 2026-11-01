"""Day 1: what a PMTiles client fetches for the Paris query box, emulating pmtiles.js:
first request = bytes 0..16383 (header + root directory), then leaf directories (cached), then tiles."""
import math, gzip, mmap
import duckdb
from pmtiles.reader import deserialize_header, deserialize_directory, find_tile
from pmtiles.tile import zxy_to_tileid
import mapbox_vector_tile as mvt

V = (2.22, 2.47, 48.80, 48.91)
f = open("fr_places.pmtiles", "rb"); m = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)

def run(z):
    reqs = [("header+root", 16384)]
    h = deserialize_header(m[0:127])
    leaf_cache, tiles_bytes, shown, inbox = set(), 0, 0, 0
    n = 2 ** z
    tx = lambda lon: int((lon + 180) / 360 * n)
    ty = lambda lat: int((1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n)
    tiles = [(x, y) for x in range(tx(V[0]), tx(V[1]) + 1) for y in range(ty(V[3]), ty(V[2]) + 1)]
    for x, y in tiles:
        tid = zxy_to_tileid(z, x, y)
        off, ln = h["root_offset"], h["root_length"]
        for _ in range(4):
            e = find_tile(deserialize_directory(m[off:off + ln]), tid)
            if e is None: break
            if e.run_length == 0:
                off, ln = h["leaf_directory_offset"] + e.offset, e.length
                if off not in leaf_cache:
                    leaf_cache.add(off); reqs.append(("leaf dir", ln))
            else:
                data = m[h["tile_data_offset"] + e.offset: h["tile_data_offset"] + e.offset + e.length]
                reqs.append(("tile", len(data))); tiles_bytes += len(data)
                feats = mvt.decode(gzip.decompress(data), default_options={"y_coord_down": True})["places"]["features"]
                shown += len(feats)
                for ft in feats:
                    px, py = ft["geometry"]["coordinates"]
                    lo = (x + px / 4096) / n * 360 - 180
                    la = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + py / 4096) / n))))
                    inbox += V[0] <= lo <= V[1] and V[2] <= la <= V[3]
                break
    return dict(zoom=z, tiles=len(tiles), requests=len(reqs), leaf_dirs=sum(r[0] == "leaf dir" for r in reqs),
                bytes=sum(r[1] for r in reqs), tile_bytes=tiles_bytes, points_in_tiles=shown, points_in_box=inbox,
                phases=[[reqs[0][1]], [r[1] for r in reqs if r[0] == 'leaf dir'], [r[1] for r in reqs if r[0] == 'tile']])

if __name__ == '__main__':
    import json
    for z in (12, 13, 14):
        r = run(z); json.dump(r.pop('phases'), open(f'phases_z{z}.json', 'w')); print(r)
