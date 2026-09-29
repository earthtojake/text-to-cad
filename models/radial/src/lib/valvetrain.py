"""Valvetrain: 18 valves with retainers and split keepers, 36 concentric valve
springs, 18 spring-seat washers, 18 forged rockers (needle bearings, adjusting
screws, locknuts) and 18 rocker shafts with their nuts and washers.

Authoring. Every rigid part is authored ONCE for cylinder 1 at ZERO LIFT
(rocker angle 0) directly in engine coordinates (cylinder 1: h = +Z, t = +X),
from the kin points (valve_seat/axis/tip, rocker_pivot, pad_centre0,
pushrod_top0). Cylinder k gets `geo.on_cylinder(proto, k)` and then its
theta = 0 pose, `kin.place(part, kin.pose_valve(0, k, v))` or
`kin.pose_rocker(0, k, v)`. The springs are the exception: each is swept
directly along `kin.spring_path(0.0, k, v, which)` (the theta = 0 compressed
shape the viewer's tube deformation starts from).

Valve-local numbers (`z` along the valve axis from the seat-face centre, tip at
z = 150): 45 deg seat face centred at z = 0, spring-seat plane z = 86
(tip - 64), retainer underside z = 136 (tip - 14).
"""

from __future__ import annotations

import math

from cadgen import build123d as bd

from lib import castings as CA
from lib import fasteners as F
from lib import geo
from lib import kin
from lib import palette as P
from lib import spec as S

MATERIALS = ("blued_steel", "fastener", "steel_machined")

VALVES = ("I", "E")
TIP_Z = S.VALVE_LENGTH                                   # 150
SEAT_PLANE_Z = TIP_Z - kin.SPRING_SEAT_FROM_TIP          # 86
RET_UNDER_Z = TIP_Z - kin.SPRING_TOP_FROM_TIP            # 136
STEM_R = S.VALVE_STEM_D / 2.0

# keeper grooves on the stem (centres, valve z) and the retainer/keeper cone
GROOVES = (139.5, 143.0)
CONE_Z0, CONE_R0, CONE_Z1, CONE_R1 = 133.5, 8.3, 143.0, 9.9
RET_R = 20.5                                             # retainer rim (outer spring OD 38.2)
KEEPER_Z = (134.3, 144.5)
SPRING_GAP = 0.05          # seat/retainer faces stand 0.05 off the spring wire ends (no tangent contact)

# rocker (cylinder-1 local; see _rocker_parts)
SHAFT_R = 7.0
SHAFT_Y = S.ROCKER_SHAFT_Y                               # (-112, 14)
BOSS_R = 15.0
BORE_R = 11.35                                           # needle-bearing bore
TUBE_R, TUBE_BORE_R = 12.0, 8.5
ADJ_SEAM = (0.0, 1.0, 0.0)
SEAT_TRIM = 0.3                                          # boss face machined below the as-forged top (no coplanar cut)
REAR_BORE_R = 10.35                                      # slim drawn-cup needle bearing (rear)
REAR_FLAT = 12.5                                         # inboard flat on the rear boss, from the pivot
FRONT_BOSS_Y = (-108.0, -90.0)
REAR_BOSS_Y = (-11.0, 7.0)
ARM_HALF_W = 7.0                                         # valve arm |y| <= 7
FRONT_WEB_Y = (-108.0, -84.0)
BALL_R = 7.0                                             # pushrod top ball (pushrods builder)
SOCKET_R = BALL_R + 0.05
ADJ_BOSS = (9.0, 21.0, 10.0)                             # (from, to along the pushrod axis, radius)
ADJ_THREAD_R = 5.0
ADJ_TOP = 31.5
ARM_FILLET = 2.5
NUT_LIFT = 0.1                                           # locknut seat gap above the boss face


# ---------------------------------------------------------------------------
# small vector helpers
# ---------------------------------------------------------------------------
def _v(p):
    return bd.Vector(*p)


def _add(a, b, s=1.0):
    return (a[0] + s * b[0], a[1] + s * b[1], a[2] + s * b[2])


def _unit(a):
    n = math.sqrt(sum(x * x for x in a))
    return tuple(x / n for x in a)


def _revolve_rz(items, arc=360.0):
    """Closed (r, z) outline in the XZ half-plane revolved about Z. Items are
    (r, z) points, ("arc", mid, end) or ("spline", [pts...], t0, t1)."""
    edges = []
    start = items[0]
    cur = bd.Vector(start[0], 0.0, start[1])
    for it in items[1:] + [start]:
        if isinstance(it, tuple) and it and it[0] == "arc":
            _, mid, end = it
            nxt = bd.Vector(end[0], 0.0, end[1])
            edges.append(bd.ThreePointArc(cur, bd.Vector(mid[0], 0.0, mid[1]), nxt))
        elif isinstance(it, tuple) and it and it[0] == "spline":
            _, pts, t0, t1 = it
            vs = [cur] + [bd.Vector(p[0], 0.0, p[1]) for p in pts]
            nxt = vs[-1]
            edges.append(bd.Spline(*vs, tangents=[bd.Vector(t0[0], 0, t0[1]), bd.Vector(t1[0], 0, t1[1])]))
        else:
            nxt = bd.Vector(it[0], 0.0, it[1])
            if (nxt - cur).length < 1e-9:
                continue
            edges.append(bd.Line(cur, nxt))
        cur = nxt
    face = bd.make_face(bd.Wire(edges))
    return bd.revolve(face, axis=bd.Axis.Z, revolution_arc=arc)


def _valve_frame(v) -> bd.Plane:
    """Valve-local frame on cylinder 1: origin at the seat-face centre, +Z along
    the stem (seat -> tip), +X outboard in the cylinder-row plane."""
    a = kin.valve_axis(1, v)
    s = 1.0 if v == "I" else -1.0
    ci, si = math.cos(math.radians(S.VALVE_INCLINE_DEG)), math.sin(math.radians(S.VALVE_INCLINE_DEG))
    lat = (s * ci, 0.0, -si)
    return geo.plane(kin.valve_seat(1, v), a, lat)


def _cone_r(z):
    return CONE_R0 + (z - CONE_Z0) * (CONE_R1 - CONE_R0) / (CONE_Z1 - CONE_Z0)


# ---------------------------------------------------------------------------
# Valve, retainer, keepers, spring seat (valve-local, placed by _valve_frame)
# ---------------------------------------------------------------------------
def _valve_local(v):
    R = S.VALVE_HEAD_D[v] / 2.0
    fw = 2.2                                      # seat face half-height (45 deg)
    top = (R - 2 * fw, fw)
    if v == "I":
        tulip = [(15.5, 6.0), (9.2, 14.0), (STEM_R, 34.0)]
    else:
        tulip = [(14.5, 6.2), (9.0, 14.0), (STEM_R, 34.0)]
    pts = [(0.0, -4.0), (R - 0.6, -4.0), (R, -3.4), (R, -fw), top,
           ("spline", tulip, (-1.0, 0.28), (0.0, 1.0))]
    for zc in GROOVES:                             # keeper grooves
        pts += [(STEM_R, zc - 0.8), (STEM_R - 0.7, zc - 0.3), (STEM_R - 0.7, zc + 0.3), (STEM_R, zc + 0.8)]
    pts += [(STEM_R, TIP_Z - 0.7), (STEM_R - 0.7, TIP_Z), (0.0, TIP_Z)]
    return _revolve_rz(pts)


def _retainer_local():
    z0, z1 = CONE_Z0, CONE_Z1
    zu = RET_UNDER_Z + SPRING_GAP
    pts = [(_cone_r(z0), z0), (9.1, z0), (9.4, z0 + 0.3), (9.4, zu),
           (RET_R - 0.4, zu), (RET_R, zu + 0.4), (RET_R, 138.8),
           (RET_R - 0.6, 139.4), (12.5, 141.8), (11.5, z1), (_cone_r(z1), z1)]
    return _revolve_rz(pts)


def _keepers_local():
    zb, zt = KEEPER_Z
    ro = lambda z: _cone_r(z) - 0.1
    ri = STEM_R + 0.1
    pts = [(ri, zb), (ro(zb) - 0.3, zb), (ro(zb), zb + 0.3), (ro(zt) - 0.5, zt - 0.5),
           (ro(zt) - 1.0, zt), (ri + 0.3, zt), (ri, zt - 0.3)]
    for zc in reversed(GROOVES):                   # beads engaging the grooves
        pts += [(ri, zc + 0.65), (STEM_R - 0.6, zc + 0.2), (STEM_R - 0.6, zc - 0.2), (ri, zc - 0.65)]
    whole = _revolve_rz(pts)
    gap = 0.4
    big = 60.0
    a = whole & bd.Pos(gap + big / 2, 0, 140) * bd.Box(big, big, big)
    b = whole & bd.Pos(-gap - big / 2, 0, 140) * bd.Box(big, big, big)
    return a, b


def _spring_seat_local():
    z = SEAT_PLANE_Z - SPRING_GAP
    pts = [(9.6, z - 2.2), (9.9, z - 2.5), (21.1, z - 2.5), (21.5, z - 2.1), (21.5, z + 1.2),
           (21.1, z + 1.6), (20.0, z + 1.6), (19.6, z + 1.2), (19.6, z), (10.0, z), (9.6, z - 0.4)]
    return _revolve_rz(pts)


# ---------------------------------------------------------------------------
# Rocker (cylinder-1 engine coordinates, rest pose)
# ---------------------------------------------------------------------------
def _xz_face(pts_xz, y=0.0):
    pts3 = [bd.Vector(x, y, z) for x, z in pts_xz]
    return bd.make_face(bd.Polyline(*pts3, close=True).edges())


def _slab(face_xz_at_y0, y0, y1):
    """Extrude a face lying in the plane y = y0 to y = y1."""
    f = bd.Pos(0, y0, 0) * face_xz_at_y0
    return bd.extrude(f, amount=y1 - y0, dir=(0, 1, 0))


def _hull2(pts):
    pts = sorted(set((round(x, 6), round(z, 6)) for x, z in pts))

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _pushrod_dir(v):
    return _unit(kin._sub(kin.pushrod_top0(1, v), kin.pushrod_bottom0(1, v)))


def _pushrod_swing(v, n=12):
    """Largest angle (deg) between the pushrod's rest axis and its axis at any
    tappet lift, seen in the ROCKER's frame (it swings about the top ball)."""
    B = kin.pushrod_top0(1, v)
    d = _pushrod_dir(v)
    worst = 0.0
    for i in range(n + 1):
        lt = S.TAPPET_LIFT[v] * i / n
        ang = kin._rocker_angle_for(1, v, lt)
        Bt = kin._addv(kin.pushrod_bottom0(1, v), kin.tappet_dir(1, v), lt)
        Tt = kin._rot_about(B, kin.ROCKER_AXIS, ang, kin.rocker_pivot(1, v))
        d_rel = kin._rot_about(_unit(kin._sub(Tt, Bt)), kin.ROCKER_AXIS, -ang, (0.0, 0.0, 0.0))
        c = max(-1.0, min(1.0, sum(d[k] * d_rel[k] for k in range(3))))
        worst = max(worst, math.degrees(math.acos(c)))
    return worst


def _pushrod_clearance(v, r=10.5, below=60.0, top=None):
    """The pushrod's swept space in the ROCKER's frame as ONE revolved solid on
    the rest axis: a Ø21 bore up to the adjusting-screw boss (clears the socket
    cup and ball), flaring below the ball into a cone that holds the pushrod
    at every lift (half-angle = the largest relative swing + 2 deg)."""
    B = kin.pushrod_top0(1, v)
    d = _pushrod_dir(v)
    top = ADJ_BOSS[0] if top is None else top
    k = math.tan(math.radians(_pushrod_swing(v) + 2.0))
    pts = [(0.0, top), (r, top), (r, -4.0), (r + (below - 4.0) * k, -below), (0.0, -below)]
    return geo.locate(_revolve_rz(pts), B, d, (0.0, 1.0, 0.0))


def _rocker_arm(v):
    s = 1.0 if v == "I" else -1.0
    Pv = kin.rocker_pivot(1, v)
    px, pz = Pv[0], Pv[2]
    A = kin.valve_axis(1, v)
    ci, si = math.cos(math.radians(S.VALVE_INCLINE_DEG)), math.sin(math.radians(S.VALVE_INCLINE_DEG))
    L = (s * ci, 0.0, -si)
    T = kin.valve_tip(1, v)
    C = kin.pad_centre0(1, v)

    def vf(sl, a):          # valve-frame (lateral outboard, along axis from tip) -> (x, z)
        return (T[0] + a * A[0] + sl * L[0], T[2] + a * A[2] + sl * L[2])

    # valve arm web: underside arched clear of the retainer, top crowned
    web = [vf(-33.0, -13.0), vf(-24.0, -4.5), vf(-8.0, 4.0), vf(-5.0, 21.0),
           vf(-21.0, 13.5), vf(-36.0, 4.5)]
    if s < 0:
        web = list(reversed(web))
    valve_web = _slab(_xz_face(web), -ARM_HALF_W, ARM_HALF_W)
    pad = bd.Pos(*C) * bd.Sphere(kin.ROCKER_PAD_R)
    pad = pad & bd.Pos(C[0], 0, C[2]) * bd.Box(40, 2 * ARM_HALF_W, 40)

    # hub: two needle-bearing bosses joined by a slim torsion tube
    rear_boss = geo.cyl_y(REAR_BOSS_Y[0], REAR_BOSS_Y[1], 2 * BOSS_R, px, pz)
    front_boss = geo.cyl_y(FRONT_BOSS_Y[0], FRONT_BOSS_Y[1], 2 * BOSS_R, px, pz)
    tube = geo.cyl_y(FRONT_BOSS_Y[1] - 2.0, REAR_BOSS_Y[0] + 2.0, 2 * TUBE_R, px, pz)

    # pushrod arm: web from the front boss to the adjusting-screw boss
    B = kin.pushrod_top0(1, v)
    d = _pushrod_dir(v)
    dxz = _unit((d[0], 0.0, d[2]))
    nxz = (dxz[2], 0.0, -dxz[0])
    a0, a1, rb = ADJ_BOSS
    corners = []
    for a in (a0, a1):
        c = _add(B, d, a)
        for sg in (-1, 1):
            corners.append((c[0] + sg * rb * nxz[0], c[2] + sg * rb * nxz[2]))
    hub = [(px + 13.0 * math.cos(t), pz + 13.0 * math.sin(t)) for t in
           [2 * math.pi * i / 24 for i in range(24)]]
    front_web = _slab(_xz_face(_hull2(hub + corners)), FRONT_WEB_Y[0], FRONT_WEB_Y[1])
    front_web = front_web - _pushrod_clearance(v)
    # seam of the boss cylinder turned to face along the rocker (ADJ_SEAM): with the
    # default seam the exhaust arm's boss face did not survive a STEP round trip
    adj_boss = geo.locate(bd.Cylinder(rb, a1 - a0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)),
                          _add(B, d, a0), d, ADJ_SEAM)

    body = rear_boss + [front_boss, tube, valve_web, pad, front_web, adj_boss]
    # the pad (sphere cut by the arm's side faces) stays sharp-edged: a rolling
    # fillet there left an edge that self-intersects the sphere after STEP I/O
    near_pad = lambda e: (CA.edge_center(e) - bd.Vector(*C)).length < kin.ROCKER_PAD_R + 1.5
    body, _ = CA.fillet_all(body, ARM_FILLET, exclude=near_pad, min_r=0.8)
    cutters = [
        geo.cyl_y(FRONT_BOSS_Y[0] - 1.0, FRONT_BOSS_Y[1] - 1.0, 2 * BORE_R, px, pz),
        geo.cyl_y(REAR_BOSS_Y[0] + 1.0, REAR_BOSS_Y[1] + 1.0, 2 * REAR_BORE_R, px, pz),
        # lift-out flat on the rear boss's inboard cheek: the box casting overhangs
        # the hub there (rocker lifts out along the cylinder axis once the cover is off)
        bd.Pos(px - s * (REAR_FLAT + 15.0), (REAR_BOSS_Y[0] + REAR_BOSS_Y[1]) / 2, pz)
        * bd.Box(30.0, REAR_BOSS_Y[1] - REAR_BOSS_Y[0] + 2.0, 60.0),
        geo.cyl_y(FRONT_BOSS_Y[1] - 1.5, REAR_BOSS_Y[0] + 1.5, 2 * TUBE_BORE_R, px, pz),
        geo.cyl_along(_add(B, d, a0 - 1.0), _add(B, d, a1 + 1.0), 2 * (ADJ_THREAD_R + 0.05)),
        geo.cyl_along(_add(B, d, a1 - SEAT_TRIM), _add(B, d, a1 + 25.0), 2 * 12.5),   # locknut seat: machined boss face, nothing above it
    ]
    return body - cutters


def _needle_bearing(v, y0, y1, slim=False):
    Pv = kin.rocker_pivot(1, v)
    px, pz = Pv[0], Pv[2]
    lip = 0.8
    # (race OD, race ID, needle circle, needle r, count); the rear one is a slim
    # drawn cup so its boss can carry the lift-out flat (REAR_FLAT)
    ro, ri, rc, rn, n = (10.3, 8.9, 8.1, 1.0, 22) if slim else (11.3, 9.3, 8.3, 1.2, 19)
    race = geo.cyl_y(y0, y1, 2 * ro, px, pz) - geo.cyl_y(y0 - 1, y1 + 1, 2 * ri, px, pz)
    lips = [geo.cyl_y(y0, y0 + lip, 2 * (ri + 0.05), px, pz) - geo.cyl_y(y0 - 1, y0 + lip + 1, 2 * 8.0, px, pz),
            geo.cyl_y(y1 - lip, y1, 2 * (ri + 0.05), px, pz) - geo.cyl_y(y1 - lip - 1, y1 + 1, 2 * 8.0, px, pz)]
    needles = [geo.cyl_y(y0 + lip + 0.1, y1 - lip - 0.1, 2 * rn,
                         px + rc * math.cos(2 * math.pi * i / n), pz + rc * math.sin(2 * math.pi * i / n))
               for i in range(n)]
    return race + lips + needles


def _adjuster(v):
    B = kin.pushrod_top0(1, v)
    d = _pushrod_dir(v)
    r = ADJ_THREAD_R
    pts = [(0.0, 0.5), (8.0, 0.5), (9.0, 1.5), (9.0, 7.2), (8.2, 8.0), (r, 8.0),
           (r, ADJ_TOP - 0.6), (r - 0.6, ADJ_TOP), (0.0, ADJ_TOP)]
    body = _revolve_rz(pts)
    slot = bd.Pos(0, 0, ADJ_TOP) * bd.Box(1.8, 14.0, 5.0)
    oil = bd.Cylinder(1.2, 60.0)
    body = body - [bd.Sphere(SOCKET_R), slot, oil]
    return geo.locate(body, B, d, (0.0, 1.0, 0.0))


def _locknut(v):
    B = kin.pushrod_top0(1, v)
    d = _pushrod_dir(v)
    nut = F.hex_nut(10) - bd.Pos(0, 0, -5) * bd.Cylinder(ADJ_THREAD_R + 0.15, 30.0)
    return geo.locate(nut, _add(B, d, ADJ_BOSS[1] - SEAT_TRIM + NUT_LIFT), d, (0.0, 1.0, 0.0))


# ---------------------------------------------------------------------------
# Rocker shaft (static) + nuts and washers outside the box walls
# ---------------------------------------------------------------------------
def _shaft(v):
    Pv = kin.rocker_pivot(1, v)
    px, pz = Pv[0], Pv[2]
    y0, y1 = SHAFT_Y
    rt = F.minor_diameter(10) / 2.0 - 0.1                 # 0.1 clear of the nut bore
    ext = 12.0
    pts = [(0.0, y0 - ext), (rt - 0.6, y0 - ext), (rt, y0 - ext + 0.6), (rt, y0), (SHAFT_R - 0.5, y0),
           (SHAFT_R, y0 + 0.5), (SHAFT_R, y1 - 0.5), (SHAFT_R - 0.5, y1), (rt, y1),
           (rt, y1 + ext - 0.6), (rt - 0.6, y1 + ext), (0.0, y1 + ext)]
    # revolve about local Z, then lay Z along +Y at the pivot
    body = _revolve_rz(pts)
    return geo.locate(body, (px, 0.0, pz), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0))


def _shaft_hardware(v):
    Pv = kin.rocker_pivot(1, v)
    px, pz = Pv[0], Pv[2]
    y0, y1 = SHAFT_Y
    w = F.washer(10)
    wt = w.bounding_box().max.Z
    nut = F.hex_nut(10)
    out = []
    for i, (y, sgn) in enumerate(((y0, -1.0), (y1, 1.0)), start=1):
        out.append((f"shaft_washer_{{}}_{i}", geo.locate(w, (px, y, pz), (0.0, sgn, 0.0), (1.0, 0.0, 0.0))))
        out.append((f"shaft_nut_{{}}_{i}", geo.locate(nut, (px, y + sgn * wt, pz), (0.0, sgn, 0.0), (1.0, 0.0, 0.0))))
    return out


# ---------------------------------------------------------------------------
# Springs: swept exactly along kin.spring_path(theta = 0)
# ---------------------------------------------------------------------------
def spring(theta, k, v, which):
    p = kin.spring_path(theta, k, v, which)
    edges = [bd.Bezier(*[bd.Vector(*q) for q in s["points"]]) for s in p["segments"]]
    path = bd.Wire(edges)
    wire_d = kin.SPRINGS[which][1]
    e0 = edges[0]
    prof = bd.Plane(origin=e0.position_at(0), z_dir=e0.tangent_at(0)) * bd.Circle(wire_d / 2.0)
    return bd.sweep(prof, path=path, is_frenet=True)


# ---------------------------------------------------------------------------
# Prototypes (cylinder 1, zero lift) and assembly
# ---------------------------------------------------------------------------
_PROTO = None


def prototypes():
    """{v: {"valve": [(name, shape, color)], "rocker": [...], "static": [...]}}"""
    global _PROTO
    if _PROTO is not None:
        return _PROTO
    out = {}
    ret, (ka, kb), seat = _retainer_local(), _keepers_local(), _spring_seat_local()
    for v in VALVES:
        fr = _valve_frame(v)
        valve = _valve_local(v)
        vparts = [("valve", fr * valve, P.STEEL_MACHINED)]
        vparts += [("retainer", fr * ret, P.STEEL_MACHINED),
                   ("keeper_a", fr * ka, P.STEEL_MACHINED),
                   ("keeper_b", fr * kb, P.STEEL_MACHINED)]
        Pv = kin.rocker_pivot(1, v)
        bearing = (_needle_bearing(v, FRONT_BOSS_Y[0] + 0.5, FRONT_BOSS_Y[1] - 1.5)
                   + _needle_bearing(v, REAR_BOSS_Y[0] + 1.5, REAR_BOSS_Y[1] - 0.5, slim=True))
        rparts = [("arm", _rocker_arm(v), P.STEEL_MACHINED),
                  ("bearing", bearing, P.STEEL_MACHINED),
                  ("adjuster", _adjuster(v), P.STEEL_MACHINED),
                  ("locknut", _locknut(v), P.FASTENER)]
        static = [("spring_seat_{}", fr * seat, P.STEEL_MACHINED),
                  ("rocker_shaft_{}", _shaft(v), P.STEEL_MACHINED)]
        static += [(n, s_, P.FASTENER) for n, s_ in _shaft_hardware(v)]
        out[v] = {"valve": vparts, "rocker": rparts, "static": static}
        del Pv
    _PROTO = out
    return out


def build():
    protos = prototypes()
    parts = []
    for k in range(1, S.N_CYL + 1):
        for v in VALVES:
            pr = protos[v]
            kv = f"{k}{v}"
            for name, shape, color in pr["valve"]:
                parts.append(P.style(kin.place(geo.on_cylinder(shape, k), kin.pose_valve(0.0, k, v)),
                                     f"valve{kv}:{name}", color))
            for name, shape, color in pr["rocker"]:
                parts.append(P.style(kin.place(geo.on_cylinder(shape, k), kin.pose_rocker(0.0, k, v)),
                                     f"rocker{kv}:{name}", color))
            for which in ("outer", "inner"):
                parts.append(P.style(spring(0.0, k, v, which), f"spring{kv}:{which}", P.BLUED_STEEL))
            for name, shape, color in pr["static"]:
                parts.append(P.style(geo.on_cylinder(shape, k), f"valvetrain:{name.format(kv)}", color))
    return parts
