#!/usr/bin/env python3
"""
iberian_blackout_flows.py

Hourly *modelled* DC power flows on the Spain / Portugal / France transmission
network for the Iberian blackout week (default 2025-04-25 .. 2025-05-03 UTC).

Pipeline
  1. Hourly load, generation by fuel and cross-border physical flows from
     Energy-Charts (Fraunhofer ISE, CC BY 4.0, no token). ENTSO-E via entsoe-py
     is still supported with --source entsoe and ENTSOE_API_KEY.
  2. Patch a known Energy-Charts gap: ES-FR flow is a flat zero from 11:00 UTC
     28 April to 21:00 UTC 29 April while France was in fact supplying Spain.
     Those hours are refilled from RTE eCO2mix commercial schedules (FR-ES),
     see patch_es_fr_gap(). crosscheck_sources.py checks the result against REE
     daily measured line totals.
  3. Load the network (a lite CSV folder from build_network.py, or a PyPSA-Eur
     .nc) and clip it to ES, PT, FR. Branches that leave the area become
     external injections equal to the observed border flows. Morocco and
     Andorra (not in the OSM grid) are injected at their Spanish border buses
     from --extra-borders.
     France load and generation come from RTE eCO2mix (--fr-source rte).
  4. Distribute country load and generation onto buses. Calibrate each
     country's net position to its measured border totals, then balance each
     AC island (residuals written to balancing_residuals.csv).
  5. Solve a DC power flow per hour (own solver, one factorisation per component).
  6. Write flows (long table), line geometry (GeoJSON) and a validation table
     comparing modelled vs measured flow on ES-FR and ES-PT.

These are modelled flows on a real topology, calibrated to measured border
data. They are NOT line-level measurements. DC power flow ignores voltage and
reactive power, so it cannot show the mechanism of the blackout.

Setup
  pip install pandas numpy scipy shapely pyarrow      (pypsa only for .nc input)

Usage (see README.md for the full run)
  python3 build_network.py ...                         # once, writes network/
  python3 crosscheck_sources.py                        # REE + RTE, writes out/
  python3 iberian_blackout_flows.py --network network \
      --extra-borders out/extra_borders_ma_ad.csv --out out
  python3 iberian_blackout_flows.py --selftest
  python3 iberian_blackout_flows.py --probe            # check Energy-Charts parsing
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("flows")

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
MODEL = ["ES", "PT", "FR"]

# Network country code -> ENTSO-E zone used for the imposed border flows.
# Codes missing here (AD, MA, MC, ...) get no imposed flow unless supplied via
# --extra-borders.
NET2ZONE = {"BE": "BE", "DE": "DE_LU", "LU": "DE_LU", "CH": "CH",
            "IT": "IT_NORD", "GB": "GB"}

# NaNs in ES/PT series inside this window (UTC) are filled with 0, because the
# grid really was down. Measured values are never overwritten.
BLACKOUT_FILL_WINDOW = ("2025-04-28 10:00", "2025-04-28 20:00")

# Borders with no line in the OSM grid: inject at the nearest in-model bus
# (>= 220 kV) to these points. Puerto de la Cruz (Tarifa) for the Morocco
# cables, Adrall/La Seu d'Urgell for Andorra.
EXTRA_BORDER_POINTS = {"ES-MA": (-5.60, 36.03), "ES-AD": (1.44, 42.36)}

# Energy-Charts ES-FR gap (UTC, inclusive), refilled from RTE schedules.
ES_FR_GAP = ("2025-04-28 11:00", "2025-04-29 21:00")
# Spain from the collapse to the end of the Energy-Charts gap (UTC, inclusive):
# load replaced by REE measured peninsular demand, generation rescaled to it.
ES_BLACKOUT = ("2025-04-28 10:00", "2025-04-29 21:00")
REE_DEMAND = ("https://apidatos.ree.es/en/datos/demanda/evolucion?start_date={s}T00:00"
              "&end_date={e}T23:59&time_trunc=hour&geo_trunc=electric_system"
              "&geo_limit=peninsular&geo_ids=8741")
VRE = ("Solar", "Wind Onshore", "Wind Offshore")

# REE interconnector line title -> model branch ids (matched by end substations
# on the OSM geometry). Used for outages (REE shows zero flow both ways for a
# day) and for the HVDC daily total. validate_lines.py uses the same table.
REE_LINE_BRANCHES = {
    "Hernani - Argia": ["L:relation/8481943-400-b"],
    "Arkale - Argia": ["L:merged_relation/8481942-225-e+4"],
    "Biescas - Pragnéres": ["L:merged_relation/8423568-225-b+1"],
    "Vic - Baixas": ["L:relation/6530789-400"],
    "Santa Llogaia - Baixas": ["K:relation/9934065-320-DC", "K:relation/9934066-320-DC"],
    "Cartelle - Lindoso": ["L:way/137265337-400", "L:way/137265338-400"],
    "Cedillo - Falagueira": ["L:merged_way/144599064-400+1"],
    "Brovales - Alqueva": ["L:merged_way/747519549-400+1"],
    "Puebla de Guzmán - Tavira": ["L:merged_way/215856860-400+1"],
}
HVDC_REE = "Santa Llogaia - Baixas"
TZ_ES = "Europe/Madrid"

# RTE eCO2mix column -> production type (France load and generation from RTE).
# eCO2mix gives total wind only; it is mapped to onshore (offshore was ~1 GW).
RTE_PSR = {"nucleaire": "Nuclear", "gaz": "Fossil Gas", "charbon": "Fossil Hard coal",
           "fioul": "Fossil Oil", "eolien": "Wind Onshore", "solaire": "Solar",
           "hydraulique_fil_eau_eclusee": "Hydro Run-of-river and poundage",
           "hydraulique_lacs": "Hydro Water Reservoir",
           "hydraulique_step_turbinage": "Hydro Pumped Storage",
           "pompage": "Hydro Pumped Storage", "bioenergies": "Biomass"}
RTE_ODRE = ("https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets/"
            "eco2mix-national-cons-def/exports/json?")

# ENTSO-E production type -> PyPSA-Eur carrier names (generators + storage units)
PSR_TO_CARRIERS = {
    "Solar": ["solar"],
    "Wind Onshore": ["onwind"],
    "Wind Offshore": ["offwind-ac", "offwind-dc", "offwind"],
    "Hydro Run-of-river and poundage": ["ror"],
    "Hydro Water Reservoir": ["hydro"],
    "Hydro Pumped Storage": ["PHS"],
    "Nuclear": ["nuclear"],
    "Fossil Gas": ["CCGT", "OCGT", "gas"],
    "Fossil Hard coal": ["coal"],
    "Fossil Brown coal/Lignite": ["lignite"],
    "Fossil Oil": ["oil"],
    "Biomass": ["biomass"],
    "Geothermal": ["geothermal"],
}


# --------------------------------------------------------------------------- #
# DC power-flow solver (no PyPSA dependency)
# --------------------------------------------------------------------------- #
def solve_dc(n_nodes: int, i0: np.ndarray, i1: np.ndarray, b: np.ndarray,
             P: np.ndarray) -> np.ndarray:
    """DC power flow.

    n_nodes : number of buses
    i0, i1  : branch end indices (flow is positive from i0 to i1)
    b       : branch susceptance in MW/rad (v_nom^2/x for lines, s_nom/x for transformers)
    P       : (n_nodes, T) net injections in MW (generation positive)
    Returns : (n_branches, T) flows in MW.

    One slack bus per connected component (highest degree). Injections inside a
    component should already sum to ~0; the slack absorbs any remainder.
    """
    from scipy import sparse as sp
    from scipy.sparse.csgraph import connected_components
    from scipy.sparse.linalg import splu

    m = len(b)
    rows = np.r_[np.arange(m), np.arange(m)]
    cols = np.r_[i0, i1]
    vals = np.r_[np.ones(m), -np.ones(m)]
    K = sp.csr_matrix((vals, (rows, cols)), shape=(m, n_nodes))
    B = (K.T @ sp.diags(b) @ K).tocsc()

    adj = sp.coo_matrix((np.ones(m), (i0, i1)), shape=(n_nodes, n_nodes))
    ncomp, label = connected_components(adj, directed=False)
    degree = np.asarray((abs(K)).sum(axis=0)).ravel()

    theta = np.zeros_like(P, dtype=float)
    for k in range(ncomp):
        nodes = np.where(label == k)[0]
        if len(nodes) < 2:
            continue
        slack = nodes[np.argmax(degree[nodes])]
        free = nodes[nodes != slack]
        Bff = B[free][:, free].tocsc()
        lu = splu(Bff)
        theta[free] = lu.solve(np.ascontiguousarray(P[free]))
    return b[:, None] * (K @ theta)


def selftest() -> None:
    # Triangle with equal susceptances: 100 MW from bus 0 to bus 2.
    # Direct path carries 2/3, two-hop path carries 1/3.
    i0 = np.array([0, 0, 1])
    i1 = np.array([2, 1, 2])
    b = np.array([1000.0, 1000.0, 1000.0])
    P = np.array([[100.0], [0.0], [-100.0]])
    f = solve_dc(3, i0, i1, b, P)[:, 0]
    assert np.allclose(f, [200 / 3, 100 / 3, 100 / 3]), f
    # Two disconnected components solve independently.
    i0 = np.array([0, 2]); i1 = np.array([1, 3]); b = np.array([500.0, 800.0])
    P = np.array([[10.0], [-10.0], [-5.0], [5.0]])
    f = solve_dc(4, i0, i1, b, P)[:, 0]
    assert np.allclose(f, [10.0, -5.0]), f
    print("selftest OK")


# --------------------------------------------------------------------------- #
# ENTSO-E data
# --------------------------------------------------------------------------- #
def _hourly(x: pd.Series | pd.DataFrame):
    return x.tz_convert("UTC").resample("1h").mean()


# --------------------------------------------------------------------------- #
# Energy-Charts data (no API token needed; CC BY 4.0, credit energy-charts.info)
# --------------------------------------------------------------------------- #
EC_BASE = "https://api.energy-charts.info/v2/"

# Energy-Charts neighbour series id -> flow key used by the model
EC_NAME2ZONE = {"spain": "ES", "portugal": "PT", "france": "FR", "belgium": "BE",
                "germany": "DE_LU", "luxembourg": "DE_LU", "switzerland": "CH",
                "italy": "IT_NORD", "united_kingdom": "GB", "great_britain": "GB",
                "uk": "GB", "morocco": "MA", "andorra": "AD"}


def ec_request(path: str, country: str, start: str, end: str, cache_dir: Path) -> dict:
    """GET one Energy-Charts v2 endpoint. Cached on disk; honours the rate limit
    (2 requests/min) and Retry-After on HTTP 429."""
    import time
    import urllib.error
    import urllib.parse
    import urllib.request

    cache = cache_dir / f"ec_{path}_{country.lower()}_{start}_{end}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    q = urllib.parse.urlencode({"country": country.lower(),
                                "start": f"{start}T00:00Z", "end": f"{end}T00:00Z"})
    url = f"{EC_BASE}{path}?{q}"
    for _ in range(6):
        try:
            log.info("GET %s", url)
            req = urllib.request.Request(url, headers={"User-Agent": "iberian-blackout-flows/1.0"})
            with urllib.request.urlopen(req, timeout=120) as r:
                j = json.loads(r.read().decode())
            break
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = int(e.headers.get("Retry-After", "40"))
                log.warning("Rate limited, waiting %ds", wait)
                time.sleep(wait + 1)
                continue
            raise
    else:
        sys.exit(f"Energy-Charts kept rate-limiting {url}")
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(j))
    time.sleep(31)  # stay under 2 requests/minute
    return j


def ec_frame(j: dict) -> pd.DataFrame:
    """v2 envelope -> hourly MW DataFrame (UTC), one column per series id."""
    recs = j["data"]
    idx = pd.to_datetime([r["timestamp"] for r in recs], utc=True)
    df = pd.DataFrame([r["values"] for r in recs], index=idx).astype(float)
    unit = str(j.get("unit", "MW")).upper()
    scale = {"GW": 1000.0, "MW": 1.0, "KW": 1e-3}.get(unit)
    if scale is None:
        sys.exit(f"Unexpected Energy-Charts unit {unit!r}")
    df = df * scale
    df.columns = [str(c).lower().replace(" ", "_").replace("-", "_") for c in df.columns]
    return df.resample("1h").mean()


def ec_psr(sid: str) -> str | None:
    """Map an Energy-Charts series id to an ENTSO-E production type name."""
    if sid in ("sum", "total", "load") or any(
            k in sid for k in ("residual", "import", "export", "balance", "forecast",
                               "share", "price", "cross_border", "trading")):
        return None
    # Pumping and battery charging are negative "generation" at the plant bus
    # (ENTSO-E load excludes them). Note: "consumption" contains "sum".
    if "solar" in sid:
        return "Solar"
    if "wind" in sid:
        return "Wind Offshore" if "off" in sid else "Wind Onshore"
    if "pump" in sid:
        return "Hydro Pumped Storage"
    if "river" in sid or sid in ("ror", "hydro_ror"):
        return "Hydro Run-of-river and poundage"
    if "reservoir" in sid or sid in ("hydro", "hydro_water", "water"):
        return "Hydro Water Reservoir"
    if "nuclear" in sid:
        return "Nuclear"
    if "gas" in sid:
        return "Fossil Gas"
    if "lignite" in sid or "brown" in sid:
        return "Fossil Brown coal/Lignite"
    if "coal" in sid:
        return "Fossil Hard coal"
    if "oil" in sid:
        return "Fossil Oil"
    if "biomass" in sid:
        return "Biomass"
    if "geothermal" in sid:
        return "Geothermal"
    return "Other"


def fetch_energycharts(start: str, end: str, cache_dir: Path) -> dict:
    data = {"load": {}, "gen": {}, "flow": {}, "extra": {}}
    for c in MODEL:
        pp = ec_frame(ec_request("public_power", c, start, end, cache_dir))
        cb = ec_frame(ec_request("cbpf", c, start, end, cache_dir))
        log.info("%s public_power series: %s", c, ", ".join(pp.columns))
        log.info("%s cbpf series: %s", c, ", ".join(cb.columns))

        groups: dict[str, list] = {}
        load = None
        for sid in pp.columns:
            if sid == "load":  # exact match: not residual_load or renewable_share_of_load
                load = pp[sid]
                continue
            psr = ec_psr(sid)
            if psr is not None:
                groups.setdefault(psr, []).append(pp[sid])
        gen = pd.DataFrame({k: pd.concat(v, axis=1).sum(axis=1, min_count=1)
                            for k, v in groups.items()})
        data["gen"][c] = gen
        if load is None:
            # No load series: load = generation + net imports (energy balance).
            imp = cb["sum"] if "sum" in cb else cb.sum(axis=1, min_count=1)
            load = gen.sum(axis=1, min_count=1) + imp
            log.warning("%s: no load series, derived as generation + net imports", c)
        data["load"][c] = load

        export: dict[str, pd.Series] = {}
        for sid in cb.columns:
            if sid in ("sum", "total"):
                continue
            z = EC_NAME2ZONE.get(sid)
            if z is None:
                log.info("%s: ignoring border series %r", c, sid)
                continue
            export[z] = export.get(z, 0) - cb[sid]  # cbpf: positive = import
        for z, ser in export.items():
            if z in ("MA", "AD"):
                data["extra"][f"{c}-{z}"] = ser
            elif (z, c) not in data["flow"]:  # store each pair once, from one side
                data["flow"][(c, z)] = ser
    return data


def probe(args) -> None:
    """Fetch one day for ES and print what Energy-Charts returns, to check parsing."""
    d0 = pd.Timestamp(args.start)
    d1 = (d0 + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    for path in ("public_power", "cbpf"):
        j = ec_request(path, "es", args.start, d1, Path(args.cache))
        print(f"--- {path}: unit={j.get('unit')} resolution={j.get('resolution')} "
              f"tz={j.get('timezone')}")
        print("series:", [s.get("id") for s in j.get("series", [])])
        print("first record:", json.dumps(j["data"][0])[:600])


def fetch_data(args) -> dict:
    if args.source == "energycharts":
        # Parse from the cached raw JSON every run (cheap), so parser fixes apply.
        data = fetch_energycharts(args.start, args.end, Path(args.cache))
        if not args.no_patch:
            patch_es_fr_gap(data, args.start, args.end, Path(args.cache))
            patch_es_blackout(data, args.start, args.end, Path(args.cache))
        if args.fr_source == "rte":
            use_rte_france(data, args.start, args.end, Path(args.cache))
        return data
    return fetch_entsoe(args.start, args.end, Path(args.cache))


def rte_hourly(start: str, end: str, cache_dir: Path) -> pd.DataFrame:
    """RTE eCO2mix definitive national data via ODRE (Licence Ouverte), hourly
    mean, UTC. ech_comm_* are commercial schedules, positive = import to France.
    ODRE blocks some cloud IPs; run from a normal connection once, it is cached."""
    import urllib.parse
    import urllib.request

    cache = cache_dir / f"rte_eco2mix_{start}_{end}.json"
    if cache.exists():
        j = json.loads(cache.read_text())
    else:
        where = (f'date_heure>="{start}T00:00:00+00:00" and '
                 f'date_heure<"{end}T00:00:00+00:00"')
        url = RTE_ODRE + urllib.parse.urlencode({"where": where, "order_by": "date_heure"})
        log.info("GET %s", url[:120])
        with urllib.request.urlopen(url, timeout=120) as r:
            j = json.loads(r.read().decode())
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(j))
    df = pd.DataFrame(j)
    df.index = pd.to_datetime(df.pop("date_heure"), utc=True)
    return df.apply(pd.to_numeric, errors="coerce").resample("1h").mean()


def ree_demand_hourly(start: str, end: str, cache_dir: Path) -> pd.Series:
    """REE REData measured peninsular demand, hourly mean MW, UTC index."""
    import urllib.request

    cache = cache_dir / f"ree_demanda_hour_{start}_{end}.json"
    if cache.exists():
        j = json.loads(cache.read_text())
    else:
        url = REE_DEMAND.format(s=start, e=end)
        log.info("GET %s", url[:120])
        with urllib.request.urlopen(url, timeout=120) as r:
            j = json.loads(r.read().decode())
        if j.get("errors"):
            sys.exit(f"REE demand: {j['errors']}")
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(j))
    v = j["included"][0]["attributes"]["values"]
    idx = pd.to_datetime([x["datetime"] for x in v], utc=True)
    return pd.Series([float(x["value"]) for x in v], index=idx)


def patch_es_blackout(data: dict, start: str, end: str, cache_dir: Path) -> None:
    """Energy-Charts Spain is unusable from the collapse until 21:00 UTC on
    29 April: load is missing, and generation shows ~5 GW of solar and ~2 GW of
    wind in the hour after the collapse, when REE measured demand was ~500 MW.
    Inside ES_BLACKOUT:
      load = REE measured peninsular demand (hourly mean)
      generation target = load + measured net exports (FR patched, PT)
      dispatchable fuels (hydro, gas, PHS, ...) keep their Energy-Charts shape
      and are scaled down if they alone exceed the target; wind and solar only
      fill what is left, capped at their Energy-Charts values.
    Morocco and Andorra are left to the per-country balancing step."""
    ree = ree_demand_hourly(start, end, cache_dir)
    w0, w1 = (pd.Timestamp(x, tz="UTC") for x in ES_BLACKOUT)
    load = data["load"]["ES"].copy()
    win = (load.index >= w0) & (load.index <= w1)
    ok = ~win & load.notna()
    common = load[ok].index.intersection(ree.index)
    log.info("ES load, Energy-Charts vs REE outside the blackout window: "
             "mean abs diff %.0f MW on mean %.0f MW",
             (load[common] - ree[common]).abs().mean(), ree[common].mean())
    load[win] = ree.reindex(load.index[win]).values
    data["load"]["ES"] = load

    exp = sum(data["flow"][k].reindex(load.index).fillna(0.0)
              for k in (("ES", "FR"), ("ES", "PT")) if k in data["flow"])
    gen = data["gen"]["ES"].copy()
    vre = [c for c in gen.columns if c in VRE]
    dis = [c for c in gen.columns if c not in VRE]
    before = gen[win].sum(axis=1).sum()
    for t in load.index[win]:
        target = max(load[t] + exp[t], 0.0)
        d = gen.loc[t, dis].fillna(0.0)
        dsum = d.sum()
        if dsum >= target:
            gen.loc[t, dis] = d * (target / dsum) if dsum > 0 else 0.0
            gen.loc[t, vre] = 0.0
        else:
            v = gen.loc[t, vre].fillna(0.0)
            room = target - dsum
            gen.loc[t, vre] = v * min(1.0, room / v.sum()) if v.sum() > 0 else 0.0
    data["gen"]["ES"] = gen
    data.setdefault("patched", {})["ES-blackout"] = (w0, w1)
    log.warning("Patched ES load/generation %s..%s (%d h): load from REE, "
                "generation %.0f -> %.0f MWh", w0, w1, win.sum(), before,
                gen[win].sum(axis=1).sum())


def use_rte_france(data: dict, start: str, end: str, cache_dir: Path) -> None:
    """France load and generation from RTE eCO2mix (the TSO's definitive data)
    instead of Energy-Charts, whose French pumped-storage consumption drops to
    zero on 1-2 May and leaves a 4-6 GW hole. Borders stay on Energy-Charts."""
    rte = rte_hourly(start, end, cache_dir)
    gen = pd.DataFrame({})
    for col, psr in RTE_PSR.items():
        gen[psr] = gen[psr] + rte[col] if psr in gen else rte[col]
    data["gen"]["FR"] = gen
    data["load"]["FR"] = rte["consommation"]
    log.info("FR load and generation from RTE eCO2mix: mean load %.0f MW, "
             "mean generation %.0f MW", rte["consommation"].mean(), gen.sum(axis=1).mean())


def patch_es_fr_gap(data: dict, start: str, end: str, cache_dir: Path) -> None:
    """Energy-Charts reports ES-FR physical flow as exactly 0 from 11:00 UTC on
    28 April to 21:00 UTC on 29 April. REE line data shows France was supplying
    Spain during restoration, so the zeros are missing data, not physics.
    Refill those hours with RTE's FR-ES commercial schedule. RTE positive =
    France imports from Spain = Spain exports, which is the ES->FR sign here."""
    key = ("ES", "FR") if ("ES", "FR") in data["flow"] else ("FR", "ES")
    s = data["flow"][key].copy()
    g0, g1 = (pd.Timestamp(x, tz="UTC") for x in ES_FR_GAP)
    gap = (s.index >= g0) & (s.index <= g1)
    if not gap.any():
        return
    zeros = int((s[gap].fillna(0) == 0).sum())
    if zeros < gap.sum() * 0.9:
        log.info("ES-FR gap window is not all zero (%d/%d): no patch", zeros, gap.sum())
        return
    rte = rte_hourly(start, end, cache_dir)["ech_comm_espagne"]
    fill = rte.reindex(s.index[gap])
    s[gap] = fill.values if key == ("ES", "FR") else -fill.values
    data["flow"][key] = s
    data.setdefault("patched", {})["ES-FR"] = (g0, g1)
    log.warning("Patched ES-FR %s..%s (%d h) from RTE schedules: net %.0f MWh "
                "(positive = Spain exports)", g0, g1, gap.sum(),
                fill.sum() if key == ("ES", "FR") else -fill.sum())


def fetch_entsoe(start: str, end: str, cache_dir: Path) -> dict:
    cache = cache_dir / f"entsoe_{start}_{end}.pkl"
    if cache.exists():
        log.info("Using cached ENTSO-E data %s", cache)
        return pd.read_pickle(cache)

    from entsoe import EntsoePandasClient

    key = os.environ.get("ENTSOE_API_KEY")
    if not key:
        sys.exit("Set ENTSOE_API_KEY (free token from transparency.entsoe.eu).")
    cl = EntsoePandasClient(api_key=key)
    s, e = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC")

    data = {"load": {}, "gen": {}, "flow": {}}
    for c in MODEL:
        log.info("Fetching load and generation for %s", c)
        ld = cl.query_load(c, start=s, end=e)
        if isinstance(ld, pd.DataFrame):
            ld = ld.iloc[:, 0]
        data["load"][c] = _hourly(ld)

        g = cl.query_generation(c, start=s, end=e, psr_type=None)
        if isinstance(g.columns, pd.MultiIndex):
            lv = g.columns.get_level_values(1)
            agg = g.loc[:, lv == "Actual Aggregated"].copy()
            agg.columns = agg.columns.get_level_values(0)
            con = g.loc[:, lv == "Actual Consumption"].copy()
            con.columns = con.columns.get_level_values(0)
            g = agg.sub(con.reindex(columns=agg.columns).fillna(0))
        data["gen"][c] = _hourly(g)

    zones = sorted(set(NET2ZONE.values()))
    pairs = [("ES", "FR"), ("FR", "ES"), ("ES", "PT"), ("PT", "ES")]
    for z in zones:
        pairs += [("FR", z), (z, "FR")]
    for a, b in pairs:
        try:
            log.info("Fetching physical flow %s -> %s", a, b)
            data["flow"][(a, b)] = _hourly(
                cl.query_crossborder_flows(a, b, start=s, end=e))
        except Exception as ex:  # no data / unsupported pair
            log.warning("No flow data for %s -> %s (%s)", a, b, type(ex).__name__)

    cache_dir.mkdir(parents=True, exist_ok=True)
    pd.to_pickle(data, cache)
    return data


def clean_series(s: pd.Series, country: str, T: pd.DatetimeIndex, name: str) -> pd.Series:
    s = s.reindex(T).interpolate(limit=3, limit_area="inside")
    if country in ("ES", "PT"):
        w0, w1 = (pd.Timestamp(x, tz="UTC") for x in BLACKOUT_FILL_WINDOW)
        mask = (T >= w0) & (T <= w1) & s.isna().values
        if mask.any():
            log.warning("%s %s: %d NaN hours inside blackout window set to 0",
                        country, name, mask.sum())
            s[mask] = 0.0
    if s.isna().any():
        log.warning("%s %s: %d NaN hours remain, ffill/0 applied",
                    country, name, int(s.isna().sum()))
        s = s.ffill().fillna(0.0)
    return s


def net_export(data: dict, a: str, b: str, T: pd.DatetimeIndex) -> pd.Series | None:
    fa, fb = data["flow"].get((a, b)), data["flow"].get((b, a))
    if fa is None and fb is None:
        return None
    fa = (fa if fa is not None else pd.Series(0.0, index=T)).reindex(T)
    fb = (fb if fb is not None else pd.Series(0.0, index=T)).reindex(T)
    return (fa - fb).interpolate(limit=3, limit_area="inside").fillna(0.0)


# --------------------------------------------------------------------------- #
# Network
# --------------------------------------------------------------------------- #
def load_network(path: Path):
    """A folder of CSVs from build_network.py, or a PyPSA(-Eur) .nc file."""
    if path.is_dir():
        from types import SimpleNamespace

        def rd(name):
            f = path / f"{name}.csv"
            return pd.read_csv(f, index_col=0) if f.exists() else pd.DataFrame()

        buses = rd("buses")
        buses.index = buses.index.astype(str)
        return SimpleNamespace(buses=buses, lines=rd("lines"), links=rd("links"),
                               transformers=rd("transformers"),
                               generators=rd("generators"), loads=rd("loads"),
                               storage_units=pd.DataFrame())
    import pypsa
    return pypsa.Network(str(path))


def build_branches(n) -> pd.DataFrame:
    """All branches as one table: id, kind, bus0, bus1, b (MW/rad, AC), cap (MW)."""
    vn = n.buses["v_nom"]
    rows = []
    L = n.lines
    if len(L):
        x = L["x"].astype(float)
        b = vn.reindex(L.bus0).values ** 2 / x.values
        cap = L["s_nom"].where(L["s_nom"] > 0, L.get("s_nom_opt", 0)).astype(float)
        rows.append(pd.DataFrame({"id": "L:" + L.index.astype(str), "kind": "line",
                                  "bus0": L.bus0.values, "bus1": L.bus1.values,
                                  "b": b, "cap": cap.values}))
    T_ = getattr(n, "transformers", None)
    if T_ is not None and len(T_):
        x = T_["x"].astype(float)
        b = T_["s_nom"].astype(float).values / x.values
        rows.append(pd.DataFrame({"id": "T:" + T_.index.astype(str), "kind": "trafo",
                                  "bus0": T_.bus0.values, "bus1": T_.bus1.values,
                                  "b": b, "cap": T_["s_nom"].astype(float).values}))
    K_ = n.links
    if len(K_):
        K_ = K_[K_.carrier.astype(str).str.upper() == "DC"]
        rows.append(pd.DataFrame({"id": "K:" + K_.index.astype(str), "kind": "dc",
                                  "bus0": K_.bus0.values, "bus1": K_.bus1.values,
                                  "b": np.nan, "cap": K_["p_nom"].astype(float).values}))
    br = pd.concat(rows, ignore_index=True)
    bad = (br.kind != "dc") & ~(np.isfinite(br.b) & (br.b > 0))
    if bad.any():
        log.warning("Dropping %d AC branches with invalid reactance", int(bad.sum()))
        br = br[~bad].reset_index(drop=True)
    return br


def bus_weights(n, buses: pd.Index, csv: Path | None) -> pd.Series:
    if csv:
        w = pd.read_csv(csv, index_col=0).iloc[:, 0]
    elif len(n.loads):
        if hasattr(n, "loads_t") and not n.loads_t.p_set.empty:
            lw = n.loads_t.p_set.mean()
        else:
            lw = n.loads["p_set"]
        w = lw.groupby(n.loads.bus.reindex(lw.index)).sum()
    else:
        log.warning("Network has no loads: using uniform bus weights. "
                    "Supply --bus-weights or a network with loads (elec_s_*.nc).")
        w = pd.Series(1.0, index=buses)
    w = w.reindex(buses).fillna(0.0).clip(lower=0)
    for c in MODEL:
        idx = n.buses.loc[buses].index[n.buses.loc[buses, "country"] == c]
        if w[idx].sum() <= 0:
            log.warning("No load weight in %s: using uniform", c)
            w[idx] = 1.0
    return w


def gen_table(n) -> pd.DataFrame:
    parts = []
    for comp in ("generators", "storage_units"):
        t = getattr(n, comp, None)
        if t is not None and len(t):
            cap = t["p_nom"].where(t["p_nom"] > 0, t.get("p_nom_max", 0))
            parts.append(pd.DataFrame({"bus": t.bus.values, "carrier": t.carrier.values,
                                       "cap": cap.fillna(0).values}))
    if not parts:
        return pd.DataFrame(columns=["bus", "carrier", "cap"])
    return pd.concat(parts, ignore_index=True)


# --------------------------------------------------------------------------- #
# Main model
# --------------------------------------------------------------------------- #
def run(args) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    T = pd.date_range(args.start, args.end, freq="1h", tz="UTC", inclusive="left")

    data = fetch_data(args)
    n = load_network(Path(args.network))
    buses_all = n.buses
    if "country" not in buses_all:
        sys.exit("Network buses need a 'country' column (PyPSA-Eur networks have one).")

    inside = buses_all.index[buses_all.country.isin(MODEL)]
    pos = {b: i for i, b in enumerate(inside)}
    nb = len(inside)
    country = buses_all.loc[inside, "country"].values

    br_all = build_branches(n)
    in0, in1 = br_all.bus0.isin(inside), br_all.bus1.isin(inside)
    br = br_all[in0 & in1].reset_index(drop=True)
    stubs = br_all[in0 ^ in1].copy()
    log.info("%d buses, %d internal branches, %d boundary branches",
             nb, len(br), len(stubs))

    w_all = bus_weights(n, inside, Path(args.bus_weights) if args.bus_weights else None)
    wl = w_all.values.astype(float)

    P = np.zeros((nb, len(T)))

    # -- load and generation ------------------------------------------------ #
    gt = gen_table(n)
    gt = gt[gt.bus.isin(inside)]
    for c in MODEL:
        bidx = np.where(country == c)[0]
        wc = wl[bidx] / wl[bidx].sum()

        load = clean_series(data["load"][c], c, T, "load").values
        P[bidx] -= np.outer(wc, load)

        gen = data["gen"][c]
        placed = np.zeros(len(T))
        for psr in gen.columns:
            series = clean_series(gen[psr], c, T, psr).values
            carriers = PSR_TO_CARRIERS.get(psr, [])
            sub = gt[gt.carrier.isin(carriers)
                     & gt.bus.map(lambda b: b in pos and country[pos[b]] == c)]
            wg = np.zeros(len(bidx))
            if len(sub) and sub.cap.sum() > 0:
                agg = sub.groupby("bus").cap.sum()
                for b_name, v in agg.items():
                    wg[np.where(bidx == pos[b_name])[0][0]] = v
                wg /= wg.sum()
            else:
                wg = wc  # unmatched fuel types follow load weights
            P[bidx] += np.outer(wg, series)
            placed += series
        log.info("%s: mean generation %.0f MW, mean load %.0f MW",
                 c, placed.mean(), load.mean())

    # -- imposed external border flows ------------------------------------- #
    extra = None
    if args.extra_borders:
        extra = pd.read_csv(args.extra_borders, parse_dates=["hour_utc"])
        extra["hour_utc"] = pd.to_datetime(extra["hour_utc"], utc=True)

    def border_series(c_in: str, c_out: str) -> pd.Series | None:
        zone = NET2ZONE.get(c_out)
        if zone is not None:
            return net_export(data, c_in, zone, T)
        auto = data.get("extra", {}).get(f"{c_in}-{c_out}")
        if auto is not None:
            return auto.reindex(T).interpolate(limit=3, limit_area="inside").fillna(0.0)
        if extra is not None:
            key = f"{c_in}-{c_out}"
            e = extra[extra.border == key].set_index("hour_utc")["net_export_mw"]
            if len(e):
                return e.reindex(T).interpolate(limit=3, limit_area="inside").fillna(0.0)
        return None

    if len(stubs):
        stubs["in_bus"] = np.where(stubs.bus0.isin(inside), stubs.bus0, stubs.bus1)
        stubs["out_bus"] = np.where(stubs.bus0.isin(inside), stubs.bus1, stubs.bus0)
        stubs["c_in"] = buses_all.loc[stubs.in_bus, "country"].values
        stubs["c_out"] = buses_all.loc[stubs.out_bus, "country"].values
        stubs["share_cap"] = stubs.cap.fillna(0).clip(lower=1.0)
        for (c_in, c_out), grp in stubs.groupby(["c_in", "c_out"]):
            ser = border_series(c_in, c_out)
            if ser is None:
                log.info("No border data for %s-%s (%d branches): no flow imposed",
                         c_in, c_out, len(grp))
                continue
            # LU shares the DE_LU zone with DE: split zone flow by capacity share
            if c_out in ("DE", "LU"):
                tot = stubs[(stubs.c_in == c_in) & stubs.c_out.isin(["DE", "LU"])].share_cap.sum()
                ser = ser * (grp.share_cap.sum() / tot)
            for _, r in grp.iterrows():
                P[pos[r.in_bus]] -= ser.values * (r.share_cap / grp.share_cap.sum())

    # Borders with no branch in the network (Morocco, Andorra): inject the
    # measured exchange at the nearest in-model HV bus to a fixed point.
    stub_pairs = set()
    if len(stubs):
        stub_pairs = {f"{a}-{b}" for a, b in zip(stubs.c_in, stubs.c_out)}
    hv = buses_all.loc[inside]
    hv = hv[hv.v_nom >= 220]
    for key, (lon, lat) in EXTRA_BORDER_POINTS.items():
        if key in stub_pairs:
            continue
        c_in, c_out = key.split("-")
        ser = border_series(c_in, c_out)
        if ser is None:
            log.info("No data for %s and no branch in the network: skipped", key)
            continue
        cand = hv[hv.country == c_in]
        d = (cand.x - lon) ** 2 * np.cos(np.radians(lat)) ** 2 + (cand.y - lat) ** 2
        b_name = d.idxmin()
        P[pos[b_name]] -= ser.values
        log.info("%s: %.0f MW mean net export injected at %s", key, ser.mean(), b_name)

    # REE daily line data: HVDC totals and outages
    ree_lines = None
    if args.ree_lines and Path(args.ree_lines).exists():
        ree_lines = pd.read_csv(args.ree_lines)
        ree_lines["date"] = ree_lines["date"].astype(str)

    # -- calibrate each country's net position to the measured exchanges ---- #
    # Residual = what the data leave unexplained (losses, metering, flat
    # Morocco profile). Removed from that country's load buses pro rata, so the
    # model's net export of each country matches the measured border totals.
    cal_rows = []
    for c in MODEL:
        bidx = np.where(country == c)[0]
        meas = np.zeros(len(T))
        for d_ in MODEL:
            if d_ != c:
                e = net_export(data, c, d_, T)
                if e is not None:
                    meas += e.values
        resid = P[bidx].sum(axis=0) - meas
        wc = wl[bidx] / wl[bidx].sum()
        P[bidx] -= np.outer(wc, resid)
        cal_rows.append({"scope": f"country {c}", "buses": len(bidx),
                         "mean_abs_balancing_mw": float(np.abs(resid).mean()),
                         "max_abs_balancing_mw": float(np.abs(resid).max()),
                         "mean_balancing_mw": float(resid.mean())})
        pd.Series(resid, index=T, name=f"{c}_mw").to_frame().to_csv(
            out / f"balancing_{c}_hourly.csv", index_label="hour_utc")

    # -- fixed flows on DC links inside the model --------------------------- #
    dc = br[br.kind == "dc"]
    fixed = {}
    for i, r in dc.iterrows():
        ca, cb = buses_all.at[r.bus0, "country"], buses_all.at[r.bus1, "country"]
        if ca == cb:
            fixed[i] = np.zeros(len(T))
            continue
        meas = net_export(data, ca, cb, T)
        if meas is None:
            fixed[i] = np.zeros(len(T))
            continue
        pair = br[(br.bus0.map(buses_all.country).isin([ca, cb]))
                  & (br.bus1.map(buses_all.country).isin([ca, cb]))
                  & (br.bus0.map(buses_all.country) != br.bus1.map(buses_all.country))]
        share = r.cap / max(pair.cap.sum(), 1.0)
        hv_ids = REE_LINE_BRANCHES[HVDC_REE]
        if ree_lines is not None and r.id in hv_ids and HVDC_REE in set(ree_lines.line):
            # REE measured daily HVDC total (into Spain), spread over the day;
            # hourly swings follow the border with the capacity share.
            hv_cap = br[br.id.isin(hv_ids)].cap.sum()
            day = T.tz_convert(TZ_ES).strftime("%Y-%m-%d")
            hd = ree_lines[ree_lines.line == HVDC_REE].set_index("date").net_mwh
            to_es = 1.0 if cb == "ES" else -1.0   # f is bus0 -> bus1
            m = pd.Series(meas.values, index=T)
            dev = m - m.groupby(day).transform("mean")
            base = pd.Series(day, index=T).map(hd / 24.0)
            f_all = np.where(base.notna(), to_es * base.fillna(0) + dev * share * hv_cap / r.cap,
                             m * share * hv_cap / r.cap)
            f = np.clip(f_all * r.cap / hv_cap, -r.cap, r.cap)
        else:
            f = np.clip(meas.values * share, -r.cap, r.cap)
        fixed[i] = f
        P[pos[r.bus0]] -= f
        P[pos[r.bus1]] += f

    # -- balance each AC island -------------------------------------------- #
    from scipy import sparse as sp
    from scipy.sparse.csgraph import connected_components

    ac = br[br.kind != "dc"].reset_index(drop=True)
    i0 = ac.bus0.map(pos).values.astype(int)
    i1 = ac.bus1.map(pos).values.astype(int)
    adj = sp.coo_matrix((np.ones(len(ac)), (i0, i1)), shape=(nb, nb))
    ncomp, lab = connected_components(adj, directed=False)
    resid_rows = []
    for k in range(ncomp):
        nodes = np.where(lab == k)[0]
        s = P[nodes].sum(axis=0)
        w = wl[nodes] if wl[nodes].sum() > 0 else np.ones(len(nodes))
        P[nodes] -= np.outer(w / w.sum(), s)
        resid_rows.append({"scope": f"AC island {k}", "buses": len(nodes),
                           "mean_abs_balancing_mw": float(np.abs(s).mean()),
                           "max_abs_balancing_mw": float(np.abs(s).max()),
                           "mean_balancing_mw": float(s.mean())})
    resid_rows.sort(key=lambda r: -r["buses"])
    pd.DataFrame(cal_rows + resid_rows).to_csv(out / "balancing_residuals.csv",
                                               index=False)

    # -- outages: REE shows no flow either way for a whole day --------------- #
    active = np.ones((len(ac), len(T)), dtype=bool)
    if ree_lines is not None:
        day = T.tz_convert(TZ_ES).strftime("%Y-%m-%d")
        out_rows = []
        for name, ids in REE_LINE_BRANCHES.items():
            rl = ree_lines[ree_lines.line == name]
            dead = set(rl[(rl.import_mwh.abs() < 1) & (rl.export_mwh.abs() < 1)].date)
            if not dead:
                continue
            hrs = np.isin(day, list(dead))
            for j in np.where(ac.id.isin(ids))[0]:
                active[j, hrs] = False
            out_rows.append({"line": name, "days_out": ", ".join(sorted(dead))})
            log.info("Out of service per REE (no flow both ways): %s on %s",
                     name, ", ".join(sorted(dead)))
        pd.DataFrame(out_rows).to_csv(out / "outages_from_ree.csv", index=False)

    # -- DC power flow ------------------------------------------------------ #
    log.info("Solving DC power flow for %d hours on %d AC branches", len(T), len(ac))
    F_ac = np.zeros((len(ac), len(T)))
    bvals = ac.b.values.astype(float)
    patterns = pd.Series([active[:, t].tobytes() for t in range(len(T))])
    for _, hrs in patterns.groupby(patterns).groups.items():
        hrs = np.asarray(list(hrs))
        on = active[:, hrs[0]]
        F_ac[np.ix_(on, hrs)] = solve_dc(nb, i0[on], i1[on], bvals[on], P[:, hrs])

    # -- assemble output ---------------------------------------------------- #
    flows = {r.id: F_ac[j] for j, r in ac.iterrows()}
    for i, r in dc.iterrows():
        flows[r.id] = fixed[i]
    meta = pd.concat([ac[["id", "kind", "bus0", "bus1", "cap"]],
                      dc[["id", "kind", "bus0", "bus1", "cap"]]], ignore_index=True)
    meta = meta[meta.kind != "trafo"].reset_index(drop=True)  # transformers are not drawn

    mat = np.vstack([flows[i] for i in meta.id])            # (branches, T)
    long = pd.DataFrame({
        "line_id": np.repeat(meta.id.values, len(T)),
        "hour_utc": np.tile(T, len(meta)),
        "flow_mw": mat.ravel(),
    })
    cap = np.repeat(meta.cap.values, len(T))
    long["loading_pct"] = np.where(cap > 0, np.abs(long.flow_mw) / cap * 100, np.nan)
    long["direction"] = np.where(long.flow_mw >= 0, "forward", "reverse")
    try:
        long.to_parquet(out / "flows_hourly.parquet", index=False)
    except Exception:
        long.to_csv(out / "flows_hourly.csv.gz", index=False)

    # -- geometry ----------------------------------------------------------- #
    feats = []
    geom = n.lines["geometry"] if "geometry" in n.lines.columns else None
    lgeom = n.links["geometry"] if len(n.links) and "geometry" in n.links.columns else None
    for _, r in meta.iterrows():
        a, b = buses_all.loc[r.bus0], buses_all.loc[r.bus1]
        coords = [[a.x, a.y], [b.x, b.y]]
        g = None
        if geom is not None and r.kind == "line":
            g = geom.get(r.id[2:])
        elif lgeom is not None and r.kind == "dc":
            g = lgeom.get(r.id[2:])
        if g is not None and not (isinstance(g, float) and np.isnan(g)):
            try:
                from shapely import wkt
                from shapely.geometry import mapping
                g = wkt.loads(g) if isinstance(g, str) else g
                coords = list(mapping(g)["coordinates"])
            except Exception:
                pass
        feats.append({"type": "Feature",
                      "properties": {"line_id": r.id, "kind": r.kind,
                                     "v_nom": float(buses_all.at[r.bus0, "v_nom"]),
                                     "cap_mw": float(r.cap),
                                     "country0": buses_all.at[r.bus0, "country"],
                                     "country1": buses_all.at[r.bus1, "country"]},
                      "geometry": {"type": "LineString", "coordinates": coords}})
    (out / "lines.geojson").write_text(json.dumps({"type": "FeatureCollection",
                                                   "features": feats}))

    # -- validation --------------------------------------------------------- #
    val = []
    bc = buses_all["country"]
    for ca, cb in (("ES", "FR"), ("ES", "PT")):
        sel = meta[(meta.bus0.map(bc) == ca) & (meta.bus1.map(bc) == cb)]
        selr = meta[(meta.bus0.map(bc) == cb) & (meta.bus1.map(bc) == ca)]
        model = sum((flows[i] for i in sel.id), np.zeros(len(T))) \
            - sum((flows[i] for i in selr.id), np.zeros(len(T)))
        meas = net_export(data, ca, cb, T)
        val.append(pd.DataFrame({
            "hour_utc": T, "border": f"{ca}->{cb}", "modelled_mw": model,
            "measured_mw": meas.values if meas is not None else np.nan}))
    val = pd.concat(val)
    val["error_mw"] = val.modelled_mw - val.measured_mw
    val.to_csv(out / "validation_borders.csv", index=False)
    log.info("Validation (mean abs error, MW):\n%s",
             val.groupby("border").error_mw.apply(lambda s: s.abs().mean()).round(0))
    log.info("Done. Output in %s", out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--network", help="PyPSA-Eur network (.nc)")
    ap.add_argument("--out", default="out")
    ap.add_argument("--cache", default="cache")
    ap.add_argument("--start", default="2025-04-25")
    ap.add_argument("--end", default="2025-05-03", help="exclusive, UTC")
    ap.add_argument("--bus-weights", help="CSV: bus, weight (optional)")
    ap.add_argument("--extra-borders",
                    help="CSV: hour_utc,border,net_export_mw (e.g. border=ES-MA)")
    ap.add_argument("--source", choices=["entsoe", "energycharts"], default="energycharts",
                    help="energycharts (default) needs no token; entsoe needs ENTSOE_API_KEY")
    ap.add_argument("--ree-lines", default="out/ree_daily_lines.csv",
                    help="REE daily per-line flows (crosscheck_sources.py): HVDC "
                         "daily totals and line outages; skipped if missing")
    ap.add_argument("--fr-source", choices=["rte", "energycharts"], default="rte",
                    help="France load and generation (borders always from Energy-Charts)")
    ap.add_argument("--no-patch", action="store_true",
                    help="do not refill the ES-FR Energy-Charts gap from RTE schedules")
    ap.add_argument("--probe", action="store_true",
                    help="fetch one day of Energy-Charts data for ES and print its structure")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.selftest:
        selftest()
        return
    if args.probe:
        probe(args)
        return
    if not args.network:
        ap.error("--network is required")
    run(args)


if __name__ == "__main__":
    main()
