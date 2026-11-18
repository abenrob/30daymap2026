"""Build the Blender scene from config and render once (Cycles CPU).
Run:  python scripts/blender_scene.py [--preview] [--out DIR]

Outputs (out_dir): beauty.png (tone-mapped 16 bit), passes.exr (multilayer, 32 bit float: AOVs terrainxy / bldcov /
turcov + Depth), screen_coords.json (receptors & turbines in pixels), scene_meta.json.
AOV terrainxy = (x_local, y_local, 1): the world position of the terrain surface (before vertical exaggeration it is
identical in x,y) relative to `origin`; after anti-aliasing the 3rd channel is the terrain coverage, so
L93 = origin + (R/B, G/B).
"""
import sys, json, math, time
from pathlib import Path
import numpy as np, yaml, rasterio, bpy
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view

ROOT = Path(__file__).resolve().parents[1]
cfg = yaml.safe_load(open(ROOT / "config.yaml"))
sc, pre = cfg["scene"], cfg["site_run"]["out_prefix"]
preview = "--preview" in sys.argv
FMT = sys.argv[sys.argv.index("--format") + 1] if "--format" in sys.argv else "16x9"
OS = sc.get("oversize", 1.0)
out = ROOT / (sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else f"outputs/blender_v2/{FMT}" + ("_preview" if preview else ""))
out.mkdir(parents=True, exist_ok=True)
EXAG = sc["vertical_exaggeration"]
oj = json.load(open(ROOT / sc["ortho_json"]))
X0, X1, Y0, Y1 = oj["xmin"], oj["xmax"], oj["ymin"], oj["ymax"]
CC = sc["cameras"][FMT]
ox, oy = (round(v / 10) * 10 for v in CC["target_xy"])     # local origin (float precision)
t_start = time.time()

# ---------------- DEM crop ----------------
with rasterio.open(ROOT / cfg["dem"]["path"]) as ds:
    dem = ds.read(1).astype(np.float64); dt = ds.transform
res = dt.a
c0 = int(round((X0 - dt.c) / res)); c1 = int(round((X1 - dt.c) / res))
r0 = int(round((dt.f - Y1) / res)); r1 = int(round((dt.f - Y0) / res))
z = dem[r0:r1, c0:c1]
ny, nx = z.shape
xs = dt.c + (np.arange(c0, c1) + 0.5) * res
ys = dt.f - (np.arange(r0, r1) + 0.5) * res
ZREF = float(np.mean(z))
print(f"terrain crop {ny}x{nx} = {ny*nx/1e6:.2f} M vertices, z {z.min():.0f}-{z.max():.0f}, ref {ZREF:.0f}")

def ground(x, y):
    c = (np.asarray(x) - dt.c) / res - 0.5; r = (dt.f - np.asarray(y)) / res - 0.5
    from scipy.ndimage import map_coordinates
    return map_coordinates(dem, [np.atleast_1d(r), np.atleast_1d(c)], order=1, mode="nearest")

def lz(zv):                      # elevation -> local z with exaggeration
    return (np.asarray(zv) - ZREF) * EXAG

# ---------------- helpers ----------------
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

def make_mesh(name, verts, faces=None, quads=None, uv=None, smooth=False):
    me = bpy.data.meshes.new(name)
    verts = np.asarray(verts, dtype=np.float32)
    if quads is not None:                                   # fast path for big regular meshes
        nq = len(quads)
        me.vertices.add(len(verts)); me.vertices.foreach_set("co", verts.ravel())
        me.loops.add(nq * 4); me.loops.foreach_set("vertex_index", quads.ravel().astype(np.int32))
        me.polygons.add(nq)
        me.polygons.foreach_set("loop_start", np.arange(nq, dtype=np.int32) * 4)
        if smooth:
            me.polygons.foreach_set("use_smooth", np.ones(nq, dtype=bool))
        me.update(); me.validate()
        if uv is not None:
            layer = me.uv_layers.new(name="UV")
            layer.data.foreach_set("uv", uv[quads.ravel()].astype(np.float32).ravel())
    else:
        me.from_pydata(verts.tolist(), [], faces)
        me.update()
        if smooth:
            for p in me.polygons: p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    return ob

def aov_material(name, base_color, rough, aov_color=None, aov_value=None, image=None, sat=1.0, val=1.0, emission_strength=0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    outn = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = rough
    nt.links.new(bsdf.outputs["BSDF"], outn.inputs["Surface"])
    if "Specular IOR Level" in bsdf.inputs: bsdf.inputs["Specular IOR Level"].default_value = 0.25
    if image is not None:
        tex = nt.nodes.new("ShaderNodeTexImage"); tex.image = image; tex.interpolation = "Cubic"
        hsv = nt.nodes.new("ShaderNodeHueSaturation")
        hsv.inputs["Saturation"].default_value = sat; hsv.inputs["Value"].default_value = val
        nt.links.new(tex.outputs["Color"], hsv.inputs["Color"]); nt.links.new(hsv.outputs["Color"], bsdf.inputs["Base Color"])
    else:
        bsdf.inputs["Base Color"].default_value = (*base_color, 1)
    if aov_color:
        geo = nt.nodes.new("ShaderNodeNewGeometry"); sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        comb = nt.nodes.new("ShaderNodeCombineColor"); a = nt.nodes.new("ShaderNodeOutputAOV"); a.aov_name = aov_color
        comb.inputs[2].default_value = 1.0
        nt.links.new(geo.outputs["Position"], sep.inputs["Vector"])
        nt.links.new(sep.outputs["X"], comb.inputs[0]); nt.links.new(sep.outputs["Y"], comb.inputs[1])
        nt.links.new(comb.outputs["Color"], a.inputs["Color"])
    if aov_value:
        a = nt.nodes.new("ShaderNodeOutputAOV"); a.aov_name = aov_value; a.inputs["Value"].default_value = 1.0
    return m

# ---------------- terrain (inner: 5 m + 1 m ortho; outer: whole DEM, stride 4, 2 m ortho) ----------------
def build_terrain(name, zarr, xs_, ys_, img_path, bounds, lower=0.0):
    t0 = time.time()
    ny_, nx_ = zarr.shape
    gx, gy = np.meshgrid(xs_ - ox, ys_ - oy)
    verts = np.column_stack([gx.ravel(), gy.ravel(), lz(zarr - lower).ravel()])
    idx = np.arange(ny_ * nx_).reshape(ny_, nx_)
    q = np.column_stack([idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, 1:].ravel(), idx[1:, :-1].ravel()])[:, ::-1]
    bx0, bx1, by0, by1 = bounds
    uv = np.column_stack([((gx.ravel() + ox) - bx0) / (bx1 - bx0), ((gy.ravel() + oy) - by0) / (by1 - by0)])
    ob = make_mesh(name, verts, quads=q, uv=uv, smooth=True)
    im = bpy.data.images.load(str(ROOT / img_path)); im.colorspace_settings.name = "sRGB"
    ob.data.materials.append(aov_material(name + "_mat", None, 0.9, aov_color="terrainxy", image=im,
                                          sat=sc["ortho_saturation"], val=sc["ortho_value"]))
    print(f"{name}: {nx_*ny_/1e6:.2f} M vertices in {time.time()-t0:.1f}s")
    return ob

build_terrain("terrain", z, xs, ys, sc["ortho_jpg"], (X0, X1, Y0, Y1))
o2 = json.load(open(ROOT / sc["ortho_outer_json"]))
sx = np.arange(0, dem.shape[1], 4); sy = np.arange(0, dem.shape[0], 4)
build_terrain("terrain_outer", dem[np.ix_(sy, sx)], dt.c + (sx + 0.5) * res, dt.f - (sy + 0.5) * res, sc["ortho_outer_jpg"],
              (o2["xmin"], o2["xmax"], o2["ymin"], o2["ymax"]), lower=2.0)

# ---------------- buildings ----------------
bj = json.load(open(ROOT / cfg["site_run"]["buildings"]))
bv, bf, bmat = [], [], []
nv = 0
heights = {}
for f in bj["features"]:
    h = f["properties"].get("hauteur") or sc["building_default_height_m"]
    heights[f["properties"]["cleabs"]] = float(h)
    for poly in f["geometry"]["coordinates"]:
        ring = np.array(poly[0])[:, :2]
        if len(ring) > 1 and np.allclose(ring[0], ring[-1]): ring = ring[:-1]
        if len(ring) < 3: continue
        if not (X0 < ring[:, 0].mean() < X1 and Y0 < ring[:, 1].mean() < Y1): continue
        zb = float(ground(ring[:, 0], ring[:, 1]).min()) - 0.5
        n = len(ring)
        base = np.column_stack([ring[:, 0] - ox, ring[:, 1] - oy, np.full(n, lz(zb))])
        top = base.copy(); top[:, 2] += h
        bv.extend(base.tolist()); bv.extend(top.tolist())
        for i in range(n):
            j = (i + 1) % n
            bf.append([nv + i, nv + j, nv + n + j, nv + n + i]); bmat.append(0)
        bf.append(list(range(nv + n, nv + 2 * n))); bmat.append(1)
        nv += 2 * n
bld = make_mesh("buildings", bv, faces=bf)
for p, m in zip(bld.data.polygons, bmat): p.material_index = m
bld.data.materials.append(aov_material("walls", (0.78, 0.74, 0.68), 0.8, aov_value="bldcov"))
bld.data.materials.append(aov_material("roofs", (0.42, 0.22, 0.17), 0.8, aov_value="bldcov"))
print(f"buildings: {len(bmat)} faces")

# ---------------- turbines ----------------
tur_used = json.load(open(ROOT / "outputs" / f"{pre}_turbines_used.json"))
tdf = __import__("pandas").read_csv(ROOT / cfg["site_run"]["turbines_csv"])
ya = math.radians(CC["from_bearing_deg"]); axis = np.array([math.sin(ya), math.cos(ya), 0.0])
upv = np.array([0, 0, 1.0]); side = np.cross(upv, axis)
S = sc["turbine_scale"]

def cone(r0, r1, h, n=20):
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    v = np.vstack([np.column_stack([r0 * np.cos(th), r0 * np.sin(th), np.zeros(n)]), np.column_stack([r1 * np.cos(th), r1 * np.sin(th), np.full(n, h)])])
    f = [[i, (i + 1) % n, n + (i + 1) % n, n + i] for i in range(n)] + [list(range(n - 1, -1, -1)), list(range(n, 2 * n))]
    return v, f

def box(c, ax_, sd, up, L, W, Hh):
    vs = []
    for a in (-1, 1):
        for b in (-1, 1):
            for d in (-1, 1):
                vs.append(c + a * ax_ * L / 2 + b * sd * W / 2 + d * up * Hh / 2)
    f = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]]
    return np.array(vs), f

def turbine_parts(hub_h, D, phase, overhang):
    V, F = [], []
    def add(v, f):
        F.extend([[i + len(V) for i in q] for q in f]); V.extend(np.asarray(v).tolist())
    add(*cone(0.018 * D * S, 0.012 * D * S, hub_h))
    hub = np.array([0, 0, hub_h]) + axis * overhang
    add(*box(hub - axis * (overhang * 0.2 + 0.05 * D * S * 0.0) - axis * 0.4 * 0 + np.array([0, 0, 0]) - axis * 3.0 * S, axis, side, upv, 0.11 * D * S, 0.034 * D * S, 0.034 * D * S))
    # spinner: elongated ellipsoid
    th = np.linspace(0, np.pi, 8); ph = np.linspace(0, 2 * np.pi, 14, endpoint=False)
    sv, sf = [], []
    for i, t in enumerate(th):
        for p in ph:
            sv.append(hub + axis * (0.025 * D * S * math.cos(t) + 0.012 * D * S) + 0.019 * D * S * math.sin(t) * (math.cos(p) * upv + math.sin(p) * side))
    for i in range(len(th) - 1):
        for j in range(len(ph)):
            a, b = i * len(ph) + j, i * len(ph) + (j + 1) % len(ph)
            sf.append([a, b, b + len(ph), a + len(ph)])
    add(sv, sf)
    R = D / 2 * S
    stations = [(0.03, 0.045, 1.4), (0.17, 0.075, 1.2), (0.5, 0.045, 0.7), (1.0, 0.012, 0.3)]   # (r/R, chord/D, thickness m)
    for k in range(3):
        phi = phase + k * 2 * np.pi / 3
        d = math.cos(phi) * upv + math.sin(phi) * side
        q = -math.sin(phi) * upv + math.cos(phi) * side
        pitch = math.radians(10)
        u = math.cos(pitch) * q + math.sin(pitch) * axis; w = -math.sin(pitch) * q + math.cos(pitch) * axis
        rings = []
        for rr, ch, th_ in stations:
            c = hub + d * (rr * R + 0.016 * D * S)
            cw, tw = ch * D * S, th_ * S
            rings.append([c + u * cw / 2 + w * tw / 2, c - u * cw / 2 + w * tw / 2, c - u * cw / 2 - w * tw / 2, c + u * cw / 2 - w * tw / 2])
        bvs = np.array(rings).reshape(-1, 3); base_i = len(V); bff = []
        for s_ in range(len(stations) - 1):
            for e in range(4):
                a, b = s_ * 4 + e, s_ * 4 + (e + 1) % 4
                bff.append([a, b, b + 4, a + 4])
        bff.append([0, 1, 2, 3]); bff.append([12, 15, 14, 13])
        add(bvs, bff)
    return np.array(V), F

tur_meta = []
twhite = aov_material("turbine_white", (0.92, 0.92, 0.9), 0.45, aov_value="turcov")
tgrey = aov_material("turbine_grey", (0.45, 0.45, 0.45), 0.6, aov_value="turcov")
rng = np.random.default_rng(3)
draw = [(t["id"], t["x"], t["y"], t["hub_height"], t["rotor_diameter"], t["overhang"], True) for t in tur_used]
if sc["show_east_group"]:
    for _, a in tdf[tdf.group.str.startswith("East group")].iterrows():
        if X0 < a.x_l93 < X1 and Y0 < a.y_l93 < Y1:
            draw.append((a.id, a.x_l93, a.y_l93, 80.0, 90.0, 6.0, False))
for tid, x, y, hh, D, ov, mod in draw:
    gz = float(ground(x, y)[0]); gl = float(lz(gz))
    V, F = turbine_parts(hh, D, rng.uniform(0, 2 * np.pi / 3), ov)
    V[:, 0] += x - ox; V[:, 1] += y - oy; V[:, 2] += gl
    ob = make_mesh(f"turbine_{tid}", V, faces=F, smooth=False)
    ob.data.materials.append(twhite if mod else tgrey)
    hub = np.array([x - ox, y - oy, gl + hh]) + axis * ov
    tur_meta.append(dict(id=tid, x=x, y=y, ground_z=gz, hub_local=hub.tolist(), base_local=[x - ox, y - oy, gl], modelled=mod))

# ---------------- world / sun ----------------
world = bpy.data.worlds.new("sky"); scene.world = world; world.use_nodes = True
nt = world.node_tree; nt.nodes.clear()
sky = nt.nodes.new("ShaderNodeTexSky"); sky.sky_type = "MULTIPLE_SCATTERING"
sky.sun_elevation = math.radians(sc["sun"]["elevation_deg"]); sky.sun_size = math.radians(sc["sun"]["size_deg"])
sky.sun_intensity = sc["sun"]["intensity"]; sky.air_density = 1.0; sky.aerosol_density = 1.5; sky.altitude = 500
# Blender world azimuth: rotation 0 puts the sun toward +Y(north)?  we set it and verify in preview
sky.sun_rotation = math.radians(sc["sun"]["azimuth_deg"])    # compass-style, calibrated below
bg = nt.nodes.new("ShaderNodeBackground"); wo = nt.nodes.new("ShaderNodeOutputWorld")
nt.links.new(sky.outputs["Color"], bg.inputs["Color"]); nt.links.new(bg.outputs["Background"], wo.inputs["Surface"])

# ---------------- camera ----------------
cc = CC
tz = float(lz(ground(cc["target_xy"][0], cc["target_xy"][1])[0]))
target = Vector((cc["target_xy"][0] - ox, cc["target_xy"][1] - oy, tz))
fb, el = math.radians(cc["from_bearing_deg"]), math.radians(cc["elevation_deg"])
campos = target + Vector((math.sin(fb) * math.cos(el), math.cos(fb) * math.cos(el), math.sin(el))) * cc["distance_m"]
cam = bpy.data.cameras.new("cam"); cam.lens = cc["lens_mm"]; cam.sensor_width = 36 * OS; cam.sensor_fit = "HORIZONTAL"; cam.clip_start = 10; cam.clip_end = 60000
camob = bpy.data.objects.new("cam", cam); bpy.context.collection.objects.link(camob); camob.location = campos
emp = bpy.data.objects.new("target", None); bpy.context.collection.objects.link(emp); emp.location = target
tc = camob.constraints.new("TRACK_TO"); tc.target = emp; tc.track_axis = "TRACK_NEGATIVE_Z"; tc.up_axis = "UP_Y"
scene.camera = camob

# ---------------- render settings ----------------
Wf, Hf = cc["resolution"]
W, H = round(Wf * OS), round(Hf * OS)
if preview: W, H = W // 3, H // 3
scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = W, H, 100
scene.render.engine = "CYCLES"
cy = scene.cycles; cy.device = "CPU"
cy.samples = 20 if preview else sc["render"]["samples"]
cy.use_denoising = sc["render"]["denoise"]; cy.denoiser = "OPENIMAGEDENOISE"
cy.max_bounces = sc["render"]["bounces"]; cy.use_adaptive_sampling = True
scene.view_settings.view_transform = "AgX"; scene.view_settings.exposure = sc.get("exposure", -3.0)
vl = scene.view_layers[0]
vl.use_pass_z = True
for name, typ in (("terrainxy", "COLOR"), ("bldcov", "VALUE"), ("turcov", "VALUE")):
    a = vl.aovs.add(); a.name = name; a.type = typ
bpy.context.view_layer.update()

# ---------------- screen coordinates ----------------
def to_px(p):
    co = world_to_camera_view(scene, camob, Vector(p))
    return [co.x * W, (1 - co.y) * H, co.z]
rec = __import__("pandas").read_csv(ROOT / "outputs" / f"{pre}_receptors.csv")
recs = []
for _, a in rec.iterrows():
    gl = float(lz(ground(a.x, a.y)[0])); hgt = heights.get(a.id, sc["building_default_height_m"])
    recs.append(dict(id=a.id, x=a.x, y=a.y, roof=to_px([a.x - ox, a.y - oy, gl + hgt]), ground=to_px([a.x - ox, a.y - oy, gl])))
for t in tur_meta:
    t["hub_px"] = to_px(t["hub_local"]); t["base_px"] = to_px(t["base_local"])
labels = []
tp = ROOT / "data/vector/toponyms_bdtopo.json"
if tp.exists():
    for n in json.load(open(tp)):
        if n["name"] and X0 < n["x"] < X1 and Y0 < n["y"] < Y1:
            gl = float(lz(ground(n["x"], n["y"])[0]))
            labels.append(dict(name=n["name"], kind=n["kind"], nature=n["nature"], importance=n["importance"], x=n["x"], y=n["y"], px=to_px([n["x"] - ox, n["y"] - oy, gl + 4])))
json.dump(dict(width=W, height=H, final=[Wf, Hf], oversize=OS, receptors=recs, turbines=tur_meta, labels=labels), open(out / "screen_coords.json", "w"))
json.dump(dict(origin=[ox, oy], zref=ZREF, exaggeration=EXAG, extent=[X0, X1, Y0, Y1], camera_location=list(campos), format=FMT, oversize=OS, final=[Wf, Hf],
               sun=sc["sun"], width=W, height=H), open(out / "scene_meta.json", "w"), indent=1)

# ---------------- render ----------------
print(f"scene built in {time.time()-t_start:.0f}s; rendering {W}x{H} @ {cy.samples} spp ...", flush=True)
t1 = time.time()
scene.render.image_settings.media_type = "MULTI_LAYER_IMAGE"
scene.render.image_settings.color_depth = "32"; scene.render.image_settings.exr_codec = "ZIP"
scene.render.filepath = str(out / "passes.exr")
bpy.ops.render.render(write_still=True)
rr = bpy.data.images["Render Result"]
scene.render.image_settings.media_type = "IMAGE"; scene.render.image_settings.file_format = "PNG"; scene.render.image_settings.color_depth = "16"
rr.save_render(str(out / "beauty.png"))
print(f"render done in {time.time()-t1:.0f}s (total {time.time()-t_start:.0f}s)")
