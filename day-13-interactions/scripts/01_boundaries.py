"""Day 13: commune + municipal arrondissement boundaries for the commuting-flows app.

Source: Etalab "Contours administratifs" 2025 (COG 1 Jan 2025, built from IGN Admin Express,
OSM for the overseas collectivities), communes at 50 m generalisation, ODbL.
It already includes the 45 arrondissements of Paris, Lyon and Marseille.

Steps: drop the 3 whole-city polygons (they overlap their arrondissements), simplify with
mapshaper (weighted Visvalingam, 10%, shared borders kept), fix validity, check every French
code in the INSEE flows matches, Hilbert-sort, write GeoParquet with GeoArrow-native geometry.

Usage: python3 01_boundaries.py <data_dir>   (data_dir = work/data/day-13-interactions)
Needs: mapshaper (MAPSHAPER env var, default "npx -y mapshaper@0.6"), geopandas>=1.0, duckdb.
"""
import gzip, os, shlex, shutil, subprocess, sys, tempfile, urllib.request, zipfile
import duckdb, geopandas as gpd, shapely

SRC_URL = ("https://etalab-datasets.geo.data.gouv.fr/contours-administratifs/2025/geojson/"
           "communes-50m-2025-01-08.geojson.gz")
WHOLE_CITIES = ["75056", "69123", "13055"]
KEEP = "10%"

data = os.path.abspath(sys.argv[1]); raw = os.path.join(data, "raw"); os.makedirs(raw, exist_ok=True)
src_gz = os.path.join(raw, os.path.basename(SRC_URL))
flows_zip = os.path.join(raw, "base-flux-mobilite-domicile-lieu-travail-2022_csv.zip")
out = os.path.join(data, "communes_2025.parquet")
if not os.path.exists(src_gz):
    urllib.request.urlretrieve(SRC_URL, src_gz)

tmp = tempfile.mkdtemp()
src = os.path.join(tmp, "src.geojson"); simp = os.path.join(tmp, "simp.geojson")
with gzip.open(src_gz) as i, open(src, "wb") as o: shutil.copyfileobj(i, o)
ms = shlex.split(os.environ.get("MAPSHAPER", "npx -y mapshaper@0.6"))
cities = ",".join(f'"{c}"' for c in WHOLE_CITIES)
subprocess.run(ms + ["-i", src, "-filter", f"[{cities}].indexOf(code) == -1",
                     "-filter-fields", "code,nom",
                     "-simplify", KEEP, "visvalingam", "weighted", "keep-shapes",
                     "-o", simp, "format=geojson", "precision=0.00001"], check=True)

g = gpd.read_file(simp).set_crs(4326, allow_override=True)
bad = (~g.is_valid).sum()
g["geometry"] = shapely.make_valid(g.geometry.values)
# keep polygonal parts only, and one geometry type (MultiPolygon) for GeoArrow encoding
def polys(geom):
    parts = [p for p in getattr(geom, "geoms", [geom]) if p.geom_type in ("Polygon", "MultiPolygon")]
    flat = [q for p in parts for q in getattr(p, "geoms", [p])]
    return shapely.MultiPolygon(flat)
g["geometry"] = g.geometry.apply(polys)
assert g.is_valid.all() and (g.geom_type == "MultiPolygon").all() and not g.geometry.is_empty.any()

# join check against the flows (foreign workplaces have letter-prefixed codes and are expected)
with zipfile.ZipFile(flows_zip) as z: z.extractall(tmp)
csv = os.path.join(tmp, "base-flux-mobilite-domicile-lieu-travail-2022.csv")
con = duckdb.connect(); con.register("g", g[["code"]])
missing = con.sql(f"""with f as (select * from read_csv('{csv}', delim=';', types={{'CODGEO':'VARCHAR','DCLT':'VARCHAR'}})),
  codes as (select CODGEO c from f union select DCLT from f)
  select list(c) from codes where c not in (select code from g) and not regexp_full_match(c, '[A-Z]{{2}}.*')""").fetchone()[0]
assert not missing, f"unmatched French codes: {missing}"

g = g.iloc[g.geometry.hilbert_distance().argsort()].reset_index(drop=True)
# No dictionary encoding (it bloats coordinate doubles: 6.1 MB vs 2.9 MB) and no bbox covering
# column (+0.8 MB, and range requests on this small file are not worth it). GeoArrow-native
# geometry costs ~0.2 MB over WKB but deck.gl can draw it without parsing.
g.to_parquet(out, compression="zstd", compression_level=19, use_dictionary=False,
             geometry_encoding="geoarrow", write_covering_bbox=False, schema_version="1.1.0")
shutil.rmtree(tmp)
print(f"{len(g)} features, {int(shapely.get_num_coordinates(g.geometry.values).sum())} vertices, "
      f"{bad} invalid before fix, {os.path.getsize(out):,} bytes -> {out}")
