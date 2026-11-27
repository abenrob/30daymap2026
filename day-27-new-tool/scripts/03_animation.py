"""Aiguille Dibona fly-in, 12 s at 24 fps (288 frames, 1080 x 1350).

Storyboard (frame numbers)
--------------------------
  1-62     Straight down on the IGN orthophoto with 40 m elevation contours, the summit ring and the
           label "AIGUILLE DIBONA / ALTITUDE 3 131". The camera sinks from 2,900 m to 1,900 m above the
           valley camera; the label fades out over 40-62 and the contours under it fade back in.
  62-112   Still flat and seen from above, the photo cross-fades into the flat-colour drawing (so the
           photo is never seen stretched over steep faces).
  70-140   The relief rises out of the flat map (terrain z-scale 0.002 -> 1).
  100-145  The ink lines switch on and fade in.
  140-240  The camera tilts and swings down to the valley view (02_still.py's camera, 135 mm lens).
  165-200  The contours fade out.
  244-264  The title fades in across the sky; 264-288 hold.

How it is built
---------------
02_still.py builds the scene (terrain, flat-colour shader, ink, sun, sky, final camera); this script runs
it with ANIM=1 (which adds the 4 m square of terrain for the top-down shot) and then adds:
  - the orthophoto and the contours inside the terrain shader, both animated;
  - the terrain's z-scale animation;
  - the map label (3D text lying on the terrain) and the end title (3D text parented to the camera);
  - the camera path and the ink fade.
Animated values inside shaders are Value nodes with keyframes. Each fading material gets its own
Value node: an earlier version copied one material, the copies shared one animation, and the end title
showed up during the opening.

usage: python3 03_animation.py -- [--res 432] [--samples 16] [--step_frames 2] [--frames a-b]
                             [--outdir renders/anim] [--blend out.blend] [--norender]
  --blend   saves a packed .blend (data, ortho and font embedded) set up to render all 288 frames
            to //frames/ next to it:  blender -b dibona_anim.blend -a
extra input: ortho_0.5m_dibona.tif (IGN ortho, 0.5 m, 6.2265-6.2595 E 44.945-44.977 N) and
             Antonio-Bold.ttf (Antonio variable font instanced at weight 700, SIL OFL) in DIBONA_DATA.
"""
import math, os, sys

# ===================================================================== options
os.environ["ANIM"] = "1"
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def opt(name, default):
    return argv[argv.index(name) + 1] if name in argv else default
RES = int(opt("--res", 432)); STEP = int(opt("--step_frames", 2)); BLEND = opt("--blend", "")
OUTDIR = opt("--outdir", "renders/anim"); FR = opt("--frames", ""); NORENDER = "--norender" in argv

# ===================================================================== build the still scene from 02_still.py
# Run 02_still.py up to (not including) its render section, in this namespace, so its variables
# (sc, mat, cam, dem_at, CX, CY, Z0, HEAD, terrain_col, srgb, NAVY, D, log, ...) are available here.
HERE = os.path.dirname(os.path.abspath(__file__))
sys.argv = ["02_still.py", "--", "--res", str(RES)]
src = open(os.path.join(HERE, "02_still.py")).read().split("# ===================================================================== render (still)")[0]
exec(compile(src, "02_still.py", "exec"))

import bpy, numpy as np, rasterio
from mathutils import Vector, Euler, Matrix

FPS = 24; F_END = 288
sc.render.fps = FPS; sc.frame_start = 1; sc.frame_end = F_END
SXr, SYr = SX - CX, SY - CY                                         # summit, relative to the camera ground point
SZr = float(dem_at(np.array([SX]), np.array([SY]))[0]) - Z0

def key_value(socket, frames_values):
    """Keyframe a node socket's default_value at [(frame, value), ...]."""
    for f, v in frames_values:
        socket.default_value = v; socket.keyframe_insert("default_value", frame=f)

# ===================================================================== orthophoto <-> drawing, inside the terrain shader
nt = mat.node_tree; N = nt.nodes; L = nt.links
emi_node = [n for n in N if n.type == "EMISSION"][0]
toon_link = emi_node.inputs["Color"].links[0]; toon_src = toon_link.from_socket; L.remove(toon_link)

# the ortho is mapped by object x, y (metres relative to the camera) -> 0..1 over the ortho's extent
ds = rasterio.open(f"{D}/ortho_0.5m_dibona.tif"); W = ds.width * ds.res[0]; H = ds.height * ds.res[1]
tcx = N.new("ShaderNodeTexCoord"); mp = N.new("ShaderNodeMapping")
mp.inputs["Scale"].default_value = (1 / W, 1 / H, 1)
mp.inputs["Location"].default_value = ((CX - ds.bounds.left) / W, (CY - ds.bounds.bottom) / H, 0)
L.new(tcx.outputs["Object"], mp.inputs[0])
otex = N.new("ShaderNodeTexImage"); otex.image = bpy.data.images.load(f"{D}/ortho_0.5m_dibona.tif"); otex.extension = "EXTEND"
L.new(mp.outputs[0], otex.inputs[0])
photo = N.new("ShaderNodeValue"); photo.label = "photo"             # 1 = photo, 0 = drawing
key_value(photo.outputs[0], [(1, 1.0), (62, 1.0), (112, 0.0)])
xf = N.new("ShaderNodeMix"); xf.data_type = "RGBA"
L.new(photo.outputs[0], xf.inputs[0]); L.new(toon_src, xf.inputs[6]); L.new(otex.outputs["Color"], xf.inputs[7])

# ===================================================================== elevation contours, also inside the terrain shader
# Painting the contours on the surface (rather than as Grease Pencil strokes) means they are hidden by
# ridges in front of them like any other surface detail. Grease Pencil strokes drew through the ridges
# once the relief stood up.
def contour_mask(interval, half_width):
    """1 on lines of constant elevation every `interval` m, about `half_width` m wide on the ground.

    Object z is elevation - Z0 and stays so while the mesh is scaled flat, because the Object texture
    coordinate is taken before the object transform. Distance to the nearest contour in metres of height
    is PINGPONG(elevation, interval/2); dividing it by the slope (tan, from the stored normal n0) turns it
    into a horizontal distance, so lines keep a constant width on steep and gentle ground alike.
    """
    sepo = N.new("ShaderNodeSeparateXYZ"); L.new(tcx.outputs["Object"], sepo.inputs[0])
    e = N.new("ShaderNodeMath"); e.operation = "ADD"; L.new(sepo.outputs["Z"], e.inputs[0]); e.inputs[1].default_value = Z0
    dv = N.new("ShaderNodeMath"); dv.operation = "PINGPONG"; L.new(e.outputs[0], dv.inputs[0]); dv.inputs[1].default_value = interval / 2
    nn = [n for n in N if n.type == "ATTRIBUTE" and n.attribute_name == "n0"][0]
    sz_ = N.new("ShaderNodeSeparateXYZ"); L.new(nn.outputs["Vector"], sz_.inputs[0])
    nz2 = N.new("ShaderNodeMath"); nz2.operation = "MULTIPLY"; L.new(sz_.outputs["Z"], nz2.inputs[0]); L.new(sz_.outputs["Z"], nz2.inputs[1])
    s2 = N.new("ShaderNodeMath"); s2.operation = "SUBTRACT"; s2.inputs[0].default_value = 1.0; L.new(nz2.outputs[0], s2.inputs[1])
    sn_ = N.new("ShaderNodeMath"); sn_.operation = "SQRT"; L.new(s2.outputs[0], sn_.inputs[0])            # sin(slope)
    tn = N.new("ShaderNodeMath"); tn.operation = "DIVIDE"; L.new(sn_.outputs[0], tn.inputs[0]); L.new(sz_.outputs["Z"], tn.inputs[1])  # tan
    tmin = N.new("ShaderNodeMath"); tmin.operation = "MAXIMUM"; L.new(tn.outputs[0], tmin.inputs[0]); tmin.inputs[1].default_value = 0.02
    hd = N.new("ShaderNodeMath"); hd.operation = "DIVIDE"; L.new(dv.outputs[0], hd.inputs[0]); L.new(tmin.outputs[0], hd.inputs[1])
    ln = N.new("ShaderNodeMath"); ln.operation = "LESS_THAN"; L.new(hd.outputs[0], ln.inputs[0]); ln.inputs[1].default_value = half_width
    return ln.outputs[0]
c_minor = contour_mask(40, 1.6)                    # every 40 m, thin
c_index = contour_mask(200, 3.4)                   # every 200 m, heavier (index contours)
c_any = N.new("ShaderNodeMath"); c_any.operation = "MAXIMUM"; L.new(c_minor, c_any.inputs[0]); L.new(c_index, c_any.inputs[1])

# keep the contours out of the label's rectangle while the label is shown. The rectangle is in the
# label's frame: centred on the summit, rotated with the camera heading, 1,440 m wide, from 150 m to
# 470 m south of the summit.
mpl = N.new("ShaderNodeMapping"); mpl.vector_type = "POINT"; mpl.inputs["Location"].default_value = (-SXr, -SYr, 0)
L.new(tcx.outputs["Object"], mpl.inputs[0])
rot = N.new("ShaderNodeVectorRotate"); rot.rotation_type = "Z_AXIS"; rot.inputs["Angle"].default_value = math.radians(HEAD)
L.new(mpl.outputs[0], rot.inputs["Vector"])
sl = N.new("ShaderNodeSeparateXYZ"); L.new(rot.outputs[0], sl.inputs[0])
ua = N.new("ShaderNodeMath"); ua.operation = "ABSOLUTE"; L.new(sl.outputs["X"], ua.inputs[0])
inu = N.new("ShaderNodeMath"); inu.operation = "LESS_THAN"; L.new(ua.outputs[0], inu.inputs[0]); inu.inputs[1].default_value = 720
v1 = N.new("ShaderNodeMath"); v1.operation = "LESS_THAN"; L.new(sl.outputs["Y"], v1.inputs[0]); v1.inputs[1].default_value = -150
v2 = N.new("ShaderNodeMath"); v2.operation = "GREATER_THAN"; L.new(sl.outputs["Y"], v2.inputs[0]); v2.inputs[1].default_value = -470
blk = N.new("ShaderNodeMath"); blk.operation = "MULTIPLY"; L.new(inu.outputs[0], blk.inputs[0]); L.new(v1.outputs[0], blk.inputs[1])
blk2 = N.new("ShaderNodeMath"); blk2.operation = "MULTIPLY"; L.new(blk.outputs[0], blk2.inputs[0]); L.new(v2.outputs[0], blk2.inputs[1])
LABEL_FADE = [(1, 1.0), (40, 1.0), (62, 0.0)]          # label on, then fading out over frames 40-62
lbl_on = N.new("ShaderNodeValue"); key_value(lbl_on.outputs[0], LABEL_FADE)
cut = N.new("ShaderNodeMath"); cut.operation = "MULTIPLY"; L.new(blk2.outputs[0], cut.inputs[0]); L.new(lbl_on.outputs[0], cut.inputs[1])
keep_ = N.new("ShaderNodeMath"); keep_.operation = "SUBTRACT"; keep_.inputs[0].default_value = 1; L.new(cut.outputs[0], keep_.inputs[1])
c_vis = N.new("ShaderNodeValue"); key_value(c_vis.outputs[0], [(1, 1.0), (165, 1.0), (200, 0.0)])   # contours fade out as the camera tilts
cm1 = N.new("ShaderNodeMath"); cm1.operation = "MULTIPLY"; L.new(c_any.outputs[0], cm1.inputs[0]); L.new(keep_.outputs[0], cm1.inputs[1])
cm2 = N.new("ShaderNodeMath"); cm2.operation = "MULTIPLY"; L.new(cm1.outputs[0], cm2.inputs[0]); L.new(c_vis.outputs[0], cm2.inputs[1])
ctr = N.new("ShaderNodeMix"); ctr.data_type = "RGBA"; L.new(cm2.outputs[0], ctr.inputs[0])
L.new(xf.outputs[2], ctr.inputs[6]); ctr.inputs[7].default_value = NAVY
L.new(ctr.outputs[2], emi_node.inputs["Color"])   # photo/drawing + contours -> Emission

# ===================================================================== terrain rises out of the flat map
for ob in terrain_col.objects:
    for f, z in ((1, 0.002), (70, 0.002), (140, 1.0)):
        ob.scale = (1, 1, z); ob.keyframe_insert("scale", index=2, frame=f)

# ===================================================================== map label and summit ring (frames 1-62)
FONT = bpy.data.fonts.load(f"{D}/Antonio-Bold.ttf", check_existing=True)

def fade_material(name, color, keys):
    """Unlit (emission) material whose opacity follows keys [(frame, 0..1)]; dithered transparency."""
    m = bpy.data.materials.new(name); m.surface_render_method = "DITHERED"
    t = m.node_tree; n = t.nodes; l = t.links
    for x in list(n):
        if x.type != "OUTPUT_MATERIAL": n.remove(x)
    e = n.new("ShaderNodeEmission"); e.inputs["Color"].default_value = color
    tr = n.new("ShaderNodeBsdfTransparent"); mx = n.new("ShaderNodeMixShader")
    v = n.new("ShaderNodeValue"); key_value(v.outputs[0], keys)
    l.new(v.outputs[0], mx.inputs[0]); l.new(tr.outputs[0], mx.inputs[1]); l.new(e.outputs[0], mx.inputs[2])
    l.new(mx.outputs[0], n["Material Output"].inputs["Surface"])
    return m

def map_label(text, size, offset_y):
    """3D text lying flat 15 m above the ground, `offset_y` m south of the summit in the camera's frame."""
    cu = bpy.data.curves.new(text, "FONT"); cu.body = text; cu.size = size
    cu.align_x = "CENTER"; cu.align_y = "CENTER"; cu.font = FONT; cu.space_character = 0.95   # tracking -5 %
    ob = bpy.data.objects.new(text, cu); sc.collection.objects.link(ob)
    yaw = math.radians(-HEAD)
    off = Matrix.Rotation(yaw, 3, "Z") @ Vector((0, offset_y, 0))
    ob.location = (SXr + off.x, SYr + off.y, 15); ob.rotation_euler = (0, 0, yaw)
    return ob

label_mat = fade_material("label", (1, 1, 1, 1), LABEL_FADE)
label_shadow_mat = fade_material("label_shadow", (0.02, 0.02, 0.03, 1), LABEL_FADE)
for ob in (map_label("AIGUILLE DIBONA", 190, -270), map_label("ALTITUDE 3 131", 68, -400)):
    ob.data.materials.append(label_mat)
    # drop shadow: a dark copy offset down-right by 4 % of the text size, 1 m lower
    sh = ob.copy(); sh.data = ob.data.copy(); sh.data.materials[0] = label_shadow_mat
    o_ = ob.data.size * 0.04; sh.location = (ob.location.x + o_, ob.location.y - o_, 14); sc.collection.objects.link(sh)
bpy.ops.mesh.primitive_torus_add(major_radius=38, minor_radius=6, location=(SXr, SYr, 16))   # summit ring
bpy.context.active_object.data.materials.append(label_mat)

# ===================================================================== camera path
cam_final_loc = Vector(cam.location); cam_final_rot = Euler(cam.rotation_euler)   # set by 02_still.py
yaw = math.radians(-HEAD)                       # top-down shots: screen "up" points up the valley (north)
def look(loc, target):
    return (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler("XYZ")
CAMERA_KEYS = [   # (frame, location m, rotation or None = look at the needle, lens mm)
    (1,   (SXr, SYr - 150, 2900), Euler((0, 0, yaw)), 40),                   # straight down, high
    (62,  (SXr, SYr - 150, 1900), Euler((0, 0, yaw)), 40),                   # straight down, closer
    (140, (SXr, SYr - 260, 1750), Euler((math.radians(10), 0, yaw)), 40),   # starts to tilt as the relief is up
    (190, (SXr * 0.5, SYr - 1000, SZr + 350), None, 70),                     # swinging down, looking at the needle
    (240, tuple(cam_final_loc), cam_final_rot, args.lens),                   # the valley view (135 mm)
]
prev = None
for f, loc, rot, lens in CAMERA_KEYS:
    if rot is None: rot = look(loc, (SXr, SYr, SZr - 120))
    if prev is not None: rot.make_compatible(prev)  # avoid 360-degree flips between keys
    prev = rot
    cam.location = loc; cam.rotation_euler = rot; cam.data.lens = lens
    cam.keyframe_insert("location", frame=f); cam.keyframe_insert("rotation_euler", frame=f)
    cam.data.keyframe_insert("lens", frame=f)
cam.data.clip_start = 2

# ===================================================================== ink fades in once the relief is up
for name in ("rock_lit", "rock_shade"):
    go = bpy.data.objects[name]
    for m in go.modifiers:                          # off before frame 100 (also saves render time)
        for f, on in ((1, False), (99, False), (100, True)):
            m.show_render = on; m.show_viewport = on
            m.keyframe_insert("show_render", frame=f); m.keyframe_insert("show_viewport", frame=f)
    lay = go.data.layers[0]
    for f, o in ((1, 0.0), (100, 0.0), (145, 1.0)):
        lay.opacity = o; lay.keyframe_insert("opacity", frame=f)

# ===================================================================== end title in the sky (frames 244-288)
# Text parented to the camera, 10 m in front of it. With the 135 mm lens the frame there is about
# 2.13 m wide and 2.67 m tall, so y = 1.02 is near the top of the frame.
title_mat = fade_material("title", (1, 1, 1, 1), [(1, 0.0), (244, 0.0), (264, 1.0)])
def cam_text(body, size, y):
    cu = bpy.data.curves.new(body, "FONT"); cu.body = body; cu.font = FONT; cu.size = size
    cu.align_x = "CENTER"; cu.align_y = "CENTER"; cu.space_character = 0.95
    ob = bpy.data.objects.new(body, cu); sc.collection.objects.link(ob)
    ob.parent = cam; ob.location = (0, y, -10); ob.data.materials.append(title_mat)
    return ob
cam_text("AIGUILLE DIBONA", 0.48, 1.02)
cam_text("ALTITUDE 3 131", 0.17, 0.77)

# smooth ease-in/out on every object keyframe
for ob in bpy.data.objects:
    ad = ob.animation_data
    if ad and ad.action:
        for fc in getattr(ad.action, "fcurves", []):
            for kp in fc.keyframe_points: kp.interpolation = "BEZIER"; kp.easing = "AUTO"

# ===================================================================== output
r = sc.render; r.engine = "BLENDER_EEVEE"
r.resolution_x = RES; r.resolution_y = int(RES * 5 / 4); r.resolution_percentage = 100
sc.eevee.taa_render_samples = int(opt("--samples", 16))
sc.view_settings.view_transform = "Standard"; sc.view_settings.look = "None"
sc.frame_step = STEP
os.makedirs(OUTDIR, exist_ok=True)
r.image_settings.file_format = "PNG"; r.filepath = OUTDIR + "/f####"
if FR:
    a, b = map(int, FR.split("-")); sc.frame_start, sc.frame_end = a, b
if BLEND:
    # the saved file renders every frame to a frames/ folder next to itself, with everything packed in
    r.filepath = "//frames/f####"; sc.frame_step = 1
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=BLEND, compress=True)
    log("saved", BLEND)
    r.filepath = OUTDIR + "/f####"; sc.frame_step = STEP
if not NORENDER:
    sc.frame_set(sc.frame_start); bpy.ops.render.render()   # warm-up render: compiles the shaders once
    log("rendering frames", sc.frame_start, "-", sc.frame_end, "step", STEP)
    bpy.ops.render.render(animation=True)
    log("done")
