"""Viewshed per turbine with Cycles ray tracing: one point light at the blade tip lights the terrain.
Lit ground can see the tip, shadowed ground cannot.

Run from the workspace root:
  blender -b -P site/day-05-senses-sight/scripts/04_viewshed_blender.py -- [--limit N] [--save-blend]

Scene (1 unit = 1 m, origin at the AOI centre):
  occluder  the 50 m DEM as a mesh; casts shadows, invisible to the camera
  receiver  the SAME mesh data, instanced 1.7 m higher (eye height); seen by the camera,
            casts no shadows. Instancing means one mesh and one BVH in memory, not two.
  light     one point light, radius 0 (hard, exact shadows), moved to each turbine's tip in turn
  camera    orthographic, straight down, 800 x 800 px = the 40 x 40 km square around the turbine,
            pixel centres on the DEM pixel centres
Receiver shader = Diffuse + Translucent, so a tip below the local slope (seen from a summit)
still lights the pixel. Constant light falloff and a huge strength turn "any light" into 255:
the 8-bit PNG is a binary visibility mask. Direct light only (0 bounces), 1 sample, box filter
0.01 px: each pixel is one camera ray plus one shadow ray, no noise, no denoiser.

Output: work/data/day-05-sight/renders/blender/<turbine id>.png and timings.json
GPU: picks Metal / OptiX / CUDA / HIP if present, else CPU.
"""
import bpy, json, os, sys, time
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
LIMIT = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else None
SAVE_BLEND = "--save-blend" in argv

D = "work/data/day-05-sight"
OUT = f"{D}/renders/blender"
os.makedirs(OUT, exist_ok=True)
meta = json.load(open(f"{D}/blender/meta.json"))
turbines = json.load(open(f"{D}/blender/turbines.json"))[:LIMIT]
z = np.load(f"{D}/blender/dem_50m.npy")
H, W = z.shape
RES, R = meta["res"], meta["range_m"]
WIN = int(2 * R / RES)                       # 800 px
ox, oy = meta["origin"]
x0 = meta["xmin"] - ox                       # scene x of the grid's west edge
y0 = meta["ymax"] - oy                       # scene y of the grid's north edge

t_start = time.time()
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# --- terrain mesh: vertices at pixel centres, one quad per 2 x 2 pixels -----------------
t0 = time.time()
cols = x0 + (np.arange(W) + 0.5) * RES
rows = y0 - (np.arange(H) + 0.5) * RES
X, Y = np.meshgrid(cols, rows)
co = np.stack([X, Y, z], axis=-1).astype("float32").ravel()
idx = np.arange(H * W, dtype=np.int32).reshape(H, W)
a, b = idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel()
c, d = idx[1:, 1:].ravel(), idx[1:, :-1].ravel()
loops = np.stack([a, d, c, b], axis=1).ravel()          # counter-clockwise seen from above
nf = a.size
mesh = bpy.data.meshes.new("dem")
mesh.vertices.add(H * W)
mesh.vertices.foreach_set("co", co)
mesh.loops.add(loops.size)
mesh.loops.foreach_set("vertex_index", loops)
mesh.polygons.add(nf)
mesh.polygons.foreach_set("loop_start", np.arange(0, 4 * nf, 4, dtype=np.int32))
mesh.update(calc_edges=True)
del co, loops, a, b, c, d, X, Y
print(f"mesh {W} x {H}: {len(mesh.vertices):,} vertices, {len(mesh.polygons):,} quads, {time.time() - t0:.1f} s")

occ = bpy.data.objects.new("occluder", mesh)
rec = bpy.data.objects.new("receiver", mesh)            # same mesh data = instanced in Cycles
rec.location.z = meta["eye_m"]
for o in (occ, rec):
    scene.collection.objects.link(o)
occ.visible_camera = False
occ.visible_shadow = True
rec.visible_camera = True
rec.visible_shadow = False

# receiver material: Diffuse + Translucent so light from either side of the surface counts
mat = bpy.data.materials.new("receiver")
try:
    mat.use_nodes = True                # always on, and deprecated, from Blender 5
except AttributeError:
    pass
nt = mat.node_tree
nt.nodes.clear()
out = nt.nodes.new("ShaderNodeOutputMaterial")
add = nt.nodes.new("ShaderNodeAddShader")
dif = nt.nodes.new("ShaderNodeBsdfDiffuse")
tra = nt.nodes.new("ShaderNodeBsdfTranslucent")
nt.links.new(dif.outputs[0], add.inputs[0])
nt.links.new(tra.outputs[0], add.inputs[1])
nt.links.new(add.outputs[0], out.inputs["Surface"])
mesh.materials.append(mat)
# receiver uses the material through the mesh; the occluder is hidden from the camera anyway

# --- light: point, radius 0, constant falloff ------------------------------------------
ld = bpy.data.lights.new("tip", "POINT")
ld.shadow_soft_size = 0.0
ld.energy = 1.0
try:
    ld.use_nodes = True
except AttributeError:
    pass
lt = ld.node_tree
em = lt.nodes["Emission"]
fo = lt.nodes.new("ShaderNodeLightFalloff")
fo.inputs["Strength"].default_value = 1e7
lt.links.new(fo.outputs["Constant"], em.inputs["Strength"])
light = bpy.data.objects.new("tip", ld)
scene.collection.objects.link(light)

# --- camera: orthographic, top-down, WIN x WIN px ----------------------------------------
cd = bpy.data.cameras.new("ortho")
cd.type = "ORTHO"
cd.ortho_scale = WIN * RES
zmax, zmin = float(z.max()), float(z.min())
cd.clip_start = 1.0
cd.clip_end = (zmax + 1000) - zmin + 100
cam = bpy.data.objects.new("ortho", cd)
cam.location.z = zmax + 1000
scene.collection.objects.link(cam)
scene.camera = cam

# --- render settings ------------------------------------------------------------------
r = scene.render
r.engine = "CYCLES"
r.resolution_x = r.resolution_y = WIN
r.resolution_percentage = 100
r.use_persistent_data = True                            # keep the BVH between renders
r.image_settings.file_format = "PNG"
r.image_settings.color_mode = "BW"
r.image_settings.color_depth = "8"
r.film_transparent = False
r.dither_intensity = 0.0                                # no noise added to the 8-bit output
scene.view_settings.view_transform = "Standard"
scene.view_settings.look = "None"
scene.world = bpy.data.worlds.new("black")
scene.world.color = (0, 0, 0)
cy = scene.cycles
cy.samples = 1
cy.use_adaptive_sampling = False
cy.use_denoising = False
cy.max_bounces = cy.diffuse_bounces = cy.glossy_bounces = cy.transmission_bounces = 0
cy.transparent_max_bounces = cy.volume_bounces = 0
cy.light_sampling_threshold = 0.0
cy.use_light_tree = False
cy.pixel_filter_type = "BOX"
cy.filter_width = 0.01
cy.seed = 0
cy.caustics_reflective = cy.caustics_refractive = False

device = "CPU"
prefs = bpy.context.preferences.addons["cycles"].preferences
for kind in ("METAL", "OPTIX", "CUDA", "HIP", "ONEAPI"):
    try:
        prefs.compute_device_type = kind
        prefs.get_devices()
        gpus = [d for d in prefs.devices if d.type == kind]
        if gpus:
            for d in prefs.devices:
                d.use = d.type == kind
            cy.device = "GPU"
            device = f"{kind}: " + ", ".join(d.name for d in gpus)
            break
    except TypeError:
        continue
print("device", device)

if SAVE_BLEND:
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(f"{D}/blender/day-05-viewshed.blend"))

# --- one render per turbine -------------------------------------------------------------
setup_s = time.time() - t_start
times = []
for i, t in enumerate(turbines):
    # camera centre on the top-left corner of the turbine's cell: window = rows/cols -400..+399
    cam.location.x = x0 + t["col"] * RES
    cam.location.y = y0 - t["row"] * RES
    light.location = t["light"]
    r.filepath = os.path.abspath(f"{OUT}/{t['id']}.png")
    t1 = time.time()
    bpy.ops.render.render(write_still=True)
    times.append(time.time() - t1)
    print(f"{i + 1}/{len(turbines)} {t['id']} {times[-1]:.2f} s")

json.dump(dict(device=device, blender=bpy.app.version_string, setup_s=setup_s,
               first_render_s=times[0], render_s=times[1:], total_render_s=sum(times),
               n=len(turbines), window_px=WIN, grid=[W, H]),
          open(f"{OUT}/timings.json", "w"), indent=1)
print(f"setup {setup_s:.1f} s, first render {times[0]:.1f} s (BVH build), "
      f"then median {np.median(times[1:]) if len(times) > 1 else 0:.2f} s; total {sum(times):.1f} s")
