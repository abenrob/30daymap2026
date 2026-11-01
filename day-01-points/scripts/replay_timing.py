"""Day 1: time a request pattern by replaying it as real HTTP range requests against Source Cooperative.

Same number of requests, same byte sizes, same phases (header+root, then leaf directory, then tiles in
parallel with 6 connections like a browser on HTTP/1.1). Byte content differs; timing is what we measure.
"""
import time, statistics, concurrent.futures as cf
import requests

URL = "https://data.source.coop/fused/fsq-os-places/2025-02-06/places/12.parquet"  # 293 MB, any big file works
s = requests.Session()
s.mount("https://", requests.adapters.HTTPAdapter(pool_connections=6, pool_maxsize=6))

def get(offset, length):
    r = s.get(URL, headers={"Range": f"bytes={offset}-{offset + length - 1}"}, timeout=60)
    assert r.status_code == 206, r.status_code
    return len(r.content)

def replay(phases, cold=True):
    if cold:
        s.close()
    t = time.perf_counter(); off = 0; got = 0
    for phase in phases:
        with cf.ThreadPoolExecutor(6) as ex:
            futs = []
            for ln in phase:
                futs.append(ex.submit(get, off % 250_000_000, ln)); off += ln + 100_000
            got += sum(f.result() for f in futs)
    return time.perf_counter() - t, got

if __name__ == "__main__":
    import json, sys
    phases = json.load(open(sys.argv[1]))
    runs = [replay(phases) for _ in range(5)]
    print(f"median {statistics.median(r[0] for r in runs):.2f}s  bytes {runs[0][1]:,}  runs {[round(r[0],2) for r in runs]}")
