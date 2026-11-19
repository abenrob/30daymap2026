"""Extract the 8 AOP cheese areas from the INAO SIQO shapefile.

Input : work/day-19-senses-smell/data/raw/<date>_delim-aire-geographique-shp.shp (Lambert-93)
Output: work/day-19-senses-smell/data/aop_areas.parquet (full, EPSG:4326)
        work/day-19-senses-smell/data/aop_areas_simple.geojson (simplified ~100 m)
"""
import glob, os, duckdb

ROOT = os.path.expanduser('~/mnt/30days2026/work/day-19-senses-smell/data')
SHP = sorted(glob.glob(f'{ROOT}/raw/*_delim-aire-geographique-shp.shp'))[-1]

# story_rank -> INAO id_app
AOPS = {1: 417, 2: 428, 3: 424, 4: 411, 5: 432, 6: 422, 7: 408, 8: 421}

c = duckdb.connect()
c.sql('install spatial; load spatial')
c.sql(f"create table src as select * from st_read('{SHP}')")
c.sql("create table ranks as select * from (values " +
      ','.join(f'({r},{i})' for r, i in AOPS.items()) + ") v(story_rank, id_app)")
print(c.sql("select r.story_rank, s.app, s.denom, s.type_denom, s.categorie, st_npoints(s.geom) pts from ranks r join src s using (id_app) order by 1"))

c.sql("""
create table aop as
select r.story_rank, s.id_app, any_value(s.app) app, any_value(s.denom) denom, any_value(s.categorie) categorie,
       st_transform(st_union_agg(st_makevalid(s.geom)), 'EPSG:2154', 'EPSG:4326', always_xy := true) geom
from ranks r join src s using (id_app)
where s.type_denom = 'appellation'
group by all
""")
c.sql("""
create table out as select *,
  round(st_area(st_transform(geom, 'EPSG:4326', 'EPSG:2154', always_xy := true)) / 1e6) area_km2,
  st_xmin(geom) xmin, st_ymin(geom) ymin, st_xmax(geom) xmax, st_ymax(geom) ymax,
  st_x(st_centroid(geom)) cx, st_y(st_centroid(geom)) cy,
  st_numgeometries(geom) nparts
from aop order by story_rank
""")
print(c.sql("select * exclude geom from out"))
c.sql(f"copy (select * from out) to '{ROOT}/aop_areas.parquet' (format parquet)")
c.sql(f"""copy (select story_rank, id_app, denom, area_km2,
          st_simplifypreservetopology(geom, 0.001) geom from out)
          to '{ROOT}/aop_areas_simple.geojson' with (format gdal, driver 'GeoJSON', layer_creation_options 'COORDINATE_PRECISION=5')""")
