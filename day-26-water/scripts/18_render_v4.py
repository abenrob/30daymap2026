"""Day 26 v4: 1080x1350 (4:5) in the Day 24 style. Water coloured by arrival date on the Velographs
blues by how long it has been wet (pale = just arrived), a dark stain once it drains; final map by arrival date (plasma); hillshade relief; BD TOPO rivers as a faded reference."""
import os, sys, numpy as np, pandas as pd, geopandas as gpd
from scipy import ndimage
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from matplotlib.colors import LightSource
W,H=1080,1350
C0,C1,R0,R1=680,1780,522,1897            # 1100 x 1375 cells of 50 m
S=W/(C1-C0)
GX0,GY1=403950,6434750                     # grid origin (cell edges)
z=np.load("timing_ab.npz")
crop=lambda a: a[R0:R1,C0:C1]
arr,dep,first,dem,fl=[crop(z[k]) for k in ["arr","dep","first","dem","flooded"]]
up=lambda a,o=1: ndimage.zoom(a,(H/a.shape[0],W/a.shape[1]),order=o)
A=up(np.where(np.isfinite(arr),arr,99.)); D=up(np.where(np.isfinite(dep),dep,-99.))
Fi=up(np.where(np.isfinite(first),first,99.),0)
# ---- relief: multi-directional hillshade, dark
d=ndimage.gaussian_filter(np.nan_to_num(dem,nan=float(np.nanmin(dem))),1.5)
hs=np.mean([LightSource(az,40).hillshade(d,vert_exag=3,dx=50,dy=50) for az in (315,270,0)],0)
hs=up(hs,1); hs=(hs-hs.min())/(hs.max()-hs.min())
BG=np.array([14,14,16])/255
base=BG+np.array([0.115,0.12,0.135])*(hs**2.0)[...,None]
# ---- polar ramp (Velographs / Day 24): d3.interpolateRgbBasis(["#8700A7","#25A39D","#FDE725"])
c0,c1,c2=np.array([135,0,167])/255,np.array([37,163,157])/255,np.array([253,231,37])/255
def polar(t):
    t=np.clip(np.asarray(t,float),0,1); i=np.where(t>=1,1,np.floor(t*2))[...,None]
    v0=np.where(i<0.5,2*c0-c1,c0); v1=np.where(i<0.5,c0,c1); v2=np.where(i<0.5,c1,c2); v3=np.where(i<0.5,c2,2*c2-c1)
    u=(t[...,None]-i/2)*2; u2=u*u; u3=u2*u
    c=((1-3*u+3*u2-u3)*v0+(4-6*u2+3*u3)*v1+(1+3*u+3*u2-3*u3)*v2+u3*v3)/6
    return np.clip(c,0,1)
TA,TB=10.0,17.5                           # ramp: 11 Feb .. 18 Feb (days after 1 Feb)
norm=lambda t:(t-TA)/(TB-TA)
import matplotlib
_pl=matplotlib.colormaps["plasma"]
def arrival_col(t): return np.asarray(_pl(0.15+0.8*np.clip(norm(np.asarray(t,float)),0,1)))[...,:3]
FRESH=np.array([0.82,0.95,1.0]); DEEP=np.array([0.10,0.34,0.64]); STAIN=np.array([0.15,0.22,0.31])
# ---- rivers
rv=gpd.read_file("rivers_all.gpkg")
main=rv[rv.toponyme=="la Garonne"]; tribs=rv[rv.toponyme.isin(["le Lot","la Baïse","le Dropt","l'Avance","le Trec","le Ciron"])]
def px(geom):
    out=[]
    for g in getattr(geom,"geoms",[geom]):
        x,y=np.asarray(g.xy); out.append(list(zip((x-GX0)/50*S-C0*S,(GY1-y)/50*S-R0*S)))
    return out
riv=Image.new("RGBA",(W,H),(0,0,0,0)); rd=ImageDraw.Draw(riv)
for g in tribs.geometry:
    for l in px(g): rd.line(l,fill=(150,195,230,70),width=1)
for g in main.geometry:
    for l in px(g): rd.line(l,fill=(160,205,238,120),width=3)
# ---- buildings
b=np.load("bld_first.npz"); bx=(b["col"]+0.5-C0)*S; by=(b["row"]+0.5-R0)*S; bt=b["t"]
k=(bx>=0)&(bx<W)&(by>=0)&(by<H); bx,by,bt=bx[k],by[k],bt[k]
# ---- type
FD="/home/claude/day26/fonts/"
fnt=lambda n,s: ImageFont.truetype(FD+n,s)
fK=fnt("IBMPlexMono-Medium.ttf",15); fH=fnt("IBMPlexSans-SemiBold.ttf",40); fDek=fnt("IBMPlexSans-Regular.ttf",19)
fClock=fnt("IBMPlexMono-Medium.ttf",64); fSmall=fnt("IBMPlexMono-Regular.ttf",20); fTick=fnt("IBMPlexMono-Regular.ttf",13)
fNum=fnt("IBMPlexSans-SemiBold.ttf",30); fLab=fnt("IBMPlexSans-Regular.ttf",16); fTown=fnt("IBMPlexSans-Medium.ttf",16); fCred=fnt("IBMPlexSans-Regular.ttf",12)
towns=[("Langon",761,913),("La Réole",1101,860),("Couthures",1289,1008),("Marmande",1414,1056),("Tonneins",1634,1306),("Aiguillon",1675,1510)]
passes=pd.read_csv("passes_ab.csv"); pt=((pd.to_datetime(passes.t).dt.tz_localize(None)-pd.Timestamp("2026-02-01"))/pd.Timedelta("1D")).values
def shadow_text(im,xy,text,font,fill,anchor="la",blur=6):
    sh=Image.new("RGBA",im.size,(0,0,0,0)); ImageDraw.Draw(sh).text(xy,text,font=font,fill=(0,0,0,230),anchor=anchor)
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(blur))); ImageDraw.Draw(im).text(xy,text,font=font,fill=fill,anchor=anchor)
RX0,RX1,RY=40,400,1268                     # ramp geometry
TL0,TL1=9.0,25.5                           # timeline range (days after 1 Feb)
def frame(t,final=False):
    img=base.copy()
    if not final:
        wet=(A<=t)&(D>t); gone=(D<=t)&(A<99)
        age=np.clip(t-A,0,None); fresh=np.clip(1-age/0.6,0,1)
        img[gone]=img[gone]*0.5+STAIN*0.5
        a=np.clip(age/3.0,0,1)[...,None]; col=FRESH*(1-a)+DEEP*a
        e=np.clip(1-age/0.3,0,1)[...,None]; col=col*(1-e)+e
        img[wet]=img[wet]*0.12+col[wet]*0.88
        glow=ndimage.gaussian_filter(np.where(wet,fresh,0),6)[...,None]*1.2
        img=img+glow*np.array([0.55,0.75,0.95])*0.5
    else:
        m=Fi<99; cf=arrival_col(Fi)
        img[m]=img[m]*0.1+cf[m]*0.9
    im=Image.fromarray((np.clip(img,0,1)*255).astype("uint8")).convert("RGBA")
    im.alpha_composite(riv)
    d=ImageDraw.Draw(im)
    r=(bt<=t) if not final else np.ones(len(bt),bool)
    bc=(255,179,71,220) if not final else (255,255,255,170)
    for x,y in zip(bx[r],by[r]): d.ellipse([x-1.1,y-1.1,x+1.1,y+1.1],fill=bc)
    for name,c,r_ in towns:
        x,y=(c+0.5-C0)*S,(r_+0.5-R0)*S
        d.ellipse([x-3,y-3,x+3,y+3],fill=(236,236,241)); shadow_text(im,(x+8,y-10),name,fTown,(236,236,241),blur=3)
    # header
    shadow_text(im,(40,34),"DAY 26 · WATER",fK,(154,154,166))
    shadow_text(im,(40,56),"Watching the Garonne flood move downriver",fH,(236,236,241))
    shadow_text(im,(41,108),"Aiguillon to Langon, February 2026, seen by Sentinel-1 radar through the clouds",fDek,(180,180,191))
    # ramp (legend = arrival date)
    if final:
        ramp=(arrival_col(np.linspace(TA,TB,RX1-RX0))*255).astype("uint8")
        for i,cc in enumerate(ramp): d.line([RX0+i,RY,RX0+i,RY+6],fill=tuple(cc))
        for v,l in [(11,"12 Feb"),(14,"15 Feb"),(17,"18 Feb")]:
            x=RX0+norm(v)*(RX1-RX0); d.text((x,RY+14),l,font=fTick,fill=(139,139,149),anchor="ma")
    else:
        d.line([RX0,RY+3,RX1,RY+3],fill=(70,70,80),width=2)
        for v,l in [(10,"11 Feb"),(17,"18 Feb"),(24,"25 Feb")]:
            x=RX0+(v-TL0)/(TL1-TL0)*(RX1-RX0); d.text((x,RY+14),l,font=fTick,fill=(139,139,149),anchor="ma")
        for p in pt:
            if TL0<=p<=TL1: x=RX0+(p-TL0)/(TL1-TL0)*(RX1-RX0); d.ellipse([x-2,RY-9,x+2,RY-5],fill=(139,139,149))
    if not final:
        day=pd.Timestamp("2026-02-01")+pd.Timedelta(days=t)
        shadow_text(im,(38,1180),f"{day.day} {day:%b}",fClock,(236,236,241))
        tx=RX0+np.clip((t-TL0)/(TL1-TL0),0,1)*(RX1-RX0)
        gl=Image.new("RGBA",im.size,(0,0,0,0)); ImageDraw.Draw(gl).rectangle([tx-3,RY-8,tx+3,RY+14],fill=(255,255,255,200))
        im.alpha_composite(gl.filter(ImageFilter.GaussianBlur(5))); d=ImageDraw.Draw(im); d.rectangle([tx-1,RY-5,tx+1,RY+11],fill="white")
        km=((A<=t)&(D>t)).sum()/S**2*0.0025; nb=int(r.sum())
        shadow_text(im,(W-40,1176),f"{km:.0f} km² of open water",fNum,(236,236,241),anchor="ra")
        shadow_text(im,(W-40,1218),f"{nb:,} buildings reached".replace(","," "),fNum,(236,236,241),anchor="ra")
    else:
        shadow_text(im,(36,1170),"When the water arrived",fnt("IBMPlexSans-SemiBold.ttf",44),(236,236,241))
        shadow_text(im,(W-40,1176),f"{fl.sum()*0.0025:.0f} km² flooded",fNum,(236,236,241),anchor="ra")
        shadow_text(im,(W-40,1218),f"{len(bt):,} buildings within 50 m".replace(","," "),fNum,(236,236,241),anchor="ra")
    d=ImageDraw.Draw(im)
    if not final: d.text((RX1+10,RY-12),"dots = radar passes",font=fTick,fill=(110,110,120))
    d.text((W-40,1300),"Between radar passes, water spreads by height above the river",font=fCred,fill=(108,108,118),anchor="ra")
    d.text((W-40,1320),"Sentinel-1 © ESA/Copernicus (EOPF Zarr) · RGE ALTI, BD TOPO © IGN",font=fCred,fill=(108,108,118),anchor="ra")
    return im.convert("RGB")
if __name__=="__main__":
    if len(sys.argv)>1:
        for a in sys.argv[1:]: (frame(0,True) if a=="final" else frame(float(a))).save(f"v4_{a}.png")
        sys.exit()
    os.makedirs("frames",exist_ok=True); i=0
    ts=np.arange(9.0,25.5,1/16)
    for tt in ts: frame(tt).save(f"frames/{i:04d}.png"); i+=1
    last=frame(ts[-1]); fin=frame(0,True)
    for kk in range(24): Image.blend(last,fin,(kk+1)/24).save(f"frames/{i:04d}.png"); i+=1
    for kk in range(120): fin.save(f"frames/{i:04d}.png"); i+=1
    print("frames",i)
