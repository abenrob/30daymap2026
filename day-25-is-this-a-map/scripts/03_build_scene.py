"""Build the day 25 Blender scene: terrain rings, city lights, fisheye camera looking at the zenith.

Run with the bpy module (Blender 5.2.3 LTS): python3 03_build_scene.py [--markers]
or inside Blender: blender -b -P 03_build_scene.py -- [--markers]

Frame: origin = observer's eye; +X east, +Y true north, +Z up (AEQD grid centred on the summit).
Each vertex: z = h - drop(d) - (GROUND + EYE), drop = d^2 / 2R * (1 - k), k = 0.13.
Units of light: Blender radiance = luminance in cd/m^2. The world (night sky, 20.97 mag/arcsec^2)
lights the terrain; city emission comes from VIIRS. Film is transparent: alpha = terrain.
Output: <WORK>/derived/scene.blend (+ marker list in derived/markers.json with --markers).
"""
import json, math, sys
import numpy as np
import bpy
from common import *

MARKERS = "--markers" in sys.argv
FULL = "--full" in sys.argv          # keep every quad (for a GPU with memory to spare)

# ---------------------------------------------------------------- terrain levels
# (name, source ring, block factor, half-width kept, hole half-width) ; overlap of 2 coarse cells at each seam
LEVELS = [
    ("t05", "inner5", 1, 2_000, 0),
    ("t25", "mid25", 1, 10_000, 1_900),
    ("t50", "mid25", 2, 30_000, 9_800),
    ("t100", "outer100", 1, 60_000, 29_600),
    ("t200", "outer100", 2, 130_000, 59_200),
]
ALBEDO = 0.12                       # limestone / forest mix, at night only the silhouette matters
LUM_PER_RAD = 3e-3                  # cd/m^2 per nW/cm2/sr: 1e-5 W/m2/sr per unit x ~300 lm/W (order of magnitude)
LIGHT_RGB = (1.0, 0.74, 0.50)       # mix of sodium (~2,000 K) and LED (~3,500 K)
SKY_LUM = 10 ** ((12.58 - SQM_ZENITH) / 2.5)   # cd/m^2 from mag/arcsec^2


def sb_to_cd(m):
    return 10 ** ((12.58 - m) / 2.5)


def block_mean(a, f):
    if f == 1:
        return a
    n = a.shape[0] // f * f
    return a[:n, :n].reshape(n // f, f, n // f, f).mean((1, 3))


def ring_array(src):
    name, half, cell = next(r for r in RINGS if r[0] == src)
    return np.load(DERIVED / f"{src}.npy").astype(np.float64), half, cell


def visibility_masks():
    """Per level, cells visible from the eye (radial sweep over the finest ring at each point), dilated by 2 cells.
    The camera never moves, so terrain outside the viewshed can never reach a pixel; dropping it cuts memory ~5x."""
    from scipy.ndimage import map_coordinates, binary_dilation
    rings = [(h, c, np.load(DERIVED / f"{n}.npy")) for n, h, c in RINGS]
    grids = {}
    for name, src, f, keep, hole in LEVELS:
        cell = next(r for r in RINGS if r[0] == src)[2] * f
        grids[name] = (keep, cell, np.zeros((int(round(2 * keep / cell)),) * 2, bool))
    d = np.concatenate([np.arange(1.0, 2000, 1.5), np.arange(2000, 10000, 6.0), np.arange(10000, 30000, 12.0),
                        np.arange(30000, 60000, 25.0), np.arange(60000, 130000, 50.0)])
    eye = GROUND + EYE
    for az in np.radians(np.arange(0, 360, 0.02)):
        x, y = d * np.sin(az), d * np.cos(az)
        h = np.full(d.shape, np.nan)
        for half, cell, a in rings:
            m = np.isnan(h) & (np.abs(x) < half - 2 * cell) & (np.abs(y) < half - 2 * cell)
            h[m] = map_coordinates(a, [(half - y[m]) / cell - .5, (x[m] + half) / cell - .5], order=1)
        e = (h - drop(d) - eye) / d
        v = e >= np.maximum.accumulate(np.r_[-1e9, e[:-1]]) - 1e-4
        xv, yv = x[v], y[v]
        for keep, cell, g in grids.values():
            n = g.shape[0]
            c = ((xv + keep) / cell).astype(int); r = ((keep - yv) / cell).astype(int)
            ok = (c >= 0) & (c < n) & (r >= 0) & (r < n)
            g[r[ok], c[ok]] = True
    out = {}
    for name, (keep, cell, g) in grids.items():
        out[name] = binary_dilation(g, iterations=2)
        print(f"  {name}: {out[name].mean():.1%} of cells visible (dilated)", flush=True)
    return out


def make_level(name, src, f, keep, hole, vis=None):
    a, half, cell = ring_array(src)
    a = block_mean(a, f); cell *= f
    n = a.shape[0]
    # crop to +-keep
    c0 = int(round((half - keep) / cell)); c1 = n - c0
    a = a[c0:c1, c0:c1]; n = a.shape[0]
    xs = -keep + (np.arange(n) + 0.5) * cell
    ys = keep - (np.arange(n) + 0.5) * cell
    X, Y = np.meshgrid(xs, ys)
    D = np.hypot(X, Y)
    Z = a - drop(D) - (GROUND + EYE)
    verts = np.c_[X.ravel(), Y.ravel(), Z.ravel()].astype(np.float32)
    # quads (i, j) -> (i, j), (i+1, j), (i+1, j+1), (i, j+1); counter-clockwise seen from above
    ii, jj = np.meshgrid(np.arange(n - 1), np.arange(n - 1), indexing="ij")
    cx = (xs[jj] + xs[jj + 1]) / 2; cy = (ys[ii] + ys[ii + 1]) / 2
    keepq = ~((np.abs(cx) < hole) & (np.abs(cy) < hole))
    if vis is not None:   # vis is on the level's cell grid (n x n); a quad is kept if any corner is visible
        v = vis[:n, :n]
        keepq &= v[ii, jj] | v[ii + 1, jj] | v[ii, jj + 1] | v[ii + 1, jj + 1]
    ii, jj = ii[keepq], jj[keepq]
    v00 = ii * n + jj
    quads = np.stack([v00 + n, v00 + n + 1, v00 + 1, v00], -1).astype(np.int32)  # south-west first, CCW from above
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(verts)); me.vertices.foreach_set("co", verts.ravel())
    nq = len(quads)
    me.loops.add(nq * 4); me.loops.foreach_set("vertex_index", quads.ravel())
    me.polygons.add(nq)
    me.polygons.foreach_set("loop_start", np.arange(0, nq * 4, 4, dtype=np.int32))
    me.polygons.foreach_set("loop_total", np.full(nq, 4, np.int32))
    # UV in the lights frame (outer100 extent)
    L = RINGS[2][1]
    uv = np.c_[(verts[:, 0] + L) / (2 * L), (verts[:, 1] + L) / (2 * L)].astype(np.float32)
    uvl = me.uv_layers.new(name="lights")
    uvl.data.foreach_set("uv", uv[quads.ravel()].ravel())
    me.update(calc_edges=True)
    me.validate()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    print(f"{name}: {n}x{n} grid, cell {cell} m, {nq:,} quads", flush=True)
    return ob


def lights_image():
    # residual = VIIRS minus the pixels whose light was moved into buildings (02c_light_points.py)
    f = DERIVED / "lights100_residual.npy"
    lum = np.load(f if f.exists() else DERIVED / "lights100.npy").astype(np.float32) * LUM_PER_RAD
    lum = np.flipud(lum)                       # Blender image row 0 = bottom = south
    n = lum.shape[0]
    img = bpy.data.images.new("viirs_lum", n, n, float_buffer=True, alpha=False)
    px = np.ones((n, n, 4), np.float32); px[..., 0] = px[..., 1] = px[..., 2] = lum
    img.pixels.foreach_set(px.ravel())
    # saved beside the .blend (not packed) so the .blend stays small enough to copy
    img.filepath_raw = str(DERIVED / "viirs_lum.exr"); img.file_format = "OPEN_EXR"
    bpy.context.scene.render.image_settings.exr_codec = "ZIP"
    img.save()
    img.colorspace_settings.name = "Non-Color"
    return img


def terrain_material(img):
    m = bpy.data.materials.new("terrain")
    m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    diff = nt.nodes.new("ShaderNodeBsdfDiffuse"); diff.inputs["Color"].default_value = (ALBEDO, ALBEDO, ALBEDO, 1)
    uvn = nt.nodes.new("ShaderNodeUVMap"); uvn.uv_map = "lights"
    tex = nt.nodes.new("ShaderNodeTexImage"); tex.image = img; tex.interpolation = "Linear"; tex.extension = "CLIP"
    em = nt.nodes.new("ShaderNodeEmission"); em.inputs["Color"].default_value = (*LIGHT_RGB, 1)
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(uvn.outputs["UV"], tex.inputs["Vector"])
    nt.links.new(tex.outputs["Color"], em.inputs["Strength"])
    nt.links.new(diff.outputs[0], add.inputs[0]); nt.links.new(em.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs["Surface"])
    return m


def emit_material(name, rgb, strength):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial"); em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*rgb, 1); em.inputs["Strength"].default_value = strength
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return m


def add_sphere(name, loc, r, mat):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=loc, segments=24, ring_count=12)
    ob = bpy.context.active_object; ob.name = name; ob.data.materials.append(mat)
    return ob


def markers():
    """Peak markers (on the DEM maxima) and a dome of 12 markers at known alt/az; positions saved for the check."""
    from pyproj import Transformer
    fwd = Transformer.from_crs(4326, AEQD, always_xy=True)
    out = []
    red = emit_material("mk_red", (1, 0.1, 0.1), 50.0)
    peaks = {"Chamechaude": (5.78808497, 45.28750573), "Grand Som": (5.81202818, 45.37034274),
             "Dent de Crolles": (5.85510227, 45.30809692), "Croix de Belledonne": (5.98812628, 45.16854142),
             "Moucherotte": (5.63946833, 45.14780574), "Mont Blanc": (6.86517, 45.83265)}
    for nm, (lo, la) in peaks.items():
        x, y = fwd.transform(lo, la)
        d = math.hypot(x, y)
        # height: highest DEM vertex near the point, from the finest ring that covers it
        for src in ("mid25", "outer100"):
            a, half, cell = ring_array(src)
            if abs(x) < half - 500 and abs(y) < half - 500:
                j, i = int((x + half) / cell), int((half - y) / cell); k = max(2, int(150 / cell))
                w = a[i - k:i + k + 1, j - k:j + k + 1]; ii, jj = np.unravel_index(np.nanargmax(w), w.shape)
                x, y = -half + (j - k + jj + .5) * cell, half - (i - k + ii + .5) * cell; h = w[ii, jj]; break
        d = math.hypot(x, y); r = d * math.tan(math.radians(0.12))
        z = h - drop(d) - (GROUND + EYE) + r * 1.2
        add_sphere(f"mk_{nm}", (x, y, z), r, red)
        out.append(dict(name=nm, kind="peak", az=math.degrees(math.atan2(x, y)) % 360, alt=math.degrees(math.atan2(z, d))))
    green = emit_material("mk_green", (0.1, 1, 0.1), 50.0)
    blue = emit_material("mk_blue", (0.2, 0.4, 1), 50.0)
    R = 400.0
    for alt in (5, 35, 65):
        for az in (0, 90, 180, 270):
            a, z = math.radians(az), math.radians(alt)
            loc = (R * math.cos(z) * math.sin(a), R * math.cos(z) * math.cos(a), R * math.sin(z))
            mat = green if az == 0 else blue
            add_sphere(f"dome_{alt}_{az}", loc, R * math.tan(math.radians(0.35)), mat)
            out.append(dict(name=f"dome {alt}/{az}", kind="dome", az=az, alt=alt))
    json.dump(out, open(DERIVED / "markers.json", "w"), indent=1)


def add_light_points():
    """One small octahedron per visible lit building (02c_light_points.py). Luminance = I / projected area,
    projected area of an octahedron ~ 2.4 r^2 averaged over directions. Per-face attributes drive the emission."""
    f = DERIVED / "light_points.npz"
    if not f.exists():
        return None
    P = np.load(f)
    x, y, z, I, rgb = P["x"], P["y"], P["z"], P["intensity"], P["rgb"]
    r = np.clip(np.sqrt(P["area"] / np.pi), 3.0, 12.0)
    lum = I / (2.4 * r * r)
    n = len(x)
    off = np.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]], np.float64)
    verts = (np.c_[x, y, z][:, None, :] + off[None] * r[:, None, None]).reshape(-1, 3).astype(np.float32)
    tri = np.array([[0, 2, 4], [2, 1, 4], [1, 3, 4], [3, 0, 4], [2, 0, 5], [1, 2, 5], [3, 1, 5], [0, 3, 5]])
    faces = (tri[None] + 6 * np.arange(n)[:, None, None]).reshape(-1, 3).astype(np.int32)
    me = bpy.data.meshes.new("light_points")
    me.vertices.add(len(verts)); me.vertices.foreach_set("co", verts.ravel())
    nf = len(faces)
    me.loops.add(nf * 3); me.loops.foreach_set("vertex_index", faces.ravel())
    me.polygons.add(nf)
    me.polygons.foreach_set("loop_start", np.arange(0, nf * 3, 3, dtype=np.int32))
    me.polygons.foreach_set("loop_total", np.full(nf, 3, np.int32))
    me.update(calc_edges=True)
    a = me.attributes.new("lum", "FLOAT", "FACE"); a.data.foreach_set("value", np.repeat(lum, 8).astype(np.float32))
    c = me.attributes.new("col", "FLOAT_COLOR", "FACE")
    c.data.foreach_set("color", np.c_[np.repeat(rgb, 8, 0), np.ones(nf)].astype(np.float32).ravel())
    m = bpy.data.materials.new("light_points"); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    o = nt.nodes.new("ShaderNodeOutputMaterial"); em = nt.nodes.new("ShaderNodeEmission")
    al = nt.nodes.new("ShaderNodeAttribute"); al.attribute_name = "lum"
    ac = nt.nodes.new("ShaderNodeAttribute"); ac.attribute_name = "col"
    nt.links.new(al.outputs["Fac"], em.inputs["Strength"]); nt.links.new(ac.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs[0], o.inputs["Surface"])
    me.materials.append(m)
    ob = bpy.data.objects.new("light_points", me); bpy.context.scene.collection.objects.link(ob)
    ob.visible_shadow = False                  # emitters, not occluders
    print(f"light_points: {n:,} buildings, {nf:,} triangles, luminance median {np.median(lum):.2f} cd/m2", flush=True)
    return ob


def camera_and_render():
    sc = bpy.context.scene
    cam = bpy.data.cameras.new("fisheye"); cam.type = "PANO"
    cam.panorama_type = "FISHEYE_EQUIDISTANT"; cam.fisheye_fov = math.radians(210)
    cam.sensor_fit = "HORIZONTAL"; cam.clip_start = 0.05; cam.clip_end = 400_000
    ob = bpy.data.objects.new("fisheye", cam); sc.collection.objects.link(ob)
    ob.location = (0, 0, 0)
    ob.rotation_euler = (0.0, 0.0, 0.0)    # Blender cameras look down -Z; set in fix_orientation()
    sc.camera = ob
    w = bpy.data.worlds.new("night"); sc.world = w; w.use_nodes = True
    bg = w.node_tree.nodes["Background"]; bg.inputs["Color"].default_value = (1, 1, 1, 1)
    bg.inputs["Strength"].default_value = SKY_LUM
    sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"
    sc.cycles.samples = 64; sc.cycles.use_denoising = False
    sc.cycles.max_bounces = 1; sc.cycles.diffuse_bounces = 1
    sc.render.film_transparent = True
    sc.render.resolution_x = sc.render.resolution_y = 2160
    sc.render.image_settings.file_format = "OPEN_EXR"; sc.render.image_settings.color_depth = "32"
    sc.render.image_settings.color_mode = "RGBA"
    sc.view_settings.view_transform = "Standard"
    return ob


if __name__ == "__main__":
    bpy.ops.wm.read_factory_settings(use_empty=True)
    img = lights_image(); mat = terrain_material(img)
    vis = None if FULL else visibility_masks()
    for lv in LEVELS:
        ob = make_level(*lv, vis=None if vis is None else vis[lv[0]]); ob.data.materials.append(mat)
    add_light_points()
    cam = camera_and_render()
    # zenith-looking camera: rotate 180 deg about X (looks +Z); then image up = -Y (south). Turn 180 about Z
    # so image up = north. East/left is checked on the marker render (check_lens.py).
    cam.rotation_euler = (math.pi, 0.0, math.pi)
    if MARKERS:
        markers()
    out = DERIVED / (("scene_markers" if MARKERS else "scene") + ("_full" if FULL else "") + ".blend")
    bpy.ops.wm.save_as_mainfile(filepath=str(out), compress=True, relative_remap=True)
    bpy.data.images["viirs_lum"].filepath = "//viirs_lum.exr"
    bpy.ops.wm.save_as_mainfile(filepath=str(out), compress=True)
    print("saved", out)
