"""Fetch vectors from IGN Géoplateforme WFS (EPSG:2154) for both appellations.

  python 01_fetch_vectors.py   ->  ap_*.geojson, topo_*.geojson, rpg_*.geojson, sol_*.geojson
  ap_    INAO aire parcellaire (AOC-VITICOLES:aire_parcellaire), denom ILIKE name
  topo_  BD TOPO zone_de_vegetation, nature = 'Vigne'
  rpg_   RPG 2023 parcelles_graphiques, code_group = '21' (vignes)
  sol_   INRAE soil map, sols_dominants_france_metropolitaine
"""
import json, urllib.parse, urllib.request

WFS = "https://data.geopf.fr/wfs/ows?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&OUTPUTFORMAT=application/json&SRSNAME=EPSG:2154"
BBOX = {"Saint-Joseph": (833000, 6425300, 847000, 6484100), "Gigondas": (856500, 6338800, 865800, 6346500)}
LAYERS = {
    "topo": ("BDTOPO_V3:zone_de_vegetation", "geometrie", "nature='Vigne'", "cleabs"),
    "rpg": ("RPG.2023:parcelles_graphiques", "geom", "code_group='21'", "id_parcel"),
    "sol": ("INRAE_CARTE-SOLS:sols_dominants_france_metropolitaine", "the_geom_l93", None, "id_poly"),
}


def get(typename, cql, sortby=None):
    feats, start = [], 0
    while True:
        u = (f"{WFS}&TYPENAMES={typename}&COUNT=5000&STARTINDEX={start}"
             + (f"&SORTBY={sortby}" if sortby else "") + "&CQL_FILTER=" + urllib.parse.quote(cql))
        d = json.load(urllib.request.urlopen(u, timeout=170))
        feats += d["features"]
        if len(d["features"]) < 5000:
            break
        start += 5000
    d["features"] = feats
    return d


for name, (x0, y0, x1, y1) in BBOX.items():
    d = get("AOC-VITICOLES:aire_parcellaire", f"denom ILIKE '%{name}%'")
    json.dump(d, open(f"ap_{name}.geojson", "w")); print("ap", name, len(d["features"]))
    for key, (tn, geom, flt, sort) in LAYERS.items():
        cql = f"BBOX({geom},{x0},{y0},{x1},{y1},'EPSG:2154')" + (f" AND {flt}" if flt else "")
        d = get(tn, cql, sort)
        json.dump(d, open(f"{key}_{name}.geojson", "w")); print(key, name, len(d["features"]))
