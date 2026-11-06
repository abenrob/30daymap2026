"""Build the wine flow table and the country (node) table for the site.

Rules
- Per reporter, year and flow, use the classification (SITC Rev.1/2/3 or HS) whose
  report covers the most partners: the most complete submission wins.
- Where importer and exporter both report a flow, the exporter's report replaces the
  importer's when the importer's volume is an estimate, when the volumes differ by more
  than 3x and the exporter's price per litre is closer to that pair's usual price, or
  when the importer's value is more than 5x the exporter's.
- Bilateral volume prefers the importer's report (M); where the importer did not
  report that partner, the exporter's report (X) is used (mirror fill).
- Volume in litres: qty in litres; kg taken as litres (wine about 0.99 kg/l);
  otherwise net weight; otherwise estimated from value at the median USD per litre
  of that reporter-year (else that year worldwide). Estimated volumes are flagged.
- Comtrade codes become nodes; nodes map to CShapes Gleditsch-Ward codes.
  Successor states keep their own node and share a lineage group with their
  predecessor so they sit together in the fixed Sankey order.

Source: UN Comtrade. Output is transformed data (reconciled, mirror-filled, unit
converted), not original records.
Usage: python 03_flows.py RAWDIR partners.json geometry.geojson OUTDIR
"""
import glob
import json
import os
import re
import sys
from collections import defaultdict

import numpy as np
import pandas as pd
import country_converter as coco

PREF = {"HS": 4, "S3": 3, "S2": 2, "S1": 1}

# Comtrade codes that need their own node key (ISO3 is shared or missing)
SPECIAL = {
    280: ("FRG", "West Germany", [260]),
    278: ("GDR", "East Germany", [265]),
    276: ("DEU", "Germany", [260]),
    58: ("BLX", "Belgium-Luxembourg", [211, 212]),
    810: ("SUN", "USSR", [365]),
    200: ("CSK", "Czechoslovakia", [315]),
    890: ("YUG", "Yugoslavia", [345]),
    891: ("SCG", "Serbia and Montenegro", [345]),
    688: ("SRB", "Serbia", [340]),
    499: ("MNE", "Montenegro", [341]),
    412: ("XKX", "Kosovo", [347]),
    230: ("ETH_OLD", "Ethiopia", [530]),
    736: ("SDN_OLD", "Sudan", [625]),
    886: ("YAR", "Yemen Arab Republic", [678]),
    720: ("YMD", "South Yemen", [680]),
    887: ("YEM", "Yemen", [679]),
    490: ("S19", "Other Asia, nes", []),   # Comtrade label, kept as is
    866: ("VDR", "North Vietnam", [816]),
    868: ("RVN", "South Vietnam", [817]),
    588: ("PAK_OLD", "Pakistan", [770]),
}
LINEAGE = {
    "SUN": ["SUN", "RUS", "UKR", "BLR", "MDA", "GEO", "ARM", "AZE", "KAZ", "UZB", "TKM", "KGZ", "TJK", "EST", "LVA", "LTU"],
    "YUG": ["YUG", "SCG", "SRB", "MNE", "XKX", "HRV", "SVN", "MKD", "BIH"],
    "CSK": ["CSK", "CZE", "SVK"],
    "GER": ["FRG", "GDR", "DEU"],
    "BLX": ["BLX", "BEL", "LUX"],
    "ETH": ["ETH_OLD", "ETH", "ERI"],
    "SDN": ["SDN_OLD", "SDN", "SSD"],
    "YEM": ["YAR", "YMD", "YEM"],
    "PAK": ["PAK_OLD", "PAK", "BGD"],
    "VNM": ["VDR", "RVN", "VNM"],
}
OLD_WORLD_EXTRA = {"GEO", "ARM", "AZE", "MDA", "ISR", "LBN", "CYP", "TUR", "DZA", "TUN", "MAR", "SUN", "RUS", "UKR"}
NEW_WORLD = {"USA", "CAN", "MEX", "CHL", "ARG", "URY", "BRA", "PER", "BOL", "ZAF", "AUS", "NZL", "CHN"}


def clean_name(t):
    return re.sub(r"\s*\(\.\.\.\d{4}\)|\s*\(\d{4}\.\.\.\)", "", t).strip()


def main():
    rawdir, partners_json, geom, outdir = sys.argv[1:5]
    os.makedirs(outdir, exist_ok=True)
    ref = {p["id"]: p for p in json.load(open(partners_json))["results"]}
    cc = coco.CountryConverter()

    # ---- load raw, keep plain bilateral rows
    recs = []
    for f in sorted(glob.glob(os.path.join(rawdir, "*.json"))):
        cl = os.path.basename(f).split("_")[0]
        for r in json.load(open(f)):
            if r["partnerCode"] == 0 or r["partner2Code"] != 0 or r["customsCode"] != "C00" or r["motCode"] != 0:
                continue
            q = None
            if r["qtyUnitCode"] in (7, 8) and r["qty"]:
                q = float(r["qty"])
            elif r.get("netWgt"):
                q = float(r["netWgt"])
            recs.append((cl, r["refYear"], r["flowCode"], r["reporterCode"], r["partnerCode"], q,
                         float(r["primaryValue"] or 0)))
    df = pd.DataFrame(recs, columns=["cl", "year", "flow", "rep", "par", "litres", "usd"])
    print("raw rows", len(df))

    # ---- pick one classification per reporter-year-flow
    # most partners reported wins (value totals would reward inflated submissions)
    tot = df.groupby(["rep", "year", "flow", "cl"]).par.nunique().reset_index(name="np")
    tot["pref"] = tot.cl.map(PREF)
    best = tot.sort_values(["np", "pref"], ascending=False).drop_duplicates(["rep", "year", "flow"])
    df = df.merge(best[["rep", "year", "flow", "cl"]], on=["rep", "year", "flow", "cl"])
    df = df.groupby(["year", "flow", "rep", "par"], as_index=False).agg(litres=("litres", "sum"), usd=("usd", "sum"),
                                                                       nq=("litres", lambda s: s.isna().sum()))
    df.loc[df.nq > 0, "litres"] = np.nan

    # ---- estimate missing or implausible volumes from value
    # Some reports carry quantities off by orders of magnitude (e.g. Kazakhstan in
    # the 1990s). A volume whose implied price is more than 15x away from that
    # year's world median price per litre is treated as missing.
    df["upl"] = df.usd / df.litres
    ok = df[(df.litres > 0) & (df.usd > 0)]
    med_year = ok.groupby("year").upl.median()
    ratio = df.upl / df.year.map(med_year)
    bad = (df.litres > 0) & (df.usd > 0) & ((ratio < 1 / 15) | (ratio > 15))
    print(f"implausible volumes replaced: {bad.sum()} rows")
    df.loc[bad, "litres"] = np.nan
    ok = df[(df.litres > 0) & (df.usd > 0)]
    med_rep = ok.groupby(["rep", "year"]).upl.median()
    med_year = ok.groupby("year").upl.median()
    miss = df.litres.isna() | (df.litres <= 0)
    est = []
    for idx in df.index[miss]:
        r = df.loc[idx]
        u = med_rep.get((r.rep, r.year), np.nan)
        if not np.isfinite(u):
            u = med_year.get(r.year, np.nan)
        est.append(r.usd / u if np.isfinite(u) and u > 0 else 0.0)
    df.loc[miss, "litres"] = est
    df["est"] = miss

    # ---- reconcile: importer report first, exporter mirror second
    m = df[df.flow == "M"].rename(columns={"rep": "imp", "par": "exp"})
    x = df[df.flow == "X"].rename(columns={"rep": "exp", "par": "imp"})
    key = ["year", "exp", "imp"]
    m = m[key + ["litres", "usd", "est"]].assign(src="M")
    x = x[key + ["litres", "usd", "est"]].assign(src="X")
    # Where both sides report a flow, the importer's report is used unless:
    # - its volume is an estimate and the exporter's is not, or
    # - the two volumes differ by more than 3x: then the report whose price per
    #   litre is closer to the pair's usual price wins, or
    # - the importer's value is more than 5x the exporter's.
    both = m.merge(x, on=key, suffixes=("_m", "_x"))
    # reference price: this pair's median price in years when both reports agree
    # on volume (within 1.5x); falls back to the year's world median
    qr0 = np.maximum(both.litres_m, both.litres_x) / np.minimum(both.litres_m, both.litres_x).clip(lower=1)
    agree = both[(qr0 <= 1.5) & (both.est_m == False) & (both.est_x == False) & (both.litres_m > 0)]
    pair_price = (agree.usd_m / agree.litres_m).groupby([agree.exp, agree.imp]).median()
    med = pd.Series([pair_price.get((e, i), np.nan) for e, i in zip(both.exp, both.imp)], index=both.index)
    med = med.fillna(both.year.map(med_year))
    dm = np.abs(np.log((both.usd_m / both.litres_m) / med))
    dx = np.abs(np.log((both.usd_x / both.litres_x) / med))
    qr = np.maximum(both.litres_m, both.litres_x) / np.minimum(both.litres_m, both.litres_x).clip(lower=1)
    use_x = ((both.est_m == True) & (both.est_x == False)) \
        | ((both.est_m == False) & (both.est_x == False) & (qr > 3) & (dx < dm)) \
        | ((both.usd_m > 5 * both.usd_x) & (both.usd_x > 0))
    swap = both[use_x]
    print(f"flows where the exporter's report replaces the importer's: {len(swap)} of {len(both)}")
    m = m.merge(swap[key].assign(drop=1), on=key, how="left")
    m = m[m["drop"].isna()].drop(columns="drop")
    x = x.merge(m[key], on=key, how="left", indicator=True)
    x = x[x._merge == "left_only"].drop(columns="_merge")
    flows = pd.concat([m, x], ignore_index=True)
    flows = flows[flows.litres > 0]

    # A single report can still carry a broken volume (Denmark 1999: 3.2 m litres
    # of Spanish wine for $74 m). Compare each flow's price with the same pair's
    # median price over the surrounding nine years; beyond 3.5x either way, the
    # volume is re-estimated from value at that pair price and flagged.
    flows = flows.sort_values(["exp", "imp", "year"]).reset_index(drop=True)
    flows["price"] = flows.usd / flows.litres
    flows["est"] = flows.est.astype(bool)
    good = flows.price.where(~flows.est & (flows.usd > 0))
    pair_ref = good.groupby([flows.exp, flows.imp]).transform(
        lambda s: s.rolling(9, center=True, min_periods=3).median())
    ratio = flows.price / pair_ref
    off = pair_ref.notna() & (flows.usd > 0) & ((ratio > 3.5) | (ratio < 1 / 3.5))
    print(f"single-flow volumes re-estimated from the pair's usual price: {off.sum()}")
    flows.loc[off, "litres"] = flows.usd[off] / pair_ref[off]
    flows.loc[off, "est"] = True
    flows = flows.drop(columns="price")

    # ---- nodes
    codes = sorted(set(flows.exp) | set(flows.imp))
    nodes = {}
    for c in codes:
        p = ref.get(c)
        if p is None or p.get("isGroup"):
            continue
        if c in SPECIAL:
            k, name, gw = SPECIAL[c]
        else:
            iso = p.get("PartnerCodeIsoAlpha3") or ""
            if not re.fullmatch(r"[A-Z]{3}", iso):
                continue  # areas nes, bunkers, free zones, special categories
            k, name = iso, clean_name(p["text"])
            g = cc.convert(iso, src="ISO3", to="GWcode", not_found=None)
            gw = [int(g)] if g not in (None, "not found") and str(g).replace(".0", "").isdigit() else []
        nd_ = nodes.setdefault(k, dict(key=k, name=name, gw=gw, codes=[]))
        nd_["codes"].append(int(c))
        if c not in SPECIAL and not p.get("entryExpiredDate"):
            nd_["name"] = name  # current name wins over historical variants
    code2key = {c: n["key"] for n in nodes.values() for c in n["codes"]}
    flows["e"] = flows.exp.map(code2key)
    flows["i"] = flows.imp.map(code2key)
    dropped = flows[flows.e.isna() | flows.i.isna()].litres.sum() / flows.litres.sum()
    flows = flows.dropna(subset=["e", "i"])
    flows = flows[flows.e != flows.i]
    flows = flows.groupby(["year", "e", "i"], as_index=False).agg(litres=("litres", "sum"), usd=("usd", "sum"), est=("est", "max"),
                                                                 src=("src", "first"))
    print(f"dropped {dropped:.2%} of volume to non-country partners")

    # lineage group, category, years active, totals
    grp_of = {k: g for g, ks in LINEAGE.items() for k in ks}
    cont = {k: cc.convert(k, src="ISO3", to="continent", not_found=None) for k in nodes}
    for k, n in nodes.items():
        n["group"] = grp_of.get(k, k)
        if k in NEW_WORLD:
            n["cat"] = "new"
        elif cont.get(k) == "Europe" or k in OLD_WORLD_EXTRA or n["group"] in ("GER", "BLX", "CSK", "YUG", "SUN"):
            n["cat"] = "old"
        else:
            n["cat"] = "other"
        ex = flows[flows.e == k]
        im = flows[flows.i == k]
        yrs = sorted(set(ex.year) | set(im.year))
        n["y0"], n["y1"] = (int(yrs[0]), int(yrs[-1])) if yrs else (None, None)
        n["exp_total"] = float(ex.litres.sum())
        n["imp_total"] = float(im.litres.sum())

    # check every node with geometry has a polygon in each active year
    gj = json.load(open(geom))
    have = defaultdict(set)
    for f in gj["features"]:
        p = f["properties"]
        for y in range(p["y0"], p["y1"] + 1):
            have[p["gw"]].add(y)
    for k, n in nodes.items():
        if n["y0"] is None:
            continue
        if not n["gw"]:
            print("no geometry:", k, n["name"], f"{n['exp_total'] + n['imp_total']:.3g} l")
            continue
        gaps = [y for y in range(n["y0"], n["y1"] + 1)
                if not any(y in have[g] for g in n["gw"])
                and ((flows.year == y) & ((flows.e == k) | (flows.i == k))).any()]
        if gaps:
            print("geometry gap:", k, n["name"], n["gw"], gaps[:5], "..." if len(gaps) > 5 else "")

    # ---- fixed order: groups by total volume, members by first year then volume
    nd = pd.DataFrame(nodes.values()).dropna(subset=["y0"])
    nd["vol"] = nd.exp_total + nd.imp_total
    gvol = nd.groupby("group").vol.sum()
    nd["gvol"] = nd.group.map(gvol)
    nd["catrank"] = nd.cat.map({"old": 0, "new": 1, "other": 2})
    nd = nd.sort_values(["catrank", "gvol", "group", "y0", "vol"], ascending=[True, False, True, True, False])
    keys = nd.key.tolist()
    idx = {k: n for n, k in enumerate(keys)}

    out_nodes = [dict(k=r.key, n=r.name, g=r.group, c=r.cat, gw=r.gw, y0=int(r.y0), y1=int(r.y1),
                      ex=round(r.exp_total), im=round(r.imp_total)) for r in nd.itertuples()]
    years = sorted(flows.year.unique().tolist())
    by_year = {}
    for y, s in flows.groupby("year"):
        by_year[int(y)] = [[idx[r.e], idx[r.i], int(round(r.litres)), int(r.est)] for r in s.itertuples()]
    data = dict(source="UN Comtrade (transformed: reconciled importer/exporter reports, mirror-filled, litres)",
                years=[int(y) for y in years], nodes=out_nodes, flows=by_year)
    json.dump(data, open(os.path.join(outdir, "wine_flows.json"), "w"), separators=(",", ":"))
    flows.to_csv(os.path.join(outdir, "wine_flows_long.csv"), index=False)
    print(len(out_nodes), "nodes,", len(flows), "flows,", years[0], "to", years[-1])
    print(flows.groupby("year").litres.sum().iloc[::5].map(lambda v: f"{v / 1e9:.2f} bn l").to_string())


if __name__ == "__main__":
    main()
