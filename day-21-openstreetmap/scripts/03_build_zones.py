"""Build the AOP / PDO cheese production zones -> aop_cheese_zones.geojson.

Switzerland: each zone is a dissolve of OSM admin boundaries following Art. 2 (geographical area) of the cheese's
cahier des charges / Pflichtenheft. Several specs name units that no longer exist (pre-2006 Bernese and Vaud
districts, merged communes); the mapping to today's units is noted inline and in the README.
Austria / Germany: the g.U. cheeses of Vorarlberg, Tirol and the Allgäu, at state / Landkreis level.
France: the INAO SIQO shapefile (same file as Day 19), cheese AOPs and IGPs (`label` column).
Italy: no cheese machines are mapped in the study box, so no zones.
"""
import re
import unicodedata

import geopandas as gpd
from shapely.ops import unary_union

from config import DATA, INAO_SHP, ZONES
from osm_polygons import load_boundaries

cantons = load_boundaries(f'{DATA}/bnd_cantons.json')       # + Liechtenstein, Vorarlberg, Tirol
districts = load_boundaries(f'{DATA}/bnd_districts.json')
communes = load_boundaries(f'{DATA}/bnd_communes.json')     # VD, BE, JU, SG only
allgaeu = load_boundaries(f'{DATA}/bnd_de.json')

# Communes carry no canton tag in OSM: assign by representative point.
pts = communes.copy()
pts['geometry'] = communes.representative_point()
communes['canton'] = gpd.sjoin(pts, cantons[['name', 'geometry']].rename(columns={'name': 'canton'}),
                               predicate='within')['canton']


def norm(s):
    """Accent- and punctuation-insensitive name key."""
    return re.sub(r'[^a-z]', '', unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().lower())


missing = []


def canton(*names):
    out = []
    for n in names:
        hit = cantons[cantons.name.map(norm) == norm(n)]
        if hit.empty:                                        # bilingual names, e.g. "Fribourg/Freiburg"
            hit = cantons[cantons.name.str.contains(n, regex=False)]
        if hit.empty:
            missing.append(f'canton {n}')
        out += list(hit.geometry)
    return out


def district(*names):
    out = []
    for n in names:
        hit = districts[districts.name == n]
        if hit.empty:
            missing.append(f'district {n}')
        out += list(hit.geometry)
    return out


def commune(in_canton, *names, required=True):
    out = []
    for n in names:
        hit = communes[(communes.name.map(norm) == norm(n)) & communes.canton.str.contains(in_canton, regex=False)]
        if hit.empty and required:
            missing.append(f'commune {n} ({in_canton})')
        out += list(hit.geometry)
    return out


def union(parts):
    return unary_union(parts)


def minus(shape, parts):
    return shape.difference(union(parts)) if parts else shape


JURA_BERNOIS = 'Arrondissement administratif du Jura bernois'
zones = {}   # name -> (geometry, country)

# Gruyère: FR, VD, NE, JU, the Jura bernois and six named Bern communes (dairy catchments ignored)
zones['Gruyère'] = (union(canton('Fribourg', 'Vaud', 'Neuchâtel', 'Jura') + district(JURA_BERNOIS) +
                          commune('Bern', 'Ferenbalm', 'Guggisberg', 'Mühleberg', 'Münchenwiler', 'Rüschegg',
                                  'Schwarzenburg')), 'CH')
# Vacherin fribourgeois: canton Fribourg + Clavaleyres (now part of Murten FR) and Münchenwiler
zones['Vacherin fribourgeois'] = (union(canton('Fribourg') + commune('Bern', 'Münchenwiler')), 'CH')
# Emmentaler: AG, BE without the former district of Moutier (approximated as BE minus the Jura bernois), LU, SO,
# SG, TG, ZG, ZH, plus the Lac/See and Sense districts of Fribourg
zones['Emmentaler'] = (union(canton('Aargau', 'Luzern', 'Solothurn', 'St. Gallen', 'Thurgau', 'Zug', 'Zürich') +
                             [minus(union(canton('Bern')), district(JURA_BERNOIS))] +
                             district('Seebezirk / District du Lac', 'Sensebezirk')), 'CH')
# Sbrinz: LU, SZ, OW, NW, ZG (the named dairy catchments in SG and AG are left out)
zones['Sbrinz'] = (union(canton('Luzern', 'Schwyz', 'Obwalden', 'Nidwalden', 'Zug')), 'CH')
# Tête de Moine: Franches-Montagnes, Porrentruy, Saulcy, and the Jura bernois minus the Plateau de Diesse,
# Nods and La Neuveville (mountain-zone limit not applied)
zones['Tête de Moine'] = (union(district('District des Franches-Montagnes', 'District de Porrentruy') +
                                commune('Jura', 'Saulcy') +
                                [minus(union(district(JURA_BERNOIS)),
                                       commune('Bern', 'Nods', 'Plateau de Diesse', 'La Neuveville'))]), 'CH')
# Vacherin Mont-d'Or: Jura-Nord vaudois minus the Yverdon plain communes, Morges minus three lakeside communes,
# ten Gros-de-Vaud and four Nyon communes (alpine pastures in (e) and (f) skipped)
VMO_EXCLUDED = ['Belmont-sur-Yverdon', 'Bioley-Magnoux', 'Chamblon', 'Champvent', 'Chavannes-le-Chêne',
                'Chêne-Pâquier', 'Cheseaux-Noréaz', 'Cronay', 'Cuarny', 'Démoret', 'Donneloye', 'Ependes',
                'Essert-Pittet', 'Mathod', 'Molondin', 'Montagny-près-Yverdon', 'Orzens', 'Pomy', 'Rovray', 'Suchy',
                'Suscévaz', 'Treycovagnes', 'Ursins', 'Valeyres-sous-Montagny', 'Valeyres-sous-Ursins',
                'Villars-Epeney', 'Yverdon-les-Bains', 'Yvonand']   # Ependes, Essert-Pittet have since merged
zones["Vacherin Mont-d'Or"] = (union(
    [minus(union(district('District du Jura-Nord vaudois')), commune('Vaud', *VMO_EXCLUDED, required=False)),
     minus(union(district('District de Morges')), commune('Vaud', 'Denges', 'Echandens', 'Préverenges'))] +
    commune('Vaud', 'Bettens', 'Bournens', 'Boussens', 'Daillens', 'Lussery-Villars', 'Mex (VD)', 'Penthalaz',
            'Penthaz', 'Sullens', 'Vufflens-la-Ville', 'Essertines-sur-Rolle', 'Longirod', 'Marchissy',
            'Saint-George')), 'CH')
# L'Etivaz: ten communes of the Vaud Alps (whole communes, not only the summer pastures)
zones["L'Etivaz"] = (union(commune('Vaud', "Château-d'Oex", 'Rougemont', 'Rossinière', 'Ollon', 'Villeneuve (VD)',
                                   'Ormont-Dessus', 'Ormont-Dessous', 'Corbeyrier', 'Leysin', 'Bex')), 'CH')
# Berner Alpkäse / Hobelkäse: the old Oberland Amtsbezirke ≈ today's four Verwaltungskreise
zones['Berner Alpkäse / Hobelkäse'] = (union(district(
    'Verwaltungskreis Interlaken-Oberhasli', 'Verwaltungskreis Frutigen-Niedersimmental',
    'Verwaltungskreis Obersimmental-Saanen', 'Verwaltungskreis Thun')), 'CH')
zones['Raclette du Valais'] = (union(canton('Valais')), 'CH')
zones["Formaggio d'alpe ticinese"] = (union(canton('Ticino')), 'CH')
zones['Glarner Alpkäse'] = (union(canton('Glarus')), 'CH')
# Werdenberger / Liechtensteiner Sauerkäse and Bloderkäse: Werdenberg + Toggenburg communes (merged names) + LI
zones['Bloder-Sauerkäse'] = (union(commune('St. Gallen', 'Wartau', 'Sevelen', 'Buchs (SG)', 'Grabs', 'Gams',
                                           'Sennwald', 'Wildhaus-Alt St. Johann', 'Nesslau', 'Ebnat-Kappel', 'Amden') +
                                   canton('Liechtenstein')), 'CH/LI')
# Austria and Germany: cheeses sharing one area are kept as one zone
zones['Vorarlberger Bergkäse & Alpkäse'] = (union(canton('Vorarlberg')), 'AT')
zones['Tiroler Bergkäse, Almkäse & Graukäse'] = (union(canton('Tirol')), 'AT')
zones['Allgäuer Bergkäse & Emmentaler'] = (union(list(allgaeu.geometry)), 'DE')   # approximate area

rows = [{'cheese': k, 'country': c, 'label': 'AOP', 'source': 'OSM admin boundaries, per specification',
         'geometry': g} for k, (g, c) in zones.items() if g is not None and not g.is_empty]

# France: INAO, dairy appellations only (the categorie field holds the product family)
fr = gpd.read_file(INAO_SHP)
cat = fr.categorie.fillna('')
fr = fr[fr.signe.isin(['AOP', 'AOC', 'IGP']) & cat.str.contains(r'P[âa]te|Ch[èe]vre|romage|Lait', case=False)
        & ~cat.str.contains('Vin|Eau', case=False)]
fr = fr[fr.type_denom.fillna('appellation') == 'appellation'].to_crs(4326)
fr = fr.dissolve(by=['app', 'signe']).reset_index()
fr = fr[~fr.app.isin(["Pâtes d'Alsace", 'Raviole du Dauphiné'])]       # pasta, caught by "Pâte"
fr.loc[fr.app == 'Gruyère', 'app'] = 'Gruyère (France, IGP)'           # not the Swiss AOP
fr = fr.cx[5.0:11.0, 44.5:48.5]
for _, r in fr.iterrows():
    rows.append({'cheese': r.app, 'country': 'FR', 'label': 'AOP' if r.signe in ('AOC', 'AOP') else 'IGP',
                 'source': 'INAO SIQO aires géographiques', 'geometry': r.geometry})

out = gpd.GeoDataFrame(rows, crs=4326)
open(ZONES, 'w').write(out.to_json())      # plain write: the Mac folder forbids the delete pyogrio does first
print(len(out), 'zones ->', ZONES)
if missing:
    print('Not found in OSM:', missing)
