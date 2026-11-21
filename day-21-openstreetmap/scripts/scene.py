"""Open Street Cheese: the frame-by-frame scene, shared by 07_animate.py (video) and 08_preview.py (card image).

Story: one AOP cheese at a time, sorted west to east. Its production zone fades in, a cow drops onto every vending
machine inside the zone, the cows lift away, and the next cheese starts. Then grey cows for the machines outside every
AOP zone, and an outro with every cow at once. render(t) returns the RGBA frame at t seconds.
"""
import math
import random

import geopandas as gpd
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from shapely.ops import unary_union

from config import BASE_MAP, COL, FONTS, FOOTER_Y, H, JOINED, MAP_H, MAP_W, MAP_Y, W, ZONES, xy
from cow import make_cow

# ---------------------------------------------------------------- data
machines = gpd.read_file(JOINED)
on_map = [6 < x < MAP_W - 6 and 30 < y < MAP_H - 4 for x, y in (xy(g.x, g.y) for g in machines.geometry)]
machines = machines[on_map].reset_index(drop=True)          # 6 machines fall outside the frame
PTS = [xy(g.x, g.y) for g in machines.geometry]
zones = gpd.read_file(ZONES)
AOP = set(zones.loc[zones.label == 'AOP', 'cheese'])         # French IGPs stay in the data, not in the story

COUNTRY = {'CH': 'Switzerland', 'CH/LI': 'Switzerland & Liechtenstein', 'FR': 'France', 'AT': 'Austria',
           'DE': 'Germany'}
MERGE = {"Mont d'Or ou Vacherin du Haut-Doubs": "Mont d'Or", "Vacherin Mont-d'Or": "Mont d'Or"}  # same cheese, 2 sides
TITLE = {"Mont d'Or": "Mont d'Or / Vacherin Mont-d'Or", 'Reblochon ou Reblochon de Savoie': 'Reblochon',
         'Berner Alpkäse / Hobelkäse': 'Berner Alpkäse', 'Bloder-Sauerkäse': 'Bloderkäse & Sauerkäse'}

groups = {}                                                  # story cheese -> zone names + machine indices
for i, likely in enumerate(machines.likely_aop.fillna('')):
    for cheese in filter(None, likely.split('; ')):
        if cheese in AOP:
            g = groups.setdefault(MERGE.get(cheese, cheese), {'zones': set(), 'idx': set()})
            g['zones'].add(cheese)
            g['idx'].add(i)

SEGMENTS = []
for key, g in groups.items():
    zz = zones[zones.cheese.isin(g['zones'])]
    idx = sorted(g['idx'])
    countries = ' & '.join(dict.fromkeys(COUNTRY[c] for c in sorted(set(zz.country))))
    SEGMENTS.append(dict(title=TITLE.get(key, key), country=countries, idx=idx,
                         zone=unary_union(list(zz.geometry)), lon=np.mean([machines.geometry[i].x for i in idx])))
SEGMENTS.sort(key=lambda s: s['lon'])                       # sweep west -> east
WITH_AOP = sorted(set(i for s in SEGMENTS for i in s['idx']))
NO_AOP = [i for i in range(len(machines)) if i not in set(WITH_AOP)]

# ---------------------------------------------------------------- timing (seconds)
FPS = 30
T_ZONE, T_FALL, T_BOUNCE, T_HOLD, T_OUT = 0.18, 0.46, 0.40, 0.50, 0.22   # T_FALL = slowest fall
INTRO, OUTRO = 1.5, 4.5


def drop_window(n):
    """Cows start at random times inside this window; it grows with the number of cows."""
    return min(0.95, 0.3 + 0.025 * n)


def segment_length(n):
    return T_ZONE + drop_window(n) + T_FALL + T_BOUNCE + T_HOLD + T_OUT


TIMELINE, t = [], INTRO
for s in SEGMENTS:
    TIMELINE.append(t)
    t += segment_length(len(s['idx']))
T_NO_AOP = t
TOTAL = T_NO_AOP + segment_length(len(NO_AOP)) + 0.4 + OUTRO

# ---------------------------------------------------------------- type and sprites
def inter(size, weight):
    f = ImageFont.truetype(f'{FONTS}/Inter.ttf', size)
    f.set_variation_by_axes([min(max(size, 14), 32), weight])   # Inter axes: optical size, weight
    return f


F_KICKER, F_SUB, F_COUNTRY, F_COUNT, F_SMALL = inter(19, 600), inter(23, 400), inter(20, 500), inter(30, 700), inter(16, 400)
F_TITLE = ImageFont.truetype(f'{FONTS}/DMSerifDisplay-Regular.ttf', 84)
F_CHEESE = ImageFont.truetype(f'{FONTS}/DMSerifDisplay-Italic.ttf', 50)
COWS = {(m, g): make_cow(36, mirror=m, grey=g) for m in (False, True) for g in (False, True)}
ease_out = lambda u: 1 - (1 - u) ** 3


def fade(img, alpha):
    """Multiply an RGBA image's alpha by `alpha` (0..1)."""
    if alpha >= 1:
        return img
    img = img.copy()
    img.putalpha(img.getchannel('A').point(lambda v: int(v * alpha)))
    return img


# ---------------------------------------------------------------- static layers
def static_frame():
    """Header title, basemap, footer notes and every machine as a faint dot."""
    im = Image.new('RGBA', (W, H), COL['paper'])
    im.alpha_composite(Image.open(BASE_MAP).convert('RGBA'), (0, MAP_Y))
    d = ImageDraw.Draw(im, 'RGBA')
    d.text((48, 40), '#30DAYMAPCHALLENGE  ·  DAY 21  ·  OPENSTREETMAP', font=F_KICKER, fill=COL['muted'])
    d.text((44, 62), 'Open Street Cheese', font=F_TITLE, fill=COL['ink'])
    d.text((48, 172), 'Cheese vending machines mapped in OpenStreetMap,', font=F_SUB, fill=COL['ink'])
    d.text((48, 202), 'and the protected cheese each one is likely to stock', font=F_SUB, fill=COL['ink'])
    d.line([(48, 246), (W - 48, 246)], fill=COL['rule'], width=1)
    d.line([(0, FOOTER_Y), (W, FOOTER_Y)], fill=COL['rule'], width=1)
    fy = FOOTER_Y
    d.text((48, fy + 84), "A cow lands on each machine (vending=cheese, fondue or dairy) that sits inside the cheese's",
           font=F_SMALL, fill=COL['muted'])
    d.text((48, fy + 105), 'official AOP / PDO production zone. Zones built from OSM boundaries per each specification.',
           font=F_SMALL, fill=COL['muted'])
    d.text((48, fy + 140), 'Data: © OpenStreetMap contributors (ODbL) · INAO · Swiss FOAG specs · SRTM3 via IGN '
           'Géoplateforme · Natural Earth', font=F_SMALL, fill=COL['muted'])
    for x, y in PTS:
        d.ellipse([x - 2.5, y + MAP_Y - 2.5, x + 2.5, y + MAP_Y + 2.5], fill=(43, 38, 32, 120))
    return im


STATIC = static_frame()
_zone_layers = {}


def zone_layer(k):
    """Translucent gold fill + outline of segment k's production zone, map-panel sized (cached)."""
    if k not in _zone_layers:
        lay = Image.new('RGBA', (MAP_W, MAP_H), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        geom = SEGMENTS[k]['zone']
        polys = [geom] if geom.geom_type == 'Polygon' else list(geom.geoms)
        for p in polys:
            d.polygon([xy(*c) for c in p.exterior.coords], fill=(232, 182, 60, 70))
            for hole in p.interiors:
                d.polygon([xy(*c) for c in hole.coords], fill=(0, 0, 0, 0))
        for p in polys:
            d.line([xy(*c) for c in p.exterior.coords], fill=(190, 135, 20, 200), width=2, joint='curve')
        _zone_layers[k] = lay
    return _zone_layers[k]


# ---------------------------------------------------------------- cows
def bounce(tl):
    """Offset (px, negative = up) and vertical squash `tl` seconds after touchdown: two decaying hops."""
    t0 = 0
    for dur, height in [(0.24, 16), (0.14, 6)]:
        if tl < t0 + dur:
            u = (tl - t0) / dur
            return -height * math.sin(math.pi * u), (0.82 if u < 0.12 else 1.0)
        t0 += dur
    return 0, (0.9 if tl - t0 < 0.05 else 1.0)


def draw_cows(im, idx, lt, grey=False, seed=0):
    """Draw the cows for machine indices `idx`, `lt` seconds into their segment.

    Each cow gets its own start time, drop height, fall time and facing from a seeded RNG, so a segment renders the
    same on every frame. After the hold they lift 40 px and fade out together.
    """
    rnd = random.Random(seed)
    window = drop_window(len(idx))
    leave = ease_out(min(1, max(0, (lt - (T_ZONE + window + T_FALL + T_BOUNCE + T_HOLD)) / T_OUT)))
    cows = []
    for i in idx:
        t0 = T_ZONE + rnd.random() ** 0.8 * window              # sprinkle, slightly front-loaded
        fall = rnd.uniform(0.32, T_FALL)
        height = rnd.uniform(180, 320)
        mirror = rnd.random() < 0.5
        u = (lt - t0) / fall
        if u <= 0:
            continue
        if u < 1:
            dy, squash = -height * (1 - u * u), 1.0              # gravity: accelerating fall
        else:
            dy, squash = bounce(lt - t0 - fall)
        x, y = PTS[i][0], PTS[i][1] + MAP_Y
        cows.append((y, x, dy - 40 * leave, squash, mirror, min(u, 1)))
    if leave >= 0.99:
        return
    cows.sort()                                                  # southern cows in front
    shadows = Image.new('RGBA', im.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadows)
    for y, x, dy, _, _, u in cows:
        k = 1 - min(1, -dy / 120) * 0.5                          # shadow shrinks while the cow is high
        sd.ellipse([x - 13 * k, y - 3, x + 13 * k, y + 4], fill=(43, 38, 32, int(70 * u * (1 - leave) * k)))
    im.alpha_composite(shadows)
    for y, x, dy, squash, mirror, _ in cows:
        sprite = COWS[mirror, grey]
        if squash != 1.0:
            sprite = sprite.resize((int(sprite.width * (2 - squash)), int(sprite.height * squash)))
        sprite = fade(sprite, 1 - leave)
        im.alpha_composite(sprite, (int(x - sprite.width / 2), int(y + dy - sprite.height + 2)))


# ---------------------------------------------------------------- header and progress
def header(im, title, subtitle, count, alpha=1.0):
    """Current-cheese block under the title: name + country on the left, cow + count on the right."""
    lay = Image.new('RGBA', (W, 90), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    d.text((46, 46), title, font=F_CHEESE, fill=COL['ink'], anchor='ls')
    d.text((48, 76), subtitle.upper(), font=F_COUNTRY, fill=COL['muted'], anchor='ls')
    label = count if isinstance(count, str) else f"{count} machine{'s' if count != 1 else ''}"
    d.text((W - 48, 44), label, font=F_COUNT, fill=COL['ink'], anchor='rs')
    lay.alpha_composite(COWS[True, False], (int(W - 48 - d.textlength(label, font=F_COUNT) - 50), 14))
    im.alpha_composite(fade(lay, alpha), (0, 252))


def progress(im, current):
    """West-to-east dots, one per cheese plus the 'no AOP' step; the current one in gold."""
    d = ImageDraw.Draw(im)
    n = len(SEGMENTS) + 1
    x0, x1, y = 120, W - 120, FOOTER_Y + 40
    d.line([(x0, y), (x1, y)], fill=COL['rule'], width=2)
    for k in range(n):
        x = x0 + k * (x1 - x0) / (n - 1)
        r = 7 if k == current else 4
        colour = COL['accent'] if k == current else (COL['ink'] if k < current else COL['rule'])
        d.ellipse([x - r, y - r, x + r, y + r], fill=colour)
    d.text((48, y), 'WEST', font=F_SMALL, fill=COL['muted'], anchor='lm')
    d.text((W - 48, y), 'EAST', font=F_SMALL, fill=COL['muted'], anchor='rm')


def in_out(lt, length):
    """Fade in over T_ZONE, out over the last T_OUT."""
    return min(1, lt / T_ZONE) * (1 - max(0, (lt - (length - T_OUT)) / T_OUT))


# ---------------------------------------------------------------- frame
def render(t):
    im = STATIC.copy()
    if t < INTRO:
        header(im, 'Which cheese is in the machine?', 'OSM does not say, so the AOP zones guess',
               f'{len(machines)} machines', alpha=min(1, t / 0.4))
        progress(im, -1)
    elif t >= TOTAL - OUTRO:                                      # every cow at once
        lt = t - (TOTAL - OUTRO)
        header(im, f'{len(machines)} cheese machines', f'{len(WITH_AOP)} sit inside at least one AOP zone',
               f'{len(SEGMENTS)} cheeses', alpha=min(1, lt / 0.4))
        settled = T_ZONE + drop_window(len(machines)) + T_FALL + T_BOUNCE + 0.1   # stop before the lift-off
        draw_cows(im, WITH_AOP, min(lt, settled), seed=7)
        draw_cows(im, NO_AOP, min(lt, settled), grey=True, seed=8)
        progress(im, len(SEGMENTS) + 1)
    elif t >= T_NO_AOP:                                           # grey cows: no AOP zone
        lt = t - T_NO_AOP
        header(im, 'No AOP cheese', 'Outside every AOP zone: Appenzell, Graubünden, Uri, Germany…', len(NO_AOP),
               alpha=in_out(lt, segment_length(len(NO_AOP))))
        draw_cows(im, NO_AOP, lt, grey=True, seed=99)
        progress(im, len(SEGMENTS))
    else:
        k = max(i for i, t0 in enumerate(TIMELINE) if t >= t0)
        s, lt = SEGMENTS[k], t - TIMELINE[k]
        alpha = in_out(lt, segment_length(len(s['idx'])))
        im.alpha_composite(fade(zone_layer(k), alpha), (0, MAP_Y))
        header(im, s['title'], s['country'], len(s['idx']), alpha=alpha)
        draw_cows(im, s['idx'], lt, seed=k)
        progress(im, k)
    return im
