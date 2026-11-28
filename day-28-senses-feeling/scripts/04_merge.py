"""Merge classifier output into the pool. Final valence = text verdict when there is a comment, else the file layer."""
import csv, json, glob, collections, sys
pool = list(csv.DictReader(open('data/pool.csv')))
cls = {}
for f in sorted(glob.glob('out/batch_*.out.jsonl')):
    for line in open(f):
        o = json.loads(line); cls[o['id']] = o
LABELS = {'PEUR','COLÈRE','AGACEMENT','INQUIÉTUDE','LASSITUDE','INCOMPRÉHENSION','CONSTAT','SOUHAIT','SOULAGEMENT','SATISFACTION','JOIE','GRATITUDE'}
bad = 0
for r in pool:
    o = cls.get(r['id'])
    if r['comment']:
        assert o, r['id']
        if o['label'] not in LABELS or o['valence'] not in ('pos','neg','mixed'): bad += 1
        r['label'], r['valence'], r['vivid'] = o['label'], o['valence'], o['vivid']
    else:
        r['label'], r['valence'], r['vivid'] = '', r['file_valence'], 0
    r['flipped'] = int(r['valence'] != r['file_valence'])
with open('data/points_classified.csv', 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=list(pool[0])); w.writeheader(); w.writerows(pool)
print('bad', bad, 'classified', len(cls))
print(collections.Counter((r['file_valence'], r['valence']) for r in pool))
print(collections.Counter(r['label'] for r in pool if r['comment']).most_common())
