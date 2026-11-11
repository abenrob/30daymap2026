# Day 11 · Senses: Sound: Seattle Sound, 1988–1992

A scrolling story map of the Seattle scene through fourteen shows in ten rooms, from Nirvana's first Seattle gig at the Vogue to their secret set at the Crocodile. Each show has its date, venue, bill and why it matters, and 13 of the 14 have a recording or a picture: a recording you can play in place wherever one exists, a photo where it doesn't. Nothing plays until you press play.

Page: https://abenrob.github.io/30daymap2026/day-11-senses-sound/

## How it works

- **Data.** One static GeoJSON, `shows.geojson`: a point per show with the story text and the YouTube clip. Built by hand from the sources below; venues geocoded from their period addresses with Nominatim.
- **Map.** MapLibre with the CARTO Dark Matter basemap, deck.gl layers on top through `MapboxOverlay`: venue dots (dim until the story reaches them), the active venue's label, and rings expanding from the active venue.
- **Scroll.** An `IntersectionObserver` with a zero-height band at mid-screen picks the active chapter; MapLibre `flyTo` moves the camera, with padding so the venue sits clear of the card. Clicking a venue scrolls to its next show.
- **Recordings.** Twelve shows have one. Where no recording of the show itself exists, the card says so and uses the nearest one: Nirvana at the Vogue a year later, Mother Love Bone at the Central two months earlier. Click to load: the card shows a still, and the YouTube player (youtube-nocookie) only loads when someone presses play. Only one plays at a time, and it keeps playing while you scroll.
- **Pictures.** Only freely licensed ones, stored in `images/`: the OK Hotel poster for 17 April 1991 (public domain) and the Central Tavern in the 1970s (Seattle Municipal Archives, CC BY 2.0). Re-bar has neither picture nor recording.
- **Video.** `?capture` switches to a 540 x 675 layout with large headlines, the long text hidden and the show's picture pinned over the map. `scripts/render/render.js` drives it with Playwright's fake clock, one screenshot per frame at 2x (1080 x 1350, 30 fps), scrolling with an ease between chapters and holding on each; ffmpeg stitches the MP4. Silent. Adding `&only=5,6,9,11,13,14` keeps just those chapters for a 30 s highlight reel (`node render.js out "only=5,6,9,11,13,14" 3.0 0.9`). YouTube stills of the performers stay on the page and out of the video, which shows a play tile instead.

Scaffolded with the CARTO for Agents app-building skill (`carto-develop-app`, storymap pattern).

## Picking the recordings

Every venue and date is checked against at least two sources, and every clip was checked as embeddable. Two lessons:

- Label uploads (NirvanaVEVO, the Soundgarden and Pearl Jam "Topic" channels) refuse to play embedded on other sites, and Pearl Jam's rights holders block fan uploads of single Drop in the Park songs. Those are linked out instead, and Drop in the Park uses a full-show upload that does embed.
- Single songs where a clip exists. The Off Ramp (Pearl Jam's first show), Drop in the Park and the Mother Love Bone recording are full shows because no single-song upload exists or embeds.

## Limitations

- The Underground's address (4518 University Way NE) comes from a single source.
- Fan uploads can disappear. The IDs are in `shows.geojson`; swap one and rebuild.
- Several venues have closed or changed names; the dots mark the period addresses.

## Sources

| What | Source |
| --- | --- |
| Show dates, bills, quotes | [Live Nirvana](https://livenirvana.com/), [Pearl Jam Concert Chronology](https://pearljamconcertchronology.com/), [HistoryLink](https://www.historylink.org/file/22524) (Central Tavern; [Re-bar](https://historylink.org/file/20179)), [Spin](https://www.spin.com/2020/03/pearl-jam-best-shows-ranked/2/) (Drop in the Park), [Wikipedia](https://en.wikipedia.org/wiki/Motorvision) (Motorvision, OK Hotel) |
| Venue addresses | [City of Seattle music map](https://seattle.gov/documents/Departments/FilmAndMusic/SeattleMusicMapComplete.pdf), HistoryLink, Seattle Times (Off Ramp), Wikipedia (OK Hotel) |
| Geocoding | Nominatim, © OpenStreetMap contributors |
| Basemap | © CARTO, © OpenStreetMap contributors |
| Recordings | YouTube, embedded with the standard player |
| Pictures | [OK Hotel poster, 17 April 1991](https://commons.wikimedia.org/wiki/File:OK_Hotel_concert_poster_-_April_17,_1991.png) (public domain); [Central Tavern, 1970s](https://commons.wikimedia.org/wiki/File:Seattle_-_Central_Tavern,_1970s_(53502918631)_(cropped).jpg), Seattle Municipal Archives, CC BY 2.0 |

## Layout

```
index.html, assets/, shows.geojson   the built page
images/preview.png                   social preview
scripts/app/                         source (npm install, npm run dev, npm run build)
scripts/render/                      frame renderer for the post video (needs the page served at localhost:8811)
```
