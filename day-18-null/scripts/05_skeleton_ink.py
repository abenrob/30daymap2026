"""Clean the skeleton plate (remove the title, number and logo) and recolour it as sepia ink."""
from PIL import Image, ImageDraw
import numpy as np
im = Image.open("skel.gif").convert("RGB")
d = ImageDraw.Draw(im)
for b in [(218, 52, 398, 102), (24, 182, 93, 226), (326, 286, 442, 331)]:
    d.rectangle(b, fill=(255, 255, 255))
S = 3
im = im.resize((im.width * S, im.height * S), Image.LANCZOS)
a = np.asarray(im).astype(np.float32) / 255
r, g, b = a[..., 0], a[..., 1], a[..., 2]
ink = np.clip((0.93 - (0.3 * r + 0.59 * g + 0.11 * b)) / 0.75, 0, 1)
red = (r - g > 0.12) & (r - b > 0.08)
out = np.zeros(a.shape[:2] + (4,), np.uint8)
out[..., 0] = np.where(red, 150, 52); out[..., 1] = np.where(red, 52, 40); out[..., 2] = np.where(red, 38, 30)
out[..., 3] = (ink * 255).astype(np.uint8)
o = Image.fromarray(out, "RGBA")
o.crop(o.getbbox()).save("skeleton_ink.png", optimize=True)
