"""Card / social preview -> site/day-21-openstreetmap/images/preview.png (1600 x 900).

The outro state (every cow on the map) on the right, title and key numbers on the left.
"""
import os

from PIL import Image, ImageDraw, ImageFont

from config import COL, DAY, FONTS, MAP_H, MAP_W, MAP_Y
import scene

frame = scene.render(scene.TOTAL - 0.5)                       # settled outro
map_panel = frame.crop((0, MAP_Y, MAP_W, MAP_Y + MAP_H)).resize((1156, 900), Image.LANCZOS)

im = Image.new('RGBA', (1600, 900), COL['paper'])
im.alpha_composite(map_panel, (1600 - 1156, 0))
d = ImageDraw.Draw(im)
serif = ImageFont.truetype(f'{FONTS}/DMSerifDisplay-Regular.ttf', 64)
italic = ImageFont.truetype(f'{FONTS}/DMSerifDisplay-Italic.ttf', 40)
kicker, body = scene.inter(17, 600), scene.inter(21, 400)
x = 40
d.text((x, 60), 'DAY 21 · OPENSTREETMAP', font=kicker, fill=COL['muted'])
for k, line in enumerate(['Open', 'Street', 'Cheese']):
    d.text((x - 3, 90 + k * 70), line, font=serif, fill=COL['ink'])
d.line([(x, 330), (404, 330)], fill=COL['rule'], width=1)
d.text((x, 350), f'{len(scene.machines)} cheese', font=italic, fill=COL['ink'])
d.text((x, 396), 'vending machines', font=italic, fill=COL['ink'])
lines = [f'{len(scene.SEGMENTS)} AOP cheeses could be inside,',
         'guessed from the production zone',
         'each machine sits in.',
         '',
         f'{len(scene.NO_AOP)} machines (grey) sit outside',
         'every AOP zone.']
for k, line in enumerate(lines):
    d.text((x, 470 + k * 30), line, font=body, fill=COL['ink'] if k < 3 else COL['muted'])
d.text((x, 850), '© OpenStreetMap contributors · INAO · IGN', font=scene.inter(14, 400), fill=COL['muted'])

out = os.path.join(DAY, 'images', 'preview.png')
# 256-colour palette keeps the card under 1 MB (the hillshade makes a full-colour PNG about 2 MB)
im.convert('RGB').quantize(256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG).save(out, optimize=True)
print('preview ->', out)
