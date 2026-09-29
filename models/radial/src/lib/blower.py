"""Blower system: the gear-driven centrifugal supercharger section (y 112..262).

    crank gear 60T m2      `crank:blower_gear` on the crank's rear splines (y 129..142),
                           located by `crank:blower_gear_spacer` against the rear main
                           nut and `crank:blower_gear_lock_ring` behind it
    3 compound idlers      `blowergear<j>:gear` 20T m2 (y 129..143) + 40T m 80/26
                           (y 150..163.5) on bronze bushings `blowergear<j>:bushing`,
                           turning on static shafts `blower:intermediate_shaft_<j>`
                           (r 80, in-plane 60/180/300) held by the case front wall and
                           the diaphragm
    impeller pinion 12T    `impeller:pinion` (y 149.5..164) on `impeller:shaft`
    impeller               `impeller:wheel` O280, 15 radial vanes with twisted
                           inducers at the rear-facing eye; `impeller:nut`;
                           ball bearings `impeller:bearing_front|rear` (inner race +
                           balls) in static outer races `blower:bearing_outer_front|rear`
    statics                `blower:case` (one casting: front flange, gear chamber,
                           collector, shroud, plenum, nine outlet bosses, nine mount
                           lugs, carburettor riser, drain bosses, parting bead),
                           `blower:diaphragm`, `blower:diffuser` (16 curved vanes),
                           machined outlet spigots, machined skins, studs/nuts, plugs,
                           safety wire

Gear frame: local XY with x_dir = +Z, z_dir = ROT_AXIS, so a local polar angle IS
the in-plane angle. Tooth clocking at theta = 0 (tooth in gap on every line of
centres; idler j at in-plane phi_j = 60, 180, 300):
    crank 60T     tooth centres 0 + 6k         (a tooth points at every idler)
    idler 20T     tooth centres phi_j+189+18k  (a gap faces the crank axis)
    idler 40T     tooth centres phi_j+180+9k   (a tooth points at the crank axis)
    pinion 12T    tooth centres 15 + 30k       (a gap faces every idler)
The idler proto is authored at phi = 0 and rotated about the crank axis, so the
three idlers share geometry.

INTERFACES (engine frame)
  * Front flange y 112..124 on the crankcase rear face; 18 holes O10.5 on r 245 at
    10 + 20 j (crankcase studs/nuts; nut seat y 124).
  * Outlet k (k = 1..9) at in-plane b_k = ALPHA(k) - 9.7, purely RADIAL axis
    (-sin b_k, 0, cos b_k) in the plane y = 200; machined slip spigot OD 56 /
    bore 48, end face centre at r 296, y 200 (hose bead O59 14..16.5 mm back).
  * Mount lugs at in-plane ALPHA(k): rear-facing machined pads y 262, bolt hole
    O14.5 along +Y at r 288, pad O44.
  * Carburettor pad: face z = -300 (normal -Z), x +-62, y 236..288, centre
    (0, 262, -300); throat 88 x 36 (x +-44, y 244..280); 4 x M8 studs at
    (+-53, 241.5) and (+-53, 282.5), 20 mm proud. The riser runs under the
    accessory case (z <= -235 behind y 262), forward of its sump (y 291).
  * Accessory flange: machined face y 262, r 150..233; 18 x M8 studs on r 200 at
    10 + 20 j, nuts assume a 12 mm accessory flange (seat y 274); rear bore O44
    (the rear impeller bearing housing) open to the rear.
"""

from __future__ import annotations

import math

from cadgen import build123d as bd

from lib import castings as C
from lib import fasteners as F
from lib import geo, kin
from lib import palette as P
from lib import spec as S

MATERIALS = ("bronze", "case_silver", "fastener", "gasket", "machined_alu", "safety_wire", "steel_machined")

_ROT = S.ROT_AXIS
BACKLASH = 0.12

# gear numbers
(ZC, MC), ((ZI1, MI1), (ZI2, MI2)), (ZP, MP) = S.BLOWER_CRANK_GEAR, S.BLOWER_INTERMEDIATE, S.BLOWER_PINION
IDLER_R = S.BLOWER_INTERMEDIATE_R
IDLER_ANGLES = S.BLOWER_INTERMEDIATE_ANGLES

CRANK_GEAR_Y = (129.0, 142.0)
SMALL_Y = (129.0, 143.0)
BIG_Y = (150.0, 163.5)
PINION_Y = (149.5, 164.0)
IDLER_HUB_R = 18.0
IDLER_BORE_R = 12.5
IDLER_SHAFT_R = 10.0

# case stations
FRONT_WALL = (112.0, 126.0)
DIAPHRAGM = (165.5, 175.5)
LEDGE_Y = 165.3
REAR_FACE_Y = 261.6          # cast rear face; the machined skins make it 262
Y_REAR = 262.0

# outlets
OUT_TILT = 0.0                     # purely radial (intake builder's straight pipe + one elbow)
OUT_PHASE = -9.7                   # in-plane offset from the cylinder axis
OUT_R0, OUT_Y0 = 252.0, 200.0      # axis crosses the drum surface here (elbow room to the head stub at y 124)
OUT_BOSS_S = (-18.0, 24.0)
OUT_BOSS_R = 33.0
OUT_SPIGOT_S = (24.0, 44.0)
OUT_SPIGOT_R = 28.0
OUT_BORE_R = 24.0

# mount lugs
LUG_R = 288.0
LUG_Y = (240.0, REAR_FACE_Y)
LUG_W = 46.0

# carburettor riser
PAD_Z = -300.0
SKIN = 0.4


def outlet_angle(k):
    return S.ALPHA(k) + OUT_PHASE


def outlet_axis(k):
    u = S.inplane(outlet_angle(k))
    c, s = math.cos(math.radians(OUT_TILT)), math.sin(math.radians(OUT_TILT))
    return (u[0] * c, -s, u[2] * c)


def outlet_point(k, s):
    """Point on outlet k's axis, s mm outward from the drum crossing."""
    c, sn = math.cos(math.radians(OUT_TILT)), math.sin(math.radians(OUT_TILT))
    return S.inplane(outlet_angle(k), OUT_R0 + s * c, OUT_Y0 - s * sn)


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _style(shape, label, color):
    return P.style(shape, label, color)


def _one(shape):
    sols = shape.solids()
    if len(sols) == 1:
        return sols[0]
    return max(sols, key=lambda s: s.volume)


def _V(p):
    return bd.Vector(p[0], p[1], 0.0)


def _prof_face(start, segs):
    """Closed (r, y) profile in the XY plane: segs = ("L", p) | ("A", mid, end) |
    ("S", [pts], (t0, t1) or None). Closed back to start with a line."""
    cur = start
    edges = []
    for sg in segs:
        if sg[0] == "L":
            edges.append(bd.Line(_V(cur), _V(sg[1])))
            cur = sg[1]
        elif sg[0] == "A":
            edges.append(bd.ThreePointArc(_V(cur), _V(sg[1]), _V(sg[2])))
            cur = sg[2]
        else:
            pts = [cur] + list(sg[1])
            tans = sg[2] if len(sg) > 2 else None
            if tans:
                edges.append(bd.Spline(*[_V(p) for p in pts], tangents=[_V(tans[0]), _V(tans[1])]))
            else:
                edges.append(bd.Spline(*[_V(p) for p in pts]))
            cur = pts[-1]
    if abs(cur[0] - start[0]) + abs(cur[1] - start[1]) > 1e-9:
        edges.append(bd.Line(_V(cur), _V(start)))
    return bd.Face(bd.Wire(edges))


def _rev(face):
    return bd.revolve(face, axis=bd.Axis.Y, revolution_arc=360.0)


def _revp(pts):
    return geo.revolve_y(pts)


def _fillet_pt(corner, r, d_in, d_out):
    """Fillet of radius r at a 90-degree corner: (start, mid, end) given the unit
    directions arriving (d_in) and leaving (d_out)."""
    cx, cy = corner
    s = (cx - d_in[0] * r, cy - d_in[1] * r)
    e = (cx + d_out[0] * r, cy + d_out[1] * r)
    c = (s[0] + d_out[0] * r, s[1] + d_out[1] * r)
    m = ((s[0] + e[0]) / 2 - c[0], (s[1] + e[1]) / 2 - c[1])
    n = math.hypot(*m)
    mid = (c[0] + m[0] / n * r, c[1] + m[1] / n * r)
    return s, mid, e


def _gear_loc(axis_xz=(0.0, 0.0), y=0.0):
    pl = bd.Plane(origin=(axis_xz[0], y, axis_xz[1]), x_dir=(0, 0, 1), z_dir=_ROT)
    return pl.location


def _span(face, y0, y1, axis_xz=(0.0, 0.0)):
    """Extrude a gear-frame face so it spans engine y in [y0, y1]."""
    return _gear_loc(axis_xz, y1) * bd.extrude(face, amount=y1 - y0)


def _pz(b_deg, r):
    p = S.inplane(b_deg, r)
    return (p[0], p[2])


# ---------------------------------------------------------------------------
# Involute spur outline (same construction as the reduction's)
# ---------------------------------------------------------------------------
def _inv(a):
    return math.tan(a) - a


def gear_face(z, m, r_a, r_f, c0_deg, thick_delta=-BACKLASH, alpha_deg=20.0, n_flank=10):
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
        return bd.Vector(r * math.cos(a), r * math.sin(a), 0.0)

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


def _tip_limiter(r_a, y0, y1, c=0.7, axis_xz=(0.0, 0.0)):
    body = _revp([(0.0, y0), (r_a - c, y0), (r_a + 0.3, y0 + c + 0.3), (r_a + 0.3, y1 - c - 0.3),
                  (r_a - c, y1), (0.0, y1)])
    if axis_xz != (0.0, 0.0):
        body = bd.Pos(axis_xz[0], 0, axis_xz[1]) * body
    return body


def _rim(z, m):
    rp = z * m / 2.0
    return rp, rp + m, rp - 1.25 * m


# ---------------------------------------------------------------------------
# Crank gear (crank group)
# ---------------------------------------------------------------------------
def _xz_slab(sketch, y_lo, y_hi):
    pl = bd.Plane(origin=(0, y_hi, 0), x_dir=(1, 0, 0), z_dir=(0, -1, 0))
    return bd.extrude(pl * sketch, amount=y_hi - y_lo)


def _spline_bore(y_lo, y_hi):
    """Internal-spline cutter matching the crank's 18 splines (r 27..30, w 5, at in-plane 20 i)."""
    slots = [bd.Rot(0, 0, 20.0 * i) * bd.Pos(0, 28.6) * bd.Rectangle(5.6, 4.6) for i in range(18)]
    sk = (bd.Circle(27.4) + slots) & bd.Circle(30.45)
    return _xz_slab(sk, y_lo, y_hi)


def crank_gear():
    rp, ra, rf = _rim(ZC, MC)
    y0, y1 = CRANK_GEAR_Y
    g = _span(gear_face(ZC, MC, ra, rf, 0.0), y0, y1)
    g = g & _tip_limiter(ra, y0, y1)
    # web recesses both faces + six lightening holes
    rec_f = _revp([(38.0, y0 - 1), (52.0, y0 - 1), (52.0, y0 + 2.0), (50.0, y0 + 3.0), (40.0, y0 + 3.0), (38.0, y0 + 2.0)])
    rec_r = _revp([(38.0, y1 - 2.0), (40.0, y1 - 3.0), (50.0, y1 - 3.0), (52.0, y1 - 2.0), (52.0, y1 + 1), (38.0, y1 + 1)])
    holes = [geo.cyl_y(y0 - 1, y1 + 1, 11.0, *_pz(30.0 + 60.0 * i, 45.0)) for i in range(6)]
    return C.cut_all(g, [rec_f, rec_r, _spline_bore(y0 - 1, y1 + 1)] + holes)


def crank_gear_spacer():
    y0, y1 = 110.0, CRANK_GEAR_Y[0]
    return _revp([(30.2, y0), (40.0, y0), (40.0, y0 + 3.0), (35.0, y0 + 6.0), (35.0, y1 - 0.5),
                  (34.5, y1), (30.2, y1)])


def crank_gear_lock_ring():
    y0 = CRANK_GEAR_Y[1]
    ring = _revp([(30.4, y0), (39.0, y0), (39.5, y0 + 0.5), (39.5, y0 + 2.5), (30.4, y0 + 2.5)])
    return ring


# ---------------------------------------------------------------------------
# Compound idler (authored at in-plane 0, rotated to 60 / 180 / 300)
# ---------------------------------------------------------------------------
def _idler_centre0():
    return _pz(0.0, IDLER_R)


def idler_proto():
    cxz = _idler_centre0()
    _, ra1, rf1 = _rim(ZI1, MI1)
    rp2, _, _ = _rim(ZI2, MI2)
    ra2 = rp2 + 0.9 * MI2                  # tip relief against the 12T pinion's flanks
    rf2 = rp2 - 1.25 * MI2
    small = _span(gear_face(ZI1, MI1, ra1, rf1, 189.0), *SMALL_Y, axis_xz=cxz)
    small = small & _tip_limiter(ra1, *SMALL_Y, c=0.6, axis_xz=cxz)
    big = _span(gear_face(ZI2, MI2, ra2, rf2, 180.0), *BIG_Y, axis_xz=cxz)
    big = big & _tip_limiter(ra2, *BIG_Y, c=0.8, axis_xz=cxz)
    hub = bd.Pos(cxz[0], 0, cxz[1]) * _revp([(0.0, SMALL_Y[1] - 0.5), (IDLER_HUB_R, SMALL_Y[1] - 0.5),
                                              (IDLER_HUB_R, BIG_Y[0] + 0.5), (0.0, BIG_Y[0] + 0.5)])
    body = C.fuse_all([small, hub, big])
    bore = geo.cyl_y(SMALL_Y[0] - 1, BIG_Y[1] + 1, 2 * IDLER_BORE_R, cxz[0], cxz[1])
    # web recess + lightening holes in the big gear
    rec = bd.Pos(cxz[0], 0, cxz[1]) * _revp([(24.0, BIG_Y[1] - 3.0), (26.0, BIG_Y[1] - 4.0), (48.0, BIG_Y[1] - 4.0),
                                              (50.0, BIG_Y[1] - 3.0), (50.0, BIG_Y[1] + 1), (24.0, BIG_Y[1] + 1)])
    holes = []
    for i in range(6):
        a = math.radians(30.0 + 60.0 * i)
        holes.append(geo.cyl_y(BIG_Y[0] - 1, BIG_Y[1] + 1, 13.0,
                               cxz[0] + 37.0 * math.sin(a), cxz[1] + 37.0 * math.cos(a)))
    return C.cut_all(body, [bore, rec] + holes)


def idler_bushing_proto():
    cxz = _idler_centre0()
    y0, y1 = SMALL_Y[0], BIG_Y[1]
    return bd.Pos(cxz[0], 0, cxz[1]) * _revp([(IDLER_SHAFT_R + 0.15, y0), (IDLER_BORE_R, y0), (IDLER_BORE_R, y1),
                                              (IDLER_SHAFT_R + 0.15, y1)])


def idler_shaft_proto():
    cxz = _idler_centre0()
    r = IDLER_SHAFT_R
    return bd.Pos(cxz[0], 0, cxz[1]) * _revp([(0.0, 115.0), (r - 0.6, 115.0), (r, 115.6), (r, 126.0), (15.0, 126.0),
                                              (15.0, 128.5), (r, 128.5), (r, DIAPHRAGM[1] - 0.6),
                                              (r - 0.6, DIAPHRAGM[1]), (3.0, DIAPHRAGM[1]), (3.0, 140.0),
                                              (0.0, 140.0)])


# ---------------------------------------------------------------------------
# Impeller group
# ---------------------------------------------------------------------------
VANE_EDGE = [(140.0, 198.0), (130.0, 200.0), (118.0, 205.0), (106.0, 214.0), (98.0, 222.0), (95.0, 228.0)]
HUB_LINE = [(140.0, 184.0), (115.0, 186.0), (90.0, 190.0), (70.0, 195.0), (55.0, 202.0), (45.0, 208.0)]
N_VANES = 15
VANE_T = 3.0
INDUCER_Y = (208.0, 228.0)
INDUCER_TWIST = 24.0


def _edge_r(y):
    """Radius of the vane's outer (shroud-side) edge at station y."""
    pts = sorted(VANE_EDGE, key=lambda p: p[1])
    for (r0, y0), (r1, y1) in zip(pts, pts[1:]):
        if y0 <= y <= y1:
            return r0 + (r1 - r0) * (y - y0) / (y1 - y0)
    return pts[-1][0] if y > pts[-1][1] else pts[0][0]


def impeller_plate():
    y0 = 179.5
    corner = _fillet_pt((45.0, 229.0), 4.0, (0, 1), (-1, 0))
    segs = [("L", (140.0, 181.5)), ("L", (140.0, 184.0)),
            ("S", HUB_LINE[1:]), ("L", (45.0, corner[0][1])), ("A", corner[1], corner[2]),
            ("L", (18.0, 229.0))]
    return _rev(_prof_face((18.0, y0), segs))


def _vane_main():
    y_top = INDUCER_Y[0] + 0.5
    pts = [(44.0, 207.0), (44.0, y_top), (_edge_r(y_top), y_top), (118.0, 205.0), (130.0, 200.0), (139.7, 198.0),
           (139.7, 183.0), (115.0, 185.0), (90.0, 189.0), (70.0, 194.0), (55.0, 201.0)]
    face = bd.make_face(bd.Polyline(*[(0.0, y, r) for r, y in pts], close=True).edges())
    return bd.extrude(face, amount=VANE_T / 2.0, dir=(1, 0, 0), both=True)


def _vane_inducer():
    secs = []
    n = 6
    for i in range(n):
        y = INDUCER_Y[0] + (INDUCER_Y[1] - INDUCER_Y[0]) * i / (n - 1)
        r0, r1 = 44.0, _edge_r(y)
        phi = INDUCER_TWIST * (i / (n - 1)) ** 1.6
        pl = bd.Plane(origin=(0, y, 0), x_dir=(1, 0, 0), z_dir=(0, 1, 0))
        f = (pl * (bd.Pos(0, -(r0 + r1) / 2.0) * bd.Rectangle(VANE_T, r1 - r0))).faces()[0]
        secs.append(geo.axis_rotation(_ROT, phi) * f)
    return bd.loft(secs, ruled=False)


def impeller_wheel():
    plate = impeller_plate()
    vane = C.fuse_all([_vane_main(), _vane_inducer()])
    vanes = [geo.axis_rotation(_ROT, 360.0 * i / N_VANES) * vane for i in range(N_VANES)]
    return _one(C.fuse_all([plate] + vanes))


def impeller_shaft():
    return _revp([(5.0, 148.0), (9.4, 148.0), (10.0, 148.6), (10.0, 164.0), (15.0, 164.0), (15.0, 179.0),
                  (18.0, 179.0), (18.0, 229.0), (12.0, 229.0), (12.0, 249.4), (11.4, 250.0), (5.0, 250.0)])


def pinion():
    rp, ra, rf = _rim(ZP, MP)
    rf = rp - 1.35 * MP
    g = _span(gear_face(ZP, MP, ra, rf, 15.0), *PINION_Y)
    g = g & _tip_limiter(ra, *PINION_Y, c=0.6)
    return g - geo.cyl_y(PINION_Y[0] - 1, PINION_Y[1] + 1, 20.0)


def impeller_nut():
    y0, h = 229.0, 7.0
    body = _revp([(12.0, y0), (21.4, y0), (22.0, y0 + 0.6), (22.0, y0 + h - 0.8), (21.2, y0 + h),
                  (12.6, y0 + h), (12.0, y0 + h - 0.6)])
    slots = [geo.axis_rotation(_ROT, 45.0 + 90.0 * i) * bd.Pos(0, y0 + h / 2.0 + 1.0, 22.0)
             * bd.Box(6.0, h, 6.0) for i in range(4)]
    return C.cut_all(body, slots)


def _bearing(y0, y1, ri, ro_i, ri_o, ro, ball_d, n):
    """(inner race + balls, outer race). Grooves: inner groove r = ball/2 - 0.1 (balls
    fused into it), outer groove ball/2 + 0.3.

    Each ball's sphere has its poles along the bearing axis (+-Y) and its seam meridian on
    the outward radial, so neither lies in the seat where the ball joins the inner race. With
    the default sphere (poles +-Z, seam through +X) the seam or a pole ran through that seat on
    most balls, and OCCT's STEP round trip re-trimmed some of those spheres on the wrong side
    of the seat loop: the races read back 19 % (front) and 7.5 % (rear) short."""
    ym = (y0 + y1) / 2.0
    rpc = (ro_i + ri_o) / 2.0
    rb = ball_d / 2.0
    inner = _revp([(ri, y0 + 0.5), (ri + 0.5, y0), (ro_i - 0.5, y0), (ro_i, y0 + 0.5), (ro_i, y1 - 0.5),
                   (ro_i - 0.5, y1), (ri + 0.5, y1), (ri, y1 - 0.5)])
    outer = _revp([(ri_o, y0 + 0.5), (ri_o + 0.5, y0), (ro - 0.5, y0), (ro, y0 + 0.5), (ro, y1 - 0.5),
                   (ro - 0.5, y1), (ri_o + 0.5, y1), (ri_o, y1 - 0.5)])
    tor_o = bd.Pos(0, ym, 0) * bd.Rot(90, 0, 0) * bd.Torus(rpc, rb + 0.3)
    outer = outer - tor_o
    tor_i = bd.Pos(0, ym, 0) * bd.Rot(90, 0, 0) * bd.Torus(rpc, rb - 0.1)
    inner = inner - tor_i
    balls = [bd.Solid.make_sphere(rb, geo.plane(S.inplane(360.0 * i / n, rpc, ym), (0.0, 1.0, 0.0),
                                                S.inplane(360.0 * i / n)))
             for i in range(n)]
    inner = _one(C.fuse_all([inner] + balls))
    return inner, outer


# ---------------------------------------------------------------------------
# Static internals
# ---------------------------------------------------------------------------
def diaphragm():
    y0, y1 = DIAPHRAGM
    body = _revp([(27.5, y0), (205.0, y0), (205.0, y1 - 1.0), (204.0, y1), (40.0, y1), (36.0, y1 + 2.0),
                  (27.5, y1 + 2.0)])
    holes = [geo.axis_rotation(_ROT, a) * geo.cyl_y(y0 - 1, y1 + 3, 2 * IDLER_SHAFT_R + 0.02, *_idler_centre0())
             for a in IDLER_ANGLES]
    # lightening windows between the idler shafts (flow-balance holes of the gear chamber)
    wins = [geo.cyl_y(y0 - 1, y1 + 3, 34.0, *_pz(a + 60.0, 150.0)) for a in IDLER_ANGLES]
    return C.cut_all(body, holes + wins)


def _diffuser_vane():
    n = 18
    r0, r1 = 150.0, 201.0
    k = 1.0 / math.tan(math.radians(18.0))
    cen, nrm = [], []
    for i in range(n + 1):
        s = i / n
        r = r0 + (r1 - r0) * s
        b = math.degrees(k * math.log(r / r0))
        x, z = _pz(b, r)
        cen.append((x, z, s))
    pts_l, pts_r = [], []
    for i, (x, z, s) in enumerate(cen):
        xa, za, _ = cen[max(0, i - 1)]
        xb, zb, _ = cen[min(n, i + 1)]
        tx, tz = xb - xa, zb - za
        L = math.hypot(tx, tz)
        nx, nz = -tz / L, tx / L
        t = 0.5 + 2.6 * math.sin(math.pi * min(1.0, s ** 0.75)) ** 0.9 + 0.5 * s
        pts_l.append((x + nx * t / 2, z + nz * t / 2))
        pts_r.append((x - nx * t / 2, z - nz * t / 2))
    # sketch in the plane y = 183.5 (local u = x, v = -z), extruded +Y
    def U(p):
        return bd.Vector(p[0], -p[1], 0)
    le_mid = (cen[0][0] - (cen[1][0] - cen[0][0]) * 0.1, cen[0][1] - (cen[1][1] - cen[0][1]) * 0.1)
    edges = [bd.Spline(*[U(p) for p in pts_l]), bd.Line(U(pts_l[-1]), U(pts_r[-1])),
             bd.Spline(*[U(p) for p in reversed(pts_r)]),
             bd.ThreePointArc(U(pts_r[0]), U(le_mid), U(pts_l[0]))]
    face = bd.Face(bd.Wire(edges))
    pl = bd.Plane(origin=(0, 183.5, 0), x_dir=(1, 0, 0), z_dir=(0, 1, 0))
    return bd.extrude(pl * face, amount=198.0 - 183.5)


def diffuser():
    plate = _revp([(147.0, 175.7), (205.0, 175.7), (205.0, 183.2), (204.2, 184.0), (146.0, 184.0),
                   (146.0, 176.7)])
    vane = _diffuser_vane()
    vanes = [geo.axis_rotation(_ROT, 360.0 * i / 16) * vane for i in range(16)]
    return _one(C.fuse_all([plate] + vanes))


# ---------------------------------------------------------------------------
# The case casting
# ---------------------------------------------------------------------------
SHROUD_FRONT = [(142.0, 200.2), (132.0, 202.2), (120.0, 207.2), (108.0, 216.2), (100.0, 224.2), (97.0, 230.0)]
SHROUD_REAR = [(146.0, 205.5), (136.0, 207.5), (124.0, 211.5), (113.0, 219.5), (106.0, 226.5), (103.0, 232.0)]


CASE_REAR_Y = 250.0          # main case rear face (the rear cover's gasket seats here)
CASE_BORE_R = 208.0          # main case bore behind the collector: the internals (r <= 205) pass it
COVER_SPIGOT_R = 207.5
COVER_FLANGE_R = 229.0
GASKET_T = 0.8
COVER_Y0 = CASE_REAR_Y + GASKET_T
COVER_SCREW_R = 219.0
COVER_SCREWS = [20.0 * j for j in range(18)]
CB_DEPTH = 7.0               # socket-head counterbore (heads sit below the accessory face)


def _case_revolve():
    """Main case: flange, gear chamber, collector; open to the rear through a
    bore r 208 so the diaphragm, diffuser, impeller and gears withdraw rearward."""
    f_w = _fillet_pt((226.0, 124.0), 5.0, (-1, 0), (0, 1))          # flange back -> waist
    segs = [
        ("L", (262.0, 112.0)), ("L", (262.0, 121.5)), ("L", (259.5, 124.0)),
        ("L", f_w[0]), ("A", f_w[1], f_w[2]), ("L", (226.0, 137.0)),
        ("S", [(229.5, 146.0), (238.0, 154.0), (247.5, 160.5), (252.0, 170.0)], ((0, 1), (0, 1))),
        ("L", (252.0, 212.0)),
        ("S", [(250.5, 226.0), (245.5, 236.0), (240.0, 243.5), (238.0, 248.5)], ((0, 1), (0, 1))),
        ("L", (236.5, CASE_REAR_Y)), ("L", (CASE_BORE_R + 0.6, CASE_REAR_Y)), ("L", (CASE_BORE_R, CASE_REAR_Y - 0.6)),
        ("L", (CASE_BORE_R, 214.0)), ("L", (244.0, 214.0)), ("L", (244.0, LEDGE_Y)),
        ("L", (200.0, LEDGE_Y)), ("L", (200.0, 158.0)), ("L", (212.0, 150.0)), ("L", (212.0, 130.0)),
        ("L", (208.0, FRONT_WALL[1])), ("L", (44.0, FRONT_WALL[1])),
    ]
    return _rev(_prof_face((44.0, FRONT_WALL[0]), segs))


def _cover_revolve():
    """Rear cover: flange on the case's rear face, a spigot in the case bore, the
    impeller shroud, the plenum, the rear wall (accessory face) and the rear
    bearing boss. Every face of it widens rearward, so it withdraws rearward."""
    boss_f = _fillet_pt((34.0, CASE_REAR_Y), 7.0, (0, 1), (1, 0))
    pl_f = _fillet_pt((200.0, CASE_REAR_Y), 6.0, (1, 0), (0, -1))
    segs = [
        ("L", (COVER_FLANGE_R - 2.5, REAR_FACE_Y)), ("L", (COVER_FLANGE_R, REAR_FACE_Y - 2.5)),
        ("L", (COVER_FLANGE_R, COVER_Y0)), ("L", (COVER_SPIGOT_R, COVER_Y0)),
        ("L", (COVER_SPIGOT_R, 199.5)), ("L", (206.5, 198.5)), ("L", (146.0, 198.5)),
        ("S", SHROUD_FRONT),
        ("L", (97.0, 236.0)), ("L", (103.0, 236.0)), ("L", (103.0, 232.0)),
        ("S", list(reversed(SHROUD_REAR[:-1]))),
        ("L", (200.0, 205.5)),
        ("L", pl_f[2]), ("A", pl_f[1], pl_f[0]),
        ("L", boss_f[2]), ("A", boss_f[1], boss_f[0]),
        ("L", (34.0, 237.0)), ("L", (22.0, 237.0)),
    ]
    return _rev(_prof_face((22.0, REAR_FACE_Y), segs))


def _outlet_boss(k):
    p0, p1 = outlet_point(k, OUT_BOSS_S[0]), outlet_point(k, OUT_BOSS_S[1])
    boss = geo.cyl_along(p0, p1, 2 * OUT_BOSS_R)
    return boss


def _lug(k):
    b = S.ALPHA(k)
    y0, y1 = LUG_Y
    arm = bd.Box(LUG_W, y1 - y0, LUG_R - 232.0, align=(bd.Align.CENTER, bd.Align.MIN, bd.Align.MIN))
    arm = bd.Pos(0, y0, 232.0) * arm
    eye = geo.cyl_y(y0, y1, LUG_W, 0.0, LUG_R)
    lug = arm + eye
    # soften the lug's radial edges (parallel to Y)
    edges = [e for e in lug.edges() if e.geom_type.name == "LINE"
             and abs(e.tangent_at(0.5).Y) > 0.99 and C.edge_center(e).Z > 240.0]
    lug, _ = C.safe_fillet(lug, edges, 4.0, min_r=1.0)
    return geo.axis_rotation(_ROT, b) * lug


def _gusset(k):
    """Cast web in the lug's radial plane, running forward from the lug onto the drum."""
    pts = [(247.0, 204.0), (253.0, 204.0), (279.0, 240.5), (240.0, 240.5), (240.0, 215.0), (245.0, 213.5)]  # (r, y)
    face = bd.make_face(bd.Polyline(*[(0.0, y, r) for r, y in pts], close=True).edges())
    web = bd.extrude(face, amount=6.0, dir=(1, 0, 0), both=True)
    edges = [e for e in web.edges() if abs(e.tangent_at(0.5).X) > 0.99 and C.edge_center(e).Z > 246.0]
    web, _ = C.safe_fillet(web, edges, 5.0, min_r=1.0)
    return geo.axis_rotation(_ROT, S.ALPHA(k)) * bd.Pos(-13.0, 0, 0) * web


PAD_Y = (236.0, 288.0)       # pad footprint (y); x +-62
RISER_Y0 = 240.0
DUCT_UP = (243.0, 249.9)     # riser duct: through the case bore and the cover's spigot window
DUCT_LO = (244.0, 280.0)     # carburettor throat at the pad


def _rbox(x, y0, y1, z0, z1, r):
    b = bd.Pos(0, y0, z0) * bd.Box(x, y1 - y0, z1 - z0, align=(bd.Align.CENTER, bd.Align.MIN, bd.Align.MIN))
    edges = [e for e in b.edges() if abs(e.tangent_at(0.5).Z) > 0.99]
    b, _ = C.safe_fillet(b, edges, r, min_r=1.0)
    return b


def _riser():
    """Carburettor riser under the rear of the case. The part behind y 262 stays
    below z -235 (the accessory case above) and forward of y 290 (its sump)."""
    top = _rbox(104.0, RISER_Y0, REAR_FACE_Y - 0.1, PAD_Z + 9.0, -222.0, 12.0)
    top = top - geo.cyl_y(CASE_REAR_Y - 0.5, Y_REAR + 5.0, 2 * (COVER_FLANGE_R + 0.6))
    tail = _rbox(104.0, RISER_Y0, PAD_Y[1] - 4.0, PAD_Z + 9.0, -235.0, 12.0)
    flange = _rbox(124.0, PAD_Y[0], PAD_Y[1], PAD_Z + SKIN, PAD_Z + 10.0, 6.0)
    # 3 mm chamfer on the flange's top front edge (clears the intake hose clamp on pipe 6)
    zt = PAD_Z + 10.0
    tri = [(PAD_Y[0] - 1.0, zt - 4.0), (PAD_Y[0] + 4.0, zt + 1.0), (PAD_Y[0] - 1.0, zt + 1.0)]
    face = bd.make_face(bd.Polyline(*[(0.0, y, z) for y, z in tri], close=True).edges())
    flange = flange - bd.extrude(face, amount=70.0, dir=(1, 0, 0), both=True)
    return C.fuse_all([top, tail, flange])


def _riser_duct():
    up = _rbox(88.0, DUCT_UP[0], DUCT_UP[1], -250.0, -195.0, 6.0)
    lo = _rbox(88.0, DUCT_LO[0], DUCT_LO[1], PAD_Z - 5.0, -248.0, 8.0)
    return [up.fuse(lo).clean()]


TAP_M8 = 2 * F._shank_radius(8.0) + 0.05     # stud shank is the thread's pitch diameter
TAP_M6 = 2 * F._shank_radius(6.0) + 0.05
PAD_STUDS = [(-53.0, 241.5), (53.0, 241.5), (-53.0, 282.5), (53.0, 282.5)]
DRAIN_COLLECTOR = (168.0, 190.0)       # in-plane angle, y
DRAIN_GEAR = (180.0, 141.0)
ACC_STUD_R = 200.0
ACC_STUDS = [10.0 + 20.0 * j for j in range(18)]
FRONT_HOLES = [10.0 + 20.0 * j for j in range(18)]


def _drain_boss(b, y, r0, r1, rad=12.0):
    return geo.cyl_along(S.inplane(b, r0, y), S.inplane(b, r1, y), 2 * rad)


def _parting_bead():
    y = 217.0
    return _revp([(248.0, y - 0.6), (251.2, y - 0.6), (251.7, y - 0.2), (251.7, y + 0.2), (251.2, y + 0.6),
                  (248.0, y + 0.6)])


_INFO: dict = {}


def case():
    import time
    t0 = time.time()
    rev = _case_revolve()
    adds = [_outlet_boss(k) for k in range(1, 10)] + [_lug(k) for k in range(1, 10)] + [_riser()]
    adds += [_gusset(k) for k in range(1, 10)]
    adds.append(_drain_boss(DRAIN_COLLECTOR[0], DRAIN_COLLECTOR[1], 247.0, 262.0))
    adds.append(_drain_boss(DRAIN_GEAR[0], DRAIN_GEAR[1], 218.0, 238.0))
    body = _one(C.fuse_all([rev] + adds))
    _INFO["t_fuse"] = round(time.time() - t0)
    # cast root blends: outlet bosses (their root curves on the outer skin), then lugs
    import numpy as np

    def on_boss(e):
        c = C.edge_center(e)
        if 164.0 < c.Y < 215.0 and math.hypot(c.X, c.Z) < 247.0:
            return False                      # the boss's cut through the collector's inner wall
        pts = [e.position_at(t) for t in (0.0, 0.33, 0.66, 1.0)]
        for k in range(1, 10):
            p0, a = np.array(outlet_point(k, 0.0)), np.array(outlet_axis(k))
            ok = True
            for p in pts:
                v = np.array([p.X, p.Y, p.Z]) - p0
                sa = v @ a
                if abs(np.linalg.norm(v - sa * a) - OUT_BOSS_R) > 0.05 or sa > OUT_BOSS_S[1] - 0.5:
                    ok = False
                    break
            if ok:
                return True
        return False

    body, got = C.safe_fillet(body, [e for e in body.edges() if on_boss(e)], 6.0, min_r=2.0)
    _INFO["outlet_fillet"] = got

    def on_lug(e):
        if e.geom_type.name in ("LINE", "CIRCLE"):
            return False
        c = C.edge_center(e)
        r = math.hypot(c.X, c.Z)
        if c.Z < -215.0 and abs(c.X) < 70.0:
            return False
        return 225.0 < r < 252.0 and 236.0 < c.Y < 259.0

    body, got = C.safe_fillet(body, [e for e in body.edges() if on_lug(e)], 5.0, min_r=1.5)
    _INFO["lug_fillet"] = got
    _INFO["t_fillet"] = round(time.time() - t0)
    bead = _parting_bead()
    body = _one(C.fuse_all([body, bead]))
    # holes
    tools = []
    for k in range(1, 10):
        tools.append(geo.cyl_along(outlet_point(k, -20.0), outlet_point(k, OUT_BOSS_S[1] + 1.0), 2 * OUT_BORE_R))
    for b in FRONT_HOLES:
        x, _, z = S.inplane(b, 245.0)
        tools.append(geo.cyl_y(FRONT_WALL[0] - 1, 124.5, 10.5, x, z))
    for b in COVER_SCREWS:
        x, _, z = S.inplane(b, COVER_SCREW_R)
        tools.append(geo.cyl_y(CASE_REAR_Y - 12.0, CASE_REAR_Y + 1, TAP_M6, x, z))
    for k in range(1, 10):
        x, _, z = S.inplane(S.ALPHA(k), LUG_R)
        tools.append(geo.cyl_y(LUG_Y[0] - 1, Y_REAR + 1, 14.5, x, z))
    for a in IDLER_ANGLES:
        x, z = _pz(a, IDLER_R)
        tools.append(geo.cyl_y(115.0, FRONT_WALL[1] + 1, 2 * IDLER_SHAFT_R + 0.02, x, z))
    tools += _riser_duct()
    for (x, y) in PAD_STUDS:
        tools.append(geo.cyl_along((x, y, PAD_Z - 1), (x, y, PAD_Z + 13.0), TAP_M8))
    b, y = DRAIN_COLLECTOR
    tools.append(geo.cyl_along(S.inplane(b, 243.0, y), S.inplane(b, 263.0, y), 10.2))
    b, y = DRAIN_GEAR
    tools.append(geo.cyl_along(S.inplane(b, 205.0, y), S.inplane(b, 239.0, y), 10.2))
    body = _one(C.cut_all(body, tools))
    _INFO["t_case"] = round(time.time() - t0)
    return body


# ---------------------------------------------------------------------------
# Machined parts on the case
# ---------------------------------------------------------------------------
def outlet_spigot(k):
    """Machined slip spigot: tube OD 56 / bore 48 with a hose bead, seated on the boss face."""
    s0, s1 = OUT_SPIGOT_S
    L = s1 - s0
    r, rb, ri = OUT_SPIGOT_R, OUT_SPIGOT_R + 1.5, OUT_BORE_R
    proto = F._rev([(ri, 0.0), (r - 0.0, 0.0), (r, 0.0), (r, L - 16.5), (rb, L - 15.5), (rb, L - 15.0),
                    (r, L - 14.0), (r, L - 0.8), (r - 0.8, L), (ri + 0.6, L), (ri, L - 0.6)])
    return F.place(proto, outlet_point(k, s0), outlet_axis(k))


def rear_cover():
    body = _cover_revolve()
    tools = [geo.cyl_y(REAR_FACE_Y - 10.0, Y_REAR + 1, TAP_M8, *_pz(b, ACC_STUD_R)) for b in ACC_STUDS]
    for b in COVER_SCREWS:
        x, z = _pz(b, COVER_SCREW_R)
        tools.append(geo.cyl_y(COVER_Y0 - 1, Y_REAR + 1, 6.6, x, z))
        tools.append(geo.cyl_y(REAR_FACE_Y - CB_DEPTH, Y_REAR + 1, 11.0, x, z))
    tools += _riser_duct()
    return _one(C.cut_all(body, tools))


def rear_cover_gasket():
    ring = _revp([(CASE_BORE_R + 1.0, CASE_REAR_Y), (COVER_FLANGE_R, CASE_REAR_Y),
                  (COVER_FLANGE_R, COVER_Y0), (CASE_BORE_R + 1.0, COVER_Y0)])
    holes = [geo.cyl_y(CASE_REAR_Y - 1, COVER_Y0 + 1, 6.6, *_pz(b, COVER_SCREW_R)) for b in COVER_SCREWS]
    return C.cut_all(ring, holes)


def accessory_face():
    ring = _revp([(150.0, REAR_FACE_Y), (COVER_FLANGE_R - 2.6, REAR_FACE_Y), (COVER_FLANGE_R - 2.6, Y_REAR - 0.1),
                  (COVER_FLANGE_R - 2.7, Y_REAR), (150.1, Y_REAR), (150.0, Y_REAR - 0.1)])
    holes = [geo.cyl_y(REAR_FACE_Y - 1, Y_REAR + 1, 8.4, *_pz(b, ACC_STUD_R)) for b in ACC_STUDS]
    holes += [geo.cyl_y(REAR_FACE_Y - 1, Y_REAR + 1, 11.0, *_pz(b, COVER_SCREW_R)) for b in COVER_SCREWS]
    return C.cut_all(ring, holes)


def mount_pad(k):
    x, _, z = S.inplane(S.ALPHA(k), LUG_R)
    return _revp([(7.25, REAR_FACE_Y), (22.0, REAR_FACE_Y), (22.0, Y_REAR - 0.1), (21.9, Y_REAR),
                  (7.35, Y_REAR), (7.25, Y_REAR - 0.1)]).moved(bd.Location((x, 0, z)))


def carb_pad_face():
    plate = _rbox(124.0, PAD_Y[0], PAD_Y[1], PAD_Z, PAD_Z + SKIN, 6.0)
    duct = _rbox(88.0, DUCT_LO[0], DUCT_LO[1], PAD_Z - 1.0, PAD_Z + 2.0, 8.0)
    holes = [geo.cyl_along((x, y, PAD_Z - 1), (x, y, PAD_Z + 2), 8.4) for x, y in PAD_STUDS]
    return C.cut_all(plate, [duct] + holes)


def _wire(points, d=0.8):
    path = bd.Spline(*[bd.Vector(*p) for p in points])
    prof = bd.Plane(origin=path.position_at(0.0), z_dir=path.tangent_at(0.0)) * bd.Circle(d / 2.0)
    return _one(bd.sweep(prof, path=path, is_frenet=False))


def _drilled_plug():
    plug = F.hex_flange_bolt(10.0, 12.0)
    hole = geo.cyl_along((-10.0, 0.0, 4.0), (10.0, 0.0, 4.0), 1.6)
    return plug - hole


# ---------------------------------------------------------------------------
def build() -> list:
    SM, CS, MA, FA, BR, SW = (P.STEEL_MACHINED, P.CASE_SILVER, P.MACHINED_ALU, P.FASTENER,
                              P.BRONZE, P.SAFETY_WIRE)
    parts = []
    # --- crank-driven gear
    parts.append(_style(crank_gear(), "crank:blower_gear", SM))
    parts.append(_style(crank_gear_spacer(), "crank:blower_gear_spacer", SM))
    parts.append(_style(crank_gear_lock_ring(), "crank:blower_gear_lock_ring", SM))
    # --- idlers
    idl, bush, shaft = idler_proto(), idler_bushing_proto(), idler_shaft_proto()
    for j, a in enumerate(IDLER_ANGLES, start=1):
        loc = geo.axis_rotation(_ROT, a)
        parts.append(_style(loc * idl, f"blowergear{j}:gear", SM))
        parts.append(_style(loc * bush, f"blowergear{j}:bushing", BR))
        parts.append(_style(loc * shaft, f"blower:intermediate_shaft_{j}", SM))
    # --- impeller
    parts.append(_style(impeller_wheel(), "impeller:wheel", MA))
    parts.append(_style(impeller_shaft(), "impeller:shaft", SM))
    parts.append(_style(pinion(), "impeller:pinion", SM))
    parts.append(_style(impeller_nut(), "impeller:nut", SM))
    fi, fo = _bearing(166.0, 177.0, 15.0, 19.5, 22.5, 27.5, 6.0, 11)
    ri, ro = _bearing(238.0, 249.0, 12.0, 15.5, 18.5, 22.0, 4.0, 11)
    parts.append(_style(fi, "impeller:bearing_front", SM))
    parts.append(_style(fo, "blower:bearing_outer_front", SM))
    parts.append(_style(ri, "impeller:bearing_rear", SM))
    parts.append(_style(ro, "blower:bearing_outer_rear", SM))
    # --- statics
    parts.append(_style(case(), "blower:case", CS))
    parts.append(_style(diaphragm(), "blower:diaphragm", CS))
    parts.append(_style(diffuser(), "blower:diffuser", MA))
    for k in range(1, 10):
        parts.append(_style(outlet_spigot(k), f"blower:outlet_spigot_{k}", MA))
        parts.append(_style(mount_pad(k), f"blower:mount_pad_{k}", MA))
    parts.append(_style(rear_cover(), "blower:rear_cover", CS))
    parts.append(_style(rear_cover_gasket(), "blower:rear_cover_gasket", P.GASKET))
    parts.append(_style(accessory_face(), "blower:accessory_face", MA))
    screw = F.socket_cap_bolt(6.0, 16.0)
    for i, b in enumerate(COVER_SCREWS, start=1):
        seat = S.inplane(b, COVER_SCREW_R, REAR_FACE_Y - CB_DEPTH)
        parts.append(_style(F.place(screw, seat, (0, 1, 0), S.inplane(b)), f"blower:rear_cover_screw_{i}", FA))
    parts.append(_style(carb_pad_face(), "blower:carb_pad_face", MA))
    # --- hardware
    stud8 = F.stud(8.0, 12.0 + 10.0, 10.0)
    nut8 = F.flange_nut(8.0)
    for i, b in enumerate(ACC_STUDS, start=1):
        radial = S.inplane(b)
        parts.append(_style(F.place(stud8, S.inplane(b, ACC_STUD_R, Y_REAR), (0, 1, 0), radial),
                            f"blower:accessory_stud_{i}", FA))
        parts.append(_style(F.place(nut8, S.inplane(b, ACC_STUD_R, Y_REAR + 12.0), (0, 1, 0), radial),
                            f"blower:accessory_nut_{i}", FA))
    pstud = F.stud(8.0, 20.0, 10.0)
    for i, (x, y) in enumerate(PAD_STUDS, start=1):
        parts.append(_style(F.place(pstud, (x, y, PAD_Z), (0, 0, -1), (1, 0, 0)), f"blower:carb_stud_{i}", FA))
    plug = _drilled_plug()
    heads = []
    for name, (b, y), r in (("collector", DRAIN_COLLECTOR, 262.0), ("gear", DRAIN_GEAR, 238.0)):
        radial = S.inplane(b)
        parts.append(_style(F.place(plug, S.inplane(b, r, y), radial, (0, 1, 0)), f"blower:drain_{name}_bolt", FA))
        heads.append((b, y, r))
    # safety wire: the two drain plugs wired to each other
    (b1, y1, r1), (b2, y2, r2) = heads
    # each end runs straight through its plug's cross-drilled head (hole along Y at r + 4)
    pts = [S.inplane(b1, r1 + 4.0, y1 - 1.0), S.inplane(b1, r1 + 4.0, y1 - 6.0), S.inplane(b1, r1 + 4.0, y1 - 11.0),
           S.inplane(b1 + 2.0, r1 + 3.0, y1 - 20.0),
           S.inplane((b1 + b2) / 2.0, 262.0, 158.0), S.inplane(b2 - 1.5, r2 + 7.0, y2 + 16.0),
           S.inplane(b2, r2 + 4.0, y2 + 11.0), S.inplane(b2, r2 + 4.0, y2 + 6.0), S.inplane(b2, r2 + 4.0, y2 + 1.0)]
    parts.append(_style(_wire(pts), "blower:drain_wire", SW))
    return parts


if __name__ == "__main__":
    import time
    t0 = time.time()
    ps = build()
    print(f"{len(ps)} leaves in {time.time() - t0:.0f}s; info {_INFO}")
    bad = [p.label for p in ps if not geo.sound(p)]
    print("unsound:", bad)
