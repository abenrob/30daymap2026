#!/usr/bin/env python3
"""
export_web.py

Pack the model output for the live page (site/day-12-power/flows/):
  lines.json   simplified line geometry + properties, in a fixed order
  flows.bin    Int16 MW, hour-major: value(h, i) at index h * nLines + i,
               sign = direction along the line's coordinate order
  series.json  hourly country load and generation, measured border flows

Usage
  python3 export_web.py --out out --dest <site>/day-12-power/flows
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
from shapely.geometry import LineString, mapping, shape

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import iberian_blackout_flows as m  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="out")
    ap.add_argument("--cache", default="cache")
    ap.add_argument("--dest", required=True)
    ap.add_argument("--start", default="2025-04-25")
    ap.add_argument("--end", default="2025-05-03")
    ap.add_argument("--tolerance", type=float, default=0.002, help="degrees")
    a = ap.parse_args()
    out, dest = Path(a.out), Path(a.dest)
    dest.mkdir(parents=True, exist_ok=True)

    feats = json.loads((out / "lines.geojson").read_text())["features"]
    pq = out / "flows_hourly.parquet"
    flows = pd.read_parquet(pq) if pq.exists() else \
        pd.read_csv(out / "flows_hourly.csv.gz", parse_dates=["hour_utc"])
    T = pd.date_range(a.start, a.end, freq="1h", tz="UTC", inclusive="left")
    piv = flows.pivot(index="hour_utc", columns="line_id", values="flow_mw").reindex(T)

    lines = []
    for f in feats:
        p = f["properties"]
        g = shape(f["geometry"])
        if g.geom_type != "LineString":
            g = LineString(f["geometry"]["coordinates"])
        s = g.simplify(a.tolerance, preserve_topology=False)
        coords = [[round(x, 4), round(y, 4)] for x, y in mapping(s)["coordinates"]]
        lines.append({"id": p["line_id"], "k": p["kind"], "v": int(p["v_nom"]),
                      "cap": round(p["cap_mw"]), "c": [p["country0"], p["country1"]],
                      "path": coords})
    ids = [l["id"] for l in lines]
    mat = piv[ids].fillna(0.0).clip(-32767, 32767).round().astype("<i2").values
    (dest / "flows.bin").write_bytes(mat.tobytes(order="C"))
    (dest / "lines.json").write_text(json.dumps(
        {"start": T[0].isoformat(), "hours": len(T), "lines": lines},
        separators=(",", ":")))

    # Country series, after the same patches the model applied
    args = SimpleNamespace(source="energycharts", start=a.start, end=a.end,
                           cache=a.cache, no_patch=False, fr_source="rte")
    data = m.fetch_data(args)
    ser = {"hours": len(T)}
    for c in m.MODEL:
        ser[f"load_{c}"] = m.clean_series(data["load"][c], c, T, "load").round().tolist()
        ser[f"gen_{c}"] = data["gen"][c].sum(axis=1, min_count=1).reindex(T) \
            .fillna(0).round().tolist()
    for a_, b_ in (("ES", "FR"), ("ES", "PT")):
        ser[f"exp_{a_}_{b_}"] = m.net_export(data, a_, b_, T).round().tolist()
    (dest / "series.json").write_text(json.dumps(ser, separators=(",", ":")))
    print(f"{len(lines)} lines, {sum(len(l['path']) for l in lines)} vertices, "
          f"{len(T)} hours -> {dest}/ "
          + ", ".join(f"{p.name} {p.stat().st_size/1e6:.2f} MB" for p in sorted(dest.iterdir())))


if __name__ == "__main__":
    main()
