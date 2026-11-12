#!/usr/bin/env python3
"""
validate_lines.py

Independent check of the modelled flows: REE publishes daily measured physical
flow per Spanish interconnector line (ree_daily_lines.csv, from
crosscheck_sources.py). The hourly border totals are imposed on the model, so
matching them proves little; how the model SPLITS a border across parallel
lines is the real test of the network and the bus weights.

Lines are matched to model branches by their end substations (checked by hand
on the OSM geometry, see REE_LINE_BRANCHES in iberian_blackout_flows.py). The four 220 kV/400 kV Douro lines
(Aldeadavila, Saucelle, Lagoaca, Pocinho) share substations in OSM and are
compared as one group. Lines below 220 kV (Irun-Errondenia, Benos-Lac d'Oo,
Conchas-Lindoso) are not in the model; REE shows ~0 on them.

The HVDC daily total is taken from REE by the model, so its row only checks
the bookkeeping. Lines REE reports as idle for a day are switched off in the
model for that day, so their rows are 0 = 0 on those days.

Output: out/validation_lines_daily.csv, MWh per Madrid day, import-positive
(positive = into Spain), and a printed summary.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from iberian_blackout_flows import REE_LINE_BRANCHES  # noqa: E402

TZ_ES = "Europe/Madrid"

# REE line title -> group shown in the output. Branch ids come from
# REE_LINE_BRANCHES in iberian_blackout_flows.py; the Douro lines are a group.
GROUP = {
    "Hernani - Argia": "ES-FR Hernani-Argia 400 kV",
    "Arkale - Argia": "ES-FR Arkale-Argia 220 kV",
    "Biescas - Pragnéres": "ES-FR Biescas-Pragneres 220 kV",
    "Vic - Baixas": "ES-FR Vic-Baixas 400 kV",
    "Santa Llogaia - Baixas": "ES-FR Santa Llogaia-Baixas HVDC",
    "Cartelle - Lindoso": "ES-PT Cartelle-Lindoso 400 kV",
    "Aldeadávila - Lagoaça": "ES-PT Douro group",
    "Aldeadávila - Pocinho1": "ES-PT Douro group",
    "Aldeadávila - Pocinho2": "ES-PT Douro group",
    "Saucelle - Pocinho": "ES-PT Douro group",
    "Cedillo - Falagueira": "ES-PT Cedillo-Falagueira 400 kV",
    "Brovales - Alqueva": "ES-PT Brovales-Alqueva 400 kV",
    "Puebla de Guzmán - Tavira": "ES-PT Puebla de Guzman-Tavira 400 kV",
}
DOURO = ["L:merged_way/144327162-400+1", "L:merged_way/144385745-1-400+4",
         "L:way/144385750-220", "L:way/144385752-220", "L:way/144385757-220",
         "L:way/144385781-220", "L:way/661761039-220", "L:way/753596560-220"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    out = Path(a.out)

    ree = pd.read_csv(out / "ree_daily_lines.csv")
    ree = ree[ree.line.isin(GROUP)]
    ree["group"] = ree.line.map(GROUP)
    meas = ree.groupby(["date", "group"]).net_mwh.sum()

    pq = out / "flows_hourly.parquet"
    flows = pd.read_parquet(pq) if pq.exists() else \
        pd.read_csv(out / "flows_hourly.csv.gz", parse_dates=["hour_utc"])
    geo = json.loads((out / "lines.geojson").read_text())["features"]
    c0 = {f["properties"]["line_id"]: f["properties"]["country0"] for f in geo}
    groups = {GROUP[n]: ids for n, ids in REE_LINE_BRANCHES.items()}
    groups["ES-PT Douro group"] = DOURO
    rows = []
    for g, ids in groups.items():
        missing = [i for i in ids if i not in c0]
        if missing:
            raise SystemExit(f"{g}: branch ids not in model output: {missing}")
        f = flows[flows.line_id.isin(ids)].copy()
        # flow_mw is bus0 -> bus1; make it positive into Spain
        f["imp"] = [-v if c0[i] == "ES" else v for i, v in zip(f.line_id, f.flow_mw)]
        h = f.groupby("hour_utc").imp.sum()
        day = pd.DatetimeIndex(h.index).tz_convert(TZ_ES).strftime("%Y-%m-%d")
        cnt = h.groupby(day).size()
        d = h.groupby(day).sum()[cnt == 24]  # full Madrid days only
        for dd, v in d.items():
            rows.append({"date": dd, "group": g, "modelled_mwh": round(v),
                         "measured_mwh": meas.get((dd, g))})
    v = pd.DataFrame(rows).dropna()
    v["error_mwh"] = v.modelled_mwh - v.measured_mwh
    v.to_csv(out / "validation_lines_daily.csv", index=False)

    v["border"] = v.group.str[:5]
    tot = v.groupby(["date", "border"]).measured_mwh.transform(lambda s: s.abs().sum())
    summ = v.assign(share_meas=v.measured_mwh.abs() / tot).groupby("group").agg(
        measured_mean_mwh=("measured_mwh", "mean"),
        modelled_mean_mwh=("modelled_mwh", "mean"),
        mean_abs_error_mwh=("error_mwh", lambda s: s.abs().mean()))
    print("Interconnector lines, daily net MWh into Spain (full Madrid days):")
    print(summ.round(0).to_string())
    for b in ("ES-FR", "ES-PT"):
        x = v[(v.border == b) & ~v.group.str.contains("HVDC")]  # AC lines only
        print(f"{b} AC lines: sum |error| / sum |measured| = "
              f"{x.error_mwh.abs().sum() / x.measured_mwh.abs().sum():.0%}")


if __name__ == "__main__":
    main()
