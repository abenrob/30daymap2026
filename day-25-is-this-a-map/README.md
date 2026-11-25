# Day 25 · Is this a map? Lying on Charmant Som on Perseid night

Built 24-25 Nov. One poster: posts/day-25-is-this-a-map/images/01.png (1080 x 1350), 23:50:44 CEST, with white callouts, title and sources (`08_poster.py`).

Lying on your back on the summit of Charmant Som (Chartreuse, 1,867 m), looking straight up, on the night of the 2026 Perseid peak. One fisheye frame holds the whole sky, the ring of the Alps and Chartreuse on the horizon, and the glow of Grenoble rising over the Rachais ridge to the south (the city centre itself is hidden, see Skyline). No meteors on the poster (dropped 25 Nov); the expected rate is kept below for the record.

The answer to "is this a map?": yes. A fisheye pointed at the zenith is an azimuthal equidistant projection of the sky, the same projection as an all-sky chart. Seen from below, east is on the left.

## The frame

| Setting | Value |
| --- | --- |
| Observer | Charmant Som summit: highest RGE ALTI 5 m cell within 300 m of the BD TOPO point, 45.325084 N, 5.764051 E, 1,863.9 m on the DEM (1,867 m on the IGN map), eye 0.3 m above ground (lying down) |
| Date and time | 12 August 2026, 23:00 to 00:00 CEST (21:00 to 22:00 UTC), the night of the Perseid peak |
| Moon | None. New moon on 12 August 2026 (the day of the total solar eclipse over Spain); age about 29.1 days at 22:00 UTC |
| Orientation | Camera looking at the zenith, true north at the top of the frame, east on the left |
| Lens | Equidistant fisheye, 210° field of view: horizon at 90/105 = 85.7% of the image radius, 15° below the horizon visible at the rim |
| Output | Poster 1080 x 1350 (4:5): title and subtitle on top, sky circle 1,040 px across (centre at y = 702), sources at the bottom, white callouts with leader lines |

Why 210° and not 180°: from a summit the whole skyline sits within 2° of the horizon, and Grenoble is below it. A 180° lens would put the peaks in a hairline at the rim and cut the city off. If the rim band still reads thin, switch to a polynomial fisheye fitted to a stereographic mapping (r = 2 tan(z/2)), which widens the edge (a day 22 callback).

### Skyline sanity table

From `scripts/check_skyline.py`: three DEM rings in one azimuthal-equidistant grid centred on the summit, curvature with k = 0.13, eye at 1,864.2 m. Peaks use the DEM maximum within 150 m of the BD TOPO point (25 m and 100 m cells shave 10 to 50 m off the true heights). "Skyline" is the highest terrain in front of the target. The render must reproduce these within about 0.3°. The whole skyline runs from ‑1.25° to +2.56°.

| Target | Distance | Azimuth | Elevation | Skyline at that azimuth | Visible |
| --- | --- | --- | --- | --- | --- |
| Chamechaude (2,082 m) [DEM 2069 m] | 4.5 km | 155° | +2.6° | +1.3° (at 4.34 km) | yes |
| Grand Som (2,026 m) [DEM 2013 m] | 6.3 km | 36° | +1.3° | -0.6° (at 6.12 km) | yes |
| Dent de Crolles (2,062 m) [DEM 2052 m] | 7.4 km | 104° | +1.4° | +0.8° (at 7.19 km) | yes |
| Croix de Belledonne (2,926 m) [DEM 2889 m] | 24.8 km | 135° | +2.3° | +1.6° (at 24.56 km) | yes |
| Grand Pic de Belledonne (2,977 m) [DEM 2926 m] | 24.8 km | 134° | +2.4° | +1.6° (at 24.57 km) | yes |
| Moucherotte (1,901 m) [DEM 1879 m] | 22.1 km | 206° | -0.0° | -0.2° (at 21.87 km) | yes |
| Mont Blanc (4,806 m) | 102.8 km | 56° | +1.2° | +1.2° (at 102.60 km) | yes |
| Grenoble centre (place Grenette) | 15.3 km | 191° | -6.2° | -4.1° (at 11.80 km) | no |
| Saint-Égrève (mairie) | 12.0 km | 212° | -7.8° | -4.2° (at 2.34 km) | no |
| Meylan (mairie) | 12.8 km | 175° | -7.3° | -3.3° (at 9.54 km) | no |
| Saint-Martin-d'Hères (mairie) | 17.6 km | 180° | -5.4° | -3.2° (at 10.01 km) | no |
| Échirolles (mairie) | 20.4 km | 189° | -4.6° | -4.7° (at 20.18 km) | yes |
| Voiron (centre) | 14.3 km | 288° | -6.3° | +0.1° (at 4.92 km) | no |
| Chambéry (centre) | 29.4 km | 25° | -3.2° | -1.0° (at 7.81 km) | no |
| Lyon (place Bellecour) | 87.2 km | 304° | -1.5° | -1.5° (at 87.00 km) | yes |

What this means for the frame: Grenoble's centre, Meylan, Saint-Martin-d'Hères and Saint-Égrève are hidden (Rachais / Saint-Eynard ridge at 10 to 12 km, Saint-Égrève by the summit's own shoulder at 2.3 km). Only the south of the agglomeration (Échirolles, Le Pont-de-Claix, Drac valley) and part of the plain towards Voiron and Lyon are in direct view: `renders/check_viewshed.png`, 9% of the ground below 600 m within 30 km. The city appears as a glow dome over the ridge plus a thin band of lights.

## Layers

Everything is computed in linear light and added together. One tone curve is applied at the end, once.

### 1. Terrain (Blender, rendered once)

The camera never moves, so the terrain is rendered once.

- **DEM, inner.** RGE ALTI from the Géoplateforme WMS-R (`ELEVATION.ELEVATIONGRIDCOVERAGE`, float32), 25 m within 30 km of the summit, 5 m within 2 km (the summit's own shoulders decide what is hidden just below the horizon).
- **DEM, outer.** Copernicus GLO-30 resampled to 100 m, out to 130 km, so the Mont Blanc massif (across the Italian border) and the Écrins have a complete silhouette. RGE ALTI stops at the border.
- **Projection and north.** Mesh in a local ENU frame centred on the summit, built from geographic coordinates, not from Lambert-93 grid coordinates. Lambert-93 grid north is 1.94° off true north here ((5.723 − 3) x sin 45.32°); building in Lambert-93 would put every star 2° off the peaks.
- **Curvature.** Drop each vertex by d² / 2R x (1 − k), k = 0.13 (about 600 m at Mont Blanc's distance).
- **Material.** Terrain is near-black with a very faint diffuse response to the sky (starlight and airglow), so ridges separate from each other. No sun, no moon.
- **City lights.** Emission draped on the valley floors from VIIRS night lights (Earth Observation Group annual VNL v2, 2025, average_masked) or, if that is out of reach, NASA Black Marble VNP46A4. Fallback with no download: BD TOPO road and building density as a proxy, labelled as such. Colour: a mix of sodium (about 2,000 K) and LED (about 3,500 K).
- **Camera.** Cycles, panoramic, fisheye equidistant, `fisheye_fov` = 210°, square sensor, rendered at 2160 x 2160 and downsampled. Passes: terrain RGB (linear EXR) and alpha (sky mask).

### 2. Stars (Python)

- **Catalogue.** Yale Bright Star Catalogue, 5th revised edition (BSC5, 9,096 entries with positions, complete to V ≈ 6.5): position, proper motion, V magnitude, B−V colour. VizieR is unreachable from both shells; the JSON mirror at github.com/brettonw/YaleBrightStarCatalog (converted from V/50) is used. Above the horizon at 23:30: 4,070 stars to V 6.5, 2,418 to V 6.0.
- **Positions.** skyfield, J2000 to apparent topocentric altitude and azimuth for the poster's time (precession, nutation, aberration), then Bennett refraction for standard conditions at 1,867 m. Refraction lifts stars by about 0.5° at the horizon, which matters for what sits just above Mont Blanc.
- **Projection.** The same equidistant fisheye as Blender: r = R x z / 105°, z = 90° − altitude, angle = azimuth with east on the left. Checked against the Blender camera with a test dome (see Checks).
- **Brightness.** Linear flux = 10^(−0.4 V). Vega (V = 0.0) to a V = 6.5 star is about 400 to 1.
- **Drawing.** Each star is a Gaussian point spread function, about 1.2 px sigma, whose integral equals its flux, added into a float buffer. Bright stars bloom bigger after tone mapping, faint ones stay pinpoints; nothing is drawn at a fixed size.
- **Colour.** B−V to temperature (Ballesteros 2012), temperature to linear sRGB, saturation reduced to about 40%, since the eye sees most stars as near-white at night.
- **Planets.** skyfield (DE421) for any planet above the horizon in the window, drawn with the same PSF and magnitude-to-flux rule. In the window: Saturn rising in the east (1.1° at 23:00, 11.4° at 00:00, az 86°); Neptune also up but below V 6.5. Sun and Moon stay below ‑19.5°; Moon 2° from new.

Why stars are drawn in Python and not as Blender objects: sub-pixel emitters are noisy in Cycles and would need very high sample counts. Drawing them analytically with the same projection keeps them exact and noise-free. Blender keeps what it does well: the terrain and its silhouette.

**Building light direction.** VIIRS measures the light going up; the summit sees every town side-on. 02c scales each building's intensity by Garstang's (1986) emission function, p(θ) = 2(1 − F) cos θ + 0.554 F θ⁴ with F = 0.15, normalised to straight up: 0.31 for every visible town (all are seen within a few degrees of grazing).

### 3. Milky Way (Python)

- An all-sky image in galactic coordinates (ESA/Gaia/DPAC, Gaia DR2 "sky in colour", Cartesian 40k x 20k, CC BY-SA 3.0 IGO), converted to linear light.
- For each sky pixel: inverse fisheye to altitude and azimuth, to RA/Dec at the frame time, to galactic l/b, then a texture lookup. Pure numpy.
- Bright stars already in the catalogue are subtracted from the texture (or the texture is used only below V = 6.5 equivalent) so they are not counted twice. Scale set so the Milky Way's surface brightness near Cygnus matches about 21.5 mag/arcsec² against a 22.0 natural sky background.
- At 23:30 the Summer Triangle and Cygnus are near the zenith and the band runs from Sagittarius (low south) to Perseus (north-east), right across the frame.

### 4. Natural sky and light pollution (Python)

- **Zenith total.** 20.97 mag/arcsec² (Falchi atlas at the summit: natural 22.0 + artificial at 1.58 × natural). Natural part: 22.0 mag/arcsec² at the zenith, brightening towards the horizon with airmass (Garstang-style gradient), neutral to slightly green (airglow).
- **Artificial skyglow.** Falchi et al. 2016, *World Atlas of Artificial Night Sky Brightness* (GFZ Data Services, doi 10.5880/GFZ.1.4.2016.001): artificial zenith brightness at the summit sets the base glow; the direction of the dome (strongest to the south, over Grenoble, then Lyon to the north-west) comes from a sum over the VIIRS light sources weighted by distance, so the dome sits where the cities are.
- **Limiting magnitude.** Reported, not used as a cut-off: NELM ≈ 7.93 − 5 log10(10^(4.316 − SQM/5) + 1). Faint stars fade where their contrast against the background drops (low in the south, under Grenoble's dome), which is how it works in reality.

### 5. Meteors (Python)

- **Shower.** Perseids, radiant RA 48°, Dec +58° at the 2026 peak, ZHR about 100, population index r = 2.2, entry speed 59 km/s. Radiant altitude from the summit: 22.6° at 23:00, 27.9° at 00:00 CEST (`derived/sky_checks.json`).
- **Rate.** Hourly rate seen = ZHR x sin(radiant altitude) x r^(LM − 6.5). With the radiant 23° to 28° up and NELM 6.10 from the atlas: about 31 meteors in the hour (43 would need LM 6.5). Drawn as a Poisson process with a fixed seed, plus a few sporadics (about 10 per hour, random directions).
- **Paths.** Each meteor runs along the great circle away from the radiant, starting 10° to 90° from it, length 5° to 25°, longer for meteors further from the radiant. The fisheye bends these into curves, as on real all-sky camera footage.
- **Brightness.** Magnitudes drawn from the population index between −3 and +6; flux by the same rule as the stars. Additive streak with a bright head and a fading tail; meteors brighter than −1 leave a faint train that lingers about 1 s.
- **Not on the poster.** Meteors were simulated (06_meteors.py, seed 25: 32 Perseids + 9 sporadics, brightest mag 1.0) and dropped from the final image; the script is in work/_to_delete.

### 6. Overlay (after tone mapping)

- North arrow only: a thin vertical line (1.5 px, white at 70% opacity) with a small "N" in Inter above it, centred over the top of the sky circle and pointing to true north. Nothing else on the image. No labels, no compass rose, no legend.
- The overlay is drawn in 2D after rendering, so the lens does not bend it.

## Tone mapping

Sum terrain + Milky Way + natural sky + skyglow + stars in linear luminance (cd/m²). One fixed log-contrast curve, u = log10(L / zenith sky): black at u = -1.2, white at +2.6, power 2.0, soft shoulder; the zenith sky lands at about 40/255. A true-exposure curve leaves the sky mid-grey (faint stars only rise ~50% above the 20.97 mag/arcsec² background at 0.2°/px). Display choice: town lights x0.35 on top of the emission direction and the haze, so they read as warm points, not white.

## Scripts (planned)

| Script | Does |
| --- | --- |
| `common.py` | Observer, frame constants, AEQD grid, curvature drop |
| `01_fetch_dem.py` | Done. RGE ALTI 5 m (±2 km) and 25 m (±30 km) from the WMS-R, GLO-30 (day 2 tiles) at 100 m (±130 km), all on one AEQD grid centred on the summit |
| `check_skyline.py`, `check_viewshed.py` | Done. Skyline profile, sanity table, valley viewshed |
| `02_fetch_lights.py` | Done. VNL 2025 crop for the 130 km window, regridded to outer100; Falchi value at the summit is in common.py |
| `02b_fetch_buildings.py` | Done. BD TOPO (WFS) for the 2 km tiles that are lit (VIIRS > 0.5) and in view, within 45 km (379 tiles, ~1 min): `batiment` (223,849: centroid, footprint, height, usage_1) and `troncon_de_route` as lamp candidates every 30 m (373,437: importance, urbain, paved; tunnels skipped) |
| `02c_light_points.py` | Done. VIIRS (Suomi NPP night pass ~01:30 local solar time, 2-3 a.m. clock time) sees public, commercial and road lighting, not houses, so the light goes to street lamps and commercial buildings. Settlements = 8-connected VIIRS pixels >= 1 nW; towns > 30 km² (Grenoble-Voiron 355, Chambéry-Aix 167). Town pixels: lamps every 30 m on every paved urban road + commercial/industrial buildings (30% of the pixel's light by footprint). Villages (Adam: only main roads and the centre stay lit at night): the settlement's total light shared by lamps on importance <= 3 urban roads (Saint-Laurent-du-Pont: avenues Victor Hugo, Jules Ferry, Jean Jaurès, de la Gare, route des Échelles, D520, place Gambetta). Town pixels without emitters: blur moved to the nearest town pixel within 4 px, else dropped (58% of town light in the tiles: fields and roads between towns); 31% of village light lands on main-road lamps, the rest dropped. Outside the tiles VIIRS stays on the terrain. Garstang emission direction (0.31). 42,879 visible emitters (40,082 lamps at 6 m, ~70 cd towards the summit each in Saint-Laurent-du-Pont, about a magnitude-1 star from 8 km) |
| `03_build_scene.py` | Done. Five terrain levels (5 / 25 / 50 / 100 / 200 m out to 2 / 10 / 30 / 60 / 130 km) on the AEQD grid, z = h − drop − eye; quads outside the viewshed (2-cell margin) culled: 811k quads instead of 4.96M (the cloud's 7 GB ran out at ~800 B/quad). `--full` keeps every quad (Mac GPU: `blender -b -P 03_build_scene.py -- --full`), `--markers` adds peak and dome markers. Building lights: one octahedron per building (r = √(area/π) clipped 3 to 12 m, luminance = I / 2.4 r²), per-face attributes drive the emission, no shadows. VIIRS × 3e-3 cd/m² per nW/cm²/sr as emission (saved beside the .blend as viirs_lum.exr); world = 20.97 mag/arcsec² sky lighting the terrain (albedo 0.12) |
| `look_terrain.py` | Quick look with a flat sky and haze; packs terrain_2160.npz |
| `check_lens.py` | Done 25 Nov: 18 markers within 0.3 px (0.06°) of the Python projection at 1080 px; north up, east left as built; rendered skyline within 0.2° of the profile on every azimuth (the four 6° outliers are the 5° dome markers) |
| `04_render_terrain.py` | Done. 2160 px, 64 spp + OIDN (3 min, cloud CPU): terrain_2160.exr (RGBA, cd/m²) and depth_2160.exr (surfaces emit distance in km; Blender 5.2's multilayer EXR only wrote Combined). Packed as renders/terrain_2160.npz (rgb, alpha, depth_km). Outside the fisheye circle Blender writes alpha 1: mask by radius |
| `05_sky.py` | Done. BSC5 + planets to alt/az (skyfield, DE421 from skyfield-data, refraction at 10 °C, 813 hPa); ICRS to ENU matrix for the Milky Way |
| `preview_sky.py` | Throwaway preview: stars + skyline silhouette, no terrain |
| `07_compose.py` | Done. The sky circle, in cd/m²: natural sky (22.0, airmass gradient) + artificial skyglow (VIIRS sources in 2 km cells, I d^-2.5, dome model, zenith scaled to the Falchi value; neutral overhead, warm in the domes) + Milky Way (Gaia DR2 map: point sources median-filtered out, log scale mapped to 1.4 decades, Cygnus = 21.5 mag/arcsec², per-pixel ENU → ICRS → galactic lookup at half resolution) + stars (PSF σ 0.7 px, flux from V, 0.2 mag/airmass extinction) + Saturn/Neptune + meteors (slerp along the path, 0.25 s growth, 0.2 s fade). Ground: emitted light split from sky-lit rock (0.12 x sky), extinction integrated along each sightline (aerosol 0.10/km at sea level, H 1.2 km + Rayleigh, H 8 km), airlight = horizon sky in that azimuth, 15% of the light scattered out of each town kept as a halo (σ 2.5 and 9 px). One log-contrast tone curve (black at log10(L/sky) = -1.2, sky at ~40/255). Constellation lines (d3-celestial, 15% white, trimmed 0.9° at stars, hidden behind terrain), north arrow in Inter |
| `08_poster.py` | Done. Layout, white callouts (targets computed from the ephemeris and the summit geometry; label offsets by hand), title, subtitle, sources: renders/poster_3044.png = posts/.../images/01.png |

Data and renders live in `work/day-25-is-this-a-map` (`D25_WORK`). Blender 5.2.3 LTS: `pip install bpy==5.2.3` in the cloud workspace (iteration, Cycles CPU), matching Adam's Mac install so the .blend opens there; the final terrain render can run on the Mac GPU with `blender -b scene.blend -P 04_render_terrain.py`.

## Checks before posting

- **Skyline.** Peak markers on the test render land within 0.3° of the sanity table.
- **Lens match.** Render a Blender dome of 12 marker spheres at known altitude and azimuth with the real camera; the Python projection must put them on the same pixels (within 1 px at 2160).
- **Sky.** Altitude and azimuth of Vega, Deneb, Polaris and Altair at 23:30 CEST match Stellarium for the same place and time within 0.05°.
- **North.** Polaris at 23:30 CEST: altitude 45.05°, azimuth 0.8° (skyfield, refracted), so r = 44.95/105 of the radius, 0.8° east of the vertical.
- **Moon and Sun.** Both below −18° for the whole window (astronomical darkness).
- **Meteors.** Every path extended backwards passes through the radiant.

## Open questions

- Resolved: summit point (see The frame). Grenoble's centre is hidden by the Rachais ridge, not by the summit's shoulder, so moving the eye on the summit does not help. Decide: keep it (glow dome + southern suburbs), or pick another viewpoint.
- Resolved 25 Nov: EOG Annual VNL V2 **2025** average_masked (downloaded by Adam, raw/*.tif.gz, 341 MB, 11.6 GB unzipped). `02_fetch_lights.py` crops it through /vsigzip/ (~50 s) to raw/vnl_2025_crop.tif and derived/lights100.npy on the outer100 AEQD grid. Only 7.9% of the radiance within 30 km is in direct view from the summit.
- Resolved 25 Nov: Falchi atlas value read from lightpollutionmap.info (World Atlas 2015 layer) at the summit: SQM 20.97 mag/arcsec² total, artificial 271 µcd/m² = 1.58 × natural, Bortle 4. NELM 6.10, so about 2,640 stars above the horizon and about 31 Perseids in the hour. The 2.9 GB GeoTIFF is not needed.
- Resolved 25 Nov: Gaia DR2 sky in colour, Cartesian (plate carrée in galactic coordinates) 40,000 x 20,000 px, raw/1567215018845-ESA_Gaia_DR2_AllSky_Brightness_Colour_Cartesian_40kx20k.png (934 MB, downloaded by Adam). Working copy derived/gaia_dr2_8000x4000.png (pyvips shrink x5, 0.045°/px, still 4x finer than the frame's 0.2°/px). Mapping checked on the LMC: l = 0 at the centre, l increasing to the left, b = +90 at the top: x = (0.5 − l/360) W with l in (−180, 180], y = (0.5 − b/180) H. ESA notes the map is log-rescaled integrated flux, so it must be linearised (and bright BSC5 stars removed) before it is added in linear light; the scale is then set by the 21.5 mag/arcsec² Cygnus target.
- Exposure: a 22.0 mag/arcsec² background over 0.2° pixels (1,040 px for 210°) outshines V 6.5 stars spread with a 1.2 px PSF (`renders/preview_2330.png`). Needs a smaller PSF for faint stars and a black-point stretch, as a real all-sky camera would.
- Resolved 25 Nov: Blender 5.2.3 LTS via `pip install bpy==5.2.3` in the cloud (download.blender.org unreachable), same version as Adam's Mac.
- Gaia sky map licence (CC BY-SA 3.0 IGO) is credited on the poster and in the first comment.
- Clock on screen: not added.
- Terrain at night is uniform (0.12 x sky luminance), so ridges separate only through haze: compose with aerial perspective from the depth pass, L = L_t e^(-βd) + L_air (1 − e^(-βd)), β ≈ 0.025/km (`renders/terrain_haze_look.png`).
- Resolved 25 Nov: lights read as snowfields (VIIRS spreads radiance evenly over 500 m cells, and its blur spills onto fields and forest). Now concentrated into BD TOPO buildings, see `02b` / `02c`.

## Limitations

- Meteors are simulated at the expected rate for a ZHR of 100; the real 2026 rate and the actual meteors are not reproduced.
- The Milky Way is a texture, not modelled from stars.
- Skyglow direction is a distance-weighted model of light sources, not a radiative transfer model; only the zenith values come from the atlas.
- Terrain lighting at night is stylised (very faint sky light); the silhouette and its angles are what is measured.

## Data and licences

IGN RGE ALTI, Licence Ouverte Etalab 2.0, via the IGN Géoplateforme. Copernicus GLO-30 DEM, © DLR e.V. 2010 to 2014 and © Airbus Defence and Space GmbH 2014 to 2018, provided under COPERNICUS by the European Union and ESA. Yale Bright Star Catalogue, 5th revised edition (Hoffleit and Warren 1991), via VizieR (V/50). JPL DE421 ephemeris via skyfield. ESA/Gaia/DPAC all-sky map, CC BY-SA 3.0 IGO. Falchi et al. (2016), World Atlas of Artificial Night Sky Brightness, GFZ Data Services. VIIRS night lights: Earth Observation Group, Payne Institute for Public Policy, Colorado School of Mines, Annual VNL V2 2025 (public domain). IGN BD TOPO batiment, Licence Ouverte Etalab 2.0. Falchi et al. (2016) value read from lightpollutionmap.info (World Atlas 2015 layer). Constellation lines: d3-celestial, (c) 2015 Olaf Frohn, BSD 3-Clause. Yale BSC5 JSON mirror: github.com/brettonw/YaleBrightStarCatalog. Inter typeface, SIL OFL.
