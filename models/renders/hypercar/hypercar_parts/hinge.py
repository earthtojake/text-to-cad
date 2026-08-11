"""The dihedral synchro-helix door hinge -- the car's one piece of jewellery.

What the mechanism actually is
------------------------------
A fixed **tower** stands just off the flank at the A-pillar base, carried on two
machined arms so you can see all the way around it.  Inside it, two helices of
very different lead do two different jobs:

``hinge_screw``   a fast three-start bronze lead screw, nine turns of deep ACME
                  thread running the whole height of the tower.  It is the
                  drive -- the actuator barrel at the base spins it -- and it
                  is the piece the eye goes to first.

``synchro_rail``  two broad aluminium ribbons caged around the screw, each
                  slotted down its centre and each twisting ``DOOR_SWEEP_DEG``
                  over the carrier's travel.  They are the anti-rotation guide,
                  and because they *twist* they turn the carrier's climb into
                  exactly 62 deg of rotation: lift and swing are one motion,
                  not two bolted together.  The slot is the visible track.

``carrier``       the machined aluminium collar that rides both: a nut on the
                  screw, two bronze shoes in the tracks.  Windows through its
                  wall show the nut ring inside.

``swing_arm`` + ``control_link``  a four-bar out to the door: the arm carries
                  the load, the shorter link below it drives the door bracket's
                  angle, so the door keeps rotating open after the carrier has
                  finished climbing.

Net door motion, which the animation sidecar takes from the constants below:
62 deg of rotation about the tower axis while translating 310 mm *along* it --
300 mm of lift and 80 mm forward.  The door leaves the body sideways, rises
most of a foot and tips nose-up.  It should look impossible.

Frame
-----
Everything is built in a local tower frame and mapped into car coordinates:

    local +X  outboard      local +Y  aft      local +Z  up the tower axis
    local origin            centre of the tower base

The right-hand assembly is a true mirror of the left, so its screw and rails
are opposite-hand, exactly as a real pair would be machined.
"""

from __future__ import annotations

import math

from build123d import (
    Align,
    Axis,
    Cylinder,
    Helix,
    Plane,
    Polyline,
    Pos,
    RectangleRounded,
    Rot,
    extrude,
    loft,
    make_face,
    mirror,
    revolve,
    sweep,
)

from cadgen import compound_from_instances

from hypercar_parts import surfaces as S
from hypercar_parts.context import group
from hypercar_parts import palette as P
from hypercar_parts.palette import style


# ---------------------------------------------------------------------------
# small vector helpers (plain tuples -- this module does a lot of frame work)
# ---------------------------------------------------------------------------


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(*vs):
    return tuple(sum(v[i] for v in vs) for i in range(3))


def _mul(v, s):
    return (v[0] * s, v[1] * s, v[2] * s)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _unit(v):
    m = math.sqrt(_dot(v, v)) or 1.0
    return (v[0] / m, v[1] / m, v[2] / m)


# ---------------------------------------------------------------------------
# where the tower stands
# ---------------------------------------------------------------------------
#
# Base and top were chosen by walking the master flank surface: over this run
# the body's half-width only moves ~55 mm, so one straight tower keeps a fairly
# even 50-100 mm stand-off for its whole length instead of diving into the
# flank at the waist.  It starts at the A-pillar base, forward of the door
# shutline (BX_DOOR_F = 785) so nothing fixed is ever bolted to the door, and
# rakes forward under the fender crest.

TOWER_BASE = (800.0, 918.0, 346.0)      # left side, car coordinates
TOWER_TOP = (903.0, 934.0, 732.0)

TOWER_H = math.sqrt(_dot(_sub(TOWER_TOP, TOWER_BASE), _sub(TOWER_TOP, TOWER_BASE)))

_U = _unit(_sub(TOWER_TOP, TOWER_BASE))                     # local +Z
_N = _unit(_sub((0.0, 1.0, 0.0), _mul(_U, _dot((0.0, 1.0, 0.0), _U))))   # local +X
_V = _cross(_U, _N)                                         # local +Y (aft)

_PL = Plane(origin=TOWER_BASE, x_dir=_N, z_dir=_U)


def _l2g(p):
    """Local tower coordinates -> car coordinates (left side)."""
    return _add(TOWER_BASE, _mul(_N, p[0]), _mul(_V, p[1]), _mul(_U, p[2]))


def _g2l(p):
    d = _sub(p, TOWER_BASE)
    return (_dot(d, _N), _dot(d, _V), _dot(d, _U))


# ---------------------------------------------------------------------------
# MOTION CONSTANTS -- the animation sidecar derives the door from these
# ---------------------------------------------------------------------------
#
# Door pose at open fraction ``t`` (0 shut, 1 open), for one side:
#
#     rotate  t * DOOR_SWEEP_DEG * DOOR_SWEEP_SIGN[side]  degrees about the
#             axis (HELIX_AXIS_ORIGIN[side], HELIX_AXIS_DIR[side])
#     then translate  t * DOOR_SWEEP_DEG * HELIX_LEAD_MM_PER_DEG  mm along
#             HELIX_AXIS_DIR[side]
#
# DIR always points UP the tower, so the translation is always the lift; the
# sign lives on the rotation, because the two sides are opposite-hand screws.

CARRIER_HOME_S = 46.0                   # carrier centre along the tower, shut
DOOR_SWEEP_DEG = 62.0
HELIX_LEAD_MM_PER_DEG = 5.0
CARRIER_TRAVEL = DOOR_SWEEP_DEG * HELIX_LEAD_MM_PER_DEG     # 310 mm

HELIX_AXIS_ORIGIN_LEFT = _l2g((0.0, 0.0, CARRIER_HOME_S))
HELIX_AXIS_ORIGIN_RIGHT = (
    HELIX_AXIS_ORIGIN_LEFT[0],
    -HELIX_AXIS_ORIGIN_LEFT[1],
    HELIX_AXIS_ORIGIN_LEFT[2],
)
HELIX_AXIS_DIR_LEFT = _U
HELIX_AXIS_DIR_RIGHT = (_U[0], -_U[1], _U[2])

HELIX_AXIS_ORIGIN = {"left": HELIX_AXIS_ORIGIN_LEFT, "right": HELIX_AXIS_ORIGIN_RIGHT}
HELIX_AXIS_DIR = {"left": HELIX_AXIS_DIR_LEFT, "right": HELIX_AXIS_DIR_RIGHT}
DOOR_SWEEP_SIGN = {"left": -1.0, "right": 1.0}

# what that works out to, so the sidecar author can sanity-check the numbers
DOOR_LIFT_MM = CARRIER_TRAVEL * _U[2]           # ~300
DOOR_FORWARD_MM = CARRIER_TRAVEL * _U[0]        # ~80


def door_axis(side):
    """(origin, unit_dir, signed_sweep_deg, lift_vector) for 'left'/'right'."""
    d = HELIX_AXIS_DIR[side]
    return (
        HELIX_AXIS_ORIGIN[side],
        d,
        DOOR_SWEEP_DEG * DOOR_SWEEP_SIGN[side],
        _mul(d, CARRIER_TRAVEL),
    )


# ---------------------------------------------------------------------------
# body-surface query (mounts and door bracket have to sit ON the skin)
# ---------------------------------------------------------------------------


def _catmull2(pts, t):
    n = len(pts) - 1
    i = min(int(t * n), n - 1)
    u = t * n - i
    p1, p2 = pts[i], pts[i + 1]
    p0 = pts[i - 1] if i > 0 else pts[i]
    p3 = pts[i + 2] if i + 2 <= n else pts[i + 1]
    out = []
    for k in (0, 1):
        m1 = 0.5 * (p2[k] - p0[k])
        m2 = 0.5 * (p3[k] - p1[k])
        u2, u3 = u * u, u * u * u
        out.append(
            (2 * u3 - 3 * u2 + 1) * p1[k]
            + (u3 - 2 * u2 + u) * m1
            + (-2 * u3 + 3 * u2) * p2[k]
            + (u3 - u2) * m2
        )
    return out


_FLANK_CACHE = {}


def _flank_y(x, z):
    """Half-width of the master body surface at station x, height z."""
    key = (round(x, 1), round(z, 1))
    hit = _FLANK_CACHE.get(key)
    if hit is not None:
        return hit
    top, flank, under = S.body_section_bands(x)
    band = top[-3:] + flank[1:] + under[1:2]
    sm = [_catmull2(band, i / 240.0) for i in range(241)]
    best = None
    for i in range(240):
        (y0, z0), (y1, z1) = sm[i], sm[i + 1]
        if (z0 - z) * (z1 - z) <= 0 and z0 != z1:
            y = y0 + (z - z0) / (z1 - z0) * (y1 - y0)
            if best is None or y > best:
                best = y
    if best is None:
        best = S.HALF_WIDTH(x) * 0.95
    _FLANK_CACHE[key] = best
    return best


def _surface_local_x(s):
    """Local x of the body skin, level with the tower axis' station ``s``."""
    g = _l2g((0.0, 0.0, s))
    return _flank_y(g[0], g[2]) - g[1]


# ---------------------------------------------------------------------------
# generic shape helpers
# ---------------------------------------------------------------------------


def _ring(pts):
    """Solid of revolution from a closed (radius, height) profile."""
    return revolve(Plane.XZ * make_face(Polyline(*pts, close=True)), Axis.Z)


def _sect(origin, x_dir, z_dir, w, h, r):
    return Plane(origin=origin, x_dir=x_dir, z_dir=z_dir) * RectangleRounded(w, h, r)


def _blade(p0, p1, profile, bow=(0.0, 0.0, 0.0), ref=(1.0, 0.0, 0.0)):
    """Loft a tapered rounded blade along a gently bowed path p0 -> p1.

    ``profile`` is [(t, width, height, corner_r)] with width measured along the
    reference direction projected perpendicular to the path.
    """
    mid = _add(_mul(_add(p0, p1), 0.5), bow)
    faces = []
    for t, w, h, r in profile:
        a, b, c = (1 - t) ** 2, 2 * (1 - t) * t, t * t
        pt = _add(_mul(p0, a), _mul(mid, b), _mul(p1, c))
        da = _mul(_sub(mid, p0), 2 * (1 - t))
        db = _mul(_sub(p1, mid), 2 * t)
        tan = _unit(_add(da, db))
        xd = _sub(ref, _mul(tan, _dot(ref, tan)))
        if _dot(xd, xd) < 1e-6:
            xd = _sub((0, 0, 1), _mul(tan, _dot((0, 0, 1), tan)))
        faces.append(_sect(pt, _unit(xd), tan, w, h, r))
    return loft(faces)


def _surface_plate(levels, out=16.0, into=7.0):
    """A lens-shaped plate lying ON the body skin, given (z, x0, x1) levels."""
    faces = []
    for z, x0, x1 in levels:
        xs = [x0 + (x1 - x0) * i / 10.0 for i in range(11)]
        outer = [(x, _flank_y(x, z) + out) for x in xs]
        inner = [(x, _flank_y(x, z) - into) for x in reversed(xs)]
        faces.append(
            Plane.XY.offset(z) * make_face(Polyline(*(outer + inner), close=True))
        )
    return loft(faces)


# ---------------------------------------------------------------------------
# the fixed tower
# ---------------------------------------------------------------------------

SCREW_CORE_R = 16.0
SCREW_PITCH_R = 18.6                    # thread centreline radius
SCREW_Z0, SCREW_Z1 = 4.0, 402.0
SCREW_LEAD = 45.0                       # axial advance per turn, per start
SCREW_STARTS = 3

RAIL_R = 32.0                           # rail centreline radius
RAIL_W_MID = 42.0                       # tangential width at mid height
RAIL_W_END = 30.0
RAIL_T = 9.0                            # radial thickness
RAIL_Z0, RAIL_Z1 = 8.0, 388.0
RAIL_PHASE = (32.0, 212.0)
TWIST_PER_MM = DOOR_SWEEP_DEG / CARRIER_TRAVEL      # 0.2 deg/mm


def _screw_core():
    return Pos(0, 0, SCREW_Z0) * Cylinder(
        radius=SCREW_CORE_R,
        height=SCREW_Z1 - SCREW_Z0,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    )


def _screw_thread(start):
    """One start of the exposed three-start ACME thread.

    Swept, never cut: subtracting a helical tool from the core is exactly the
    boolean OCC gives up on silently -- it hands back the uncut solid, or an
    empty one.  A swept rib overlapping the core reads identically and always
    builds.
    """
    path = Pos(0, 0, SCREW_Z0 - 22.0) * Rot(0, 0, 360.0 * start / SCREW_STARTS) * Helix(
        pitch=SCREW_LEAD, height=SCREW_Z1 - SCREW_Z0 + 44.0, radius=SCREW_PITCH_R
    )
    prof = make_face(
        Polyline((-4.6, -6.8), (4.2, -4.0), (4.2, 4.0), (-4.6, 6.8), close=True)
    )
    p0 = path @ 0
    sec = Plane(origin=p0, x_dir=(p0.X, p0.Y, 0.0), z_dir=path % 0) * prof
    return sweep(sec, path, is_frenet=True)


def _rail_loft(phase, thick, width_fn, corner, z0=RAIL_Z0, z1=RAIL_Z1):
    faces = []
    n = 19
    for i in range(n):
        f = i / (n - 1)
        z = z0 + (z1 - z0) * f
        th = math.radians(phase + TWIST_PER_MM * z)
        c = (RAIL_R * math.cos(th), RAIL_R * math.sin(th), z)
        faces.append(
            _sect(
                c, (math.cos(th), math.sin(th), 0.0), (0, 0, 1),
                thick, width_fn(f), corner,
            )
        )
    return loft(faces)


def _rail(phase):
    """One twisted ribbon of the synchro cage, with its track slot cut through.

    Two broad ribbons rather than several narrow ones: a wide ribbon turns its
    face to the light as it twists, so the twist becomes the highlight instead
    of something you have to be told about.  The slot down the middle is the
    track the carrier's shoe actually rides in, and its silhouette is what
    makes the twist unmistakable.
    """
    ribbon = _rail_loft(
        phase,
        RAIL_T,
        lambda f: RAIL_W_END + (RAIL_W_MID - RAIL_W_END) * math.sin(math.pi * f) ** 0.7,
        3.4,
    )
    slot = _rail_loft(
        phase, RAIL_T + 14.0, lambda f: 14.0, 4.6, RAIL_Z0 + 40.0, RAIL_Z1 - 40.0
    )
    return ribbon - slot


def _block(sections):
    """Machined housing: a loft of rounded-rectangle sections up the axis."""
    return loft([
        _sect((0, 0, s), (1, 0, 0), (0, 0, 1), w, h, r) for s, w, h, r in sections
    ])


BASE_BLOCK = [
    (-34.0, 72.0, 80.0, 13.0),
    (-24.0, 90.0, 100.0, 16.0),
    (-6.0, 92.0, 102.0, 16.0),
    (12.0, 82.0, 90.0, 14.0),
    (26.0, 66.0, 72.0, 12.0),
]
TOP_BLOCK = [
    (382.0, 66.0, 74.0, 12.0),
    (396.0, 62.0, 70.0, 12.0),
    (410.0, 48.0, 54.0, 10.0),
]


def _base_housing():
    return _block(BASE_BLOCK)


def _top_housing():
    return _block(TOP_BLOCK)


def _bearing_cap():
    return _ring([
        (0, 408), (26, 408), (26, 414), (22, 418), (22, 422), (14, 426),
        (0, 426),
    ])


def _drive_motor():
    """Compact actuator barrel poking forward out of the base housing."""
    barrel = _ring([
        (0, 0), (21, 0), (21, 7), (18.5, 10), (18.5, 15), (21, 18), (21, 23),
        (18.5, 26), (18.5, 31), (21, 34), (21, 39), (16, 45), (0, 45),
    ])
    return Plane(origin=(0, -44.0, 2.0), x_dir=(1, 0, 0), z_dir=(0, -1, 0)) * barrel


# -- mounting arms ----------------------------------------------------------
#
# Each arm is a machined casting: a slab lofted from the tower out to the body
# skin, then lightened with big through-holes so it reads as engineering rather
# than as a lump of filler.  Both sit CLEAR of the carrier's 310 mm of travel --
# one under the base housing, one over the top housing -- so nothing fixed ever
# stands in the moving collar's way.

LOWER_ARM = [(-34.0, 22.0), (-18.0, 40.0), (0.0, 46.0), (14.0, 34.0)]
UPPER_ARM = [(380.0, 18.0), (392.0, 33.0), (406.0, 31.0), (418.0, 16.0)]

LOWER_HOLES = [(-12.0, 16.0), (6.0, 11.0)]      # (station, radius)
UPPER_HOLES = [(392.0, 12.0), (408.0, 9.0)]


def _mount_arm(stations, holes):
    faces = []
    for s, hw in stations:
        x_in, x_out = _bracket_x(s)
        w = x_out - x_in
        h = 2.0 * hw
        faces.append(
            _sect(
                (0.5 * (x_in + x_out), 0.0, s),
                (1, 0, 0),
                (0, 0, 1),
                w,
                h,
                min(w, h) * 0.20,
            )
        )
    arm = loft(faces)
    for s, r in holes:
        x_in, x_out = _bracket_x(s)
        cut = Plane(
            origin=(0.5 * (x_in + x_out) - 4.0, 0.0, s), x_dir=(1, 0, 0), z_dir=(0, 1, 0)
        ) * Cylinder(radius=r, height=260)
        arm = arm - cut
    return arm


def _bracket_x(s):
    """(inboard, outboard) local x of a mounting arm at station ``s``.

    The outboard limit deliberately laps INTO the housing it hangs off, so the
    arm is one piece with the tower instead of floating a few mm short of it.
    """
    x_in = _surface_local_x(s) - 14.0
    return x_in, -28.0


# -- pads bolted to the skin ------------------------------------------------

LOWER_PAD = [
    (300.0, 810.0, 852.0),
    (320.0, 794.0, 868.0),
    (344.0, 788.0, 874.0),
    (368.0, 794.0, 868.0),
    (388.0, 810.0, 852.0),
]
UPPER_PAD = [
    (700.0, 876.0, 918.0),
    (714.0, 862.0, 932.0),
    (730.0, 856.0, 938.0),
    (746.0, 862.0, 932.0),
    (758.0, 876.0, 918.0),
]

PAD_BOLTS = [
    (796.0, 312.0), (796.0, 376.0), (862.0, 344.0),
    (866.0, 708.0), (866.0, 750.0), (930.0, 729.0),
]


def _bolt_proto():
    """Cap-head fastener, axis +Z, head at +Z."""
    return _ring([
        (0, 0), (4.4, 0), (4.4, 9), (7.6, 9), (7.6, 14.2), (6.2, 16.0),
        (2.6, 16.0), (2.6, 13.0), (0, 13.0),
    ])


# ---------------------------------------------------------------------------
# the carrier and the four-bar
# ---------------------------------------------------------------------------

CARRIER_H = 54.0
CARRIER_RO = 52.0
CARRIER_RI = 39.0
_CZ0 = CARRIER_HOME_S - CARRIER_H / 2.0
_CZ1 = CARRIER_HOME_S + CARRIER_H / 2.0


def _carrier_collar():
    z0, z1 = _CZ0, _CZ1
    collar = _ring([
        (CARRIER_RI, z0), (45, z0), (CARRIER_RO, z0 + 5), (CARRIER_RO, z0 + 13),
        (49, z0 + 17), (49, z1 - 17), (CARRIER_RO, z1 - 13),
        (CARRIER_RO, z1 - 5), (45, z1), (CARRIER_RI, z1),
    ])
    for th in (131.0, 311.0):
        a = math.radians(th)
        cut = Plane(
            origin=(0, 0, CARRIER_HOME_S),
            x_dir=(0, 0, 1),
            z_dir=(math.cos(a), math.sin(a), 0),
        ) * Cylinder(radius=13.0, height=160)
        collar = collar - cut
    return collar


def _nut_ring():
    z = CARRIER_HOME_S
    return _ring([
        (14.6, z - 20), (32, z - 20), (32, z - 14), (27, z - 11),
        (27, z + 11), (32, z + 14), (32, z + 20), (14.6, z + 20),
    ])


def _shoe_proto():
    """Bronze follower-shoe cap, axis +Z."""
    return _ring([(0, 0), (8.4, 0), (8.4, 4.6), (6.6, 7.0), (0, 7.0)])


# four-bar pivots, local
PIV_ARM_C = (2.0, 52.0, 66.0)
PIV_LNK_C = (2.0, 52.0, 24.0)

# door-side pivots stand off the door skin, so the bracket sits ON the door
_LUG_A_G = (700.0, _flank_y(700.0, 468.0) + 36.0, 468.0)
_LUG_B_G = (692.0, _flank_y(692.0, 418.0) + 36.0, 418.0)
PIV_ARM_D = _g2l(_LUG_A_G)
PIV_LNK_D = _g2l(_LUG_B_G)


def _swing_arm():
    arm = _blade(
        PIV_ARM_C,
        PIV_ARM_D,
        [(0.0, 32, 54, 10), (0.28, 26, 48, 9), (0.62, 21, 39, 8), (1.0, 24, 34, 9)],
        bow=(7.0, 0.0, 8.0),
    )
    d = _unit(_sub(PIV_ARM_D, PIV_ARM_C))
    xd = _unit(_sub(d, _mul((1, 0, 0), _dot(d, (1, 0, 0)))))
    for t, ln in ((0.36, 26.0), (0.66, 20.0)):
        p = _add(_mul(PIV_ARM_C, 1 - t), _mul(PIV_ARM_D, t), (3.0, 0.0, 4.0))
        cut = Plane(origin=p, x_dir=xd, z_dir=(1, 0, 0)) * RectangleRounded(ln, 13.0, 6.0)
        arm = arm - (extrude(cut, amount=60) + extrude(cut, amount=-60))
    return arm


def _control_link():
    return _blade(
        PIV_LNK_C,
        PIV_LNK_D,
        [(0.0, 19, 30, 7), (0.4, 14, 22, 6), (1.0, 17, 25, 7)],
        bow=(5.0, 0.0, -6.0),
    )


def _pin_proto():
    """Pivot pin, axis +Z, domed head at +Z."""
    return _ring([
        (0, -20), (6.8, -20), (6.8, 13), (10.5, 13), (10.5, 18), (8.0, 21),
        (0, 21),
    ])


# ---------------------------------------------------------------------------
# the door-side bracket (built in car coordinates -- it hugs the door skin)
# ---------------------------------------------------------------------------

DOOR_PAD = [
    (386.0, 706.0, 748.0),
    (404.0, 682.0, 768.0),
    (430.0, 668.0, 776.0),
    (458.0, 676.0, 768.0),
    (478.0, 700.0, 748.0),
]

DOOR_BOLTS = [(676.0, 432.0), (770.0, 432.0), (722.0, 396.0), (722.0, 468.0)]


def _lug(pivot_g):
    x, y, z = pivot_g
    base_y = _flank_y(x, z) + 9.0
    return _blade(
        (x, base_y, z),
        (x, y, z),
        [(0.0, 54, 30, 11), (0.45, 44, 26, 10), (1.0, 32, 22, 9)],
        ref=(1, 0, 0),
    )


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------


def _left_leaves():
    """[(shape, role, colour)] for the left-hand hinge, in car coordinates."""
    out = [
        (_PL * _screw_core(), "hinge_screw_core", P.BRONZE_DARK),
        (_PL * _base_housing(), "tower_base_housing", P.BRONZE),
        (_PL * _drive_motor(), "actuator_barrel", P.BRONZE_DARK),
        (_PL * _top_housing(), "tower_top_housing", P.BRONZE),
        (_PL * _bearing_cap(), "tower_bearing_cap", P.BRONZE_DARK),
        (_PL * _mount_arm(LOWER_ARM, LOWER_HOLES), "hinge_mount_lower", P.ALUMINIUM),
        (_PL * _mount_arm(UPPER_ARM, UPPER_HOLES), "hinge_mount_upper", P.ALUMINIUM),
        (_surface_plate(LOWER_PAD), "mount_pad_lower", P.BRONZE_DARK),
        (_surface_plate(UPPER_PAD), "mount_pad_upper", P.BRONZE_DARK),
        (_PL * _carrier_collar(), "carrier", P.ALUMINIUM),
        (_PL * _nut_ring(), "carrier_nut", P.BRONZE),
        (_PL * _swing_arm(), "swing_arm", P.ALUMINIUM),
        (_PL * _control_link(), "control_link", P.ALUMINIUM_DARK),
        (_surface_plate(DOOR_PAD), "door_bracket", P.BRONZE),
        (_lug(_LUG_A_G), "door_lug_upper", P.ALUMINIUM),
        (_lug(_LUG_B_G), "door_lug_lower", P.ALUMINIUM),
    ]
    for i, phase in enumerate(RAIL_PHASE):
        out.append((_PL * _rail(phase), f"synchro_rail_{i + 1}", P.ALUMINIUM))
    for k in range(SCREW_STARTS):
        out.append((_PL * _screw_thread(k), f"hinge_screw_thread_{k + 1}", P.BRONZE))
    return out


def _hardware(side):
    """Bolts, shoe caps and pivot pins for one side, as shared instances."""
    name = "left" if side > 0 else "right"

    def loc(pos_g, dir_g):
        p = (pos_g[0], side * pos_g[1], pos_g[2])
        d = (dir_g[0], side * dir_g[1], dir_g[2])
        return Plane(origin=p, z_dir=d).location

    bolt = style(_bolt_proto(), f"mount_bolt:{name}", P.BRONZE_DARK)
    shoe = style(_shoe_proto(), f"carrier_shoe:{name}", P.BRONZE)
    pin = style(_pin_proto(), f"pivot_pin:{name}", P.BRONZE)

    inst = []
    for i, (x, z) in enumerate(PAD_BOLTS + DOOR_BOLTS):
        y = _flank_y(x, z) + 7.0
        inst.append((bolt, loc((x, y, z), (0.0, 1.0, 0.0)), f"mount_bolt:{name}_{i}"))

    for i, phase in enumerate(RAIL_PHASE):
        th = math.radians(phase + TWIST_PER_MM * CARRIER_HOME_S)
        d = _add(_mul(_N, math.cos(th)), _mul(_V, math.sin(th)))
        p = _l2g((CARRIER_RO * math.cos(th), CARRIER_RO * math.sin(th), CARRIER_HOME_S))
        inst.append((shoe, loc(_add(p, _mul(d, -2.0)), d), f"carrier_shoe:{name}_{i}"))

    for i, piv in enumerate((PIV_ARM_C, PIV_LNK_C, PIV_ARM_D, PIV_LNK_D)):
        inst.append((pin, loc(_l2g(piv), _N), f"pivot_pin:{name}_{i}"))

    return compound_from_instances(f"hinge_hardware:{name}", inst)


# The bodyside sits at |y| ~866 with a 14 mm skin, so the mechanism is clipped
# at the skin's inner face.  It is therefore fully concealed with the door shut
# and fully revealed once the door lifts away -- the motion is the reveal.
# An open bay in the flank was tried instead and abandoned: any hole big enough
# to show the mechanism also shows through the hollow body.
CLIP_Y = 850.0


def _clip_inboard(shape):
    from build123d import Box, Pos
    keep = Pos(0.0, 0.0, 0.0) * Box(6000.0, 2.0 * CLIP_Y, 6000.0)
    return shape & keep


def build():
    leaves = _left_leaves()

    left = [style(_clip_inboard(sh), f"{role}:left", col) for sh, role, col in leaves]
    left.append(_clip_inboard(_hardware(1)))

    right = [
        style(_clip_inboard(mirror(sh, Plane.XZ)), f"{role}:right", col)
        for sh, role, col in leaves
    ]
    right.append(_clip_inboard(_hardware(-1)))

    left = [sh for sh in left if sh.solids()]
    right = [sh for sh in right if sh.solids()]

    return group("hinge", [group("hinge:left", left), group("hinge:right", right)])
