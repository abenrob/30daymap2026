"""Day 3, step 2: merge the tiles into one table of buildings, each tagged with its arrondissement.

Reads:  bdtopo/tiles/*.json and bdtopo/arr.json (from 01_fetch_bdtopo.py)
Writes: bdtopo/bat.parquet (buildings) and bdtopo/arr.parquet (arrondissements), both in Lambert-93
"""
import glob
import json

import geopandas as gpd
import pandas as pd
import shapely

# Flatten every tile into one list of rows: the attributes plus the raw GeoJSON geometry.
rows = []
for fn in glob.glob("bdtopo/tiles/*.json"):
    for f in json.load(open(fn))["features"]:
        p = f["properties"]
        p["geom"] = f["geometry"]
        rows.append(p)

# A building that crosses a tile edge was downloaded once per tile; cleabs is BD TOPO's stable id.
df = pd.DataFrame(rows).drop_duplicates("cleabs")
g = gpd.GeoDataFrame(df.drop(columns="geom"),
                     geometry=[shapely.geometry.shape(x) for x in df.geom], crs=2154)
# BD TOPO geometries carry a Z value (roof altitude). We only need the footprint.
g["geometry"] = shapely.force_2d(g.geometry.values)

print(len(g), g.etat_de_l_objet.value_counts().to_dict())
# Drop buildings that are planned, under construction or in ruins.
g = g[g.etat_de_l_objet == "En service"]

arr = gpd.read_file("bdtopo/arr.json").to_crs(2154)[
    ["numero_de_l_arrondissement_municipal", "nom_officiel", "population", "geometry"]]
arr["n"] = arr.numero_de_l_arrondissement_municipal.astype(int)

# Assign each building to one arrondissement. A representative point is guaranteed to lie
# inside the footprint (a centroid can fall outside an L- or U-shaped building), so a
# building on a boundary street lands in exactly one arrondissement. Buildings whose point
# falls outside Paris (the inner suburbs caught by the download box) are dropped by the
# inner join.
c = g.copy()
c["geometry"] = g.geometry.representative_point()
j = gpd.sjoin(c, arr[["n", "geometry"]], predicate="within", how="inner")
g = g.loc[j.index]
g["arr"] = j.n
g["area"] = g.geometry.area  # m², since Lambert-93 is in metres

# Quick checks printed to the console: counts by use and by arrondissement, missing heights.
print(len(g))
print(g.usage_1.value_counts(dropna=False).to_dict())
print(g.groupby("arr").size().to_dict())
print("null hauteur %", round(100 * g.hauteur.isna().mean(), 1),
      "nature", g.nature.value_counts().head(8).to_dict())

g.to_parquet("bdtopo/bat.parquet")
arr.to_parquet("bdtopo/arr.parquet")
