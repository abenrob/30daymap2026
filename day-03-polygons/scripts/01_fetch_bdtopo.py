"""Day 3: download IGN BD TOPO buildings over Paris from the Géoplateforme WFS, in 0.01 degree tiles (each under the 5,000 feature page size)."""
import json, os, urllib.request, urllib.parse, concurrent.futures as cf , time
x0,y0,x1,y1=2.224,48.815,2.470,48.903
step=0.01
props="cleabs,usage_1,usage_2,nature,hauteur,nombre_d_etages,nombre_de_logements,date_d_apparition,etat_de_l_objet,construction_legere,geometrie"
os.makedirs('bdtopo/tiles', exist_ok=True)
tiles=[(round(x0+i*step,4),round(y0+j*step,4)) for i in range(int((x1-x0)/step)+1) for j in range(int((y1-y0)/step)+1)]
def get(t):
    fn=f"bdtopo/tiles/{t[0]}_{t[1]}.json"
    if os.path.exists(fn): return fn,0
    bb=f"{t[1]},{t[0]},{t[1]+step},{t[0]+step},urn:ogc:def:crs:EPSG::4326"
    q=dict(SERVICE="WFS",VERSION="2.0.0",REQUEST="GetFeature",TYPENAMES="BDTOPO_V3:batiment",OUTPUTFORMAT="application/json",SRSNAME="EPSG:2154",BBOX=bb,COUNT="5000",PROPERTYNAME=props)
    url="https://data.geopf.fr/wfs/ows?"+urllib.parse.urlencode(q)
    for a in range(4):
        try:
            d=urllib.request.urlopen(url,timeout=120).read(); j=json.loads(d)
            n=len(j['features'])
            open(fn,'wb').write(d); return fn,n
        except Exception as e:
            time.sleep(2+a*3); err=e
    return fn,-1
t=time.time()
with cf.ThreadPoolExecutor(8) as ex:
    res=list(ex.map(get,tiles))
print(len(tiles),'tiles', sum(1 for r in res if r[1]<0),'failed', max(r[1] for r in res),'max per tile', round(time.time()-t),'s')
