"""Geocode the 8 hotels with CARTO LDS (TomTom) and import them to BigQuery.
Needs a logged-in CARTO CLI (carto auth login) on the CS team org."""
import csv, json, subprocess

DEST = 'cartodb-on-gcp-cs-team.paris_restaurants.hotels'
feats = []
for hid, name, addr, area in csv.reader(open('hotels_in.tsv', encoding='utf-8'), delimiter='\t'):
    out = subprocess.run(['carto', 'lds', 'geocode', addr, '--country', 'FR', '--limit', '1', '--json'],
                         capture_output=True, text=True, check=True).stdout
    g = json.loads(out)[0]['value'][0]
    print(hid, g['longitude'], g['latitude'], g['matchConfidence'])
    feats.append({'type': 'Feature', 'properties': {'hotel_id': hid, 'name': name, 'address': addr, 'area': area},
                  'geometry': {'type': 'Point', 'coordinates': [g['longitude'], g['latitude']]}})
json.dump({'type': 'FeatureCollection', 'features': feats}, open('hotels.geojson', 'w'), ensure_ascii=False)
subprocess.run(['carto', 'import', '--file', 'hotels.geojson', '--connection', 'cs_bigquery',
                '--destination', DEST, '--overwrite'], check=True)
