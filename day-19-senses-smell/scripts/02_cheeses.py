"""Write cheeses.csv: one row per chapter. Facts from INAO product pages and cahiers des charges;
Cranfield ranks from the Cranfield University press release (Nov 2004). cranfield_aop_rank re-ranks
the 11 AOP cheeses Cranfield tested among themselves (the other 4: Vieux-Boulogne, Parmesan, Raclette, Cheddar)."""
import csv, os
# Tasting notes and pairings: CNAOL product pages (produits-laitiers-aop.fr), INAO pages and the
# AOP specifications, paraphrased. Empty = the sources give nothing beyond drinks and bread.
TABLE = {
 1: ('Creamy and melting, undergrowth and dried fruit; barnyard notes grow as it ripens',
     'A Burgundy red or dry Burgundy white; amber beer', 'Wholemeal or rye; gingerbread if you are feeling bold', ''),
 2: ('Mild and smooth: milk, butter, nuts, sometimes a little smoke',
     'Cotentin brut cider, Pommeau, a Meursault or a Pomerol; IPA or stout', 'Brioche, country bread, black bread', 'Normandy apples or grapes'),
 3: ('Supple and melting under a loud rind: milky, hay, ripe fruit, nuts, a little yeast',
     'Gewurztraminer or Pinot gris; amber beer', 'Country bread, raisin or fig bread', 'Cumin seeds (some Munster has them in the paste); quiches, omelettes, pies'),
 4: ('Milky (butter, cream) and barnyard, turning to mushroom and undergrowth when ripe to the core',
     'Pays d\'Auge cider, Pommeau or Champagne; Chinon, Beaujolais or Gevrey-Chambertin', 'Brioche, country bread, bread with candied apple and walnuts', 'Normandy apples or grapes'),
 5: ('Rich and salty, with a sharp tang from the blue',
     'A sweet white (moelleux), Port or Banyuls; amber beer', 'Nut, fig or pear bread; gingerbread', 'Walnuts, hazelnuts, figs, pears, quince paste; endive'),
 6: ('Milky and slightly salty, with some acidity in the paste (from the specification)',
     'Amber beer, a Burgundy or Bordeaux red, Pommeau', 'Sourdough, bread with lardons, country bread', 'Baked: tarte au Maroilles, goyère'),
 7: ('Cream, butter and hazelnut (from the specification)',
     'Brut Champagne, a Burgundy or Loire red, cider', 'Seeded baguette, fig or raisin bread, sourdough', ''),
 8: ('Straw and hay, turning smoky and animal with age',
     'Abbey or amber beer, Calvados, Pommeau; a Pomerol, Pommard or Vouvray', 'Cumin bread, rye, buckwheat, sourdough', ''),
}
OUT = os.path.expanduser('~/mnt/30days2026/work/day-19-senses-smell/data/cheeses.csv')
F = ['story_rank','cheese','id_app','n_lists','pct_lists','position_score','cranfield_rank','cranfield_aop_rank','aoc_year',
     'region','milk','rind','washed_with','smell_notes','story_text','taste','drink','bread','food']
R = [
 [1,'Époisses',417,21,88,73,10,9,1991,'Auxois, Burgundy (Côte-d\'Or, Yonne, Haute-Marne)','cow','washed','brine, increasingly laced with marc de Bourgogne',
  'Farmyard and brandy over a rind that turns brick red',
  'Named on 21 of the 24 lists, more than any other cheese. During ripening the rind is washed one to three times a week in brine that gets stronger in marc de Bourgogne, the local grape brandy. The twist: in the one measured test, the electronic nose and 19 human sniffers put it 9th of the 11 AOP cheeses they tried.'],
 [2,'Pont-l\'Évêque',428,15,62,60,2,1,1972,'Normandy (Calvados, Orne, Manche, part of Eure)','cow','bloomy, brushed or washed','salted water',
  'Damp cellar and hay; louder at the rind than in the paste',
  'The smelliest AOP cheese by measurement: 1st of the 11 AOP cheeses Cranfield tested. Oddly, its specification calls the rind bloomy, which may then be brushed or washed. Square, to tell it apart from its neighbour Livarot. Its area covers some 1,300 communes, most of old Lower Normandy.'],
 [3,'Munster',424,14,58,55,4,3,1969,'Vosges (Alsace and Lorraine sides)','cow','washed','salted water',
  'Sweaty and meaty from the rind, mild inside',
  'One cheese, two names, both sides of a mountain range: Munster on the Alsace side, Géromé (from Gérardmer) on the Lorraine side. Regular washing feeds the red bacteria that turn the rind ivory-orange to orange-red. 3rd of the 11 AOP cheeses Cranfield tested.'],
 [4,'Camembert de Normandie',411,10,42,78,3,2,1983,'Normandy','cow (raw)','bloomy','not washed',
  'Mushroom and cabbage, stronger as it runs',
  'The exception at the top: a bloomy rind, never washed, yet 2nd of the 11 AOP cheeses Cranfield measured, and the highest position score of all (78). Raw milk only; generic "camembert" made anywhere does not count. Its area overlaps Pont-l\'Évêque\'s and swallows Livarot\'s whole.'],
 [5,'Roquefort',432,10,42,45,6,5,1925,'Southern Massif Central (milk); Roquefort-sur-Soulzon (ripening)','ewe (raw, Lacaune)','blue','not washed',
  'Sharp, peppery blue; the smell is in the veins, not the rind',
  'The first cheese with an appellation of origin, by law in 1925. The milk comes from Lacaune ewes over a wide area of the southern Massif Central, but every Roquefort ripens for at least 90 days in the caves of one commune, under the Combalou. The blue veins are Penicillium roqueforti. 5th of the 11 AOP cheeses Cranfield tested.'],
 [6,'Maroilles',422,8,33,38,None,None,1976,'Thiérache (Nord, Aisne)','cow','washed','salted water',
  'Cellar, damp brick and undergrowth, a touch of ammonia (from the AOP specification)',
  'Its specification spells out the smell: cellar, damp brick and undergrowth, slightly ammoniated. Square and red-orange, from the Thiérache on the Belgian border. The smallest area of the eight, about 2,100 km². Cranfield did not test it.'],
 [7,'Brie de Meaux',408,5,21,39,5,4,1980,'Brie and east to the Meuse','cow (raw)','bloomy','not washed',
  'Cream, butter, mushroom and damp woodland',
  'A 36 cm wheel of raw milk with a white rind streaked red. The largest area of the eight, about 16,300 km², stretching far east of Meaux to the Meuse, where the big dairies grew in the 19th century. 4th of the 11 AOP cheeses Cranfield tested.'],
 [8,'Livarot',421,4,17,50,8,7,1975,'Pays d\'Auge, Normandy','cow (Normande breed only)','washed','salted water',
  'Smoky and animal, powerful and long',
  'Nicknamed "the Colonel" for the strips of sedge that circle it like a colonel\'s stripes. Since 2017 only milk from Normande cows qualifies. The Pays d\'Auge area, 290 communes, sits entirely inside both the Camembert and Pont-l\'Évêque areas. 7th of the 11 AOP cheeses Cranfield tested.'],
]
with open(OUT,'w',newline='',encoding='utf-8') as f:
    w=csv.writer(f); w.writerow(F); w.writerows([r + list(TABLE[r[0]]) for r in R])
print(open(OUT).read()[:600])
