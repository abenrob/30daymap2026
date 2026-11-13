"""Day 13: build the files the page reads.

  places.parquet  one row per place (French communes + arrondissements + placed foreign workplaces):
                  code, name, country, lon, lat, residents (employed, 15+), jobs (held by residents
                  of France), stay (live and work there), job_ratio. Loaded whole at start.
  flows.parquet   every origin-destination flow written twice, once from each end
                  (focus, other, dir 0 = focus residents working in other, 1 = other residents
                  working in focus), intra-commune flows once (dir 2), with distance in km.
                  Sorted by focus in small row groups, so one click reads one or two row groups
                  over an HTTP range request.
  communes.parquet  boundaries from 01_boundaries.py (copied).

Usage: python3 03_web_data.py <data_dir> <out_dir>
"""
import os, shutil, sys, tempfile, zipfile
import duckdb, geopandas as gpd

data, out = map(os.path.abspath, sys.argv[1:3]); os.makedirs(out, exist_ok=True)
tmp = tempfile.mkdtemp()
with zipfile.ZipFile(os.path.join(data, "raw", "base-flux-mobilite-domicile-lieu-travail-2022_csv.zip")) as z:
    z.extractall(tmp)
g = gpd.read_parquet(os.path.join(data, "communes_2025.parquet"))
pt = g.to_crs(2154).geometry.representative_point().to_crs(4326)
communes = g.assign(lon=pt.x.round(5), lat=pt.y.round(5), country="FR")[["code", "nom", "country", "lon", "lat"]]
foreign = gpd.pd.read_parquet(os.path.join(data, "foreign_places.parquet"), columns=["code", "osm_name", "country", "lon", "lat"]).rename(columns={"osm_name": "name"})

con = duckdb.connect()
con.register("communes", communes); con.register("foreign_pl", foreign)
con.sql(f"""create table f as select CODGEO AS o, DCLT AS d, NBFLUX_C22_ACTOCC15P::double AS n
  from read_csv('{tmp}/base-flux-mobilite-domicile-lieu-travail-2022.csv', delim=';',
                types={{'CODGEO':'VARCHAR','DCLT':'VARCHAR'}})""")
# Places off the map (abroad without a commune, region only, unplaced) keep a row with null coords.
con.sql("""create table pl as
  with named as (select DCLT AS code, any_value(L_DCLT) AS raw_name from read_csv('""" + tmp + """/base-flux-mobilite-domicile-lieu-travail-2022.csv',
                  delim=';', types={'CODGEO':'VARCHAR','DCLT':'VARCHAR'}) group by 1),
  geo as (select code, nom AS name, country, lon, lat from communes
          union all select code, name, country, lon, lat from foreign_pl)
  select n.code,
         coalesce(g.name,
                  case n.code when 'ZZZZZ' then 'Abroad, commune not given'
                              when 'AL199' then 'Saarland, commune not given'
                              when 'AL3ZZ' then 'Baden-Württemberg, commune not given' end,
                  n.raw_name) AS name,
         coalesce(g.country, case left(n.code,2) when 'SU' then 'CH' when 'AL' then 'DE' when 'BE' then 'BE'
                                    when 'LU' then 'LU' when 'MO' then 'MC' end) AS country,
         g.lon, g.lat
  from named n left join geo g using (code)
  union all
  select c.code, c.nom, 'FR', c.lon, c.lat from communes c where c.code not in (select code from named)""")
con.sql("""create table places as
  select p.*, coalesce(r.residents, 0) AS residents, coalesce(j.jobs, 0) AS jobs, coalesce(s.stay, 0) AS stay,
         round(coalesce(j.jobs, 0) / nullif(r.residents, 0), 3) AS job_ratio
  from pl p
  left join (select o code, sum(n) AS residents from f group by 1) r using (code)
  left join (select d code, sum(n) AS jobs from f group by 1) j using (code)
  left join (select o code, n AS stay from f where o = d) s using (code)""")
con.sql("""create table fl as
  with x as (
    select o AS focus, d AS other, 0::tinyint AS dir, n from f where o <> d
    union all select d, o, 1::tinyint, n from f where o <> d
    union all select o, d, 2::tinyint, n from f where o = d)
  select x.focus, x.other, x.dir, round(x.n, 1)::float AS n,
    case when a.lon is null or b.lon is null then null
         else round(12742 * asin(sqrt(pow(sin(radians(b.lat - a.lat) / 2), 2)
              + cos(radians(a.lat)) * cos(radians(b.lat)) * pow(sin(radians(b.lon - a.lon) / 2), 2))), 1)::float end AS km
  from x left join places a on a.code = x.focus left join places b on b.code = x.other""")
# Row offsets: the page reads rows [flow_start, flow_start + flow_len) for a clicked commune.
con.sql("""create table fl_sorted as select * from fl order by focus, dir, n desc, other""")
con.sql("""create table off as select focus AS code, min(rn) - 1 AS flow_start, count(*) AS flow_len
  from (select focus, row_number() over (order by focus, dir, n desc, other) AS rn from fl_sorted) group by 1""")
con.sql(f"copy (select * from fl_sorted order by focus, dir, n desc, other) to '{out}/flows.parquet' "
        f"(format parquet, compression zstd, compression_level 19, row_group_size 16384)")
con.sql(f"copy (select p.code, p.name, p.country, p.lon::float AS lon, p.lat::float AS lat, round(p.residents)::int AS residents, "
        f"round(p.jobs)::int AS jobs, round(p.stay)::int AS stay, p.job_ratio::float AS job_ratio, "
        f"coalesce(o.flow_start, 0)::int AS flow_start, coalesce(o.flow_len, 0)::int AS flow_len "
        f"from places p left join off o using (code) order by p.code) "
        f"to '{out}/places.parquet' (format parquet, compression zstd, compression_level 19)")
# check the offsets point at the right rows
chk = con.sql(f"""with r as (select focus, row_number() over () - 1 AS i from read_parquet('{out}/flows.parquet'))
  select count(*) from r join read_parquet('{out}/places.parquet') p on p.code = r.focus
  where r.i < p.flow_start or r.i >= p.flow_start + p.flow_len""").fetchone()[0]
assert chk == 0, f"{chk} rows outside their offsets"
shutil.copy(os.path.join(data, "communes_2025.parquet"), os.path.join(out, "communes.parquet"))
shutil.rmtree(tmp)
print(con.sql("select count(*) AS n_rows, count(distinct focus) AS foci from fl"))
print(con.sql("select count(*) AS n_places, count(lon) AS placed, sum(residents)::bigint AS total_residents from places"))
for f in ("places", "flows", "communes"): print(f, os.path.getsize(f"{out}/{f}.parquet"))
