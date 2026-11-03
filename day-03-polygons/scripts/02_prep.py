"""Day 3: merge the tiles, keep buildings in service, assign each to an arrondissement by a point inside it.
Needs bdtopo/arr.json: the 20 arrondissements from the WFS layer ADMINEXPRESS-COG.LATEST:arrondissement_municipal
(filter code_insee_de_la_commune_de_rattach = 75056, SRSNAME EPSG:4326)."""
import json, glob, geopandas as gpd, pandas as pd, shapely
rows=[]
for fn in glob.glob('bdtopo/tiles/*.json'):
    for f in json.load(open(fn))['features']:
        p=f['properties']; p['geom']=f['geometry']; rows.append(p)
df=pd.DataFrame(rows).drop_duplicates('cleabs')
g=gpd.GeoDataFrame(df.drop(columns='geom'), geometry=[shapely.geometry.shape(x) for x in df.geom], crs=2154)
g['geometry']=shapely.force_2d(g.geometry.values)
print(len(g), g.etat_de_l_objet.value_counts().to_dict())
g=g[g.etat_de_l_objet=='En service']
arr=gpd.read_file('bdtopo/arr.json').to_crs(2154)[['numero_de_l_arrondissement_municipal','nom_officiel','population','geometry']]
arr['n']=arr.numero_de_l_arrondissement_municipal.astype(int)
c=g.copy(); c['geometry']=g.geometry.representative_point()
j=gpd.sjoin(c,arr[['n','geometry']],predicate='within',how='inner')
g=g.loc[j.index]; g['arr']=j.n
g['area']=g.geometry.area
print(len(g)); print(g.usage_1.value_counts(dropna=False).to_dict())
print(g.groupby('arr').size().to_dict())
print('null hauteur %', round(100*g.hauteur.isna().mean(),1), 'nature', g.nature.value_counts().head(8).to_dict())
g.to_parquet('bdtopo/bat.parquet'); arr.to_parquet('bdtopo/arr.parquet')
