"""Land layer and fallback anchor points.

CShapes only draws independent states, so territories (Reunion, Hong Kong...) and
colonies before independence have no polygon. They still trade wine, so arcs
need a point: Natural Earth label points by ISO3, plus a short manual list for
territories Natural Earth folds into a parent country. A Natural Earth land layer
sits under the CShapes states so those areas still read as land.
Natural Earth: public domain.
Usage: python 04_basemap.py ne_50m_land.zip ne_50m_admin_0_countries.zip wine_flows.json OUTDIR
"""
import json
import subprocess
import sys

import geopandas as gpd

MANUAL = {  # lon, lat
    "BMU": (-64.75, 32.30), "VGB": (-64.62, 18.43), "GUF": (-53.1, 3.9), "PYF": (-149.4, -17.6),
    "GIB": (-5.35, 36.14), "GLP": (-61.55, 16.25), "HKG": (114.17, 22.32), "MTQ": (-61.02, 14.64),
    "ANT": (-68.9, 12.17), "NCL": (165.6, -21.3), "PCZ": (-79.6, 9.1), "REU": (55.53, -21.12),
    "SPM": (-56.3, 46.9), "PUS": (-169.5, 16.7), "VDR": (105.8, 21.0), "ABW": (-69.97, 12.52),
    "CUW": (-68.99, 12.17), "SXM": (-63.05, 18.04), "MAC": (113.55, 22.19), "CYM": (-81.25, 19.31),
    "TCA": (-71.8, 21.8), "MYT": (45.15, -12.82), "FRO": (-6.9, 62.0), "GRL": (-41.0, 74.0),
    "AIA": (-63.05, 18.22), "MSR": (-62.19, 16.74), "SHN": (-5.7, -15.95), "FLK": (-59.5, -51.7),
    "WLF": (-176.2, -13.3), "COK": (-159.78, -21.24), "NIU": (-169.86, -19.05), "TKL": (-171.8, -9.2),
    "ASM": (-170.7, -14.3), "GUM": (144.79, 13.44), "MNP": (145.7, 15.2), "PCN": (-130.1, -25.07),
}


def main():
    land_zip, adm_zip, flows_json, outdir = sys.argv[1:5]
    land = gpd.read_file(f"zip://{land_zip}")
    land.to_file(f"{outdir}/land.geojson", driver="GeoJSON")
    subprocess.run(["mapshaper", f"{outdir}/land.geojson", "-simplify", "8%", "keep-shapes",
                    "-filter-islands", "min-area=150km2", "-dissolve",
                    "-o", "format=topojson", "quantization=1e5", f"{outdir}/land.topo.json"], check=True)

    adm = gpd.read_file(f"zip://{adm_zip}")
    pts = {}
    for r in adm.itertuples():
        for iso in {r.ISO_A3, r.ISO_A3_EH, r.ADM0_A3}:
            if iso and iso != "-99":
                pts.setdefault(iso, (round(r.LABEL_X, 3), round(r.LABEL_Y, 3)))
    pts.update(MANUAL)
    nodes = json.load(open(flows_json))["nodes"]
    fb = {}
    for n in nodes:
        k = n["k"]
        if k in pts:
            fb[k] = pts[k]
    missing = [n["k"] + " " + n["n"] for n in nodes if n["k"] not in fb]
    json.dump(fb, open(f"{outdir}/fallback_points.json", "w"), separators=(",", ":"))
    print(len(fb), "fallback points; none for:", missing)


if __name__ == "__main__":
    main()
