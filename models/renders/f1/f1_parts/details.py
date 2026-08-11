"""Detail furniture — the jewellery that makes the render read as a real car.

THE RULE THIS MODULE NOW OBEYS
------------------------------
Nothing here is bolted onto the car at a right angle, and nothing here floats.
Every item either grows out of a surface whose position was measured off the
module that owns it, or it is not in the model at all. Concretely:

  * MIRRORS — the one item that has to be beautiful. The housing is a real
    teardrop: a round leading edge whose half-width and half-height follow a
    single elliptic growth law to a blunt maximum at the glass, then roll over
    a quarter-ellipse rim. The section is a per-quadrant superellipse, rounder
    outboard than inboard, so the outer edge is genuinely rolled. The stalk is
    NOT a stick meeting a wall: it is a blade stack with a per-station chord
    AND per-station thickness, so it keeps a near-constant chord while its t/c
    doubles at each end — a fillet where it leaves the tub flank, a collar
    where it enters the housing — and wastes to a slim aerofoil in between.
    Housing and stalk are FUSED into one body: there is no joint to hide.
  * SIDE CAMERAS — same construction, one third the size, rooted in the
    cockpit-surround deck flank at x = -1220 (measured: the tub flank is
    y = 385 there, near vertical). They used to sit at y = 150, z = 830, which
    is inside the engine cover and above nothing; that pod is gone.
  * TYRE IR SENSORS — one faired bracket per corner, its root buried in the
    brake-duct drum wall and spread into a fairing, its head swelling into the
    sensor body.
  * PITOT MAST — was a four-tube rake. Now ONE probe on one faired blade mast:
    the critic read the rake as a row of loose fittings, and restraint beats
    quantity.
  * DZUS — one row, five a side, on the floor's outboard mounting line, each
    sunk in a machined recess so only a dish and a flush head show. The engine
    cover row is deleted: it rode `spec.shoulder_at`, which by x = -2400 is
    38 mm OUTBOARD of the cover's own crease, so those heads hung in air — and
    `engine_cover.py` already carries the fasteners for its own panel.
  * TOW EYES AND JACK POINTS — verified against their hosts (nose crease at
    x = 1150 is y = 123.4/z = 232.4; the rear crash structure at x = -3930 is
    hw = 57.6, z = 345..396). The rear jack moved 26 mm forward to clear the
    beam wing leading edge at x = -3960.
  * GPS PUCK — deleted. It sat at (-2400, 0, 505); the engine cover's crown at
    that station is z = 762, so the puck was 257 mm inside the bodywork.

Numbers taken off neighbouring modules are stated as datums below with the
station they were measured at, so a hand-off change is a one-line edit.
"""

from __future__ import annotations

import math

from build123d import Box, Cylinder, Pos, Torus

from . import lib, spec

# ==========================================================================
# DATUMS — everything below is derived from spec or measured off a neighbour
# ==========================================================================

# --- mirrors ---------------------------------------------------------------
# Measured host: the survival cell's deck flank is y = 346.8 at (x=-600,z=595)
# and y = 350.4 at (x=-600,z=470) — effectively vertical through the whole
# mirror-root band, so a fairing lofted along +Y cuts it as a clean teardrop.
MIR_NOSE_X = -516.0  # housing leading edge
MIR_LEN = 190.0  # nose -> the blunt maximum at the glass
MIR_HW = 52.0  # housing half-width at the maximum
MIR_HH = 32.0  # housing half-height at the maximum
MIR_CY0 = 510.0  # centreline of the housing at the nose
MIR_CY1 = 494.0  # ... and at the glass: a slight inboard toe
MIR_CZ = 641.0
MIR_RIM_ROLL = 0.16  # rim rolls to nothing over this much of the length
MIR_POW_W = 0.55  # plan growth exponent (0.5 = ellipse; higher = finer nose)
MIR_POW_H = 0.50  # section growth exponent

# Glass plane: yawed inboard so the mirror looks back at the driver's eye. The
# cut therefore lands further aft on the outboard side than the inboard one,
# which is exactly what a real aimed mirror does.
GLASS_C = (-694.0, 498.0, 646.0)
GLASS_N = (-0.94, -0.33, 0.05)

#  (quarter-chord point), chord, thickness ratio
#  The fillet is a flare in THICKNESS, not in chord. Flaring the chord instead
#  — the first attempt ran 182 mm at the root — turns the root into a straight
#  sided triangle in plan, which reads as a shark fin bolted to the flank, not
#  as a strut growing out of it. Chord stays nearly constant; t/c doubles over
#  the last 30 mm of span at each end.
_MIR_STALK = (
    ((-606.0, 296.0, 588.0), 120.0, 0.38),
    ((-606.0, 324.0, 592.0), 116.0, 0.36),
    ((-606.0, 346.0, 597.0), 104.0, 0.30),
    ((-608.0, 360.0, 603.0), 92.0, 0.25),
    ((-610.0, 378.0, 611.0), 84.0, 0.22),
    ((-613.0, 402.0, 621.0), 78.0, 0.21),
    ((-616.0, 432.0, 631.0), 76.0, 0.22),
    ((-619.0, 462.0, 639.0), 78.0, 0.28),
    ((-621.0, 488.0, 645.0), 88.0, 0.42),
)

# --- tyre sensors (wheel frame: origin at the hub, +Y outboard on the left)
# Measured host: `wheels._duct` draws the drum from yd = -RIM_HW, so its wall
# at r = 168 spans y = yd-7.6 .. yd+2.3. RIM_HW is 137 front / 183 rear.
SENS_PHI = 125.0  # clocked up and rearward, clear of the duct's kidney exits
SENS_ROOT_R = 152.0  # bracket root, inside the drum wall
SENS_POD_R = 206.0  # pod centre, outside the drum lip, inside the tyre bead
SENS_ROOT_DY = -3.0  # y = -(rim half width) + this: in the drum's wall
SENS_POD_DY = 30.0  # pod sits this far inboard of the rim flange plane

# --- pitot mast ------------------------------------------------------------
# Measured host: the tub deck on the centreline is z = 604 at x = -120.
RAKE_X = -120.0
PITOT_Z = 722.0
PITOT_L = 112.0
PITOT_R = 4.4

#  (quarter-chord point), chord, thickness ratio
_MAST = (
    ((RAKE_X, 0.0, 566.0), 168.0, 0.150),
    ((RAKE_X, 0.0, 592.0), 146.0, 0.145),
    ((RAKE_X - 1.0, 0.0, 622.0), 110.0, 0.155),
    ((RAKE_X - 3.0, 0.0, 658.0), 80.0, 0.175),
    ((RAKE_X - 5.0, 0.0, 700.0), 58.0, 0.200),
    ((RAKE_X - 7.0, 0.0, 740.0), 46.0, 0.220),
)

# --- fastener row ----------------------------------------------------------
# Measured host: the floor's topside at |y| = 830, station by station.
DZUS_FLOOR_Y = 830.0
#  x,       top z at y=830, outboard tilt of that surface
_DZUS_FLOOR = (
    (-1240.0, 95.7, 12.6),
    (-1580.0, 99.6, 13.9),
    (-1920.0, 106.5, 9.7),
    (-2260.0, 108.8, 14.2),
    (-2600.0, 106.1, 18.1),
)

# --- recovery / jacking ----------------------------------------------------
# Measured host: nose crease at x = 1150 is (123.4, 232.4); nose underside on
# the centreline at x = 1080 is z = 204.4.
TOW_F = (1150.0, 116.0, 230.0)
TOW_R = (-3900.0, 55.0, 372.0)
JACK_F = (1080.0, 0.0, 200.0)
JACK_R_X = -3930.0  # forward of the beam wing leading edge at x = -3960
JACK_R_Z = 302.0

# --- side cameras ----------------------------------------------------------
# Measured host: the tub deck flank at x = -1240 is y = 385.1 at z = 647.6 and
# y = 386.6 at z = 594.3 — vertical to within 1.5 mm over the root band.
#  x,       hw,   hh,   cy,     cz
_SIDE_CAM = (
    (-1160.0, 14.0, 12.5, 420.0, 650.0),
    (-1172.0, 20.0, 17.5, 420.0, 650.5),
    (-1188.0, 23.0, 20.0, 419.0, 651.0),
    (-1210.0, 22.6, 19.6, 417.5, 651.0),
    (-1236.0, 19.5, 16.8, 415.5, 650.0),
    (-1262.0, 13.5, 11.4, 413.5, 648.0),
    (-1284.0, 5.5, 4.6, 412.0, 645.5),
)

#  (quarter-chord point), chord, thickness ratio
_CAM_STALK = (
    ((-1214.0, 336.0, 628.0), 118.0, 0.30),
    ((-1214.0, 362.0, 632.0), 112.0, 0.26),
    ((-1216.0, 386.0, 639.0), 104.0, 0.22),
    ((-1219.0, 402.0, 645.0), 84.0, 0.26),
    ((-1221.0, 415.0, 649.0), 80.0, 0.44),
)


# ==========================================================================
# small shared geometry
# ==========================================================================


def _v(a, b=None, s: float = 1.0):
    """a + s*b, on 3-tuples."""
    if b is None:
        return (a[0], a[1], a[2])
    return (a[0] + s * b[0], a[1] + s * b[1], a[2] + s * b[2])


def _unit(v):
    m = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2) or 1.0
    return (v[0] / m, v[1] / m, v[2] / m)


def _solid(shape):
    """Normalise a one-solid body to a plain `Solid` before it is labelled.

    build123d's primitives (`Cylinder`, `Box`, `Torus`) and every boolean that
    touches one come back as `Part` — a Compound subclass wrapping a single
    solid — so a module full of machined details exports a tree of Compounds
    where every other part of this car exports Solids. Same geometry, but it
    makes `shapeCount` and the export warnings noisier than they need to be and
    it is one more thing between a body and its colour. A no-op on anything
    already a single solid; genuinely multi-solid bodies are left alone.
    """
    if shape is None:
        return None
    try:
        solids = shape.solids()
    except Exception:
        return shape
    return solids[0] if len(solids) == 1 else shape


def _blade_stack(stations, ruled: bool = False):
    """Loft blade sections with a PER-STATION chord AND thickness ratio.

    `lib.blade_path` fixes one t/c for the whole member, and that single
    limitation is what makes every stalk on a car meet its host at a hard right
    angle: the root cannot swell. Here each station carries its own chord and
    its own thickness, so a member can start as a long shallow fairing lying
    down on the bodywork, waste to a slim aerofoil mid-span, and thicken into a
    collar where it enters a pod. Same blade family as `lib.blade_face`, so it
    still speaks the car's structural vocabulary.
    """
    pts = [lib.Vector(*st[0]) for st in stations]
    faces = []
    for i, (_, chord, tr) in enumerate(stations):
        if i == 0:
            axis = pts[1] - pts[0]
        elif i == len(pts) - 1:
            axis = pts[-1] - pts[-2]
        else:
            axis = pts[i + 1] - pts[i - 1]
        faces.append(lib.blade_face(pts[i], axis, chord, tr))
    return lib.loft_solid(faces, ruled=ruled)


def _teardrop_f(s: float, power: float, roll: float = 0.16) -> float:
    """Normalised half-size at fraction `s` along a teardrop pod.

    Over the body (s <= 1) this is `(2s - s^2)^power`: zero with an INFINITE
    slope at the nose — a genuinely round leading edge, not a wedge — rising to
    a blunt maximum with zero slope at s = 1. Past that it is a quarter ellipse
    that rolls the rim over to nothing by s = 1 + roll, which is what gives the
    mirror shell a rolled outer edge where the glass plane cuts it instead of a
    sheared-off tube. The two branches meet C1 at s = 1.
    """
    if s <= 1.0:
        return max(2.0 * s - s * s, 0.0) ** power
    u = (s - 1.0) / roll
    return math.sqrt(max(1.0 - u * u, 0.0))


def _pod_pts(cy, cz, hw, hh, n_out=2.05, n_in=2.90, n_top=2.50, n_bot=2.25,
             samples=40):
    """`lib.superellipse_pts` whose exponent varies SMOOTHLY round the section.

    The outboard half is rounder than the inboard half, which is what gives the
    mirror pod its rolled outer edge and lets the inboard flank run flat into
    the stalk instead of bulging over it.

    The exponent is cosine-blended, not switched per quadrant. Switching it at
    the quadrant boundaries — which is the obvious way to write this — puts a
    slope discontinuity at all four of the section's extremes, and the periodic
    spline through it then wobbles: the pod renders with a faint scalloped
    crease running its whole length. Blending costs nothing and the surface is
    clean.
    """
    pts = []
    for i in range(samples):
        a = 2.0 * math.pi * i / samples
        ca, sa = math.cos(a), math.sin(a)
        wx, wz = 0.5 * (1.0 + ca), 0.5 * (1.0 + sa)
        n = 0.5 * (
            n_out * wx + n_in * (1.0 - wx) + n_top * wz + n_bot * (1.0 - wz)
        )
        pts.append(
            (
                cy + hw * math.copysign(abs(ca) ** (2.0 / n), ca),
                cz + hh * math.copysign(abs(sa) ** (2.0 / n), sa),
            )
        )
    return pts


def _circle_pts(cy, cz, r, n: int = 20):
    return [
        (cy + r * math.cos(2 * math.pi * i / n), cz + r * math.sin(2 * math.pi * i / n))
        for i in range(n)
    ]


def _plate(center, normal, stations, up=(0, 0, 1)):
    """A rounded plate lofted between offsets along `normal`.

    stations: ((offset, length, height, corner), ...) — the one construction
    used for every bezel and fastener ring in this module.
    """
    out = []
    for off, length, height, corner in stations:
        out.append(
            {
                "plane": lib.plate_plane(_v(center, normal, off), normal, up=up),
                "pts": lib.rounded_plate_pts(length, height, corner),
            }
        )
    return lib.swept_plate(out, ruled=True)


# ==========================================================================
# 1 — MIRRORS
# ==========================================================================

# Section fractions: clustered hard at the nose so the round leading edge is
# resolved, and again at the rim so the roll-over reads.
_MIR_S = (
    0.004, 0.014, 0.036, 0.070, 0.120, 0.190, 0.280, 0.380, 0.500,
    0.620, 0.740, 0.840, 0.920, 0.970, 1.000, 1.040, 1.080, 1.120, 1.150,
)


def _mirror_housing():
    """Teardrop shell, aft end CUT by the glass plane."""
    faces = []
    for s in _MIR_S:
        fw = _teardrop_f(s, MIR_POW_W, MIR_RIM_ROLL)
        fh = _teardrop_f(s, MIR_POW_H, MIR_RIM_ROLL)
        t = min(s, 1.0)
        cy = MIR_CY0 + (MIR_CY1 - MIR_CY0) * t
        cz = MIR_CZ + 6.0 * _teardrop_f(t, 0.5)
        faces.append(
            lib.section_face(
                MIR_NOSE_X - MIR_LEN * s,
                _pod_pts(cy, cz, MIR_HW * fw, MIR_HH * fh),
            )
        )
    shell = lib.body_loft(faces)
    n = _unit(GLASS_N)
    cutter = lib.plate_plane(_v(GLASS_C, n, 150.0), n) * Box(420.0, 420.0, 300.0)
    shell = lib.cut(shell, cutter)
    # A real pocket for the bezel. Left to simply overlap the shell, the bezel's
    # curved flank meets the rolled rim at a shallow angle and the two meshes
    # cross in a visibly serrated seam; a pocket turns that into a designed
    # panel gap and the bezel is genuinely let in rather than stuck on.
    return lib.cut(shell, _plate(GLASS_C, n, ((-7.0, 82.0, 48.0, 14.0),
                                              (30.0, 82.0, 48.0, 14.0))))


def _mirror_shell():
    """ONE body: housing + faired stalk, fused and healed.

    A crown winglet was modelled here and then deleted. Seen from above — the
    angle half a launch render is shot from — any winglet small enough to suit
    a mirror pod is a flat straight-edged trapezoid stuck on its shoulder,
    which is the exact failure the rest of this rewrite is undoing. The pod's
    own rolled outer edge carries the shape instead.
    """
    return lib.fuse_all(_mirror_housing(), [_blade_stack(_MIR_STALK)])


def _mirror_optics():
    """Machined bezel let into the rolled rim, pocketed glass, accent ring."""
    n = _unit(GLASS_N)
    bezel = _plate(
        GLASS_C, n,
        ((-6.0, 80.5, 46.5, 13.5), (1.0, 78.0, 44.0, 13.0),
         (5.0, 73.5, 40.5, 12.0)),
    )
    bezel = lib.cut(
        bezel,
        _plate(GLASS_C, n, ((-0.4, 68.0, 36.5, 10.0), (16.0, 68.0, 36.5, 10.0))),
    )
    glass = _plate(GLASS_C, n, ((0.0, 67.0, 35.5, 9.6), (3.4, 66.2, 34.7, 9.4)))
    # THE accent, and the only one in this module: a 2 mm machined ring capping
    # the joint between the bezel and the pocket. Wider than that and it reads
    # as a painted frame, which is exactly the "if in doubt use less" case.
    ring = lib.cut(
        _plate(GLASS_C, n, ((-1.0, 84.0, 50.0, 15.0), (2.0, 83.0, 49.0, 14.5))),
        _plate(GLASS_C, n, ((-6.0, 80.0, 46.0, 13.5), (9.0, 80.0, 46.0, 13.5))),
    )
    return bezel, glass, ring


def _mirrors():
    bodies = []
    bezel, glass, ring = _mirror_optics()
    items = (
        (_mirror_shell(), "mirror_shell", spec.CARBON_GLOSS),
        (bezel, "mirror_bezel", spec.ANODIZED),
        (glass, "mirror_glass", spec.GLASS),
        (ring, "mirror_ring", spec.ACCENT),
    )
    for shape, label, color in items:
        bodies += lib.pair(_solid(shape), label, color)
    return bodies


# ==========================================================================
# 2 — TYRE IR SENSORS  (built in the wheel frame: hub at the origin)
#
# The bracket root is buried in the brake-duct drum wall and spread into a
# fairing; its head thickens into a collar inside the sensor body, and the two
# are fused. Both axles share every number except the rim half width, so all
# four corners are the same object.
# ==========================================================================

RIM_HW = {"f": 137.0, "r": 183.0}  # measured off wheels.RIM_HW


def _sensor_corner(bh: float):
    a = math.radians(SENS_PHI)
    rad = (math.cos(a), 0.0, math.sin(a))
    aim = _unit((rad[0] * 118.0, 20.0, rad[2] * 118.0))
    c = (SENS_POD_R * rad[0], -(bh + SENS_POD_DY), SENS_POD_R * rad[2])

    def at(r, dy):
        return (r * rad[0], -(bh + dy), r * rad[2])

    bracket = _blade_stack(
        (
            (at(SENS_ROOT_R, SENS_ROOT_DY), 62.0, 0.44),
            (at(166.0, 6.0), 46.0, 0.40),
            (at(182.0, 17.0), 32.0, 0.40),
            (at(196.0, 26.0), 34.0, 0.62),
        )
    )
    body = lib.plate_plane(c, aim) * Cylinder(12.5, 40.0)
    pod = lib.fuse_all(body, [bracket])
    bezel = lib.plate_plane(_v(c, aim, 20.0), aim) * Cylinder(14.0, 6.0)
    lens = lib.plate_plane(_v(c, aim, 22.8), aim) * Cylinder(10.4, 4.6)
    return (
        (_solid(lib.fuse_all(pod, [bezel])), "tyre_sensor_pod", spec.ANODIZED),
        (_solid(lens), "tyre_sensor_lens", spec.GLASS),
    )


def _tyre_sensors():
    bodies = []
    for axle, x_axle, hub_y in (
        ("f", spec.FRONT_AXLE_X, spec.FRONT_HUB_Y),
        ("r", spec.REAR_AXLE_X, spec.REAR_HUB_Y),
    ):
        place = Pos(x_axle, hub_y, spec.HUB_Z)
        for shape, label, color in _sensor_corner(RIM_HW[axle]):
            bodies += lib.pair(_solid(place * shape), f"{label}_{axle}", color)
    return bodies


# ==========================================================================
# 3 — PITOT MAST: one faired blade mast, one probe
# ==========================================================================


def _pitot(z: float, x_root: float, length: float, r: float):
    """A fine probe: parallel shank, then a long taper to a small tip cone."""
    stations = (
        (x_root, r), (x_root + 0.10 * length, r),
        (x_root + 0.38 * length, 0.92 * r), (x_root + 0.66 * length, 0.76 * r),
        (x_root + 0.86 * length, 0.60 * r), (x_root + 0.95 * length, 0.46 * r),
        (x_root + length, 0.22 * r),
    )
    return lib.body_loft(
        [lib.section_face(x, _circle_pts(0.0, z, rr, n=16)) for x, rr in stations]
    )


def _pitot_mast():
    mast = _blade_stack(_MAST)
    probe = _pitot(PITOT_Z, RAKE_X - 12.0, PITOT_L, PITOT_R)
    return [
        lib.styled(_solid(mast), "pitot_mast", spec.CARBON),
        # Anodized, not bright: on the presentation stage a bare metal probe
        # this small is a specular sliver and reads as a stray highlight ahead
        # of the cockpit rather than as an instrument.
        lib.styled(_solid(probe), "pitot_probe", spec.ANODIZED),
    ]


# ==========================================================================
# 4 — DZUS ROW, RECESSED
#
# One row only, on the floor's outboard mounting line, five a side. Each
# fastener is a machined dish sunk INTO the surface with the quarter-turn head
# flush inside it, so the row reads as a panel break rather than as a line of
# proud bolt-heads. Both the dishes and the heads fuse into one body a side.
# ==========================================================================


def _dzus_recess(center, normal):
    """(dish, head) — the dish is sunk, the head sits flush inside it."""
    outer = lib.plate_plane(_v(center, normal, -4.6), normal) * Cylinder(9.8, 9.0)
    pocket = lib.plate_plane(_v(center, normal, -2.4), normal) * Cylinder(7.4, 6.0)
    dish = lib.cut(outer, pocket)
    head = lib.plate_plane(_v(center, normal, -3.4), normal) * Cylinder(7.0, 2.2)
    slot = lib.plate_plane(_v(center, normal, -2.5), normal) * Box(16.0, 2.2, 1.4)
    return dish, lib.cut(head, slot)


def _dzus_row():
    # One labelled body per part per station. Fusing the five into a single
    # body a side is tempting but produces a Compound of disjoint solids, which
    # is neither addressable nor a solid — and these are the bodies most likely
    # to need moving when the floor edge changes.
    out = []
    for k, (x, z_top, tilt) in enumerate(_DZUS_FLOOR):
        n = _unit((0.0, math.sin(spec.deg(tilt)), math.cos(spec.deg(tilt))))
        dish, head = _dzus_recess((x, DZUS_FLOOR_Y, z_top), n)
        out += lib.pair(_solid(dish), f"floor_dzus_recess_{k}", spec.ANODIZED)
        out += lib.pair(_solid(head), f"floor_dzus_{k}", spec.TITANIUM)
    return out


# ==========================================================================
# 5 / 6 — TOW EYES AND JACK POINTS
# ==========================================================================


def _tow_eye(center, boss_l, boss_h, major, minor, out_dy, n):
    """A machined loop standing in a pocketed carbon boss on a flank.

    `n` is the host flank's outward normal INCLUDING its plan taper, so the
    boss lies down on the flank instead of sinking in at one end and standing
    proud at the other.
    """
    boss = _plate(
        center, n,
        ((-9.0, boss_l, boss_h, 0.20 * boss_h),
         (2.0, 0.92 * boss_l, 0.92 * boss_h, 0.19 * boss_h),
         (8.0, 0.78 * boss_l, 0.76 * boss_h, 0.17 * boss_h)),
    )
    boss = lib.cut(
        boss,
        _plate(
            center, n,
            ((-2.0, 0.60 * boss_l, 0.56 * boss_h, 0.16 * boss_h),
             (24.0, 0.60 * boss_l, 0.56 * boss_h, 0.16 * boss_h)),
        ),
    )
    loop = lib.plate_plane(_v(center, n, out_dy), (0, 0, 1)) * Torus(major, minor)
    return boss, loop


def _front_jack():
    axis = _unit((0.32, 0.0, -0.95))
    plane = lib.plate_plane(JACK_F, axis)
    socket = lib.cut(
        plane * Cylinder(15.0, 36.0),
        lib.plate_plane(_v(JACK_F, axis, 7.0), axis) * Cylinder(9.0, 32.0),
    )
    mouth = lib.plate_plane(_v(JACK_F, axis, 13.0), axis)
    ring = lib.cut(mouth * Cylinder(11.6, 5.0), mouth * Cylinder(8.8, 7.0))
    return socket, ring


def _rear_jack():
    """Bracket faired up into the crash structure, bar slung below it."""
    bracket = _plate(
        (JACK_R_X + 26.0, 0.0, 330.0), (-1, 0, 0),
        ((-9.0, 84.0, 62.0, 14.0), (0.0, 80.0, 58.0, 13.0),
         (9.0, 70.0, 50.0, 12.0)),
    )
    bar = lib.plate_plane((JACK_R_X, 0.0, JACK_R_Z), (0, 1, 0)) * Cylinder(9.0, 70.0)
    return bracket, bar


# ==========================================================================
# 7 — ONBOARD SIDE CAMERAS (same pod family as the mirrors and the nose)
# ==========================================================================


def _side_camera():
    pod = lib.body_loft(
        [
            lib.section_face(x, _pod_pts(cy, cz, hw, hh, n_out=2.2, n_in=2.6))
            for x, hw, hh, cy, cz in _SIDE_CAM
        ]
    )
    shell = lib.fuse_all(pod, [_blade_stack(_CAM_STALK)])
    x0, _, _, cy, cz = _SIDE_CAM[0]
    bezel = lib.plate_plane((x0 - 3.0, cy, cz), (1, 0, 0)) * Cylinder(15.5, 16.0)
    lens = lib.plate_plane((x0 + 3.5, cy, cz), (1, 0, 0)) * Cylinder(11.0, 8.0)
    return lib.fuse_all(shell, [bezel]), lens


# ==========================================================================
# PUBLIC BUILDER
# ==========================================================================


def build_details():
    bodies = _mirrors() + _tyre_sensors() + _pitot_mast() + _dzus_row()

    boss, loop = _tow_eye(TOW_F, 78.0, 54.0, 17.0, 4.2, -1.0, (0.183, 0.983, 0.0))
    bodies += lib.pair(_solid(boss), "tow_boss_front", spec.CARBON)
    bodies += lib.pair(_solid(loop), "tow_eye_front", spec.TITANIUM)
    boss, loop = _tow_eye(TOW_R, 68.0, 46.0, 15.0, 3.8, 1.0, (-0.108, 0.994, 0.0))
    bodies += lib.pair(_solid(boss), "tow_boss_rear", spec.CARBON)
    bodies += lib.pair(_solid(loop), "tow_eye_rear", spec.TITANIUM)

    socket, ring = _front_jack()
    bodies.append(lib.styled(_solid(socket), "jack_socket_front", spec.ANODIZED))
    bodies.append(lib.styled(_solid(ring), "jack_ring_front", spec.TITANIUM))
    bracket, bar = _rear_jack()
    bodies.append(lib.styled(_solid(bracket), "jack_bracket_rear", spec.ANODIZED))
    bodies.append(lib.styled(_solid(bar), "jack_bar_rear", spec.TITANIUM))

    shell, lens = _side_camera()
    bodies += lib.pair(_solid(shell), "side_cam_pod", spec.CARBON_GLOSS)
    bodies += lib.pair(_solid(lens), "side_cam_lens", spec.GLASS)

    return lib.group("details", bodies)
