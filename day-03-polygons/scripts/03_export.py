"""Day 3: per-arrondissement building files for the page. Coordinates in Lambert-93 decimetres relative to each arrondissement's SW corner."""
import json, math, numpy as np, geopandas as gpd, shapely
g=gpd.read_parquet('bdtopo/bat.parquet'); arr=gpd.read_parquet('bdtopo/arr.parquet').sort_values('n')
TYPES={'Résidentiel':0,'Commercial et services':1,'Industriel':2,'Religieux':3,'Sportif':4,'Agricole':5,'Annexe':6,'Indifférencié':7}
g['t']=g.usage_1.map(TYPES).fillna(7).astype(int)
g['geometry']=g.geometry.simplify(0.3)
import os; os.makedirs("buildings", exist_ok=True)
idx=[]
for _,a in arr.iterrows():
    n=int(a.n); s=g[g.arr==n].sort_values('area',ascending=False)
    x0,y0,x1,y1=a.geometry.bounds
    out=[]
    for r in s.itertuples():
        rings=[]
        for p in getattr(r.geometry,'geoms',[r.geometry]):
            if p.is_empty: continue
            c=np.asarray(p.exterior.coords)[:-1]
            rings.append(np.round((c-[x0,y0])*10).astype(int).ravel().tolist())
        if not rings: continue
        mrr=r.geometry.minimum_rotated_rectangle
        cc=np.asarray(mrr.exterior.coords)
        e1=cc[1]-cc[0]; e2=cc[2]-cc[1]; e=e1 if np.hypot(*e1)>=np.hypot(*e2) else e2
        ang=math.atan2(e[1],e[0])
        out.append([r.t, round(r.area,1), None if r.hauteur!=r.hauteur or r.hauteur is None else round(r.hauteur,1),
                    None if r.nombre_de_logements!=r.nombre_de_logements or r.nombre_de_logements is None else int(r.nombre_de_logements),
                    round(ang,3), rings])
    outline=[np.round((np.asarray(p.exterior.coords)-[x0,y0])*10).astype(int).ravel().tolist() for p in getattr(a.geometry,'geoms',[a.geometry])]
    json.dump(dict(n=n,name=a.nom_officiel,pop=int(a.population),w=round((x1-x0)*10),h=round((y1-y0)*10),outline=outline,b=out),
              open(f'buildings/arr{n:02d}.json','w'),separators=(',',':'))
    # summary for index
    tc=np.bincount(s.t,minlength=8); ta=np.bincount(s.t,weights=s.area,minlength=8)
    bins=[0,50,200,1000,1e12]; sc=np.histogram(s.area,bins)[0]; sa=np.histogram(s.area,bins,weights=s.area)[0]
    idx.append(dict(n=n,name=a.nom_officiel,pop=int(a.population),count=len(s),foot=round(s.area.sum()),
        tc=tc.tolist(),ta=np.round(ta).tolist(),sc=sc.tolist(),sa=np.round(sa).tolist(),
        land=round(a.geometry.area), medh=None if s.hauteur.isna().all() else round(float(s.hauteur.median()),1)))
# simplified outlines in a shared frame for the picker
X0,Y0,X1,Y1=arr.total_bounds
pick=[dict(n=int(a.n),rings=[np.round((np.asarray(p.exterior.coords)-[X0,Y0])).astype(int).ravel().tolist() for p in getattr(a.geometry.simplify(15),'geoms',[a.geometry.simplify(15)])]) for _,a in arr.iterrows()]
json.dump(dict(types=list(TYPES),w=round(X1-X0),h=round(Y1-Y0),arr=idx,pick=pick),open('buildings/index.json','w'),separators=(',',':'))
