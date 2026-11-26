"""Garonne, Lot and other main rivers from BD TOPO (cours_d_eau) for the frame."""
import io, requests, geopandas as gpd
bbox="437950,6340000,494000,6409000"   # Lambert-93, covers the v4 frame
r=requests.get("https://data.geopf.fr/wfs/ows",timeout=300,params=dict(SERVICE="WFS",VERSION="2.0.0",REQUEST="GetFeature",
   TYPENAMES="BDTOPO_V3:cours_d_eau",SRSNAME="EPSG:2154",BBOX=bbox+",urn:ogc:def:crs:EPSG::2154",OUTPUTFORMAT="application/json",COUNT=5000))
g=gpd.read_file(io.BytesIO(r.content)).set_crs(2154,allow_override=True)
print(len(g)); print(g.columns.tolist()[:20])
print(g.toponyme.value_counts().head(15))
g.to_file("rivers_all.gpkg")
