"""Cheese vending machines from the Overpass dump -> cheese_vending.geojson.

Keeps machines whose vending tag mentions cheese, fondue or dairy (milk-only dispensers and farm shops are left out)
and drops the one vending=vegan_cheese machine.
"""
import json
import re

from config import DATA, MACHINES

KEEP = re.compile(r'cheese|fondue|dairy')

features = []
for e in json.load(open(f'{DATA}/raw.json'))['elements']:
    tags = e.get('tags', {})
    vending = tags.get('vending', '')
    if not KEEP.search(vending) or 'vegan_cheese' in vending:
        continue
    lat = e['lat'] if 'lat' in e else e['center']['lat']      # ways/relations come with a center
    lon = e['lon'] if 'lon' in e else e['center']['lon']
    features.append({'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [lon, lat]},
                     'properties': {'osm': f"{e['type']}/{e['id']}", **tags}})

json.dump({'type': 'FeatureCollection', 'features': features}, open(MACHINES, 'w'))
print(len(features), 'cheese machines ->', MACHINES)
