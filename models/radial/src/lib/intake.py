"""Intake: nine swan-neck intake pipes from the blower outlets to the heads, their
rubber hose couplings, band clamps and union nuts, and the updraft carburettor
under the rear of the blower section.

INTERFACES (read from the owners' modules; mirrored here, never imported)
  * blower outlet k: in-plane b_k = ALPHA(k) - 12, axis radial tilted 25 deg
    FORWARD, crossing the drum at (r 252, y 172); machined slip spigot OD 56 /
    bore 48 from s 24 to s 44 along that axis (end face centre r 291.9,
    y 153.4), hose bead O59 at s 27.5..30.
  * head intake stub (cylinder-1 local t, y, h): axis (t 80, h 468) along +y,
    flange O72 y 96..110, stub OD 56 to y 124 with its thread crest R 29.2 at
    y 118..120.
  * carburettor pad: face z -300 (normal -Z), x +-62, y 212..262, throat
    88 x 26, 4 x M8 studs (+-53, 218 | 256), 20 proud (blower's studs).

THE PIPE (cylinder-1 local, authored once, placed with geo.on_cylinder)
  The outlet leans 25 deg forward, the stub faces rearward, and the stub face
  (y 124) lies 30 mm forward of the outlet: the pipe must reverse its fore-aft
  travel. It does so as a swan neck: out of the hose along the outlet axis, a
  R 61 bend swings it up and rearward (heading 25 deg forward -> 54 deg aft),
  then a R 50 bend carries it over the top and forward into the stub (144 deg).
  Tangent-continuous throughout (two-arc solution sampled into one spline, the
  cylinder-row offset t blended by a Hermite cubic). OD 56, wall 1.5, polished
  aluminium; a brazed ferrule collar at the head end is held to the stub thread
  by a hex union nut. At the blower the pipe butts the spigot inside a rubber
  hose held by two band clamps.

  The y budget (stub face 124 .. outlet 153, rise 166) leaves no straight run
  for a second hose at the head: there the joint is the union nut alone.

CARBURETTOR (engine frame, authored directly)
  A period twin-barrel updraft float carburettor: cast adapter (pad flange,
  neck, lower flange) on the blower's four pad studs; the carburettor body
  (throttle body with twin O38 barrels, float chamber on the -X side with a
  screwed cover, drilled drain plug wired to a cast ear) on four studs under the
  adapter; throttle shaft across both barrels with two throttle plates visible
  from below, throttle lever with ball-end link stud; mixture-control shaft and
  lever; brass fuel-inlet fitting; machined air-scoop flange face at the bottom.

MUSEUM SECTION: cylinder 1's pipe, hose and clamps are cut by the section
cutter (geo.cut_with_skin, 0 < y < 340, r > 300): the pipe and hose end in an
annular section at r 300 showing the bore, its cut faces carried by red skins
`intake:section_skin_<part>`. Its union nut and outer clamp (seats inside the
removed region) are omitted.
"""

from __future__ import annotations

import math

from cadgen import build123d as bd

from lib import castings as C
from lib import fasteners as F
from lib import geo
from lib import palette as P
from lib import spec as S

MATERIALS = ("brass", "carb_alu", "fastener", "polished_alu", "rubber", "safety_wire", "section_red")

# ---------------------------------------------------------------------------
# Interfaces (see docstring)
# ---------------------------------------------------------------------------
OUT_OFF = -9.7             # outlet in-plane angle relative to its cylinder (radial axis)
OUT_R0, OUT_Y0 = 252.0, 200.0
SPIGOT_END_S = 44.0        # spigot end face at r 296
STUB_T, STUB_H = 80.0, 468.0
STUB_R = math.hypot(STUB_T, STUB_H)      # 474.8: the stub lies in the outlet's radial plane
STUB_END_Y = 124.0
PAD_Z = -300.0
PAD_STUDS = [(-53.0, 241.5), (53.0, 241.5), (-53.0, 282.5), (53.0, 282.5)]

# pipe run (radial distance r in the plane y = OUT_Y0)
PIPE_R, PIPE_WALL = 28.0, 1.5
R_ELBOW = 70.0                           # elbow centreline radius (1.25 D)
R_BEND0 = STUB_R - R_ELBOW               # 404.8: the elbow's bend starts here
PIPE_S0 = 45.0                           # pipe starts 1 mm past the spigot end
JOINT_R = 380.0                          # pipe / elbow joint under hose b
FERRULE_Y = (124.4, 126.6)
FERRULE_R = 29.2

# hoses + clamps (radial distance r)
HOSE_A = (OUT_R0 + 31.0, OUT_R0 + 51.0)      # short: pipe 6's coupling passes 3 mm from the carb pad
HOSE_B = (JOINT_R - 18.0, JOINT_R + 18.0)
HOSE_RI, HOSE_RO = 28.35, 31.5
CLAMP_R = (OUT_R0 + 35.5, OUT_R0 + 46.0, JOINT_R - 11.0, JOINT_R + 11.0)
CLAMP_W = 8.0
CLAMP_RI, CLAMP_RO = 31.6, 32.8

# union nut (cylinder-1 local y)
NUT_Y = (112.0, 129.5)
NUT_AF = 68.0
NUT_BORE_R = 29.45
NUT_LIP_Y = 127.0
NUT_LIP_R = 28.35


def V(*a):
    return bd.Vector(*a)


def _one(shape):
    sols = shape.solids()
    if len(sols) == 1:
        return sols[0]
    return max(sols, key=lambda s: s.volume)


def _rev_z(pts):
    """Closed (r, z) polygon revolved about +Z."""
    face = bd.make_face(bd.Polyline(*[V(r, 0.0, z) for r, z in pts], close=True).edges())
    return bd.revolve(face, axis=bd.Axis.Z)


# ---------------------------------------------------------------------------
# Outlet frame (cylinder-1 local: X = t, Y = y, Z = h)
# ---------------------------------------------------------------------------
_SB, _CB = math.sin(math.radians(-OUT_OFF)), math.cos(math.radians(-OUT_OFF))
U = (_SB, 0.0, _CB)                      # the radial run direction
HOUSING_X = (-_CB, 0.0, _SB)             # clamp screw housings face -t (away from the carb pad)


def rp(r, y=OUT_Y0):
    """Point at radial distance r on cylinder 1's intake plane, station y."""
    return (r * _SB, y, r * _CB)


def op(s):
    """Point on cylinder 1's outlet axis, s mm outward from the drum crossing."""
    return rp(OUT_R0 + s)


def _tube(r0, r1, ro=PIPE_R, ri=PIPE_R - PIPE_WALL):
    """Straight tube along the radial run from r0 to r1."""
    return F.place(_rev_z([(ri, 0.0), (ro, 0.0), (ro, r1 - r0), (ri, r1 - r0)]), rp(r0), U, HOUSING_X)


# ---------------------------------------------------------------------------
# Pipe (straight radial run) and elbow (one R 70 bend into the head stub)
# ---------------------------------------------------------------------------
def pipe_proto():
    return _one(_tube(OUT_R0 + PIPE_S0, JOINT_R - 1.0))


def elbow_proto():
    ri = PIPE_R - PIPE_WALL
    leg = _tube(JOINT_R + 1.0, R_BEND0)
    # the bend: the annulus at the bend start revolved 90 deg about the axis through
    # the bend centre (r R_BEND0, y OUT_Y0 - R_ELBOW), normal to the (U, Y) plane
    ann = bd.Plane(origin=V(*rp(R_BEND0)), x_dir=V(0, 1, 0), z_dir=V(*U)) * \
        (bd.Circle(PIPE_R) - bd.Circle(ri))
    c = rp(R_BEND0, OUT_Y0 - R_ELBOW)
    n = (_CB, 0.0, -_SB)                 # U x Y
    bend = None
    for sgn in (1.0, -1.0):
        b = bd.revolve(ann, axis=bd.Axis(V(*c), V(*n) * sgn), revolution_arc=90.0)
        if b.bounding_box().min.Y < OUT_Y0 - R_ELBOW + 1.0:
            bend = b
            break
    y_end = OUT_Y0 - R_ELBOW
    tail = geo.locate(_rev_z([(ri, FERRULE_Y[0]), (PIPE_R, FERRULE_Y[0]), (PIPE_R, y_end), (ri, y_end)]),
                      (STUB_T, 0.0, STUB_H), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0))
    fr = _rev_z([(ri, FERRULE_Y[0] + 0.4), (ri + 0.4, FERRULE_Y[0]),
                 (FERRULE_R - 0.4, FERRULE_Y[0]), (FERRULE_R, FERRULE_Y[0] + 0.4),
                 (FERRULE_R, FERRULE_Y[1] - 0.3), (FERRULE_R - 0.3, FERRULE_Y[1]),
                 (PIPE_R - 0.1, FERRULE_Y[1] + 0.25), (ri + 0.3, FERRULE_Y[1] + 0.25)])
    fr = geo.locate(fr, (STUB_T, 0.0, STUB_H), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0))
    return _one(leg.fuse(bend, tail, fr).clean())


# ---------------------------------------------------------------------------
# Hoses, clamps, union nut
# ---------------------------------------------------------------------------
def hose_proto(r0, r1):
    L = r1 - r0
    b = 1.6
    prof = [(HOSE_RI, 0.0), (HOSE_RO - b, 0.0), (HOSE_RO - 0.45 * b, 0.25 * b), (HOSE_RO, b),
            (HOSE_RO, L - b), (HOSE_RO - 0.45 * b, L - 0.25 * b), (HOSE_RO - b, L), (HOSE_RI, L)]
    return F.place(_rev_z(prof), rp(r0), U, HOUSING_X)


def _clamp_local():
    """Band clamp: local z = pipe axis, band centred on z = 0, the tangential
    screw housing on local +X (placed facing rearward)."""
    w = CLAMP_W
    band = _rev_z([(CLAMP_RI, -w / 2 + 0.3), (CLAMP_RI + 0.3, -w / 2), (CLAMP_RO - 0.3, -w / 2),
                   (CLAMP_RO, -w / 2 + 0.3), (CLAMP_RO, w / 2 - 0.3), (CLAMP_RO - 0.3, w / 2),
                   (CLAMP_RI + 0.3, w / 2), (CLAMP_RI, w / 2 - 0.3)])
    # housing: the band's two turned-up ears joined by a trunnion block
    blk = bd.Pos(CLAMP_RO + 3.2, 0.0, 0.0) * bd.Box(8.4, 17.0, w - 0.6)
    blk, _ = C.safe_fillet(blk, [e for e in blk.edges() if abs(e.tangent_at(0.5).Z) > 0.99], 2.2, min_r=0.5)
    gap = bd.Pos(CLAMP_RO + 3.2, 0.0, 0.0) * bd.Box(9.0, 2.2, w + 2.0)
    blk = blk - gap
    # screw along local Y through both ears: slotted fillister head on +Y, tail on -Y
    shank = geo.cyl_along((CLAMP_RO + 3.6, -11.5, 0.0), (CLAMP_RO + 3.6, 11.0, 0.0), 4.2)
    head = geo.cyl_along((CLAMP_RO + 3.6, 8.3, 0.0), (CLAMP_RO + 3.6, 12.6, 0.0), 7.6)
    slot = bd.Pos(CLAMP_RO + 3.6, 12.2, 0.0) * bd.Box(1.1, 1.2, 9.0)
    head = head - slot
    body = band.fuse(blk, shank, head).clean()
    return _one(body)


def clamp_protos():
    loc = _clamp_local()
    return [F.place(loc, rp(r), U, HOUSING_X) for r in CLAMP_R]


def union_nut_proto():
    y0, y1 = NUT_Y
    hexn = F._wrench_head(NUT_AF, y0, y1, chamfer_bottom=True, rotation=0.0)
    bore = _rev_z([(0.0, y0 - 1.0), (NUT_BORE_R + 0.8, y0 - 1.0), (NUT_BORE_R, y0 + 0.8),
                   (NUT_BORE_R, NUT_LIP_Y), (NUT_LIP_R, NUT_LIP_Y + 0.6), (NUT_LIP_R, y1 - 0.6),
                   (NUT_LIP_R + 0.6, y1 + 1.0), (0.0, y1 + 1.0)])
    # two spanner grooves round the hex waist: a period union nut reads as a fitting
    groove = _rev_z([(NUT_AF, 120.6), (NUT_AF / 2 - 0.9, 121.2), (NUT_AF / 2 - 0.9, 122.0), (NUT_AF, 122.6)])
    nut = _one(hexn - [bore, groove])
    # local z = +Y (rear); authored about the local z axis, placed on the stub axis
    return geo.locate(nut, (STUB_T, 0.0, STUB_H), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0))


# ---------------------------------------------------------------------------
# Carburettor (engine frame)
# ---------------------------------------------------------------------------
def _rrect(x0, x1, y0, y1, z0, z1, r):
    """Rounded-corner (in XY) box between z0 < z1."""
    sk = bd.RectangleRounded(x1 - x0, y1 - y0, r)
    return bd.Pos((x0 + x1) / 2, (y0 + y1) / 2, z0) * bd.extrude(sk, amount=z1 - z0)


def _cyl(p0, p1, d):
    return geo.cyl_along(p0, p1, d)


AD_TOP = (PAD_Z - 0.2, PAD_Z - 10.2)        # adapter pad flange z (top, bottom)
AD_BOT_NEW = (-408.0, -416.0)               # adapter lower flange (below the mount ring)
# The carburettor proper is authored in a compact local layout (its top face at
# z -336.2, barrels at y 237) and moved by CARB_SHIFT under the adapter: forward
# of the accessory sump, under the mount ring, clear of pipe 6 and the exhaust ring.
CARB_SHIFT = (0.0, 26.0, -80.0)
AD_BOT = (-326.0, -336.0)                   # (local layout) adapter lower flange
CARB_TOP = -336.2
CARB_FL = (CARB_TOP, -346.0)
BODY_Z = (-346.0, -396.0)
SCOOP_FL = (-396.0, -404.0)
BORES_X = (-21.0, 21.0)
BORE_D = 38.0
BORE_Y = 237.0
CARB_STUDS = [(-56.0, 218.0), (56.0, 218.0), (-56.0, 258.0), (56.0, 258.0)]
CARB_FL_Y = (210.0, 266.0)
THR_Z = -371.0
FC = (-48.0, 40.0, 174.0, 216.0, -356.0, -398.0)    # float chamber (on the FRONT face) x0,x1,y0,y1,ztop,zbot
FUEL_IN = (-37.0, 174.0, -377.0)            # on the chamber's front face, beside the cover
MIX = (-44.0, 250.0, -385.0)                # mixture shaft on the throttle body's -X face
DRAIN = (8.0, 195.0, FC[5] - 3.0)
EAR = (30.0, 195.0, -406.0)                 # drilled ear for the drain-plug safety wire (hole along X)


def _rr_face(x0, x1, y0, y1, z, r):
    return bd.Plane.XY.offset(z) * bd.Pos((x0 + x1) / 2, (y0 + y1) / 2) * bd.RectangleRounded(x1 - x0, y1 - y0, r)


def carb_adapter():
    """Cast adapter: pad flange on the blower's studs, a duct stepping forward of
    the accessory sump and dropping in front of the mount ring, and a lower flange
    carrying the carburettor below the ring."""
    zt, zb = AD_TOP[1], AD_BOT_NEW[0]
    top = _rrect(-62.0, 62.0, 236.0, 288.0, AD_TOP[1], AD_TOP[0], 6.0)
    up = bd.extrude(_rr_face(-42.0, 42.0, 238.0, 286.0, zt + 1.0, 10.0), amount=-11.0)
    trans = bd.loft([_rr_face(-42.0, 42.0, 238.0, 286.0, zt - 10.0, 10.0),
                     _rr_face(-46.0, 46.0, 238.0, 272.0, -352.0, 10.0)])
    down = bd.extrude(_rr_face(-46.0, 46.0, 238.0, 272.0, -352.0, 10.0), amount=zb - 1.0 + 352.0)
    bot = _rrect(-66.0, 66.0, CARB_FL_Y[0] + CARB_SHIFT[1], CARB_FL_Y[1] + CARB_SHIFT[1],
                 AD_BOT_NEW[1], AD_BOT_NEW[0], 7.0)
    body = _one(top.fuse(up, trans, down, bot).clean())
    a = bd.extrude(_rr_face(-37.0, 37.0, 244.0, 280.0, AD_TOP[0] + 1.0, 8.0), amount=-(1.0 + 10.0 + 11.0))
    b = bd.loft([_rr_face(-37.0, 37.0, 244.0, 280.0, zt - 10.0, 8.0),
                 _rr_face(-40.0, 40.0, 243.0, 267.0, -352.0, 8.0)])
    c = bd.extrude(_rr_face(-40.0, 40.0, 243.0, 267.0, -352.0, 8.0), amount=AD_BOT_NEW[1] - 1.0 + 352.0)
    air = _one(a.fuse(b, c).clean())
    holes = [_cyl((x, y, AD_TOP[0] + 1), (x, y, AD_TOP[1] - 1), 8.8) for x, y in PAD_STUDS]
    taps = [_cyl((x, y + CARB_SHIFT[1], AD_BOT_NEW[1] - 1), (x, y + CARB_SHIFT[1], AD_BOT_NEW[1] + 6.5),
                 2 * F._shank_radius(8.0) + 0.1) for x, y in CARB_STUDS]
    return _one(C.cut_all(body, [air] + holes + taps))


def carb_body():
    fl = _rrect(-66.0, 66.0, CARB_FL_Y[0], CARB_FL_Y[1], CARB_FL[1], CARB_FL[0], 7.0)
    main = _rrect(-44.0, 44.0, 214.0, 260.0, BODY_Z[1], BODY_Z[0] + 1.0, 9.0)
    scoop = _rrect(-48.0, 48.0, 212.0, 263.0, SCOOP_FL[1], SCOOP_FL[0] + 1.0, 8.0)
    x0, x1, y0, y1, zt, zb = FC
    fch = _rrect(x0, x1, y0, y1 + 2.0, zb, zt, 10.0)
    boss_r = _cyl((43.0, BORE_Y, THR_Z), (52.0, BORE_Y, THR_Z), 20.0)
    fuel_boss = _cyl((FUEL_IN[0], FUEL_IN[1] + 2.0, FUEL_IN[2]), (FUEL_IN[0], FUEL_IN[1] - 6.0, FUEL_IN[2]), 22.0)
    mix_boss = _cyl((MIX[0] + 2.0, MIX[1], MIX[2]), (MIX[0] - 6.0, MIX[1], MIX[2]), 16.0)
    ear = _cyl((EAR[0] - 3.0, EAR[1], EAR[2]), (EAR[0] + 3.0, EAR[1], EAR[2]), 9.0)
    ear_web = bd.Pos(EAR[0], EAR[1], (EAR[2] + zb) / 2 + 1.0) * bd.Box(6.0, 6.0, zb - EAR[2] + 2.0)
    drain_boss = _cyl((DRAIN[0], DRAIN[1], zb + 2.0), (DRAIN[0], DRAIN[1], DRAIN[2]), 22.0)
    body = _one(fl.fuse(main, scoop, fch, boss_r, fuel_boss, mix_boss, ear, ear_web, drain_boss).clean())
    tools = [_cyl((x, BORE_Y, SCOOP_FL[1] - 1.0), (x, BORE_Y, CARB_FL[0] + 1.0), BORE_D) for x in BORES_X]
    tools.append(_cyl((-40.0, BORE_Y, THR_Z), (53.0, BORE_Y, THR_Z), 8.2))     # throttle shaft bore
    tools += [_cyl((x, y, CARB_FL[0] + 1.0), (x, y, CARB_FL[1] - 1.0), 8.8) for x, y in CARB_STUDS]
    # scoop-flange tapped holes (blind, from below)
    for x in (-40.0, 0.0, 40.0):
        for y in (217.5, 257.5):
            tools.append(_cyl((x, y, SCOOP_FL[1] - 1.0), (x, y, SCOOP_FL[1] + 9.0), 5.0))
    # float-cover screw taps, drain tap, fuel-inlet tap, mixture-shaft bore, ear hole
    for p in _cover_screw_pts():
        tools.append(_cyl((p[0], p[1] + 1.0, p[2]), (p[0], p[1] + 12.0, p[2]), 2 * F._shank_radius(5.0) + 0.1))
    tools.append(_cyl((DRAIN[0], DRAIN[1], DRAIN[2] - 1.0), (DRAIN[0], DRAIN[1], DRAIN[2] + 13.0),
                      2 * F._shank_radius(10.0) + 0.1))
    tools.append(_cyl((FUEL_IN[0], FUEL_IN[1] - 7.0, FUEL_IN[2]), (FUEL_IN[0], FUEL_IN[1] + 10.0, FUEL_IN[2]), 12.2))
    tools.append(_cyl((MIX[0] - 7.0, MIX[1], MIX[2]), (MIX[0] + 5.0, MIX[1], MIX[2]), 7.2))
    tools.append(_cyl((EAR[0] - 4.0, EAR[1], EAR[2]), (EAR[0] + 4.0, EAR[1], EAR[2]), 2.2))
    return _one(C.cut_all(body, tools))


COVER = (-24.0, 34.0, 170.2, 174.0, -360.0, -394.0)   # x0, x1, y0 (front face), y1, ztop, zbot


def _cover_screw_pts():
    y = COVER[2]
    return [(x, y, z) for z in (-365.0, -377.0, -389.0) for x in (-18.0, 28.0)]


def float_cover():
    x0, x1, y0, y1, zt, zb = COVER
    pl = bd.Plane(origin=((x0 + x1) / 2, y1 - 0.2, (zt + zb) / 2), x_dir=(1, 0, 0), z_dir=(0, -1, 0))
    cov = bd.extrude(pl * bd.RectangleRounded(x1 - x0, zt - zb, 6.0), amount=(y1 - y0) - 0.2)
    rib = bd.extrude(bd.Plane(origin=(4.0, y0 + 0.01, -377.0), x_dir=(1, 0, 0), z_dir=(0, -1, 0))
                     * bd.RectangleRounded(30.0, 12.0, 5.0), amount=1.6)
    cov = _one(cov.fuse(rib))
    holes = [_cyl((p[0], p[1] - 3.0, p[2]), (p[0], p[1] + 6.0, p[2]), 2 * F._shank_radius(5.0) + 0.3)
             for p in _cover_screw_pts()]
    return _one(C.cut_all(cov, holes))


def _fillister_screw(d=5.0, length=12.0):
    """Slotted fillister-head screw, seat at z = 0, head above."""
    r = _r = F._shank_radius(d)
    head = _rev_z([(0.0, 0.0), (4.3, 0.0), (4.3, 3.2), (3.8, 4.0), (0.0, 4.0)])
    shank = _rev_z([(0.0, 0.5), (r, 0.5), (r, -length + 0.5), (r - 0.4, -length), (0.0, -length)])
    slot = bd.Pos(0, 0, 4.0) * bd.Box(1.0, 10.0, 2.4)
    return _one(head.fuse(shank) - slot)


def throttle_parts():
    shaft = _cyl((-38.0, BORE_Y, THR_Z), (66.0, BORE_Y, THR_Z), 8.0)
    # lever: hub + arm hanging down/forward to a ball-end link stud (plate in the YZ plane)
    hub = bd.Circle(10.0)
    # sketch x = engine +Y, sketch y = engine +Z: the arm hangs down, clear of pipe 6
    tip = bd.Pos(4.0, -20.0) * bd.Circle(6.0)
    arm = bd.Polygon((-7.0, -3.0), (7.0, -3.0), (9.5, -20.0), (-1.5, -20.0), align=None)
    sk = hub + tip + arm
    pl = bd.Plane(origin=(54.0, BORE_Y, THR_Z), x_dir=(0, 1, 0), z_dir=(1, 0, 0))
    lever = bd.extrude(pl * sk, amount=4.0)
    lever = lever - _cyl((53.0, BORE_Y, THR_Z), (59.0, BORE_Y, THR_Z), 8.1)
    ball_c = (58.0, BORE_Y + 4.0, THR_Z - 20.0)
    stem = _cyl((57.5, ball_c[1], ball_c[2]), (63.0, ball_c[1], ball_c[2]), 6.0)
    ball = bd.Pos(64.5, ball_c[1], ball_c[2]) * bd.Sphere(4.5)
    lever = _one(lever.fuse(stem, ball))
    nut = F._wrench_head(11.0, 0.0, 5.5, chamfer_bottom=True)
    nut = nut - bd.Pos(0, 0, -1) * bd.Cylinder(4.05, 8.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    nut = F.place(_one(nut), (58.2, BORE_Y, THR_Z), (1, 0, 0), (0, 1, 0))
    return shaft, lever, nut


def _plate_in_bore(x):
    """Throttle plate on the shaft (which runs across its diameter along X): a
    disc with a split hub wrapped round the shaft, tilted 12 deg (just cracked)."""
    disc = bd.Cylinder(BORE_D / 2 - 0.6, 1.6)
    hub = geo.cyl_along((-15.5, 0.0, 0.0), (15.5, 0.0, 0.0), 10.4)
    plate = disc.fuse(hub) - geo.cyl_along((-20.0, 0.0, 0.0), (20.0, 0.0, 0.0), 8.2)
    return bd.Pos(x, BORE_Y, THR_Z) * bd.Rot(12.0, 0.0, 0.0) * _one(plate)


def mixture_parts():
    """Mixture-control shaft out of the throttle body's -X face; the lever reaches
    forward and down (clear of the mount ring behind and exhaust stack 5 below)."""
    x, y, z = MIX
    shaft = _cyl((x + 4.0, y, z), (x - 16.0, y, z), 7.0)
    pl = bd.Plane(origin=(x - 8.0, y, z), x_dir=(0, 1, 0), z_dir=(-1, 0, 0))   # sketch y = engine -Z
    sk = bd.Circle(8.0) + bd.Pos(-25.0, 8.0) * bd.Circle(5.0) + \
        bd.Polygon((0.0, -5.0), (0.0, 5.0), (-25.0, 13.0), (-25.0, 3.0), align=None)
    lever = bd.extrude(pl * sk, amount=3.5)
    lever = lever - [_cyl((x - 7.0, y, z), (x - 13.0, y, z), 7.1),
                     _cyl((x - 7.0, y - 25.0, z - 8.0), (x - 13.0, y - 25.0, z - 8.0), 3.5)]
    lever = _one(lever)
    nut = F._wrench_head(10.0, 0.0, 4.5, chamfer_bottom=True)
    nut = _one(nut - bd.Pos(0, 0, -1) * bd.Cylinder(3.55, 8.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)))
    nut = F.place(nut, (x - 11.7, y, z), (-1, 0, 0), (0, 1, 0))
    return shaft, lever, nut


def fuel_inlet():
    """Brass inlet: hex body, threaded nipple, 37 deg flare cone; axis along -Y."""
    x, y, z = FUEL_IN
    hexb = F._wrench_head(22.0, 0.0, 9.0, chamfer_bottom=True)
    thr = _rev_z([(0.0, -12.0), (6.0, -12.0), (6.0, 0.4), (0.0, 0.4)])     # screwed into the boss
    nip = _rev_z([(0.0, 8.5), (8.0, 8.5), (8.0, 10.0), (7.4, 10.6), (7.4, 11.4), (8.0, 12.0), (8.0, 13.0),
                  (7.4, 13.6), (7.4, 14.4), (8.0, 15.0), (8.0, 16.0), (7.4, 16.6), (7.4, 17.4), (8.0, 18.0),
                  (8.0, 20.5), (5.2, 23.2), (0.0, 23.2)])
    body = _one(hexb.fuse(thr, nip))
    body = _one(body - bd.Pos(0, 0, -13.0) * bd.Cylinder(3.2, 40.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)))
    return F.place(body, (x, y - 6.0, z), (0, -1, 0), (1, 0, 0))


def drain_plug():
    plug = F.hex_flange_bolt(10.0, 12.0)
    hole = geo.cyl_along((-10.0, 0.0, 5.0), (10.0, 0.0, 5.0), 1.6)
    return F.place(plug - hole, DRAIN, (0, 0, -1), (1, 0, 0))


def drain_wire():
    """Safety wire from the drain plug's drilled head to the cast ear (both holes along X)."""
    x, y, zs = DRAIN
    return _cyl((x - 4.0, y, zs - 5.0), (EAR[0] + 2.6, y, zs - 5.0), 0.8)


def carb_parts():
    fixed = [("carb_adapter", carb_adapter(), P.CARB_ALU)]
    out = [("carb_body", carb_body(), P.CARB_ALU), ("carb_float_cover", float_cover(), P.CARB_ALU)]
    nut8 = _one(F.flange_nut(8.0) - bd.Pos(0, 0, -1) * bd.Cylinder(
        F._shank_radius(8.0) + 0.06, 12.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)))
    stud8 = F.stud(8.0, 20.0, 6.0)
    hex8 = _one(F.hex_nut(8.0) - bd.Pos(0, 0, -1) * bd.Cylinder(
        F._shank_radius(8.0) + 0.06, 12.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)))
    for i, (x, y) in enumerate(PAD_STUDS, start=1):
        # plain hex nuts, a flat toward pipe 6's coupling
        fixed.append((f"carb_adapter_nut_{i}", F.place(hex8, (x, y, AD_TOP[1]), (0, 0, -1), (0, 1, 0)), P.FASTENER))
    for i, (x, y) in enumerate(CARB_STUDS, start=1):
        out.append((f"carb_stud_{i}", F.place(stud8, (x, y, AD_BOT[1]), (0, 0, -1), (1, 0, 0)), P.FASTENER))
        out.append((f"carb_nut_{i}", F.place(nut8, (x, y, CARB_FL[1]), (0, 0, -1), (1, 0, 0)), P.FASTENER))
    shaft, lever, tnut = throttle_parts()
    out.append(("carb_throttle_shaft", shaft, P.FASTENER))
    for i, x in enumerate(BORES_X, start=1):
        out.append((f"carb_throttle_plate_{i}", _plate_in_bore(x), P.BRASS))
    out.append(("carb_throttle_lever", lever, P.FASTENER))
    out.append(("carb_throttle_nut", tnut, P.FASTENER))
    ms, ml, mn = mixture_parts()
    out.append(("carb_mixture_shaft", ms, P.FASTENER))
    out.append(("carb_mixture_lever", ml, P.FASTENER))
    out.append(("carb_mixture_nut", mn, P.FASTENER))
    out.append(("carb_fuel_inlet", fuel_inlet(), P.BRASS))
    scr = _fillister_screw()
    for i, p in enumerate(_cover_screw_pts(), start=1):
        out.append((f"carb_cover_screw_{i}", F.place(scr, p, (0, -1, 0), (1, 0, 0)), P.FASTENER))
    out.append(("carb_drain_bolt", drain_plug(), P.FASTENER))
    out.append(("carb_drain_wire", drain_wire(), P.SAFETY_WIRE))
    shift = bd.Pos(*CARB_SHIFT)
    return fixed + [(n, shift * sh, c) for n, sh, c in out]


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
def pipe_protos():
    """[(name, shape, colour, seat_point)] for cylinder 1; name uses {k}."""
    out = [("pipe_{k}", pipe_proto(), P.POLISHED_ALU, None),
           ("elbow_{k}", elbow_proto(), P.POLISHED_ALU, None),
           ("hose_{k}_a", hose_proto(*HOSE_A), P.RUBBER, None),
           ("hose_{k}_b", hose_proto(*HOSE_B), P.RUBBER, None)]
    for n, (c, r) in enumerate(zip(clamp_protos(), CLAMP_R), start=1):
        out.append((f"clamp_{{k}}_{n}", c, P.FASTENER, rp(r)))
    out.append(("union_nut_{k}", union_nut_proto(), P.FASTENER, (STUB_T, 120.0, STUB_H)))
    return out


def build():
    parts = []
    protos = pipe_protos()
    for k in range(1, S.N_CYL + 1):
        for name, shape, colour, seat in protos:
            label = "intake:" + name.format(k=k)
            if k == geo.SECTION_CYL:
                if seat is not None and geo.in_section(seat):
                    continue
                kept, skin = geo.cut_with_skin(shape, "section")
                if kept is None:          # wholly inside the removed region
                    continue
                sols = kept.solids()
                if not sols:
                    continue
                shp = max(sols, key=lambda s: s.volume)
                if skin is not None:
                    ss = skin.solids()
                    sk = ss[0] if len(ss) == 1 else bd.Compound(children=list(ss))
                    parts.append(P.style(sk, "intake:section_skin_" + name.format(k=k), P.SECTION_RED))
            else:
                shp = geo.on_cylinder(shape, k)
            parts.append(P.style(shp, label, colour))
    for name, shape, colour in carb_parts():
        parts.append(P.style(shape, "intake:" + name, colour))
    return parts


if __name__ == "__main__":
    import time
    t0 = time.time()
    ps = build()
    print(f"{len(ps)} leaves in {time.time() - t0:.0f}s")
    print("unsound:", [p.label for p in ps if not geo.sound(p)])
