"""Join areas + cheeses.csv and write the web GeoJSON (simplified 0.002 deg, ~200 m; 4 decimals).
Features are ordered largest area first so smaller areas draw on top."""
import duckdb, json, csv, os
D = os.path.expanduser('~/mnt/30days2026/work/day-19-senses-smell/data')
OUT = os.path.expanduser('~/mnt/30days2026/site/day-19-senses-smell/scripts/app/public/aop.geojson')
c = duckdb.connect(); c.sql('load spatial')
rows = {int(r['story_rank']): r for r in csv.DictReader(open(f'{D}/cheeses.csv', encoding='utf-8'))}
q = f"""select story_rank, area_km2, cx, cy, xmin, ymin, xmax, ymax,
        st_asgeojson(st_simplifypreservetopology(geom, 0.002)) g
        from '{D}/aop_areas.parquet' order by area_km2 desc"""
def rnd(o): return [rnd(x) for x in o] if isinstance(o[0], list) else [round(o[0], 4), round(o[1], 4)]
feats = []
for rk, area, cx, cy, x0, y0, x1, y1, g in c.sql(q).fetchall():
    p = dict(rows[rk])
    for k in ('story_rank', 'id_app', 'n_lists', 'pct_lists', 'aoc_year', 'position_score', 'cranfield_rank', 'cranfield_aop_rank'):
        p[k] = int(p[k]) if p[k] else None
    p.update(area_km2=int(area), center=[round(cx, 4), round(cy, 4)], bbox=[round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4)])
    gj = json.loads(g); gj['coordinates'] = rnd(gj['coordinates'])
    feats.append({'type': 'Feature', 'properties': p, 'geometry': gj})
s = json.dumps({'type': 'FeatureCollection', 'features': feats}, ensure_ascii=False, separators=(',', ':'))
open(OUT, 'w', encoding='utf-8').write(s); print(OUT, len(s))
