#!/usr/bin/env python3
"""
build_network.py

Build the "lite" network folder that iberian_blackout_flows.py reads with
--network <folder>. No PyPSA or Snakemake needed.

Inputs (download once, see README):
  OSM prebuilt grid for PyPSA-Eur, Zenodo record 14144752 (v0.6, ODbL):
    buses.csv lines.csv links.csv transformers.csv converters.csv
  powerplantmatching powerplants.csv (PyPSA, MIT): plant locations by fuel
  Natural Earth ne_10m_populated_places_simple.geojson (public domain)

What it does
  - keeps AC buses in ES, PT, FR plus the outside buses one branch away
    (those become boundary stubs in the flow model)
  - lines keep OSM-derived reactance x (ohm), rating s_nom (MVA) and geometry
  - transformers get x = 0.1 per unit on s_nom (the PyPSA-Eur default)
  - HVDC links: DC end buses are moved to their AC converter buses
  - generators: plants in service in April 2025, snapped to the nearest
    >= 220 kV AC bus in the same country, carriers named as in PyPSA-Eur
  - loads: one weight per bus = 0.7 x population share + 0.3 x share of
    attached line capacity, per country. Population = Natural Earth places,
    each spread over nearby >= 220 kV buses with a 30 km Gaussian kernel.
    A demand proxy, not measured demand.

Usage
  python3 build_network.py --osm osm/ --plants powerplants.csv \
      --places ne_10m_populated_places_simple.geojson --out network/
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

MODEL = ["ES", "PT", "FR"]
PPM_COUNTRY = {"Spain": "ES", "Portugal": "PT", "France": "FR"}
EVENT_YEAR = 2025.32  # late April 2025


def read_osm(path: Path, name: str) -> pd.DataFrame:
    return pd.read_csv(path / f"{name}.csv", index_col=0, quotechar="'")


def ppm_carrier(fuel: str, tech) -> str | None:
    tech = str(tech)
    if fuel == "Nuclear":
        return "nuclear"
    if fuel == "Natural Gas":
        return "CCGT"
    if fuel == "Hard Coal":
        return "coal"
    if fuel == "Lignite":
        return "lignite"
    if fuel == "Oil":
        return "oil"
    if fuel in ("Solid Biomass", "Biogas", "Waste"):
        return "biomass"
    if fuel == "Geothermal":
        return "geothermal"
    if fuel == "Solar":
        return "solar"
    if fuel == "Wind":
        return "offwind-ac" if tech == "Offshore" else "onwind"
    if fuel == "Hydro":
        return {"Run-Of-River": "ror", "Pumped Storage": "PHS"}.get(tech, "hydro")
    return None  # batteries, heat/hydrogen storage: not in the generation data


def snap(lon, lat, country, buses: pd.DataFrame) -> np.ndarray:
    """Nearest bus in the same country (equirectangular distance)."""
    out = np.empty(len(lon), dtype=object)
    for c in MODEL:
        m = np.asarray(country) == c
        if not m.any():
            continue
        cand = buses[buses.country == c]
        cl = np.cos(np.radians(cand.y.mean()))
        bx, by = cand.x.values * cl, cand.y.values
        px, py = np.asarray(lon)[m] * cl, np.asarray(lat)[m]
        d = (px[:, None] - bx[None, :]) ** 2 + (py[:, None] - by[None, :]) ** 2
        out[m] = cand.index.values[d.argmin(axis=1)]
    return out


def spread(lon, lat, country, val, buses: pd.DataFrame, sigma_km: float) -> pd.Series:
    """Share each place's value over same-country buses with a Gaussian kernel,
    so a metro area loads several substations instead of one."""
    acc = pd.Series(0.0, index=buses.index)
    for c in MODEL:
        m = np.asarray(country) == c
        if not m.any():
            continue
        cand = buses[buses.country == c]
        cl = np.cos(np.radians(cand.y.mean()))
        dx = (np.asarray(lon)[m][:, None] - cand.x.values[None, :]) * cl * 111.2
        dy = (np.asarray(lat)[m][:, None] - cand.y.values[None, :]) * 111.2
        d2 = dx ** 2 + dy ** 2
        d2 -= d2.min(axis=1, keepdims=True)  # nearest bus always gets weight 1
        k = np.exp(-d2 / (2 * sigma_km ** 2))
        k /= k.sum(axis=1, keepdims=True)
        acc[cand.index] += (np.asarray(val)[m][:, None] * k).sum(axis=0)
    return acc


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--osm", required=True)
    ap.add_argument("--plants", required=True)
    ap.add_argument("--places", required=True)
    ap.add_argument("--out", default="network")
    a = ap.parse_args()
    osm, out = Path(a.osm), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    B = read_osm(osm, "buses")
    L = read_osm(osm, "lines")
    K = read_osm(osm, "links")
    TR = read_osm(osm, "transformers")
    CV = read_osm(osm, "converters")

    # HVDC: move DC ends onto their AC converter bus
    dc2ac = dict(zip(CV.bus0, CV.bus1))
    K = K.assign(bus0=K.bus0.map(dc2ac), bus1=K.bus1.map(dc2ac)).dropna(subset=["bus0", "bus1"])

    ac = B[B.dc.astype(str) == "f"]
    inside = set(ac.index[ac.country.isin(MODEL)])

    def touching(df):
        return df[df.bus0.isin(inside) | df.bus1.isin(inside)]

    L, K, TR = touching(L), touching(K), touching(TR)
    keep = inside | set(L.bus0) | set(L.bus1) | set(K.bus0) | set(K.bus1) \
        | set(TR.bus0) | set(TR.bus1)
    buses = ac.loc[ac.index.isin(keep), ["voltage", "x", "y", "country"]] \
        .rename(columns={"voltage": "v_nom"})
    buses.index.name = "bus"
    L = L[L.bus0.isin(buses.index) & L.bus1.isin(buses.index)]
    K = K[K.bus0.isin(buses.index) & K.bus1.isin(buses.index)]
    TR = TR[TR.bus0.isin(buses.index) & TR.bus1.isin(buses.index)]

    lines = pd.DataFrame({"bus0": L.bus0, "bus1": L.bus1, "x": L.x, "r": L.r,
                          "s_nom": L.s_nom, "v_nom": L.voltage, "length_m": L.length,
                          "circuits": L.circuits, "underground": L.underground,
                          "geometry": L.geometry})
    lines.index.name = "line"
    links = pd.DataFrame({"bus0": K.bus0, "bus1": K.bus1, "p_nom": K.p_nom,
                          "carrier": "DC", "v_nom": K.voltage, "length_m": K.length,
                          "geometry": K.geometry})
    links.index.name = "link"
    trafos = pd.DataFrame({"bus0": TR.bus0, "bus1": TR.bus1, "s_nom": TR.s_nom, "x": 0.1})
    trafos.index.name = "transformer"

    # Generators ----------------------------------------------------------------
    hv = buses[buses.index.isin(inside) & (buses.v_nom >= 220)]
    P = pd.read_csv(a.plants)
    P = P[P.Country.isin(PPM_COUNTRY)].copy()
    P["country"] = P.Country.map(PPM_COUNTRY)
    P = P[(P.DateIn.isna() | (P.DateIn <= EVENT_YEAR))
          & (P.DateOut.isna() | (P.DateOut > EVENT_YEAR))]
    P["carrier"] = [ppm_carrier(f, t) for f, t in zip(P.Fueltype, P.Technology)]
    P = P.dropna(subset=["carrier", "lat", "lon"])
    P["bus"] = snap(P.lon.values, P.lat.values, P.country.values, hv)
    gens = P.groupby(["bus", "carrier"]).Capacity.sum().reset_index() \
        .rename(columns={"Capacity": "p_nom"})
    gens.index = gens.bus + " " + gens.carrier
    gens.index.name = "generator"

    # Load weights --------------------------------------------------------------
    pl = json.loads(Path(a.places).read_text())["features"]
    pp = pd.DataFrame([f["properties"] for f in pl])
    pp = pp[pp.iso_a2.isin(MODEL) & (pp.pop_max > 0)]
    pop = spread(pp.longitude.values, pp.latitude.values, pp.iso_a2.values,
                 pp.pop_max.values, hv, sigma_km=30.0)
    capw = pd.concat([lines.groupby("bus0").s_nom.sum(),
                      lines.groupby("bus1").s_nom.sum()]).groupby(level=0).sum()
    w = []
    for c in MODEL:
        idx = hv.index[hv.country == c]
        ps = pop.reindex(idx).fillna(0)
        cs = capw.reindex(idx).fillna(0)
        w.append(0.7 * ps / ps.sum() + 0.3 * cs / cs.sum())
    loads = pd.DataFrame({"bus": pd.concat(w).index, "p_set": pd.concat(w).values})
    loads.index = "load " + loads.bus
    loads.index.name = "load"

    for name, df in (("buses", buses), ("lines", lines), ("links", links),
                     ("transformers", trafos), ("generators", gens), ("loads", loads)):
        df.to_csv(out / f"{name}.csv")
    print(f"{len(buses)} buses ({len(inside)} inside), {len(lines)} lines, "
          f"{len(links)} HVDC links, {len(trafos)} transformers, "
          f"{len(gens)} generator groups ({P.Capacity.sum()/1e3:.0f} GW), "
          f"{len(pp)} places -> {out}/")
    print(gens.groupby([gens.bus.map(buses.country), "carrier"]).p_nom.sum()
          .div(1e3).round(1).unstack(0).to_string())


if __name__ == "__main__":
    main()
