"""Static check chart: the three profiles (square-root heights) over the official class band.
Not published; used to sanity-check profile.json before building the page."""
import json, matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt

S = json.load(open('profile.json'))['samples']
km = [s['km'] for s in S]
fig, ax = plt.subplots(figsize=(12, 4.2), dpi=150)

# class band along the bottom, one 1 km cell per sample
COL = {3: '#b2182b', 2: '#ef8a62', 1: '#7a9a5a', 0: '#4a7ab0'}
for s in S:
    ax.axvspan(s['km'] - 0.5, s['km'] + 0.5, ymin=0, ymax=0.06, color=COL[s['smod_l1']], lw=0)

for key, lab, c in [('pop_h', 'Population density (GHS-POP)', '#222222'),
                    ('imd_h', 'Imperviousness (HRL)', '#3a6ea5'),
                    ('bv_h', 'Built volume (GHS-BUILT-V)', '#c08a2b')]:
    ax.plot(km, [0.08 + 0.9 * s[key] for s in S], label=lab, color=c, lw=1.6)

# communes at the window centre (see 05_communes.py)
for t, k in [('Paris', 0), ('Meudon', 11), ('Magny-les-Hameaux', 24), ('Clairefontaine', 41), ('Chartres', 77)]:
    ax.text(k, 1.0, t, ha='center', fontsize=8, color='#555')
ax.text(78, 0.02, 'heights: square root of share of transect max', ha='right', fontsize=7, color='#777')

ax.set_xlim(-0.5, 78); ax.set_ylim(0, 1.05); ax.set_yticks([]); ax.set_xlabel('km from Notre-Dame')
for sp in ('top', 'right', 'left'): ax.spines[sp].set_visible(False)
h = [plt.Rectangle((0, 0), 1, 1, color=COL[k]) for k in (3, 2, 1)]
l1 = ax.legend(loc='upper right', frameon=False, fontsize=8); ax.add_artist(l1)
ax.legend(h, ['Urban centre', 'Urban cluster', 'Rural'], loc='center right', frameon=False, fontsize=8, title='GHS-SMOD', title_fontsize=8)
plt.tight_layout(); plt.savefig('preview.png')
