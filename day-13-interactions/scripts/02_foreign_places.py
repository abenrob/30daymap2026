"""Day 13: place the foreign workplaces in the INSEE flows (Switzerland, Germany, Belgium,
Luxembourg, Monaco) as points.

INSEE gives them letter-prefixed codes (SUC1L Geneve, AL157 Saarbruecken...) with upper-case,
unaccented names. Geocoded with Nominatim (OpenStreetMap), 1 request per second, cached so the
script can be re-run until done. Names repeat within a country (3 x Lichtenau in Germany), so
among up to 10 candidates we keep the one nearest the flow-weighted centroid of the French
communes that send workers there. ZZZZZ (abroad, no commune) cannot be placed and is skipped.

Usage: python3 02_foreign_places.py <data_dir> [seconds]   (re-run until "remaining 0")
Writes <data_dir>/foreign_places.parquet and foreign_places.csv (for review) when complete.
"""
import json, math, os, sys, tempfile, time, urllib.parse, urllib.request, zipfile
import duckdb, geopandas as gpd

data = os.path.abspath(sys.argv[1]); budget = float(sys.argv[2]) if len(sys.argv) > 2 else 160
cache_p = os.path.join(data, "raw", "nominatim_cache.json")
cache = json.load(open(cache_p)) if os.path.exists(cache_p) else {}
CC = {"SU": "ch", "AL": "de", "BE": "be", "LU": "lu", "MO": "mc"}
# INSEE names are cut at 20 characters and some carry typos; corrected queries, checked by hand
# against the region the code prefix points to.
OVERRIDES = {
    "BE349": "Waregem", "AL3EG": "Iffezheim", "AL245": "Kandel", "SU92D": "Bussigny",
    "SU936": "Cheseaux-sur-Lausanne", "SUB1X": "La Sagne", "SU97L": "Montagny-près-Yverdon",
    "AL236": "Offenbach an der Queich", "AL2F0": "Ludwigshafen am Rhein", "BE320": "Diksmuide",
    "AL35P": "Bruchsal", "SU94W": "Essert-sous-Champvent", "SUB1Z": "Le Landeron",
    "AL37Y": "Eggenstein-Leopoldshafen", "SUB25": "Les Geneveys-sur-Coffrane",
    "SU92Y": "Chavannes-près-Renens", "BE536": "Honnelles", "SU99W": "Saint-Légier-La Chiésaz",
    "AL224": "Landstuhl", "SU96L": "Le Vaud", "SUA4E": "Saint-Maurice", "BE21D": "Saint-Josse-ten-Noode",
    "SUB1E": "Corcelles-Cormondrèche", "SU97S": "Montricher", "SU93P": "Corcelles-près-Payerne",
    "BE522": "Chapelle-lez-Herlaimont", "AL33O": "Ballrechten-Dottingen", "BE516": "Flobecq",
    "AL3TV": "Vogtsburg im Kaiserstuhl", "AL214": "Thaleischweiler-Fröschen",
    "SU28R": "Reichenbach im Kandertal", "BE464": "Belsele",
    "AL3HH": "Leinfelden-Echterdingen", "AL35D": "Bonndorf im Schwarzwald",
    "AL274": "Schönenberg-Kübelberg", "SU47A": "Ursy", "BE551": "Écaussinnes", "SU95K": "Gingins",
    "SU73E": "Ziefen", "SU12V": "Hofstetten ZH", "SU113": "Aesch (ZH)", "SUD23": "Saignelégier",  # Goumois merged into Saignelégier
}
# "SAI" = sans autre indication: only the region is known. Kept off the map, like ZZZZZ.
REGION_ONLY = {"AL199": "Saarland", "AL3ZZ": "Baden-Württemberg"}
PLACE_TYPES = {"city", "town", "village", "hamlet", "municipality", "suburb", "city_district", "county",
               "state", "locality", "quarter", "borough", "neighbourhood", "isolated_dwelling"}
UA = "30daymap2026 day-13 commuting map (github.com/abenrob/30daymap2026)"

tmp = tempfile.mkdtemp()
with zipfile.ZipFile(os.path.join(data, "raw", "base-flux-mobilite-domicile-lieu-travail-2022_csv.zip")) as z:
    z.extractall(tmp)
g = gpd.read_parquet(os.path.join(data, "communes_2025.parquet"))
pts = g.to_crs(2154).geometry.representative_point().to_crs(4326)
cent = g.assign(lon=pts.x, lat=pts.y)[["code", "lon", "lat"]]
con = duckdb.connect(); con.register("cent", cent)
places = con.sql(f"""
  with f as (select * from read_csv('{tmp}/base-flux-mobilite-domicile-lieu-travail-2022.csv', delim=';',
                    types={{'CODGEO':'VARCHAR','DCLT':'VARCHAR'}}))
  select DCLT AS code, any_value(L_DCLT) AS name, left(DCLT, 2) cc, sum(NBFLUX_C22_ACTOCC15P) workers,
         sum(NBFLUX_C22_ACTOCC15P * c.lon) / sum(NBFLUX_C22_ACTOCC15P) olon,
         sum(NBFLUX_C22_ACTOCC15P * c.lat) / sum(NBFLUX_C22_ACTOCC15P) olat
  from f join cent c on c.code = f.CODGEO
  where regexp_full_match(DCLT, '[A-Z]{{2}}.*') and DCLT <> 'ZZZZZ'
    and DCLT not in ({",".join(repr(k) for k in REGION_ONLY)})
  group by all order by workers desc""").fetchall()

def variants(name):
    n = name.replace("(MO001)", "").strip()
    v = [n]
    for a, b in (("UE", "Ü"), ("OE", "Ö"), ("AE", "Ä")):
        if a in n.upper(): v.append(n.upper().replace(a, b))
    v.append(n.split("(")[0].split("/")[0].strip())
    return list(dict.fromkeys(v))

def search(q, cc, settlement=True):
    params = {"q": q, "countrycodes": cc, "format": "jsonv2", "limit": 10}
    if settlement: params["featureType"] = "settlement"
    req = urllib.request.Request("https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(params),
                                 headers={"User-Agent": UA})
    time.sleep(1.1)
    return json.load(urllib.request.urlopen(req, timeout=30))

t0 = time.time()
for code, name, cc, *_ in places:
    if code in cache and cache[code].get("override") == OVERRIDES.get(code): continue
    if time.time() - t0 > budget: break
    res, used = [], None
    for q in ([OVERRIDES[code]] if code in OVERRIDES else variants(name)):
        for settlement in (True, False):
            res = search(q, CC[cc], settlement)
            if res: used = q; break
        if res: break
    cache[code] = {"query": used, "override": OVERRIDES.get(code), "candidates": [
        {"name": r["name"], "lat": float(r["lat"]), "lon": float(r["lon"]), "type": r.get("addresstype"),
         "display": r["display_name"]} for r in res]}
    json.dump(cache, open(cache_p, "w"), ensure_ascii=False)

remaining = sum(1 for p in places if p[0] not in cache or cache[p[0]].get("override") != OVERRIDES.get(p[0]))
print(f"cached {len(cache)}, remaining {remaining}")
if remaining: sys.exit(0)

def km(lon1, lat1, lon2, lat2):
    p = math.pi / 180
    a = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(a))

# Pass 1: nearest place-type candidate to the flow-weighted centroid of the French origins.
# Pass 2: the 3rd character of the INSEE code is a region (SU9 Vaud, BE5 Hainaut, AL3
# Baden-Wuerttemberg...). For groups of 5+ places, re-pick the candidate nearest the group's
# median position. A pick is rejected when it is further from that centre than
# max(100 km, 2 x the group's 90th-percentile spread): catches Koeln-Muelheim for a Rhineland-
# Palatinate code without rejecting Weil am Rhein in a group as wide as Baden-Wuerttemberg.
import statistics
def cands(code):
    return [c for c in cache[code]["candidates"] if c["type"] in PLACE_TYPES]
first = {}
for code, name, cc, workers, olon, olat in places:
    cs = cands(code)
    if cs: first[code] = min(cs, key=lambda c: km(olon, olat, c["lon"], c["lat"]))
groups = {}
for code, b in first.items(): groups.setdefault(code[:3], []).append(b)
centre, limit = {}, {}
for k, v in groups.items():
    if len(v) < 5: continue
    glon, glat = statistics.median(b["lon"] for b in v), statistics.median(b["lat"] for b in v)
    spread = sorted(km(glon, glat, b["lon"], b["lat"]) for b in v)
    centre[k], limit[k] = (glon, glat), max(100, 2 * spread[int(0.9 * (len(spread) - 1))])
rows = []
for code, name, cc, workers, olon, olat in places:
    cs, flag = cands(code), None
    best = first.get(code)
    if cs and code[:3] in centre:
        glon, glat = centre[code[:3]]
        best = min(cs, key=lambda c: km(glon, glat, c["lon"], c["lat"]))
        if km(glon, glat, best["lon"], best["lat"]) > limit[code[:3]]: flag = "far from region"
    if not cs: flag = "not found"
    if flag == "far from region": best = None
    rows.append({"code": code, "name": name, "query": cache[code]["query"], "country": CC[cc].upper(),
                 "workers": round(workers, 1), "osm_name": best and best["name"],
                 "osm_display": best and best["display"], "lon": best and round(best["lon"], 5),
                 "lat": best and round(best["lat"], 5),
                 "km_from_origins": best and round(km(olon, olat, best["lon"], best["lat"]), 1),
                 "flag": flag})
df = gpd.pd.DataFrame(rows)
df.to_csv(os.path.join(data, "foreign_places.csv"), index=False)
ok = df.dropna(subset=["lon"])
gpd.GeoDataFrame(ok, geometry=gpd.points_from_xy(ok.lon, ok.lat), crs=4326).to_parquet(
    os.path.join(data, "foreign_places.parquet"), compression="zstd", geometry_encoding="geoarrow")
print(f"placed {len(ok)} of {len(df)}; unplaced workers {df[df.lon.isna()].workers.sum():.0f}; "
      f"flags {df.flag.value_counts().to_dict()}")
