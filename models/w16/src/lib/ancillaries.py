"""Front ancillaries, coolant manifolds, mounts and the bell-housing face.

Everything that hangs off the engine and is not induction, exhaust or oil:

  * the serpentine accessory drive — two water pumps, an alternator, an idler,
    a spring-loaded swinging tensioner and the 6-rib belt that ties them to
    the crank damper,
  * a thermostat housing per bank, seated directly on the head's own
    front-face coolant boss (`heads.COOLANT_MH`), and the hose down to that
    bank's pump — NO coolant rail (see COOLANT below),
  * the dipstick, the two engine-mount ears, the lifting eyes,
  * the transaxle adapter flange at BELL_FACE_X with its starter.

BELT PLANE.  The damper (lib/bottom_end) carries six V-grooves on a 4.5 mm
pitch between x = 344 and 368.5, so the belt runs in the plane x = 356.25 —
the centre of that groove band — and is 25 mm wide, not `spec.BELT_X` = 372 /
21 mm wide, which would hang the belt half off the damper's front face.  Every
pulley here repeats the damper's groove pitch exactly, so the belt's six ribs
sit in six real grooves on every wheel.

BELT PATH.  `_solve_loop()` is the general belt/chain tangent solver: an
ordered list of (centre, radius, wrap sign) becomes the closed run of straight
tangents and wrap arcs.  `validate_loop()` then PROVES the route is a belt a
real engine could run: every wrap turns the way its sign says, no two straight
runs cross, and no run passes inside a pulley it does not touch.  `build_belt`
asserts it, so a station edit that made the belt cross itself (an earlier
layout wrapped the damper on two arcs and the bottom run sawed through the
water-pump pulley) can no longer reach a solid.  The belt is the band between
two constant offsets of that path (rib face and back face) plus six ribs, so
its thickness is constant by construction and the ribs bottom 0.3 mm clear of
every groove root.

COOLANT.  A layout-arbitration deletion: an earlier design ran a cast log the
length of each head at its raised port-pad landing, and that log — plus the
turbo housings outboard of it — left no corridor for the exhaust primaries to
climb the head's outer face (see `exhaust.py`'s frame notes). There is no
coolant rail. Each bank keeps only the thermostat housing, seated flush on
the head's own front-face Ø30 coolant boss (`heads.COOLANT_MH[0]`, at
m = -104, h = 340), with a 3-bolt cap, and a Ø44 hose down to that bank's
water-pump inlet. Nothing else is outboard of the heads between bank h 240
and 430.

SECTION.  The front accessory drive is bank-agnostic hardware standing clear
in front of the block, so — like the cam drive — it is not cut.  The bank-1
thermostat/hose sit on the sectioned head's coolant boss and are dropped by
`geo.in_section_void`, and the bank-1 front lifting eye is dropped the same
way.
"""

from __future__ import annotations

import math

from cadgen import build123d as bd

from lib import block as B, fasteners as F, geo, heads as H, oil_system as O, palette as P, spec as S
from lib.castings import fuse_all, is_sound, safe_fillet, soften

# ---------------------------------------------------------------------------
# Belt plane and groove geometry (mirrors the damper in lib/bottom_end)
# ---------------------------------------------------------------------------

BELT_X = 356.25                      # belt centre plane
BELT_W = 25.0                        # belt width along X
BELT_T = 4.5                         # belt thickness
BELT_CLEAR = 0.3                     # rib tip -> groove root
RIB_X = [345.0 + 4.5 * k for k in range(6)]     # damper groove centres
RIB_W = 1.8
RIB_H = 2.7                          # rib height below the belt's inner face
GROOVE_W = 2.0
GROOVE_D = 3.0                       # groove depth in a pulley rim
PULLEY_X = (BELT_X - 14.0, BELT_X + 14.0)       # 342.25 .. 370.25

DAMPER_R = 91.0                      # damper rim radius (bottom_end)

# Pulley stations, (y, z) in the belt plane, and rim radius.
# The alternator sits 16 mm further outboard than spec.ALTERNATOR: at
# y = 262 its Ø62 pulley overlaps the Ø110 water-pump pulley by 8 mm.
WP_YZ = {1: (190.0, 0.0), 2: (-190.0, 0.0)}
WP_R = S.WATER_PUMP[1]["pulley_d"] / 2.0                 # 55
ALT_YZ = (278.0, -30.0)
ALT_R = S.ALTERNATOR["pulley_d"] / 2.0                   # 31
IDLER_YZ = (-270.0, -100.0)
IDLER_R = 35.0
TENS_YZ = (170.0, -130.0)
TENS_R = 35.0

# Travel order of the loop (CCW seen from +X), one entry per wheel: a ribbed
# belt cannot cross itself, so the damper is wrapped ONCE (its top arc) and
# everything else is routed below it.  `validate_loop` proves that before the
# solid is built.  Sign -1 would be a back-side wrap; none is used, because a
# back-side bite on the bottom run pushes the belt into the damper and one on
# the alternator->wp1 run pushes it into the water-pump pulley.
BELT_ORDER = [
    ("damper", (0.0, 0.0), DAMPER_R, 1),
    ("wp2", WP_YZ[2], WP_R, 1),
    ("idler", IDLER_YZ, IDLER_R, 1),
    ("tensioner", TENS_YZ, TENS_R, 1),
    ("alternator", ALT_YZ, ALT_R, 1),
    ("wp1", WP_YZ[1], WP_R, 1),
]

# Water pump: flange pad centre on the block front face (|y|, z).  Kept below
# z = -10 so bank 1's pattern lands on block that the museum section leaves.
WP_PAD = (148.0, -40.0)
WP_BOLT_R = 24.0
BLOCK_F = S.BLOCK_FRONT_X            # 306

MOUNT_YZ = 250.0                     # engine-mount bore |y|
BELL_X = (S.BELL_FACE_X, S.BLOCK_REAR_X)         # -345 .. -318
BELL_R = S.BELL_HOUSING_D / 2.0                  # 215
BELL_BORE_R = 165.0                              # 5 mm clear of the flywheel
BELL_PCD = 200.0
STARTER_YZ = (-160.0, -78.0)         # r = 178: pinion 3 mm clear of the ring gear


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _sgn(bank: int) -> float:
    return 1.0 if bank == 1 else -1.0


def _out_dir(bank: int):
    """Unit vector pointing OUT of a bank (away from the engine centre)."""
    m = S.bank_m(bank)
    return (0.0, -m[1], -m[2])


def _edge_r(e):
    try:
        return e.radius
    except Exception:
        return None


def _face(points):
    """Closed face from a (y, z) point list, for use with geo.yz_plane."""
    return bd.make_face(bd.Polyline(*[(y, z) for y, z in points], close=True).edges())


def _plate(points, x0: float, x1: float):
    """Prism between two X stations from a (y, z) outline (CCW or CW)."""
    pts = list(points)
    area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
               for i in range(len(pts)))
    if area < 0:
        pts = list(reversed(pts))
    return geo.prism_yz(pts, x0, x1)


def _tube_path(points, d: float, bend: float = 26.0):
    """Round tube of diameter d swept along a filleted polyline of 3D points.
    Returns (solid, path); the path is what a hose clip is placed FROM, so the
    clip bore is concentric with the tube instead of merely near it."""
    for r in (bend, bend * 0.6, bend * 0.35, 0.0):
        try:
            path = bd.Polyline(*points) if r <= 0 else bd.FilletPolyline(*points, radius=r)
            tangent = path.edges()[0] % 0.0
            section = bd.Plane(origin=points[0], z_dir=tangent) * bd.Circle(d / 2.0)
            solid = bd.sweep(section, path)
        except Exception:
            continue
        if is_sound(solid):
            return solid, path
    raise RuntimeError("tube sweep failed")


def _tube(points, d: float, bend: float = 26.0):
    return _tube_path(points, d, bend)[0]


# --- mid-scale cast detail --------------------------------------------------
# Ribs, gussets and bolt bosses on the accessory brackets, plus a repeated
# hose-clip family on the front face.  Every one is fused into its bracket
# BEFORE `soften()` so it gets the same root fillets as the rest of the
# casting; separate solids would need to overlap to look attached, and an
# overlap is a clash.

BOSS_PROUD = 3.4                     # bolt-boss height above a bracket face
BOSS_D = (20.0, 17.0)                # base / crown diameter


def _bolt_boss(y: float, z: float, x0: float, proud: float = BOSS_PROUD):
    """A drafted cast boss standing `proud` off a bracket face at station x0."""
    return geo.locate(bd.Cone(BOSS_D[0] / 2.0, BOSS_D[1] / 2.0, proud,
                              align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)),
                      (x0, y, z), (1, 0, 0))


def _rib(points, x0: float, x1: float):
    """A cast rib standing off a bracket's front face: the same (y, z) prism
    the brackets are built from, just narrow and further forward in X."""
    return _plate(points, x0, x1)


def _ring(centre, axis_pt, d_out: float, d_in: float):
    """Short ring (hose clamp / bead) around a tube: centre and a second point
    giving the axis."""
    v = tuple(axis_pt[i] - centre[i] for i in range(3))
    n = math.sqrt(sum(c * c for c in v))
    u = tuple(c / n for c in v)
    p0 = tuple(centre[i] - u[i] * 3.0 for i in range(3))
    p1 = tuple(centre[i] + u[i] * 3.0 for i in range(3))
    return geo.cyl_along(p0, p1, d_out) - geo.cyl_along(
        tuple(centre[i] - u[i] * 5.0 for i in range(3)),
        tuple(centre[i] + u[i] * 5.0 for i in range(3)), d_in)


# ---------------------------------------------------------------------------
# Pulleys
# ---------------------------------------------------------------------------

def _pulley_solid(r_out: float, r_in: float, grooved: bool = True,
                  web: bool = False, x_span=PULLEY_X):
    """A serpentine pulley as ONE revolve: hub, optional thin web, and a rim
    carrying the damper's six V-grooves.  Rim edges are chamfered in the
    section, so no 3D chamfer ladder runs on a grooved cylinder."""
    x0, x1 = x_span
    r_rim = r_out - 12.0
    r_hub = r_in + 8.0
    pts = [(x0, r_in), (x1, r_in)]
    if web and r_rim > r_hub + 6.0:
        xw0, xw1 = BELT_X - 4.5, BELT_X + 4.5
        pts += [(x1, r_hub), (xw1, r_hub), (xw1, r_rim), (x1, r_rim)]
    pts += [(x1, r_out - 1.4), (x1 - 1.4, r_out)]
    if grooved:
        for gx in reversed(RIB_X):
            pts += [(gx + GROOVE_W / 2, r_out), (gx, r_out - GROOVE_D),
                    (gx - GROOVE_W / 2, r_out)]
    pts += [(x0 + 1.4, r_out), (x0, r_out - 1.4)]
    if web and r_rim > r_hub + 6.0:
        pts += [(x0, r_rim), (xw0, r_rim), (xw0, r_hub), (x0, r_hub)]
    profile = bd.make_face(bd.Polyline(*pts, close=True).edges())
    return bd.revolve(bd.Plane.XZ * profile, bd.Axis.X)


def pulley(name: str, yz, r_out: float, r_in: float, grooved=True, web=False,
           lightening=0, colour=P.MACHINED_STEEL):
    solid = _pulley_solid(r_out, r_in, grooved=grooved, web=web)
    if lightening:
        holes = []
        r_hole = (r_out - 12.0 + r_in + 8.0) / 2.0
        d_hole = min(18.0, (r_out - 12.0 - r_in - 8.0) - 4.0)
        for k in range(lightening):
            a = math.radians(360.0 * k / lightening + 15.0)
            holes.append(geo.cyl_x(PULLEY_X[0] - 4, PULLEY_X[1] + 4, d_hole,
                                   r_hole * math.cos(a), r_hole * math.sin(a)))
        solid = solid - holes
    solid = solid.moved(bd.Location((0.0, yz[0], yz[1])))
    return P.style(solid, f"pulley:{name}", colour)


# ---------------------------------------------------------------------------
# Belt: tangent solver + band
# ---------------------------------------------------------------------------

def _solve_loop(wheels):
    """wheels: [(name, (y, z), radius, sign)] in travel order.  Returns
    [(kind, ...)] segments: ('line', p0, p1) and ('arc', c, r, a0, a1, sign)
    with angles in degrees.  sign +1 wraps counter-clockwise (belt outside),
    -1 wraps clockwise (belt's back face on the wheel)."""
    n = len(wheels)
    tangents = []
    for i in range(n):
        (_, ca, ra, sa) = wheels[i]
        (_, cb, rb, sb) = wheels[(i + 1) % n]
        dy, dz = cb[0] - ca[0], cb[1] - ca[1]
        d = math.hypot(dy, dz)
        k = sb * rb - sa * ra
        if d <= abs(k) + 1e-9:
            raise ValueError(f"belt: no tangent between {wheels[i][0]} and {wheels[(i+1)%n][0]}")
        psi = math.atan2(dz, dy) - math.asin(k / d)
        t = (math.cos(psi), math.sin(psi))
        left = (-t[1], t[0])
        p0 = (ca[0] - sa * ra * left[0], ca[1] - sa * ra * left[1])
        p1 = (cb[0] - sb * rb * left[0], cb[1] - sb * rb * left[1])
        tangents.append((p0, p1))
    segs = []
    for i in range(n):
        name, c, r, s = wheels[i]
        arrive, leave = tangents[i - 1][1], tangents[i][0]
        a0 = math.degrees(math.atan2(arrive[1] - c[1], arrive[0] - c[0]))
        a1 = math.degrees(math.atan2(leave[1] - c[1], leave[0] - c[0]))
        sweep = (a1 - a0) % 360.0 if s > 0 else -((a0 - a1) % 360.0)
        segs.append(("arc", name, c, r, a0, sweep))
        segs.append(("line", name, tangents[i][0], tangents[i][1]))
    return segs


def _seg_hit(a0, a1, b0, b1) -> bool:
    """True when two open segments properly cross (shared endpoints ignored)."""
    def cross(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])

    if (math.dist(a0, b0) < 1e-6 or math.dist(a0, b1) < 1e-6
            or math.dist(a1, b0) < 1e-6 or math.dist(a1, b1) < 1e-6):
        return False
    d1, d2 = cross(a0, a1, b0), cross(a0, a1, b1)
    d3, d4 = cross(b0, b1, a0), cross(b0, b1, a1)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def _seg_circle_gap(p0, p1, c, r) -> float:
    """Clearance from a segment to a circle (negative = the segment cuts in)."""
    vx, vy = p1[0] - p0[0], p1[1] - p0[1]
    L2 = vx * vx + vy * vy
    t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((c[0] - p0[0]) * vx + (c[1] - p0[1]) * vy) / L2))
    q = (p0[0] + t * vx, p0[1] + t * vy)
    return math.dist(q, c) - r


def validate_loop(wheels, margin: float = 4.0):
    """A ribbed belt cannot cross itself or saw through a pulley.  Returns
    (ok, reason, worst clearance): every wrap must turn the way its sign says,
    no two straight runs may properly intersect, and no run may pass inside a
    pulley it does not touch."""
    segs = _solve_loop(wheels)
    arcs = [s for s in segs if s[0] == "arc"]
    lines = [s for s in segs if s[0] == "line"]
    for _, name, _c, _r, _a0, sweep in arcs:
        sign = dict((n, s) for n, _c2, _r2, s in wheels)[name]
        if sweep == 0.0 or (sweep > 0) != (sign > 0) or abs(sweep) > 300.0:
            return False, f"wrap on {name} is {sweep:.1f} deg (sign {sign})", 0.0
    for i in range(len(lines)):
        for j in range(i + 1, len(lines)):
            if _seg_hit(lines[i][2], lines[i][3], lines[j][2], lines[j][3]):
                return False, f"belt crosses itself: run after {lines[i][1]} x run after {lines[j][1]}", 0.0
    worst = 1e9
    for k, (_, name, p0, p1) in enumerate(lines):
        touching = {name, lines[k][1], wheels[(k + 1) % len(wheels)][0]}
        for n, c, r, _s in wheels:
            if n in touching:
                continue
            gap = _seg_circle_gap(p0, p1, c, r)
            worst = min(worst, gap)
            if gap < margin:
                return False, f"run after {name} passes {gap:.1f} mm from {n}", gap
    return True, "ok", worst


def _loop_radii(kind: str):
    """Wheel radii for one of the belt's three surfaces."""
    out = []
    for name, c, r, s in BELT_ORDER:
        base = r + BELT_CLEAR
        if s > 0:
            off = {"rib": 0.0, "back": BELT_T, "tip": -RIB_H}[kind]
        else:
            off = {"rib": BELT_T, "back": 0.0, "tip": BELT_T + RIB_H}[kind]
        out.append((name, c, base + off, s))
    return out


def _loop_face(kind: str):
    """Closed 2D face bounded by one belt surface (exact lines + arcs)."""
    edges = []
    for seg in _solve_loop(_loop_radii(kind)):
        if seg[0] == "arc":
            _, _, c, r, a0, sweep = seg
            if abs(sweep) > 1e-6:
                edges += bd.CenterArc(c, r, a0, sweep).edges()
        else:
            _, _, p0, p1 = seg
            if math.dist(p0, p1) > 1e-6:
                edges += bd.Line(p0, p1).edges()
    return bd.make_face(edges)


def belt_stations():
    """Reporting helper: [(name, (y, z), rim radius, wrap deg)]."""
    rim = {name: r for name, _c, r, _s in BELT_ORDER}
    out = []
    for seg in _solve_loop(_loop_radii("rib")):
        if seg[0] == "arc":
            out.append((seg[1], seg[2], rim[seg[1]], round(seg[5], 1)))
    return out


def build_belt():
    ok, why, gap = validate_loop(_loop_radii("rib"))
    assert ok, f"belt layout invalid: {why}"
    rib, back, tip = _loop_face("rib"), _loop_face("back"), _loop_face("tip")
    band = back - rib
    ribband = rib - tip
    x0 = BELT_X - BELT_W / 2.0
    body = bd.extrude(geo.yz_plane(x0) * band, amount=BELT_W)
    ribs = [bd.extrude(geo.yz_plane(gx - RIB_W / 2.0) * ribband, amount=RIB_W)
            for gx in RIB_X]
    belt = fuse_all([body] + ribs)
    return P.style(belt, "accessory_belt", P.BELT)


# ---------------------------------------------------------------------------
# Water pumps
# ---------------------------------------------------------------------------

def _wp_bolt_points(bank: int):
    s = _sgn(bank)
    cy, cz = s * WP_PAD[0], WP_PAD[1]
    return [(cy + s * WP_BOLT_R * math.cos(math.radians(30 + 60 * k)),
             cz + WP_BOLT_R * math.sin(math.radians(30 + 60 * k))) for k in range(6)]


def build_water_pump(bank: int):
    s = _sgn(bank)
    ay, az = WP_YZ[bank]
    py, pz = s * WP_PAD[0], WP_PAD[1]
    parts = []

    # cast body: mounting pad on the block face, volute, bearing snout
    pad2d = bd.Pos(py, pz) * bd.Circle(WP_BOLT_R + 11.0)
    pad2d = pad2d + [bd.Pos(ay, az) * bd.Circle(44.0),
                     bd.Pos((py + ay) / 2, (pz + az) / 2) * bd.Rot(0, 0, math.degrees(
                         math.atan2(az - pz, ay - py))) * bd.Rectangle(math.dist((py, pz), (ay, az)), 56.0)]
    pad = bd.extrude(geo.yz_plane(BLOCK_F + 0.6) * pad2d, amount=9.4)
    volute = fuse_all([
        geo.cyl_x(BLOCK_F + 8.0, BLOCK_F + 26.0, 118.0, ay, az),
        geo.cyl_x(BLOCK_F + 24.0, BLOCK_F + 34.0, 96.0, ay, az),
        geo.cyl_x(BLOCK_F + 8.0, BLOCK_F + 12.0, 46.0, ay + s * -28.0, az + 22.0),
    ])
    snout = geo.cyl_x(BLOCK_F + 30.0, PULLEY_X[0] - 1.2, 54.0, ay, az)
    # inlet spigot, outward and down, in a plane clear of the belt
    sx = BLOCK_F + 16.0
    d = (0.0, s * 0.62, -0.78)
    p0 = (sx, ay, az)
    p1 = (sx, ay + d[1] * 78.0, az + d[2] * 78.0)
    spigot = geo.cyl_along(p0, p1, 38.0)
    bead = geo.cyl_along(tuple(p1[i] - d[i] * 9.0 for i in range(3)),
                         tuple(p1[i] - d[i] * 3.0 for i in range(3)), 44.0)
    body = fuse_all([pad, volute, snout, spigot, bead])
    body = body - [geo.cyl_along(p0, tuple(p1[i] + d[i] * 2.0 for i in range(3)), 26.0),
                   geo.cyl_x(BLOCK_F - 6.0, BLOCK_F + 30.0, 26.0, ay, az)]
    body, _ = soften(body, 4.0, min_r=0.8)
    # cast bosses under the 6 flange bolts.  Fused AFTER soften on purpose:
    # the pump body's all-edge fillet pass is already the module's slowest
    # step, and a boss crown wants a crisp seat, not a 4 mm blend.
    body = fuse_all([body] + [_bolt_boss(by, bz, BLOCK_F + 10.0)
                              for by, bz in _wp_bolt_points(bank)])
    # the volute is a plain cylinder about (ay, az); the block's front-face
    # silhouette tapers inward below the crank axis (skirt_point), so the
    # volute's lower-inboard arc plows into real block material there —
    # measured against block.build_block() as ~700 mm^3 before this cut.
    body = _clip_to_block(body, bank)
    parts.append(P.style(body, f"water_pump_housing:{bank}", P.CAST))

    # machined flange skin on the block face
    skin = bd.extrude(geo.yz_plane(BLOCK_F) * pad2d, amount=0.6)
    skin = _clip_to_block(skin, bank)
    parts.append(P.style(skin, f"water_pump_flange:{bank}", P.MACHINED))

    # 6-bolt ring
    bolt = F.hex_flange_bolt(8.0, 24.0)
    for k, (by, bz) in enumerate(_wp_bolt_points(bank)):
        parts.append(P.style(geo.locate(bolt, (BLOCK_F + 10.0 + BOSS_PROUD, by, bz), (1, 0, 0)),
                             f"water_pump_bolt:{bank}_{k + 1}", P.TITANIUM))

    # shaft, pulley, nut
    parts.append(P.style(geo.cyl_x(BLOCK_F + 28.0, PULLEY_X[1] + 6.0, 22.0, ay, az),
                         f"water_pump_shaft:{bank}", P.MACHINED_STEEL))
    parts.append(pulley(f"water_pump_{bank}", (ay, az), WP_R, 13.0, web=True, lightening=6))
    parts.append(P.style(geo.locate(F.hex_nut(12.0), (PULLEY_X[1] + 6.0, ay, az), (1, 0, 0)),
                         f"water_pump_nut:{bank}", P.STEEL_DARK))
    return parts


# ---------------------------------------------------------------------------
# Alternator
# ---------------------------------------------------------------------------

ALT_BODY_X = (373.0, 440.0)
ALT_R_BODY = 62.0
ALT_FEET = [(85.0, -88.0), (145.0, -90.0), (105.0, -45.0)]     # M10 into the block face
# the front face each foot bolt lands on: the first two sit on `foot`
# (BLOCK_F + 16), the third only on `footpad` (BLOCK_F + 13).  A boss whose
# base floats off its own plate is the one way this detail can go wrong.
ALT_FOOT_X = [BLOCK_F + 16.0, BLOCK_F + 16.0, BLOCK_F + 13.0]
ALT_PIVOT = (278.0, -102.0)
ALT_POST_Y = 340.0


def build_alternator():
    ay, az = ALT_YZ
    x0, x1 = ALT_BODY_X
    parts = []

    # finned cast housing: one drum, 12 radial fins, machined band at the joint
    drum = geo.cyl_x(x0, x1, 2 * ALT_R_BODY, ay, az)
    fins = []
    fin = bd.Box(28.0, 3.6, 13.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)).moved(
        bd.Location(((x0 + x1) / 2, 0.0, ALT_R_BODY - 5.0)))
    for k in range(12):
        fins.append(fin.rotate(bd.Axis.X, 30.0 * k).moved(bd.Location((0.0, ay, az))))
    housing = fuse_all([drum] + fins)
    housing = housing - geo.cyl_x(x0 - 4, x0 + 3.0, 46.0, ay, az)
    # pivot lug hanging below the drive end
    lug = _plate([(ay - 11, az - 46), (ay + 11, az - 46), (ay + 11, ALT_PIVOT[1] - 14),
                  (ay - 11, ALT_PIVOT[1] - 14)], x0 + 3.0, x0 + 21.0)
    lug = lug - geo.cyl_x(x0 - 2, x0 + 26, 13.0, *ALT_PIVOT)
    # adjuster ear on top, at the rear end
    ear = _plate([(ay - 10, az + 40), (ay + 10, az + 40), (ay + 10, az + 74), (ay - 10, az + 74)],
                 x1 - 24.0, x1 - 8.0)
    ear = ear - geo.cyl_x(x1 - 30, x1 - 2, 11.0, ay, az + 62.0)
    housing = fuse_all([housing, lug, ear])
    housing, _ = soften(housing, 2.0, min_r=0.5)
    parts.append(P.style(housing, "alternator_housing", P.CAST))

    # rear cover + B+ terminal
    cover = geo.cyl_x(x1, x1 + 12.0, 112.0, ay, az)
    boss = geo.cyl_x(x1 + 10.0, x1 + 20.0, 26.0, ay + 26.0, az + 18.0)
    cover = fuse_all([cover, boss])
    cover, _ = soften(cover, 2.0, min_r=0.5)
    parts.append(P.style(cover, "alternator_cover", P.COMPOSITE))
    parts.append(P.style(geo.cyl_x(x1 + 18.0, x1 + 32.0, 10.0, ay + 26.0, az + 18.0),
                         "alternator_terminal:b_plus", P.BRASS))
    parts.append(P.style(geo.locate(F.hex_nut(8.0), (x1 + 28.0, ay + 26.0, az + 18.0), (1, 0, 0)),
                         "alternator_terminal_nut", P.STEEL_DARK))

    # shaft, pulley, nut
    parts.append(P.style(geo.cyl_x(PULLEY_X[0] - 8.0, x0 + 2.0, 20.0, ay, az),
                         "alternator_shaft", P.MACHINED_STEEL))
    parts.append(pulley("alternator", ALT_YZ, ALT_R, 10.0))
    parts.append(P.style(geo.locate(F.hex_nut(10.0), (PULLEY_X[0] - 8.0, ay, az), (-1, 0, 0)),
                         "alternator_nut", P.STEEL_DARK))

    # cast bracket: foot on the block face, arm outboard, leg forward, pivot
    # clevis under the drive end, post carrying the adjuster
    foot = _plate([(66, -30), (160, -100), (160, -112), (66, -100)], BLOCK_F, BLOCK_F + 16.0)
    footpad = _plate([(64, -24), (120, -24), (160, -74), (160, -112), (64, -112)],
                     BLOCK_F, BLOCK_F + 13.0)
    arm = _plate([(110, -66), (ALT_PIVOT[0] + 18, ALT_PIVOT[1] + 12),
                  (ALT_PIVOT[0] + 18, ALT_PIVOT[1] - 20), (110, -104)], BLOCK_F, BLOCK_F + 24.0)
    leg = _plate([(ALT_PIVOT[0] - 17, ALT_PIVOT[1] + 14), (ALT_PIVOT[0] + 17, ALT_PIVOT[1] + 14),
                  (ALT_PIVOT[0] + 17, ALT_PIVOT[1] - 20), (ALT_PIVOT[0] - 17, ALT_PIVOT[1] - 20)],
                 BLOCK_F + 20.0, x0 + 34.0)
    clevis = _plate([(ALT_PIVOT[0] - 17, ALT_PIVOT[1] + 26), (ALT_PIVOT[0] + 17, ALT_PIVOT[1] + 26),
                     (ALT_PIVOT[0] + 17, ALT_PIVOT[1] - 20), (ALT_PIVOT[0] - 17, ALT_PIVOT[1] - 20)],
                    x0 + 22.0, x0 + 34.0)
    post = _plate([(ALT_POST_Y - 15, -96), (ALT_POST_Y + 15, -96),
                   (ALT_POST_Y + 15, az + 66), (ALT_POST_Y - 15, az + 66)], x1 - 22.0, x1 - 8.0)
    postleg = _plate([(ALT_PIVOT[0], ALT_PIVOT[1] + 14), (ALT_POST_Y + 15, -96),
                      (ALT_POST_Y + 15, -112), (ALT_PIVOT[0], ALT_PIVOT[1] - 20)],
                     x1 - 22.0, x1 - 8.0)
    spine = _plate([(ALT_PIVOT[0] - 15, ALT_PIVOT[1] + 8), (ALT_PIVOT[0] + 15, ALT_PIVOT[1] + 8),
                    (ALT_PIVOT[0] + 15, ALT_PIVOT[1] - 18), (ALT_PIVOT[0] - 15, ALT_PIVOT[1] - 18)],
                   x0 + 30.0, x1 - 8.0)
    # cast ribs along the arm's load path (foot -> pivot) and a drafted boss
    # under every foot bolt, fused BEFORE soften so they get root fillets
    ribs = [_rib([(112, -70), (292, -94), (292, -104), (112, -80)], BLOCK_F + 24.0, BLOCK_F + 32.0),
            _rib([(112, -90), (292, -108), (292, -118), (112, -100)], BLOCK_F + 24.0, BLOCK_F + 32.0),
            _rib([(70, -34), (150, -96), (158, -88), (78, -26)], BLOCK_F + 13.0, BLOCK_F + 19.0)]
    bosses = [_bolt_boss(by, bz, bx) for (by, bz), bx in zip(ALT_FEET, ALT_FOOT_X)]
    bracket = fuse_all([foot, footpad, arm, leg, clevis, spine, postleg, post])
    bracket = bracket - [geo.cyl_x(x0 + 18, x0 + 38, 13.0, *ALT_PIVOT),
                         geo.cyl_x(x1 - 26, x1 - 4, 11.0, ALT_POST_Y, az + 62.0)]
    bracket, _ = soften(bracket, 5.0, min_r=1.0)
    # the foot beds on the block front face (bank-1 side, all +y): clear it
    # of the block's real surface the same way as the mount ears.
    bracket = _clip_to_block(bracket, 1)
    # ribs and bolt bosses go on AFTER the all-edge fillet pass and the block
    # clip: fusing them first tripled the narrow-face count `fillet_all` has to
    # dodge (33 -> 72 skipped edges) and the same change on the tensioner
    # SEGFAULTED OCC outright.  Cast root fillets are not worth a hard crash.
    bracket = fuse_all([bracket] + ribs + bosses)
    parts.append(P.style(bracket, "alternator_bracket", P.CAST))

    m10 = F.hex_flange_bolt(10.0, 30.0)
    for k, ((by, bz), bx) in enumerate(zip(ALT_FEET, ALT_FOOT_X)):
        parts.append(P.style(geo.locate(m10, (bx + BOSS_PROUD, by, bz), (1, 0, 0)),
                             f"alternator_bolt:{k + 1}", P.TITANIUM))
    parts.append(P.style(geo.locate(F.hex_flange_bolt(12.0, 46.0), (x0 + 34.0, *ALT_PIVOT), (1, 0, 0)),
                         "alternator_pivot_bolt", P.TITANIUM))

    # slotted tensioning arm from the housing ear out to the post
    slot = _plate([(ay + 2, az + 54), (ALT_POST_Y + 8, az + 54),
                   (ALT_POST_Y + 8, az + 70), (ay + 2, az + 70)], x1 - 8.0, x1 - 1.0)
    slot = slot - [geo.cyl_x(x1 - 12, x1 + 2, 11.0, ay + 8.0, az + 62.0),
                   geo.cyl_x(x1 - 12, x1 + 2, 11.0, ALT_POST_Y, az + 62.0),
                   bd.Box(12.0, ALT_POST_Y - ay - 8.0, 11.0,
                          align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.CENTER)).moved(
                              bd.Location((x1 - 5.0, (ay + 8.0 + ALT_POST_Y) / 2, az + 62.0)))]
    slot, _ = safe_fillet(slot, [e for e in slot.edges() if abs(e.length - 7.0) < 1e-6], 2.0)
    parts.append(P.style(slot, "alternator_adjuster_arm", P.STEEL))
    parts.append(P.style(geo.locate(F.hex_flange_bolt(10.0, 26.0), (x1 - 1.0, ALT_POST_Y, az + 62.0), (1, 0, 0)),
                         "alternator_adjuster_bolt", P.TITANIUM))
    parts.append(P.style(geo.locate(F.hex_flange_bolt(10.0, 26.0), (x1 - 1.0, ay + 8.0, az + 62.0), (1, 0, 0)),
                         "alternator_ear_bolt", P.TITANIUM))
    return parts


# ---------------------------------------------------------------------------
# Idler (off the bank-2 pump housing) and the spring-loaded tensioner
# ---------------------------------------------------------------------------

def build_idler():
    iy, iz = IDLER_YZ
    py, pz = WP_YZ[2]
    parts = []
    arm = _plate([(py - 26, pz - 34), (py - 46, pz + 4), (iy + 16, iz + 22), (iy - 16, iz - 6)],
                 BLOCK_F + 12.0, BLOCK_F + 28.0)
    hubs = fuse_all([geo.cyl_x(BLOCK_F + 12.0, PULLEY_X[0] - 1.0, 44.0, iy, iz),
                     geo.cyl_x(BLOCK_F + 10.0, BLOCK_F + 28.0, 34.0, py - 44.0, pz - 8.0),
                     geo.cyl_x(BLOCK_F + 10.0, BLOCK_F + 28.0, 34.0, py - 24.0, pz - 40.0)])
    bracket = fuse_all([arm, hubs])
    bracket = bracket - [geo.cyl_x(BLOCK_F + 6, BLOCK_F + 32, 10.5, py - 44.0, pz - 8.0),
                         geo.cyl_x(BLOCK_F + 6, BLOCK_F + 32, 10.5, py - 24.0, pz - 40.0)]
    bracket, _ = soften(bracket, 3.0, min_r=1.5)
    parts.append(P.style(bracket, "idler_bracket", P.CAST))
    for k, (by, bz) in enumerate(((py - 44.0, pz - 8.0), (py - 24.0, pz - 40.0))):
        parts.append(P.style(geo.locate(F.hex_flange_bolt(10.0, 28.0), (BLOCK_F + 28.0, by, bz), (1, 0, 0)),
                             f"idler_bracket_bolt:{k + 1}", P.TITANIUM))
    parts.append(P.style(geo.cyl_x(BLOCK_F + 20.0, PULLEY_X[1] + 4.0, 20.0, iy, iz),
                         "idler_axle", P.MACHINED_STEEL))
    parts.append(pulley("idler", IDLER_YZ, IDLER_R, 11.0))
    parts.append(P.style(geo.locate(F.socket_cap_bolt(10.0, 30.0), (PULLEY_X[1] + 4.0, iy, iz), (1, 0, 0)),
                         "idler_bolt", P.TITANIUM))
    return parts


# Pivot: r = 134 from the crank axis, so the spring housing and arm clear the
# damper's Ø182 rim, and everything but the pulley stays behind the belt plane.
TENS_PIVOT = (105.0, -85.0)
TENS_FEET = [(48.0, -36.0), (52.0, -92.0)]


def build_tensioner():
    ty, tz = TENS_YZ
    vy, vz = TENS_PIVOT
    parts = []
    bracket = fuse_all([
        _plate([(38, -24), (86, -24), (128, -70), (128, -108), (38, -108)], BLOCK_F, BLOCK_F + 14.0),
        geo.cyl_x(BLOCK_F, BLOCK_F + 26.0, 50.0, vy, vz),
    ])
    bracket = bracket - geo.cyl_x(BLOCK_F - 4, BLOCK_F + 30, 17.0, vy, vz)
    bracket, _ = soften(bracket, 4.0, min_r=0.8)
    # foot beds on the block front face (bank-1 side, all +y): same clearance
    # cut as the mount ears / alternator bracket.
    bracket = _clip_to_block(bracket, 1)
    # two gussets from the feet into the pivot barrel plus a cast boss under
    # each foot bolt, fused AFTER soften/clip (see the alternator's note)
    bracket = fuse_all([
        bracket,
        _rib([(42, -30), (100, -78), (100, -88), (42, -40)], BLOCK_F + 14.0, BLOCK_F + 21.0),
        _rib([(42, -60), (100, -92), (100, -102), (42, -70)], BLOCK_F + 14.0, BLOCK_F + 21.0),
    ] + [_bolt_boss(by, bz, BLOCK_F + 14.0) for by, bz in TENS_FEET])
    parts.append(P.style(bracket, "tensioner_bracket", P.CAST))
    for k, (by, bz) in enumerate(TENS_FEET):
        parts.append(P.style(geo.locate(F.hex_flange_bolt(10.0, 28.0),
                                        (BLOCK_F + 14.0 + BOSS_PROUD, by, bz), (1, 0, 0)),
                             f"tensioner_bracket_bolt:{k + 1}", P.TITANIUM))
    # spring housing over the pivot
    parts.append(P.style(geo.cyl_x(BLOCK_F + 10.0, BLOCK_F + 26.0, 52.0, vy, vz)
                         - geo.cyl_x(BLOCK_F + 6, BLOCK_F + 30, 17.0, vy, vz),
                         "tensioner_spring_housing", P.STEEL_DARK))
    # swinging arm, behind the belt plane
    arm = fuse_all([
        _plate([(vy - 14, vz + 13), (ty - 12, tz + 15), (ty + 12, tz - 13), (vy + 14, vz - 15)],
               BLOCK_F + 26.0, BLOCK_F + 38.0),
        geo.cyl_x(BLOCK_F + 26.0, BLOCK_F + 38.0, 42.0, vy, vz),
        geo.cyl_x(BLOCK_F + 26.0, PULLEY_X[0] - 1.0, 40.0, ty, tz),
    ])
    arm = arm - [geo.cyl_x(BLOCK_F + 22, BLOCK_F + 42, 17.0, vy, vz),
                 geo.cyl_x(BLOCK_F + 22, PULLEY_X[0] + 2, 17.0, ty, tz)]
    arm, _ = soften(arm, 3.0, min_r=0.8)
    parts.append(P.style(arm, "tensioner_arm", P.MACHINED))
    parts.append(P.style(geo.locate(F.hex_flange_bolt(16.0, 46.0), (BLOCK_F + 38.0, vy, vz), (1, 0, 0)),
                         "tensioner_pivot_bolt", P.TITANIUM))
    parts.append(P.style(geo.cyl_x(BLOCK_F + 26.0, PULLEY_X[1] + 4.0, 16.0, ty, tz),
                         "tensioner_axle", P.MACHINED_STEEL))
    parts.append(pulley("tensioner", TENS_YZ, TENS_R, 9.0))
    parts.append(P.style(geo.locate(F.socket_cap_bolt(10.0, 30.0), (PULLEY_X[1] + 4.0, ty, tz), (1, 0, 0)),
                         "tensioner_bolt", P.TITANIUM))
    return parts


# ---------------------------------------------------------------------------
# Thermostat + hose (NO coolant rail — see module docstring: a per-bank log
# at the head's raised port-pad landing left no corridor for the exhaust
# primaries. Each bank's thermostat mounts directly on the head's own
# front-face Ø30 coolant boss instead.)
# ---------------------------------------------------------------------------

HOSE_CLIP_U = (0.38, 0.58, 0.78)     # clip stations along the coolant hose.
# Not 0.22 for the first one: that far up the run the clip's screw
# housing reached back into the head's own coolant face (13.8 mm^3 into
# head:2, 5.9 into head_face:2_coolant_face_2 in the clearance sweep).


def _bp(bank, x, m, h):
    return S.bank_point(bank, x, m, h)


def build_coolant(bank: int, sectioned: bool = True):
    parts = []
    out = _out_dir(bank)
    boss_m, boss_h = H.COOLANT_MH[0]
    seat = _bp(bank, H.HEAD_FRONT_X, boss_m, boss_h)
    if geo.in_section_void(seat, bank, sectioned):
        return parts               # bank-1: this boss sits on the sectioned head
    ry, rz = seat[1], seat[2]

    # thermostat housing, flush on the head's own boss (proud face at
    # HEAD_FRONT_X + COOLANT_PROUD) + hose to the pump inlet
    hd = (0.0, out[1] * 0.4 - S.bank_up(bank)[1] * 0.92, out[2] * 0.4 - S.bank_up(bank)[2] * 0.92)
    nrm = math.sqrt(hd[1] ** 2 + hd[2] ** 2)
    hd = (0.0, hd[1] / nrm, hd[2] / nrm)
    x0 = H.HEAD_FRONT_X + H.COOLANT_PROUD
    tstat_x = (x0, x0 + 30.0)
    # the neck is a cylinder whose AXIS lies in the Y-Z plane, so — unlike
    # the housing's own X-axis body — its full diameter reaches backward
    # along X from wherever it is rooted.  Rooted near the housing's base
    # (tstat_x[0] + 12, as when this housing hung off the far end of the
    # since-deleted rail) that backward reach bit into the head's front
    # face, now that the housing sits flush on it instead: empirically
    # zero clear of `heads.build()`'s head:2 only from tstat_x[1] - 9 on.
    neck0 = (tstat_x[1] - 9.0, ry, rz)
    neck1 = (neck0[0], ry + hd[1] * 46.0, rz + hd[2] * 46.0)
    housing = fuse_all([
        geo.cyl_x(tstat_x[0], tstat_x[1], 58.0, ry, rz),
        geo.cyl_along(neck0, neck1, 42.0),
    ])
    housing = housing - geo.cyl_x(tstat_x[0] - 4.0, tstat_x[1] - 8.0, 34.0, ry, rz)
    housing, _ = soften(housing, 3.0, min_r=0.8)
    parts.append(P.style(housing, f"thermostat_housing:{bank}", P.CAST))
    cap = geo.cyl_x(tstat_x[1], tstat_x[1] + 9.0, 58.0, ry, rz)
    cap, _ = soften(cap, 2.0, min_r=0.5)
    parts.append(P.style(cap, f"thermostat_cap:{bank}", P.CAST))
    cbolt = F.hex_flange_bolt(8.0, 24.0)
    for k in range(3):
        a = math.radians(90 + 120 * k)
        parts.append(P.style(geo.locate(cbolt, (tstat_x[1] + 9.0, ry + 23.0 * math.cos(a),
                                                rz + 23.0 * math.sin(a)), (1, 0, 0)),
                             f"thermostat_bolt:{bank}_{k + 1}", P.TITANIUM))

    # hose: thermostat neck -> pump inlet spigot tip
    s = _sgn(bank)
    ay, az = WP_YZ[bank]
    sx = BLOCK_F + 16.0
    tip = (sx, ay + s * 0.62 * 74.0, az - 0.78 * 74.0)
    path = [
        (neck1[0], neck1[1] - hd[1] * 15.0, neck1[2] - hd[2] * 15.0),
        (neck1[0] - 2.0, neck1[1] + hd[1] * 40.0, neck1[2] + hd[2] * 40.0),
        (sx - 6.0, (neck1[1] * 0.35 + tip[1] * 0.65), (neck1[2] * 0.3 + tip[2] * 0.7) - 18.0),
        (sx, tip[1] - s * 0.62 * 16.0, tip[2] + 0.78 * 16.0),
    ]
    hose, hpath = _tube_path(path, 44.0, bend=46.0)
    parts.append(P.style(hose, f"coolant_hose:{bank}", P.HOSE))
    # A repeated clip family along the front face: three identical worm-drive
    # clips spaced along the run, each SAMPLED FROM THE SWEPT PATH so its bore
    # is concentric with the tube rather than merely near it.
    for k, u in enumerate(HOSE_CLIP_U):
        c = tuple(hpath @ u)
        t = hpath % u
        tan = (t.X, t.Y, t.Z)
        band = (geo.cyl_along(tuple(c[i] - tan[i] * 5.0 for i in range(3)),
                              tuple(c[i] + tan[i] * 5.0 for i in range(3)), 54.0)
                - geo.cyl_along(tuple(c[i] - tan[i] * 8.0 for i in range(3)),
                                tuple(c[i] + tan[i] * 8.0 for i in range(3)), 44.4))
        # radial direction for the screw housing: tangent x X, so it lies in
        # the Y-Z plane and faces the camera rather than the block
        n = (0.0, tan[2], -tan[1])
        ln = math.sqrt(sum(v * v for v in n)) or 1.0
        n = tuple(v / ln for v in n)
        housing = geo.cyl_along(tuple(c[i] + n[i] * 22.0 for i in range(3)),
                                tuple(c[i] + n[i] * 36.0 for i in range(3)), 13.0)
        clip = fuse_all([band, housing])
        if is_sound(clip):
            parts.append(P.style(clip, f"hose_clip:{bank}_{k + 1}", P.STEEL))
    # +6 mm in x: the clamp ring's own Ø50 reach (bigger than the neck's
    # Ø42) still grazed the head's coolant boss at the neck's own station.
    clamp0 = (neck1[0] + 6.0, neck1[1] - hd[1] * 8.0, neck1[2] - hd[2] * 8.0)
    parts.append(P.style(_ring(clamp0, path[1], 50.0, 43.0), f"hose_clamp:{bank}_1", P.STEEL))
    clamp1 = (sx, tip[1] - s * 0.62 * 24.0, tip[2] + 0.78 * 24.0)
    parts.append(P.style(_ring(clamp1, path[-2], 50.0, 43.0), f"hose_clamp:{bank}_2", P.STEEL))
    return parts


# ---------------------------------------------------------------------------
# Dipstick (bank 2)
# ---------------------------------------------------------------------------

DIP_X = 285.0


def build_dipstick():
    """Bank 2, entry at the block skirt to a loop handle above the cam cover.

    The old route ran the whole climb at a fixed x = DIP_X on the bank's
    outer (m, h) face — the same face `exhaust.py` now lands each cylinder's
    flange on (heads.EX_BAND_H, h 248..308, full length of the head) — and
    grazed cylinder 9's flange there (measured ~1400 / ~600 mm^3 into the
    clip / tube). There is no outboard corridor left at that height either
    (module docstring: turbo housings sit outboard of the head), so instead
    of hugging the outer face through that band the tube detours to the
    FRONT of the head: a short corridor at x = CORR_X, 1 mm proud of
    `heads.HEAD_FRONT_X` (306) and well clear of every cylinder's flange
    (which stops at their own x +/- FLANGE_W/2) and of the nearer chain
    plane (bank 1, `spec.CHAIN_X[1]` = 318). The P-clip moves with it: it
    now seats on the front face itself, above h 320 (clear of the band and
    of the front-face coolant boss at `heads.COOLANT_MH[0]`, m=-104 h=340),
    reaching out to the corridor instead of the old outer-face seat.
    """
    b = 2
    bp = lambda x, m, h: S.bank_point(b, x, m, h)
    CORR_X = 307.0        # 1 mm proud of HEAD_FRONT_X (306); tube surface then
                           # spans x 301..313, clear of every flange (<=295)
                           # and >=5 mm shy of CHAIN_X[1] (318)
    CORR_M = -152.0        # same outboard lane the old outer-face route used
    path = [
        (DIP_X, -200.0, 22.0),
        bp(DIP_X, -133.0, 220.0),
        bp(302.0, -145.0, 232.0),
        bp(CORR_X, CORR_M, 280.0),
        bp(CORR_X, -135.0, 325.0),
        (DIP_X, -375.5, 112.5),
        (DIP_X, -395.0, 180.0),
        (DIP_X, -410.0, 224.0),
        (DIP_X, -370.0, 272.0),
        (DIP_X, -330.0, 315.0),
        (DIP_X, -316.0, 337.0),
    ]
    tube = _tube(path, 12.0, bend=30.0)
    # block.py has no matching drilled passage for this tube (out of scope
    # here — never edit block.py without being told to), so clip both the
    # tube and its entry boss to the real block surface instead of letting
    # them plow into solid material (measured ~2400 / ~7000 mm^3 uncut).
    tube = _clip_to_block(tube, 2)
    parts = [P.style(tube, "dipstick_tube", P.MACHINED_STEEL)]
    # boss where it enters the block skirt
    boss = geo.cyl_along((DIP_X, -196.0, 19.0), (DIP_X, -216.0, 33.0), 24.0)
    boss = _clip_to_block(boss, 2)
    parts.append(P.style(boss, "dipstick_boss", P.CAST))
    # loop handle
    d = (path[-1][1] - path[-2][1], path[-1][2] - path[-2][2])
    n = math.hypot(*d)
    d = (d[0] / n, d[1] / n)
    c = (DIP_X, path[-1][1] + d[0] * 22.0, path[-1][2] + d[1] * 22.0)
    ring = bd.Torus(22.0, 4.5).moved(bd.Location(c, (0.0, 90.0, 0.0)))
    stem = geo.cyl_along((DIP_X, path[-1][1], path[-1][2]), c, 9.0)
    parts.append(P.style(fuse_all([ring, stem]), "dipstick_handle", P.RED_ANODISE))
    # P-clip on the head's FRONT face (normal = +X), above h 320. The seat
    # sits at m = -125 (5 mm inboard of the +/-130 face edge) and h = 331:
    # close enough to CORR_M that the arm never swings toward the engine
    # centreline, which is where camdrive's bank-2 chain run 3 lands a
    # spacer right at m ~= -107, h ~= 322 (`chain_guide_spacer:2_3_*`), and
    # h = 331 splits the gap between that spacer and the front-face coolant
    # boss (`heads.COOLANT_MH[0]`, m=-104 h=340) to clear both by >= 3 mm.
    clip_c = bp(CORR_X, -135.0, 325.0)          # matches the tube's corridor-exit waypoint
    face_n = (1.0, 0.0, 0.0)
    seat = bp(H.HEAD_FRONT_X, -125.0, 331.0)
    # the arm's cap sits exactly on the front face; nudged 2 mm proud along
    # the face normal so its round cross-section does not graze the real
    # (fillet-softened) casting surface there.
    arm_end = tuple(seat[i] + face_n[i] * 2.0 for i in range(3))
    clip = fuse_all([
        _ring(clip_c, (clip_c[0] + 1.0, clip_c[1], clip_c[2]), 22.0, 12.6),
        geo.cyl_along(clip_c, arm_end, 12.0),
    ])
    clip = clip - geo.cyl_along((clip_c[0], clip_c[1] - 6.0, clip_c[2] - 4.0),
                                 (clip_c[0], clip_c[1] + 6.0, clip_c[2] + 4.0), 12.4)
    parts.append(P.style(clip, "dipstick_clip", P.STEEL))
    parts.append(P.style(geo.locate(F.hex_flange_bolt(8.0, 24.0), seat, face_n, S.bank_up(b)),
                         "dipstick_clip_bolt", P.TITANIUM))
    return parts


# ---------------------------------------------------------------------------
# Engine mounts and lifting eyes
# ---------------------------------------------------------------------------

def _block_envelope(bank: int = None):
    """The block's own smooth envelope plus its proud lower-skirt features:
    `oil_system.block_trim` (bulkhead ribs, rail rib, cross-bolt bosses,
    parting bead) fused with the water-jacket bulge(s) (`block._jacket`).
    NOT `block.build_block()`: subtracting that casting whole is
    pathological for OCC (oil_system's own note: tens of minutes, never
    returned).

    `bank=1`/`2` includes only that bank's jacket (use for a part that sits
    on one side, e.g. a per-bank water pump); `bank=None` (the default)
    includes BOTH — cheap enough, and correct for anything not tied to one
    side (the front accessory drive is bank-agnostic hardware; see the
    module docstring).

    The jacket bulge is the one proud feature `block_trim` does not carry
    (oil_system's own castings sit well below it); measured empirically
    against `block.build_block()`, it was the sole remaining source of
    overlap for every part here that beds against the block's front face
    or skirt without its own explicit clearance cut — not just the mount
    ears (~1500 mm^3), but the water-pump housings, the alternator and
    tensioner brackets, the dipstick tube/boss and the bell-housing plate
    all pick up a few hundred to a few thousand mm^3 of it from ordinary
    cosmetic `soften()` fillets blending back past the true surface.

    Also missing from `block_trim` (it only serves oil_system's own
    castings, which sit well clear of the front face): the sump-rail bolt
    bosses (`block._rail_bosses`), which stand proud right where the
    alternator and tensioner brackets' feet land near the bottom of the
    skirt, and the front crank-seal retainer boss (centred on the crank
    axis, Ø110 x 6 mm proud), which the tensioner bracket's foot clips.

    `copy.deepcopy` is required, not optional: `block_trim` is memoized in
    `oil_system`, and cutting a part with the cached object directly would
    mutate OCCT's shared tool (booleans mutate their tool — see
    `oil_system.block_trim`'s own note), corrupting it for every later
    caller."""
    import copy
    from lib.castings import boss as _c_boss
    trim = copy.deepcopy(O.block_trim(True))
    jackets = [B._jacket(bank)] if bank is not None else [B._jacket(1), B._jacket(2)]
    rail_envelope = geo.prism_yz(B.section_outline(), S.BLOCK_REAR_X - 1.0, S.BLOCK_FRONT_X + 1.0)
    seal = geo.locate(_c_boss(B.SEAL_F_OD, B.SEAL_F_PROUD + 2.0, draft_deg=5.0, fillet_r=4.0),
                      (S.BLOCK_FRONT_X - 2.0, 0.0, 0.0), (1, 0, 0))
    return fuse_all([trim, seal] + jackets + B._bell_lugs() + B._rail_bosses(rail_envelope))


def _clip_to_block(shape, bank: int = None):
    """`shape` trimmed clear of the real block casting (see
    `_block_envelope`).  Falls back to the uncut shape if the cut ever
    comes back unsound — never worse than what the caller already had."""
    cut = shape - _block_envelope(bank)
    return cut if is_sound(cut) else shape


def _skirt_face(bank: int, z: float):
    """(y, z) on the block's lower outer face at height z, for this bank."""
    y = 165.0 + (198.7 - 165.0) * (z + 95.0) / 116.9
    return (_sgn(bank) * y, z)


def build_mounts(sectioned: bool = True):
    parts = []
    fy = (0.9612, -0.2757)            # outward normal of the bank-1 skirt face
    for bank in (1, 2):
        s = _sgn(bank)
        p_lo = _skirt_face(bank, -62.0)
        p_hi = _skirt_face(bank, -4.0)
        nrm = (0.0, s * fy[0], fy[1])
        # ear: pad against the skirt face, ribbed web out to the bore boss
        def off(p, t):
            return (p[0] + s * fy[0] * t, p[1] + fy[1] * t)

        pad_poly = [off(p_lo, -4.0), off(p_hi, -4.0), off(p_hi, 22.0), off(p_lo, 22.0)]
        pad_body = _plate(pad_poly, -60.0, 60.0)
        # the web crosses the pad's faces transversally (no vertex sitting on
        # another solid's edge, which is what makes a fuse come back unsound)
        w_lo, w_hi = _skirt_face(bank, -72.0), _skirt_face(bank, 6.0)
        web_poly = [off(w_lo, 5.0), off(w_hi, 5.0), (s * (MOUNT_YZ + 34.0), 26.0),
                    (s * (MOUNT_YZ + 34.0), -26.0)]
        web = _plate(web_poly, -17.0, 17.0)
        boss = geo.cyl_x(-46.0, 46.0, 96.0, s * MOUNT_YZ, 0.0)
        ribs = [_plate(web_poly, xr - 6.0, xr + 6.0) for xr in (-36.0, 36.0)]
        ear = fuse_all([pad_body, web, boss] + ribs)
        # the pad is authored 4 mm INSIDE the skirt so the fuse is transversal;
        # the block envelope (+ its proud skirt features, + the oversized
        # local rib reliefs) then takes that bedding back off, leaving the
        # pad face ON the skirt (the bore cutter is well clear of it, so the
        # tools of this cut do not overlap).
        ear = ear - [geo.cyl_x(-56.0, 56.0, 60.0, s * MOUNT_YZ, 0.0), _block_envelope(bank)]
        ear, _ = soften(ear, 5.0, min_r=1.0)
        parts.append(P.style(ear, f"engine_mount:{bank}", P.CAST))
        # ID pad on the ear's outer cheek
        pad = F.id_pad(50.0, 18.0, 2.0)
        c_lo, c_hi = off(p_lo, 9.0), off(p_hi, 9.0)
        pad_pt = (60.0, (c_lo[0] + c_hi[0]) / 2.0, (c_lo[1] + c_hi[1]) / 2.0)
        parts.append(P.style(geo.locate(pad, pad_pt, (1, 0, 0), (0.0, -s * fy[1], fy[0])),
                             f"engine_mount_id_pad:{bank}", P.MACHINED))
        # 4 M12 into the skirt face
        m12 = F.hex_flange_bolt(12.0, 34.0)
        for k, (bx, bp) in enumerate([(-46.0, p_lo), (46.0, p_lo), (-46.0, p_hi), (46.0, p_hi)]):
            seat = (bx, off(bp, 18.0)[0], off(bp, 18.0)[1])
            parts.append(P.style(geo.locate(m12, seat, nrm, (1, 0, 0)),
                                 f"engine_mount_bolt:{bank}_{k + 1}", P.TITANIUM))

    # lifting eyes on the heads' front and rear end faces
    eye = F.lifting_eye()
    for bank, end, x_face, xdir in ((1, "front", S.CAM_FRONT_X, 1.0), (1, "rear", S.HEAD_REAR_X, -1.0),
                                    (2, "front", S.CAM_FRONT_X, 1.0), (2, "rear", S.HEAD_REAR_X, -1.0)):
        if bank == 1 and end == "front":
            seat = S.bank_point(bank, x_face, -112.0, S.DECK_H + 74.0)
            assert geo.in_section_void((x_face, seat[1], seat[2]), bank, sectioned), \
                "bank-1 front lifting eye should be in the section void"
            continue
        if bank == 2 and end == "rear":
            continue                   # two eyes: bank-2 front, bank-1 rear
        seat = S.bank_point(bank, x_face, -112.0, S.DECK_H + 74.0)
        up = S.bank_up(bank)
        # the eye's foot bears on its own local z = 0 (fasteners.lifting_eye);
        # seating it AT x_face put the foot's full footprint over the head's
        # EYE_PROUD boss root instead of its tip, burying the whole boss
        # (Ø34, proud 7 mm) inside the foot — seat on the boss's proud face.
        # On bank 2's front eye the foot's 40 mm length (along `up`) also
        # reaches the coolant boss 40 mm further up (`heads.COOLANT_MH`), so
        # clear whichever of the two front-face bosses stands proudest.
        eye_x = x_face + xdir * max(H.EYE_PROUD, H.COOLANT_PROUD)
        parts.append(P.style(geo.locate(eye, (eye_x, seat[1], seat[2]), (xdir, 0, 0), up),
                             f"lifting_eye:{bank}_{end}", P.STEEL_DARK))
        parts.append(P.style(geo.locate(F.hex_flange_bolt(10.0, 30.0),
                                        (x_face + xdir * 10.0, seat[1], seat[2]), (xdir, 0, 0)),
                             f"lifting_eye_bolt:{bank}_{end}", P.TITANIUM))
    return parts


# ---------------------------------------------------------------------------
# Bell-housing face + starter
# ---------------------------------------------------------------------------

def build_bell():
    x0, x1 = BELL_X
    parts = []
    plate = geo.cyl_x(x0, x1, 2 * BELL_R) - geo.cyl_x(x0 - 6, x1 + 6, 2 * BELL_BORE_R)
    ribs = []
    for k in range(8):
        a = 45.0 * k + 22.5
        rib = bd.Box(9.0, 40.0, 11.0, align=(bd.Align.CENTER, bd.Align.MIN, bd.Align.CENTER)).moved(
            bd.Location((x0 - 4.0, BELL_BORE_R + 4.0, 0.0)))
        ribs.append(rib.rotate(bd.Axis.X, a))
    boss = geo.cyl_x(x0 - 12.0, x1, 62.0, *STARTER_YZ)
    plate = fuse_all([plate] + ribs + [boss])
    cuts = [geo.cyl_x(x0 - 16, x1 + 4, 36.0, *STARTER_YZ)]
    for k in range(12):
        a = math.radians(30.0 * k + 15.0)
        cuts.append(geo.cyl_x(x0 - 4, x1 + 4, 13.5,
                              BELL_PCD * math.cos(a), BELL_PCD * math.sin(a)))
    for a_deg in (105.0, 285.0):
        a = math.radians(a_deg)
        cuts.append(geo.cyl_x(x0 - 4, x1 + 4, 16.2,
                              BELL_PCD * math.cos(a), BELL_PCD * math.sin(a)))
    plate = plate - cuts
    plate, _ = safe_fillet(plate, [e for e in plate.edges()
                                   if _edge_r(e) is not None and abs(_edge_r(e) - BELL_R) < 1e-6], 4.0)
    assert is_sound(plate), "bell housing plate not sound"
    # clear of the block's own rear-face cast lugs (`block._bell_lugs`),
    # which stand proud of the skirt right at this plate's inner edge.
    plate = _clip_to_block(plate)
    parts.append(P.style(plate, "bell_housing_plate", P.CAST))

    m12 = F.hex_flange_bolt(12.0, 32.0)
    for k in range(12):
        a = math.radians(30.0 * k + 15.0)
        parts.append(P.style(geo.locate(m12, (x0, BELL_PCD * math.cos(a), BELL_PCD * math.sin(a)),
                                        (-1, 0, 0)),
                             f"bell_housing_bolt:{k + 1}", P.TITANIUM))
    for i, a_deg in enumerate((105.0, 285.0)):
        a = math.radians(a_deg)
        y, z = BELL_PCD * math.cos(a), BELL_PCD * math.sin(a)
        dowel = geo.cyl_x(x0 - 14.0, x1 - 6.0, 16.0, y, z)
        dowel, _ = safe_fillet(dowel, [e for e in dowel.edges()
                                       if _edge_r(e) is not None and abs(_edge_r(e) - 8.0) < 1e-6
                                       and abs(e.bounding_box().center().X - (x0 - 14.0)) < 0.2], 1.6)
        parts.append(P.style(dowel, f"bell_housing_dowel:{i + 1}", P.MACHINED_STEEL))

    # starter: nose through the (unchanged) plate boss to the ring gear, body
    # mounted alongside the block skirt running FORWARD from the bell face —
    # real starters sit beside the bellhousing, not hung off the back of it.
    # REAR is the group's rearmost station (>= -360 required); the boss/plate
    # itself already reaches to x0-12, so the register butts flush to it.
    sy, sz = STARTER_YZ
    REAR = x0 - 12.0
    # the snout through the plate and the pinion stay outside the flywheel's
    # R160 disc; only the pinion reaches the ring-gear station, 3 mm clear
    nose = fuse_all([geo.cyl_x(REAR, x0, 88.0, sy, sz),
                     geo.cyl_x(x0, x1 - 24.0, 34.0, sy, sz)])
    nose = nose - geo.cyl_x(REAR - 4.0, x1 - 16.0, 22.0, sy, sz)
    nose, _ = soften(nose, 3.0, min_r=0.8)
    parts.append(P.style(nose, "starter_drive_housing", P.CAST))
    parts.append(P.style(geo.cyl_x(x1 - 24.0, x1 - 4.0, 30.0, sy, sz), "starter_pinion", P.MACHINED_STEEL))
    parts.append(P.style(geo.cyl_x(REAR, x1 - 18.0, 20.0, sy, sz), "starter_shaft", P.MACHINED_STEEL))
    # body: the pinion axis (r 178 from the crank) sits INSIDE the block's own
    # skirt wall once x runs past the block's rear face (O.skirt_y peaks near
    # 199), so the housing cannot stay coaxial with the pinion out here — it
    # has to walk outward in y while still behind/at the boss (bore-limited to
    # r 18 there), then run straight at the cleared offset. Every station is
    # checked against `O.skirt_y(z)` so nothing rides inside the casting.
    bridge = geo.cyl_x(x1 - 4.0, x1, 30.0, sy, sz)                    # x1-4..x1, still on-axis
    seg1 = geo.cyl_x(x1, x1 + 18.0, 40.0, -193.0, -78.0)              # first step clear of the skirt
    seg2 = geo.cyl_x(x1 + 18.0, x1 + 38.0, 60.0, -215.0, -73.0)
    body_yz = (-230.0, -70.0)                                        # clears skirt_y (<= 199) with margin
    main = geo.cyl_x(x1 + 38.0, x1 + 118.0, 80.0, *body_yz)
    cap = geo.cyl_x(x1 + 118.0, x1 + 128.0, 68.0, *body_yz)
    body = fuse_all([bridge, seg1, seg2, main, cap])
    body, _ = soften(body, 3.0, min_r=0.8)
    parts.append(P.style(body, "starter_body", P.COMPOSITE))
    soln_yz = (body_yz[0], -10.0)
    sol = fuse_all([geo.cyl_x(-260.0, -210.0, 48.0, *soln_yz),
                    geo.cyl_x(-272.0, -260.0, 30.0, *soln_yz)])
    sol, _ = soften(sol, 2.0, min_r=0.5)
    parts.append(P.style(sol, "starter_solenoid", P.CAST))
    parts.append(P.style(geo.cyl_x(-276.0, -268.0, 14.0, *soln_yz),
                         "starter_terminal", P.BRASS))
    for k, a_deg in enumerate((35.0, 215.0)):
        a = math.radians(a_deg)
        parts.append(P.style(geo.locate(F.hex_flange_bolt(12.0, 34.0),
                                        (x0 - 3.0, sy + 36.0 * math.cos(a), sz + 36.0 * math.sin(a)),
                                        (-1, 0, 0)),
                             f"starter_bolt:{k + 1}", P.TITANIUM))
    return parts


# ---------------------------------------------------------------------------

def build(sectioned: bool = True):
    parts = []
    parts += build_water_pump(1)
    parts += build_water_pump(2)
    parts += build_alternator()
    parts += build_idler()
    parts += build_tensioner()
    parts.append(build_belt())
    parts += build_coolant(1, sectioned)
    parts += build_coolant(2, sectioned)
    parts += build_dipstick()
    parts += build_mounts(sectioned)
    parts += build_bell()
    return parts


if __name__ == "__main__":
    import time

    t0 = time.time()
    groups = [("water_pump_1", lambda: build_water_pump(1)),
              ("water_pump_2", lambda: build_water_pump(2)),
              ("alternator", build_alternator),
              ("idler", build_idler),
              ("tensioner", build_tensioner),
              ("belt", lambda: [build_belt()]),
              ("coolant_1", lambda: build_coolant(1, True)),
              ("coolant_2", lambda: build_coolant(2, True)),
              ("dipstick", build_dipstick),
              ("mounts", lambda: build_mounts(True)),
              ("bell", build_bell)]
    bad, total = [], 0
    for name, fn in groups:
        t = time.time()
        try:
            ps = fn()
        except Exception as exc:
            print(f"{name:>14}  BUILD FAILED: {type(exc).__name__}: {exc}")
            bad.append(name)
            continue
        total += len(ps)
        unsound = [p.label for p in ps if not geo.sound(p)]
        bad += unsound
        print(f"{name:>14}  {len(ps):3d} parts  {time.time() - t:6.1f}s  "
              f"{'OK' if not unsound else 'UNSOUND: ' + ','.join(unsound)}")
    print(f"total {total} parts in {time.time() - t0:.1f}s; problems: {bad or 'none'}")
    print("belt stations (name, (y,z), rim radius, wrap deg):")
    for row in belt_stations():
        print("   ", row)
