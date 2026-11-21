"""Spatial join: machines x zones -> cheese_vending_aop.geojson.

Adds likely_aop (every zone the machine sits in, '; '-joined), n_aop, and most_local_aop (the smallest of those
zones, used to colour machines in quick looks).
"""
import geopandas as gpd

from config import JOINED, MACHINES, ZONES

machines = gpd.read_file(MACHINES)
for c in machines.columns:                                # OSM check_date tags parse as datetimes
    if c != 'geometry' and str(machines[c].dtype).startswith('datetime'):
        machines[c] = machines[c].astype(str)
zones = gpd.read_file(ZONES)
zones['area_km2'] = zones.to_crs(3035).area / 1e6

hits = gpd.sjoin(machines[['osm', 'geometry']], zones[['cheese', 'country', 'area_km2', 'geometry']],
                 predicate='within')
per_machine = hits.groupby('osm').agg(likely_aop=('cheese', lambda s: '; '.join(sorted(s))),
                                      n_aop=('cheese', 'count'))
per_machine['most_local_aop'] = hits.sort_values('area_km2').groupby('osm').first()['cheese']

out = machines.merge(per_machine, left_on='osm', right_index=True, how='left')
out['n_aop'] = out['n_aop'].fillna(0).astype(int)
open(JOINED, 'w').write(out.to_json())
print(f'{len(out)} machines, {(out.n_aop > 0).sum()} in at least one zone ->', JOINED)
print(hits.cheese.value_counts().to_string())
