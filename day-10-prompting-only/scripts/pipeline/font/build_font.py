"""Build the app font: DejaVu Sans Mono subset + 256 synthesized braille glyphs
sized to the monospace cell, so the map's 2x4 dot grid tiles without gaps."""
import sys
from fontTools.ttLib import TTFont
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools import subset

src, out = sys.argv[1], sys.argv[2]
f = TTFont(src)
adv = f['hmtx']['M'][0]
hhea = f['hhea']; asc, desc = hhea.ascent, hhea.descent  # desc negative
cell_h = asc - desc
cmap = f.getBestCmap()
# dot layout: 2 cols x 4 rows, dots are rounded-ish squares
cw, ch = adv / 2, cell_h / 4
dw, dh = cw * 0.46, ch * 0.46
# bit order of U+2800: dots 1,2,3,7 in left column top->bottom; 4,5,6,8 right
bits = {(0,0):0,(0,1):1,(0,2):2,(1,0):3,(1,1):4,(1,2):5,(0,3):6,(1,3):7}
glyf, hmtx = f['glyf'], f['hmtx']
order = list(f.getGlyphOrder())
for code in range(0x2800, 0x2900):
    name = f'braille{code:04X}'
    pen = TTGlyphPen(None)
    m = code - 0x2800
    for (cx, cy), b in bits.items():
        if m >> b & 1:
            x0 = cx * cw + (cw - dw) / 2
            ytop = asc - cy * ch - (ch - dh) / 2
            x0, x1 = round(x0), round(x0 + dw)
            y1, y0 = round(ytop), round(ytop - dh)
            pen.moveTo((x0, y0)); pen.lineTo((x0, y1)); pen.lineTo((x1, y1)); pen.lineTo((x1, y0)); pen.closePath()
    glyf[name] = pen.glyph()
    hmtx[name] = (adv, 0)
    order.append(name)
    for t in f['cmap'].tables:
        if t.isUnicode(): t.cmap[code] = name
f.setGlyphOrder(order); glyf.glyphOrder = order
f['maxp'].numGlyphs = len(order)
tmp = out + '.ttf'; f.save(tmp)
opts = subset.Options(); opts.flavor = 'woff2'; opts.layout_features = ['*']
s = subset.Subsetter(opts)
s.populate(unicodes=list(range(0x20,0x7F))+list(range(0xA0,0x180))+list(range(0x2010,0x205F))+[0x20AC]
           +list(range(0x2190,0x2200))+list(range(0x2500,0x2600))+list(range(0x2600,0x2700))+list(range(0x2800,0x2900)))
ff = TTFont(tmp); s.subset(ff); ff.flavor = 'woff2'; ff.save(out)
print(out, 'adv', adv, 'cell_h', cell_h)
