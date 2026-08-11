"""F-14D nose landing gear -- leg, twin wheels, launch bar, doors, bay.

Gear DOWN, aircraft parked on the deck.

Retraction sense
----------------
The F-14 nose gear retracts AFT.  That is forced, not chosen: the leg is
1.40 m long and the wheel station is 3.12 m, so a forward-retracting unit would
have to stow between 1.7 and 3.2 m -- inside the AWG-9 radar bay, whose aft
bulkhead is at 2.48 m.  So the trunnion sits at the FORWARD end of the well,
the leg rakes 4 deg top-forward, the drag brace folds AFT, and the bay runs aft
from the trunnion under the front cockpit floor.

Everything downstream follows from that: the drag brace, downlock link,
retraction actuator and shimmy damper live on the AFT face of the leg, and the
forward face carries the launch bar, the approach/indexer light, the taxi light
and the steering actuators.

Ground contact
--------------
The module builds in the WATERLINE frame and :func:`stance` lifts it.  That
transform is a rotation about +Y by ``GROUND_PITCH`` then a lift by
``WATERLINE``, so a waterline-frame point ``(x, y, z)`` lands at world
``z' = -x*sin(t) + z*cos(t) + WATERLINE``.  :func:`ground_z` inverts it, which
is how the tyre contact plane is placed EXACTLY on Z=0 instead of being dialled
in by eye -- and it is also why the contact cut is made with a plane that is
tilted 0.6 deg in this frame rather than a flat one.

Bay opening
-----------
The bay is recessed INTO the body: its sill follows ``SEC.surfaces(x, y)``, so
the door hinge lines and the wall feet sit on the real skin.  The skin CUT
itself belongs to the airframe module -- this module publishes the opening as
:data:`BAY_OPENING` and :func:`bay_cutter` so the cut and the bay cannot drift
apart.
"""

from __future__ import annotations

import math

from build123d import (Align, Axis, Box, Compound, Cylinder, Face, Location,
                       Plane, Polyline, Pos, Sphere, Vector, Wire, extrude,
                       revolve)

from f14_parts import geometry as G
from f14_parts import sections as SEC
from f14_parts.airframe import stance
from f14_parts import palette as P
from f14_parts.context import group

# ---------------------------------------------------------------------------
# frame helpers
# ---------------------------------------------------------------------------

_T = math.radians(G.GROUND_PITCH)


def ground_z(x):
    """Waterline-frame z at station ``x`` that lands on world Z=0 after stance.

    stance() rotates about +Y by GROUND_PITCH and then lifts by WATERLINE:
        z_world = -x*sin(t) + z*cos(t) + WATERLINE
    Solving that for z_world = 0 is the whole reason the wheels touch the deck
    to the millimetre rather than to the nearest guess.
    """
    return (x * math.sin(_T) - G.WATERLINE) / math.cos(_T)


def _ground_normal():
    """World +Z expressed in the waterline frame."""
    return Vector(-math.sin(_T), 0.0, math.cos(_T))


def _skin_z(x, y):
    """Belly (bottom) height of the airframe skin at (x, y)."""
    _, b = SEC.surfaces(x, y)
    return -470.0 if b is None else b


# ---------------------------------------------------------------------------
# primitive helpers
# ---------------------------------------------------------------------------


def _rod(p0, p1, r):
    """Solid cylinder from p0 to p1."""
    v = Vector(*p1) - Vector(*p0)
    return (Plane(origin=Vector(*p0), z_dir=v)
            * Cylinder(r, v.length, align=(Align.CENTER, Align.CENTER, Align.MIN)))


def _tube(p0, p1, ro, ri):
    """Hollow cylinder; the bore overshoots both ends so no face is coplanar."""
    v = Vector(*p1) - Vector(*p0)
    u = v.normalized()
    outer = (Plane(origin=Vector(*p0), z_dir=v)
             * Cylinder(ro, v.length, align=(Align.CENTER, Align.CENTER, Align.MIN)))
    bore = (Plane(origin=Vector(*p0) - u * 2.0, z_dir=v)
            * Cylinder(ri, v.length + 4.0, align=(Align.CENTER, Align.CENTER, Align.MIN)))
    return outer - bore


def _beam(p0, p1, w, t, x_dir=(0, 1, 0)):
    """Rectangular beam p0->p1; ``w`` across x_dir, ``t`` across the third axis."""
    v = Vector(*p1) - Vector(*p0)
    u = v.normalized()
    xd = Vector(*x_dir)
    xd = xd - u * xd.dot(u)
    if xd.length < 1e-6:
        xd = Vector(1, 0, 0) - u * Vector(1, 0, 0).dot(u)
    return (Plane(origin=Vector(*p0), z_dir=v, x_dir=xd)
            * Box(w, t, v.length, align=(Align.CENTER, Align.CENTER, Align.MIN)))


def _blk(c, dx, dy, dz):
    return Pos(*c) * Box(dx, dy, dz)


def _pipe(pts, r):
    """A plumbing run: straight segments with spherical knuckles.

    Far more robust than sweeping a section along a spline with tight bends.
    The pieces are gathered with ``Compound(list)`` rather than fused: they are
    ONE occurrence either way, the overlaps are interior, and fusing every run
    cost ~30 s of build time to produce the same image.
    """
    segs = [_rod(pts[i], pts[i + 1], r) for i in range(len(pts) - 1)]
    knuckles = [Pos(*p) * Sphere(r) for p in pts[1:-1]]
    return Compound(segs + knuckles)


def _plate_face(pts):
    """Closed planar face through 3D points."""
    poly = Polyline(*[Vector(*p) for p in pts], close=True)
    return Face(Wire(poly.edges()))


def _rot_x(pt, hy, hz, deg):
    """Rotate a point about a hinge line parallel to +X through (hy, hz)."""
    a = math.radians(deg)
    dy, dz = pt[1] - hy, pt[2] - hz
    return (pt[0], hy + dy * math.cos(a) - dz * math.sin(a),
            hz + dy * math.sin(a) + dz * math.cos(a))


def _hinge_loc(hy, hz, deg):
    """Location that rotates a shape about the hinge line at (hy, hz)."""
    return (Location((0, hy, hz)) * Location((0, 0, 0), (deg, 0, 0))
            * Location((0, -hy, -hz)))


def _half_space(p, n, side):
    """Vertical-plane cutter: removes everything on the +n side of the plane
    through ``p``.  ``n`` is given for the port side and mirrored by ``side``."""
    nn = Vector(n[0], side * n[1], 0.0).normalized()
    return (Plane(origin=Vector(p[0], side * p[1], 0.0), z_dir=nn)
            * Box(3000, 3000, 2000, align=(Align.CENTER, Align.CENTER, Align.MIN)))


# ---------------------------------------------------------------------------
# stations
# ---------------------------------------------------------------------------

X_AXLE = G.X_NOSE_GEAR                 # 3.120 m
RAKE = -4.0                            # deg; negative == leg top FORWARD
R_TYRE = G.NOSE_TIRE_D / 2.0           # 280
W_TYRE = G.NOSE_TIRE_W                 # 170
Y_WHEEL = G.NOSE_TRACK / 2.0           # 235
TYRE_FLAT = 30.0                       # static deflection at the contact patch

Z_GROUND = ground_z(X_AXLE)            # -1812.77
Z_AXLE = Z_GROUND + R_TYRE - TYRE_FLAT

_RR = math.radians(RAKE)
_UX, _UZ = math.sin(_RR), math.cos(_RR)          # "up the leg"
_FX, _FZ = -math.cos(_RR), math.sin(_RR)         # "forward", perpendicular


def LP(s, f=0.0, y=0.0):
    """Point on the leg: ``s`` up the leg axis from the axle, ``f`` forward."""
    return (X_AXLE + s * _UX + f * _FX, y, Z_AXLE + s * _UZ + f * _FZ)


S_FORK_TOP = 180.0
S_CYL_BOT = 410.0                      # gland: 230 mm of chrome showing
S_TRUNNION = 1400.0

R_CYL = 88.0
R_PISTON = 64.0

# --- bay ------------------------------------------------------------------
# The forward bulkhead is set by the LEG, not by taste: the leg rakes forward
# going up, so the steering actuators and their horn -- the highest, most
# forward things on the leg -- would otherwise end up buried in the nose
# structure ahead of the well.
BAY_X0 = 2820.0
BAY_X1 = 4300.0
BAY_Y = 340.0                          # opening half-width
BAY_ROOF = -20.0                       # roof underside, waterline-relative

BAY_OPENING = {
    "x0": BAY_X0, "x1": BAY_X1, "half_width": BAY_Y,
    "roof_z": BAY_ROOF, "corner_r": 90.0,
}

DOOR_SPLIT = 3510.0                    # forward doors / aft doors
DOOR_GAP = 18.0                        # centreline gap between the door pairs
DOOR_T = 10.0
DOOR_OPEN_FWD = 100.0                  # deg
DOOR_OPEN_AFT = 95.0


def bay_cutter():
    """The nose-gear well opening, for the AIRFRAME module to subtract.

    Published here so the skin cut and the bay it exposes cannot drift apart.
    The cutter overshoots the skin by 400 mm below and reaches the bay roof
    above, and its plan corners are relieved so the opening is not a square
    hole in a stressed skin.
    """
    r = BAY_OPENING["corner_r"]
    x0, x1, w = BAY_X0, BAY_X1, BAY_Y
    plan = [
        (x0 + r, -w), (x1 - r, -w), (x1, -w + r), (x1, w - r),
        (x1 - r, w), (x0 + r, w), (x0, w - r), (x0, -w + r),
    ]
    z0, z1 = -900.0, BAY_ROOF + 4.0
    face = _plate_face([(x, y, z0) for x, y in plan])
    return extrude(face, z1 - z0, dir=(0, 0, 1))


# ---------------------------------------------------------------------------
# wheels
# ---------------------------------------------------------------------------


def _ground_cutter():
    """Half-space below the deck, in the waterline frame.

    The deck is not horizontal in THIS frame -- stance() rotates the model 0.6
    deg -- so the contact patch is cut on the tilted plane.  Cutting on a flat
    z-plane instead would leave one tyre edge 2.4 mm proud of the deck.
    """
    pl = Plane(origin=Vector(X_AXLE, 0, Z_GROUND), z_dir=_ground_normal())
    return pl * Box(1600, 1600, 1400, align=(Align.CENTER, Align.CENTER, Align.MAX))


def _crown(y):
    """Tread radius across the section -- a gentle crown, not a flat band."""
    return 280.0 - 0.0009 * y * y


def _tyre_profile():
    """(radius, axial) section of one tyre, grooves included.

    The four circumferential grooves are NOTCHES IN THE PROFILE, not boolean
    cuts.  Revolving eight extra points is free; subtracting four revolved
    groove rings from the fused tyre cost 88 seconds of the build for exactly
    the same picture.
    """
    gw, gd = 6.5, 12.0
    wall = [(143.0, -74.0), (152.0, -80.0), (168.0, -83.5), (200.0, -85.0),
            (232.0, -84.0), (252.0, -78.0), (264.0, -70.0), (272.0, -65.5)]
    tread = [(_crown(-62.0), -62.0)]
    for g in (-48.0, -16.0, 16.0, 48.0):
        tread.append((_crown(g - gw), g - gw))
        tread.append((_crown(g - gw) - gd, g - gw))
        tread.append((_crown(g + gw) - gd, g + gw))
        tread.append((_crown(g + gw), g + gw))
    tread.append((_crown(62.0), 62.0))
    return wall + tread + [(r, -y) for r, y in reversed(wall)]


_TYRE_PROFILE = _tyre_profile()

_RIM_PROFILE = [
    (0.0, -80.0), (54.0, -80.0), (62.0, -90.0), (104.0, -91.0),
    (132.0, -88.0), (150.0, -84.0), (161.0, -75.0), (164.0, -62.0),
    (156.0, -54.0), (150.0, -49.0), (150.0, 49.0), (156.0, 54.0),
    (164.0, 62.0), (161.0, 75.0), (150.0, 84.0), (132.0, 88.0),
    (104.0, 91.0), (62.0, 90.0), (54.0, 80.0), (0.0, 80.0),
]


def _revolved(profile, axis):
    """Revolve a (radius, axial) profile.  The profile lives in the XY plane
    with x = radius, y = axial, so Axis.Y sweeps it into a wheel."""
    face = _plate_face([(r, a, 0.0) for r, a in profile])
    return revolve(face, axis)


def _tyre_solid():
    """One loaded tyre, axle along Y, centred on the axle.

    The flat is not a cut alone: a real parked tyre bulges sideways where it is
    squashed, and that bulge is what makes the aircraft look like it has weight
    on it.  A prolate spheroid is fused in at the contact patch and the whole
    thing is then cut on the deck plane, so the patch comes out flat AND wider
    than the tread.
    """
    tyre = _revolved(_TYRE_PROFILE, Axis.Y)
    a, b = 142.0, 101.0
    n = 33
    half = [(a * math.cos(math.pi * i / (n - 1)),
             b * math.sin(math.pi * i / (n - 1)), 0.0) for i in range(n)]
    bulge = revolve(_plate_face(half), Axis.X)
    z_contact = -(R_TYRE - TYRE_FLAT)
    return tyre + (Pos(0, 0, z_contact + 30.0) * bulge)


def _rim_solid():
    rim = _revolved(_RIM_PROFILE, Axis.Y)
    bore = Plane.XZ * Cylinder(42.0, 260.0)
    pockets = []
    for i in range(5):
        a = math.radians(90.0 + 72.0 * i)
        for sgn in (1, -1):
            pockets.append(Pos(92.0 * math.cos(a), sgn * 82.0, 92.0 * math.sin(a))
                           * (Plane.XZ * Cylinder(30.0, 40.0)))
    return rim - ([bore] + pockets)


def _wheels():
    cut = _ground_cutter()
    out = []
    for side in (1, -1):
        tag = "port" if side > 0 else "stbd"
        base = Location((X_AXLE, side * Y_WHEEL, Z_AXLE))
        tyre = (base * _tyre_solid()) - cut
        out.append(P.style(tyre, f"nose_tyre:{tag}", P.TYRE))
        rim = (base * _rim_solid()) - cut
        out.append(P.style(rim, f"nose_wheel_rim:{tag}", P.ALUMINIUM))
        cap = base * (Pos(0, side * 92.0, 0) * (Plane.XZ * Cylinder(50.0, 26.0)))
        out.append(P.style(cap, f"nose_hub_cap:{tag}", P.ALUM_DARK))
        # inflation valve, poking through the outer wheel face
        stem = base * (Pos(0, side * 100.0, 118.0) * (Plane.XZ * Cylinder(9.0, 46.0)))
        out.append(P.style(stem, f"nose_valve_stem:{tag}", P.BRASS))

    axle = _rod((X_AXLE, -(Y_WHEEL + 110.0), Z_AXLE),
                (X_AXLE, Y_WHEEL + 110.0, Z_AXLE), 40.0)
    out.append(P.style(axle, "nose_axle:centre", P.STEEL_DARK))
    for side in (1, -1):
        tag = "port" if side > 0 else "stbd"
        nut = _rod((X_AXLE, side * (Y_WHEEL + 78.0), Z_AXLE),
                   (X_AXLE, side * (Y_WHEEL + 112.0), Z_AXLE), 62.0)
        out.append(P.style(nut, f"nose_axle_nut:{tag}", P.ALUM_DARK))
    return out


# ---------------------------------------------------------------------------
# the leg
# ---------------------------------------------------------------------------


def _oleo():
    out = []

    # --- trunnion -------------------------------------------------------
    tr = _rod(LP(S_TRUNNION, 0, -215.0), LP(S_TRUNNION, 0, 215.0), 52.0)
    out.append(P.style(tr, "nose_trunnion_shaft:centre", P.STEEL_DARK))
    for side in (1, -1):
        tag = "port" if side > 0 else "stbd"
        brg = _tube(LP(S_TRUNNION, 0, side * 120.0), LP(S_TRUNNION, 0, side * 195.0),
                    88.0, 53.0)
        out.append(P.style(brg, f"nose_trunnion_bearing:{tag}", P.ALUM_DARK))

    # --- outer cylinder -------------------------------------------------
    body = _rod(LP(S_CYL_BOT - 20.0), LP(S_TRUNNION + 26.0), R_CYL)
    yoke = _rod(LP(S_TRUNNION - 118.0, 0, -112.0), LP(S_TRUNNION - 118.0, 0, 112.0),
                98.0)
    cheek = _blk(LP(S_TRUNNION - 56.0), 168.0, 224.0, 152.0)
    out.append(P.style(body + [yoke, cheek], "nose_oleo_cylinder:centre",
                       P.GEAR_WHITE))

    gland = _tube(LP(S_CYL_BOT - 40.0), LP(S_CYL_BOT + 20.0), 103.0, 58.0)
    out.append(P.style(gland, "nose_oleo_gland:centre", P.ALUM_DARK))
    scraper = _tube(LP(S_CYL_BOT - 58.0), LP(S_CYL_BOT - 40.0), 78.0, 56.0)
    out.append(P.style(scraper, "nose_oleo_scraper:centre", P.STEEL_DARK))

    # charging valve and the two hydraulic unions on the cylinder flank
    out.append(P.style(_rod(LP(1050.0, -20.0, 86.0), LP(1050.0, -20.0, 128.0), 22.0),
                       "nose_oleo_charge_valve:port", P.BRASS))
    for s in (700.0, 880.0):
        out.append(P.style(_rod(LP(s, 10.0, -86.0), LP(s, 10.0, -126.0), 19.0),
                           f"nose_oleo_union:s{int(s)}", P.ALUM_DARK))

    collar = _tube(LP(1120.0), LP(1300.0), 114.0, R_CYL - 4.0)
    out.append(P.style(collar, "nose_steering_collar:centre", P.GEAR_WHITE))

    # --- polished piston ------------------------------------------------
    piston = _rod(LP(120.0), LP(S_CYL_BOT - 6.0), R_PISTON)
    out.append(P.style(piston, "nose_oleo_piston:centre", P.OLEO_CHROME))

    # --- lower fork -----------------------------------------------------
    fork_head = _blk(LP(120.0), 190.0, 250.0, 150.0)
    out.append(P.style(fork_head, "nose_fork_head:centre", P.GEAR_WHITE))
    for side in (1, -1):
        tag = "port" if side > 0 else "stbd"
        arm = _beam(LP(150.0, 0, side * 108.0), LP(-6.0, 0, side * 108.0), 128.0, 62.0)
        boss = _rod(LP(0.0, 0, side * 74.0), LP(0.0, 0, side * 132.0), 66.0)
        out.append(P.style(arm + boss, f"nose_fork_arm:{tag}", P.GEAR_WHITE))
    # tie-down / tow ring on the fork
    ring = _tube(LP(190.0, -70.0, 128.0), LP(190.0, -70.0, 158.0), 46.0, 26.0)
    out.append(P.style(ring, "nose_tiedown_ring:port", P.STEEL_DARK))

    return out


def _torque_links():
    """Scissors on the AFT face, plus the shimmy damper hung off the knee."""
    out = []
    a = LP(455.0, -95.0)
    k = LP(320.0, -238.0)
    b = LP(185.0, -95.0)

    upper = _beam(a, k, 62.0, 42.0)
    out.append(P.style(upper, "nose_torque_link_upper:centre", P.GEAR_WHITE))
    for side in (1, -1):
        tag = "port" if side > 0 else "stbd"
        lo = _beam((k[0], side * 48.0, k[2]), (b[0], side * 48.0, b[2]), 56.0, 22.0)
        out.append(P.style(lo, f"nose_torque_link_lower:{tag}", P.GEAR_WHITE))

    for pt, name in ((a, "upper"), (k, "knee"), (b, "lower")):
        pin = _rod((pt[0], -76.0, pt[2]), (pt[0], 76.0, pt[2]), 17.0)
        out.append(P.style(pin, f"nose_torque_pin:{name}", P.STEEL_DARK))

    # shimmy damper: body on the aft face, rod down to the scissor knee
    d0, d1 = LP(600.0, -222.0), LP(410.0, -244.0)
    out.append(P.style(_rod(d0, d1, 34.0), "nose_shimmy_damper:body", P.GEAR_WHITE))
    out.append(P.style(_rod(d1, LP(336.0, -240.0), 15.0),
                       "nose_shimmy_damper:rod", P.OLEO_CHROME))
    out.append(P.style(_beam(LP(600.0, -222.0), LP(612.0, -100.0), 54.0, 26.0),
                       "nose_shimmy_damper:mount", P.ALUM_DARK))
    return out


def _drag_brace():
    """Two-piece brace folding AFT, bifurcated at the bottom so the centreline
    stays clear for the launch bar and the light cluster."""
    out = []
    fitting = (3540.0, 0.0, -110.0)
    knee = (3320.0, 0.0, -334.0)

    out.append(P.style(_beam(fitting, knee, 92.0, 54.0),
                       "nose_drag_brace_upper:centre", P.GEAR_WHITE))
    for side in (1, -1):
        tag = "port" if side > 0 else "stbd"
        lug = LP(1010.0, -95.0, side * 108.0)
        out.append(P.style(_beam(knee, lug, 62.0, 40.0),
                           f"nose_drag_brace_lower:{tag}", P.GEAR_WHITE))
        out.append(P.style(_rod((lug[0], side * 78.0, lug[2]),
                                (lug[0], side * 150.0, lug[2]), 26.0),
                           f"nose_drag_brace_pin:{tag}", P.STEEL_DARK))
    out.append(P.style(_rod((knee[0], -96.0, knee[2]), (knee[0], 96.0, knee[2]), 22.0),
                       "nose_drag_brace_knee_pin:centre", P.STEEL_DARK))
    out.append(P.style(_blk((fitting[0] + 20.0, 0.0, fitting[2] + 40.0),
                            120.0, 150.0, 130.0),
                       "nose_drag_brace_fitting:centre", P.ALUM_DARK))

    # over-centre downlock link and its spring
    lock_lug = LP(1250.0, -95.0)
    out.append(P.style(_beam(knee, lock_lug, 44.0, 26.0),
                       "nose_downlock_link:centre", P.GEAR_WHITE))
    out.append(P.style(_rod((knee[0] - 20.0, 62.0, knee[2] + 40.0),
                            (lock_lug[0] + 10.0, 62.0, lock_lug[2] + 26.0), 11.0),
                       "nose_downlock_spring:port", P.STEEL_DARK))
    return out


def _actuators():
    """Retraction actuator (aft, one side) and the twin steering actuators."""
    out = []
    base = (2962.0, -214.0, -74.0)
    mid = LP(1150.0, -150.0, -172.0)
    rod_end = LP(1092.0, -168.0, -178.0)
    out.append(P.style(_blk((base[0] + 16.0, base[1], base[2]), 110.0, 96.0, 96.0),
                       "nose_retract_actuator:base", P.ALUM_DARK))
    out.append(P.style(_rod(base, mid, 44.0),
                       "nose_retract_actuator:body", P.GEAR_WHITE))
    out.append(P.style(_rod(mid, rod_end, 23.0),
                       "nose_retract_actuator:rod", P.OLEO_CHROME))
    out.append(P.style(_blk(rod_end, 90.0, 70.0, 74.0),
                       "nose_retract_actuator:lug", P.ALUM_DARK))

    for side in (1, -1):
        tag = "port" if side > 0 else "stbd"
        top = LP(1290.0, 86.0, side * 116.0)
        low = LP(1150.0, 122.0, side * 116.0)
        end = LP(1092.0, 140.0, side * 116.0)
        out.append(P.style(_rod(top, low, 25.0),
                           f"nose_steer_actuator_body:{tag}", P.GEAR_WHITE))
        out.append(P.style(_rod(low, end, 13.0),
                           f"nose_steer_actuator_rod:{tag}", P.OLEO_CHROME))
        out.append(P.style(_blk(top, 74.0, 56.0, 60.0),
                           f"nose_steer_actuator_mount:{tag}", P.ALUM_DARK))
    horn = _blk(LP(1086.0, 142.0), 74.0, 258.0, 58.0)
    out.append(P.style(horn, "nose_steering_horn:centre", P.ALUM_DARK))

    # hydraulic supply down the leg, clipped to the aft face
    for side, name in ((1, "port"), (-1, "stbd")):
        pts = [LP(1330.0, -60.0, side * 96.0), LP(1120.0, -108.0, side * 104.0),
               LP(820.0, -118.0, side * 100.0), LP(560.0, -112.0, side * 92.0),
               LP(430.0, -96.0, side * 78.0)]
        out.append(P.style(_pipe(pts, 13.0), f"nose_leg_hydraulic:{name}", P.HYDRAULIC))
    for s in (620.0, 900.0, 1180.0):
        clip = _blk(LP(s, -110.0), 30.0, 250.0, 34.0)
        out.append(P.style(clip, f"nose_leg_clamp:s{int(s)}", P.ALUM_DARK))
    return out


def _launch_bar():
    """Catapult launch bar, RETRACTED: swung up against the front of the leg.

    Stow angle matters.  Any higher and the bar hides the approach-light
    cluster, which is the one detail on this leg that says NAVY at a glance; on
    the aircraft the bar stows below the lights for exactly that reason.
    """
    out = []
    pivot = LP(60.0, 100.0)
    tilt = math.radians(30.0)
    dx = _UX * math.cos(tilt) - _UZ * math.sin(tilt)
    dz = _UX * math.sin(tilt) + _UZ * math.cos(tilt)
    length = 560.0
    tip = (pivot[0] + dx * length, 0.0, pivot[2] + dz * length)
    mid = (pivot[0] + dx * length * 0.58, 0.0, pivot[2] + dz * length * 0.58)

    neck = (pivot[0] + dx * (length - 130.0), 0.0, pivot[2] + dz * (length - 130.0))
    out.append(P.style(_beam(pivot, neck, 112.0, 72.0),
                       "nose_launch_bar:shank", P.ALUMINIUM))
    out.append(P.style(_beam(neck, tip, 148.0, 88.0),
                       "nose_launch_bar:head", P.STEEL_DARK))
    # the transverse roller that rides the shuttle track
    roller = _rod((tip[0], -104.0, tip[2]), (tip[0], 104.0, tip[2]), 44.0)
    out.append(P.style(roller, "nose_launch_bar:roller", P.STEEL_DARK))
    for side in (1, -1):
        tag = "port" if side > 0 else "stbd"
        cap = _rod((tip[0], side * 100.0, tip[2]), (tip[0], side * 122.0, tip[2]), 30.0)
        out.append(P.style(cap, f"nose_launch_bar:roller_cap_{tag}", P.ALUM_DARK))
    for side in (1, -1):
        tag = "port" if side > 0 else "stbd"
        out.append(P.style(_blk((pivot[0], side * 96.0, pivot[2]), 160.0, 48.0, 140.0),
                           f"nose_launch_bar_lug:{tag}", P.GEAR_WHITE))
    out.append(P.style(_rod((pivot[0], -114.0, pivot[2]),
                            (pivot[0], 114.0, pivot[2]), 22.0),
                       "nose_launch_bar_pin:centre", P.STEEL_DARK))

    # hold-down actuator: leg front -> bar mid-span
    act_top = LP(520.0, 122.0, 120.0)
    act_mid = ((act_top[0] + mid[0]) * 0.5 + 10.0, 120.0,
               (act_top[2] + mid[2]) * 0.5)
    out.append(P.style(_rod(act_top, act_mid, 26.0),
                       "nose_launch_bar_actuator:body", P.GEAR_WHITE))
    out.append(P.style(_rod(act_mid, (mid[0], 120.0, mid[2]), 13.0),
                       "nose_launch_bar_actuator:rod", P.OLEO_CHROME))
    out.append(P.style(_blk(act_top, 70.0, 62.0, 58.0),
                       "nose_launch_bar_actuator:mount", P.ALUM_DARK))
    return out


def _holdback():
    """Holdback fitting on the AFT face at axle height -- what the deck
    holdback bar hooks into while the cat builds thrust."""
    out = []
    root = LP(150.0, -110.0)
    tail = LP(120.0, -290.0)
    out.append(P.style(_beam(root, tail, 150.0, 96.0),
                       "nose_holdback_arm:centre", P.GEAR_WHITE))
    eye = _rod((tail[0], -74.0, tail[2]), (tail[0], 74.0, tail[2]), 62.0)
    bore = _rod((tail[0], -90.0, tail[2]), (tail[0], 90.0, tail[2]), 26.0)
    out.append(P.style(eye - bore, "nose_holdback_eye:centre", P.STEEL_DARK))
    for side in (1, -1):
        tag = "port" if side > 0 else "stbd"
        out.append(P.style(_blk(LP(170.0, -170.0, side * 96.0), 120.0, 34.0, 130.0),
                           f"nose_holdback_gusset:{tag}", P.GEAR_WHITE))
    return out


def _lights():
    """Approach/indexer cluster and the taxi light, both on the leg front.

    The three stacked lenses are the LSO's read on approach: red high, amber on
    speed, green fast.  They are the most recognisably NAVY thing on the whole
    leg, so they are modelled as real lenses in a real housing.
    """
    out = []
    house = _blk(LP(730.0, 134.0), 124.0, 132.0, 268.0)
    out.append(P.style(house, "nose_approach_light:housing", P.ALUM_DARK))
    lenses = (("red", 840.0, P.LIGHT_RED), ("amber", 730.0, P.HANDLE_YELLOW),
              ("green", 620.0, P.LIGHT_GREEN))
    for name, s, col in lenses:
        lens = _rod(LP(s, 178.0), LP(s, 208.0), 35.0)
        out.append(P.style(lens, f"nose_approach_lens:{name}", col))
        bezel = _tube(LP(s, 170.0), LP(s, 198.0), 44.0, 34.0)
        out.append(P.style(bezel, f"nose_approach_bezel:{name}", P.STEEL_DARK))

    taxi_can = _tube(LP(1000.0, 118.0), LP(1004.0, 186.0), 58.0, 50.0)
    out.append(P.style(taxi_can, "nose_taxi_light:can", P.ALUM_DARK))
    taxi_back = _rod(LP(998.0, 102.0), LP(1000.0, 126.0), 58.0)
    out.append(P.style(taxi_back, "nose_taxi_light:body", P.GEAR_WHITE))
    taxi_lens = _rod(LP(1002.0, 164.0), LP(1004.0, 186.0), 50.0)
    out.append(P.style(taxi_lens, "nose_taxi_light:lens", P.LIGHT_WHITE))
    out.append(P.style(_blk(LP(1000.0, 94.0), 130.0, 140.0, 38.0),
                       "nose_taxi_light:bracket", P.GEAR_WHITE))
    return out


# ---------------------------------------------------------------------------
# the bay
# ---------------------------------------------------------------------------


def _bay_shell():
    """Roof, walls and bulkheads.  The wall feet and bulkhead feet FOLLOW the
    belly, so the sill is the skin line rather than a flat guess."""
    out = []
    xs = [BAY_X0 + (BAY_X1 - BAY_X0) * i / 12.0 for i in range(13)]

    roof = _blk(((BAY_X0 + BAY_X1) / 2.0, 0.0, BAY_ROOF + 16.0),
                BAY_X1 - BAY_X0, 2 * BAY_Y + 60.0, 32.0)
    out.append(P.style(roof, "nose_bay_roof:centre", P.BAY_GREEN))

    for side in (1, -1):
        tag = "port" if side > 0 else "stbd"
        yw = side * BAY_Y
        bottom = [(x, yw, _skin_z(x, abs(yw)) + 2.0) for x in xs]
        top = [(x, yw, BAY_ROOF) for x in reversed(xs)]
        wall = extrude(_plate_face(bottom + top), 12.0, dir=(0, 1, 0), both=True)
        out.append(P.style(wall, f"nose_bay_wall:{tag}", P.BAY_GREEN))
        # sill rail along the door line
        rail = [(x, yw, _skin_z(x, abs(yw)) + 26.0) for x in xs]
        out.append(P.style(_pipe(rail, 17.0), f"nose_bay_sill:{tag}", P.ALUM_DARK))

    ys = [-BAY_Y + 2 * BAY_Y * i / 8.0 for i in range(9)]
    for x, tag in ((BAY_X0, "fwd"), (BAY_X1, "aft")):
        bottom = [(x, y, _skin_z(x, y) + 2.0) for y in ys]
        top = [(x, y, BAY_ROOF) for y in reversed(ys)]
        bulk = extrude(_plate_face(bottom + top), 13.0, dir=(1, 0, 0), both=True)
        out.append(P.style(bulk, f"nose_bay_bulkhead:{tag}", P.BAY_GREEN))
    return out


def _bay_structure():
    """Ring frames, stringers and the trunnion carry-through.

    An empty box reads as a box.  What makes a well look like a well is the
    frames standing proud of the roof skin with the plumbing threaded past
    them, so the frames go in first and everything else is routed around them.
    """
    out = []
    frames = (2985.0, 3175.0, 3350.0, 3540.0, 3730.0, 3930.0, 4140.0)
    for i, x in enumerate(frames):
        web = _blk((x, 0.0, BAY_ROOF - 34.0), 22.0, 2 * BAY_Y - 8.0, 68.0)
        cap = _blk((x, 0.0, BAY_ROOF - 72.0), 54.0, 2 * BAY_Y - 8.0, 18.0)
        col = P.BAY_GREEN if i % 2 == 0 else P.ALUM_DARK
        out.append(P.style(web + cap, f"nose_bay_frame:f{i + 1}", col))
        for side in (1, -1):
            tag = "port" if side > 0 else "stbd"
            zf = _skin_z(x, BAY_Y) + 2.0
            rib = _blk((x, side * (BAY_Y - 20.0), 0.5 * (zf + BAY_ROOF)),
                       20.0, 30.0, BAY_ROOF - zf)
            out.append(P.style(rib, f"nose_bay_wall_rib:f{i + 1}_{tag}", P.BAY_GREEN))

    for side in (1, -1):
        tag = "port" if side > 0 else "stbd"
        for j, y in enumerate((0.36, 0.74)):
            st = _blk(((BAY_X0 + BAY_X1) / 2.0, side * BAY_Y * y, BAY_ROOF - 16.0),
                      BAY_X1 - BAY_X0 - 40.0, 34.0, 30.0)
            out.append(P.style(st, f"nose_bay_stringer:{tag}{j + 1}", P.BAY_GREEN))

    # trunnion carry-through: two deep webs straddling the leg
    for side in (1, -1):
        tag = "port" if side > 0 else "stbd"
        web = _blk((LP(S_TRUNNION)[0], side * 208.0, -100.0), 300.0, 26.0, 190.0)
        out.append(P.style(web, f"nose_trunnion_web:{tag}", P.BAY_GREEN))
        pad = _blk((LP(S_TRUNNION)[0], side * 208.0, LP(S_TRUNNION)[2]),
                   190.0, 46.0, 130.0)
        out.append(P.style(pad, f"nose_trunnion_pad:{tag}", P.ALUMINIUM))
        gus = _beam((LP(S_TRUNNION)[0], side * 208.0, -46.0),
                    (LP(S_TRUNNION)[0] + 240.0, side * 300.0, -46.0), 90.0, 18.0)
        out.append(P.style(gus, f"nose_trunnion_gusset:{tag}", P.BAY_GREEN))
    return out


def _bay_systems():
    """Plumbing, looms, connectors and the odd black box.

    The rubric line is 'gear bays are deep and full'; this is the 'full'.
    """
    out = []
    z = BAY_ROOF - 76.0

    runs = [
        ("hyd_pressure", P.HYDRAULIC, 15.0,
         [(BAY_X0 + 40, 250.0, z + 20), (3120.0, 268.0, z),
          (3480.0, 250.0, z + 6), (3860.0, 232.0, z - 6), (BAY_X1 - 40, 226.0, z)]),
        ("hyd_return", P.ALUMINIUM, 13.0,
         [(BAY_X0 + 40, 296.0, z + 26), (3200.0, 302.0, z + 8),
          (3620.0, 292.0, z + 2), (BAY_X1 - 40, 280.0, z + 10)]),
        ("hyd_utility", P.HYDRAULIC, 14.0,
         [(BAY_X0 + 60, -244.0, z + 14), (3260.0, -272.0, z - 4),
          (3700.0, -256.0, z + 4), (BAY_X1 - 40, -238.0, z + 12)]),
        ("brake_air", P.ALUM_DARK, 10.0,
         [(3000.0, -300.0, z + 34), (3400.0, -308.0, z + 16),
          (3900.0, -296.0, z + 24), (BAY_X1 - 60, -286.0, z + 30)]),
        ("leg_feed", P.HYDRAULIC, 12.0,
         [(3060.0, 210.0, z + 40), (3140.0, 150.0, z + 4), (3120.0, 96.0, -240.0),
          (3180.0, 88.0, -360.0)]),
    ]
    for name, col, r, pts in runs:
        out.append(P.style(_pipe(pts, r), f"nose_bay_pipe:{name}", col))

    looms = [
        ("loom_main", 21.0,
         [(BAY_X0 + 30, 200.0, BAY_ROOF - 42.0), (3220.0, 212.0, BAY_ROOF - 54.0),
          (3640.0, 196.0, BAY_ROOF - 46.0), (BAY_X1 - 30, 184.0, BAY_ROOF - 52.0)]),
        ("loom_gear", 17.0,
         [(BAY_X0 + 30, -186.0, BAY_ROOF - 48.0), (3300.0, -200.0, BAY_ROOF - 60.0),
          (3800.0, -182.0, BAY_ROOF - 48.0), (BAY_X1 - 30, -172.0, BAY_ROOF - 54.0)]),
        ("loom_light", 12.0,
         [(3080.0, 306.0, z + 44), (3300.0, 316.0, z + 26), (3700.0, 306.0, z + 34)]),
    ]
    for name, r, pts in looms:
        out.append(P.style(_pipe(pts, r), f"nose_bay_loom:{name}", P.WIRE_LOOM))

    boxes = [
        ("junction", (3410.0, 268.0, BAY_ROOF - 68.0), (150.0, 96.0, 90.0), P.ALUM_DARK),
        ("relay", (3860.0, -258.0, BAY_ROOF - 64.0), (170.0, 110.0, 82.0), P.STEEL_DARK),
        ("valve", (3230.0, -286.0, BAY_ROOF - 86.0), (120.0, 84.0, 96.0), P.ALUMINIUM),
        ("manifold", (2960.0, 250.0, BAY_ROOF - 92.0), (160.0, 110.0, 84.0), P.ALUMINIUM),
        ("prox_switch", (3050.0, 244.0, BAY_ROOF - 100.0), (66.0, 54.0, 60.0), P.STEEL_DARK),
        ("downlock_sw", (3300.0, 130.0, BAY_ROOF - 96.0), (74.0, 58.0, 56.0), P.STEEL_DARK),
    ]
    for name, c, d, col in boxes:
        out.append(P.style(_blk(c, *d), f"nose_bay_box:{name}", col))

    acc = _rod((4060.0, 190.0, BAY_ROOF - 94.0), (4060.0, -60.0, BAY_ROOF - 94.0), 62.0)
    out.append(P.style(acc, "nose_bay_accumulator:centre", P.ALUMINIUM))
    out.append(P.style(_rod((4060.0, -60.0, BAY_ROOF - 94.0),
                            (4060.0, -96.0, BAY_ROOF - 94.0), 30.0),
                       "nose_bay_accumulator:head", P.ALUM_DARK))

    # clamps that actually straddle the runs they hold
    for i, x in enumerate((3060.0, 3300.0, 3560.0, 3820.0, 4060.0)):
        out.append(P.style(_blk((x, 258.0, z + 12.0), 40.0, 120.0, 44.0),
                           f"nose_bay_clamp:port{i + 1}", P.ALUM_DARK))
        out.append(P.style(_blk((x, -262.0, z + 14.0), 40.0, 110.0, 44.0),
                           f"nose_bay_clamp:stbd{i + 1}", P.ALUM_DARK))
        out.append(P.style(_blk((x, 200.0, BAY_ROOF - 34.0), 34.0, 74.0, 40.0),
                           f"nose_bay_loom_clip:port{i + 1}", P.ALUM_DARK))
        out.append(P.style(_blk((x, -190.0, BAY_ROOF - 38.0), 34.0, 68.0, 40.0),
                           f"nose_bay_loom_clip:stbd{i + 1}", P.ALUM_DARK))

    plate = _blk((3700.0, 322.0, BAY_ROOF - 112.0), 150.0, 4.0, 70.0)
    out.append(P.style(plate, "nose_bay_placard:port", P.LIGHT_WHITE))
    plate2 = _blk((3160.0, -322.0, BAY_ROOF - 116.0), 120.0, 4.0, 60.0)
    out.append(P.style(plate2, "nose_bay_placard:stbd", P.STENCIL))
    return out


# ---------------------------------------------------------------------------
# doors
# ---------------------------------------------------------------------------


def _door_band(x0, x1, y0, y1, thick, x_ref, side, dz=0.0, n=13):
    """A plate that follows the belly curvature across y, extruded along x."""
    ys = [y0 + (y1 - y0) * i / (n - 1) for i in range(n)]
    outer = [(x0, side * y, _skin_z(x_ref, y) + dz) for y in ys]
    inner = [(x0, side * y, _skin_z(x_ref, y) + dz + thick) for y in reversed(ys)]
    return extrude(_plate_face(outer + inner), x1 - x0, dir=(1, 0, 0))


def _one_door(side, x0, x1, name, open_deg, bevel):
    """One gear-bay door, hinged outboard and swung down.

    The inner face is the whole point: an open door that is a blank slab reads
    as cardboard.  So the door is an outer skin plus a white inner liner, with
    ribbing, hinge fittings, an actuator, wiring and placards on the inside --
    and the outer skin carries its own scribed panel lines, because that face
    is the one you see from beside the aircraft.
    """
    tag = "port" if side > 0 else "stbd"
    x_ref = 0.5 * (x0 + x1)
    y_in, y_out = DOOR_GAP, BAY_Y - 2.0
    hz = _skin_z(x_ref, y_out)
    hy = side * y_out
    loc = _hinge_loc(hy, hz, side * open_deg)

    # corner relief so the doors are not four identical rectangles
    wedges = []
    if bevel == "fwd":
        wedges.append(_half_space((x0 + 88.0, y_in + 72.0), (-145.0, -175.0), side))
    else:
        wedges.append(_half_space((x1 - 88.0, y_in + 72.0), (145.0, -175.0), side))

    panels = []

    grooves = [_door_band(x0 + (x1 - x0) * f - 5, x0 + (x1 - x0) * f + 5,
                          y_in + 8, y_out - 6, 15.0, x_ref, side, dz=-7.5)
               for f in (0.34, 0.68)]
    skin = _door_band(x0, x1, y_in, y_out, DOOR_T, x_ref, side) - grooves
    panels.append((skin, f"nose_door_skin:{name}_{tag}", P.GREY_LIGHT))

    liner = _door_band(x0 + 26, x1 - 26, y_in + 22, y_out - 26, 7.0, x_ref, side,
                       dz=DOOR_T)
    panels.append((liner, f"nose_door_liner:{name}_{tag}", P.GEAR_WHITE))

    seal_o = _door_band(x0 + 6, x1 - 6, y_in + 4, y_out - 6, 12.0, x_ref, side,
                        dz=DOOR_T)
    seal_i = _door_band(x0 + 26, x1 - 26, y_in + 22, y_out - 26, 30.0, x_ref, side,
                        dz=DOOR_T - 4.0)
    panels.append((seal_o - seal_i, f"nose_door_seal:{name}_{tag}", P.RUBBER))

    kids = []
    for shape, label, col in panels:
        kids.append(P.style(loc * (shape - wedges), label, col))

    # transverse ribs
    n_rib = 3 if (x1 - x0) < 720 else 4
    for i in range(n_rib):
        xr = x0 + (x1 - x0) * (i + 1) / (n_rib + 1)
        rib = _door_band(xr - 11, xr + 11, y_in + 26, y_out - 28, 44.0, x_ref, side,
                         dz=DOOR_T + 6.0)
        kids.append(P.style(loc * rib, f"nose_door_rib:{name}_{tag}{i + 1}",
                            P.GEAR_WHITE))

    # fore-aft stiffeners
    for j, fy in enumerate((0.36, 0.70)):
        yr = y_in + (y_out - y_in) * fy
        zb = _skin_z(x_ref, yr) + DOOR_T + 6.0
        st = _blk((x_ref + 14.0, side * yr, zb + 22.0), x1 - x0 - 96, 13.0, 44.0)
        kids.append(P.style(loc * st, f"nose_door_stiffener:{name}_{tag}{j + 1}",
                            P.ALUMINIUM))

    # hinges along the outboard edge
    n_h = 3
    for i in range(n_h):
        xh = x0 + (x1 - x0) * (i + 0.5) / n_h
        br = _blk((xh, side * (y_out - 44.0), hz + 50.0), 96.0, 42.0, 100.0)
        kids.append(P.style(loc * br, f"nose_door_hinge:{name}_{tag}{i + 1}",
                            P.ALUMINIUM))
    pin = _rod((x0 + 20, hy, hz + 4.0), (x1 - 20, hy, hz + 4.0), 13.0)
    kids.append(P.style(pin, f"nose_door_hinge_pin:{name}_{tag}", P.STEEL_DARK))

    # fastener rows along the hinge edge and the inboard edge.  Individual
    # rivets are sub-pixel on the whole aircraft but they do read in a part
    # close-up.  They are ADDITIVE domes gathered into ONE un-fused occurrence
    # -- `Compound(list)` (no `children=`) is exactly the collapse-to-one-leaf
    # behaviour wanted here, and it costs no boolean at all; fusing the rows
    # instead added 48 s to the build for no visible difference.
    for j, yr in enumerate((y_out - 20.0, y_in + 14.0)):
        zr = _skin_z(x_ref, yr)
        n_riv = max(6, int((x1 - x0) / 58.0))
        heads = [Pos(x0 + 24 + (x1 - x0 - 48) * i / (n_riv - 1), side * yr, zr)
                 * Sphere(6.5) for i in range(n_riv)]
        kids.append(P.style(loc * Compound(heads),
                            f"nose_door_fasteners:{name}_{tag}{j + 1}", P.PANEL_DARK))

    # placards on the inner face
    for i, (fx, col) in enumerate(((0.30, P.LIGHT_WHITE), (0.66, P.LIGHT_RED))):
        xp = x0 + (x1 - x0) * fx
        yp = y_in + (y_out - y_in) * 0.52
        zp = _skin_z(x_ref, yp) + DOOR_T + 10.0
        pl = _blk((xp, side * yp, zp), 104.0, 64.0, 4.0)
        kids.append(P.style(loc * pl, f"nose_door_placard:{name}_{tag}{i + 1}", col))

    # door wiring, clipped along the inner face to the hinge line
    wy = y_out - 68.0
    wz = _skin_z(x_ref, wy) + DOOR_T + 18.0
    wire = _pipe([(x0 + 46, side * wy, wz), (x_ref, side * (wy - 20), wz + 6),
                  (x1 - 46, side * wy, wz)], 9.0)
    kids.append(P.style(loc * wire, f"nose_door_wire:{name}_{tag}", P.WIRE_LOOM))

    # actuator: bay wall -> a fitting on the door, drawn to the ROTATED fitting
    xa = x0 + (x1 - x0) * 0.32
    ya = y_in + (y_out - y_in) * 0.54
    za = _skin_z(x_ref, ya) + DOOR_T + 46.0
    fit = _blk((xa, side * ya, za - 12.0), 74.0, 60.0, 62.0)
    kids.append(P.style(loc * fit, f"nose_door_act_fitting:{name}_{tag}",
                        P.ALUM_DARK))
    rod_end = _rot_x((xa, side * ya, za), hy, hz, side * open_deg)
    anchor = (xa - 150.0, side * (BAY_Y - 46.0), BAY_ROOF - 96.0)
    knee = (anchor[0] + (rod_end[0] - anchor[0]) * 0.45,
            anchor[1] + (rod_end[1] - anchor[1]) * 0.45,
            anchor[2] + (rod_end[2] - anchor[2]) * 0.45)
    kids.append(P.style(_rod(anchor, knee, 24.0),
                        f"nose_door_actuator_body:{name}_{tag}", P.GEAR_WHITE))
    kids.append(P.style(_rod(knee, rod_end, 12.0),
                        f"nose_door_actuator_rod:{name}_{tag}", P.OLEO_CHROME))
    kids.append(P.style(_blk(anchor, 74.0, 62.0, 62.0),
                        f"nose_door_actuator_mount:{name}_{tag}", P.ALUM_DARK))
    return kids


def _doors():
    out = []
    for side in (1, -1):
        out += _one_door(side, BAY_X0 + 8, DOOR_SPLIT - 10, "fwd",
                         DOOR_OPEN_FWD, "fwd")
        out += _one_door(side, DOOR_SPLIT + 10, BAY_X1 - 8, "aft",
                         DOOR_OPEN_AFT, "aft")
    return out


# ---------------------------------------------------------------------------


def build():
    """The whole nose gear, in world position."""
    kids = []
    kids += _bay_shell()
    kids += _bay_structure()
    kids += _bay_systems()
    kids += _oleo()
    kids += _torque_links()
    kids += _drag_brace()
    kids += _actuators()
    kids += _launch_bar()
    kids += _holdback()
    kids += _lights()
    kids += _wheels()
    kids += _doors()
    return stance(group("nose_gear", kids))


if __name__ == "__main__":
    import time

    t0 = time.time()
    grp = build()
    bb = grp.bounding_box()
    print(f"build {time.time() - t0:6.2f}s   leaves {len(grp.leaves)}")
    print(f"world bbox  x {bb.min.X:9.1f}..{bb.max.X:9.1f}"
          f"  y {bb.min.Y:8.1f}..{bb.max.Y:8.1f}"
          f"  z {bb.min.Z:8.1f}..{bb.max.Z:8.1f}")
