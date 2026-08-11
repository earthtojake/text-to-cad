"""juno humanoid -- leg segments: thigh, shin, foot.

Local frames (units mm, robot faces +X, +Y is robot-left, +Z up):
- thigh: origin at hip-pitch joint center; knee axis = Y through (0,0,-245).
- shin:  origin at knee joint center; ankle-pitch axis = Y through (0,0,-245).
- foot:  origin at ankle-roll joint center, 26 mm above the sole bottom.

Builders return identity-location Compounds of labeled, colored solids.
Left/right mirror about the XZ plane.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path



from build123d import (
    Axis,
    Box,
    Compound,
    Cylinder,
    GeomType,
    Plane,
    Pos,
    RectangleRounded,
    Rot,
    chamfer,
    fillet,
    loft,
    mirror,
)

from .juno_lib import (
    ACCENT_COLOR,
    ALU_COLOR,
    RUBBER_COLOR,
    SHELL_COLOR,
    STRUCT_COLOR,
    actuator_solids,
    part_compound,
    rounded_box,
    styled,
)


# --------------------------------------------------------------- helpers


def _solo(shape):
    """Largest solid of a boolean result (keeps each child manifold)."""
    sols = shape.solids()
    if len(sols) == 1:
        return sols[0]
    return max(sols, key=lambda s: s.volume)


def _solids_over(shape, min_volume=800.0):
    """All solids of a boolean result above a volume floor, biggest first."""
    sols = sorted(shape.solids(), key=lambda s: s.volume, reverse=True)
    return [s for s in sols if s.volume > min_volume] or sols[:1]


def _try_fillet(shape, edges, radius):
    try:
        edges = list(edges)
        if edges:
            return _solo(fillet(edges, radius))
    except Exception:
        pass
    return shape


def _try_chamfer(shape, edges, length):
    try:
        edges = list(edges)
        if edges:
            return _solo(chamfer(edges, length))
    except Exception:
        pass
    return shape


def _cyl_y(radius, length, center=(0.0, 0.0, 0.0)):
    return Pos(*center) * Rot(-90, 0, 0) * Cylinder(radius, length)


def _cyl_x(radius, length, center=(0.0, 0.0, 0.0)):
    return Pos(*center) * Rot(0, 90, 0) * Cylinder(radius, length)


def _loft_z(specs):
    """Loft rounded-rectangle sections normal to Z.

    specs: iterable of (z, x_size, y_size, x_center, y_center, corner_r).
    """
    faces = [
        Pos(xc, yc, z) * RectangleRounded(w, d, r)
        for (z, w, d, xc, yc, r) in specs
    ]
    return _solo(loft(faces))


def _loft_x(specs):
    """Loft rounded-rectangle sections normal to X.

    specs: iterable of (x, y_size, z_size, z_center, corner_r).
    """
    faces = [
        Plane.YZ.offset(x) * Pos(0, zc, 0) * RectangleRounded(wy, hz, r)
        for (x, wy, hz, zc, r) in specs
    ]
    return _solo(loft(faces))


def _rim_chamfer(shape, radius, length):
    """Chamfer circular edges of a given radius (collar rims etc.)."""
    try:
        edges = [
            e
            for e in shape.edges().filter_by(GeomType.CIRCLE)
            if abs(e.radius - radius) < 0.6
        ]
        return _try_chamfer(shape, edges, length)
    except Exception:
        return shape


def _yoke_fillet(shape, z_lo, z_hi, radius):
    """Fillet vertical (Z) edges whose centers lie in a z band."""
    try:
        edges = [
            e
            for e in shape.edges().filter_by(Axis.Z)
            if z_lo < e.center().Z < z_hi and e.length > 20
        ]
        return _try_fillet(shape, edges, radius)
    except Exception:
        return shape


def _mirror_children(children):
    out = []
    for c in children:
        m = mirror(c, about=Plane.XZ)
        if m.volume < 0:  # reversed orientation from the mirror
            try:
                m = m.fix()
            except Exception:
                pass
        out.append(styled(m, c.label, c.color))
    return out


def _fallback(label, size):
    return [styled(Box(*size), f"{label}_fallback", STRUCT_COLOR)]


# ----------------------------------------------------------------- thigh

KNEE_Z = -290.0  # stretched +45 per proportion audit (G1-like leg ratio)


def _thigh_children():
    ch = []

    # Exposed hip-pitch actuator (locked interface).
    ch += actuator_solids("hip_pitch", 92, 72, center=(0, 0, 0), axis=(0, 1, 0))

    # Graphite structural core: quad-like taper + full hip collar ring,
    # bored for the actuator can so faces stay clear.
    core = _loft_z(
        [
            (-30, 92, 72, 2, 0, 18),
            (-100, 98, 86, 8, 0, 22),
            (-185, 84, 76, 6, 0, 18),
            (-225, 60, 68, 2, 0, 14),
        ]
    )
    core = _solo(core + _cyl_y(55, 34))  # hip collar band |y|<=17
    core = _solo(core - _cyl_y(46.5, 130))  # can clearance bore
    core = _rim_chamfer(core, 55.0, 2.0)
    ch.append(styled(core, "thigh_core", STRUCT_COLOR))

    # Ice-gray fairing wrapping front + outer (robot-left) faces, split into
    # two shells by a panel reveal that exposes the graphite core.
    shell = _loft_z(
        [
            (-58, 94, 78, 11, 3, 18),
            (-105, 99, 88, 12, 4, 22),
            (-185, 84, 80, 11, 3, 18),
            (-221, 62, 70, 8, 2, 14),
        ]
    )
    shell = shell - core
    shell = shell - (Pos(0, 0, -140.5) * Box(320, 320, 3))  # panel reveal
    panels = _solids_over(shell)[:2]
    tags = ("upper", "lower")
    for sol, tag in zip(panels, tags):
        sol = _try_chamfer(sol, sol.edges(), 0.5)
        ch.append(styled(sol, f"thigh_fairing_{tag}", SHELL_COLOR))

    # Knee fork (locked): yoke + twin plates, inner faces y=+-38, outer
    # y=+-48, spanning z -225..-324, bored dia 56 on the knee axis.
    fork = Pos(0, 0, -241) * Box(58, 96, 32)
    for s in (1.0, -1.0):
        fork = fork + Pos(0, s * 43, -273) * Box(60, 10, 34)
        fork = fork + _cyl_y(34, 10, (0, s * 43, KNEE_Z))
    fork = _solo(fork - _cyl_y(28, 120, (0, 0, KNEE_Z)))
    # relief arch so the shin's knee can (dia 92, |y|<=33) swings clear
    fork = _solo(fork - _cyl_y(46.8, 67.6, (0, 0, KNEE_Z)))
    fork = _yoke_fillet(fork, -258, -224, 8.0)
    fork = _try_chamfer(fork, fork.edges(), 0.8)
    ch.append(styled(fork, "knee_fork", STRUCT_COLOR))

    # Aluminum bearing bosses dia 56 at (0,+-43,-245), through the plates.
    for s, tag in ((1.0, "out"), (-1.0, "in")):
        boss = _cyl_y(28, 10, (0, s * 43, KNEE_Z)) + _cyl_y(
            30.5, 1.8, (0, s * 48.9, KNEE_Z)
        )
        boss = _solo(boss)
        boss = _try_chamfer(boss, boss.edges(), 0.6)
        ch.append(styled(boss, f"knee_boss_{tag}", ALU_COLOR))

    return ch


def build_thigh(side="left"):
    label = f"thigh_{side}"
    try:
        ch = _thigh_children()
    except Exception:
        traceback.print_exc()
        ch = _fallback(label, (90, 90, 260))
    if side == "right":
        ch = _mirror_children(ch)
    return part_compound(label, ch)


# ------------------------------------------------------------------ shin

ANKLE_Z = -290.0  # stretched +45 per proportion audit (G1-like leg ratio)


def _shin_children():
    ch = []

    # Exposed knee actuator (locked interface; dia 92 per torque hierarchy).
    ch += actuator_solids("knee", 92, 66, center=(0, 0, 0), axis=(0, 1, 0))

    # Graphite calf core: full upper rear (calf), slim near ankle.
    core = _loft_z(
        [
            (-26, 82, 60, 0, 0, 16),
            (-95, 84, 72, -6, 0, 18),
            (-185, 62, 58, -2, 0, 14),
            (-225, 44, 50, 0, 0, 11),
        ]
    )
    core = _solo(core + _cyl_y(53, 30))  # knee collar band |y|<=15
    core = _solo(core - _cyl_y(46.5, 120))  # can clearance bore
    core = _rim_chamfer(core, 53.0, 2.0)
    ch.append(styled(core, "shin_core", STRUCT_COLOR))

    # Front shin-guard ridge (ice-gray), split by a panel reveal.
    guard = _loft_z(
        [
            (-55, 78, 64, 7, 0, 16),
            (-100, 78, 64, 6, 0, 16),
            (-185, 64, 50, 6, 0, 12),
            (-223, 46, 40, 4, 0, 10),
        ]
    )
    guard = guard - core
    guard = guard - (Pos(0, 0, -145.5) * Box(320, 320, 3))
    panels = _solids_over(guard)[:2]
    for sol, tag in zip(panels, ("upper", "lower")):
        sol = _try_chamfer(sol, sol.edges(), 0.5)
        ch.append(styled(sol, f"shin_guard_{tag}", SHELL_COLOR))

    # Ankle fork (locked): plates inner y=+-26, outer y=+-34, bored dia 40
    # on the ankle-pitch axis through (0,0,-290).
    fork = Pos(0, 0, -241) * Box(46, 68, 28)
    for s in (1.0, -1.0):
        fork = fork + Pos(0, s * 30, -270.5) * Box(54, 8, 39)
        fork = fork + _cyl_y(27, 8, (0, s * 30, ANKLE_Z))
    fork = _solo(fork - _cyl_y(20, 100, (0, 0, ANKLE_Z)))
    fork = _yoke_fillet(fork, -256, -226, 7.0)
    fork = _try_chamfer(fork, fork.edges(), 0.8)
    ch.append(styled(fork, "ankle_fork", STRUCT_COLOR))

    # Aluminum bearing bosses dia 40 at (0,+-30,-245).
    for s, tag in ((1.0, "out"), (-1.0, "in")):
        boss = _cyl_y(20, 8, (0, s * 30, ANKLE_Z)) + _cyl_y(
            22, 1.8, (0, s * 34.9, ANKLE_Z)
        )
        boss = _solo(boss)
        boss = _try_chamfer(boss, boss.edges(), 0.6)
        ch.append(styled(boss, f"ankle_boss_{tag}", ALU_COLOR))

    return ch


def build_shin(side="left"):
    label = f"shin_{side}"
    try:
        ch = _shin_children()
    except Exception:
        traceback.print_exc()
        ch = _fallback(label, (80, 80, 260))
    if side == "right":
        ch = _mirror_children(ch)
    return part_compound(label, ch)


# ------------------------------------------------------------------ foot


def _foot_children():
    ch = []

    # Clearance for the ankle-roll can (dia 44, |x|<21 keep-clear r<24).
    roll_clear = _cyl_x(24.5, 43)

    # Rubber sole plate z -26..-19, x -68..112, width 70, toe-up + heel kick.
    sole = rounded_box(
        "sole_blank", RUBBER_COLOR, (180, 70, 7), center=(22, 0, -22.5),
        radius=16, axes="z",
    )
    sole = sole - roll_clear
    # toe-up wedge over the last ~30 mm (cut line (82,-26) -> (113,-20.4))
    sole = sole - (Pos(96.5, 0, -29.46) * Rot(0, -10.3, 0) * Box(44, 96, 12))
    # small heel kick (cut line (-58,-26) -> (-69,-22.5))
    sole = sole - (Pos(-63, 0, -29.66) * Rot(0, 17.65, 0) * Box(24, 96, 10))
    for gx in (-54.0, -36.0, -18.0, 36.0, 54.0, 72.0):  # tread grooves
        sole = sole - (Pos(gx, 0, -25.8) * Box(4.5, 100, 4.5))
    ch.append(styled(_solo(sole), "sole", RUBBER_COLOR))

    # Sneaker-like wedge upper (ice-gray), lofted along X. Heights raised
    # ~+6 mm per the visual review (feet read too thin in profile).
    upper = _loft_x(
        [
            (-62, 54, 27, -5.5, 6),
            (-30, 62, 32, -3.0, 7),
            (30, 62, 30, -4.0, 7),
            (72, 56, 22, -8.0, 5),
            (104, 38, 10, -14.0, 2.4),
        ]
    )
    recess = rounded_box(
        "recess_cut", SHELL_COLOR, (66, 64, 20), center=(0, 0, 2),
        radius=9, axes="z",
    )
    upper = upper - recess  # saddle recess down to z=-8
    upper = _solo(upper - roll_clear)
    ch.append(styled(upper, "foot_upper", SHELL_COLOR))

    # Top saddle (locked): twin plates normal to X at x 22..32 / -32..-22,
    # domed around the roll axis, tied by side rails outside the keep-clear.
    saddle = None
    for s in (1.0, -1.0):
        plate = Pos(27 * s, 0, -1) * Box(10, 62, 14)
        plate = plate + _cyl_x(19, 10, (27 * s, 0, 0))
        saddle = plate if saddle is None else saddle + plate
        saddle = saddle + Pos(0, s * 27.75, -2) * Box(64, 6.5, 12)
    saddle = saddle & (Pos(0, 0, 4) * Box(80, 90, 24))  # clip to z -8..16
    saddle = _solo(saddle)
    saddle = _try_chamfer(saddle, saddle.edges(), 0.8)
    ch.append(styled(saddle, "roll_saddle", STRUCT_COLOR))

    # Aluminum bearing bosses dia 34, coaxial with X through the origin.
    for s, tag in ((1.0, "out"), (-1.0, "in")):
        boss = _cyl_x(17, 5.5, (34.75 * s, 0, 0)) + _cyl_x(
            9, 2, (38.5 * s, 0, 0)
        )
        boss = _solo(boss)
        boss = _try_chamfer(boss, boss.edges(), 0.6)
        ch.append(styled(boss, f"roll_boss_{tag}", ALU_COLOR))

    # Graphite toe bumper wrapping the toe box.
    toe = rounded_box(
        "toe_blank", STRUCT_COLOR, (13, 50, 10), center=(105.5, 0, -14),
        radius=5, axes="z",
    )
    toe = _solo(toe - upper)
    ch.append(styled(toe, "toe_bumper", ACCENT_COLOR))

    # Graphite heel bumper.
    heel = rounded_box(
        "heel_blank", STRUCT_COLOR, (10, 52, 11), center=(-63, 0, -13.5),
        radius=4, axes="z",
    )
    heel = _solo(heel - upper)
    ch.append(styled(heel, "heel_bumper", ACCENT_COLOR))

    return ch


def build_foot(side="left"):
    label = f"foot_{side}"
    try:
        ch = _foot_children()
    except Exception:
        traceback.print_exc()
        ch = _fallback(label, (180, 70, 32))
    if side == "right":
        ch = _mirror_children(ch)
    return part_compound(label, ch)


# ------------------------------------------------------------------ demo


def gen_step():
    cols = []
    x = 0.0
    for side in ("left", "right"):
        for builder in (build_thigh, build_shin, build_foot):
            comp = builder(side)
            comp.location = Pos(x, 0, 0)
            cols.append(comp)
            x += 260.0
    demo = Compound(children=cols)
    demo.label = "juno_legs_demo"
    return demo
