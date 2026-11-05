"""What a walker on the GR 7 can see, frame by frame: a point light at eye height lights every
patch of ground with a clear line of sight. The lit shape IS the viewshed, ray traced and drawn
in the same pass.

Run from the workspace root:
  blender -b -P site/day-05-senses-sight/scripts/11_walk_blender.py -- [options]
    --preview          540 x 675, 8 samples
    --frames A B       render frames A..B only (default all)
    --stride N         every Nth frame (quick previews)
    --still F          render frame F only, to renders/walk_still_F.png (camera tuning)
    --view NAME        camera: south (default), southeast, top
    --flat             no Earth curvature
    --step 2           use every other DEM post (50 m): a quarter of the memory, for previews
    --check F [F ...]  instead of the animation: top-down orthographic binary masks at those
                       frames, pixel = DEM cell, for 13_check.py to compare with gdal_viewshed
Output: work/data/day-05-sight/renders/walk[_preview]/####.png, blender/walk/day-05-walk.blend

Scene (1 unit = 1 m, origin = centre of the crop):
  terrain   25 m DEM as triangles (split exactly as 10_trail.py assumes), flat shaded
  curvature Geometry Nodes lower every vertex by cc x d^2 / 2R, d = distance to the walker,
            R = 6,371 km, cc = 0.85714 (GDAL's default: curvature with 1/7 refraction).
            The terrain bends away from the walker every frame, as it does for GDAL's observer.
  walker    one point light, radius 0, constant falloff, 1.7 m above the rendered surface
  shading   Toon BSDF (size 1, smooth 0): any light reaching the ground gives the same
            brightness, so lit = visible, with no cosine fade at grazing angles.
            Plus a dim emission from a baked hillshade so the relief reads at night.
"""
import bpy, json, math, os, sys
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def arg(name, n=1, cast=int):
    if name not in argv:
        return None
    i = argv.index(name)
    vals = [cast(v) for v in argv[i + 1:i + 1 + n]] if n else []
    return vals if n != 1 else vals[0]
PREVIEW = "--preview" in argv
FLAT = "--flat" in argv
STILL = arg("--still")
FRANGE = arg("--frames", 2)
CHECK = None
if "--check" in argv:
    CHECK = []
    for v in argv[argv.index("--check") + 1:]:
        if not v.isdigit():
            break
        CHECK.append(int(v))
VIEW = argv[argv.index("--view") + 1] if "--view" in argv else "south"
CC, R_EARTH = 0.85714, 6_371_000.0

D = "work/data/day-05-sight"
B = f"{D}/blender/walk"
meta = json.load(open(f"{B}/meta.json"))
trail = json.load(open(f"{B}/trail.json"))
STEP = arg("--step") or 1           # 2 = every other DEM post (50 m), for small machines
z = np.load(f"{B}/dem.npy")[::STEP, ::STEP]
H, W = z.shape
RES = meta["res"] * STEP
ox, oy = meta["origin"]
x0 = meta["xmin"] - ox + meta["res"] / 2 - RES / 2    # keeps vertices on original post centres
y0 = meta["ymax"] - oy - meta["res"] / 2 + RES / 2

def ground(x, y):
    """Height of the rendered triangle under scene (x, y), same split as the mesh below."""
    cf, rf = (x - x0) / RES - 0.5, (y0 - y) / RES - 0.5
    j, i = int(np.floor(cf)), int(np.floor(rf))
    u, v = cf - j, rf - i
    za, zb, zc, zd = z[i, j], z[i, j + 1], z[i + 1, j + 1], z[i + 1, j]
    if u >= v:
        return float(za + u * (zb - za) + v * (zc - zb))
    return float(za + v * (zd - za) + u * (zc - zd))
for fr in trail:                     # eye 1.7 m above the surface actually rendered
    fr["ground"] = ground(fr["x"], fr["y"])
    fr["eye"] = fr["ground"] + meta["eye_m"]

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

def nodes_on(idblock):
    try:
        idblock.use_nodes = True        # always on (and deprecated) from Blender 5
    except AttributeError:
        pass
    return idblock.node_tree

# --- terrain: triangles a-b-c and a-c-d per quad (a top-left, c bottom-right) ------------------
cols = x0 + (np.arange(W) + 0.5) * RES
rows = y0 - (np.arange(H) + 0.5) * RES
X, Y = np.meshgrid(cols, rows)
co = np.stack([X, Y, z], axis=-1).astype("float32").ravel()
idx = np.arange(H * W, dtype=np.int32).reshape(H, W)
a, b = idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel()
c, d = idx[1:, 1:].ravel(), idx[1:, :-1].ravel()
loops = np.concatenate([np.stack([a, c, b], 1), np.stack([a, d, c], 1)]).ravel()   # CCW from above
nt_ = loops.size // 3
mesh = bpy.data.meshes.new("dem")
mesh.vertices.add(H * W)
mesh.vertices.foreach_set("co", co)
mesh.loops.add(loops.size)
mesh.loops.foreach_set("vertex_index", loops)
mesh.polygons.add(nt_)
mesh.polygons.foreach_set("loop_start", np.arange(0, loops.size, 3, dtype=np.int32))
mesh.update(calc_edges=True)
del co, loops, a, b, c, d, X, Y
terrain = bpy.data.objects.new("terrain", mesh)
scene.collection.objects.link(terrain)
print(f"terrain {W} x {H}: {len(mesh.polygons):,} triangles")

# --- walker: a point light keyed to the trail, one position per frame -------------------------
ld = bpy.data.lights.new("eye", "POINT")
ld.shadow_soft_size = 0.0
ld.color = (1.0, 0.72, 0.38)
lt = nodes_on(ld)
fo = lt.nodes.new("ShaderNodeLightFalloff")
fo.inputs["Strength"].default_value = 1e6 if CHECK else 3.0
lt.links.new(fo.outputs["Constant"], lt.nodes["Emission"].inputs["Strength"])
walker = bpy.data.objects.new("walker", ld)
scene.collection.objects.link(walker)
for fr in trail:
    walker.location = (fr["x"], fr["y"], fr["eye"])
    walker.keyframe_insert("location", frame=fr["f"] + 1)
for fc in walker.animation_data.action.fcurves:
    for kp in fc.keyframe_points:
        kp.interpolation = "LINEAR"

# --- curvature: Geometry Nodes, drop = cc * d^2 / 2R from the walker ------------------------
def curvature_group():
    ng = bpy.data.node_groups.new("earth_curvature", "GeometryNodeTree")
    ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    n, L = ng.nodes, ng.links
    gi, go = n.new("NodeGroupInput"), n.new("NodeGroupOutput")
    pos = n.new("GeometryNodeInputPosition")
    obj = n.new("GeometryNodeObjectInfo")
    obj.inputs["Object"].default_value = walker
    obj.transform_space = "ORIGINAL"
    sub = n.new("ShaderNodeVectorMath"); sub.operation = "SUBTRACT"
    sep = n.new("ShaderNodeSeparateXYZ")
    flat = n.new("ShaderNodeCombineXYZ")                     # (dx, dy, 0)
    dot = n.new("ShaderNodeVectorMath"); dot.operation = "DOT_PRODUCT"
    k = n.new("ShaderNodeMath"); k.operation = "MULTIPLY"
    k.inputs[1].default_value = -CC / (2 * R_EARTH)
    off = n.new("ShaderNodeCombineXYZ")
    sp = n.new("GeometryNodeSetPosition")
    L.new(pos.outputs[0], sub.inputs[0]); L.new(obj.outputs["Location"], sub.inputs[1])
    L.new(sub.outputs[0], sep.inputs[0])
    L.new(sep.outputs["X"], flat.inputs["X"]); L.new(sep.outputs["Y"], flat.inputs["Y"])
    L.new(flat.outputs[0], dot.inputs[0]); L.new(flat.outputs[0], dot.inputs[1])
    L.new(dot.outputs["Value"], k.inputs[0]); L.new(k.outputs[0], off.inputs["Z"])
    L.new(gi.outputs[0], sp.inputs["Geometry"]); L.new(off.outputs[0], sp.inputs["Offset"])
    L.new(sp.outputs[0], go.inputs[0])
    return ng
curv = None if FLAT else curvature_group()
def bend(o):
    if curv:
        o.modifiers.new("curvature", "NODES").node_group = curv
bend(terrain)

# --- terrain material ----------------------------------------------------------------------
# hillshade baked from the DEM (NW light), as an image the shader samples by Generated coords
gy, gx = np.gradient(z, RES)
az, alt = math.radians(315), math.radians(35)
slope = np.arctan(np.hypot(gx, gy))
aspect = np.arctan2(-gx, gy)
hs = np.clip(np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect), 0, 1)
img = bpy.data.images.new("hillshade", W, H, float_buffer=True, alpha=False)
px = np.ones((H, W, 4), np.float32)
px[..., :3] = hs[::-1, :, None]                              # Blender images start bottom-left
img.pixels.foreach_set(px.ravel())
img.pack()
del px, gx, gy, slope, aspect

mat = bpy.data.materials.new("ground")
nt = nodes_on(mat)
nt.nodes.clear()
N, Lk = nt.nodes, nt.links
out = N.new("ShaderNodeOutputMaterial")
tc = N.new("ShaderNodeTexCoord")
tex = N.new("ShaderNodeTexImage"); tex.image = img; tex.interpolation = "Linear"
tex.extension = "EXTEND"
Lk.new(tc.outputs["Generated"], tex.inputs["Vector"])
toon = N.new("ShaderNodeBsdfToon")
toon.inputs["Size"].default_value = 1.0
toon.inputs["Smooth"].default_value = 0.0
if CHECK:
    toon.inputs["Color"].default_value = (1, 1, 1, 1)
    Lk.new(toon.outputs[0], out.inputs["Surface"])
else:
    # lit colour keeps some relief: 0.55 + 0.45 x hillshade
    mr = N.new("ShaderNodeMapRange")
    mr.inputs["To Min"].default_value = 0.55
    Lk.new(tex.outputs["Color"], mr.inputs["Value"])
    Lk.new(mr.outputs["Result"], toon.inputs["Color"])
    night = N.new("ShaderNodeMix"); night.data_type = "RGBA"
    night.inputs["A"].default_value = (0.004, 0.006, 0.012, 1)
    night.inputs["B"].default_value = (0.028, 0.036, 0.058, 1)
    Lk.new(tex.outputs["Color"], night.inputs["Factor"])
    em = N.new("ShaderNodeEmission")
    Lk.new(night.outputs["Result"], em.inputs["Color"])
    add = N.new("ShaderNodeAddShader")
    Lk.new(toon.outputs[0], add.inputs[0]); Lk.new(em.outputs[0], add.inputs[1])
    Lk.new(add.outputs[0], out.inputs["Surface"])
mat.cycles.emission_sampling = "NONE"   # glow only; never a light source (20 M emissive triangles)
mesh.materials.append(mat)

# --- trail ribbon and walker marker (seen by the camera, never block the light) ----------------
if not CHECK:
    pts = np.array([[fr["x"], fr["y"], fr["ground"] + 6] for fr in trail], np.float32)
    seg = np.diff(pts[:, :2], axis=0)
    nrm = np.c_[-seg[:, 1], seg[:, 0]] / np.hypot(*seg.T)[:, None]
    nrm = np.r_[nrm[:1], (nrm[:-1] + nrm[1:]) / 2, nrm[-1:]]
    half = 14.0
    left = pts.copy(); left[:, :2] += nrm * half
    right = pts.copy(); right[:, :2] -= nrm * half
    n = len(pts)
    rv = np.empty((2 * n, 3), np.float32); rv[0::2], rv[1::2] = left, right
    q = np.arange(n - 1)
    faces = np.stack([2 * q, 2 * q + 1, 2 * q + 3, 2 * q + 2], 1)
    rm = bpy.data.meshes.new("trail")
    rm.from_pydata(rv.tolist(), [], faces.tolist())
    fi = rm.attributes.new("fi", "FLOAT", "POINT")
    fi.data.foreach_set("value", np.repeat(np.arange(n, dtype=np.float32), 2))
    ribbon = bpy.data.objects.new("trail", rm)
    scene.collection.objects.link(ribbon)
    ribbon.visible_shadow = False
    bend(ribbon)
    tm = bpy.data.materials.new("trail")
    tn = nodes_on(tm); tn.nodes.clear()
    to = tn.nodes.new("ShaderNodeOutputMaterial")
    at = tn.nodes.new("ShaderNodeAttribute"); at.attribute_name = "fi"
    cur = tn.nodes.new("ShaderNodeValue"); cur.name = "current"
    lt_ = tn.nodes.new("ShaderNodeMath"); lt_.operation = "LESS_THAN"
    tn.links.new(at.outputs["Fac"], lt_.inputs[0]); tn.links.new(cur.outputs[0], lt_.inputs[1])
    mx = tn.nodes.new("ShaderNodeMix"); mx.data_type = "RGBA"
    mx.inputs["A"].default_value = (0.35, 0.38, 0.45, 1)      # still ahead
    mx.inputs["B"].default_value = (1.0, 0.95, 0.85, 1)       # walked
    tn.links.new(lt_.outputs[0], mx.inputs["Factor"])
    te = tn.nodes.new("ShaderNodeEmission"); te.inputs["Strength"].default_value = 1.5
    tn.links.new(mx.outputs["Result"], te.inputs["Color"]); tn.links.new(te.outputs[0], to.inputs["Surface"])
    tm.cycles.emission_sampling = "NONE"
    rm.materials.append(tm)
    for fr in trail:                                      # walked part grows with the frame
        cur.outputs[0].default_value = fr["f"]
        cur.outputs[0].keyframe_insert("default_value", frame=fr["f"] + 1)

    bpy.ops.mesh.primitive_uv_sphere_add(radius=70, segments=16, ring_count=8)
    mk = bpy.context.active_object
    mk.name = "marker"
    mk.visible_shadow = False
    mm = bpy.data.materials.new("marker")
    mn = nodes_on(mm); mn.nodes.clear()
    me = mn.nodes.new("ShaderNodeEmission"); me.inputs["Color"].default_value = (1, 1, 1, 1)
    me.inputs["Strength"].default_value = 6
    mn.links.new(me.outputs[0], mn.nodes.new("ShaderNodeOutputMaterial").inputs["Surface"])
    mm.cycles.emission_sampling = "NONE"
    mk.data.materials.append(mm)
    mk.parent = walker                                    # rides with the light
    mk.location = (0, 0, 60)

# --- world, camera, render ------------------------------------------------------------------
world = bpy.data.worlds.new("night")
wn = nodes_on(world)
wn.nodes["Background"].inputs["Color"].default_value = (0.004, 0.005, 0.01, 1)
scene.world = world

cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
scene.collection.objects.link(cam)
scene.camera = cam
r = scene.render
cy = scene.cycles
r.engine = "CYCLES"
cy.max_bounces = cy.diffuse_bounces = cy.glossy_bounces = cy.transmission_bounces = 0
cy.transparent_max_bounces = cy.volume_bounces = 0
cy.light_sampling_threshold = 0.0
cy.use_light_tree = False
r.use_persistent_data = True
r.image_settings.file_format = "PNG"
r.dither_intensity = 0.0

if CHECK:
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = max(W, H) * RES
    cam.location = (0, 0, float(z.max()) + 2000)
    cam.data.clip_end = float(z.max() - z.min()) + 4000
    r.resolution_x, r.resolution_y = W, H
    cy.samples = 1
    cy.use_denoising = False
    cy.pixel_filter_type = "BOX"
    cy.filter_width = 0.01
    r.image_settings.color_mode = "BW"
    scene.view_settings.view_transform = "Standard"
else:
    # fixed oblique view from the south-south-east, high enough to see the whole viewshed
    tgt = bpy.data.objects.new("target", None)
    scene.collection.objects.link(tgt)
    mid = trail[len(trail) // 2]
    # (target offset from mid-trail, camera offset from mid-trail, lens mm); steep enough that
    # the frame is all terrain: the shape on the map is the point, not the horizon
    V = dict(south=((-11000, 1000, 1200), (-3000, -32000, 42000), 42),
             southeast=((-6000, 0, 1200), (16000, -28000, 42000), 42),
             top=((-5000, 0, 1200), (-5000, -1, 70000), 40))[VIEW]
    tgt.location = (mid["x"] + V[0][0], mid["y"] + V[0][1], V[0][2])
    cam.location = (mid["x"] + V[1][0], mid["y"] + V[1][1], V[1][2])
    cam.data.lens = V[2]
    cam.data.clip_start = 100
    cam.data.clip_end = 300_000
    tr = cam.constraints.new("TRACK_TO")
    tr.target, tr.track_axis, tr.up_axis = tgt, "TRACK_NEGATIVE_Z", "UP_Y"
    r.resolution_x, r.resolution_y = (540, 675) if PREVIEW else (1080, 1350)
    cy.samples = 8 if PREVIEW else 48
    cy.use_denoising = True
    scene.view_settings.view_transform = "AgX"
    r.image_settings.color_mode = "RGB"
    r.fps = 30

prefs = bpy.context.preferences.addons["cycles"].preferences
for kind in ("METAL", "OPTIX", "CUDA", "HIP", "ONEAPI"):
    try:
        prefs.compute_device_type = kind
        prefs.get_devices()
        if any(dv.type == kind for dv in prefs.devices):
            for dv in prefs.devices:
                dv.use = dv.type == kind
            cy.device = "GPU"
            break
    except TypeError:
        continue
print("device", cy.device, prefs.compute_device_type if cy.device == "GPU" else "")

scene.frame_start, scene.frame_end = 1, len(trail)
os.makedirs(f"{D}/renders", exist_ok=True)
if not CHECK:
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(f"{B}/day-05-walk.blend"))

import time
if CHECK:
    os.makedirs(f"{D}/renders/walk_check", exist_ok=True)
    for f in CHECK:
        scene.frame_set(f + 1)
        r.filepath = os.path.abspath(f"{D}/renders/walk_check/blender_{f:04d}{'_flat' if FLAT else ''}.png")
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        print(f"check frame {f}: {time.time() - t0:.1f} s")
elif STILL is not None:
    scene.frame_set(STILL + 1)
    r.filepath = os.path.abspath(f"{D}/renders/walk_still_{VIEW}_{STILL:04d}{'_preview' if PREVIEW else ''}.png")
    bpy.ops.render.render(write_still=True)
else:
    a_, b_ = FRANGE or (0, len(trail) - 1)
    scene.frame_start, scene.frame_end = a_ + 1, b_ + 1
    scene.frame_step = arg("--stride") or 1
    r.filepath = os.path.abspath(f"{D}/renders/walk{'_preview' if PREVIEW else ''}") + "/"
    t0 = time.time()
    bpy.ops.render.render(animation=True)
    print(f"{b_ - a_ + 1} frames in {time.time() - t0:.0f} s")
