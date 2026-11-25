"""Render the terrain once (the camera never moves): linear EXR, RGB = luminance in cd/m^2, A = terrain mask.

python3 04_render_terrain.py [samples] [res]       (bpy module, cloud CPU)
blender -b <WORK>/derived/scene.blend -P 04_render_terrain.py -- [samples] [res]   (Adam's Mac, GPU)
"""
import sys
import bpy
from common import *

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
SPP = int(args[0]) if args else 128
RES = int(args[1]) if len(args) > 1 else 2160

if not bpy.data.filepath:
    bpy.ops.wm.open_mainfile(filepath=str(DERIVED / "scene.blend"))
sc = bpy.context.scene
sc.render.resolution_x = sc.render.resolution_y = RES
sc.cycles.samples = SPP
sc.cycles.use_denoising = True
try:
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
except TypeError:
    pass
# GPU when Blender has one (Metal on the Mac); falls back to CPU silently
prefs = bpy.context.preferences.addons.get("cycles")
if prefs:
    cp = prefs.preferences
    for t in ("METAL", "OPTIX", "CUDA", "HIP"):
        try:
            cp.compute_device_type = t; cp.get_devices()
            if any(d.type == t for d in cp.devices):
                for d in cp.devices:
                    d.use = True
                sc.cycles.device = "GPU"; print("device", t); break
        except TypeError:
            continue
out = RENDERS / f"terrain_{RES}.exr"
sc.render.filepath = str(out)
bpy.ops.render.render(write_still=True)
print("saved", out)

# Depth: re-render with every terrain surface emitting its distance from the eye in km (camera at the origin).
# Blender 5.2's multilayer EXR wrote only Combined here, so depth comes from this second, cheap render.
dm = bpy.data.materials.new("depth_km"); nt = dm.node_tree if dm.node_tree else None
dm.use_nodes = True; nt = dm.node_tree; nt.nodes.clear()
geo = nt.nodes.new("ShaderNodeNewGeometry"); vm = nt.nodes.new("ShaderNodeVectorMath"); vm.operation = "LENGTH"
mul = nt.nodes.new("ShaderNodeMath"); mul.operation = "MULTIPLY"; mul.inputs[1].default_value = 0.001
em = nt.nodes.new("ShaderNodeEmission"); o = nt.nodes.new("ShaderNodeOutputMaterial")
nt.links.new(geo.outputs["Position"], vm.inputs[0]); nt.links.new(vm.outputs["Value"], mul.inputs[0])
nt.links.new(mul.outputs[0], em.inputs["Strength"]); nt.links.new(em.outputs[0], o.inputs["Surface"])
for ob in bpy.data.objects:
    if ob.type == "MESH" and ob.name.startswith("t"):
        ob.data.materials[0] = dm
    elif ob.name == "light_points":
        ob.hide_render = True              # depth is for the terrain only
sc.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.0
sc.cycles.samples = 4; sc.cycles.use_denoising = False; sc.cycles.max_bounces = 0
sc.render.filter_size = 0.01            # no blending of near and far depths across silhouettes
out = RENDERS / f"depth_{RES}.exr"
sc.render.filepath = str(out)
bpy.ops.render.render(write_still=True)
print("saved", out)
