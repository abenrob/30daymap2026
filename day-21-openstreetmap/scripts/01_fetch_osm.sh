#!/bin/bash
# Download everything this day needs from OpenStreetMap through Overpass:
#   - vending machines selling cheese / dairy (plus self-service farm shops, kept in raw.json for reference)
#   - admin boundaries used to build the AOP zones: Swiss cantons + Liechtenstein + Vorarlberg/Tirol,
#     Swiss districts, communes of VD/BE/JU/SG, and the Allgäu Landkreise.
# Overpass is reachable from the Mac-side shell but not from the cloud workspace.
set -euo pipefail
DATA="${OSC_WORK:-$(cd "$(dirname "$0")/../../../work/day-21-openstreetmap" && pwd)}/data"
mkdir -p "$DATA"; cd "$DATA"
UA="30daymapchallenge-day21/1.0"   # overpass-api.de answers 406 without a User-Agent

q() {   # q <outfile> <overpass QL>
  curl -sS -m 175 -A "$UA" --data-urlencode "data=$2" https://overpass-api.de/api/interpreter -o "$1"
  head -c 80 "$1" | grep -q '"version"' || { echo "Overpass error for $1:"; head -c 400 "$1"; exit 1; }
  echo "ok $1 ($(wc -c < "$1") bytes)"; sleep 5
}

BOX="45.0,5.5,47.9,10.6"   # keep in sync with config.BBOX
q raw.json "[out:json][timeout:120];
( nwr[\"vending\"~\"cheese|dairy|milk\"]($BOX);
  nwr[\"shop\"=\"farm\"][\"self_service\"=\"yes\"]($BOX); );
out center tags;"

q bnd_cantons.json '[out:json][timeout:170];
area["ISO3166-1"="CH"][admin_level=2]->.ch;
( rel(area.ch)[boundary=administrative][admin_level=4];
  rel["ISO3166-1"="LI"][admin_level=2];
  rel[boundary=administrative][admin_level=4][name~"^(Vorarlberg|Tirol)$"]["ISO3166-2"~"^AT-"]; );
out geom;'

q bnd_districts.json '[out:json][timeout:170];
area["ISO3166-1"="CH"][admin_level=2]->.ch;
rel(area.ch)[boundary=administrative][admin_level=6]; out geom;'

q bnd_communes.json '[out:json][timeout:170];
area["ISO3166-1"="CH"][admin_level=2]->.ch;
area[boundary=administrative][admin_level=4][name~"^(Vaud|Bern/Berne|Jura|St. Gallen)$"](area.ch)->.k;
rel(area.k)[boundary=administrative][admin_level=8]; out geom;'

# Allgäu: Lindau, Oberallgäu, Ostallgäu, Unterallgäu, Kempten, Kaufbeuren, Memmingen + Lkr Ravensburg
q bnd_de.json '[out:json][timeout:170];
rel[boundary=administrative][admin_level=6]["de:amtlicher_gemeindeschluessel"~"^(09776|09780|09777|09778|09763|09762|09764|08436)"];
out geom;'
