"""juno pelvis: waist-yaw ring, graphite chassis, hip pods, shell fairings.

Local frame: origin = waist-yaw joint center at the TOP of the pelvis.
Geometry spans z -120..+2. Robot faces +X, +Y robot-left, +Z up.

Locked interfaces (do not move):
- Waist ring: aluminum cylinder dia 96, z -2..+2, centered on Z.
- Hip pods: flat round mounting face dia 80 at z=-120 centered (0, +-90, -120);
  everything below z=-120 stays clear for the leg hip-yaw actuator (dia 76).
- Envelope: x -65..+65, |y| <= 115 (pod faces at y=+-90 r40 reach 122 by the
  locked interface itself).
"""

from __future__ import annotations

import sys
from pathlib import Path



import math

from build123d import (
    Axis,
    Box,
    Cylinder,
    Plane,
    Pos,
    RectangleRounded,
    Rot,
    chamfer,
    extrude,
    fillet,
)

from .juno_lib import (
    ALU_COLOR,
    SHELL_COLOR,
    STRUCT_COLOR,
    part_compound,
    styled,
)


def _safe(op, solid):
    """Run a fillet/chamfer op; fall back to the input solid on any failure."""
    try:
        out = op(solid)
        if out is not None and out.volume > 1.0:
            return out
    except Exception:
        pass
    return solid


def _zband(solid, lo, hi):
    return solid.edges().filter_by_position(Axis.Z, lo, hi)


# ---------------------------------------------------------------- chassis ---

def _waist_deck():
    deck = Pos(0, 0, -8) * Box(104, 118, 12)
    deck = _safe(lambda s: fillet(s.edges().filter_by(Axis.Z), 14), deck)
    deck = _safe(lambda s: chamfer(_zband(s, -2.01, -1.99), 2.0), deck)
    deck = _safe(lambda s: chamfer(_zband(s, -14.01, -13.99), 2.0), deck)
    return deck


def _abdomen_column():
    try:
        sk = Plane(
            origin=(0, 0, -14), x_dir=(1, 0, 0), z_dir=(0, 0, -1)
        ) * RectangleRounded(86, 96, 13)
        col = extrude(sk, amount=58, taper=6)
        if col.volume > 1.0:
            return col
    except Exception:
        pass
    return Pos(0, 0, -43) * Box(80, 90, 58)


def _hip_yoke():
    yoke = Pos(0, 0, -86) * Box(76, 164, 36)
    yoke = _safe(lambda s: chamfer(s.edges().filter_by(Axis.Y), 5.0), yoke)
    return yoke


def _pod(side):
    return Pos(0, side * 90, -86) * Cylinder(radius=40, height=56)


def _chassis():
    chassis = _waist_deck() + _abdomen_column() + _hip_yoke()
    chassis = chassis + _pod(+1) + _pod(-1)

    # Recessed service pockets on yoke front/back faces.
    for sx in (+1, -1):
        for sy in (+1, -1):
            chassis -= Pos(sx * 38, sy * 48, -86) * Box(4, 36, 22)

    # Panel seam groove around each pod above the aluminum rim.
    for sy in (+1, -1):
        ring = Pos(0, sy * 90, -100) * (
            Cylinder(radius=45, height=1.8) - Cylinder(radius=37.5, height=1.8)
        )
        chassis -= ring
    return styled(chassis, "pelvis_chassis", STRUCT_COLOR)


# ----------------------------------------------------------------- accents ---

def _waist_ring():
    ring = Cylinder(radius=48, height=4)
    ring = _safe(lambda s: chamfer(s.edges(), 0.8), ring)
    return styled(ring, "pelvis_waist_ring", ALU_COLOR)


def _pod_rim(side, tag):
    rim = Pos(0, side * 90, -117) * Cylinder(radius=40, height=6)
    rim = _safe(lambda s: chamfer(_zband(s, -120.01, -119.9), 1.0), rim)
    rim = _safe(lambda s: chamfer(_zband(s, -114.1, -113.9), 0.8), rim)
    # machined witness groove
    rim -= Pos(0, side * 90, -116) * (
        Cylinder(radius=41, height=1.0) - Cylinder(radius=39, height=1.0)
    )
    return styled(rim, f"pelvis_pod_rim_{tag}", ALU_COLOR)


def _pod_collar(side, tag):
    collar = Pos(0, side * 90, -83) * (
        Cylinder(radius=42.5, height=4) - Cylinder(radius=40, height=4)
    )
    collar = _safe(lambda s: chamfer(_zband(s, -85.01, -84.9), 0.7), collar)
    return styled(collar, f"pelvis_pod_collar_{tag}", ALU_COLOR)


# ---------------------------------------------------------------- fairings ---

def _fairing(side, tag):
    s = side
    # Volumetric upper hip shell: y 56..112, z -76..-12, x -58..58.
    blank = Pos(0, s * 84, -44) * Box(116, 56, 64)
    blank = _safe(lambda b: fillet(b.edges().filter_by(Axis.Z), 14), blank)

    # Plan-view 45 deg facets at the outer-front / outer-rear corners.
    blank -= (
        Pos(50, s * 100, -44) * Rot(0, 0, -s * 45.0) * Pos(16, 0, 0) * Box(32, 64, 84)
    )
    blank -= (
        Pos(-50, s * 100, -44) * Rot(0, 0, s * 45.0) * Pos(-16, 0, 0) * Box(32, 64, 84)
    )
    blank = _safe(lambda b: fillet(b.edges().filter_by(Axis.Z), 5.0), blank)

    # Gentle top-outer slope (hip shoulder).
    blank -= (
        Pos(0, s * 72, -12)
        * Rot(-18.0 * s, 0, 0)
        * Pos(0, 0, 36)
        * Box(150, 170, 72)
    )
    # Gentle front-top and rear-top slopes.
    blank -= Pos(38, s * 84, -13) * Rot(0, 20, 0) * Pos(0, 0, 36) * Box(110, 150, 72)
    blank -= Pos(-38, s * 84, -13) * Rot(0, -20, 0) * Pos(0, 0, 36) * Box(110, 150, 72)

    # Mild bottom tucks: lower edge rises toward front and rear.
    blank -= (
        Pos(28, s * 84, -76) * Rot(0, -14, 0) * Pos(0, 0, -36) * Box(130, 150, 72)
    )
    blank -= (
        Pos(-28, s * 84, -76) * Rot(0, 14, 0) * Pos(0, 0, -36) * Box(130, 150, 72)
    )
    # Angled under-edge: bottom rises inboard so the shell lower line meets
    # the yoke clearance (-64 at y=56) flush, no stepped notch.
    blank -= (
        Pos(0, s * 56, -64)
        * Rot(-12.0 * s, 0, 0)
        * Pos(0, 0, -36)
        * Box(150, 170, 72)
    )
    # NOTE: no post-cut fillets here. OCCT's fillet on the sloped-cut edge
    # network can throw inside ChFi3d and the unwind wedges the process under
    # Rosetta, so the sculpted creases stay crisp by design.

    # Clearance cuts: ride over the chassis with a visible seam gap.
    blank -= Pos(0, s * 90, -88) * Cylinder(radius=43.5, height=70)  # pod dome
    blank -= Pos(0, s * 60, -86) * Box(84, 120, 44)  # yoke
    blank -= Pos(0, 0, -7) * Box(110, 126, 14)  # waist deck

    # Angled vent grooves on the front 45 deg facet.
    ux, uy = math.cos(math.radians(45)), math.sin(math.radians(45))
    for d in (-8.0, 0.0, 8.0):
        cx = 50.0 + d * ux + 2.5 * ux
        cy = s * (100.0 - d * uy + 2.5 * uy)
        blank -= Pos(cx, cy, -48) * Rot(0, 0, -s * 45.0) * Box(3.0, 8.0, 20.0)

    # Horizontal panel-line groove across the outer face.
    blank -= Pos(0, s * 112.8, -42) * Box(60.0, 4.0, 2.2)

    return styled(blank, f"pelvis_fairing_{tag}", SHELL_COLOR)


# ------------------------------------------------------------- crotch guard --

def _crotch_guard():
    # Faceted plate built in a local frame, then tilted and pushed to the
    # front of the yoke.
    p = Box(8, 46, 40)
    front_vert = (
        lambda g: chamfer(
            g.edges().filter_by(Axis.Z).filter_by_position(Axis.X, 3.9, 4.1),
            6.0,
        )
    )
    p = _safe(front_vert, p)
    p = _safe(
        lambda g: chamfer(
            g.edges()
            .filter_by(Axis.Y)
            .filter_by_position(Axis.Z, -20.1, -19.9)
            .filter_by_position(Axis.X, 0.0, 4.2),
            5.0,
        ),
        p,
    )
    p = _safe(
        lambda g: chamfer(
            g.edges()
            .filter_by(Axis.Y)
            .filter_by_position(Axis.Z, 19.9, 20.1)
            .filter_by_position(Axis.X, 0.0, 4.2),
            3.0,
        ),
        p,
    )
    guard = Pos(50, 0, -86) * Rot(0, 4, 0) * p
    # Base wedge filling the gap back to the yoke front face (x=38).
    guard += Pos(42.75, 0, -88) * Box(9.5, 40, 32)
    return styled(guard, "pelvis_crotch_guard", STRUCT_COLOR)


# ------------------------------------------------------------------- part ---

def build_pelvis():
    children = [
        _chassis(),
        _waist_ring(),
        _pod_rim(+1, "left"),
        _pod_rim(-1, "right"),
        _pod_collar(+1, "left"),
        _pod_collar(-1, "right"),
        _fairing(+1, "left"),
        _fairing(-1, "right"),
        _crotch_guard(),
    ]
    return part_compound("pelvis", children)


def gen_step():
    return build_pelvis()
