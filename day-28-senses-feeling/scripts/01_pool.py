"""Merge red (needs attention) and green (improved) points into one pool. Parking ignored."""
import json, csv, sys, os
src = sys.argv[1]; out = sys.argv[2]
rows = []
for fn, val in [('points-rouges-200040715.geojson', 'neg'), ('points-verts-200040715.geojson', 'pos')]:
    for i, f in enumerate(json.load(open(os.path.join(src, fn)))['features']):
        lon, lat = f['geometry']['coordinates']
        d = (f['properties'].get('description') or '').strip()
        rows.append(dict(id=f"{val[0]}{i:05d}", lon=lon, lat=lat, commune=f['properties']['commune'], file_valence=val, comment=d))
with open(os.path.join(out, 'pool.csv'), 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
c = [r for r in rows if r['comment']]
print(len(rows), 'points,', len(c), 'with comment')
# batches for classification
N = 10; k = -(-len(c)//N)
for b in range(N):
    with open(os.path.join(out, f'../batches/batch_{b:02d}.jsonl'), 'w') as fh:
        for r in c[b*k:(b+1)*k]:
            fh.write(json.dumps(dict(id=r['id'], file=r['file_valence'], text=r['comment']), ensure_ascii=False) + '\n')
