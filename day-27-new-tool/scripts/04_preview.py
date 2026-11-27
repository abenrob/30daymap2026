"""Site card image (1600 x 900) for Day 27: the opening frame (orthophoto, contours, label) next to the
final frame (the drawing with the title), on a navy background.

usage: python3 04_preview.py opening.png final.png out.png
    opening.png  frame 30 of the animation (03_animation.py --frames 30-30 --res 1080)
    final.png    frame 288 (or 02_still.py with the title), 1080 x 1350
"""
import sys
from PIL import Image

opening, final, out = sys.argv[1:4]
W, H = 1600, 900
PANEL_H = 900; PANEL_W = int(PANEL_H * 4 / 5)        # 720 x 900, the animation's 4:5 frame
GAP = 16
card = Image.new("RGB", (W, H), (20, 24, 42))          # NAVY, the drawing's shadow colour
x0 = (W - 2 * PANEL_W - GAP) // 2
for i, path in enumerate((opening, final)):
    im = Image.open(path).convert("RGB").resize((PANEL_W, PANEL_H), Image.LANCZOS)
    card.paste(im, (x0 + i * (PANEL_W + GAP), 0))
card.save(out, optimize=True)
print("wrote", out, card.size)
