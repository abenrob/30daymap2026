"""Fetch the Isère, Drac, Romanche and Arc from IGN BD TOPO (WFS, Géoplateforme)."""
import urllib.parse, urllib.request
params = {
    "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
    "TYPENAMES": "BDTOPO_V3:cours_d_eau", "OUTPUTFORMAT": "application/json",
    "SRSNAME": "EPSG:4326", "COUNT": "500",
    # lon/lat order inside the CQL BBOX; importance 5 carries the full-detail line
    "CQL_FILTER": "toponyme IN ('l''Isère','le Drac','la Romanche','l''Arc') "
                  "AND BBOX(geometrie,5.185,44.93,6.518,45.64,'EPSG:4326')",
}
url = "https://data.geopf.fr/wfs/ows?" + urllib.parse.urlencode(params)
open("named.json", "wb").write(urllib.request.urlopen(url, timeout=400).read())
print("wrote named.json")
