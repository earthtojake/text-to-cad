"""Cam system: cam ring (two roller-envelope lobe tracks + internal gear), its
drive (crank gear 32T -> compound idler 48T/15T -> ring 80T internal), and the
18 roller tappets with their bronze guides.

Kinematics come from `kin` only:
  * the lobe SURFACE is the exact inner envelope of the roller circle (radius
    TAPPET_ROLLER_R) whose centre rides at CAM_BASE_R + TAPPET_ROLLER_R +
    kin.lift_profile(rho, v) on a radial line -- so the physical ring produces
    kin.tappet_lift, not an approximation of it;
  * gear teeth are clocked at theta = 0 so every mesh has a tooth in a gap
    (see _PHASE below), and stay engaged under kin.pose_crank /
    kin.pose_cam_idler / kin.pose_cam_ring;
  * the ring turns exactly 90 deg per 720 deg cycle, so every ring feature is
    4-fold symmetric (lobes x4, 80 teeth, 16 face holes); the idler turns -480,
    so its features are 3-fold (48T, 15T, 6 web holes); the roller turns 3x.

Coordinates: in-plane angle b is the unit vector (-sin b, 0, cos b). Gears and
cam profiles are drawn in a local XY plane whose POLAR angle equals the in-plane
angle (x_dir = +Z, z_dir = ROT_AXIS = -Y), so the local +Z extrusion runs to -Y.
Tappets are authored along +Z (s = radius along the tappet axis) at y = 0 and
placed by a rotation of tappet_angle about ROT_AXIS plus the station offset.
"""

from __future__ import annotations

import math

import numpy as np
from cadgen import build123d as bd

from lib import geo, kin, palette as P, spec as S

MATERIALS = ("bronze", "fastener", "steel_machined")

# ---------------------------------------------------------------------------
# Dimensions (design)
# ---------------------------------------------------------------------------
RB = S.CAM_BASE_R                       # 150 base circle (roller contact)
RR = S.TAPPET_ROLLER_R                  # 12.5
TRACK_HALF = 10.0                       # lobe track half-width along y (20 wide)
RING_Y0, RING_Y1 = S.CAM_RING_Y         # every cam-system station below derives from spec
LAND_R = 146.0                          # lands / centre groove below the base circle
TRACK_ROOT_R = 140.0                    # lobe discs are annuli down to here (inside the core)
BUSH_BORE_R = 131.0                     # ring bore that carries the bronze bushing
BUSH_ID_R = 125.0                       # bushing bore = nose-case support hub OD (hub <= Ø249.6)
BUSH_Y = (RING_Y0, RING_Y0 + 25.5)
GEAR_ZONE_Y0 = RING_Y0 + 26.0          # internal teeth from here to the rear face
FACE_HOLES = 16                         # front-face lightening holes (4-fold)
FACE_HOLE_R, FACE_HOLE_D, FACE_HOLE_DEPTH = 138.5, 7.0, 12.0

# gears
M1 = S.CAM_CRANK_GEAR[1]                # 2.5
M2 = S.CAM_RING_GEAR[1]                 # 100/32.5
BACKLASH = 0.08                         # tooth-thickness reduction per gear at the pitch circle
_YB, _YS = S.CAM_IDLER_Y["big"], S.CAM_IDLER_Y["small"]   # idler gear face centres
CRANK_GEAR_Y = (_YB - 9.0, _YB + 9.0)  # on the crank-nose seat (-140..-116) + NOSE_SHIFT
IDLER_BIG_Y = (_YB - 8.5, _YB + 8.5)
IDLER_SMALL_Y = (_YS - 11.0, _YS + 11.0)
IDLER_BORE_R = 14.0
IDLER_HUB_R = 18.0
IDLER_WEB_Y = (_YB - 3.0, _YB + 3.0)
IDLER_RIM_R = 50.0
RING_TIP_R = 120.8                      # internal-gear tip circle (short addendum: clears the 15T's
                                        # line-of-action interference point at r 120.61)
SHAFT_R = 11.0                          # idler shaft Ø22 (static), nose-hub supported
SHAFT_Y = (RING_Y0, IDLER_BIG_Y[1] + 6.3)
SHAFT_THREAD_R = 8.0

# tappets (s = radius along the tappet axis)
S_AXLE = RB + RR                        # 162.5 roller centre at zero lift
S_BALL = S.TAPPET_SOCKET_R              # 205 pushrod-bottom ball centre
BALL_R = 7.0
CUP_R = 7.25
BODY_R = 13.0                           # tappet Ø26
BODY_TOP = 206.0
FOOT_R = 11.0                           # clevis nose radius about the axle (< RR: never meets the cam)
SLOT_HALF = 7.0
ROLLER_HALF = 6.5
AXLE_R = 3.5
ROLLER_BORE_R = 3.6
GUIDE_IR, GUIDE_OR = 13.15, 17.0       # running bore (bronze liner ID) / guide OD = nose boss bore Ø34
LINER_OR = 13.75                        # thin bronze liner pressed into the steel guide (hidden in the bore)
GUIDE_S = (178.0, 217.0)                # guide bottom / top face (top ⊥ tappet axis). 217, not 218: the
                                        # tilted lower packing nut's seat disc dips to s 217.61 (intake)

_ROT = S.ROT_AXIS


# ---------------------------------------------------------------------------
# Frames
# ---------------------------------------------------------------------------
def _gear_loc(axis_xz=(0.0, 0.0), y=0.0) -> bd.Location:
    """Local XY (polar angle = in-plane angle) -> engine, origin at (x, y, z)."""
    pl = bd.Plane(origin=(axis_xz[0], y, axis_xz[1]), x_dir=(0, 0, 1), z_dir=_ROT)
    return pl.location


def _span(face, y0, y1, axis_xz=(0.0, 0.0)):
    """Extrude a local-XY face so it spans engine y in [y0, y1] (y0 < y1)."""
    return _gear_loc(axis_xz, y1) * bd.extrude(face, amount=y1 - y0)


def _polar(r, a):
    return (r * math.cos(a), r * math.sin(a))


def _tappet_loc(k, v) -> bd.Location:
    return bd.Pos(0, S.TAPPET_Y[v], 0) * geo.axis_rotation(_ROT, kin.tappet_angle(k, v))


def _rev_z(pts):
    """Revolve a closed (r, z) polygon about local +Z."""
    face = bd.Plane.XZ * bd.Polygon(*pts, align=None)
    return bd.revolve(face, bd.Axis.Z)


def _rev_y(pts):
    """Revolve a closed (r, y) polygon about the engine Y axis."""
    return geo.revolve_y(pts)


# ---------------------------------------------------------------------------
# Cam profile: inner envelope of the roller circle
# ---------------------------------------------------------------------------
def _lift_and_slope(rho_deg, v):
    """lift_profile and its derivative d(lift)/d(rho) per RADIAN."""
    w = kin.lobe_width(v)
    if abs(rho_deg) >= w / 2.0:
        return 0.0, 0.0
    L = kin.lift_profile(rho_deg, v)
    a = math.pi * (rho_deg / w + 0.5)
    dL = S.TAPPET_LIFT[v] * math.sin(2 * a) * math.pi / math.radians(w)
    return L, dL


def _wrap90(a):
    return (a + 45.0) % 90.0 - 45.0


def cam_samples(v):
    """Sorted ring-frame in-plane angles (deg) at which the path is sampled:
    0.1 deg across each lobe (+-1.5 deg), 0.5 deg on the base circle."""
    ph, w = kin.lobe_phase(v), kin.lobe_width(v)
    out = []
    for j in range(S.CAM_LOBES):
        c = ph + 90.0 * j
        a0, a1 = c - w / 2.0 - 1.5, c + w / 2.0 + 1.5
        n = int(round((a1 - a0) / 0.1))
        out += [a0 + (a1 - a0) * i / n for i in range(n)]
        nxt = c + 90.0 - w / 2.0 - 1.5
        nb = max(2, int(math.ceil((nxt - a1) / 0.5)))
        out += [a1 + (nxt - a1) * i / nb for i in range(nb)]
    return out


def envelope_point(psi_deg, v):
    """(X, Z) of the cam surface for the roller whose centre sits on the radial
    line at ring-frame in-plane angle psi (roller centre radius RB+RR+lift)."""
    rho = _wrap90(psi_deg - kin.lobe_phase(v))
    L, dL = _lift_and_slope(rho, v)
    R = RB + RR + L
    p = math.radians(psi_deg)
    e = (-math.sin(p), math.cos(p))
    ep = (-math.cos(p), -math.sin(p))          # de/dpsi
    C = (R * e[0], R * e[1])
    T = (dL * e[0] + R * ep[0], dL * e[1] + R * ep[1])
    tn = math.hypot(*T)
    n = (T[1] / tn, -T[0] / tn)
    if n[0] * e[0] + n[1] * e[1] > 0:          # inward normal
        n = (-n[0], -n[1])
    return (C[0] + RR * n[0], C[1] + RR * n[1])


def path_min_concave_radius(v):
    """Smallest radius of curvature where the roller-centre path is concave
    (seen from outside): must exceed RR or the envelope would undercut."""
    worst = float("inf")
    for psi in cam_samples(v):
        h = 0.01
        pts = []
        for d in (-h, 0.0, h):
            rho = _wrap90(psi + d - kin.lobe_phase(v))
            R = RB + RR + kin.lift_profile(rho, v)
            p = math.radians(psi + d)
            pts.append(np.array([-R * math.sin(p), R * math.cos(p)]))
        d1 = (pts[2] - pts[0]) / (2 * h)
        d2 = (pts[2] - 2 * pts[1] + pts[0]) / (h * h)
        k = (d1[0] * d2[1] - d1[1] * d2[0]) / (np.hypot(*d1) ** 3)
        if k < 0:                               # CCW path in polar angle: k<0 = concave
            worst = min(worst, 1.0 / -k)
    return worst


def cam_edge(v, y):
    """Periodic BSpline edge of track v's lobe surface in the plane y."""
    from OCP.GeomAPI import GeomAPI_Interpolate
    from OCP.TColgp import TColgp_HArray1OfPnt
    from OCP.gp import gp_Pnt
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge

    pts = [envelope_point(a, v) for a in cam_samples(v)]
    arr = TColgp_HArray1OfPnt(1, len(pts))
    for i, (x, z) in enumerate(pts):
        arr.SetValue(i + 1, gp_Pnt(x, y, z))
    it = GeomAPI_Interpolate(arr, True, 1e-6)
    it.Perform()
    assert it.IsDone()
    return bd.Edge(BRepBuilderAPI_MakeEdge(it.Curve()).Edge())


# ---------------------------------------------------------------------------
# Involute gear outlines (local XY, polar angle = in-plane angle)
# ---------------------------------------------------------------------------
def _inv(a):
    return math.tan(a) - a


def gear_face(z, m, r_a, r_f, c0_deg, thick_delta=0.0, alpha_deg=20.0, n_flank=10):
    """External spur-gear outline face: z teeth, module m, tip r_a, root r_f,
    tooth CENTRES at c0 + 360 i / z; tooth thickness at pitch pi m/2 + thick_delta.
    Below the base circle the flank is a radial line."""
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


# Mesh phasing at theta = 0 (tooth-in-gap on each line of centres, idler axis at in-plane -30):
#   crank 32T  : a tooth centred at -30 (pointing at the idler)
#   idler 48T  : a GAP at 150 (pointing back at the crank)   -> tooth centres at 150 + 3.75
#   idler 15T  : a tooth centred at -30 (pointing out at the ring)
#   ring 80T   : a GAP at -30 (internal)                     -> the gap cutter's tooth at -30
_PHASE = {"crank": S.CAM_IDLER_ANGLE,
          "idler_big": S.CAM_IDLER_ANGLE + 180.0 + 180.0 / S.CAM_IDLER[0][0],
          "idler_small": S.CAM_IDLER_ANGLE,
          "ring_gap": S.CAM_IDLER_ANGLE}


# ---------------------------------------------------------------------------
# Cam ring
# ---------------------------------------------------------------------------
def _track_disc(v):
    y = S.TAPPET_Y[v]
    y0, y1 = y - TRACK_HALF, y + TRACK_HALF
    edge = cam_edge(v, y0)
    face = bd.Face(bd.Wire([edge]))
    disc = bd.extrude(face, amount=y1 - y0, dir=(0, 1, 0))
    disc = disc - geo.cyl_y(y0 - 1, y1 + 1, 2 * TRACK_ROOT_R)
    # break the two lobe-track edges (outside the roller's 13 mm path)
    outer = [e for e in disc.edges() if e.geom_type != bd.GeomType.CIRCLE
             and min(math.hypot(p.X, p.Z) for p in (e @ 0.0, e @ 0.37, e @ 0.71)) > RB - 1]
    disc, _ = _safe_chamfer(disc, outer, 0.6)
    return disc


def _safe_chamfer(part, edges, length):
    from lib.fasteners import safe_chamfer
    return safe_chamfer(part, edges, length)


def cam_ring():
    c = 1.0
    y0, y1 = RING_Y0, RING_Y1
    core = _rev_y([
        (BUSH_BORE_R + 0.6, y0), (LAND_R - c, y0), (LAND_R, y0 + c), (LAND_R, y1 - c),
        (LAND_R - c, y1), (RING_TIP_R + 0.6, y1), (RING_TIP_R, y1 - 0.6),
        (RING_TIP_R, GEAR_ZONE_Y0), (BUSH_BORE_R, GEAR_ZONE_Y0), (BUSH_BORE_R, y0 + 0.6),
    ])
    ring = core + [_track_disc("I"), _track_disc("E")]
    # internal teeth: the gap cutter is an 'external gear' whose teeth are the ring's gaps
    rp = S.CAM_RING_GEAR[0] * M2 / 2.0
    cutter_face = gear_face(S.CAM_RING_GEAR[0], M2, rp + 1.25 * M2, RING_TIP_R - 2.5,
                            _PHASE["ring_gap"], thick_delta=+BACKLASH)
    cutter = _span(cutter_face, GEAR_ZONE_Y0 - 1.0, y1 + 1.0)
    holes = []
    for i in range(FACE_HOLES):
        b = 360.0 * i / FACE_HOLES + 360.0 / FACE_HOLES / 2.0
        x, _, z = S.inplane(b, FACE_HOLE_R)
        h = geo.cyl_y(y0 - 1.0, y0 + FACE_HOLE_DEPTH, FACE_HOLE_D, x, z)
        holes.append(h)
    ring = ring - ([cutter] + holes)
    return ring


def cam_bushing():
    y0, y1 = BUSH_Y
    return _rev_y([(BUSH_ID_R + 0.8, y0), (BUSH_BORE_R, y0), (BUSH_BORE_R, y1),
                   (BUSH_ID_R, y1), (BUSH_ID_R, y0 + 0.8)])


# ---------------------------------------------------------------------------
# Crank gear, idler
# ---------------------------------------------------------------------------
def crank_gear():
    z = S.CAM_CRANK_GEAR[0]
    rp = z * M1 / 2.0
    face = gear_face(z, M1, rp + M1, rp - 1.25 * M1, _PHASE["crank"], thick_delta=-BACKLASH)
    g = _span(face, *CRANK_GEAR_Y)
    bore = geo.cyl_y(CRANK_GEAR_Y[0] - 1, CRANK_GEAR_Y[1] + 1, S.CRANK_NOSE_D)
    key = _keyway()
    g = g - bore
    g = g - key
    return g


def _keyway(r0=29.0, r1=33.5, w=6.0):
    """Keyway at in-plane 0 (+Z at theta = 0) through the gear."""
    y0, y1 = CRANK_GEAR_Y
    return bd.Pos(0, (y0 + y1) / 2.0, (r0 + r1) / 2.0) * bd.Box(w, y1 - y0 + 2.0, r1 - r0)


def crank_gear_key():
    y0, y1 = CRANK_GEAR_Y
    r0, r1 = 30.0, 33.3
    return bd.Pos(0, (y0 + y1) / 2.0, (r0 + r1) / 2.0) * bd.Box(5.9, y1 - y0 - 3.0, r1 - r0)


def idler_gear():
    ax = kin.cam_idler_axis_point()
    axz = (ax[0], ax[2])
    (zb, mb), (zs, ms) = S.CAM_IDLER
    rpb, rps = zb * mb / 2.0, zs * ms / 2.0
    big = gear_face(zb, mb, rpb + mb, rpb - 1.25 * mb, _PHASE["idler_big"], thick_delta=-BACKLASH)
    small = gear_face(zs, ms, rps + ms, rps - 1.25 * ms, _PHASE["idler_small"], thick_delta=-BACKLASH)
    rim = _span(big, *IDLER_BIG_Y, axis_xz=axz) - _span(bd.Circle(IDLER_RIM_R), IDLER_BIG_Y[0] - 1,
                                                        IDLER_BIG_Y[1] + 1, axis_xz=axz)
    sm = _span(small, *IDLER_SMALL_Y, axis_xz=axz)
    hub = _span(bd.Circle(IDLER_HUB_R), IDLER_SMALL_Y[1] - 0.5, IDLER_BIG_Y[1], axis_xz=axz)
    web = _span(bd.Circle(IDLER_RIM_R + 1.0), *IDLER_WEB_Y, axis_xz=axz)
    body = sm + [hub, web, rim]
    tools = [_span(bd.Circle(IDLER_BORE_R), IDLER_SMALL_Y[0] - 1, IDLER_BIG_Y[1] + 1, axis_xz=axz)]
    for i in range(6):
        a = math.radians(30.0 + 60.0 * i)
        tools.append(_span(bd.Pos(35.0 * math.cos(a), 35.0 * math.sin(a)) * bd.Circle(7.0),
                           IDLER_WEB_Y[0] - 1, IDLER_WEB_Y[1] + 1, axis_xz=axz))
    return body - tools


def idler_bushing():
    ax = kin.cam_idler_axis_point()
    ring = bd.Circle(IDLER_BORE_R) - bd.Circle(SHAFT_R + 0.15)
    return _span(ring, IDLER_SMALL_Y[0], IDLER_BIG_Y[1], axis_xz=(ax[0], ax[2]))


def idler_shaft():
    ax = kin.cam_idler_axis_point()
    axz = (ax[0], ax[2])
    y_sh = IDLER_BIG_Y[1] + 0.3            # shoulder (washer seat)
    main = _span(bd.Circle(SHAFT_R), SHAFT_Y[0], y_sh, axis_xz=axz)
    thread = _span(bd.Circle(SHAFT_THREAD_R), y_sh - 0.5, SHAFT_Y[1], axis_xz=axz)
    return main + thread, y_sh


def idler_washer(y_sh):
    ax = kin.cam_idler_axis_point()
    w = bd.Circle(17.0) - bd.Circle(SHAFT_THREAD_R + 0.1)
    return _span(w, y_sh, y_sh + 1.5, axis_xz=(ax[0], ax[2]))


def idler_nut(y_sh):
    from lib.fasteners import _wrench_head
    ax = kin.cam_idler_axis_point()
    y0, y1 = y_sh + 1.5, SHAFT_Y[1]
    nut = _wrench_head(22.0, 0.0, y1 - y0, chamfer_bottom=True) - bd.Cylinder(
        SHAFT_THREAD_R, 40.0)
    return geo.locate(nut, (ax[0], y0, ax[2]), (0, 1, 0))


# ---------------------------------------------------------------------------
# Tappets (authored along +Z at y = 0: s = Z, tangential = X, axial = Y)
# ---------------------------------------------------------------------------
def tappet_body():
    c = S_AXLE
    top = BODY_TOP
    k_s = c + 6.0                                    # where the flank reaches full width
    # tangent point from (BODY_R, k_s - c) to the nose circle FOOT_R about the axle
    px, pz = BODY_R, k_s - c
    d = math.hypot(px, pz)
    phi0 = math.atan2(pz, px)
    dphi = math.acos(FOOT_R / d)
    ph = phi0 - dphi                                  # lower tangent
    tx, tz = FOOT_R * math.cos(ph), FOOT_R * math.sin(ph)
    pts_right = (tx, c + tz)
    prof = [
        bd.Line((-BODY_R, top), (-BODY_R, k_s)),
        bd.Line((-BODY_R, k_s), (-pts_right[0], pts_right[1])),
        bd.ThreePointArc((-pts_right[0], pts_right[1]), (0, c - FOOT_R), pts_right),
        bd.Line(pts_right, (BODY_R, k_s)),
        bd.Line((BODY_R, k_s), (BODY_R, top)),
        bd.Line((BODY_R, top), (-BODY_R, top)),
    ]
    face = bd.Plane.XZ * bd.Face(bd.Wire(prof))     # XZ plane: local (x, y) -> world (x, z); normal -Y
    blank = bd.extrude(face, amount=BODY_R + 1, both=True)
    body = blank & bd.Pos(0, 0, c - 20) * bd.Cylinder(BODY_R, top - c + 30, align=(bd.Align.CENTER,) * 2 + (bd.Align.MIN,))
    slot = bd.Pos(0, 0, (c - 20 + c + RR + 1.0) / 2.0) * bd.Box(40, 2 * SLOT_HALF, (RR + 1.0) + 20)
    body = body - slot
    axle_hole = bd.Pos(0, 0, c) * bd.Rot(90, 0, 0) * bd.Cylinder(AXLE_R, 40)
    sphere = bd.Pos(0, 0, S_BALL) * bd.Sphere(CUP_R)
    cone = _rev_z([(0.0, top - 1.6), (math.sqrt(CUP_R ** 2 - (top - 1.6 - S_BALL) ** 2) + 0.05, top - 1.6),
                   (math.sqrt(CUP_R ** 2 - (top - 1.6 - S_BALL) ** 2) + 1.7, top + 0.1), (0.0, top + 0.1)])
    groove = _rev_z([(BODY_R - 0.8, 188.0), (BODY_R + 1, 188.0), (BODY_R + 1, 190.0), (BODY_R - 0.8, 190.0)])
    body = body - axle_hole
    body = body - (sphere + cone)
    body = body - groove
    # top outer edge: constructive chamfer via a revolved limiter
    lim = _rev_z([(0.0, c - 30), (BODY_R + 5, c - 30), (BODY_R + 5, top - 0.8 - 5),
                  (BODY_R - 0.8, top), (0.0, top)])
    return body & lim


def tappet_roller():
    c = S_AXLE
    b = 0.6
    return bd.Pos(0, 0, c) * bd.Rot(90, 0, 0) * _rev_z([
        (ROLLER_BORE_R + 0.3, -ROLLER_HALF), (RR - b, -ROLLER_HALF), (RR, -ROLLER_HALF + b),
        (RR, ROLLER_HALF - b), (RR - b, ROLLER_HALF), (ROLLER_BORE_R + 0.3, ROLLER_HALF),
        (ROLLER_BORE_R, ROLLER_HALF - 0.3), (ROLLER_BORE_R, -ROLLER_HALF + 0.3)])


def roller_recess():
    """Shallow turned recess on both roller faces (axisymmetric)."""
    c = S_AXLE
    return [bd.Pos(0, 0, c) * bd.Rot(90, 0, 0) * _rev_z([(5.5, s * (ROLLER_HALF - 0.6)), (9.5, s * (ROLLER_HALF - 0.6)),
                                                         (9.5, s * (ROLLER_HALF + 1)), (5.5, s * (ROLLER_HALF + 1))])
            for s in (-1, 1)]


def tappet_axle():
    L = 12.6
    b = 0.4
    return bd.Pos(0, 0, S_AXLE) * bd.Rot(90, 0, 0) * _rev_z([
        (0, -L), (AXLE_R - b, -L), (AXLE_R, -L + b), (AXLE_R, L - b), (AXLE_R - b, L), (0, L)])


def tappet_guide():
    """Slim machined-steel guide: plain Ø34 sleeve in the nose boss, crisp chamfers,
    standing 1.5 proud of the boss face (r 215.5) -- no flange."""
    s0, s1 = GUIDE_S
    b = 0.5
    return _rev_z([
        (LINER_OR + b, s0), (GUIDE_OR - b, s0), (GUIDE_OR, s0 + b), (GUIDE_OR, s1 - 0.6),
        (GUIDE_OR - 0.6, s1), (LINER_OR + 1.6, s1), (LINER_OR, s1 - 1.6), (LINER_OR, s0 + b)])


def tappet_liner():
    """Bronze running liner inside the guide (the tappet rides on this)."""
    s0, s1 = GUIDE_S[0] + 1.0, GUIDE_S[1] - 3.5     # stops short of the mouth: the leaning pushrod passes there
    return _rev_z([(GUIDE_IR + 0.3, s0), (LINER_OR, s0), (LINER_OR, s1), (GUIDE_IR + 0.3, s1),
                   (GUIDE_IR, s1 - 0.3), (GUIDE_IR, s0 + 0.3)])


SEAT_CLEAR = 0.25                       # guide/liner tops stay this far below the packing-nut seat plane


def _seat_trim(shape, v):
    """Re-face a cylinder-1 guide/liner top to the lower packing nut's seat plane (normal to the
    pushrod TUBE axis, which leans ~26-28 deg off the tappet axis), SEAT_CLEAR below it. The plane
    comes from lib/pushrods.tube_axis so the two systems can never disagree."""
    from lib import pushrods
    a_lo, _, w, _, gap = pushrods.tube_axis(v)
    origin = kin._addv(a_lo, w, gap - SEAT_CLEAR)
    half = geo.plane(origin, w) * bd.Box(800.0, 800.0, 400.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    return shape - half


# ---------------------------------------------------------------------------
def build() -> list:
    parts = []
    st, br, fa = P.STEEL_MACHINED, P.BRONZE, P.FASTENER

    parts.append(P.style(cam_ring(), "camring:ring", st))
    parts.append(P.style(cam_bushing(), "camring:bushing", br))
    parts.append(P.style(crank_gear(), "crank:cam_gear", st))
    parts.append(P.style(crank_gear_key(), "crank:cam_gear_key", st))
    parts.append(P.style(idler_gear(), "camidler:gear", st))
    parts.append(P.style(idler_bushing(), "camidler:bushing", br))
    shaft, y_sh = idler_shaft()
    parts.append(P.style(shaft, "cam:idler_shaft", st))
    parts.append(P.style(idler_washer(y_sh), "cam:idler_washer", fa))
    parts.append(P.style(idler_nut(y_sh), "cam:idler_nut", fa))

    body = tappet_body()
    roller = tappet_roller() - roller_recess()
    axle = tappet_axle()
    guide = tappet_guide()
    liner = tappet_liner()
    tops = {v: (_seat_trim(_tappet_loc(1, v) * guide, v), _seat_trim(_tappet_loc(1, v) * liner, v))
            for v in kin.VALVES}
    for k in range(1, S.N_CYL + 1):
        for v in kin.VALVES:
            loc = _tappet_loc(k, v)
            parts.append(P.style(kin.place(loc * body, kin.pose_tappet(0.0, k, v)), f"tappet{k}{v}:body", st))
            parts.append(P.style(kin.place(loc * axle, kin.pose_tappet(0.0, k, v)), f"tappet{k}{v}:axle", st))
            parts.append(P.style(kin.place(loc * roller, kin.pose_tappet_roller(0.0, k, v)),
                                 f"tappet{k}{v}:roller", st))
            g1, l1 = tops[v]
            parts.append(P.style(geo.on_cylinder(g1, k), f"cam:tappet_guide_{k}{v}", st))
            parts.append(P.style(geo.on_cylinder(l1, k), f"cam:tappet_liner_{k}{v}", br))
    return parts
