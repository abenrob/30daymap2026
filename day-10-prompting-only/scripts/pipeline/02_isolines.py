"""Walking isolines (CARTO LDS, TravelTime) from each hotel at every minute 1..30,
then import them as one table. TravelTime takes one range per request: 8 x 30 = 240 calls."""
import json, subprocess
from concurrent.futures import ThreadPoolExecutor

DEST = 'cartodb-on-gcp-cs-team.paris_restaurants.isolines'
hotels = json.load(open('hotels.geojson'))['features']

def iso(job):
    h, m = job
    lon, lat = h['geometry']['coordinates']
    out = subprocess.run(['carto', 'lds', 'isolines', f'{lon},{lat}', '--mode', 'walk', '--range', str(m * 60),
                          '--range-type', 'time', '--json'], capture_output=True, text=True, check=True).stdout
    return [{'type': 'Feature', 'properties': {'hotel_id': h['properties']['hotel_id'], 'minutes': m}, 'geometry': f['geometry']}
            for f in json.loads(out)['features']]

jobs = [(h, m) for h in hotels for m in range(1, 31)]
with ThreadPoolExecutor(8) as ex:
    feats = [f for fs in ex.map(iso, jobs) for f in fs]
json.dump({'type': 'FeatureCollection', 'features': feats}, open('isolines.geojson', 'w'))
subprocess.run(['carto', 'import', '--file', 'isolines.geojson', '--connection', 'cs_bigquery',
                '--destination', DEST, '--overwrite'], check=True)
