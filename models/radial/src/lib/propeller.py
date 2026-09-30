"""Propeller system: a three-blade, ground-adjustable split-barrel steel hub
(Hamilton-Standard pattern) with polished aluminium Clark-Y blades.

    prop:hub_front, prop:hub_rear   the forged steel barrel, split in the plane of
        rotation (y = PROP_HUB_Y); its bore carries 24 internal splines on the
        reduction builder's shaft splines (propshaft:shaft, y -530.5..-425.5 + NOSE_SHIFT),
        seats on the shaft's rear cone (propshaft:rear_cone) and receives the
        front cone. Three blade sockets clamp the round blade shanks.
    prop:front_cone                 driven home by the reduction builder's hub nut
        (propshaft:hub_nut, bearing face y -541 + NOSE_SHIFT).
    prop:clamp_ring_<k>             one split clamp ring round each socket end, drawn
        up by prop:clamp_ring_bolt_<k> + prop:clamp_ring_nut_<k>.
    prop:barrel_bolt_<k>_<i>, prop:barrel_nut_<k>_<i>, prop:barrel_wire_<k>
        two through-bolts in each lug between the sockets, heads forward, heads
        wired in pairs.
    prop:blade_<k>                  polished aluminium, doubled root-to-tip span: Clark-Y
        family sections with the original chord, thickness and twist retained.
        Root-to-tip span 2435 mm, with the root fixed at radius 82 mm;
        paddle planform with an elliptical tip, 0.7 mm trailing edge. Shown
        FEATHERED: the whole twisted blade is turned in its socket so the chord
        at 0.75 R stands at 89 deg (root sections past 90), leading edge forward;
        the ground-adjustable clamp allows any setting.

Frame: blade k at in-plane angle 20 + 120 (k-1) (between cylinders). The
propeller turns right-handed about ROT_AXIS = -Y (clockwise from the rear): a
blade at in-plane b moves along in-plane b + 90. Leading edge = that motion
direction tipped forward (-Y) by the pitch angle; the cambered (suction) face
looks forward - a tractor. Everything is 3-fold (the prop turns 480 deg/cycle).

No spinner, by choice: a look-test spinner (polished ellipsoid, D 350) hid the
hub, the reduction builder's hub nut and the line of sight into the nose
cutaway's reduction gearing; the bare hub reads as the period museum engines do.
"""

from __future__ import annotations

import math

import numpy as np
from cadgen import build123d as bd

from lib import castings as C
from lib import fasteners as F
from lib import geo
from lib import palette as P
from lib import spec as S

MATERIALS = ("fastener", "polished_alu", "safety_wire", "steel_machined", "steel_polished")

_ROT = S.ROT_AXIS
HUB_Y = S.PROP_HUB_Y                  # blade axes lie in this plane
_DY = S.NOSE_SHIFT                    # the nose section (shaft, cones, hub nut) sits this far forward
BLADE_ANGLES = (20.0, 140.0, 260.0)   # at theta = 0 (between cylinders)
PHASE = BLADE_ANGLES[0]               # parts are authored for blades at 0/120/240, then rotated

# ---- interface with the reduction (propshaft:*) --------------------------------
REAR_CONE = ((56.0, -413.5 + _DY), (49.0, -425.0 + _DY))   # (r, y) ends of the rear cone's seat line
SPL_Y = (-530.5 + _DY, -425.5 + _DY)                      # shaft spline run
SPL_ROOT, SPL_TIP, SPL_N, SPL_PHASE = 42.0, 45.0, 24, 7.5
NUT_FACE_Y = -541.0 + _DY                           # hub-nut flange bearing face (r 40..56)

# ---- hub ----------------------------------------------------------------------
HUB_REAR_Y = -414.0 + _DY
HUB_FRONT_Y = -538.3 + _DY
BARREL_Y = (-516.0 + _DY, -424.0 + _DY)          # main barrel (lug faces)
BARREL_R = 74.0
BORE_R = 45.4
SEAT_GAP = 0.2
SOCKET_R = 50.0
SOCKET_END = 156.0
SHANK_R = 40.0
SHANK_BORE_R = 40.15
RING_S = (128.0, 150.0)
RING_OR = 58.0
LIP = (150.5, 156.0, 52.5)            # socket lip s0, s1, r
LUG_R_OUT, LUG_W = 104.0, 48.0
LUG_BOLT_R, LUG_BOLT_T = 82.0, 12.0
BOLT_D = 9.5                          # 3/8 in
SPLIT_GAP = 0.2                       # each half stops 0.2 short of y = HUB_Y

# ---- blade --------------------------------------------------------------------
R_TIP = 1300.0                       # reference radius for the original section profiles
BLADE_SPAN_SCALE = 2.0               # stretch along each blade axis, anchored at its root
PITCH = 2450.0                        # geometric pitch (mm/rev)
X_REF = 0.33                          # pitch axis, fraction of chord from the LE
BLEND = (190.0, 470.0)                # round shank -> airfoil
N_HALF = 44                           # points per surface

# Clark Y (NACA TN 1937 ordinates, % chord)
_CY_X = [0, 1.25, 2.5, 5, 7.5, 10, 15, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100]
_CY_U = [3.50, 5.45, 6.50, 7.90, 8.85, 9.60, 10.69, 11.36, 11.70, 11.40, 10.52, 9.15, 7.35, 5.22, 2.80, 1.49, 0.12]
_CY_L = [3.50, 1.93, 1.47, 0.93, 0.63, 0.42, 0.15, 0.03, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


def _style(shape, label, color):
    return P.style(shape, label, color)


def _rev(pts):
    return geo.revolve_y(pts)


def _rot(deg):
    return geo.axis_rotation(_ROT, deg)


def _ip(b, r=1.0, y=0.0):
    return S.inplane(b, r, y)


# ---------------------------------------------------------------------------
# Blade
# ---------------------------------------------------------------------------
def _pchip(xs, ys):
    from scipy.interpolate import PchipInterpolator
    return PchipInterpolator(np.asarray(xs, float), np.asarray(ys, float))


_CY_SQ = np.sqrt(np.array(_CY_X) / 100.0)
_U = _pchip(_CY_SQ, np.array(_CY_U) / 100.0)
_L = _pchip(_CY_SQ, np.array(_CY_L) / 100.0)

_CHORD = _pchip([190, 260, 330, 400, 470, 560, 650, 800, 950, 1080], [92, 128, 160, 185, 203, 218, 228, 235, 233, 222])
_TC = _pchip([190, 260, 330, 400, 470, 560, 700, 900, 1100, 1300], [0.84, 0.58, 0.42, 0.32, 0.25, 0.19, 0.13, 0.092, 0.074, 0.062])
TIP_S0 = 1080.0


def chord(s):
    if s <= TIP_S0:
        return float(_CHORD(s))
    c1 = float(_CHORD(TIP_S0))
    q = (s - TIP_S0) / (R_TIP - TIP_S0)
    return c1 * math.sqrt(max(0.0, 1.0 - q * q))


def _helix_angle(s):
    return math.degrees(math.atan(PITCH / (2.0 * math.pi * s)))


FEATHER_REF_S = 0.75 * R_TIP
FEATHER_BETA = 89.0                   # blade angle at 0.75 R: FEATHERED (display pose)
FEATHER = FEATHER_BETA - _helix_angle(FEATHER_REF_S)


def pitch_angle(s):
    """Blade angle: the design twist (helix of PITCH) turned bodily about the
    span axis to the feathered setting, so the chord at 0.75 R lies almost along
    the crank axis and the head-on star shows past the thin leading edges."""
    return _helix_angle(s) + FEATHER


def te_thickness(s):
    return 0.7 if s < 1150 else 0.7 - 0.3 * (s - 1150) / (R_TIP - 1150)


def _smooth(u):
    u = min(1.0, max(0.0, u))
    return u * u * u * (u * (6 * u - 15) + 10)          # C2 smootherstep


def section_2d(s):
    """(xi, eta) points of the section at station s: TE upper -> LE -> TE lower.
    xi along the chord from the pitch axis toward the TE, eta toward the
    cambered (suction) face."""
    w = _smooth((s - BLEND[0]) / (BLEND[1] - BLEND[0]))
    te = te_thickness(s)
    t = np.linspace(0.0, math.pi, N_HALF + 1)            # 0 = LE, pi = TE
    x = 0.5 * (1.0 - np.cos(t))
    sq = np.sqrt(x)
    c = chord(max(s, BLEND[0]))
    tc = float(_TC(max(s, BLEND[0])))
    kt = tc / 0.117
    up = kt * _U(sq)
    lo = kt * _L(sq)
    up = up + x * max(0.0, te / c - (up[-1] - lo[-1]))  # finite trailing edge
    shift = kt * 0.5 * (float(_U(math.sqrt(X_REF))) + float(_L(math.sqrt(X_REF))))
    a_xi = (x - X_REF) * c
    a_up = (up - shift) * c
    a_lo = (lo - shift) * c
    # round shank with the same parametrisation (tiny te flat on the "TE" side)
    delta = math.asin(min(0.5, te / 2.0 / SHANK_R))
    phi = t * (math.pi - delta) / math.pi
    c_xi = -SHANK_R * np.cos(phi)
    c_up = SHANK_R * np.sin(phi)
    c_lo = -SHANK_R * np.sin(phi)
    xi_u = (1 - w) * c_xi + w * a_xi
    et_u = (1 - w) * c_up + w * a_up
    xi_l = (1 - w) * c_xi + w * a_xi
    et_l = (1 - w) * c_lo + w * a_lo
    upper = list(zip(xi_u[::-1], et_u[::-1]))            # TE -> LE
    lower = list(zip(xi_l[1:], et_l[1:]))                # LE -> TE
    return upper + lower


def _section_pts(s):
    """3D section points at station s for the blade at in-plane 0 (axis +Z at y = HUB_Y)."""
    beta = math.radians(pitch_angle(s))
    d_rot = np.array([-1.0, 0.0, 0.0])                   # motion direction at in-plane 0
    fwd = np.array([0.0, -1.0, 0.0])
    a = math.cos(beta) * d_rot + math.sin(beta) * fwd     # toward the leading edge
    n = -math.sin(beta) * d_rot + math.cos(beta) * fwd    # suction-face normal
    o = np.array([0.0, HUB_Y, span_station(s)])
    return [o - xi * a + eta * n for xi, eta in section_2d(s)]


STATIONS = [82, 110, 140, 165, 190, 210, 230, 250, 270, 290, 310, 332, 356, 382, 410, 440, 470, 510, 560, 620,
            710, 800, 890, 980, 1060, 1120, 1170, 1210, 1242, 1266, 1283, 1293, 1298, 1299.5]


def span_station(s):
    """Stretch only blade length; keep its root and all section profiles fixed."""
    root = STATIONS[0]
    return root + BLADE_SPAN_SCALE * (s - root)


def _interp(points, params):
    from OCP.GeomAPI import GeomAPI_Interpolate
    from OCP.TColgp import TColgp_HArray1OfPnt
    from OCP.TColStd import TColStd_HArray1OfReal
    from OCP.gp import gp_Pnt
    hp = TColgp_HArray1OfPnt(1, len(points))
    hk = TColStd_HArray1OfReal(1, len(points))
    for i, (p, t) in enumerate(zip(points, params)):
        hp.SetValue(i + 1, gp_Pnt(*map(float, p)))
        hk.SetValue(i + 1, float(t))
    it = GeomAPI_Interpolate(hp, hk, False, 1e-7)
    it.Perform()
    return it.Curve()


def _blade_surface():
    """Tensor-product interpolation done by hand: every section is interpolated
    with the SAME parameters (the cosine-spacing index, so all sections share one
    knot vector), then each pole row is interpolated across the stations with
    the station radius as parameter. Exact through every grid point."""
    from OCP.Geom import Geom_BSplineSurface
    from OCP.TColgp import TColgp_Array2OfPnt
    from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal
    nu = 2 * N_HALF + 1
    upar = [i / (nu - 1) for i in range(nu)]
    secs = [_interp(_section_pts(s), upar) for s in STATIONS]
    c0 = secs[0]
    npu = c0.NbPoles()
    for c in secs:
        assert c.NbPoles() == npu and all(abs(c.Knot(i) - c0.Knot(i)) < 1e-12 for i in range(1, c0.NbKnots() + 1))
    vpar = [float(s) for s in STATIONS]
    rows = []
    for k in range(1, npu + 1):
        pts = [(c.Pole(k).X(), c.Pole(k).Y(), c.Pole(k).Z()) for c in secs]
        rows.append(_interp(pts, vpar))
    r0 = rows[0]
    npv = r0.NbPoles()
    poles = TColgp_Array2OfPnt(1, npu, 1, npv)
    for i, r in enumerate(rows):
        for j in range(1, npv + 1):
            poles.SetValue(i + 1, j, r.Pole(j))

    def kv(c):
        kn = TColStd_Array1OfReal(1, c.NbKnots())
        ml = TColStd_Array1OfInteger(1, c.NbKnots())
        for i in range(1, c.NbKnots() + 1):
            kn.SetValue(i, c.Knot(i))
            ml.SetValue(i, c.Multiplicity(i))
        return kn, ml
    uk, um = kv(c0)
    vk, vm = kv(r0)
    return Geom_BSplineSurface(poles, uk, vk, um, vm, c0.Degree(), r0.Degree())


def blade_proto():
    """One B-spline surface interpolated through the section grid (contour x
    span), a ruled trailing-edge strip, planar root and tip caps, sewn."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace,
                                    BRepBuilderAPI_MakeSolid, BRepBuilderAPI_MakeWire,
                                    BRepBuilderAPI_Sewing)
    from OCP.BRepFill import BRepFill
    from OCP.GeomAbs import GeomAbs_C2
    from OCP.GeomAPI import GeomAPI_PointsToBSplineSurface
    from OCP.ShapeFix import ShapeFix_Solid
    from OCP.TColgp import TColgp_Array2OfPnt
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Dir, gp_Pln, gp_Pnt

    surf = _blade_surface()
    u0, u1, v0, v1 = surf.Bounds()
    main = BRepBuilderAPI_MakeFace(surf, 1e-6).Face()
    e_up = BRepBuilderAPI_MakeEdge(surf.UIso(u0)).Edge()         # TE, upper side
    e_lo = BRepBuilderAPI_MakeEdge(surf.UIso(u1)).Edge()         # TE, lower side
    te = BRepFill.Face_s(e_up, e_lo)
    faces = [main, te]
    for v, st in ((v0, STATIONS[0]), (v1, STATIONS[-1])):
        c = surf.VIso(v)
        e = BRepBuilderAPI_MakeEdge(c).Edge()
        l = BRepBuilderAPI_MakeEdge(c.Value(c.LastParameter()), c.Value(c.FirstParameter())).Edge()
        w = BRepBuilderAPI_MakeWire(e, l).Wire()
        mf = BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(0.0, HUB_Y, span_station(st)), gp_Dir(0.0, 0.0, 1.0)), w, True)
        if not mf.IsDone():
            raise RuntimeError(f"blade cap at s={st} failed")
        faces.append(mf.Face())
    sew = BRepBuilderAPI_Sewing(1e-3)
    for f in faces:
        sew.Add(f)
    sew.Perform()
    shell = TopoDS.Shell_s(sew.SewedShape())
    solid = BRepBuilderAPI_MakeSolid(shell).Solid()
    fix = ShapeFix_Solid(solid)
    fix.Perform()
    out = bd.Solid(fix.Solid())
    if out.volume < 0:
        out = bd.Solid(out.wrapped.Reversed())
    return out


# ---------------------------------------------------------------------------
# Hub
# ---------------------------------------------------------------------------
def _rear_seat_r(y):
    (r0, y0), (r1, y1) = REAR_CONE
    return r0 + (r1 - r0) * (y - y0) / (y1 - y0) + SEAT_GAP


FC_CYL = (56.0, -540.9 + _DY, -538.8 + _DY)      # front cone: cylinder r, y front, y where the taper starts
FC_TIP = (49.0, -530.8 + _DY)             # small end (r, y)


def _front_seat_r(y):
    r0, y0 = FC_CYL[0], FC_CYL[2]
    r1, y1 = FC_TIP
    return r0 + (r1 - r0) * (y - y0) / (y1 - y0) + SEAT_GAP


BARREL_BULGE_R = 90.0


def hub_revolved():
    """Central barrel: a true-arc bulge between the lug faces, machined bosses
    fore and aft, the cone seats and the bore inside."""
    V = lambda r, y: bd.Vector(r, y, 0.0)
    ya, yb = HUB_REAR_Y - 4.0, HUB_FRONT_Y + 14.3        # arc ends (-418, -524)
    pts_a = [V(_rear_seat_r(HUB_REAR_Y), HUB_REAR_Y), V(60.0, HUB_REAR_Y), V(62.0, HUB_REAR_Y - 2.0), V(62.0, ya)]
    pts_b = [
        V(62.0, yb), V(62.0, HUB_FRONT_Y + 1.5), V(60.5, HUB_FRONT_Y),
        V(_front_seat_r(HUB_FRONT_Y), HUB_FRONT_Y), V(FC_TIP[0] + SEAT_GAP, FC_TIP[1]),
        V(BORE_R, FC_TIP[1]), V(BORE_R, REAR_CONE[1][1]),
        V(_rear_seat_r(REAR_CONE[1][1]), REAR_CONE[1][1]), V(_rear_seat_r(HUB_REAR_Y), HUB_REAR_Y),
    ]
    edges = [bd.Edge.make_line(p, q) for p, q in zip(pts_a[:-1], pts_a[1:])]
    edges.append(bd.Edge.make_three_point_arc(pts_a[-1], V(BARREL_BULGE_R, HUB_Y), pts_b[0]))
    edges += [bd.Edge.make_line(p, q) for p, q in zip(pts_b[:-1], pts_b[1:])]
    face = bd.Face(bd.Wire(edges))
    return bd.revolve(face, axis=bd.Axis.Y)


def _blade_loc(b):
    return _rot(b)


def socket_proto():
    """Socket for the blade at in-plane 0: a boss along +Z at y = HUB_Y."""
    s0, s1, rl = LIP
    prof = [(0.0, 0.0), (SOCKET_R, 0.0), (SOCKET_R, s0), (rl - 0.6, s0), (rl, s0 + 0.6),
            (rl, s1 - 1.0), (rl - 1.0, s1), (0.0, s1)]
    body = F._rev(prof)                                    # about local +Z
    return bd.Pos(0, HUB_Y, 0) * body


def lug_proto():
    """Clamp lug between two sockets, authored at in-plane 60 (between blades 0 and 120)."""
    rc = LUG_R_OUT - LUG_W / 2.0
    sk = bd.Rectangle(rc - 50.0, LUG_W, align=(bd.Align.MIN, bd.Align.CENTER))
    sk = bd.Pos(50.0, 0) * sk
    sk = sk + bd.Pos(rc, 0) * bd.Circle(LUG_W / 2.0)
    face = sk.face() if hasattr(sk, "face") else sk
    yb0, yb1 = BARREL_Y
    # local XY: x = radial (in-plane 0 = +Z), y = in-plane 90 (-X); extrude along -Y from yb1
    pl = bd.Plane(origin=(0, yb1, 0), x_dir=(0, 0, 1), z_dir=(0, -1, 0))
    body = bd.extrude(pl * face, amount=yb1 - yb0)
    return _rot(60.0) * body


def lug_bolt_points():
    """(x, z) of the bolts of the lug at in-plane 60 (authoring frame)."""
    pts = []
    for sgn in (-1.0, 1.0):
        rad = np.array(_ip(60.0, LUG_BOLT_R))
        tan = np.array(_ip(150.0, 1.0))
        p = rad + sgn * LUG_BOLT_T * tan
        pts.append((p[0], p[2]))
    return pts


def _inner_envelope():
    """Everything inside the bore / cone-seat line (the sockets reach the axis)."""
    return _rev([(0.0, HUB_REAR_Y + 3.0), (_rear_seat_r(HUB_REAR_Y + 3.0), HUB_REAR_Y + 3.0),
                 (_rear_seat_r(REAR_CONE[1][1]), REAR_CONE[1][1]), (BORE_R, REAR_CONE[1][1]),
                 (BORE_R, FC_TIP[1]), (FC_TIP[0] + SEAT_GAP, FC_TIP[1]),
                 (_front_seat_r(HUB_FRONT_Y - 3.0), HUB_FRONT_Y - 3.0), (0.0, HUB_FRONT_Y - 3.0)])


def hub_body():
    parts = [hub_revolved()]
    sock, lug = socket_proto(), lug_proto()
    for i in range(3):
        parts.append(_rot(120.0 * i) * sock)
        parts.append(_rot(120.0 * i) * lug)
    body = C.fuse_all(parts)
    body = C.cut_all(body, [_inner_envelope()])

    # blend the sockets into the barrel (the forging's generous root radius)
    def _junction(e):
        if e.geom_type in (bd.GeomType.LINE, bd.GeomType.CIRCLE):
            return False
        c = C.edge_center(e)
        return 55.0 < math.hypot(c.X, c.Z) < 110.0
    roots = [e for e in body.edges() if _junction(e)]
    def _near_socket(e):
        c = C.edge_center(e)
        b = math.degrees(math.atan2(-c.X, c.Z)) % 120.0
        return min(b, 120.0 - b) < 25.0
    sock_roots = [e for e in roots if _near_socket(e)]
    body, applied = C.safe_fillet(body, sock_roots, 9.0, min_r=1.5)
    if applied is None:
        C._warn("propeller hub: socket root fillet failed")
    # (the lug-to-barrel edges stay sharp: OCC segfaults filleting them, and a
    #  machined lug reads right with a crisp root)
    # blade bores, bolt holes
    tools = []
    for i in range(3):
        bore = bd.Pos(0, HUB_Y, 0) * F._rev([(0.0, 60.0), (SHANK_BORE_R, 60.0), (SHANK_BORE_R, SOCKET_END + 1.0),
                                             (0.0, SOCKET_END + 1.0)])
        tools.append(_rot(120.0 * i) * bore)
    for i in range(3):
        for (x, z) in lug_bolt_points():
            tools.append(_rot(120.0 * i) * geo.cyl_y(BARREL_Y[0] - 1, BARREL_Y[1] + 1, BOLT_D + 0.4, x, z))
    return C.cut_all(body, tools)


def hub_splines():
    """Internal spline teeth (in the shaft's gaps), authoring frame (pre-PHASE)."""
    n = SPL_N
    w = 5.2
    r0, r1 = SPL_ROOT + 0.4, BORE_R + 0.6
    # shaft teeth at in-plane 7.5 + 15 k (final frame) -> gaps at 15 k -> authoring 15 k - PHASE
    teeth = [bd.Rot(0, 0, (15.0 * i - PHASE)) * bd.Pos(0.5 * (r0 + r1), 0) * bd.Rectangle(r1 - r0, w) for i in range(n)]
    sk = bd.Sketch() + teeth
    y0, y1 = SPL_Y[0] + 1.0, SPL_Y[1] - 1.0
    pl = bd.Plane(origin=(0, y1, 0), x_dir=(0, 0, 1), z_dir=_ROT)
    return pl.location * bd.extrude(sk, amount=y1 - y0)


def front_cone():
    r, yf, yt = FC_CYL
    return _rev([(40.2, yf), (r - 0.5, yf), (r, yf + 0.5), (r, yt), FC_TIP,
                 (42.35, FC_TIP[1]), (42.35, -533.7 + _DY), (40.2, -533.7 + _DY)])


# ---------------------------------------------------------------------------
# Hardware
# ---------------------------------------------------------------------------
def hex_bolt(d, af, head_h, length, wire_hole=True):
    """Drilled-head hex bolt: bearing face z = 0, head up +Z, shank down."""
    head = F._wrench_head(af, 0.0, head_h, chamfer_bottom=True, dish=0.0)
    ch = 0.8
    shank = F._rev([(0, -length), (d / 2 - ch, -length), (d / 2, -length + ch), (d / 2, 0.5), (0, 0.5)])
    b = C.fuse_all([head, shank])
    if wire_hole:
        b = b - (bd.Pos(0, 0, head_h * 0.5) * bd.Rot(90, 0, 0) * bd.Cylinder(0.8, af * 2))
    return b


def nut(d, af, h):
    body = F._wrench_head(af, 0.0, h, chamfer_bottom=True, dish=0.0)
    return body - bd.Pos(0, 0, -1) * bd.Cylinder(d / 2.0 + 0.05, h + 2, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))


def wire_between(p, q, sag_dir, sag=2.5, d=0.8):
    mid = tuple((a + b) / 2 + sag * s for a, b, s in zip(p, q, sag_dir))
    path = bd.Edge.make_spline([bd.Vector(*p), bd.Vector(*mid), bd.Vector(*q)])
    prof = bd.Plane(origin=path @ 0.0, z_dir=path % 0.0) * bd.Circle(d / 2.0)
    return bd.sweep(prof, path=path)


def cotter(length, d=2.4):
    shaft = bd.Pos(0, 0, -length) * bd.Cylinder(d / 2.0, length, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    eye = bd.Pos(0, 0, 2.0) * bd.Rot(90, 0, 0) * bd.Torus(2.0, d / 2.0)
    return C.fuse_all([shaft, eye])


# clamp ring: authored for the blade at in-plane 0 (axis +Z), split + ears FORWARD (-Y)
EAR_T, EAR_GAP, EAR_OUT = 10.0, 5.0, 84.0     # ear thickness (along X), split gap, ear reach (-Y from axis)
RING_BOLT_Y = HUB_Y - 76.0


def clamp_ring():
    s0, s1 = RING_S
    ring = F._rev([(SOCKET_R + 0.15, s0 + 0.8), (SOCKET_R + 0.95, s0), (RING_OR - 1.0, s0), (RING_OR, s0 + 1.0),
                   (RING_OR, s1 - 1.0), (RING_OR - 1.0, s1), (SOCKET_R + 0.95, s1), (SOCKET_R + 0.15, s1 - 0.8)])
    ears = []
    for sgn in (-1, 1):
        x0 = sgn * EAR_GAP / 2.0
        box = bd.Box(EAR_T, EAR_OUT - (SOCKET_R + 4.0), s1 - s0 - 2.0,
                     align=(bd.Align.MIN if sgn > 0 else bd.Align.MAX, bd.Align.MAX, bd.Align.MIN))
        ears.append(bd.Pos(x0, -(SOCKET_R + 4.0), s0 + 1.0) * box)
    body = C.fuse_all([ring] + ears)
    # the split, the bore (ears reach into the ring wall), the bolt hole
    slot = bd.Pos(0, -SOCKET_R + 3.0, s0 - 5) * bd.Box(EAR_GAP, EAR_OUT, s1 - s0 + 10, align=(bd.Align.CENTER, bd.Align.MAX, bd.Align.MIN))
    bore = bd.Pos(0, 0, s0 - 5) * bd.Cylinder(SOCKET_R + 0.15, s1 - s0 + 10, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    hole = bd.Pos(0, RING_BOLT_Y - HUB_Y, 0.5 * (s0 + s1)) * bd.Rot(0, 90, 0) * bd.Cylinder(4.2, 60)
    body = C.cut_all(body, [slot, bore, hole])
    # break the ear edges
    ed = [e for e in body.edges() if C.edge_center(e).Y < -(SOCKET_R + 6.0) and e.geom_type == bd.GeomType.LINE]
    body, _ = C.safe_fillet(body, ed, 1.5, min_r=0.5)
    return bd.Pos(0, HUB_Y, 0) * body


def ring_hardware():
    """Bolt (head on the +X ear), nut on the -X ear, cotter through the nut; authoring frame blade 0."""
    s0, s1 = RING_S
    zc = 0.5 * (s0 + s1)
    x_face = EAR_GAP / 2.0 + EAR_T
    bolt = hex_bolt(8.0, 12.7, 5.5, 2 * x_face + 10.0, wire_hole=False)
    b = F.place(bolt, (x_face, RING_BOLT_Y, zc), (1, 0, 0), (0, 0, 1))
    nt = nut(8.0, 12.7, 7.0)
    n = F.place(nt, (-x_face, RING_BOLT_Y, zc), (-1, 0, 0), (0, 0, 1))
    return b, n


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
def build():
    SM, SD, PA, FA, SW = P.STEEL_MACHINED, P.STEEL_POLISHED, P.POLISHED_ALU, P.FASTENER, P.SAFETY_WIRE
    rot = _rot(PHASE)
    parts = []

    hub = hub_body()
    spl = hub_splines()
    big = 2000.0
    front_box = bd.Pos(0, HUB_Y - SPLIT_GAP, 0) * bd.Box(big, big, big, align=(bd.Align.CENTER, bd.Align.MAX, bd.Align.CENTER))
    rear_box = bd.Pos(0, HUB_Y + SPLIT_GAP, 0) * bd.Box(big, big, big, align=(bd.Align.CENTER, bd.Align.MIN, bd.Align.CENTER))
    hub_f = C.fuse_all([hub & front_box, spl & front_box])
    hub_r = C.fuse_all([hub & rear_box, spl & rear_box])
    parts.append(_style(rot * hub_f, "prop:hub_front", SD))
    parts.append(_style(rot * hub_r, "prop:hub_rear", SD))
    parts.append(_style(rot * front_cone(), "prop:front_cone", SM))

    # through-bolts in the lugs: heads forward, nuts on the rear face
    L = BARREL_Y[1] - BARREL_Y[0]
    bolt = hex_bolt(BOLT_D, 14.3, 6.0, L + 10.5)
    nt = nut(BOLT_D, 14.3, 7.5)
    for k in range(3):
        loc = rot * _rot(120.0 * k)
        heads = []
        for i, (x, z) in enumerate(lug_bolt_points()):
            radial = _ip(60.0)
            parts.append(_style(loc * F.place(bolt, (x, BARREL_Y[0], z), (0, -1, 0), (radial[0], 0, radial[2])),
                                f"prop:barrel_bolt_{k + 1}_{i + 1}", FA))
            parts.append(_style(loc * F.place(nt, (x, BARREL_Y[1], z), (0, 1, 0), (radial[0], 0, radial[2])),
                                f"prop:barrel_nut_{k + 1}_{i + 1}", FA))
            heads.append((x, z))
        # wire between the two heads (holes drilled across the flats, radial)
        yw = BARREL_Y[0] - 3.0
        (x1, z1), (x2, z2) = heads
        r1 = np.array(_ip(60.0))
        p = (x1 + r1[0] * 7.2, yw, z1 + r1[2] * 7.2)
        q = (x2 + r1[0] * 7.2, yw, z2 + r1[2] * 7.2)
        parts.append(_style(loc * wire_between(p, q, tuple(r1), sag=4.0), f"prop:barrel_wire_{k + 1}", SW))

    ring = clamp_ring()
    rb, rn = ring_hardware()
    blade = blade_proto()
    for k in range(3):
        loc = rot * _rot(120.0 * k)
        parts.append(_style(loc * ring, f"prop:clamp_ring_{k + 1}", SM))
        parts.append(_style(loc * rb, f"prop:clamp_ring_bolt_{k + 1}", FA))
        parts.append(_style(loc * rn, f"prop:clamp_ring_nut_{k + 1}", FA))
        parts.append(_style(loc * blade, f"prop:blade_{k + 1}", PA))
    return parts


if __name__ == "__main__":
    import sys
    import time
    t0 = time.time()
    if "blade" in sys.argv:
        b = blade_proto()
        print("blade sound", geo.sound(b), round(b.volume), f"{time.time() - t0:.1f}s")
        bb = b.bounding_box()
        print(bb.min, bb.max)
        sys.exit()
    ps = build()
    bad = [p.label for p in ps if not geo.sound(p)]
    print(len(ps), "parts", f"{time.time() - t0:.1f}s", "unsound:", bad)
    for p in ps:
        bb = p.bounding_box()
        print(f"{p.label:30s} vol {p.volume:10.0f} y[{bb.min.Y:7.1f},{bb.max.Y:7.1f}]")
