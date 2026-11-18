import numpy as np, urllib.request, sys
LAT0,LAT1,LON0,LON1=44.93,45.64,5.185,6.518
NXT,NYT,TW,TH=3,3,960,720
full=np.zeros((NYT*TH,NXT*TW),np.float32)
for j in range(NYT):
  for i in range(NXT):
    lo0=LON0+(LON1-LON0)*i/NXT; lo1=LON0+(LON1-LON0)*(i+1)/NXT
    la1=LAT1-(LAT1-LAT0)*j/NYT; la0=LAT1-(LAT1-LAT0)*(j+1)/NYT
    url=("https://data.geopf.fr/wms-r?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=ELEVATION.ELEVATIONGRIDCOVERAGE"
         f"&STYLES=&CRS=EPSG:4326&BBOX={la0},{lo0},{la1},{lo1}&WIDTH={TW}&HEIGHT={TH}&FORMAT=image/x-bil;bits=32")
    b=urllib.request.urlopen(url,timeout=120).read()
    a=np.frombuffer(b,dtype='<f4')
    if a.size!=TW*TH: print('bad',i,j,len(b),b[:200]); sys.exit(1)
    full[j*TH:(j+1)*TH,i*TW:(i+1)*TW]=a.reshape(TH,TW)
    print(i,j,a.min(),a.max())
np.save('dem.npy',full)
