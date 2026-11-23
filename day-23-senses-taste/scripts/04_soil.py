"""Parent rock and dominant soil under the vines, from the INRAE soil map (map units name their parent material).

  python 04_soil.py  ->  soil_stats.json
Rock classes are keyword groups on the map-unit description (nom_ucs); see rock().
"""
import geopandas as gpd, pandas as pd, json
def rock(u):
    u=u.lower()
    if "granite" in u or "gneiss" in u: return "Granite & gneiss"
    if "micaschiste" in u or "schiste" in u: return "Mica-schist & schist"
    if "loess" in u or "éolien" in u: return "Loess"
    if "trias" in u or "jurass" in u: return "Limestone & marl (Triassic–Jurassic)"
    if "miocène" in u or "calcarénite" in u or "molassique" in u or "marnes" in u: return "Sandy marl & calcarenite (Miocene)"
    if "terrasse" in u or "alluvi" in u or "colluvi" in u or "cailloutis" in u: return "River terraces & alluvium"
    return "Other"
res={}
for n in ["Saint-Joseph","Gigondas"]:
    s=gpd.read_file(f"sol_{n}.geojson").set_crs(2154,allow_override=True)
    A=gpd.read_file(f"ap_{n}.geojson").set_crs(2154,allow_override=True).union_all()
    V=pd.concat([gpd.read_file(f"topo_{n}.geojson"),gpd.read_file(f"rpg_{n}.geojson")]).set_crs(2154,allow_override=True).union_all().buffer(0)&A
    s["rock"]=s.nom_ucs.map(rock); s["ha"]=s.intersection(V).area/1e4
    r=(s.groupby("rock").ha.sum()/s.ha.sum()*100).round(1).sort_values(ascending=False)
    soil=(s.groupby("nom_sol_dominant").ha.sum()/s.ha.sum()*100).round(1).sort_values(ascending=False)
    calc=s[s.nom_sol_dominant.isin(["CALCOSOL","CALCISOL"])|s.nom_ucs.str.contains("calcaire",case=False)].ha.sum()/s.ha.sum()*100
    res[n]=dict(rock=r.to_dict(),soil=soil.to_dict(),calcareous_pct=round(calc,1),cover_ha=round(s.ha.sum()))
    print(n,json.dumps(res[n],indent=1,ensure_ascii=False))
    print(s[s.rock=="Other"].nom_ucs.unique())
json.dump(res,open("soil_stats.json","w"),indent=1,ensure_ascii=False)
