"""Ignition: the polished harness ring, eighteen braided leads with shielded
plug elbows, the ring's clamp brackets and the two magneto feeds.

Authored ONCE for cylinder 1 (t = +X, y = +Y, h = +Z) and placed on cylinders
2..9 with `geo.on_cylinder`, so the star is exact.

HARNESS RING (`ignition:ring`, polished aluminium conduit, one solid)
  torus R_RING 276 about the crank axis at y -121.5, tube Ø12 (spec Ø14 at
  y -119 would sit 2.3 mm from the exhaust pushrod tubes and 0.3 mm from the
  front drain plug at 180; Ø12 here clears both by > 3.5 mm), between the
  crankcase front (drum and nose flange r 262, flange nuts on r 250) and the
  exhaust pushrod tubes. 18 outlet stubs, one every 20 deg in-plane (front
  leads at ALPHA(k), rear leads at ALPHA(k)+20 = the mid-plane between k and
  k+1), all identical, tilted TAU 18 deg forward of radial so each front lead
  leaves in one clean line; each carries a hex ferrule nut (`ring_nut_<k>F/R`).
  Two larger feed stubs at in-plane +-90 (outboard-rear) take the magneto feeds.

LEADS (`lead_<k>F/R`, Ø8 braided conduit) are swept along filleted polylines
  (straight runs + true arcs, every bend R >= 24 = 3 x D: taut, never draped).
  FRONT: ring outlet -> one straight run up the middle of the pushrod V
  (t = 0) -> one 58 deg arc (R 45) into the plug elbow, whose exit points
  forward-down. REAR: ring outlet -> one straight spoke on the mid-plane
  continuing the outlet's forward tilt (y -126 -> -150, in front of the
  heads, the same rhythm as the front leads) -> 108 deg arc (R 30) into a
  GALLERY that runs straight aft along the mid-plane at r GALLERY_R 408
  (t -139.5, h 383.4: 10 mm outside the barrel fins' tip radius 126, below
  the heads' side fins, which stay >= 13 mm off the mid-plane) -> arc (R 30)
  at y Y_BACK 172 into a run across BEHIND the cylinder at h 383 (under the
  exhaust stack and its port flange) to t = 0 -> arc (R 26) up a short riser
  behind the rear plug -> 40 deg arc (R 24) into the rear plug elbow, whose
  exit points rearward-down (in front of the exhaust collector).
  EXPLODE RULE (binding): no lead point lies in the swept extrusion of any
  cylinder k's head, barrel, plugs or exhaust studs along its bore axis,
  outward to infinity, so each cylinder slides straight out past the harness
  (margins: rear lead >= 9.5 mm, front lead >= 16 mm). Behind the cylinder
  the rear run stays at y >= 168 (plug <= 141, studs <= 136, head <= 124) and
  below h 389 where it crosses the stack's (t, h) footprint, so the stack
  also slides straight off rearward.
ELBOWS (`elbow_<k>F/R`) are period shielded 90 deg elbows: a coupling nut
  (`elbow_nut_`) threaded on the plug's shielding barrel, a cap over the
  terminal, a bend (R 13) and a ferrule nut (`elbow_lead_nut_`).

SUPPORT (nothing floats)
  * `ring_clamp_<n>`: six brackets at the mid-planes 20, 60, 140, 220, 300,
    340 (mirror-symmetric left/right): a saddle hugging the ring and a flat
    arm back to a hex SOCKET CAP keyed over the crankcase through-bolt head
    (r 272, y -72..-82; 0.25 mm socket clearance). Not at 180 (the front
    drain plug and its safety wire own that through-bolt head) nor at 100 /
    260 (the feed gaps: the feeds, anchored at the magnetos, carry the ring
    there). Each lead is carried by its ring outlet and its plug elbow.
MAGNETO FEEDS (`feed_L` x < 0 seen from the front, stub at in-plane +90;
  `feed_R` its mirror): Ø9 braided conduit from the ring's feed stub, round
  the ring into the mid-plane 100 / 260 lane at r 297 (below the barrel fins),
  lifted to r 307 over the pad crease at the split line, back past the
  blower outlets, round behind the blower (r 250, y 300) to a terminal block
  (`feed_terminal_L/R`) whose REAR FACE is at y 370, centre (-+150, 370, 130):
  the magneto's distributor face mates there (the accessory builder must keep
  r 245..255 at y 290..310 between in-plane +-60 and +-100 clear for the feeds).

MUSEUM SECTION: cylinder 1's rear plug/elbow lies wholly in the removed rear
region (omitted); its rear lead is cut on the section plane y = 0 (it runs on
the sector's +-20 deg boundary) and the cut face carries a SKIN_T red skin
(`section_skin_lead_1R`) lying in the removed region.
"""

from __future__ import annotations

import math

from cadgen import build123d as bd

from lib import geo
from lib import palette as P
from lib import spec as S

MATERIALS = ("braid", "fastener", "polished_alu", "section_red", "steel_polished")

# ---------------------------------------------------------------------------
# Numbers (mm)
# ---------------------------------------------------------------------------
R_RING = 276.0
Y_RING = -121.5
RT = 6.0                          # ring tube radius (Ø12: Ø14 leaves < 3 mm to the exhaust pushrod tubes)
TAU = math.radians(18.0)          # outlet tilt forward of radial
STUB_R = 4.6
STUB_END = 16.0                   # stub end (lead start) from the ring centre line
NUT_AF, NUT_D = 12.0, (9.0, 17.0)  # ferrule nut: across flats, span along the outlet axis
LEAD_R = 4.0

PLUG_ELEV = math.radians(50.0)
PLUG_FACE = {"F": (0.0, -95.0, 478.0), "R": (0.0, 95.0, 478.0)}
PLUG_AXIS = {"F": (0.0, -math.sin(PLUG_ELEV), math.cos(PLUG_ELEV)),
             "R": (0.0, math.sin(PLUG_ELEV), math.cos(PLUG_ELEV))}
ELBOW_EXIT = {"F": (0.0, -math.cos(PLUG_ELEV), -math.sin(PLUG_ELEV)),   # forward-down
              "R": (0.0, math.cos(PLUG_ELEV), -math.sin(PLUG_ELEV))}   # rearward-down
ELBOW_BEND_R = 13.0
ELBOW_CAP = (47.05, 58.0)         # cap span along the plug axis
ELBOW_TURN_Z = 58.0               # bend starts here along the plug axis
ELBOW_LEG = 6.0                   # straight after the bend
ELBOW_SPIGOT = 7.0                # spigot inside the lead nut
ELBOW_TUBE_R = 7.0

GALLERY_R = 408.0                 # rear-lead gallery radius on the mid-plane (t -139.5, h 383.4)
Y_BACK = 172.0                    # rear run: behind plug (y <= 141), studs (136), head (124)
RB_SPOKE, RB_GALLERY, RB_UNDER, RB_RISE = 30.0, 30.0, 26.0, 24.0   # rear-lead bends (>= 3 x D)
FEED_LANE_R = 297.0
FEED_R = 4.5
FEED_ANGLE = 90.0                 # feed stub in-plane angle (L side; R mirrored)
FEED_GAP = 100.0
TERMINAL = (-150.0, 370.0, 130.0)  # feed_L terminal rear-face centre (feed_R mirrored in x)

TB_R, TB_Y0 = 272.0, -72.0        # crankcase through-bolt head seat (r, y) on each mid-plane
CUP = {"af": 15.5, "ro": 11.2, "y0": -73.9, "y1": -81.9, "cap": -83.4}
BRACKET_GAPS = (1, 2, 4, 6, 8, 9)  # cylinder k whose +20 mid-plane carries a clamp bracket
FEED_GAPS = {3: "L", 7: "R"}      # 100 and 260


# ---------------------------------------------------------------------------
# vector helpers
# ---------------------------------------------------------------------------
def _add(a, b, s=1.0):
    return (a[0] + s * b[0], a[1] + s * b[1], a[2] + s * b[2])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _len(a):
    return math.sqrt(_dot(a, a))


def _unit(a):
    n = _len(a)
    return (a[0] / n, a[1] / n, a[2] / n)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _m(b_deg):
    """Unit radial vector at in-plane angle b (cylinder-1 frame == engine frame)."""
    return S.inplane(b_deg)


def _pt(b_deg, r, y):
    x, _, z = S.inplane(b_deg, r)
    return (x, y, z)


def _outlet_dir(b_deg):
    m = _m(b_deg)
    return _unit((m[0] * math.cos(TAU), -math.sin(TAU), m[2] * math.cos(TAU)))


def _ring_centre(b_deg):
    return _pt(b_deg, R_RING, Y_RING)


def _one(shape):
    sols = shape.solids()
    if len(sols) == 1:
        return sols[0]
    sols = sorted(sols, key=lambda s: -s.volume)
    if sols[1].volume > 1.0:
        raise RuntimeError(f"expected one solid, got {[round(s.volume) for s in sols]}")
    return sols[0]


def _rev(pts):
    """Solid of revolution about local Z from a closed (r, z) polygon."""
    face = bd.make_face(bd.Polyline(*pts, close=True).edges())
    return bd.revolve(bd.Plane.XZ * face, axis=bd.Axis.Z)


def _hex(af, z0, z1, chamfer=0.8):
    """Hex prism z0..z1 (a flat facing +X), corners double-chamfered by a revolved limiter."""
    r = af / math.sqrt(3.0)
    pts = [(r * math.cos(math.radians(30 + 60 * i)), r * math.sin(math.radians(30 + 60 * i))) for i in range(6)]
    body = bd.Pos(0, 0, z0) * bd.extrude(bd.make_face(bd.Polyline(*pts, close=True).edges()), amount=z1 - z0)
    a = af / 2.0
    lim = _rev([(0.0, z0 - 0.01), (a + 0.2, z0 - 0.01), (r + 0.5, z0 + chamfer), (r + 0.5, z1 - chamfer),
                (a + 0.2, z1 + 0.01), (0.0, z1 + 0.01)])
    return body & lim


def _frame(origin, z_dir, x_dir):
    return geo.plane(origin, z_dir, x_dir)


# ---------------------------------------------------------------------------
# Filleted polyline paths (lines + true arcs => tangent-continuous)
# ---------------------------------------------------------------------------
def fillet_path(points, radii):
    """Wire through `points` with each interior corner i replaced by an arc of radii[i-1]."""
    edges = []
    prev = points[0]
    for i in range(1, len(points) - 1):
        c = points[i]
        d_in = _unit(_sub(c, points[i - 1]))
        d_out = _unit(_sub(points[i + 1], c))
        cosang = max(-1.0, min(1.0, _dot(d_in, d_out)))
        th = math.acos(cosang)
        if th < 1e-4:
            continue
        R = radii[i - 1]
        tl = R * math.tan(th / 2.0)
        a = _add(c, d_in, -tl)
        b = _add(c, d_out, tl)
        u = _unit(_sub(d_out, d_in))
        mid = _add(c, u, R / math.cos(th / 2.0) - R)
        if _len(_sub(a, prev)) > 1e-6:
            edges.append(bd.Edge.make_line(bd.Vector(*prev), bd.Vector(*a)))
        edges.append(bd.Edge.make_three_point_arc(bd.Vector(*a), bd.Vector(*mid), bd.Vector(*b)))
        prev = b
    edges.append(bd.Edge.make_line(bd.Vector(*prev), bd.Vector(*points[-1])))
    return bd.Wire(edges)


def check_path(points, radii):
    """Tangent lengths must fit their legs; returns the worst leg slack (mm)."""
    tls = [0.0]
    for i in range(1, len(points) - 1):
        d_in = _unit(_sub(points[i], points[i - 1]))
        d_out = _unit(_sub(points[i + 1], points[i]))
        th = math.acos(max(-1.0, min(1.0, _dot(d_in, d_out))))
        tls.append(radii[i - 1] * math.tan(th / 2.0))
    tls.append(0.0)
    worst = 1e9
    for i in range(len(points) - 1):
        L = _len(_sub(points[i + 1], points[i]))
        worst = min(worst, L - tls[i] - tls[i + 1])
    return worst


def tube_along(wire, r):
    e0 = wire.edges()[0]
    p0, t0 = e0.position_at(0.0), e0.tangent_at(0.0)
    prof = bd.Plane(origin=p0, z_dir=t0) * bd.Circle(r)
    return _one(bd.sweep(prof, path=wire, is_frenet=False, transition=bd.Transition.ROUND))


# ---------------------------------------------------------------------------
# Harness ring + ferrule nuts
# ---------------------------------------------------------------------------
def _feed_stub_axis(side):
    """(start, dir) of the feed stub for side 'L' (in-plane +FEED_ANGLE) or 'R' (mirror)."""
    b = FEED_ANGLE if side == "L" else -FEED_ANGLE
    m = _m(b)
    d = _unit((m[0] * math.cos(math.radians(45)), math.sin(math.radians(45)), m[2] * math.cos(math.radians(45))))
    return _ring_centre(b), d


FEED_STUB = (5.6, 12.0)          # (radius, end distance) of the feed stub
FEED_NUT = (14.0, (9.5, 16.5))   # (af, span)


def ring():
    face = bd.Plane.XY * bd.Pos(R_RING, Y_RING) * bd.Circle(RT)
    torus = bd.revolve(face, axis=bd.Axis.Y)
    stubs = []
    for j in range(18):
        b = 20.0 * j
        c = _ring_centre(b)
        stubs.append(geo.cyl_along(c, _add(c, _outlet_dir(b), STUB_END), 2 * STUB_R))
    for side in ("L", "R"):
        c, d = _feed_stub_axis(side)
        stubs.append(geo.cyl_along(c, _add(c, d, FEED_STUB[1]), 2 * FEED_STUB[0]))
    return _one(torus.fuse(*stubs).clean())


def ferrule_nut_proto():
    """Ferrule nut on the cylinder-1 FRONT outlet (in-plane 0)."""
    z0, z1 = NUT_D
    nut = _hex(NUT_AF, z0, z1) - bd.Pos(0, 0, z0 - 1) * bd.Cylinder(
        STUB_R + 0.05, z1 - z0 + 2, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    c = _ring_centre(0.0)
    d = _outlet_dir(0.0)
    return _frame(c, d, (1.0, 0.0, 0.0)).location * nut


def feed_nut(side):
    af, (z0, z1) = FEED_NUT
    nut = _hex(af, z0, z1) - bd.Pos(0, 0, z0 - 1) * bd.Cylinder(
        FEED_STUB[0] + 0.05, z1 - z0 + 2, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    c, d = _feed_stub_axis(side)
    t = _cross((0.0, 1.0, 0.0), d)
    return _frame(c, d, t).location * nut


# ---------------------------------------------------------------------------
# Plug elbow (plug-local frame: origin seat face, +Z plug axis, +X exit direction)
# ---------------------------------------------------------------------------
def elbow_local():
    c0, c1 = ELBOW_CAP
    cap = _rev([(8.05, c0), (9.4, c0), (9.4, c1), (0.0, c1), (0.0, 54.3), (8.05, 54.3)])
    Rb, z = ELBOW_BEND_R, ELBOW_TURN_Z
    path = fillet_path([(0, 0, z - 3.0), (0, 0, z + Rb), (Rb + ELBOW_LEG, 0, z + Rb)], [Rb])
    bend = tube_along(path, ELBOW_TUBE_R)
    xe = Rb + ELBOW_LEG
    spig = bd.Pos(xe - 0.5, 0, z + Rb) * bd.Rot(0, 90, 0) * bd.Cylinder(
        5.2, ELBOW_SPIGOT + 0.5, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    collar = bd.Pos(xe - 3.0, 0, z + Rb) * bd.Rot(0, 90, 0) * bd.Cylinder(
        7.8, 2.2, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    return _one(cap.fuse(bend, spig, collar).clean())


def elbow_nut_local():
    """Coupling nut on the plug's shielding barrel (plug r 7.9 over z 37..53.2)."""
    return _hex(19.0, 36.6, 47.0, chamfer=1.0) - bd.Pos(0, 0, 35.0) * bd.Cylinder(
        8.3, 14.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))


def lead_nut_local():
    """Ferrule nut on the elbow spigot, axis +X."""
    xe = ELBOW_BEND_R + ELBOW_LEG
    nut = _hex(13.0, 0.0, 8.0) - bd.Pos(0, 0, -1) * bd.Cylinder(
        5.25, 10.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    return bd.Pos(xe + 0.3, 0, ELBOW_TURN_Z + ELBOW_BEND_R) * bd.Rot(0, 90, 0) * nut


def elbow_exit_local():
    """(point, dir) where the lead starts, plug-local."""
    return (ELBOW_BEND_R + ELBOW_LEG + ELBOW_SPIGOT, 0.0, ELBOW_TURN_Z + ELBOW_BEND_R), (1.0, 0.0, 0.0)


def plug_frame(k):
    return _frame(PLUG_FACE[k], PLUG_AXIS[k], ELBOW_EXIT[k])


def elbow_exit(k):
    p, _ = elbow_exit_local()
    pl = plug_frame(k)
    q = pl.from_local_coords(bd.Vector(*p))
    return (q.X, q.Y, q.Z), ELBOW_EXIT[k]


# ---------------------------------------------------------------------------
# Lead paths (cylinder 1)
# ---------------------------------------------------------------------------
def _ray_intersect_2d(p, d, q, e):
    """Intersect p + a d with q + s e (vectors in the same plane; 3D tuples). Returns (a, s)."""
    # least squares on the 3D system a d - s e = q - p
    w = _sub(q, p)
    dd, ee, de = _dot(d, d), _dot(e, e), _dot(d, e)
    wd, we = _dot(w, d), _dot(w, e)
    det = dd * ee - de * de
    a = (wd * ee - we * de) / det
    s = (wd * de - we * dd) / det
    return a, s


def front_path():
    c = _ring_centre(0.0)
    d = _outlet_dir(0.0)
    s1 = _add(c, d, STUB_END + 0.05)
    e, D = elbow_exit("F")
    a, s = _ray_intersect_2d(s1, d, e, D)
    k = _add(s1, d, a)
    th = math.acos(max(-1.0, min(1.0, _dot(d, (-D[0], -D[1], -D[2])))))
    R = min(45.0, 0.9 * min(s, a) / math.tan(th / 2.0))
    return [s1, k, e], [R]


def rear_path():
    """Ring outlet (mid-plane +20) -> straight spoke -> gallery along the mid-plane at GALLERY_R
    -> behind the cylinder at y Y_BACK -> across under the exhaust stack -> up into the elbow.

    Every point stays out of the upward sweep of its own and its neighbour's cylinder (the
    exploded view slides each cylinder straight out along its bore): the spoke and the
    gallery's front corner lie in front of / below the head, the gallery lies on the
    mid-plane beyond the barrel fins (|t| 126) and below the heads' side fins, and the
    rear run lies behind the plug, the exhaust studs and the head (y >= 148)."""
    b = 20.0
    c = _ring_centre(b)
    d = _outlet_dir(b)
    s1 = _add(c, d, STUB_END + 0.05)
    rr = R_RING + (STUB_END + 0.05) * math.cos(TAU)          # radius of s1
    a = (GALLERY_R - rr) / math.cos(TAU)
    k1 = _add(s1, d, a)                                       # spoke meets the gallery radius
    k2 = _pt(b, GALLERY_R, Y_BACK)                            # gallery rear corner
    h_g = k2[2]
    k3 = (0.0, Y_BACK, h_g)                                   # under the plug, behind the head
    e, D = elbow_exit("R")
    s = (Y_BACK - e[1]) / D[1]
    k4 = _add(e, D, s)                                        # the elbow's exit ray meets the riser
    return [s1, k1, k2, k3, k4, e], [RB_SPOKE, RB_GALLERY, RB_UNDER, RB_RISE]


def feed_path_L():
    c, d = _feed_stub_axis("L")
    s1 = _add(c, d, FEED_STUB[1] + 0.05)
    # rise along the stub axis to the feed lane radius, run round the ring to the gap, then rearward
    rr = math.hypot(s1[0], s1[2])
    a = (FEED_LANE_R - rr) / math.hypot(d[0], d[2])
    k1 = _add(s1, d, a)
    k2 = _pt(FEED_GAP, FEED_LANE_R, k1[1])
    k3a = _pt(FEED_GAP, FEED_LANE_R, -45.0)
    k3b = _pt(FEED_GAP, FEED_LANE_R + 10.0, -5.0)   # lift over the pad-to-pad crease at the split line
    k3 = _pt(FEED_GAP, FEED_LANE_R + 10.0, 250.0)
    ring_pts = [_pt(b, 250.0, 300.0) for b in (FEED_GAP, 90.0, 80.0, 70.0, 60.0)]
    tx, ty, tz = TERMINAL
    k6 = (tx, 336.0, tz)
    end = (tx, 352.0, tz)
    pts = [s1, k1, k2, k3a, k3b, k3] + ring_pts + [k6, end]
    radii = [8.0, 12.0, 60.0, 60.0, 40.0, 30.0, 150.0, 150.0, 150.0, 40.0, 25.0]
    return pts, radii


def terminal_L():
    tx, ty, tz = TERMINAL
    body = _rev([(0.0, 352.0), (9.0, 352.0), (9.0, 356.0), (15.0, 358.0), (15.0, 364.0),
                 (21.0, 364.0), (21.0, 370.0), (0.0, 370.0)])
    return geo.plane((tx, 0.0, tz), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0)).location * body


# ---------------------------------------------------------------------------
# Ring clamp bracket (cylinder-1 +20 mid-plane)
# ---------------------------------------------------------------------------
def _gap_frame(b=20.0):
    """Plane at the through-bolt axis point (r TB_R, y 0): +Z = +Y, +X = radial."""
    m = _m(b)
    return geo.plane(_pt(b, TB_R, 0.0), (0.0, 1.0, 0.0), m)


def bracket():
    """Saddle round the ring + arm + hex socket cap over the through-bolt head."""
    b = 20.0
    pl = _gap_frame(b)
    # gap frame: local z = engine y, local x = radial offset from r TB_R, local y = tangential
    z0, z1, zc = CUP["y0"], CUP["y1"], CUP["cap"]
    cup = bd.Pos(0, 0, zc) * bd.Cylinder(CUP["ro"], z0 - zc, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    cup = cup - _hex(CUP["af"], z1, z0 + 1.0, chamfer=0.01)
    a0 = Y_RING + RT + 0.5
    arm = bd.Pos(4.0, 0, (a0 + -83.0) / 2.0) * bd.Box(3.0, 9.0, -83.0 - a0)
    body = pl.location * _one(cup.fuse(arm).clean())
    # saddle: annulus section round the ring tube (rear, inner, front), revolved over +-4.5 mm
    half = math.degrees(4.5 / R_RING)
    pts = []
    n = 24
    f0, f1 = 65.0, 283.0     # stops clear of the tilted outlet stub (phi -18 +- 50)
    for i in range(n + 1):
        f = math.radians(f0 + (f1 - f0) * i / n)
        pts.append((R_RING + (RT + 1.5) * math.cos(f), Y_RING + (RT + 1.5) * math.sin(f)))
    for i in range(n, -1, -1):
        f = math.radians(f0 + (f1 - f0) * i / n)
        pts.append((R_RING + (RT + 0.05) * math.cos(f), Y_RING + (RT + 0.05) * math.sin(f)))
    face = bd.Plane.XY * bd.make_face(bd.Polyline(*pts, close=True).edges())
    sad = bd.revolve(face, axis=bd.Axis.Y, revolution_arc=2 * half)
    # revolving +X about +Y sweeps in-plane angles -90 .. -90-2*half; re-centre on b
    sad = geo.axis_rotation(S.ROT_AXIS, b + 90.0 + half) * sad
    return _one(body.fuse(sad).clean())


# ---------------------------------------------------------------------------
_PROTO = None


def prototypes():
    global _PROTO
    if _PROTO is not None:
        return _PROTO
    out = {}
    out["ring"] = ring()
    nf = ferrule_nut_proto()
    out["nut_F"] = nf
    out["nut_R"] = geo.axis_rotation(S.ROT_AXIS, 20.0) * nf
    pts, radii = front_path()
    out["lead_F"] = tube_along(fillet_path(pts, radii), LEAD_R)
    pts, radii = rear_path()
    out["lead_R"] = tube_along(fillet_path(pts, radii), LEAD_R)
    el, en, ln = elbow_local(), elbow_nut_local(), lead_nut_local()
    for k in ("F", "R"):
        loc = plug_frame(k).location
        out[f"elbow_{k}"] = loc * el
        out[f"elbow_nut_{k}"] = loc * en
        out[f"elbow_lead_nut_{k}"] = loc * ln
    out["bracket"] = bracket()
    pts, radii = feed_path_L()
    out["feed_L"] = tube_along(fillet_path(pts, radii), FEED_R)
    out["terminal_L"] = terminal_L()
    _PROTO = out
    return out


def _mirror_x(shape):
    return bd.mirror(shape, about=bd.Plane.YZ)


def build():
    pr = prototypes()
    parts = [P.style(pr["ring"], "ignition:ring", P.POLISHED_ALU)]
    half_rear = bd.Box(3000.0, 3000.0, 3000.0, align=(bd.Align.CENTER, bd.Align.MIN, bd.Align.CENTER))
    n_br = 0
    for k in range(1, S.N_CYL + 1):
        on = lambda s: geo.on_cylinder(s, k)  # noqa: E731
        parts.append(P.style(on(pr["nut_F"]), f"ignition:ring_nut_{k}F", P.FASTENER))
        parts.append(P.style(on(pr["nut_R"]), f"ignition:ring_nut_{k}R", P.FASTENER))
        parts.append(P.style(on(pr["lead_F"]), f"ignition:lead_{k}F", P.BRAID))
        for v in ("F", "R"):
            e_pt, _ = elbow_exit(v)
            if k == geo.SECTION_CYL and geo.in_section(e_pt):
                continue
            parts.append(P.style(on(pr[f"elbow_{v}"]), f"ignition:elbow_{k}{v}", P.STEEL_POLISHED))
            parts.append(P.style(on(pr[f"elbow_nut_{v}"]), f"ignition:elbow_nut_{k}{v}", P.STEEL_POLISHED))
            parts.append(P.style(on(pr[f"elbow_lead_nut_{v}"]), f"ignition:elbow_lead_nut_{k}{v}", P.FASTENER))
        if k == geo.SECTION_CYL:
            # museum section: cut on the cylinder-row plane y = 0 (the lead runs ON the
            # section's +-20 deg boundary, so the sector cutter would split it lengthwise)
            lead_r = _one(pr["lead_R"] - half_rear)
            skin = pr["lead_R"] & bd.Box(3000.0, geo.SKIN_T, 3000.0,
                                         align=(bd.Align.CENTER, bd.Align.MIN, bd.Align.CENTER))
            parts.append(P.style(_one(skin), f"ignition:section_skin_lead_{k}R", P.SECTION_RED))
        else:
            lead_r = on(pr["lead_R"])
        parts.append(P.style(lead_r, f"ignition:lead_{k}R", P.BRAID))
        if k in BRACKET_GAPS:
            n_br += 1
            parts.append(P.style(on(pr["bracket"]), f"ignition:ring_clamp_{n_br}", P.FASTENER))
    parts.append(P.style(pr["feed_L"], "ignition:feed_L", P.BRAID))
    parts.append(P.style(_mirror_x(pr["feed_L"]), "ignition:feed_R", P.BRAID))
    parts.append(P.style(feed_nut("L"), "ignition:feed_nut_L", P.FASTENER))
    parts.append(P.style(feed_nut("R"), "ignition:feed_nut_R", P.FASTENER))
    parts.append(P.style(pr["terminal_L"], "ignition:feed_terminal_L", P.STEEL_POLISHED))
    parts.append(P.style(_mirror_x(pr["terminal_L"]), "ignition:feed_terminal_R", P.STEEL_POLISHED))
    return parts
