"""Trace the Rhone network upstream from the sea with a recursive SQL query.

Reads the raw HydroSHEDS downloads (01_download.sh) and writes to
work/data/day-02-lines/derived/:
  rivers.parquet  every HydroRIVERS reach upstream of the Rhone mouth, with
                  network depth, distance to outlet and our own accumulation
  basin.parquet   basin outline (HydroBASINS level-12 units sharing the outlet MAIN_BAS, slivers filled)
  lakes.parquet   HydroLAKES polygons inside the basin
  ocean.parquet   Natural Earth 10m ocean, clipped to the basin bbox + margin

Run from the workspace root: python3 site/day-02-lines/scripts/02_trace_rhone.py
"""
import duckdb, os, sys

RAW = "work/data/day-02-lines/raw"
OUT = "work/data/day-02-lines/derived"
os.makedirs(OUT, exist_ok=True)

c = duckdb.connect()
c.sql("INSTALL spatial; LOAD spatial;")

c.sql(f"""
CREATE TABLE riv AS
SELECT * EXCLUDE (OGC_FID) FROM ST_Read('/vsizip/{RAW}/HydroRIVERS_v10_eu_shp.zip/HydroRIVERS_v10_eu_shp/HydroRIVERS_v10_eu.shp')
""")

# Outlet: the sea-draining reach (NEXT_DOWN = 0) with the largest upstream area
# near the Rhone delta.
outlet = c.execute("""
SELECT HYRIV_ID, UPLAND_SKM, DIS_AV_CMS, MAIN_RIV, ST_AsText(ST_EndPoint(geom)) AS mouth
FROM riv
WHERE NEXT_DOWN = 0
  AND ST_Intersects(geom, ST_MakeEnvelope(4.3, 43.2, 5.1, 43.6))
ORDER BY UPLAND_SKM DESC LIMIT 1
""").fetchone()
print("outlet:", outlet)
OUTLET = outlet[0]

# Upstream trace: walk NEXT_DOWN backwards from the outlet.
# depth = number of reaches to the outlet, dist_km = network distance from the
# outlet to the reach's DOWNSTREAM end.
c.sql(f"""
CREATE TABLE up AS
WITH RECURSIVE t(id, depth, dist_km) AS (
    SELECT {OUTLET}::BIGINT, 0, 0.0::DOUBLE
  UNION ALL
    SELECT r.HYRIV_ID, t.depth + 1, t.dist_km + p.LENGTH_KM::DOUBLE
    FROM t
    JOIN riv r ON r.NEXT_DOWN = t.id
    JOIN riv p ON p.HYRIV_ID = t.id
)
SELECT * FROM t
""")

n_trace, = c.execute("SELECT count(*) FROM up").fetchone()
n_main, = c.execute(f"SELECT count(*) FROM riv WHERE MAIN_RIV = {outlet[3]}").fetchone()
print(f"reaches traced: {n_trace:,}   reaches with same MAIN_RIV: {n_main:,}")
if n_trace != n_main:
    sys.exit("trace and MAIN_RIV disagree, check topology")

# Our own accumulation: total channel length upstream of (and including) each
# reach. Summing over ancestors is a second recursion, done here as one pass
# from each reach down to the outlet, then grouped.
c.sql("""
CREATE TABLE acc AS
WITH RECURSIVE d(src, id) AS (
    SELECT HYRIV_ID, HYRIV_ID FROM riv WHERE HYRIV_ID IN (SELECT id FROM up)
  UNION ALL
    SELECT d.src, r.NEXT_DOWN
    FROM d JOIN riv r ON r.HYRIV_ID = d.id
    WHERE r.NEXT_DOWN <> 0
)
SELECT d.id, sum(s.LENGTH_KM) AS up_len_km, count(*) AS up_reaches
FROM d JOIN riv s ON s.HYRIV_ID = d.src
GROUP BY d.id
""")

c.sql(f"""
COPY (
  SELECT r.HYRIV_ID AS id, r.NEXT_DOWN AS next_down,
         r.LENGTH_KM AS length_km,
         u.depth, u.dist_km AS dist_to_outlet_km,
         u.dist_km + r.LENGTH_KM AS dist_upstream_end_km,
         a.up_len_km, a.up_reaches,
         r.UPLAND_SKM AS upland_km2, r.DIS_AV_CMS AS discharge_m3s,
         r.ORD_STRA AS strahler, r.ORD_FLOW AS ord_flow, r.HYBAS_L12 AS hybas_l12,
         r.geom AS geometry
  FROM riv r JOIN up u ON u.id = r.HYRIV_ID JOIN acc a ON a.id = r.HYRIV_ID
) TO '{OUT}/rivers.parquet' (FORMAT parquet)
""")

# Basin outline: every HydroBASINS level-12 unit that drains to the same outlet
# (MAIN_BAS) as the unit holding our outlet reach. Using only units that contain
# a reach would leave holes, because HydroRIVERS skips catchments under 10 km2.
c.sql(f"""
CREATE TABLE hb AS
SELECT * FROM ST_Read('/vsizip/{RAW}/hybas_eu_lev12_v1c.zip/hybas_eu_lev12_v1c.shp')
""")
c.sql(f"""
CREATE TABLE bas AS
SELECT * FROM hb
WHERE MAIN_BAS = (SELECT MAIN_BAS FROM hb WHERE HYBAS_ID =
                   (SELECT HYBAS_L12 FROM riv WHERE HYRIV_ID = {OUTLET}))
""")
c.sql(f"""
COPY (SELECT ST_MakePolygon(ST_ExteriorRing(ST_Union_Agg(geom))) AS geometry, sum(SUB_AREA) AS area_km2 FROM bas)
TO '{OUT}/basin.parquet' (FORMAT parquet)
""")
area, bbox = c.execute(f"SELECT area_km2, ST_Extent(geometry) FROM '{OUT}/basin.parquet'").fetchone()
print(f"basin area: {area:,.0f} km2   bbox: {bbox}")

# Lakes inside the basin (bbox prefilter, then polygon test).
xmin, ymin, xmax, ymax = (bbox[k] for k in ("min_x", "min_y", "max_x", "max_y"))
c.sql(f"""
COPY (
  SELECT l.Hylak_id AS id, l.Lake_name AS name, l.Lake_type AS lake_type,
         l.Lake_area AS area_km2, l.Elevation AS elevation_m, l.Depth_avg AS depth_avg_m,
         l.geom AS geometry
  FROM ST_Read('/vsizip/{RAW}/HydroLAKES_polys_v10_shp.zip/HydroLAKES_polys_v10_shp/HydroLAKES_polys_v10.shp') l,
       '{OUT}/basin.parquet' b
  WHERE l.Pour_long BETWEEN {xmin} AND {xmax} AND l.Pour_lat BETWEEN {ymin} AND {ymax}
    AND ST_Intersects(l.geom, b.geometry)
) TO '{OUT}/lakes.parquet' (FORMAT parquet)
""")

m = 1.0
c.sql(f"""
COPY (
  SELECT ST_Intersection(geom, ST_MakeEnvelope({xmin-m}, {ymin-m}, {xmax+m}, {ymax+m})) AS geometry
  FROM ST_Read('/vsizip/{RAW}/ne_10m_ocean.zip/ne_10m_ocean.shp')
  WHERE ST_Intersects(geom, ST_MakeEnvelope({xmin-m}, {ymin-m}, {xmax+m}, {ymax+m}))
) TO '{OUT}/ocean.parquet' (FORMAT parquet)
""")

print(c.sql(f"""
SELECT count(*) AS reaches, round(sum(length_km)) AS km, max(depth) AS max_depth,
       round(max(dist_upstream_end_km)) AS longest_path_km, max(strahler) AS max_strahler,
       round(max(up_len_km)) AS outlet_up_len_km
FROM '{OUT}/rivers.parquet'"""))
print(c.sql(f"SELECT strahler, count(*) n FROM '{OUT}/rivers.parquet' GROUP BY 1 ORDER BY 1"))
print(c.sql(f"""SELECT count(*) lakes, round(sum(area_km2)) km2 FROM '{OUT}/lakes.parquet'"""))
print(c.sql(f"""SELECT name, round(area_km2,1) km2, elevation_m FROM '{OUT}/lakes.parquet'
               ORDER BY area_km2 DESC LIMIT 12"""))
