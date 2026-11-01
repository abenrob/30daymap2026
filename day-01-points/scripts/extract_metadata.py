"""Day 1 step 1: read only Parquet footers to get counts and per-row-group bounding boxes.

Writes rg.parquet (one row per row group) and idf_pts.parquet (places around Paris for the figure).
"""
import re, urllib.request
import duckdb

LIST = "https://data.source.coop/fused/fsq-os-places/"
RELEASE = "2025-02-06"
xml = urllib.request.urlopen(LIST).read().decode()
keys = [k for k in re.findall(r"<Key>(.*?)</Key>", xml) if f"{RELEASE}/places/" in k and not k.endswith("_metadata")]
urls = ["https://data.source.coop/fused/" + k for k in keys]
L = "[" + ",".join(f"'{u}'" for u in urls) + "]"

con = duckdb.connect()
con.sql("INSTALL httpfs; LOAD httpfs; SET threads=16;")
print(con.sql(f"select count(*) files, sum(num_rows) rows, sum(num_row_groups) row_groups from parquet_file_metadata({L})"))
con.sql(f"""
copy (
  select file_name, row_group_id, any_value(row_group_num_rows) rows,
    max(case when path_in_schema='bbox, xmin' then stats_min::double end) x0,
    max(case when path_in_schema='bbox, xmin' then stats_max::double end) x1,
    max(case when path_in_schema='bbox, ymin' then stats_min::double end) y0,
    max(case when path_in_schema='bbox, ymin' then stats_max::double end) y1
  from parquet_metadata({L}) group by all
) to 'rg.parquet'""")
con.sql(f"""
copy (select longitude lon, latitude lat from read_parquet({L})
      where bbox.xmin between 1.9 and 2.8 and bbox.ymin between 48.6 and 49.1) to 'idf_pts.parquet'""")
