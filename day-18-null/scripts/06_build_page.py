import base64
s=open('atlas.html').read()
b=lambda p:base64.b64encode(open(p,'rb').read()).decode()
s=s.replace('SKELETON_SRC','data:image/png;base64,'+b('plate/skeleton_ink.png'))
s=s.replace('BASEMAP_SRC','data:image/jpeg;base64,'+b('geo/basemap.jpg'))
s=s.replace("'SIMGRID'","'"+open('geo/sim_grid.b64').read()+"'")
s=s.replace('RIVERJSON',open('geo/rivers_km.json').read())
open('atlas_built.html','w').write(s); print(len(s))
