"""
Step 3: build the inverted-coast scene in Blender from data/terrain.npz.

Run headless from the project folder (use the full path to Blender if it is not on PATH):
    blender --background --python 03_build_blender.py -- --out monterey.blend
    blender --background --python 03_build_blender.py -- --out monterey.blend --render still.png
    blender --background --python 03_build_blender.py -- --out morph.blend --morph --block

What you get
  * One terrain mesh: 1 Blender unit = 1 km, +X east, +Y north, centred on the origin, true scale.
    Basis shape = ORIGINAL terrain; shape key "Inverted" = Z -> -Z about sea level. Key = 1 shows the
    inverted world (default). Animate it 0 -> 1 for the morph (--morph does this).
  * Real water: a translucent reflective surface at sea level (Z = 0).
  * Land vs underwater is decided by the height of the surface AS DISPLAYED, not by the original
    elevation. Above sea level the terrain is shaded like land (lowland green/sand, dry hills, rock on
    steep faces, snow on high ground). Below sea level it is shaded like seabed seen through water
    (depth tint) with isobath lines. So after the inversion, the old California is underwater and the
    old seafloor is land, and during the morph the coastline moves by itself.
  * --block: cut the model as a diorama slab: cream side walls and base, water column visible in the walls.
  * Vertical exaggeration is just the object's Z scale; change it any time.

Compatible with Blender 4.x and 5.x.
"""
import argparse
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

# Loop: normal -> inverted -> normal. Frame 150 equals frame 1, so --render-anim stops at 149 for a seamless GIF.
MORPH_KEYS = ((1, 0.0), (15, 0.0), (60, 1.0), (90, 1.0), (135, 0.0), (150, 0.0))
WATER_EPS = 0.0002  # km above Z=0
ARGV_FALLBACK = ["--npz", "data/terrain.npz", "--out", "monterey.blend"]

# ---- palettes: (metres, sRGB hex). Edit freely. ---------------------------------------------------
LAND = [  # by height above sea level
    (0, "#c9bf93"), (25, "#a2ad66"), (250, "#b9ad6f"), (700, "#8f8a5c"), (1200, "#7f7b58"),
    (1800, "#8d8173"), (2600, "#9a948c"), (3600, "#b3aea6"),
]
SEA = [  # by depth below sea level; this is the seabed as seen through the water
    (0, "#8fd6cb"), (40, "#63bcc3"), (250, "#3f93b3"), (800, "#27699a"), (1800, "#17487a"), (3500, "#0b2a52"),
]
ROCK, SNOW, FOAM = "#7d756b", "#f4f6f8", "#f2efe2"
ISOBATH_COLOR = "#dff1ff"
WATER_COLOR = (0.03, 0.22, 0.36, 1.0)
WALL_COLOR = (0.86, 0.82, 0.73, 1.0)
SKY_HORIZON, SKY_ZENITH = "#d8e6ee", "#3f78b5"


# --------------------------------------------------------------------------- small helpers
def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else ARGV_FALLBACK
    ap = argparse.ArgumentParser()
    ap.add_argument("--npz", default="data/terrain.npz")
    ap.add_argument("--out", default="monterey.blend")
    ap.add_argument("--ve", type=float, default=3.0, help="vertical exaggeration (default 3)")
    ap.add_argument("--max-verts", type=float, default=3e6, help="block-average the grid to about this many vertices")
    ap.add_argument("--state", choices=["inverted", "original"], default="inverted", help="initial shape-key state")
    ap.add_argument("--morph", action="store_true", help="loop original -> inverted -> original over 150 frames")
    ap.add_argument("--block", action="store_true", help="diorama slab: side walls + base")
    ap.add_argument("--square", action="store_true", help="crop to a square (the short side of the grid) for portrait/square frames")
    ap.add_argument("--square-offset", type=float, default=0.4, help="where the square sits along the long side: 0 = west edge, 1 = east edge")
    ap.add_argument("--no-water", action="store_true")
    ap.add_argument("--isobath", type=float, default=250.0, help="isobath interval in metres (0 = off)")
    ap.add_argument("--isobath-width", type=float, default=0.0, help="line width in metres on the ground (default: one cell)")
    ap.add_argument("--flag-fill", action="store_true", help="wash out ocean cells that are coarse gap-fill, not survey data")
    ap.add_argument("--sun-az", type=float, default=235.0, help="compass direction the sun is IN (default SW)")
    ap.add_argument("--sun-follow", action="store_true", help="sun turns with the camera, so --sun-az is relative to the view (315 = upper left)")
    ap.add_argument("--sun-alt", type=float, default=24.0)
    ap.add_argument("--engine", choices=["cycles", "eevee"], default="cycles")
    ap.add_argument("--render", default=None, help="also render a still to this PNG")
    ap.add_argument("--render-anim", default=None, metavar="DIR", help="render the morph as PNG frames into DIR (use with --morph)")
    ap.add_argument("--step", type=int, default=1, help="render every Nth frame (3 = 50 frames, good for a GIF)")
    ap.add_argument("--frames", default=None, help="frame range for --render-anim, e.g. 1-150 or 1,75,150")
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--aspect", default="16:9", help="frame shape W:H, e.g. 4:5 for a LinkedIn portrait")
    ap.add_argument("--tilt", type=float, default=36.0, help="camera elevation angle in degrees")
    ap.add_argument("--cam-start", type=float, default=190.0, help="camera compass bearing at the start (0=N, 90=E, 180=S, 270=W)")
    ap.add_argument("--cam-end", type=float, default=None, help="bearing at the fully inverted state; with --morph the camera follows the morph and returns (default: no orbit). North to west: --cam-start 0 --cam-end -90")
    return ap.parse_args(argv)


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def rgba(h):
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return (srgb_to_linear(r), srgb_to_linear(g), srgb_to_linear(b), 1.0)


def block_mean(a, f):
    """Average f x f blocks of cells: keeps the vertex count down for big grids (area mean, not point sampling)."""
    if f == 1:
        return a
    h, w = (a.shape[0] // f) * f, (a.shape[1] // f) * f
    return a[:h, :w].reshape(h // f, f, w // f, f).mean(axis=(1, 3))


class Shader:
    """Tiny node-building DSL. Every helper takes sockets or plain numbers and returns an output socket."""

    def __init__(self, nt):
        self.nt = nt

    def node(self, kind, **attrs):
        n = self.nt.nodes.new(kind)
        for k, v in attrs.items():
            setattr(n, k, v)
        return n

    def _set(self, sock, v):
        if isinstance(v, (int, float)):
            sock.default_value = v
        elif isinstance(v, (tuple, list)):
            sock.default_value = v
        else:
            self.nt.links.new(v, sock)

    def math(self, op, a, b=None, c=None, clamp=False):
        n = self.node("ShaderNodeMath", operation=op, use_clamp=clamp)
        for i, v in enumerate((a, b, c)):
            if v is not None:
                self._set(n.inputs[i], v)
        return n.outputs[0]

    def mrange(self, v, fmin, fmax, tmin=0.0, tmax=1.0, smooth=True, clamp=True):
        n = self.node("ShaderNodeMapRange", interpolation_type="SMOOTHSTEP" if smooth else "LINEAR", clamp=clamp)
        for i, x in enumerate((v, fmin, fmax, tmin, tmax)):
            self._set(n.inputs[i], x)
        return n.outputs[0]

    def mix(self, fac, a, b, blend="MIX"):
        n = self.node("ShaderNodeMix", data_type="RGBA", blend_type=blend)
        self._set(n.inputs[0], fac)
        self._set(n.inputs[6], a)
        self._set(n.inputs[7], b)
        return n.outputs[2]

    def ramp(self, v, stops, lo, hi):
        """Colour ramp over [lo, hi] metres from (metres, hex) stops."""
        pos = self.mrange(v, lo, hi, 0.0, 1.0, smooth=False)
        n = self.node("ShaderNodeValToRGB")
        el = n.color_ramp.elements
        while len(el) > 1:
            el.remove(el[-1])
        for i, (m, h) in enumerate(stops):
            p = min(max((m - lo) / (hi - lo), 0.0), 1.0)
            e = el[0] if i == 0 else el.new(p)
            e.position, e.color = p, rgba(h)
        self.nt.links.new(pos, n.inputs[0])
        return n.outputs[0]

    def xyz(self, vec):
        n = self.node("ShaderNodeSeparateXYZ")
        self.nt.links.new(vec, n.inputs[0])
        return n.outputs["X"], n.outputs["Y"], n.outputs["Z"]


def new_material(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.node_tree.nodes.clear()
    return mat


# --------------------------------------------------------------------------- geometry
def perimeter(ny, nx):
    """Vertex indices around the grid, clockwise as seen from above, starting at the NW corner."""
    idx = np.arange(nx * ny, dtype=np.int32).reshape(ny, nx)
    return np.concatenate([idx[0, :], idx[1:, -1], idx[-1, -2::-1], idx[-2:0:-1, 0]])


def set_polys(mesh, loops, starts, lengths, mat_index=None, smooth=None):
    """Fill a mesh's faces from flat numpy arrays (much faster than bmesh for millions of faces)."""
    nf = len(starts)
    mesh.loops.add(len(loops))
    mesh.loops.foreach_set("vertex_index", loops.astype(np.int32))
    mesh.polygons.add(nf)
    mesh.polygons.foreach_set("loop_start", starts.astype(np.int32))
    if bpy.app.version < (4, 0, 0):
        mesh.polygons.foreach_set("loop_total", lengths.astype(np.int32))
    if mat_index is not None:
        mesh.polygons.foreach_set("material_index", mat_index.astype(np.int32))
    if smooth is not None:
        mesh.polygons.foreach_set("use_smooth", smooth.astype(bool))


def build_terrain(elev, surveyed, cell_m, block, base_z):
    """Build the terrain mesh straight from the elevation array.

    Units: 1 Blender unit = 1 km, +X east, +Y north, centred on the origin. Real heights, no exaggeration
    (that is the object's Z scale). Vertices are laid out as [terrain grid | block extras]. Material slots:
    0 terrain, 1 cream cut wall + base, 2 water wall.
    Returns the object, the vertex coordinates (original state) and inv_mask: which vertices the 'Inverted'
    shape key negates (everything that follows the surface; the base plate stays put)."""
    ny, nx = elev.shape
    xs = (np.arange(nx) + 0.5) * cell_m / 1000.0
    ys = (np.arange(ny) + 0.5) * cell_m / 1000.0
    xs -= xs.mean()
    ys = ys.mean() - ys  # row 0 -> +Y (north)
    X, Y = np.meshgrid(xs, ys)
    Z = elev / 1000.0
    co = np.stack([X, Y, Z], axis=-1).astype(np.float32).reshape(-1, 3)
    nT = nx * ny

    idx = np.arange(nT, dtype=np.int32).reshape(ny, nx)
    quads = np.stack([idx[:-1, :-1], idx[1:, :-1], idx[1:, 1:], idx[:-1, 1:]], axis=-1).reshape(-1)  # NW SW SE NE: CCW from above
    nq = (ny - 1) * (nx - 1)
    loops, starts, lengths = [quads], [np.arange(0, 4 * nq, 4)], [np.full(nq, 4)]
    mat = [np.zeros(nq, np.int32)]
    smooth = [np.ones(nq, bool)]
    inv_mask = np.ones(nT, bool)  # which vertices negate in the "Inverted" key

    if block:
        # Diorama slab: cream walls dropped from the terrain edge to a flat base plate. The wall tops are copies of the
        # edge vertices, so they follow the surface when the shape key moves.
        p = perimeter(ny, nx)
        P = len(p)
        top = co[p].copy()  # duplicated so the walls do not share normals with the terrain
        bot = top.copy()
        bot[:, 2] = base_z
        co = np.concatenate([co, top, bot])
        inv_mask = np.concatenate([inv_mask, np.ones(P, bool), np.zeros(P, bool)])
        t0, b0 = nT, nT + P
        a = np.arange(P)
        b = (a + 1) % P
        wall = np.stack([t0 + a, t0 + b, b0 + b, b0 + a], axis=-1).reshape(-1)
        base = b0 + np.arange(P)
        # Water wall on its own vertices, pushed 0.06% outward so it never lies exactly on the cream cut wall.
        # Lower edge = copy of the terrain's perimeter (same z in both shape keys, so it tracks the terrain exactly);
        # upper edge fixed at sea level. Where the terrain is above sea level the face lies above Z=eps and the shader
        # makes it transparent.
        push = 1.0006
        e0 = len(co)
        eco = top.copy()
        eco[:, :2] *= push
        eco[:, 2] = WATER_EPS
        wco = top.copy()
        wco[:, :2] *= push
        w0 = e0 + P
        co = np.concatenate([co, eco, wco])
        inv_mask = np.concatenate([inv_mask, np.zeros(P, bool), np.ones(P, bool)])
        wwall = np.stack([e0 + a, e0 + b, w0 + b, w0 + a], axis=-1).reshape(-1)
        off = 4 * nq
        loops += [wall, base, wwall]
        starts += [off + np.arange(0, 4 * P, 4), np.array([off + 4 * P]), off + 4 * P + P + np.arange(0, 4 * P, 4)]
        lengths += [np.full(P, 4), np.array([P]), np.full(P, 4)]
        mat += [np.ones(P + 1, np.int32), np.full(P, 2, np.int32)]
        smooth += [np.zeros(P + 1, bool), np.zeros(P, bool)]

    mesh = bpy.data.meshes.new("Terrain")
    mesh.vertices.add(len(co))
    mesh.vertices.foreach_set("co", co.ravel())
    set_polys(mesh, np.concatenate(loops), np.concatenate(starts), np.concatenate(lengths),
              np.concatenate(mat), np.concatenate(smooth))
    mesh.update(calc_edges=True)
    mesh.validate()

    # Per-vertex "is this real survey data" flag, usable in shaders (--flag-fill); 1 on the block walls.
    for name, arr in (("surveyed", surveyed.astype(np.float32).ravel()),):
        attr = mesh.attributes.new(name, "FLOAT", "POINT")
        full = np.ones(len(co), np.float32)
        full[:nT] = arr
        attr.data.foreach_set("value", full)

    obj = bpy.data.objects.new("Terrain", mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj, co, inv_mask


def add_terrain_keys(obj, co, inv_mask, state, morph):
    """Basis = the terrain as it is; 'Inverted' = the same vertices with Z negated (about sea level, Z = 0).
    Key value 0 -> original, 1 -> inverted, 0.5 -> perfectly flat. With --morph the value is keyframed 0 -> 1 -> 0."""
    obj.shape_key_add(name="Basis")  # original terrain
    inv = co.copy()
    inv[inv_mask, 2] *= -1.0
    key = obj.shape_key_add(name="Inverted", from_mix=False)
    key.data.foreach_set("co", inv.ravel())
    key.value = 1.0 if state == "inverted" else 0.0
    if morph:
        sc = bpy.context.scene
        sc.frame_start, sc.frame_end = 1, 150
        for frame, val in MORPH_KEYS:
            key.value = val
            key.keyframe_insert("value", frame=frame)
    return key


def build_water(width_km, height_km):
    """Water surface: one flat quad at sea level. (The water you see in the block's side walls is part of the
    terrain mesh, see build_terrain.)"""
    w, h = width_km / 2, height_km / 2
    co = np.array([[-w, -h, WATER_EPS], [w, -h, WATER_EPS], [w, h, WATER_EPS], [-w, h, WATER_EPS]], np.float32)
    mesh = bpy.data.meshes.new("Water")
    mesh.vertices.add(4)
    mesh.vertices.foreach_set("co", co.ravel())
    set_polys(mesh, np.array([0, 1, 2, 3]), np.array([0]), np.array([4]))
    mesh.update(calc_edges=True)
    obj = bpy.data.objects.new("Water", mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


# --------------------------------------------------------------------------- materials
def terrain_material(ve, cell_m, args, obj=None):
    """One material for the whole surface. Everything is decided from the height of the surface AS DISPLAYED
    (object-space Z), so the look follows the shape through the morph: above 0 it is land, below 0 it is seabed."""
    mat = new_material("Terrain")
    nt = mat.node_tree
    S = Shader(nt)
    out = S.node("ShaderNodeOutputMaterial")
    bsdf = S.node("ShaderNodeBsdfPrincipled")
    tc = S.node("ShaderNodeTexCoord")
    geo = S.node("ShaderNodeNewGeometry")

    _, _, zkm = S.xyz(tc.outputs["Object"])  # real height of the DISPLAYED surface, km (object space, before VE)
    zm = S.math("MULTIPLY", zkm, 1000.0)
    # land/sea switch. Crisp at the end states; around the flat midpoint of the morph the transition widens (driven by the
    # shape key) so the look dissolves instead of popping when every cell crosses sea level together.
    flat = S.node("ShaderNodeValue")
    flat.label = "flatness (driven by shape key)"
    keyblocks = obj.data.shape_keys if obj is not None else None
    if keyblocks is not None and "Inverted" in keyblocks.key_blocks:
        fcu = flat.outputs[0].driver_add("default_value")
        drv = fcu.driver
        drv.type = "SCRIPTED"
        var = drv.variables.new()
        var.name = "v"
        var.type = "SINGLE_PROP"
        var.targets[0].id_type = "KEY"
        var.targets[0].id = keyblocks
        var.targets[0].data_path = 'key_blocks["Inverted"].value'
        drv.expression = "1 - abs(1 - 2 * v)"
    f3 = S.math("MULTIPLY", S.math("MULTIPLY", flat.outputs[0], flat.outputs[0]), flat.outputs[0])
    width = S.math("ADD", S.math("MULTIPLY", f3, 4000.0), 6.0)
    is_sea = S.mrange(zm, width, S.math("MULTIPLY", width, -1.0), 0.0, 1.0)
    elev = S.math("MAXIMUM", zm, 0.0)
    depth = S.math("MAXIMUM", S.math("MULTIPLY", zm, -1.0), 0.0)

    # slope of the real surface (undo the vertical exaggeration baked into the world normal)
    _, _, nz = S.xyz(geo.outputs["Normal"])
    nzc = S.math("MAXIMUM", nz, 0.05)
    slope_ve = S.math("DIVIDE", S.math("SQRT", S.math("SUBTRACT", 1.0, S.math("MULTIPLY", nz, nz), clamp=False)), nzc)
    slope = S.math("DIVIDE", slope_ve, max(ve, 1e-3))

    # ---- land ----
    noise = S.node("ShaderNodeTexNoise", noise_dimensions="3D")
    noise.inputs["Scale"].default_value = 7.0  # per km
    noise.inputs["Detail"].default_value = 8.0
    noise.inputs["Roughness"].default_value = 0.6
    S.nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    noise2 = S.node("ShaderNodeTexNoise", noise_dimensions="3D")
    noise2.inputs["Scale"].default_value = 0.5
    noise2.inputs["Detail"].default_value = 3.0
    S.nt.links.new(tc.outputs["Object"], noise2.inputs["Vector"])
    land = S.ramp(S.math("ADD", elev, S.math("MULTIPLY", S.math("SUBTRACT", noise2.outputs["Fac"], 0.5), 500.0)), LAND, 0, 3600)
    land = S.mix(0.55, land, noise.outputs["Fac"], blend="MULTIPLY")  # fine grain
    rock = S.mrange(slope, 0.35, 0.85)
    land = S.mix(rock, land, rgba(ROCK))
    snow = S.mrange(S.math("ADD", elev, S.math("MULTIPLY", S.math("SUBTRACT", noise.outputs["Fac"], 0.5), 350.0)), 3100.0, 3800.0)
    land = S.mix(S.math("MULTIPLY", S.math("MULTIPLY", snow, 0.8), S.math("SUBTRACT", 1.0, S.math("MULTIPLY", rock, 0.6))), land, rgba(SNOW))

    # ---- seabed seen through water ----
    sea = S.ramp(depth, SEA, 0, 3500)
    if args.flag_fill:
        sv = S.node("ShaderNodeAttribute", attribute_type="GEOMETRY", attribute_name="surveyed")
        unsurveyed = S.math("SUBTRACT", 1.0, sv.outputs["Fac"], clamp=True)
        sea = S.mix(S.math("MULTIPLY", unsurveyed, 0.6), sea, rgba("#a9b9c6"))
    if args.isobath > 0:
        width_m = args.isobath_width or cell_m
        floor_slope = S.math("MAXIMUM", slope, 0.03)

        def lines(interval, wmul):
            t = S.math("FRACT", S.math("DIVIDE", depth, interval))
            d = S.math("MULTIPLY", S.math("MINIMUM", t, S.math("SUBTRACT", 1.0, t)), interval)  # metres to nearest isobath
            we = S.math("MULTIPLY", floor_slope, width_m * wmul)
            return S.mrange(d, S.math("MULTIPLY", we, 0.5), we, 1.0, 0.0)

        minor = S.math("MULTIPLY", lines(args.isobath, 1.0), 0.32)
        major = S.math("MULTIPLY", lines(args.isobath * 4, 1.8), 0.75)
        off_shore = S.mrange(depth, 8.0, 40.0)  # no lines right on the beach
        line = S.math("MULTIPLY", S.math("MAXIMUM", minor, major), off_shore)
        sea = S.mix(line, sea, rgba(ISOBATH_COLOR))

    base = S.mix(is_sea, land, sea)
    shore = S.mrange(S.math("ABSOLUTE", zm), 0.0, 14.0, 0.55, 0.0)  # thin surf line at the datum
    base = S.mix(shore, base, rgba(FOAM))

    rough = S.math("SUBTRACT", 0.95, S.math("MULTIPLY", is_sea, 0.2))
    nt.links.new(base, bsdf.inputs["Base Color"])
    nt.links.new(rough, bsdf.inputs["Roughness"])
    for name in ("Specular IOR Level", "Specular"):
        if name in bsdf.inputs:
            bsdf.inputs[name].default_value = 0.15
            break
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def wall_material():
    mat = new_material("Walls")
    nt = mat.node_tree
    S = Shader(nt)
    out, bsdf = S.node("ShaderNodeOutputMaterial"), S.node("ShaderNodeBsdfPrincipled")
    tc = S.node("ShaderNodeTexCoord")
    _, _, zkm = S.xyz(tc.outputs["Object"])
    zm = S.math("MULTIPLY", zkm, 1000.0)
    sea_line = S.mrange(S.math("ABSOLUTE", zm), 6.0, 22.0, 1.0, 0.0)  # dark line at sea level on the cut walls
    col = S.mix(sea_line, WALL_COLOR, rgba("#20495e"))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.9
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def water_material(wall=False):
    mat = new_material("WaterWall" if wall else "Water")
    nt = mat.node_tree
    S = Shader(nt)
    out, bsdf = S.node("ShaderNodeOutputMaterial"), S.node("ShaderNodeBsdfPrincipled")
    tc = S.node("ShaderNodeTexCoord")
    noise = S.node("ShaderNodeTexNoise", noise_dimensions="3D")
    noise.inputs["Scale"].default_value = 6.0
    noise.inputs["Detail"].default_value = 6.0
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    bump = S.node("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.04
    bump.inputs["Distance"].default_value = 0.01
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    bsdf.inputs["Base Color"].default_value = WATER_COLOR
    bsdf.inputs["Roughness"].default_value = 0.04
    bsdf.inputs["IOR"].default_value = 1.33
    bsdf.inputs["Alpha"].default_value = 0.30
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    if wall:  # fully transparent above sea level (object-space Z, km), water below it
        _, _, zkm = S.xyz(tc.outputs["Object"])
        below = S.math("LESS_THAN", zkm, WATER_EPS * 0.9)
        clear = S.node("ShaderNodeBsdfTransparent")
        mixsh = S.node("ShaderNodeMixShader")
        nt.links.new(below, mixsh.inputs[0])
        nt.links.new(clear.outputs["BSDF"], mixsh.inputs[1])
        nt.links.new(bsdf.outputs["BSDF"], mixsh.inputs[2])
        nt.links.new(mixsh.outputs["Shader"], out.inputs["Surface"])
    else:
        nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    if hasattr(mat, "blend_method"):  # Blender < 4.2 Eevee
        try:
            mat.blend_method = "BLEND"
        except (AttributeError, TypeError):
            pass
    return mat


# --------------------------------------------------------------------------- scene
def add_sun_and_sky(az_deg, alt_deg, parent=None):
    az, alt = math.radians(az_deg), math.radians(alt_deg)
    to_sun = Vector((math.sin(az) * math.cos(alt), math.cos(az) * math.cos(alt), math.sin(alt)))
    light = bpy.data.lights.new("Sun", "SUN")
    light.energy = 4.5
    light.angle = math.radians(1.2)
    light.color = (1.0, 0.88, 0.74)  # warm key
    obj = bpy.data.objects.new("Sun", light)
    obj.rotation_euler = (-to_sun).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.collection.objects.link(obj)
    if parent is not None:
        obj.parent = parent

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    S = Shader(nt)
    tc = S.node("ShaderNodeTexCoord")
    _, _, zdir = S.xyz(tc.outputs["Generated"])
    sky = S.ramp(S.mrange(zdir, 0.45, 0.95, 0.0, 1.0, smooth=False), [(0, SKY_HORIZON), (1000, SKY_ZENITH)], 0, 1000)
    bg = S.node("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = 0.9
    nt.links.new(sky, bg.inputs["Color"])
    wout = S.node("ShaderNodeOutputWorld")
    nt.links.new(bg.outputs["Background"], wout.inputs["Surface"])
    bpy.context.scene.world = world


def add_camera(width_km, height_km, aspect_wh, tilt_deg, cam_start, cam_end, morph):
    """Camera on an orbit rig. Rig rotation tracks the morph so 'flat' (key = 0.5) is halfway round."""
    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens = 50
    cam_data.sensor_fit = "HORIZONTAL"
    cam_data.clip_start, cam_data.clip_end = 0.1, 4000
    cam = bpy.data.objects.new("Camera", cam_data)
    rig = bpy.data.objects.new("CameraRig", None)
    sc = bpy.context.scene
    sc.collection.objects.link(rig)
    sc.collection.objects.link(cam)
    cam.parent = rig
    add_camera.rig = rig
    radius = 0.5 * math.hypot(width_km, height_km)  # must fit at every orbit angle
    hfov = 2 * math.atan(18.0 / cam_data.lens)
    dist = 1.06 * radius / math.tan(hfov / 2)
    el = math.radians(tilt_deg)
    cam.location = (0.0, -dist * math.cos(el), dist * math.sin(el))
    cam.rotation_euler = (math.radians(90) - el, 0.0, 0.0)  # looks at the rig origin

    def rig_z(bearing):  # camera at compass bearing b -> rig rotation 180 - b
        return math.radians(180.0 - bearing)

    rig.rotation_euler = (0.0, 0.0, rig_z(cam_start))
    if morph and cam_end is not None:
        for frame, val in MORPH_KEYS:
            rig.rotation_euler[2] = rig_z(cam_start + (cam_end - cam_start) * val)
            rig.keyframe_insert("rotation_euler", index=2, frame=frame)
    elif cam_end is not None:
        rig.rotation_euler[2] = rig_z(cam_end)
    sc.camera = cam


def pick_engine(want):
    sc = bpy.context.scene
    if want == "cycles":
        sc.render.engine = "CYCLES"
        return
    items = [i.identifier for i in sc.render.bl_rna.properties["engine"].enum_items]
    sc.render.engine = next((i for i in items if i.startswith("BLENDER_EEVEE")), "CYCLES")


def main():
    args = parse_args()
    # 1. Load the elevation grid and thin it out if it is too big for a comfortable mesh.
    # 2. Build terrain + shape keys + materials + water. 3. Light, camera, render settings. 4. Save (and render).
    bpy.ops.wm.read_factory_settings(use_empty=True)

    d = np.load(args.npz)
    elev = d["elev"].astype(np.float32)
    surveyed = d["surveyed"].astype(np.float32) if "surveyed" in d else np.ones_like(elev)
    cell = float(d["cell"])
    if args.square:
        ny0, nx0 = elev.shape
        side = min(ny0, nx0)
        if nx0 > side:
            x0 = int(round((nx0 - side) * args.square_offset))
            elev, surveyed = elev[:, x0:x0 + side], surveyed[:, x0:x0 + side]
        else:
            y0 = int(round((ny0 - side) * 0.5))
            elev, surveyed = elev[y0:y0 + side], surveyed[y0:y0 + side]
        print(f"Square crop: {side * cell / 1000:.0f} km, offset {args.square_offset}")
    f = max(1, math.ceil(math.sqrt(elev.shape[0] * elev.shape[1] / args.max_verts)))
    elev, surveyed, cell = block_mean(elev, f), block_mean(surveyed, f), cell * f
    ny, nx = elev.shape
    width_km, height_km = nx * cell / 1000, ny * cell / 1000
    print(f"Mesh: {nx} x {ny} = {nx * ny / 1e6:.2f} M vertices, {cell:g} m cells (block factor {f}), "
          f"{width_km:.0f} x {height_km:.0f} km, relief {elev.min():.0f} to {elev.max():.0f} m")

    base_z = -(max(abs(float(elev.min())), abs(float(elev.max()))) / 1000.0) * 1.03 - 0.15
    obj, co, inv_mask = build_terrain(elev, surveyed, cell, args.block, base_z)
    add_terrain_keys(obj, co, inv_mask, "original" if args.morph else args.state, args.morph)
    obj.data.materials.append(terrain_material(args.ve, cell, args, obj))
    if args.block:
        obj.data.materials.append(wall_material())
    obj.scale.z = args.ve
    obj["vertical_exaggeration"] = args.ve
    obj["note"] = "1 BU = 1 km. Basis = original terrain; shape key 'Inverted' = Z negated about sea level."

    if not args.no_water:
        wobj = build_water(width_km, height_km)
        wobj.data.materials.append(water_material())
        wobj.scale.z = args.ve
        wobj.visible_shadow = False  # the sun reaches the seabed through the water
        if args.block:
            obj.data.materials.append(water_material(wall=True))

    add_camera(width_km, height_km, None, args.tilt, args.cam_start, args.cam_end, args.morph)
    add_sun_and_sky(args.sun_az, args.sun_alt, add_camera.rig if args.sun_follow else None)

    sc = bpy.context.scene
    aw, ah = (float(v) for v in args.aspect.split(":"))
    sc.render.resolution_x, sc.render.resolution_y = args.width, int(round(args.width * ah / aw))
    pick_engine(args.engine)
    if sc.render.engine == "CYCLES":
        sc.cycles.samples = args.samples
        sc.cycles.use_denoising = True
    sc.view_settings.view_transform = "Standard"

    out = str(Path(args.out).resolve())
    bpy.ops.wm.save_as_mainfile(filepath=out)
    print(f"Saved {out}")
    if args.render_anim:
        outdir = Path(args.render_anim).resolve()
        outdir.mkdir(parents=True, exist_ok=True)
        sc.render.image_settings.file_format = "PNG"
        if args.frames and "," in args.frames:
            frames = [int(x) for x in args.frames.split(",")]
        elif args.frames and "-" not in args.frames:
            frames = [int(args.frames)]
        elif args.frames:
            a, b = (int(x) for x in args.frames.split("-"))
            frames = list(range(a, b + 1, max(1, args.step)))
        else:
            frames = list(range(sc.frame_start, sc.frame_end, max(1, args.step)))  # last frame = first, so omit it for a clean loop
        for fr in frames:
            sc.frame_set(fr)
            sc.render.filepath = str(outdir / f"frame_{fr:04d}.png")
            bpy.ops.render.render(write_still=True)
        print(f"Rendered {len(frames)} frames to {outdir}; encode with: ffmpeg -framerate 30 -i frame_%04d.png (with --step N use -framerate 30/N) -c:v libx264 -pix_fmt yuv420p morph.mp4")
    if args.render:
        sc.render.filepath = str(Path(args.render).resolve())
        sc.render.image_settings.file_format = "PNG"
        bpy.ops.render.render(write_still=True)
        print(f"Rendered {sc.render.filepath}")


main()
