#!/usr/bin/env python3
"""
crosscheck_sources.py

Token-free cross-checks for iberian_blackout_flows.py, replacing the ENTSO-E
comparison (no API token in time). Two independent TSO sources:

  REE REData (Red Electrica, Spain)  https://www.ree.es/en/apidatos
    Daily measured physical exchanges (MWh) per border AND per interconnector
    line (FR and PT). Also Morocco and Andorra, which Energy-Charts lacks.
    Hourly resolution is not served for exchanges (HTTP 400), only daily.
  RTE eCO2mix via ODRE (France)       https://odre.opendatasoft.com
    Definitive 30-min national data: load, generation by fuel, total physical
    exchange, commercial schedules per border (15-min). Licence Ouverte (Etalab).

Outputs (in --out):
  ree_daily_borders.csv      date (Madrid local day), border, import/export/net MWh
  ree_daily_lines.csv        date, border, line, import/export/net MWh
  extra_borders_ma_ad.csv    hour_utc, border, net_export_mw  (feed to
                             iberian_blackout_flows.py --extra-borders);
                             flat profile = daily net / 24, see caveats
  check_es_borders_daily.csv Energy-Charts (raw and with the RTE gap patch) vs
                             REE, daily net MWh, ES-FR and ES-PT
  check_fr_hourly.csv        Energy-Charts vs RTE, hourly MW: load, fuels, FR-ES
Sign convention in all check files: positive = import into the first country.

Usage
  python3 crosscheck_sources.py               # uses ../cache, writes ./out
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from iberian_blackout_flows import (ES_FR_GAP, ec_frame, ec_request,  # noqa: E402
                                    rte_hourly)

TZ_ES = "Europe/Madrid"
REE = "https://apidatos.ree.es/en/datos/intercambios/{w}?{q}"
REE_BORDERS = {"FR": "francia-frontera", "PT": "portugal-frontera",
               "MA": "marruecos-frontera", "AD": "andorra-frontera"}
REE_LINES = {"FR": "lineas-francia", "PT": "lineas-portugal"}
# eCO2mix column -> Energy-Charts-style fuel label used for the comparison
RTE_FUELS = {"nucleaire": "Nuclear", "gaz": "Fossil Gas", "charbon": "Fossil Hard coal",
             "fioul": "Fossil Oil", "eolien": "Wind", "solaire": "Solar",
             "hydraulique": "Hydro (all)", "bioenergies": "Biomass/waste"}


def get_json(url: str, cache: Path, pause: float = 5.0):
    if cache.exists():
        return json.loads(cache.read_text())
    print("GET", url[:140])
    with urllib.request.urlopen(url, timeout=120) as r:
        j = json.loads(r.read().decode())
    if isinstance(j, dict) and j.get("errors"):
        sys.exit(f"{url}\n-> {j['errors']}")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(j))
    time.sleep(pause)  # be gentle; REData sits behind a bot filter
    return j


def ree(widget: str, start: str, end_incl: str, cache_dir: Path) -> dict:
    q = urllib.parse.urlencode({"start_date": f"{start}T00:00",
                                "end_date": f"{end_incl}T23:59", "time_trunc": "day"})
    return get_json(REE.format(w=widget, q=q),
                    cache_dir / f"ree_{widget}_{start}_{end_incl}.json")


def _vals(attrs: dict) -> dict:
    return {v["datetime"][:10]: float(v["value"]) for v in attrs.get("values", [])}


def ree_borders(start, end_incl, cache_dir) -> pd.DataFrame:
    rows = []
    for nb, w in REE_BORDERS.items():
        parts = {}
        for inc in ree(w, start, end_incl, cache_dir)["included"]:
            key = {"Exports": "export_mwh", "Imports": "import_mwh",
                   "saldo": "net_mwh"}.get(inc["type"])
            if key:
                parts[key] = _vals(inc["attributes"])
        for d in sorted(set().union(*[p.keys() for p in parts.values()])):
            rows.append({"date": d, "border": f"ES-{nb}",
                         **{k: v.get(d) for k, v in parts.items()}})
    return pd.DataFrame(rows)


def ree_lines(start, end_incl, cache_dir) -> pd.DataFrame:
    rows = []
    for nb, w in REE_LINES.items():
        for inc in ree(w, start, end_incl, cache_dir)["included"]:
            content = inc["attributes"].get("content") or []
            if not content:
                continue  # line listed but no data (e.g. not in service)
            name = content[0]["attributes"]["title"]
            exp_, imp_, net = (_vals(c["attributes"]) for c in content[:3])
            for d in net:
                rows.append({"date": d, "border": f"ES-{nb}", "line": name,
                             "export_mwh": exp_.get(d), "import_mwh": imp_.get(d),
                             "net_mwh": net[d]})
    return pd.DataFrame(rows)


def flat_hourly(borders: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """Daily net (Madrid day) -> flat hourly MW in UTC, in --extra-borders format.
    net_export_mw is positive when Spain exports."""
    out = []
    for _, r in borders[borders.border.isin(["ES-MA", "ES-AD"])].iterrows():
        d0 = pd.Timestamp(r.date, tz=TZ_ES)
        hrs = pd.date_range(d0, d0 + pd.Timedelta(days=1), freq="1h",
                            inclusive="left").tz_convert("UTC")
        mw = -float(r.net_mwh) / len(hrs)  # REE saldo: negative = export
        out += [{"hour_utc": h, "border": r.border, "net_export_mw": mw} for h in hrs]
    df = pd.DataFrame(out)
    t0, t1 = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC")
    return df[(df.hour_utc >= t0) & (df.hour_utc < t1)]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2025-04-25")
    ap.add_argument("--end", default="2025-05-03", help="exclusive, UTC")
    ap.add_argument("--cache", default="cache")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    cache, out = Path(a.cache), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    end_incl = (pd.Timestamp(a.end) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    # REE -------------------------------------------------------------------
    b = ree_borders(a.start, end_incl, cache)
    b.to_csv(out / "ree_daily_borders.csv", index=False)
    ln = ree_lines(a.start, end_incl, cache)
    ln.to_csv(out / "ree_daily_lines.csv", index=False)
    ex = flat_hourly(b, a.start, a.end)
    ex.to_csv(out / "extra_borders_ma_ad.csv", index=False)

    # Energy-Charts ES borders, summed to Madrid local days (MWh), import-positive
    cb = ec_frame(ec_request("cbpf", "ES", a.start, a.end, cache))
    day = cb.index.tz_convert(TZ_ES).strftime("%Y-%m-%d")
    # Patched copy: ES-FR gap refilled from RTE schedules, as the model does.
    # RTE ech_comm_espagne is positive = France imports = Spain exports, so the
    # Spain import-positive value is its negative.
    rte_es = -rte_hourly(a.start, a.end, cache)["ech_comm_espagne"]
    g0, g1 = (pd.Timestamp(x, tz="UTC") for x in ES_FR_GAP)
    fr_p = cb["france"].copy()
    gap = (fr_p.index >= g0) & (fr_p.index <= g1)
    fr_p[gap] = rte_es.reindex(fr_p.index[gap]).values
    ecd = cb[["france", "portugal"]].assign(france_patched=fr_p) \
        .groupby(day).sum(min_count=1)
    rows = []
    for nb, col in (("FR", "france"), ("PT", "portugal")):
        for d, v in ecd[col].items():
            r = b[(b.border == f"ES-{nb}") & (b.date == d)]
            if len(r):
                rows.append({"date": d, "border": f"ES-{nb}",
                             "energycharts_net_mwh": round(v),
                             "energycharts_patched_net_mwh": round(
                                 ecd.at[d, "france_patched"] if nb == "FR" else v),
                             "ree_net_mwh": r.net_mwh.iloc[0],
                             "ree_sum_of_lines_mwh": ln[(ln.border == f"ES-{nb}") &
                                                        (ln.date == d)].net_mwh.sum()})
    chk = pd.DataFrame(rows)
    chk["diff_raw_mwh"] = chk.energycharts_net_mwh - chk.ree_net_mwh
    chk["diff_patched_mwh"] = chk.energycharts_patched_net_mwh - chk.ree_net_mwh
    chk.to_csv(out / "check_es_borders_daily.csv", index=False)
    # Partial first/last Madrid days (UTC window edges) are not comparable.
    print("\nES borders, daily net MWh (import-positive):\n", chk.to_string(index=False))

    # RTE vs Energy-Charts, France hourly -------------------------------------
    rte = rte_hourly(a.start, a.end, cache)
    pp = ec_frame(ec_request("public_power", "FR", a.start, a.end, cache))
    fcb = ec_frame(ec_request("cbpf", "FR", a.start, a.end, cache))
    fr = pd.DataFrame({"rte_load": rte["consommation"],
                       "ec_load": pp.get("load"),
                       "rte_fr_es_commercial": rte["ech_comm_espagne"],
                       "ec_fr_es_physical": fcb.get("spain"),
                       "rte_net_physical": rte["ech_physiques"],
                       "ec_net_physical": fcb.get("sum")})
    for col, lab in RTE_FUELS.items():
        fr[f"rte_{lab}"] = rte[col]
    for sid in pp.columns:
        fr[f"ec_{sid}"] = pp[sid]
    fr.index.name = "hour_utc"
    fr.to_csv(out / "check_fr_hourly.csv")
    s = pd.DataFrame({
        "mean_abs_diff_mw": [(fr.rte_load - fr.ec_load).abs().mean(),
                             (fr.rte_net_physical - fr.ec_net_physical).abs().mean(),
                             (fr.rte_fr_es_commercial - fr.ec_fr_es_physical).abs().mean()],
        "mean_level_mw": [fr.rte_load.mean(), fr.rte_net_physical.abs().mean(),
                          fr.rte_fr_es_commercial.abs().mean()]},
        index=["FR load", "FR net physical exchange", "FR-ES commercial vs physical"])
    print("\nFrance, RTE vs Energy-Charts (hourly):\n", s.round(0).to_string())
    print(f"\nWrote {out}/ (credit: REE REData, RTE eCO2mix/ODRE, energy-charts.info)")


if __name__ == "__main__":
    main()
