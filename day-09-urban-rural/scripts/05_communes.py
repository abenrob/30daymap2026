"""Add the commune at each window centre to profile/profile.json, for the place labels.
Uses geo.api.gouv.fr (reverse lookup by point). Run from site/day-09-urban-rural/."""
import json, urllib.request

P = json.load(open('profile/profile.json'))
for s in P['samples']:
    r = json.load(urllib.request.urlopen(
        f"https://geo.api.gouv.fr/communes?lat={s['lat']}&lon={s['lon']}&fields=nom", timeout=15))
    s['commune'] = r[0]['nom'] if r else None
json.dump(P, open('profile/profile.json', 'w'), indent=1, ensure_ascii=False)
print('ok', sum(1 for s in P['samples'] if s['commune']))
