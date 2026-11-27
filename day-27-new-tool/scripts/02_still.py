"""Aiguille Dibona as a drawn comic-book panel: IGN LiDAR HD terrain rendered in Blender EEVEE with a flat
"toon" colour shader and Grease Pencil Line Art ink. Renders one still, and is also the scene builder that
03_animation.py runs before it adds the animation.

How the picture is made
-----------------------
1. Terrain. IGN LiDAR HD ground model (MNT): 1 m around the needle, 2 m elsewhere, sampled bilinearly.
   Only the part the camera can see is meshed: a 1.5 m grid in a narrow wedge from the camera to just
   behind the summit, an 8 m grid for the far ridges. In the animation (ANIM=1) a 4 m square around the
   needle is added for the top-down opening shot.
2. Colour ("toon" shader on the terrain). Blender's diffuse lighting is turned into a single brightness
   value (Shader to RGB), then cut into flat bands with CONSTANT colour ramps: navy shadow, mid grey,
   light grey on steep rock; navy, sand, pale sand on gentle ground. A slope mask decides which ramp a
   surface uses, low-frequency noise jitters both thresholds so the edges are ragged but crisp, and
   distant ridges fade towards a pale blue-grey. The sun is a point source (angle 0) so cast shadows
   have hard edges.
3. Rock texture. Vertically stretched noise paints fall-line streaks on steep rock: dark streaks on lit
   rock, pale scratches across the shadow masses.
4. Ink. Grease Pencil Line Art traces the terrain's silhouettes, split by the sun's shadow into two
   objects: thick black lines where the rock is lit, thin pale lines inside the shadow. A stack of
   Grease Pencil modifiers (noise, smooth, tapered thickness, overshoot, simplify) makes them look
   hand-inked.
5. Sky. A screen-space gradient from deep ultramarine at the top to cerulean at the horizon.

Blender 5.3 notes (learned the hard way)
- Line Art "crease" lines come back empty in 5.3 for this terrain; only contour/silhouette lines work.
  That is why the rock detail is painted by the shader (step 3), not drawn by Line Art.
- Several Line Art modifiers on one Grease Pencil object share one cache and the later ones come back
  empty, so each Line Art pass lives on its own object.
- Where two terrain meshes meet, Line Art draws the seam. Faces along every mesh border are tagged
  (freestyle_face) and excluded from Line Art.

usage: python3 02_still.py -- [--res 540] [--lens 135] [--sun_az 235] [--sun_el 30] [--out still.png]
environment: DIBONA_DATA=<folder with the rasters and font>, STYLE=rochette|ink, ANIM=1 (set by 03_animation.py)
inputs (in DIBONA_DATA, fetched with 01_fetch_rasters.py):
    dem_2m_dibona.tif   LiDAR HD MNT, 2 m, 6.19-6.30 E 44.915-44.995 N
    dem_1m_dibona.tif   LiDAR HD MNT, 1 m, 6.230-6.256 E 44.950-44.975 N (the needle)
"""
import argparse, math, os, sys, time
import numpy as np
import bpy, rasterio
from pyproj import Transformer
from mathutils import Euler
from scipy.ndimage import map_coordinates

# ===================================================================== options
ap = argparse.ArgumentParser()
ap.add_argument("--res", type=int, default=540)            # output width in px; height is 5/4 of it (4:5)
ap.add_argument("--lens", type=float, default=135)         # focal length (mm): long lens flattens the wall
ap.add_argument("--step", type=float, default=1.5)         # grid step (m) of the fine terrain mesh
ap.add_argument("--sun_az", type=float, default=235)       # sun azimuth (deg from north): SW, lights the west face
ap.add_argument("--sun_el", type=float, default=30)        # sun elevation (deg)
ap.add_argument("--dark", type=float, default=0.22)        # brightness below which a surface is in shadow
ap.add_argument("--steep", type=float, default=0.62)       # normal.z below this (~52 deg slope) counts as rock
ap.add_argument("--crease", type=float, default=110)       # Line Art crease angle (deg), STYLE=ink only
ap.add_argument("--noink", action="store_true")            # skip the Line Art (fast colour-only previews)
ap.add_argument("--out", default="renders/ink.png")
ap.add_argument("--save", default="")                      # optional .blend to save before rendering
args = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])

D = os.environ.get("DIBONA_DATA", "/home/claude/d27/dibona")
STYLE = os.environ.get("STYLE", "rochette")   # "rochette": flat colour + blue sky; "ink": black on paper
ANIM = bool(os.environ.get("ANIM"))            # set by 03_animation.py: also build the top-down square mesh

t0 = time.time()
def log(*a): print(f"[{time.time() - t0:6.1f}s]", *a, flush=True)

def srgb(r, g, b):
    """8-bit sRGB colour -> linear RGBA, which is what Blender colour sockets expect."""
    f = lambda c: (c / 255) / 12.92 if c / 255 <= 0.04045 else (((c / 255) + 0.055) / 1.055) ** 2.4
    return (f(r), f(g), f(b), 1)

# Palette. Shadow is a navy rather than black so it sits with the blue sky.
NAVY = srgb(20, 24, 42)
PAPER = (0.93, 0.91, 0.86, 1)                  # STYLE=ink background and lit surfaces
INK = (0.035, 0.032, 0.03, 1)                  # line colour
ROCK_TONES = [NAVY, srgb(140, 137, 134), srgb(208, 202, 190)]                 # shadow, mid, light
SCREE_TONES = [srgb(48, 52, 68), srgb(170, 160, 140), srgb(222, 212, 188)]    # shadow, sand, pale sand
HAZE = srgb(150, 170, 198)                     # colour distant ridges fade towards

# ===================================================================== elevation and geometry of the view
# Everything in the scene is in metres, Lambert-93, shifted so that the camera's ground point is the
# origin and its ground elevation is z = 0. That keeps coordinates small (float32-safe in Blender).
dem_ds = rasterio.open(f"{D}/dem_2m_dibona.tif"); DEM = dem_ds.read(1); T = dem_ds.transform
d1 = rasterio.open(f"{D}/dem_1m_dibona.tif"); DEM1 = d1.read(1); T1 = d1.transform; B1 = d1.bounds

def _bilinear(A, TT, x, y):
    """Bilinear sample of raster A (affine TT) at Lambert-93 x, y (pixel centres at +0.5)."""
    c = (x - TT.c) / TT.a - 0.5; r = (y - TT.f) / TT.e - 0.5
    return map_coordinates(A, [r, c], order=1, mode="nearest")

def dem_at(x, y):
    """Ground elevation (m) at Lambert-93 x, y: the 1 m LiDAR where it covers, the 2 m LiDAR elsewhere."""
    x = np.asarray(x, float); y = np.asarray(y, float); shape = x.shape; x = x.ravel(); y = y.ravel()
    z = _bilinear(DEM, T, x, y)
    m = (x > B1.left + 2) & (x < B1.right - 2) & (y > B1.bottom + 2) & (y < B1.top - 2)
    z[m] = _bilinear(DEM1, T1, x[m], y[m])
    return z.reshape(shape)

tf = Transformer.from_crs(4326, 2154, always_xy=True)
SX, SY = tf.transform(6.24306, 44.9629)        # Aiguille Dibona summit (BD TOPO detail_orographique)
CX, CY = tf.transform(6.24089, 44.94903)       # camera: floor of the Vallon du Soreiller, 1.55 km south.
                                               # Found by a line-of-sight search: from Les Étages and from
                                               # the refuge the summit is hidden by terrain.
Z0 = float(dem_at(np.array([CX]), np.array([CY]))[0])            # camera ground elevation (~2,230 m)
HEAD = math.degrees(math.atan2(SX - CX, SY - CY))                  # bearing camera -> summit (deg, ~4)
log("camera ground", round(Z0), "m, heading", round(HEAD, 1))

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
terrain_col = bpy.data.collections.new("terrain"); sc.collection.children.link(terrain_col)

# ===================================================================== terrain meshes
def in_wedge(x, y, r0, r1, half, grow=0.0):
    """True for points (relative to the camera) between r0 and r1 m away and within `half` degrees of the
    camera heading. `grow` (m) enlarges (or, negative, shrinks) the wedge on every side."""
    d = np.hypot(x, y); a = np.abs((np.degrees(np.arctan2(x, y)) - HEAD + 180) % 360 - 180)
    return (d >= r0 - grow) & (d < r1 + grow) & (a < half + np.degrees(grow / np.maximum(d, 1)))

def wedge_box(r0, r1, half, step):
    """Bounding box (x0, x1, y0, y1) of a wedge, padded by one grid step."""
    angs = np.radians(np.linspace(HEAD - half, HEAD + half, 40))
    ex = np.r_[r1 * np.sin(angs), r0 * np.sin(angs)]; ey = np.r_[r1 * np.cos(angs), r0 * np.cos(angs)]
    return ex.min() - step, ex.max() + step, ey.min() - step, ey.max() + step

def grid_mesh(name, x0, x1, y0, y1, step, keep, hole=None, drop=0.0, sink=None):
    """Build a terrain mesh from a regular grid over [x0, x1] x [y0, y1] (m, relative to the camera).

    keep(x, y, grow)  which quads to keep, tested at the quad centre.
    hole(x, y, grow)  region owned by a finer mesh: its quads are removed here, and vertices near it are
                      lowered by `drop` m so that where both meshes overlap, the finer one is on top.
    sink=(fn, m)      lower the vertices where fn(x, y) is true by m metres (used to get the coarse
                      square out of the valley camera's sight line).

    Two per-vertex/per-face attributes are stored for the shaders and Line Art:
      n0              the vertex normal of the real relief. The animation flattens the terrain by scaling
                      z, which would flatten the normals too; the shaders read n0 instead, so slope and
                      lighting stay correct while the map is flat.
      freestyle_face  True on the two rings of faces along every mesh border; Line Art ignores these
                      faces so the seams between meshes draw no lines.
    """
    xs = np.arange(x0, x1 + step, step); ys = np.arange(y0, y1 + step, step)
    gx, gy = np.meshgrid(xs, ys)
    z = dem_at(gx + CX, gy + CY) - Z0
    if hole is not None and drop:
        z = np.where(hole(gx, gy, grow=step * 1.5), z - drop, z)
    if sink is not None:
        z = np.where(sink[0](gx, gy), z - sink[1], z)
    ny, nx = gx.shape
    verts = np.c_[gx.ravel(), gy.ravel(), z.ravel()].astype(np.float32)
    ii = np.arange(ny * nx).reshape(ny, nx)
    quads = np.stack([ii[:-1, :-1], ii[:-1, 1:], ii[1:, 1:], ii[1:, :-1]], -1).reshape(-1, 4)
    qx = (gx[:-1, :-1] + step / 2).ravel(); qy = (gy[:-1, :-1] + step / 2).ravel()
    k = keep(qx, qy, 0.0)
    if hole is not None: k &= ~hole(qx, qy, grow=-step)
    quads = quads[k]
    used = np.unique(quads); remap = np.full(len(verts), -1); remap[used] = np.arange(len(used))
    verts = verts[used]; quads = remap[quads]                 # drop unused vertices, renumber
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(verts)); me.vertices.foreach_set("co", verts.ravel())
    me.loops.add(quads.size); me.loops.foreach_set("vertex_index", quads.ravel().astype(np.int32))
    me.polygons.add(len(quads)); me.polygons.foreach_set("loop_start", (np.arange(len(quads)) * 4).astype(np.int32))
    me.update(calc_edges=True)
    # border faces: an edge used by only one quad is on the border; grow that set by two rings
    e = np.sort(np.stack([quads, np.roll(quads, -1, 1)], -1).reshape(-1, 2), 1)
    ek = e[:, 0].astype(np.int64) * (len(verts) + 1) + e[:, 1]
    _, inv, cnt = np.unique(ek, return_inverse=True, return_counts=True)
    border_face = (cnt[inv] == 1).reshape(-1, 4).any(1)
    for _ in range(2):
        vm = np.zeros(len(verts), bool); vm[quads[border_face].ravel()] = True
        border_face = vm[quads].any(1)
    me.attributes.new("freestyle_face", "BOOLEAN", "FACE").data.foreach_set("value", border_face)
    nrm = np.zeros(len(me.vertices) * 3, np.float32); me.vertex_normals.foreach_get("vector", nrm)
    me.attributes.new("n0", "FLOAT_VECTOR", "POINT").data.foreach_set("vector", nrm)
    ob = bpy.data.objects.new(name, me); terrain_col.objects.link(ob)
    log(name, f"{len(quads):,} faces")
    return ob

# fine wedge: 500 m to 2.4 km from the camera, +-8.5 deg (the 135 mm view is +-7.6 deg wide)
fine_keep = lambda x, y, grow=0.0: in_wedge(x, y, 500, 2400, 8.5, grow)
far_keep = lambda x, y, grow=0.0: in_wedge(x, y, 2350, 9000, 10, grow)
near = grid_mesh("terrain", *wedge_box(500, 2400, 8.5, args.step), args.step, fine_keep)
if ANIM:
    # 4 m square around the needle for the top-down opening; it matches the 0.5 m ortho's extent.
    SQ = (SX - CX - 1250, SX - CX + 1250, SY - CY - 1950, SY - CY + 1500)
    sq_keep = lambda x, y, grow=0.0: (x >= SQ[0] - grow) & (x < SQ[1] + grow) & (y >= SQ[2] - grow) & (y < SQ[3] + grow)
    # its ground right in front of the valley camera is sunk 60 m so it never blocks the final view
    square = grid_mesh("terrain_square", *SQ, 4, sq_keep, hole=fine_keep, drop=0.8,
                       sink=(lambda x, y: (np.hypot(x, y) < 520) & in_wedge(x, y, 0, 520, 25), 60.0))
    far = grid_mesh("terrain_far", *wedge_box(2350, 9000, 10, 8), 8, far_keep,
                    hole=lambda x, y, grow=0.0: fine_keep(x, y, grow) | sq_keep(x, y, grow), drop=2.0)
else:
    far = grid_mesh("terrain_far", *wedge_box(2350, 9000, 10, 8), 8, far_keep, hole=fine_keep, drop=2.0)

# ===================================================================== terrain shader (flat colour)
# Node-graph overview (all inside one material, output through an Emission shader so the colours
# are shown exactly as chosen, without being lit a second time):
#
#   Diffuse(normal = n0) -> Shader to RGB -> brightness ---+--> rock tone ramp  --+
#   noise -> +-0.175 jitter --------------------------------+--> scree tone ramp --+-> slope mix -> haze -> Emission
#   n0.z + noise jitter < steep -----------------------------------------------------^
mat = bpy.data.materials.new("toon"); nt = mat.node_tree; N = nt.nodes; L = nt.links
for n in list(N):
    if n.type != "OUTPUT_MATERIAL": N.remove(n)
out = N["Material Output"]

# brightness from Blender's own lighting (sun + cast shadows), using the stored relief normals
dif = N.new("ShaderNodeBsdfDiffuse"); dif.inputs["Color"].default_value = (1, 1, 1, 1)
n0 = N.new("ShaderNodeAttribute"); n0.attribute_name = "n0"; n0.attribute_type = "GEOMETRY"
L.new(n0.outputs["Vector"], dif.inputs["Normal"])
s2r = N.new("ShaderNodeShaderToRGB"); L.new(dif.outputs[0], s2r.inputs[0])   # EEVEE only
bw = N.new("ShaderNodeRGBToBW"); L.new(s2r.outputs[0], bw.inputs[0])

# low-detail noise in object space (~33 m features): jitters the thresholds so band edges are ragged.
# Detail is kept low (2) on purpose: high detail made the edges speckled and soft-looking.
tc = N.new("ShaderNodeTexCoord")
noi = N.new("ShaderNodeTexNoise"); noi.inputs["Scale"].default_value = 0.03
noi.inputs["Detail"].default_value = 2; noi.inputs["Roughness"].default_value = 0.45
L.new(tc.outputs["Object"], noi.inputs["Vector"])
jit = N.new("ShaderNodeMath"); jit.operation = "MULTIPLY_ADD"; L.new(noi.outputs["Fac"], jit.inputs[0])
jit.inputs[1].default_value = 0.35; jit.inputs[2].default_value = -0.175       # noise -> +-0.175
lit = N.new("ShaderNodeMath"); lit.operation = "ADD"                           # jittered brightness
L.new(bw.outputs[0], lit.inputs[0]); L.new(jit.outputs[0], lit.inputs[1])

# slope mask: 1 where the ground is steep enough to be rock (and may go to the rock palette)
sep = N.new("ShaderNodeSeparateXYZ"); L.new(n0.outputs["Vector"], sep.inputs[0])
nz = N.new("ShaderNodeMath"); nz.operation = "ADD"; L.new(sep.outputs["Z"], nz.inputs[0])
jit2 = N.new("ShaderNodeMath"); jit2.operation = "MULTIPLY_ADD"; L.new(noi.outputs["Fac"], jit2.inputs[0])
jit2.inputs[1].default_value = 0.3; jit2.inputs[2].default_value = -0.15         # noise -> +-0.15
L.new(jit2.outputs[0], nz.inputs[1])
steep = N.new("ShaderNodeMath"); steep.operation = "LESS_THAN"; steep.inputs[1].default_value = args.steep
L.new(nz.outputs[0], steep.inputs[0])
mix_ = N.new("ShaderNodeMix"); mix_.data_type = "RGBA"          # gentle (A) vs steep (B) colour
L.new(steep.outputs[0], mix_.inputs[0])

def tone_ramp(cols, stops):
    """CONSTANT colour ramp on the jittered brightness: cols[i] from stops[i-1] up (cols[0] from 0)."""
    rp = N.new("ShaderNodeValToRGB"); cr = rp.color_ramp; cr.interpolation = "CONSTANT"
    cr.elements[0].position = 0; cr.elements[0].color = cols[0]
    cr.elements[1].position = stops[0]; cr.elements[1].color = cols[1]
    for c, st in zip(cols[2:], stops[1:]):
        cr.elements.new(st).color = c
    L.new(lit.outputs[0], rp.inputs[0]); return rp

if STYLE == "rochette":
    rock_r = tone_ramp(ROCK_TONES, [args.dark, 0.42])
    scree_r = tone_ramp(SCREE_TONES, [args.dark * 0.7, 0.4])

    # rock streaks: noise stretched 10x along z (in world space) gives vertical, fall-line marks.
    # Two independent noises (4D, different W): dark streaks on lit rock, pale streaks in shadow.
    gpos = N.new("ShaderNodeNewGeometry")
    stretch = N.new("ShaderNodeVectorMath"); stretch.operation = "MULTIPLY"
    stretch.inputs[1].default_value = (0.12, 0.12, 0.012)
    L.new(gpos.outputs["Position"], stretch.inputs[0])
    def streaks(w, threshold):
        sn = N.new("ShaderNodeTexNoise"); sn.inputs["Scale"].default_value = 1.0; sn.inputs["Detail"].default_value = 1.5
        sn.noise_dimensions = "4D"; sn.inputs["W"].default_value = w
        L.new(stretch.outputs[0], sn.inputs["Vector"])
        st = N.new("ShaderNodeMath"); st.operation = "GREATER_THAN"; st.inputs[1].default_value = threshold
        L.new(sn.outputs["Fac"], st.inputs[0]); return st.outputs[0]
    dark_s = streaks(0.0, 0.62); pale_s = streaks(7.3, 0.65)
    is_lit = N.new("ShaderNodeMath"); is_lit.operation = "GREATER_THAN"; is_lit.inputs[1].default_value = args.dark
    L.new(lit.outputs[0], is_lit.inputs[0])
    d_on = N.new("ShaderNodeMath"); d_on.operation = "MULTIPLY"; L.new(dark_s, d_on.inputs[0]); L.new(is_lit.outputs[0], d_on.inputs[1])
    in_shadow = N.new("ShaderNodeMath"); in_shadow.operation = "SUBTRACT"; in_shadow.inputs[0].default_value = 1
    L.new(is_lit.outputs[0], in_shadow.inputs[1])
    p_on = N.new("ShaderNodeMath"); p_on.operation = "MULTIPLY"; L.new(pale_s, p_on.inputs[0]); L.new(in_shadow.outputs[0], p_on.inputs[1])
    rk1 = N.new("ShaderNodeMix"); rk1.data_type = "RGBA"; L.new(d_on.outputs[0], rk1.inputs[0])
    L.new(rock_r.outputs[0], rk1.inputs[6]); rk1.inputs[7].default_value = NAVY
    rk2 = N.new("ShaderNodeMix"); rk2.data_type = "RGBA"; L.new(p_on.outputs[0], rk2.inputs[0])
    L.new(rk1.outputs[2], rk2.inputs[6]); rk2.inputs[7].default_value = srgb(150, 150, 158)
    L.new(scree_r.outputs[0], mix_.inputs[6]); L.new(rk2.outputs[2], mix_.inputs[7])

    # aerial perspective: beyond 2.3 km fade up to 60 % towards HAZE by distance from the valley camera
    # (measured from the fixed camera position, not the animated camera, so the fade does not crawl)
    camd = N.new("ShaderNodeVectorMath"); camd.operation = "DISTANCE"; camd.inputs[1].default_value = (0, 0, 1.7)
    L.new(gpos.outputs["Position"], camd.inputs[0])
    fd = N.new("ShaderNodeMapRange"); fd.inputs["From Min"].default_value = 2300; fd.inputs["From Max"].default_value = 9000
    fd.inputs["To Max"].default_value = 0.6; L.new(camd.outputs["Value"], fd.inputs[0])
    hz = N.new("ShaderNodeMix"); hz.data_type = "RGBA"; L.new(fd.outputs[0], hz.inputs[0])
    L.new(mix_.outputs[2], hz.inputs[6]); hz.inputs[7].default_value = HAZE
    FINAL = hz.outputs[2]
else:
    # STYLE=ink: black on steep shadowed rock, paper everywhere else
    ramp = tone_ramp([(0, 0, 0, 1), (1, 1, 1, 1)], [args.dark])
    mix_.inputs[6].default_value = PAPER
    mul = N.new("ShaderNodeMix"); mul.data_type = "RGBA"; mul.blend_type = "MULTIPLY"; mul.inputs[0].default_value = 1
    L.new(ramp.outputs[0], mul.inputs[6]); mul.inputs[7].default_value = PAPER
    L.new(mul.outputs[2], mix_.inputs[7])
    FINAL = mix_.outputs[2]

# 03_animation.py finds this Emission node and inserts the photo cross-fade and contours before it
emi = N.new("ShaderNodeEmission"); L.new(FINAL, emi.inputs["Color"])
L.new(emi.outputs[0], out.inputs["Surface"])
for ob in terrain_col.objects:
    ob.data.materials.append(mat)

# ===================================================================== sun, sky, camera
# Sun: a point source (angle 0) so cast shadows have hard edges and the bands stay crisp.
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); sc.collection.objects.link(sun)
sun.data.energy = 1.0; sun.data.angle = 0.0
sun.rotation_euler = Euler((math.radians(90 - args.sun_el), 0, math.radians(180 - args.sun_az)), "XYZ")

# World: the camera sees the sky colour, but the world does not light the terrain (only the sun does),
# otherwise the ambient light would lift the shadows out of the navy band.
w = bpy.data.worlds.new("sky"); sc.world = w
wn = w.node_tree.nodes; wl = w.node_tree.links
bg = wn["Background"]; bg.inputs["Color"].default_value = PAPER; bg.inputs["Strength"].default_value = 1.0
dark = wn.new("ShaderNodeBackground"); dark.inputs["Strength"].default_value = 0.0
lp = wn.new("ShaderNodeLightPath"); ms = wn.new("ShaderNodeMixShader")
wl.new(lp.outputs["Is Camera Ray"], ms.inputs[0]); wl.new(dark.outputs[0], ms.inputs[1]); wl.new(bg.outputs[0], ms.inputs[2])
wl.new(ms.outputs[0], wn["World Output"].inputs["Surface"])
if STYLE == "rochette":
    # screen-space vertical gradient (Window coordinates) with a faint 6 % noise so it is not a perfect ramp
    wtc = wn.new("ShaderNodeTexCoord"); wsep = wn.new("ShaderNodeSeparateXYZ"); wl.new(wtc.outputs["Window"], wsep.inputs[0])
    wno = wn.new("ShaderNodeTexNoise"); wno.inputs["Scale"].default_value = 6; wno.inputs["Detail"].default_value = 4
    wl.new(wtc.outputs["Window"], wno.inputs["Vector"])
    wadd = wn.new("ShaderNodeMath"); wadd.operation = "MULTIPLY_ADD"; wl.new(wno.outputs["Fac"], wadd.inputs[0])
    wadd.inputs[1].default_value = 0.06; wl.new(wsep.outputs["Y"], wadd.inputs[2])
    wr = wn.new("ShaderNodeValToRGB"); cr = wr.color_ramp
    cr.elements[0].position = 0.45; cr.elements[0].color = srgb(110, 180, 236)   # cerulean at the horizon
    cr.elements[1].position = 1.0; cr.elements[1].color = srgb(16, 52, 160)      # ultramarine at the top
    cr.elements.new(0.75).color = srgb(36, 98, 200)
    wl.new(wadd.outputs[0], wr.inputs[0]); wl.new(wr.outputs[0], bg.inputs["Color"])

# Camera: eye height on the valley floor, aimed 120 m below the summit so the needle sits low in the
# frame and leaves sky above it for the title.
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.lens = args.lens; cam.data.sensor_fit = "AUTO"; cam.data.sensor_width = 36
cam.data.clip_start = 5; cam.data.clip_end = 20000
sz = float(dem_at(np.array([SX]), np.array([SY]))[0]) - Z0
dist = math.hypot(SX - CX, SY - CY)
pitch = math.degrees(math.atan2(sz - 1.7 - 120, dist))
cam.location = (0, 0, 1.7)
cam.rotation_euler = Euler((math.radians(90 + pitch), 0, math.radians(-HEAD)), "XYZ")
log("pitch", round(pitch, 1), "deg, summit", round(sz), "m above the camera")

# ===================================================================== ink (Grease Pencil Line Art)
def ink_object(name, color, radius, shadow_region=None, crease_deg=95, noise_seed=5):
    """One Grease Pencil object whose Line Art modifier traces the terrain, plus the hand-drawn modifiers.

    shadow_region: "ILLUMINATED" or "SHADED" keeps only the lines in the sun-lit or shadowed part
    (Line Art computes the shadow from the sun object itself).
    """
    gd = bpy.data.grease_pencils.new(name); go = bpy.data.objects.new(name, gd); sc.collection.objects.link(go)
    gd.layers.new(name).frames.new(1)
    mt = bpy.data.materials.new(name); bpy.data.materials.create_gpencil_data(mt)
    mt.grease_pencil.color = color; mt.grease_pencil.show_fill = False; gd.materials.append(mt)
    la = go.modifiers.new(name, "LINEART")
    la.source_type = "COLLECTION"; la.source_collection = terrain_col
    la.target_layer = name; la.target_material = mt
    la.use_contour = True                       # silhouettes against the sky and against farther terrain
    la.use_crease = True                        # kept on, but returns nothing in Blender 5.3 (see header)
    la.crease_threshold = math.radians(crease_deg)
    la.use_loose = False; la.use_material = False; la.use_edge_mark = False; la.use_intersection = False
    if shadow_region:
        la.use_shadow = True; la.light_contour_object = sun; la.shadow_region_filtering = shadow_region
    la.chaining_image_threshold = 0.006         # join line pieces closer than this (fraction of the image)
    la.smooth_tolerance = 0.3
    la.radius = radius                          # base stroke radius
    la.use_face_mark = True; la.use_face_mark_invert = True   # skip faces tagged freestyle_face (mesh seams)
    la.use_face_mark_keep_contour = False
    # hand-drawn look, applied in this order:
    nm = go.modifiers.new("noise", "GREASE_PENCIL_NOISE")          # wobble in position and thickness
    nm.factor = 1.6; nm.factor_thickness = 0.6; nm.noise_scale = 0.35; nm.seed = noise_seed
    sm = go.modifiers.new("smooth", "GREASE_PENCIL_SMOOTH")         # take the jitter out of the wobble
    sm.factor = 0.6; sm.step = 2
    th = go.modifiers.new("thick", "GREASE_PENCIL_THICKNESS")       # taper: thin ends, fat early middle
    th.use_custom_curve = True; pts = th.custom_curve.curves[0].points
    pts[0].location = (0, 0.1); pts[1].location = (1, 0.1); pts.new(0.3, 1.0); pts.new(0.65, 0.75)
    th.custom_curve.update()
    ln = go.modifiers.new("length", "GREASE_PENCIL_LENGTH")         # strokes overshoot a little, like ink
    ln.start_factor = 0.05; ln.end_factor = 0.08
    si = go.modifiers.new("simplify", "GREASE_PENCIL_SIMPLIFY"); si.factor = 0.0004
    return go

if not args.noink:
    if STYLE == "rochette":
        ink_object("rock_lit", INK, 1.7, "ILLUMINATED")                     # bold black on lit rock
        ink_object("rock_shade", srgb(196, 196, 200), 1.0, "SHADED")        # pale scratches in shadow
    else:
        ink_object("lines", INK, 0.9, None, crease_deg=args.crease, noise_seed=3)
    log("line art set up")

# ===================================================================== render (still)
# 03_animation.py executes everything above this line and replaces this section with its own.
r = sc.render; r.engine = "BLENDER_EEVEE"
r.resolution_x = args.res; r.resolution_y = int(args.res * 5 / 4); r.resolution_percentage = 100
sc.eevee.taa_render_samples = 16
# sharp shadow maps (no filtering, no jitter): keeps the shadow bands crisp
for k, v in (("shadow_resolution_scale", 1.0), ("shadow_ray_count", 1), ("shadow_step_count", 16)):
    if hasattr(sc.eevee, k): setattr(sc.eevee, k, v)
for k, v in (("shadow_maximum_resolution", 0.001), ("use_shadow_jitter", False), ("shadow_filter_radius", 0.0)):
    if hasattr(sun.data, k): setattr(sun.data, k, v)
sc.view_settings.view_transform = "Standard"; sc.view_settings.look = "None"   # colours exactly as chosen
r.image_settings.file_format = "PNG"; r.filepath = args.out
if args.save: bpy.ops.wm.save_as_mainfile(filepath=args.save)
log("rendering")
bpy.ops.render.render(write_still=True)
log("done", args.out)
