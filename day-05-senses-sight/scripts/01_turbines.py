"""Wind turbines in Ardeche (07) and Drome (26) from OpenStreetMap, with a blade-tip height each.

Input : work/data/day-05-sight/raw/turbines_osm.json
        (Overpass: power=generator + generator:source=wind or generator:method=wind_turbine,
         inside the two departements; see the query in README.md)
Output: work/data/day-05-sight/derived/turbines.csv  (id, lon, lat, x, y in EPSG:2154, tip_m, tip_source)

Tip height rule, in order:
  1. OSM height (total height to blade tip)
  2. height:hub + rotor:diameter / 2
  3. model default: Jeumont J48/750 = 46 m hub + 24 m blade = 70 m
  4. median of tagged tips in the two departements (flagged as 'median')
Abandoned turbines (disused:power) are dropped.
"""
import csv, json, os, statistics
from pyproj import Transformer

RAW = "work/data/day-05-sight/raw/turbines_osm.json"
OUT = "work/data/day-05-sight/derived/turbines.csv"
MODEL_TIP = {"J48/750": 70.0}

els = json.load(open(RAW))["elements"]
els = [e for e in els if e.get("tags", {}).get("power") == "generator"]

def num(v):
    try:
        return float(str(v).replace("m", "").strip())
    except (TypeError, ValueError):
        return None

tagged = [num(e["tags"].get("height")) for e in els if num(e["tags"].get("height"))]
median_tip = statistics.median(tagged)

to93 = Transformer.from_crs(4326, 2154, always_xy=True)
rows = []
for e in els:
    t = e["tags"]
    tip, src = num(t.get("height")), "osm_height"
    if tip is None and num(t.get("height:hub")) and num(t.get("rotor:diameter")):
        tip, src = num(t["height:hub"]) + num(t["rotor:diameter"]) / 2, "hub_plus_rotor"
    if tip is None and t.get("model") in MODEL_TIP:
        tip, src = MODEL_TIP[t["model"]], "model_default"
    if tip is None:
        tip, src = median_tip, "median"
    x, y = to93.transform(e["lon"], e["lat"])
    rows.append(dict(id=e["id"], lon=round(e["lon"], 6), lat=round(e["lat"], 6),
                     x=round(x, 1), y=round(y, 1), tip_m=tip, tip_source=src))

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)

from collections import Counter
print(f"{len(rows)} turbines, tip {min(r['tip_m'] for r in rows):.0f} to {max(r['tip_m'] for r in rows):.0f} m, "
      f"median tagged tip {median_tip:.0f} m; sources {dict(Counter(r['tip_source'] for r in rows))}")
