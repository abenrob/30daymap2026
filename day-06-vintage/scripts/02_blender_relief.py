"""Day 6 Vintage: render shaded relief passes in Blender (Cycles, orthographic, top down).

Renders two greyscale passes of a white diffuse terrain:
  sun  : one soft sun from the north-west (cast shadows included)
  sky  : uniform sky dome only (ambient light, valleys darker than ridges)
They are combined and coloured afterwards in 03_imhof_colour.py.

Run: blender -b -P 02_blender_relief.py -- DEM.tif OUTDIR [--step 2] [--exag 2.0]
     [--px 1080] [--samples 64] [--sun-elev 35] [--sun-az 315]
"""
import sys
import math
import argparse
import numpy as np
import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
ap = argparse.ArgumentParser()
ap.add_argument("dem")
ap.add_argument("outdir")
ap.add_argument("--step", type=int, default=2, help="take every Nth DEM pixel for the mesh")
ap.add_argument("--exag", type=float, default=2.0, help="vertical exaggeration")
ap.add_argument("--px", type=int, default=1080, help="output width in pixels")
ap.add_argument("--samples", type=int, default=64)
ap.add_argument("--sun-elev", type=float, default=35.0)
ap.add_argument("--sun-az", type=float, default=315.0, help="azimuth, degrees clockwise from north")
ap.add_argument("--sun-angle", type=float, default=1.5, help="sun disc size in degrees (shadow softness)")
a = ap.parse_args(argv)

# --- read DEM without GDAL (Blender's Python has no rasterio): via tifffile-free raw path
# 01_fetch_dem.py also writes DEM.npy-compatible data if asked; simplest is a sidecar .npy
dem = np.load(a.dem.replace(".tif", ".npy"))
res = float(open(a.dem.replace(".tif", ".res")).read())
dem = dem[::a.step, ::a.step]
h, w = dem.shape
cell = res * a.step
print(f"mesh {w} x {h} verts, cell {cell} m")

# Work in km so Blender units stay sane
S = 1 / 1000.0
xs = (np.arange(w) - (w - 1) / 2) * cell * S
ys = ((h - 1) / 2 - np.arange(h)) * cell * S
X, Y = np.meshgrid(xs, ys)
Z = (dem - dem.min()) * a.exag * S

# --- scene reset
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# --- grid mesh via foreach_set (fast)
verts = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()]).astype(np.float32)
idx = np.arange(h * w).reshape(h, w)
q = np.column_stack([idx[:-1, :-1].ravel(), idx[1:, :-1].ravel(),
                     idx[1:, 1:].ravel(), idx[:-1, 1:].ravel()]).astype(np.int32)
mesh = bpy.data.meshes.new("terrain")
mesh.vertices.add(len(verts))
mesh.vertices.foreach_set("co", verts.ravel())
mesh.loops.add(q.size)
mesh.loops.foreach_set("vertex_index", q.ravel())
mesh.polygons.add(len(q))
mesh.polygons.foreach_set("loop_start", np.arange(0, q.size, 4, dtype=np.int32))
mesh.polygons.foreach_set("loop_total", np.full(len(q), 4, dtype=np.int32))
mesh.update(calc_edges=True)
mesh.validate()
mesh.polygons.foreach_set("use_smooth", np.ones(len(q), dtype=bool))
obj = bpy.data.objects.new("terrain", mesh)
scene.collection.objects.link(obj)

mat = bpy.data.materials.new("white")
mat.use_nodes = True
bsdf = mat.node_tree.nodes["Principled BSDF"]
bsdf.inputs["Base Color"].default_value = (0.8, 0.8, 0.8, 1)
bsdf.inputs["Roughness"].default_value = 1.0
bsdf.inputs["Specular IOR Level"].default_value = 0.0
mesh.materials.append(mat)

# --- orthographic camera, straight down
width_km, height_km = (w - 1) * cell * S, (h - 1) * cell * S
cam_data = bpy.data.cameras.new("cam")
cam_data.type = "ORTHO"
cam_data.ortho_scale = max(width_km, height_km)
cam_data.clip_end = 1000
cam = bpy.data.objects.new("cam", cam_data)
cam.location = (0, 0, 100)
scene.collection.objects.link(cam)
scene.camera = cam

scene.render.resolution_x = a.px
scene.render.resolution_y = int(round(a.px * height_km / width_km))
scene.render.resolution_percentage = 100

# --- render settings
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = a.samples
scene.cycles.use_denoising = True
scene.cycles.max_bounces = 2
scene.cycles.diffuse_bounces = 2
scene.view_settings.view_transform = "Standard"
scene.view_settings.look = "None"
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "BW"
scene.render.image_settings.color_depth = "16"
scene.render.film_transparent = False

world = bpy.data.worlds.new("world")
world.use_nodes = True
scene.world = world
bg = world.node_tree.nodes["Background"]

# sun object
sun_data = bpy.data.lights.new("sun", "SUN")
sun_data.angle = math.radians(a.sun_angle)
sun = bpy.data.objects.new("sun", sun_data)
scene.collection.objects.link(sun)
# Blender sun shines along its local -Z. Rotate: tilt from zenith, then spin.
# Light coming FROM azimuth az (clockwise from north): Z rotation = 180 - az... checked
# against day 2 note: Z rot -135 lights from the north-west (az 315).
sun.rotation_euler = (math.radians(90 - a.sun_elev), 0, math.radians(180 - a.sun_az))


def render(name, sun_strength, sky_strength):
    sun_data.energy = sun_strength
    bg.inputs["Strength"].default_value = sky_strength
    bg.inputs["Color"].default_value = (1, 1, 1, 1)
    scene.render.filepath = f"{a.outdir}/{name}.png"
    bpy.ops.render.render(write_still=True)
    print("wrote", scene.render.filepath)


render("sun", sun_strength=3.0, sky_strength=0.0)
render("sky", sun_strength=0.0, sky_strength=1.0)
