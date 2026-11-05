"""Beauty render: every turbine tip is a lamp, all 193 on at once, over the true-scale terrain.
The glow is the viewshed made visible: ground a tip can see is lit, brighter where more tips see it.
(The analytical counts come from 04, one exact render per turbine; this one is for looking at.)

Run from the workspace root:
  blender -b -P site/day-05-senses-sight/scripts/08_hero.py -- [--preview] [--samples N] [--view NAME]
  --preview   540 x 675 px, few samples (checking the framing)
  default     1080 x 1350 px (LinkedIn 4:5)
Views are defined in VIEWS below: camera position and target in EPSG:2154 + altitude.
Output: work/data/day-05-sight/renders/hero_<view>[_preview].png and .blend
"""
import bpy, json, math, os, sys
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
PREVIEW = "--preview" in argv
SAMPLES = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else (32 if PREVIEW else 1024)
VIEW = argv[argv.index("--view") + 1] if "--view" in argv else "overview"

# camera (x, y, altitude m) -> target (x, y, altitude m), lens mm; EPSG:2154
VIEWS = {
    # from above Montelimar's latitude, south of the clusters, looking north up the Rhone
    "rhone_north": dict(cam=(838000, 6340000, 9000), target=(835000, 6420000, 500), lens=30),
    # high oblique over the whole study area from the south
    "overview": dict(cam=(842000, 6362000, 80000), target=(842000, 6418000, 300), lens=45),
    # over the Rhone looking west onto the Ardeche plateau ridges
    "plateau_west": dict(cam=(832000, 6402000, 16000), target=(786000, 6414000, 900), lens=32),
}

D = "work/data/day-05-sight"
meta = json.load(open(f"{D}/blender/meta.json"))
turbines = json.load(open(f"{D}/blender/turbines.json"))
z = np.load(f"{D}/blender/dem_50m.npy")
H, W = z.shape
RES = meta["res"]
ox, oy = meta["origin"]
x0, y0 = meta["xmin"] - ox, meta["ymax"] - oy

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# --- terrain (same mesh as 04, true scale: exaggerating z would change what is visible) --
cols = x0 + (np.arange(W) + 0.5) * RES
rows = y0 - (np.arange(H) + 0.5) * RES
X, Y = np.meshgrid(cols, rows)
co = np.stack([X, Y, z], axis=-1).astype("float32").ravel()
idx = np.arange(H * W, dtype=np.int32).reshape(H, W)
a, b, c, d = idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, 1:].ravel(), idx[1:, :-1].ravel()
loops = np.stack([a, d, c, b], axis=1).ravel()
mesh = bpy.data.meshes.new("dem")
mesh.vertices.add(H * W)
mesh.vertices.foreach_set("co", co)
mesh.loops.add(loops.size)
mesh.loops.foreach_set("vertex_index", loops)
mesh.polygons.add(a.size)
mesh.polygons.foreach_set("loop_start", np.arange(0, loops.size, 4, dtype=np.int32))
mesh.update(calc_edges=True)
mesh.polygons.foreach_set("use_smooth", np.ones(a.size, bool))
del co, loops, a, b, c, d, X, Y
terrain = bpy.data.objects.new("terrain", mesh)
scene.collection.objects.link(terrain)

mat = bpy.data.materials.new("ground")
try:
    mat.use_nodes = True                # always on, and deprecated, from Blender 5
except AttributeError:
    pass
bsdf = mat.node_tree.nodes["Principled BSDF"]
bsdf.inputs["Base Color"].default_value = (0.7, 0.7, 0.7, 1)
bsdf.inputs["Roughness"].default_value = 1.0
mesh.materials.append(mat)

# --- one lamp per turbine tip, constant falloff, plus a small emissive marker -----------
lamp_col = (1.0, 0.5, 0.18)
mk = bpy.data.materials.new("marker")
try:
    mk.use_nodes = True
except AttributeError:
    pass
nt = mk.node_tree
nt.nodes.clear()
e = nt.nodes.new("ShaderNodeEmission")
e.inputs["Color"].default_value = (1.0, 0.85, 0.6, 1)
e.inputs["Strength"].default_value = 40
o = nt.nodes.new("ShaderNodeOutputMaterial")
nt.links.new(e.outputs[0], o.inputs["Surface"])
bpy.ops.mesh.primitive_uv_sphere_add(radius=60, segments=12, ring_count=6)
proto = bpy.context.active_object
proto.data.materials.append(mk)
scene.collection.objects.unlink(proto)

ld = bpy.data.lights.new("tip", "POINT")
ld.shadow_soft_size = 0.0
ld.color = lamp_col
try:
    ld.use_nodes = True
except AttributeError:
    pass
fo = ld.node_tree.nodes.new("ShaderNodeLightFalloff")
fo.inputs["Strength"].default_value = 0.8
# range limit: strength x (distance to the lamp < 20 km), the same disc as the analysis
lp = ld.node_tree.nodes.new("ShaderNodeLightPath")
lt = ld.node_tree.nodes.new("ShaderNodeMath")
lt.operation = "LESS_THAN"
lt.inputs[1].default_value = meta["range_m"]
mul = ld.node_tree.nodes.new("ShaderNodeMath")
mul.operation = "MULTIPLY"
ld.node_tree.links.new(lp.outputs["Ray Length"], lt.inputs[0])
ld.node_tree.links.new(lt.outputs[0], mul.inputs[0])
ld.node_tree.links.new(fo.outputs["Constant"], mul.inputs[1])
ld.node_tree.links.new(mul.outputs[0], ld.node_tree.nodes["Emission"].inputs["Strength"])
for t in turbines:
    L = bpy.data.objects.new(f"tip_{t['id']}", ld)
    L.location = t["light"]
    scene.collection.objects.link(L)
    m = bpy.data.objects.new(f"marker_{t['id']}", proto.data)
    m.location = t["light"]
    m.visible_shadow = False            # the lamp sits inside it
    scene.collection.objects.link(m)

# faint cold moonlight and sky, only so the relief reads where no tip reaches
sun = bpy.data.objects.new("moon", bpy.data.lights.new("moon", "SUN"))
sun.data.energy = 0.0012
sun.data.color = (0.55, 0.65, 1.0)
sun.data.angle = math.radians(0.5)
sun.rotation_euler = (math.radians(60), 0, math.radians(-135))   # from the north-west
scene.collection.objects.link(sun)
world = bpy.data.worlds.new("night")
try:
    world.use_nodes = True
except AttributeError:
    pass
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.006, 0.008, 0.016, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0
scene.world = world

# --- camera ---------------------------------------------------------------------------
v = VIEWS[VIEW]
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.lens = v["lens"]
cam.data.clip_start = 50
cam.data.clip_end = 400_000
cam.location = (v["cam"][0] - ox, v["cam"][1] - oy, v["cam"][2])
tgt = bpy.data.objects.new("target", None)
tgt.location = (v["target"][0] - ox, v["target"][1] - oy, v["target"][2])
scene.collection.objects.link(tgt)
scene.collection.objects.link(cam)
tr = cam.constraints.new("TRACK_TO")
tr.target = tgt
tr.track_axis = "TRACK_NEGATIVE_Z"
tr.up_axis = "UP_Y"
scene.camera = cam

# --- render ---------------------------------------------------------------------------
r = scene.render
r.engine = "CYCLES"
r.resolution_x, r.resolution_y = (540, 675) if PREVIEW else (1080, 1350)
r.image_settings.file_format = "PNG"
r.image_settings.color_depth = "16"
scene.view_settings.view_transform = "AgX"
try:
    scene.view_settings.look = "AgX - Medium High Contrast"
except TypeError:
    pass
cy = scene.cycles
cy.samples = SAMPLES
cy.use_denoising = True
cy.max_bounces = 2
cy.diffuse_bounces = 1
cy.use_light_tree = True
cy.light_sampling_threshold = 0.0
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
print("device", cy.device, prefs.compute_device_type)

suffix = "_preview" if PREVIEW else ""
r.filepath = os.path.abspath(f"{D}/renders/hero_{VIEW}{suffix}.png")
bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(f"{D}/blender/day-05-hero.blend"))
bpy.ops.render.render(write_still=True)
