"""A small side-view Holstein, drawn with PIL at 4x and downsampled. Run directly for a test sheet."""
from PIL import Image, ImageDraw

INK = (43, 38, 32, 255)
WHITE = (255, 253, 248, 255)
PINK = (236, 166, 160, 255)
HORN = (240, 226, 196, 255)


def make_cow(width=34, mirror=False, grey=False):
    """Return an RGBA cow `width` px wide, facing left (or right if mirror). grey=True for 'no AOP' cows."""
    S = 4                                    # draw on a 40 x 30 unit grid at 4 px per unit
    im = Image.new('RGBA', (40 * S, 30 * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    lw = 2 * S
    for x in (12, 16, 27, 31):               # legs and hooves
        d.rounded_rectangle([x * S, 19 * S, (x + 3) * S, 28 * S], radius=S, fill=WHITE, outline=INK, width=lw)
        d.rounded_rectangle([x * S, 25.5 * S, (x + 3) * S, 28 * S], radius=S, fill=INK)
    d.line([(35 * S, 9 * S), (38 * S, 15 * S), (37.5 * S, 20 * S)], fill=INK, width=lw)   # tail
    d.ellipse([36 * S, 19 * S, 39 * S, 22.5 * S], fill=INK)
    d.ellipse([22 * S, 17 * S, 27 * S, 22 * S], fill=PINK, outline=INK, width=S)          # udder
    d.rounded_rectangle([9 * S, 6 * S, 36 * S, 21 * S], radius=6 * S, fill=WHITE, outline=INK, width=lw)  # body
    d.ellipse([18 * S, 7.5 * S, 26 * S, 13 * S], fill=INK)                                # spots
    d.ellipse([28 * S, 12 * S, 33 * S, 18 * S], fill=INK)
    d.pieslice([9 * S, 11 * S, 17 * S, 21 * S], 90, 200, fill=INK)
    d.polygon([(2 * S, 6 * S), (11 * S, 4 * S), (12 * S, 14 * S), (4 * S, 17 * S)], fill=WHITE, outline=INK)  # neck
    d.rounded_rectangle([1 * S, 3 * S, 12 * S, 15 * S], radius=4 * S, fill=WHITE, outline=INK, width=lw)      # head
    d.rounded_rectangle([0, 10 * S, 9 * S, 17 * S], radius=3 * S, fill=PINK, outline=INK, width=lw)          # muzzle
    d.ellipse([2.2 * S, 12.5 * S, 3.6 * S, 14 * S], fill=INK)                             # nostrils
    d.ellipse([5.4 * S, 12.5 * S, 6.8 * S, 14 * S], fill=INK)
    d.ellipse([4 * S, 6 * S, 6.5 * S, 8.5 * S], fill=INK)                                 # eye
    d.ellipse([9.5 * S, 3.5 * S, 14.5 * S, 6.5 * S], fill=INK)                            # ear
    d.polygon([(5 * S, 3.5 * S), (3.5 * S, 0), (7.5 * S, 3 * S)], fill=HORN, outline=INK)  # horns
    d.polygon([(9 * S, 3.2 * S), (10.5 * S, 0), (11 * S, 3.4 * S)], fill=HORN, outline=INK)
    cow = im.resize((width, round(width * 30 / 40)), Image.LANCZOS)
    if mirror:
        cow = cow.transpose(Image.FLIP_LEFT_RIGHT)
    if grey:                                 # desaturate and lighten, keep alpha
        r, g, b, a = cow.split()
        lum = Image.merge('RGB', (r, g, b)).convert('L').point(lambda v: int(v * 0.6 + 150 * 0.4))
        cow = Image.merge('RGBA', (lum, lum, lum, a))
    return cow


if __name__ == '__main__':
    sheet = Image.new('RGBA', (440, 180), (244, 238, 223, 255))
    sheet.alpha_composite(make_cow(200), (10, 10))
    sheet.alpha_composite(make_cow(36), (240, 60))
    sheet.alpha_composite(make_cow(36, mirror=True), (300, 60))
    sheet.alpha_composite(make_cow(36, grey=True), (360, 60))
    sheet.save('cow_test.png')
