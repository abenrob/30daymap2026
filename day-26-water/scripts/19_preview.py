"""1600x900 gallery preview: the arrival-date map, no text (the card carries the title)."""
import re, numpy as np
from PIL import Image, ImageDraw
src=open("18_render_v4.py").read().split("def shadow_text")[0]
src=src.replace("W,H=1080,1350","W,H=1600,900").replace("C0,C1,R0,R1=680,1780,522,1897","C0,C1,R0,R1=560,1877,815,1556")
exec(src)
img=base.copy(); m=Fi<99; cf=arrival_col(Fi); img[m]=img[m]*0.1+cf[m]*0.9
im=Image.fromarray((np.clip(img,0,1)*255).astype("uint8")).convert("RGBA"); im.alpha_composite(riv)
d=ImageDraw.Draw(im)
for x,y in zip(bx,by): d.ellipse([x-1.3,y-1.3,x+1.3,y+1.3],fill=(255,255,255,170))
for name,c,r_ in towns:
    x,y=(c+0.5-C0)*S,(r_+0.5-R0)*S
    if 0<x<W and 0<y<H: d.ellipse([x-3,y-3,x+3,y+3],fill=(236,236,241)); d.text((x+8,y-10),name,font=fTown,fill=(236,236,241))
im.convert("RGB").save("preview.png"); print(im.size)
