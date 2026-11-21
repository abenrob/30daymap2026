"""Turn Overpass `out geom` boundary relations into shapely polygons."""
import json

import geopandas as gpd
from shapely.geometry import LineString
from shapely.ops import polygonize, unary_union


def relation_to_polygon(rel):
    """Polygonize the outer member ways and cut out the inner ones (enclaves, lakes mapped as holes)."""
    outer, inner = [], []
    for m in rel.get('members', []):
        if m['type'] != 'way' or 'geometry' not in m:
            continue
        line = LineString([(p['lon'], p['lat']) for p in m['geometry'] if p])
        (inner if m.get('role') == 'inner' else outer).append(line)
    if not outer:
        return None
    shape = unary_union(list(polygonize(unary_union(outer))))
    if shape.is_empty:
        return None
    if inner:
        shape = shape.difference(unary_union(list(polygonize(unary_union(inner)))))
    return shape.buffer(0)


def load_boundaries(path):
    """Overpass JSON -> GeoDataFrame(name, osm_id, geometry) in EPSG:4326."""
    rows = []
    for rel in json.load(open(path))['elements']:
        if rel['type'] != 'relation':
            continue
        g = relation_to_polygon(rel)
        if g is not None:
            rows.append({'name': rel['tags'].get('name'), 'osm_id': rel['id'], 'geometry': g})
    return gpd.GeoDataFrame(rows, crs=4326)
