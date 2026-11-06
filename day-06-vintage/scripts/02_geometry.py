"""Historical country geometry for 1962-2023 from CShapes 2.0.

Keeps every CShapes polygon version that is in force on 1 July of at least one
year in the range, records its first and last such year, extends versions still
in force at the end of CShapes (2019) to 2023, and adds an anchor point
(pole of inaccessibility of the largest part) for flow arcs.

Borders are used exactly as CShapes draws them; no edits.
CShapes 2.0, Schvitz et al. 2022, CC BY-NC-SA 4.0.
Usage: python 02_geometry.py CShapes-2.0.shp OUT.geojson
"""
import sys
import json
import pandas as pd
import geopandas as gpd
from shapely.ops import polylabel

Y0, Y1, CSHAPES_END = 1962, 2023, 2019


def main():
    shp, out = sys.argv[1:3]
    g = gpd.read_file(shp)
    g["s"] = pd.to_datetime(g.gwsdate)
    g["e"] = pd.to_datetime(g.gwedate)
    rows = []
    for r in g.itertuples():
        years = [y for y in range(Y0, Y1 + 1) if r.s <= pd.Timestamp(y, 7, 1) <= r.e]
        if r.e >= pd.Timestamp(CSHAPES_END, 12, 31):
            years += list(range(CSHAPES_END + 1, Y1 + 1))
        years = sorted(set(y for y in years if Y0 <= y <= Y1))
        if not years:
            continue
        geom = r.geometry
        part = max(geom.geoms, key=lambda p: p.area) if geom.geom_type == "MultiPolygon" else geom
        a = polylabel(part, tolerance=0.05)
        rows.append(dict(gw=int(r.gwcode), name=r.cntry_name, y0=years[0], y1=years[-1],
                         ax=round(a.x, 3), ay=round(a.y, 3), geometry=geom))
    out_g = gpd.GeoDataFrame(rows, crs=g.crs)
    out_g.to_file(out, driver="GeoJSON")
    print(len(out_g), "polygon versions;", out_g.gw.nunique(), "countries")
    # sanity: no gw should have two versions in the same year
    for gw, s in out_g.groupby("gw"):
        yrs = [y for r in s.itertuples() for y in range(r.y0, r.y1 + 1)]
        if len(yrs) != len(set(yrs)):
            print("overlap", gw, s[["name", "y0", "y1"]].values.tolist())


if __name__ == "__main__":
    main()
