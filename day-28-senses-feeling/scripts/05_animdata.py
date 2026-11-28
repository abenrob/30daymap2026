"""Build everything the animation needs: terrain heights, point drops (with timing), opening quotes, H3 res-9 hexes with bivariate class."""
import csv, json, random, collections, numpy as np, rasterio, h3
from pyproj import Transformer
from scipy.ndimage import zoom

OUT = 'web/'   # run from the day folder; data/ holds dem_40m.tif and points_classified.csv
tr = Transformer.from_crs(4326, 2154, always_xy=True)
dem = rasterio.open('data/dem_40m.tif'); Z = dem.read(1)
X0, Y1, RES = dem.transform.c, dem.transform.f, dem.transform.a
H, W = Z.shape
XC, YC = X0 + W*RES/2, Y1 - H*RES/2          # scene origin (Lambert-93)
EXAG = 1.25
def elev(x, y):
    c = min(max((x - X0)/RES, 0), W-1.001); r = min(max((Y1 - y)/RES, 0), H-1.001)
    c0, r0 = int(c), int(r); fc, fr = c-c0, r-r0
    z = Z[r0:r0+2, c0:c0+2]
    return float((z[0,0]*(1-fc)+z[0,1]*fc)*(1-fr) + (z[1,0]*(1-fc)+z[1,1]*fc)*fr)
def scene(lon, lat):
    x, y = tr.transform(lon, lat)
    return [round((x-XC)/1000, 4), round(-(y-YC)/1000, 4), round(elev(x, y)/1000*EXAG, 4)]

# --- terrain: 100 m grid, float32 heights in scene units (km * EXAG)
S = 0.4
Zs = zoom(Z, S, order=1).astype('float32')
(Zs/1000*EXAG).astype('<f4').tofile(OUT + 'terrain.f32')
terrain = dict(w=int(Zs.shape[1]), h=int(Zs.shape[0]), sizeX=W*RES/1000, sizeY=H*RES/1000)

# --- points
pts = list(csv.DictReader(open('data/points_classified.csv')))
VAL = {'neg': 0, 'mixed': 1, 'pos': 2}
LABELS = ['PEUR','COLÈRE','AGACEMENT','INQUIÉTUDE','LASSITUDE','INCOMPRÉHENSION','CONSTAT','SOUHAIT','SOULAGEMENT','SATISFACTION','JOIE','GRATITUDE']
OPEN = [  # id, optional excerpt
    ('n01131', 'Carrefour de la mort ! quand il s’agit de tourner.'),
    ('p01729', 'Ce chemin de halage fermé aux voitures, quel bonheur.'),
    ('p02653', None),
    ('n01104', None),
    ('p00768', None),
    ('n00265', None),
    ('p02673', None),
    ('n05626', None),
]
byid = {p['id']: p for p in pts}
quotes = []
for pid, txt in OPEN:
    p = byid[pid]
    quotes.append(dict(id=pid, text=txt or p['comment'].strip(), label=p['label'], valence=VAL[p['valence']],
                       file=VAL[p['file_valence']], flipped=int(p['flipped']), pos=scene(float(p['lon']), float(p['lat']))))
open_ids = {q['id'] for q in quotes}
random.seed(28)
rest = [p for p in pts if p['id'] not in open_ids]
random.shuffle(rest)
# phase 2 (speed-up): commented points first, labels shown; phase 3: everything else
commented = [p for p in rest if p['comment'] and p['label'] != 'CONSTAT']; plain = [p for p in rest if not (p['comment'] and p['label'] != 'CONSTAT')]
N2 = 160
phase2 = commented[:N2]; phase3 = commented[N2:] + plain; random.shuffle(phase3)
# timeline (seconds)
T_Q0, QDUR = 2.6, 2.4
t_quotes_end = T_Q0 + sum(QDUR + (0.9 if q['flipped'] else 0) for q in quotes)
T2a, T2b = t_quotes_end + 0.3, t_quotes_end + 9.0
T3a, T3b = T2b, T2b + 6.0
def accel(i, n, a, b, k):   # times bunching toward the end (accelerating rain)
    u = (i + 1) / n
    return a + (b - a) * u ** (1/k)
out_pts = []
t = T_Q0
for q in quotes:
    dur = QDUR + (0.9 if q['flipped'] else 0)
    q['t0'] = round(t, 3); q['tland'] = round(t + dur - 0.35, 3); t += dur
    out_pts.append(q['pos'] + [q['valence'], q['tland'], LABELS.index(q['label'])])
for i, p in enumerate(phase2):
    tl = accel(i, len(phase2), T2a + 0.6, T2b, 0.45)
    out_pts.append(scene(float(p['lon']), float(p['lat'])) + [VAL[p['valence']], round(tl, 3), LABELS.index(p['label'])])
for i, p in enumerate(phase3):
    tl = accel(i, len(phase3), T3a, T3b, 0.5)
    lab = LABELS.index(p['label']) if p['label'] else -1
    out_pts.append(scene(float(p['lon']), float(p['lat'])) + [VAL[p['valence']], round(tl, 3), lab])

# --- hexes (res 9), lean x volume
cnt = collections.defaultdict(lambda: [0, 0, 0])
for p in pts:
    cnt[h3.latlng_to_cell(float(p['lat']), float(p['lon']), 9)][VAL[p['valence']]] += 1
hexes = []
for cell, (n, m, pz) in cnt.items():
    tot = n + m + pz
    if tot < 3: continue
    lean = (pz + 0.5*m) / tot
    li = 0 if lean < 0.35 else (1 if lean <= 0.65 else 2)
    vi = 0 if tot < 6 else (1 if tot < 15 else 2)
    ring = [scene(lon, lat) for lat, lon in h3.cell_to_boundary(cell)]
    hexes.append(dict(r=ring, l=li, v=vi, n=tot))
summary = dict(total=len(pts), commented=sum(1 for p in pts if p['comment']),
               neg=sum(p['valence']=='neg' for p in pts), pos=sum(p['valence']=='pos' for p in pts), mixed=sum(p['valence']=='mixed' for p in pts),
               flipped=sum(p['flipped']=='1' for p in pts), hexes=len(hexes),
               classes={f'{l}{v}': sum(1 for h in hexes if h['l']==l and h['v']==v) for l in range(3) for v in range(3)},
               labels=collections.Counter(p['label'] for p in pts if p['label']).most_common())
tl = dict(n2=len(quotes) + len(phase2), quotesStart=T_Q0, quotesEnd=t_quotes_end, p2=[T2a, T2b], p3=[T3a, T3b], hexIn=T3b + 0.4, end=T3b + 11.0)
json.dump(dict(terrain=terrain, labels=LABELS, quotes=quotes, points=out_pts, hexes=hexes, timeline=tl, summary=summary),
          open(OUT + 'anim.json', 'w'), ensure_ascii=False, separators=(',', ':'))
print(json.dumps(tl), json.dumps(summary, ensure_ascii=False)[:600])
