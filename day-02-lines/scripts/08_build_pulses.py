"""Loopable variant: the whole network on, light running downstream. Two modes:
  MODE = "drips"  (default) each river piece carries its own train of comet-shaped drips,
                  at a random phase, at a speed set by stream order
  MODE = "ants"   one global pattern of beads tied to distance to the sea, so beads on
                  tributaries arrive in step with the main stem

    blender -b -P site/day-02-lines/scripts/08_build_pulses.py

Run from the workspace root after 07_build_scene.py. Opens work/blender/day-02-rhone.blend
read-only and saves a NEW file, work/blender/day-02-rhone-pulses.blend, so the drawing-in
animation is untouched. Same terrain, lakes, light, camera and render settings.

What changes:
  - the clock is frozen at the end of the drawing-in animation: every river and lake is on
  - each curve point stores its clock time (t0 + position along the piece * (t1 - t0)),
    which is D_max minus its network distance to the sea
  - the river shader adds beads where fract((t_point - SPEED * f) / SPACING) is near 0.5,
    so beads move downstream at one constant speed. Because the clock is continuous
    across confluences, tributary beads arrive in step with the main stem
  - lakes carry the beads across as bands: each lake pixel already has a clock time from
    the fill front (lake_time.png), so the same formula on that time gives bands that
    enter with the inflowing river and leave with the outflow, in step
  - after LOOP frames the beads have moved exactly one SPACING, so frame LOOP + 1 equals
    frame 1 and the clip loops without a seam

Drips: position along each piece (km from its upstream end) instead of the global clock,
a random phase per piece so streams are out of step, and a speed tier per Strahler order.
Each tier moves a whole number of spacings per loop, so the loop stays seamless. Speeds run
from 1x (first-order streams) to 3x (orders 6 and 7), close to the 2 to 3x rise in mean
velocity that downstream hydraulic geometry gives over this range of discharge (v ~ Q^0.1,
Leopold and Maddock 1953). Each drip has a bright head and a fading tail upstream of it.
"""
import bpy, json, os
import numpy as np

ROOT = os.getcwd()
SRC = os.path.join(ROOT, "work/blender/day-02-rhone.blend")
DST = os.path.join(ROOT, "work/blender/day-02-rhone-pulses.blend")
DATA = os.path.join(ROOT, "work/data/day-02-lines/blender")

SPACING = 25.0     # network km between beads
LOOP = 120         # frames per loop (4 s at 30 fps)
BEAD = 0.22        # bead length as a fraction of SPACING
BASE = 0.30        # dim strength of the always-on network
BASE_W = 0.6       # ... plus this times the accumulation weight
PULSE = 3.0        # bead strength
PULSE_W = 10.0     # ... plus this times the accumulation weight
LAKE_BASE = 0.22   # lake surface strength between bands (was 0.6 once filled), dimmer so bands read
LAKE_PULSE = 1.8   # extra strength in a band crossing the lake
MODE = "drips"
DRIP_SPACING = 20.0                                    # km between drips on one piece
TIERS = {1: 1, 2: 1, 3: 2, 4: 2, 5: 2, 6: 3, 7: 3}     # Strahler order -> spacings per loop
TAIL = 0.30        # drip length (head plus tail) as a fraction of DRIP_SPACING
SEED = 2

D_MAX = json.load(open(os.path.join(DATA, "meta.json")))["d_max_km"]
FULL = D_MAX + 1.0

bpy.ops.wm.open_mainfile(filepath=SRC)
scene = bpy.context.scene

# ---------------------------------------------------------------- freeze the clock: everything on
rivers = bpy.data.objects["Rivers"]
rt = bpy.data.node_groups["Rivers"]
sock = {it.name: it.identifier for it in rt.interface.items_tree if it.in_out == "INPUT"}
path = f'modifiers["Rivers"]["{sock["Clock"]}"]'
rivers.driver_remove(path)
rivers.modifiers["Rivers"][sock["Clock"]] = FULL

lake_mat = bpy.data.materials["Lake"]
clk = next(n for n in lake_mat.node_tree.nodes if n.type == "VALUE" and n.label == "Clock")
clk.outputs[0].driver_remove("default_value")
clk.outputs[0].default_value = FULL

# ---------------------------------------------------------------- per-piece speed tier and random phase
r = np.load(os.path.join(DATA, "rivers.npz"))
cv = rivers.data
assert len(cv.curves) == len(r["strahler"])
tier = np.array([TIERS[int(o)] for o in r["strahler"]], "float32")
rnd = np.random.default_rng(SEED).random(len(tier)).astype("float32")
for name, vals in (("tier", tier), ("rnd", rnd)):
    a = cv.attributes.get(name) or cv.attributes.new(name, "FLOAT", "CURVE")
    a.data.foreach_set("value", vals)

# ---------------------------------------------------------------- store each point's clock time
nodes, links = rt.nodes, rt.links
def node(kind, x, y, **kw):
    n = nodes.new(kind)
    n.location = (x, y)
    for k, v in kw.items():
        setattr(n, k, v)
    return n

def named(name, x, y):
    a = node("GeometryNodeInputNamedAttribute", x, y, data_type="FLOAT")
    a.inputs["Name"].default_value = name
    return a.outputs["Attribute"]

sg = next(n for n in nodes if n.bl_idname == "GeometryNodeStoreNamedAttribute"
          and n.inputs["Name"].default_value == "glow")
c2m = next(n for n in nodes if n.bl_idname == "GeometryNodeCurveToMesh")
par = node("GeometryNodeSplineParameter", 600, -900)
t0, t1 = named("t0", 600, -1000), named("t1", 600, -1100)
span = node("ShaderNodeMath", 800, -1050, operation="SUBTRACT")
links.new(t1, span.inputs[0]); links.new(t0, span.inputs[1])
tp = node("ShaderNodeMath", 1000, -950, operation="MULTIPLY_ADD")
links.new(par.outputs["Factor"], tp.inputs[0])
links.new(span.outputs[0], tp.inputs[1])
links.new(t0, tp.inputs[2])
st = node("GeometryNodeStoreNamedAttribute", 900, 150, data_type="FLOAT", domain="POINT")
st.inputs["Name"].default_value = "tpt"
links.new(sg.outputs[0], st.inputs["Geometry"])
links.new(tp.outputs[0], st.inputs["Value"])
sl = node("ShaderNodeMath", 1000, -1200, operation="MULTIPLY")      # km from the piece's upstream end
links.new(par.outputs["Factor"], sl.inputs[0])
links.new(span.outputs[0], sl.inputs[1])
st2 = node("GeometryNodeStoreNamedAttribute", 1000, 150, data_type="FLOAT", domain="POINT")
st2.inputs["Name"].default_value = "sloc"
links.new(st.outputs[0], st2.inputs["Geometry"])
links.new(sl.outputs[0], st2.inputs["Value"])
links.new(st2.outputs[0], c2m.inputs["Curve"])

# ---------------------------------------------------------------- river shader: base + beads
mr = bpy.data.materials["River"]
N, L = mr.node_tree.nodes, mr.node_tree.links
for n in list(N):
    if n.type != "OUTPUT_MATERIAL":
        N.remove(n)
out = next(n for n in N if n.type == "OUTPUT_MATERIAL")

def sn(kind, x, y, **kw):
    n = N.new(kind)
    n.location = (x, y)
    for k, v in kw.items():
        setattr(n, k, v)
    return n

def m(op, a, b=None, x=0, y=0, c=None):
    n = sn("ShaderNodeMath", x, y, operation=op)
    for i, v in enumerate([a, b, c]):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            n.inputs[i].default_value = v
        else:
            L.new(v, n.inputs[i])
    return n.outputs[0]

tpt = sn("ShaderNodeAttribute", -1400, 0, attribute_name="tpt").outputs["Fac"]
w = sn("ShaderNodeAttribute", -1400, -300, attribute_name="glow").outputs["Fac"]
f = sn("ShaderNodeValue", -1400, 200, label="Frame")
fc = f.outputs[0].driver_add("default_value")
fc.driver.type = "SCRIPTED"
fc.driver.expression = f"(frame - 1) % {LOOP}"
if MODE == "ants":
    shift = m("MULTIPLY", f.outputs[0], SPACING / LOOP, x=-1200, y=200)          # km moved so far
    phase = m("FRACT", m("DIVIDE", m("SUBTRACT", tpt, shift, x=-1000, y=100), SPACING, x=-850, y=100), x=-700, y=100)
    dist = m("ABSOLUTE", m("SUBTRACT", phase, 0.5, x=-550, y=100), x=-400, y=100)  # 0 at the bead centre
    bead = sn("ShaderNodeMapRange", -250, 100, interpolation_type="SMOOTHSTEP")
    L.new(dist, bead.inputs["Value"])
    bead.inputs["From Min"].default_value, bead.inputs["From Max"].default_value = BEAD / 2, 0.0
else:
    sloc = sn("ShaderNodeAttribute", -1600, 100, attribute_name="sloc").outputs["Fac"]
    tr = sn("ShaderNodeAttribute", -1600, 300, attribute_name="tier").outputs["Fac"]
    rn = sn("ShaderNodeAttribute", -1600, 450, attribute_name="rnd").outputs["Fac"]
    # cycles moved so far = tier * frame / LOOP; phase rises downstream, so the head sits at phase 1
    moved = m("MULTIPLY", tr, m("DIVIDE", f.outputs[0], LOOP, x=-1300, y=250), x=-1150, y=250)
    phase = m("FRACT", m("ADD", m("SUBTRACT", m("DIVIDE", sloc, DRIP_SPACING, x=-1300, y=100),
                                       moved, x=-1000, y=100), rn, x=-850, y=100), x=-700, y=100)
    tail = sn("ShaderNodeMapRange", -500, 100)                 # 0 at the tail end, 1 at the head
    L.new(phase, tail.inputs["Value"])
    tail.inputs["From Min"].default_value, tail.inputs["From Max"].default_value = 1 - TAIL, 1.0
    tail.clamp = True
    shaped = m("POWER", tail.outputs[0], 3.0, x=-350, y=100)  # sharp head, long fading tail
    bead = shaped.node
base = m("MULTIPLY_ADD", w, BASE_W, x=-250, y=-250, c=BASE)
pulse = m("MULTIPLY_ADD", w, PULSE_W, x=-250, y=-100, c=PULSE)
strength = m("MULTIPLY_ADD", bead.outputs[0], pulse, x=0, y=0, c=base)
em = sn("ShaderNodeEmission", 200, 0)
em.inputs["Color"].default_value = (0.20, 0.95, 0.85, 1)
L.new(strength, em.inputs["Strength"])
L.new(em.outputs[0], out.inputs["Surface"])

# ---------------------------------------------------------------- lakes: bands in step with the beads
K = lake_mat.node_tree
KN, KL = K.nodes, K.links
tex = next(n for n in KN if n.type == "TEX_IMAGE")
tpx = next(l.to_node for l in tex.outputs["Color"].links if l.to_node.type == "MATH").outputs[0]
emis = next(n for n in KN if n.type == "EMISSION")
for l in list(emis.inputs["Strength"].links):
    KL.remove(l)

def km(op, a, b=None, x=0, y=0, c=None):
    n = KN.new("ShaderNodeMath")
    n.location = (x, y)
    n.operation = op
    for i, v in enumerate([a, b, c]):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            n.inputs[i].default_value = v
        else:
            KL.new(v, n.inputs[i])
    return n.outputs[0]

lf = KN.new("ShaderNodeValue")
lf.location, lf.label = (-1000, -700), "Frame"
fc = lf.outputs[0].driver_add("default_value")
fc.driver.type = "SCRIPTED"
fc.driver.expression = f"(frame - 1) % {LOOP}"
lshift = km("MULTIPLY", lf.outputs[0], SPACING / LOOP, x=-800, y=-700)
lphase = km("FRACT", km("DIVIDE", km("SUBTRACT", tpx, lshift, x=-650, y=-600), SPACING, x=-500, y=-600), x=-350, y=-600)
ldist = km("ABSOLUTE", km("SUBTRACT", lphase, 0.5, x=-200, y=-600), x=-50, y=-600)
lbead = KN.new("ShaderNodeMapRange")
lbead.location, lbead.interpolation_type = (100, -600), "SMOOTHSTEP"
KL.new(ldist, lbead.inputs["Value"])
lbead.inputs["From Min"].default_value, lbead.inputs["From Max"].default_value = BEAD / 2, 0.0
lbead.inputs["To Min"].default_value, lbead.inputs["To Max"].default_value = LAKE_BASE, LAKE_BASE + LAKE_PULSE
KL.new(lbead.outputs[0], emis.inputs["Strength"])

# ---------------------------------------------------------------- frames and output
scene.frame_start, scene.frame_end = 1, LOOP
# PNG frames, not MP4: a clean source for ffmpeg (GIF palette, looped MP4)
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGB"
scene.render.image_settings.color_depth = "8"
scene.render.filepath = "//../renders/day-02-pulses/frame_"
bpy.ops.wm.save_as_mainfile(filepath=DST, relative_remap=True)
print("saved", DST)
