"""Reduction system: the 3:2 planetary propeller reduction in the nose.

    crank-driven internal BELL gear 72T  (`crank:bell_gear`, bolted to the crank
        nose flange with the crankshaft's own 8 bolts)
    FIXED sun 36T                        (`reduction:sun`, one forging with its
        spigot sleeve; anchored in front of the nose-case web by
        `reduction:sun_support` + 12 wired bolts + a ring nut)
    six 18T planets                      (`planet<j>:gear` + bronze `planet<j>:bearing`)
    pinion carrier                       (`propshaft:carrier`: a splined hub, a
        backing plate BEHIND the planets and six cage fingers between them; the
        pins `propshaft:planet_pin_<j>` are pressed into the plate)
    propeller shaft                      (`propshaft:shaft`, hollow: pilot in the
        crank nose bore, splines for the carrier, journal through the sun,
        thrust-bearing seat, hub splines, threaded end + hub nut + cotter)
    thrust bearing                       (`propshaft:thrust_inner` inner race,
        `propshaft:thrust_balls` 18 balls + cage, `reduction:thrust_outer` in the nose liner)

TOPOLOGY (why the carrier is BEHIND the planets): the sun is static and must
reach the nose case, the carrier turns and must reach the shaft, and behind the
gears everything turns with the crank. So the sun leaves FORWARD (sleeve
through the nose web bore) and the carrier meets the shaft BEHIND the sun,
between the gears and the bell web. The crankshaft's forward-facing bell-bolt
heads (F0-11.5..F0-6, r 55..70) sit in a recess of the bell hub; the carrier
plate runs in front of them (G0+22..G0+29), so the planet and sun faces are
G0+1..G0+20.5 inside the G0..G0+38 gear span (the ring's teeth run G0..G0+30).
(Stations: G0 = spec.RED_FACE_Y[0], F0 = spec.CRANK_NOSE_FLANGE_Y.)

Every propshaft/planet feature is 3- or 6-fold (the carrier turns 480 deg per
720 deg cycle, the planets 1440 deg); the single hub-nut cotter is the only
exception (it sits inside the spinner).

Gear frame: local XY with x_dir = +Z, z_dir = ROT_AXIS, so a local polar angle
IS the in-plane angle (see spec.inplane). Tooth clocking at theta = 0 (tooth in
gap on every line of centres; planet j centre at in-plane 60(j-1)):
    sun   36T : tooth centres at 0 + 10 k      (a tooth points at every planet)
    planet 18T: tooth centres at 10 + 20 k     (a gap faces the sun AND the ring)
    ring  72T : tooth centres at 0 + 5 k       (a tooth points at every planet)
"""

from __future__ import annotations

import math

from cadgen import build123d as bd

from lib import castings as C
from lib import fasteners as F
from lib import geo, kin
from lib import palette as P
from lib import spec as S

MATERIALS = ("bronze", "fastener", "safety_wire", "steel_dark", "steel_machined")

_ROT = S.ROT_AXIS
M = S.RED_MODULE                         # 3
ZR, ZS, ZP = S.RED_RING_T, S.RED_SUN_T, S.RED_PLANET_T
RP_R, RP_S, RP_P = ZR * M / 2, ZS * M / 2, ZP * M / 2     # 108, 54, 27
CD = S.RED_PLANET_R                      # 81 centre distance
BACKLASH = 0.08

# ---------------------------------------------------------------------------
# Axial stations (engine y; front is more negative). Every station is an offset
# from a spec anchor: G0 = front gear face (spec.RED_FACE_Y[0]), F0 = crank nose
# flange front face (spec.CRANK_NOSE_FLANGE_Y) - both carry spec.NOSE_SHIFT.
# ---------------------------------------------------------------------------
G0 = S.RED_FACE_Y[0]
F0 = S.CRANK_NOSE_FLANGE_Y
PLANET_Y = (G0 + 1, G0 + 20.5)
SUN_Y = (G0 + 0.5, G0 + 20.5)
RING_TEETH_Y = (G0, G0 + 30)
PLATE_Y = (G0 + 22, G0 + 29)               # carrier backing plate
HUB_Y = (G0 + 22, G0 + 38)                 # carrier hub (splined on the shaft)
FINGER_Y = (G0 - 0.5, G0 + 23)
CARRIER_NUT_Y = (F0 - 6, F0 - 1.8)
FLANGE_Y0 = F0                           # crank nose flange front face
BOLT_SEAT_Y = FLANGE_Y0 - 6.0            # bell hub front face (bolt heads seat here)
WEB_FACE_Y = F0 - 10                      # bell web front face outside the bolt recess
NOSE_WEB = (G0 - 20, G0 - 5)              # nose-case web (front, rear face)
NOSE_WEB_BORE = 61.5
SUPPORT_Y = (G0 - 28, G0 - 20.65)            # sun anchor flange (in front of the web)
SUN_NUT_Y = (G0 - 35.5, G0 - 28)
BRG_Y = (G0 - 92, G0 - 60)                 # thrust bearing (nose liner seat)
BRG_BALL_Y = G0 - 76
THRUST_NUT_Y = (G0 - 99.5, G0 - 91.5)       # seats on the inner race front face
REAR_CONE_Y = (G0 - 125, G0 - 111)
SPLINE_Y = (G0 - 230.5, G0 - 125.5)
HUB_NUT_Y = (G0 - 256, G0 - 241)
SHAFT_END_Y = G0 - 260

# radii
SHAFT_R = 34.0                           # journal through the sun
SUN_BORE_R = 36.5
BUSH_IR = 34.3
PIN_R = 12.0
PLANET_BORE_R = 17.0
PIN_HEAD_R = 15.0
SUPPORT_BOLT_R, SUPPORT_BOLT_N, SUPPORT_BOLT_PHASE = 85.0, 12, 15.0   # nose's tapped holes


# ---------------------------------------------------------------------------
# Frames and small helpers
# ---------------------------------------------------------------------------
def _gear_loc(axis_xz=(0.0, 0.0), y=0.0) -> bd.Location:
    pl = bd.Plane(origin=(axis_xz[0], y, axis_xz[1]), x_dir=(0, 0, 1), z_dir=_ROT)
    return pl.location


def _span(face, y0, y1, axis_xz=(0.0, 0.0)):
    """Extrude a local-XY face so it spans engine y in [y0, y1] (y0 < y1)."""
    return _gear_loc(axis_xz, y1) * bd.extrude(face, amount=y1 - y0)


def _polar(r, a):
    return (r * math.cos(a), r * math.sin(a))


def _pz(b_deg, r):
    """(x, z) of in-plane angle b at radius r."""
    p = S.inplane(b_deg, r)
    return (p[0], p[2])


def _rev(pts):
    return geo.revolve_y(pts)


def _style(shape, label, color):
    return P.style(shape, label, color)


# ---------------------------------------------------------------------------
# Involute outlines (local XY, polar angle = in-plane angle)
# ---------------------------------------------------------------------------
def _inv(a):
    return math.tan(a) - a


def gear_face(z, m, r_a, r_f, c0_deg, thick_delta=0.0, alpha_deg=20.0, n_flank=10):
    """External spur outline: z teeth, tooth CENTRES at c0 + 360 i / z, tooth
    thickness at the pitch circle pi m / 2 + thick_delta. Radial flank below
    the base circle."""
    al = math.radians(alpha_deg)
    rp = z * m / 2.0
    rbase = rp * math.cos(al)
    psi_p = (math.pi * m / 2.0 + thick_delta) / (2.0 * rp)

    def psi(r):
        ar = math.acos(min(1.0, rbase / max(r, rbase)))
        return psi_p + _inv(al) - _inv(ar)

    r0 = max(r_f, rbase)
    t0 = math.sqrt(max(0.0, (r0 / rbase) ** 2 - 1.0))
    ta = math.sqrt((r_a / rbase) ** 2 - 1.0)
    radii = [rbase * math.sqrt(1.0 + (t0 + (ta - t0) * i / n_flank) ** 2) for i in range(n_flank + 1)]
    radii[0], radii[-1] = r0, r_a
    assert psi(r_a) > 0.02 / r_a, "pointed tooth"

    def V(r, a):
        x, yy = _polar(r, a)
        return bd.Vector(x, yy, 0.0)

    edges = []
    pitch = 2.0 * math.pi / z
    c0 = math.radians(c0_deg)
    for i in range(z):
        c = c0 + i * pitch
        right = [V(r, c - psi(r)) for r in radii]
        left = [V(r, c + psi(r)) for r in reversed(radii)]
        if r_f < r0 - 1e-6:
            edges.append(bd.Line(V(r_f, c - psi(r0)), right[0]))
        edges.append(bd.Spline(*right))
        edges.append(bd.ThreePointArc(right[-1], V(r_a, c), left[0]))
        edges.append(bd.Spline(*left))
        a_end = c + psi(r0)
        if r_f < r0 - 1e-6:
            edges.append(bd.Line(left[-1], V(r_f, a_end)))
        a_next = c + pitch - psi(r0)
        edges.append(bd.ThreePointArc(V(r_f, a_end), V(r_f, (a_end + a_next) / 2.0), V(r_f, a_next)))
    return bd.Face(bd.Wire(edges))


def _tip_limiter(r_a, y0, y1, c=0.8, axis_xz=(0.0, 0.0)):
    """Revolved limiter that breaks an external gear's tooth-tip edges at both faces."""
    body = _rev([(0.0, y0), (r_a - c, y0), (r_a + 0.3, y0 + c + 0.3), (r_a + 0.3, y1 - c - 0.3),
                 (r_a - c, y1), (0.0, y1)])
    if axis_xz != (0.0, 0.0):
        body = bd.Pos(axis_xz[0], 0, axis_xz[1]) * body
    return body


# ---------------------------------------------------------------------------
# Bell gear (crank group)
# ---------------------------------------------------------------------------
RING_TIP_R = 105.4        # internal tip circle: clears the 18T base-circle interference point (r 105.2)
RING_ROOT_R = RP_R + 1.25 * M
BELL_OD = 123.0
BELL_HUB_BORE = 51.0
BOLT_RECESS_R = 78.0
BELL_BOLT_PCD_R = 62.5


def bell_gear():
    y0 = RING_TEETH_Y[0]
    prof = [
        (BELL_HUB_BORE, FLANGE_Y0),                   # rear hub face on the crank flange
        (75.2, FLANGE_Y0),
        (75.2, F0 + 5.4), (75.8, F0 + 6),               # spigot lip over the flange OD
        (85.0, F0 + 6), (86.2, F0 + 5),
        (BELL_OD, F0 - 10),                            # conical web back (the "bell")
        (BELL_OD, y0 + 1.2), (BELL_OD - 1.2, y0),     # rim OD, front chamfer
        (RING_TIP_R + 0.8, y0), (RING_TIP_R, y0 + 0.8),
        (RING_TIP_R, RING_TEETH_Y[1]),                # tooth tips to the teeth end
        (113.0, RING_TEETH_Y[1]), (113.0, WEB_FACE_Y),  # runout groove
        (BOLT_RECESS_R + 1.0, WEB_FACE_Y), (BOLT_RECESS_R, WEB_FACE_Y + 1.0),
        (BOLT_RECESS_R, BOLT_SEAT_Y),                 # bolt-head recess wall
        (BELL_HUB_BORE + 0.8, BOLT_SEAT_Y), (BELL_HUB_BORE, BOLT_SEAT_Y + 0.8),
    ]
    body = _rev(prof)
    # internal teeth: gap cutter = external outline whose teeth are the ring's gaps (centres 2.5 + 5 k)
    cutter = gear_face(ZR, M, RING_ROOT_R, RING_TIP_R - 1.5, 180.0 / ZR, thick_delta=+BACKLASH)
    cutter = _span(cutter, y0 - 1.0, RING_TEETH_Y[1] + 2.0)
    holes = []
    for i in range(8):
        x, z = _pz(22.5 + 45.0 * i, BELL_BOLT_PCD_R)
        holes.append(geo.cyl_y(BOLT_SEAT_Y - 1, FLANGE_Y0 + 1, 8.4, x, z))
    # lightening holes through the conical web, between the bolts (8-fold, crank group)
    for i in range(8):
        x, z = _pz(45.0 * i, 99.0)
        holes.append(geo.cyl_y(WEB_FACE_Y - 1, F0 + 6, 15.0, x, z))
    body = C.cut_all(body, [cutter])
    return C.cut_all(body, holes)


# ---------------------------------------------------------------------------
# Sun (static) + anchor
# ---------------------------------------------------------------------------
SLEEVE_R = 61.2           # spigot through the nose web bore (r 61.5)
SUN_THREAD_R = 55.0


def sun():
    y0, y1 = SUN_Y
    ra, rf = RP_S + M, RP_S - 1.25 * M
    g = _span(gear_face(ZS, M, ra, rf, 0.0, thick_delta=-BACKLASH), y0, y1)
    g = g & _tip_limiter(ra, y0, y1)
    sleeve = _rev([
        (SUN_BORE_R, y1 - 2.0), (46.0, y1 - 2.0), (46.0, y0),
        (50.0, y0), (50.0, G0 - 1.4), (50.6, G0 - 2),
        (SLEEVE_R - 0.8, G0 - 2), (SLEEVE_R, G0 - 2.8),
        (SLEEVE_R, NOSE_WEB[0] + 0.3), (SLEEVE_R - 0.8, NOSE_WEB[0] - 0.5),
        (SUN_THREAD_R, NOSE_WEB[0] - 0.5),
        (SUN_THREAD_R, SUN_NUT_Y[0] - 0.3), (SUN_THREAD_R - 0.8, SUN_NUT_Y[0] - 1.1),
        (SUN_BORE_R + 0.8, SUN_NUT_Y[0] - 1.1), (SUN_BORE_R, SUN_NUT_Y[0] - 0.3),
    ])
    body = C.fuse_all([g, sleeve])
    body = C.cut_all(body, [geo.cyl_y(y0 - 1, y1 + 1, 2 * SUN_BORE_R)])
    # six anti-rotation dog slots in the sleeve front (the support's dogs sit in them)
    dogs = [_dog(i, grow=0.15) for i in range(6)]
    return C.cut_all(body, dogs)


def _dog(i, grow=0.0):
    """Driving dog between the support flange bore and the sun sleeve, at in-plane 30 + 60 i."""
    y0, y1 = SUPPORT_Y
    box = bd.Box(8.0 + 2 * grow, y1 - y0 + 2 * grow, 4.0 + 2 * grow)
    return geo.axis_rotation(_ROT, 30.0 + 60.0 * i) * bd.Pos(0, 0.5 * (y0 + y1), SUN_THREAD_R) * box


def sun_support():
    y0, y1 = SUPPORT_Y
    body = _rev([(SUN_THREAD_R + 0.15, y1), (99.0, y1), (100.0, y1 - 1.0), (100.0, y0 + 1.2),
                 (98.8, y0), (58.0, y0), (SUN_THREAD_R + 0.15, y0 + 1.0)])
    body = C.fuse_all([body] + [_dog(i) & geo.cyl_y(y0, y1, 2 * (SUN_THREAD_R + 2.2)) for i in range(6)])
    holes = []
    for i in range(SUPPORT_BOLT_N):
        x, z = _pz(SUPPORT_BOLT_PHASE + 30.0 * i, SUPPORT_BOLT_R)
        holes.append(geo.cyl_y(y0 - 1, y1 + 1, 8.4, x, z))
    return C.cut_all(body, holes)


def ring_nut(r_in, r_out, h, slots=6, slot_w=5.0, slot_d=2.5, phase=0.0):
    """Slotted ring nut, seat at z = 0, body up +Z (4 slots on the outer rim)."""
    body = F._rev([(r_in, 0.5), (r_in + 0.5, 0), (r_out - 0.8, 0), (r_out, 0.8), (r_out, h - 0.8),
                   (r_out - 0.8, h), (r_in + 0.5, h), (r_in, h - 0.5)])
    cuts = [bd.Rot(0, 0, phase + 360.0 * i / slots) * bd.Pos(r_out, 0, h / 2.0 + 0.8) * bd.Box(2 * slot_d, slot_w, h)
            for i in range(slots)]
    return C.cut_all(body, cuts)


def sun_bushing(y0, y1):
    return _rev([(BUSH_IR + 0.4, y0), (SUN_BORE_R, y0), (SUN_BORE_R, y1), (BUSH_IR + 0.4, y1),
                 (BUSH_IR, y1 - 0.4), (BUSH_IR, y0 + 0.4)])


# ---------------------------------------------------------------------------
# Planets (authored for planet 1, rotated about the axis for the others)
# ---------------------------------------------------------------------------
PC1 = _pz(0.0, CD)        # planet 1 centre (x, z) = (0, 81)


def planet_gear():
    y0, y1 = PLANET_Y
    ra, rf = RP_P + M, RP_P - 1.25 * M
    g = _span(gear_face(ZP, M, ra, rf, 10.0, thick_delta=-BACKLASH), y0, y1, axis_xz=PC1)
    g = g & _tip_limiter(ra, y0, y1, axis_xz=PC1)
    bore = geo.cyl_y(y0 - 1, y1 + 1, 2 * PLANET_BORE_R, *PC1)
    cb = geo.cyl_y(y0 - 1, y0 + 1.5, 2 * 19.2, *PC1)
    g = C.cut_all(g, [bore])
    g = C.cut_all(g, [cb])
    # a shallow relief ring on the front face (machined recess reads as a finished gear)
    rel = geo.cyl_y(y0 - 1, y0 + 0.5, 2 * 21.5, *PC1) - geo.cyl_y(y0 - 2, y0 + 2, 2 * 19.2, *PC1)
    return C.cut_all(g, [rel])


def planet_bearing():
    """Flanged bronze bush pressed into the planet (turns with it, runs on the pin)."""
    y0, y1 = PLANET_Y
    b = _rev([(PIN_R + 0.15, y0 - 0.2), (19.0 - 0.4, y0 - 0.2), (19.0, y0 + 0.2), (19.0, y0 + 1.5),
              (PLANET_BORE_R, y0 + 1.5), (PLANET_BORE_R, y1), (PIN_R + 0.55, y1), (PIN_R + 0.15, y1 - 0.4)])
    return bd.Pos(PC1[0], 0, PC1[1]) * b


def planet_pin():
    ph0, ph1 = G0 - 2.5, PLANET_Y[0] - 0.6
    p = _rev([(0.0, ph0), (PIN_HEAD_R - 1.0, ph0), (PIN_HEAD_R, ph0 + 1.0), (PIN_HEAD_R, ph1),
              (PIN_R, ph1), (PIN_R, PLATE_Y[1] - 0.6), (PIN_R - 0.6, PLATE_Y[1]), (0.0, PLATE_Y[1])])
    p = p - _rev([(0.0, ph0 - 1), (4.0, ph0 - 1), (4.0, PLATE_Y[1] + 1), (0.0, PLATE_Y[1] + 1)])  # oil bore
    p = bd.Pos(PC1[0], 0, PC1[1]) * p
    # a hex socket in the head (removal) - 6-fold like everything on the carrier
    sock = _span(bd.RegularPolygon(5.5, 6), ph0 - 1.0, ph0 + 3.0, axis_xz=PC1)
    return p - sock


# ---------------------------------------------------------------------------
# Carrier + shaft (propshaft group)
# ---------------------------------------------------------------------------
N_SPL = 24


def _spline_sketch(r_root, r_tip, w, n=N_SPL, phase=0.0):
    teeth = [bd.Rot(0, 0, phase + 360.0 * i / n) * bd.Pos(0.5 * (r_root - 0.5 + r_tip), 0)
             * bd.Rectangle(r_tip - r_root + 0.5, w) for i in range(n)]
    return (bd.Circle(r_root) + teeth) & bd.Circle(r_tip)


def carrier():
    plate = _rev([
        (SHAFT_R + 0.2, HUB_Y[0]), (98.8, PLATE_Y[0]), (100.0, PLATE_Y[0] + 1.2),
        (100.0, PLATE_Y[1] - 1.2), (98.8, PLATE_Y[1]), (49.0, PLATE_Y[1]),
        (44.0, PLATE_Y[1] + 4.0), (44.0, HUB_Y[1] + 0.8), (43.2, HUB_Y[1]), (SHAFT_R + 0.2, HUB_Y[1]),
    ])
    # six cage fingers between the planets: annular sector minus the planets' clearance circles
    clear = 32.8
    sk = bd.Sketch() + [bd.make_face(bd.Wire([
        bd.ThreePointArc(bd.Vector(*_polar(99.0, math.radians(4))), bd.Vector(*_polar(99.0, math.radians(30))),
                         bd.Vector(*_polar(99.0, math.radians(56)))),
        bd.Line(bd.Vector(*_polar(99.0, math.radians(56))), bd.Vector(*_polar(63.5, math.radians(56)))),
        bd.ThreePointArc(bd.Vector(*_polar(63.5, math.radians(56))), bd.Vector(*_polar(63.5, math.radians(30))),
                         bd.Vector(*_polar(63.5, math.radians(4)))),
        bd.Line(bd.Vector(*_polar(63.5, math.radians(4))), bd.Vector(*_polar(99.0, math.radians(4)))),
    ]))]
    sk = sk - [bd.Pos(*_polar(CD, 0.0)) * bd.Circle(clear), bd.Pos(*_polar(CD, math.pi / 3)) * bd.Circle(clear)]
    finger0 = _span(sk.face(), *FINGER_Y)
    fingers = [geo.axis_rotation(_ROT, 60.0 * i) * finger0 for i in range(6)]
    body = C.fuse_all([plate] + fingers)
    # soften the finger front ends and their long edges
    fr = [e for e in body.edges() if abs(C.edge_center(e).Y - FINGER_Y[0]) < 1e-3]
    body, _ = C.safe_fillet(body, fr, 1.5, min_r=0.5)
    # pin holes, bore splines
    tools = [geo.cyl_y(PLATE_Y[0] - 1, PLATE_Y[1] + 1, 2 * PIN_R, *_pz(60.0 * j, CD)) for j in range(6)]
    body = C.cut_all(body, tools)
    hole = _spline_sketch(31.15, SHAFT_R + 0.2, 4.0 + 0.3)
    body = C.cut_all(body, [_span(hole, HUB_Y[0] - 1, HUB_Y[1] + 1)])
    # lightening holes in the plate between the pins (6-fold)
    lh = [geo.cyl_y(PLATE_Y[0] - 1, PLATE_Y[1] + 1, 11.0, *_pz(30.0 + 60.0 * j, 54.0)) for j in range(6)]
    return C.cut_all(body, lh)


def shaft():
    outer_in = [
        (12.0, F0 + 30), (17.0, F0 + 30), (17.6, F0 + 29.4), (17.6, F0 - 1.8),
        (29.4, F0 - 1.8), (30.0, F0 - 2.4), (30.0, HUB_Y[1]), (31.0, HUB_Y[1]),
        (31.0, G0 + 19), (SHAFT_R, G0 + 19),
        (SHAFT_R, G0 - 45), (45.0, G0 - 51.5), (51.0, G0 - 51.5), (52.0, G0 - 52.5), (52.0, BRG_Y[1]),
        (45.0, BRG_Y[1]), (45.0, THRUST_NUT_Y[1]), (43.0, THRUST_NUT_Y[1]), (43.0, THRUST_NUT_Y[0]),
        (45.0, THRUST_NUT_Y[0] - 1.0), (45.0, SPLINE_Y[1]), (42.0, SPLINE_Y[1] - 1.0),
        (42.0, SPLINE_Y[0] - 1.5), (40.0, SPLINE_Y[0] - 3.0),
        (40.0, SHAFT_END_Y + 0.8), (39.2, SHAFT_END_Y), (25.0, SHAFT_END_Y),
        (25.0, G0 - 50), (20.0, G0 - 45), (20.0, G0 + 32), (12.0, G0 + 38),
    ]
    body = _rev(outer_in)
    rear_spl = _span(_spline_sketch(30.8, SHAFT_R, 4.0) - bd.Circle(25.0), G0 + 21, HUB_Y[1] - 0.5)
    front = _span(_spline_sketch(41.8, 45.0, 5.0, phase=7.5) - bd.Circle(38.0), *SPLINE_Y)
    # spline run-outs: taper the tooth tips into the shaft at both ends
    front = front & _rev([(0.0, SPLINE_Y[0]), (42.2, SPLINE_Y[0]), (45.2, SPLINE_Y[0] + 5.0),
                          (45.2, SPLINE_Y[1] - 5.0), (42.2, SPLINE_Y[1]), (0.0, SPLINE_Y[1])])
    body = C.fuse_all([body, rear_spl, front])
    # cotter cross-hole through the threaded end (along X at theta = 0)
    cy = HUB_NUT_Y[0] + 3.0
    return C.cut_all(body, [geo.cyl_along((-60, cy, 0), (60, cy, 0), 4.6)])


# ---------------------------------------------------------------------------
# Thrust bearing
# ---------------------------------------------------------------------------
BALL_N = 18
BALL_R = 8.5
BALL_PR = 62.75


def thrust_inner():
    """Inner race: deep groove concentric with the ball path, 0.25 mm running clearance.
    (Balls fused INTO the race left a sphere/torus seat that fails BRepCheck after the STEP
    round trip, so the balls + cage are their own body, `propshaft:thrust_balls`.)"""
    y0, y1 = BRG_Y[0] + 0.5, BRG_Y[1]
    race = _rev([(45.0, y0), (56.4, y0), (57.0, y0 + 0.6), (57.0, y1 - 0.6), (56.4, y1), (45.0, y1)])
    groove = bd.Pos(0, BRG_BALL_Y, 0) * bd.Rot(90, 0, 0) * bd.Torus(BALL_PR, BALL_R + 0.25)
    return race - groove


def thrust_balls():
    """18 balls strung on their cage ring (one body; 18 = 3-fold for the 480 deg loop)."""
    balls = [bd.Pos(*S.inplane(20.0 * i, BALL_PR, BRG_BALL_Y)) * bd.Rot(90, 0, 0) * bd.Sphere(BALL_R)
             for i in range(BALL_N)]
    cage = _rev([(59.5, BRG_BALL_Y - 2.5), (66.0, BRG_BALL_Y - 2.5), (66.0, BRG_BALL_Y + 2.5),
                 (59.5, BRG_BALL_Y + 2.5)])
    return C.fuse_all([cage] + balls)


def thrust_outer():
    y0, y1 = BRG_Y
    race = _rev([(68.5, y0 + 0.6), (69.1, y0), (80.0, y0), (80.0, y1), (69.1, y1), (68.5, y1 - 0.6)])
    groove = bd.Pos(0, BRG_BALL_Y, 0) * bd.Rot(90, 0, 0) * bd.Torus(BALL_PR, BALL_R + 0.3)
    return race - groove


# ---------------------------------------------------------------------------
# Hardware
# ---------------------------------------------------------------------------
def hex_bolt(d, af, head_h, length, wire_hole=True):
    """Hex bolt, bearing face z = 0, head up, shank down; head drilled across the flats."""
    head = F._wrench_head(af, 0.0, head_h, chamfer_bottom=True, dish=0.0)
    ch = 0.8
    shank = F._rev([(0, -length), (d / 2 - ch, -length), (d / 2, -length + ch), (d / 2, 0.5), (0, 0.5)])
    b = C.fuse_all([head, shank])
    if wire_hole:
        b = b - (bd.Pos(0, 0, head_h * 0.5) * bd.Rot(90, 0, 0) * bd.Cylinder(0.8, af * 2))
    return b


def cotter_pin(length, d=4.0):
    """Split cotter along -Z from its eye at z = 0; legs spread at the tip."""
    shaft_ = bd.Pos(0, 0, -length) * bd.Cylinder(d / 2.0, length, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    eye = bd.Pos(0, 0, 3.0) * bd.Rot(90, 0, 0) * bd.Torus(3.0, d / 2.0)
    return C.fuse_all([shaft_, eye])


def _wire_between(p, q, sag_dir, sag=2.5, d=0.8):
    mid = tuple((a + b) / 2 + sag * s for a, b, s in zip(p, q, sag_dir))
    path = bd.Spline(bd.Vector(*p), bd.Vector(*mid), bd.Vector(*q))
    prof = bd.Plane(origin=path @ 0.0, z_dir=path % 0.0) * bd.Circle(d / 2.0)
    return bd.sweep(prof, path=path)


def hub_nut():
    y0, y1 = HUB_NUT_Y
    h = y1 - y0
    af = 84.0
    body = F._wrench_head(af, 0.0, h - 3.0, chamfer_bottom=False, dish=0.0)
    flange = F._rev([(40.0, 0.0), (55.5, 0.0), (56.0, 0.5), (56.0, 3.0), (40.0, 3.0)])
    body = C.fuse_all([bd.Pos(0, 0, 3.0) * body, flange])
    body = body - bd.Pos(0, 0, -1) * bd.Cylinder(40.15, h + 2, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    slots = [bd.Rot(0, 0, 30.0 + 60.0 * i) * bd.Pos(40.0, 0, h - 3.5) * bd.Box(30.0, 5.2, 8.0) for i in range(6)]
    return C.cut_all(body, slots)


def rear_cone():
    y0, y1 = REAR_CONE_Y
    return _rev([(45.15, y1), (55.4, y1), (56.0, y1 - 0.6), (56.0, y1 - 2.5), (49.0, y0), (45.15, y0)])


def build():
    SM, SD, BR, FA, SW = P.STEEL_MACHINED, P.STEEL_DARK, P.BRONZE, P.FASTENER, P.SAFETY_WIRE
    cutter = geo.nose_cutter()
    parts = []

    # ---- bell gear (turns with the crank)
    parts.append(_style(bell_gear(), "crank:bell_gear", SM))

    # ---- static: sun, support, bushings, bolts, wire, thrust outer race
    parts.append(_style(sun(), "reduction:sun", SM))
    parts.append(_style(sun_bushing(SUN_Y[0] + 0.5, SUN_Y[1]), "reduction:sun_rear_bushing", BR))
    parts.append(_style(sun_bushing(SUN_NUT_Y[0] - 1.0, NOSE_WEB[0] + 2.0), "reduction:sun_front_bushing", BR))
    parts.append(_style(geo.cut(sun_support(), cutter), "reduction:sun_support", SD))
    nut = ring_nut(SUN_THREAD_R + 0.15, 64.0, SUN_NUT_Y[1] - SUN_NUT_Y[0], phase=0.0)
    parts.append(_style(F.place(nut, (0, SUPPORT_Y[0], 0), (0, -1, 0), (0, 0, 1)), "reduction:sun_nut", SD))

    bolt = hex_bolt(8.0, 13.0, 5.5, 20.0)
    kept = {}
    for i in range(SUPPORT_BOLT_N):
        b = SUPPORT_BOLT_PHASE + 30.0 * i
        p = S.inplane(b, SUPPORT_BOLT_R, SUPPORT_Y[0])
        if geo.in_nose_cut(p):
            continue
        rad = S.inplane(b)
        kept[i] = (p, rad, b)
        parts.append(_style(F.place(bolt, p, (0, -1, 0), rad), f"reduction:sun_support_bolt_{i + 1}", FA))
    for i in range(0, SUPPORT_BOLT_N, 2):
        j = i + 1
        if i in kept and j in kept:
            (p, rad, b), (q, radq, bq) = kept[i], kept[j]
            yw = SUPPORT_Y[0] - 2.75
            pw = (p[0], yw, p[2])
            qw = (q[0], yw, q[2])
            bm = 0.5 * (b + bq)
            sag = S.inplane(bm)
            parts.append(_style(_wire_between(pw, qw, sag, sag=3.0), f"reduction:sun_support_wire_{i // 2 + 1}", SW))
    parts.append(_style(geo.cut(thrust_outer(), cutter), "reduction:thrust_outer", SM))

    # ---- planets: prototype for planet 1, rotated copies (teeth stay clocked: 60 = 3 x 20 deg)
    pg, pb = planet_gear(), planet_bearing()
    for j in range(1, 7):
        loc = geo.axis_rotation(_ROT, 60.0 * (j - 1))
        parts.append(_style(loc * pg, f"planet{j}:gear", SM))
        parts.append(_style(loc * pb, f"planet{j}:bearing", BR))

    # ---- carrier, pins, shaft, thrust inner, nuts, cone
    parts.append(_style(carrier(), "propshaft:carrier", SD))
    pin = planet_pin()
    for j in range(1, 7):
        parts.append(_style(geo.axis_rotation(_ROT, 60.0 * (j - 1)) * pin, f"propshaft:planet_pin_{j}", SM))
    parts.append(_style(shaft(), "propshaft:shaft", SM))
    cn = ring_nut(30.15, 43.0, CARRIER_NUT_Y[1] - CARRIER_NUT_Y[0])
    parts.append(_style(F.place(cn, (0, HUB_Y[1], 0), (0, 1, 0), (0, 0, 1)), "propshaft:carrier_nut", SD))
    parts.append(_style(thrust_inner(), "propshaft:thrust_inner", SM))
    parts.append(_style(thrust_balls(), "propshaft:thrust_balls", SM))
    tn = ring_nut(43.15, 46.5, THRUST_NUT_Y[1] - THRUST_NUT_Y[0], slot_w=4.0, slot_d=1.2)
    parts.append(_style(F.place(tn, (0, THRUST_NUT_Y[1], 0), (0, -1, 0), (0, 0, 1)), "propshaft:thrust_nut", SD))
    parts.append(_style(rear_cone(), "propshaft:rear_cone", BR))
    parts.append(_style(F.place(hub_nut(), (0, HUB_NUT_Y[1], 0), (0, -1, 0), (0, 0, 1)), "propshaft:hub_nut", SM))
    cy = HUB_NUT_Y[0] + 3.0
    cot = cotter_pin(92.0)
    parts.append(_style(F.place(cot, (50.0, cy, 0), (1, 0, 0), (0, 1, 0)), "propshaft:hub_cotter", SW))
    return parts


if __name__ == "__main__":
    import time
    t0 = time.time()
    ps = build()
    bad = [p.label for p in ps if not geo.sound(p)]
    print(len(ps), "parts", f"{time.time() - t0:.1f}s", "unsound:", bad)
    for p in ps:
        bb = p.bounding_box()
        print(f"{p.label:36s} vol {p.volume:10.0f}  y[{bb.min.Y:7.1f},{bb.max.Y:7.1f}]  "
              f"r~[{min(abs(bb.min.X), abs(bb.max.X)):6.1f}..{max(abs(bb.min.X), abs(bb.max.X), abs(bb.max.Z), abs(bb.min.Z)):6.1f}]")
