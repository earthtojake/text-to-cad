"""juno torso/chest.

Local frame: origin at the waist-yaw joint center (bottom of torso),
+X forward, +Y robot-left, +Z up. Units mm.

Locked interfaces (do not change):
- nothing below z=+2; graphite waist collar dia 100 spans z 2..36
- chest volume z 36..320, |y| <= 118, x -78..+82
- shoulder bosses: ALU cylinders along Y at (0, +-y, 290), |y| 112..132, dia 76
- neck: ALU collar dia 52, z 318..324; z > 324 kept clear within r < 40
- top deck <= z 330

Construction: a graphite lofted core plus a 5 mm conformal shell ring
(outer loft minus inner loft). Ice-gray armor panels are pieces of that
ring clipped by rounded region boxes, so every seam is a 5 mm-deep
recess exposing the graphite core (G1-style two-tone panel lines).
"""

from __future__ import annotations

import math  # noqa: F401  (kept for parity with sibling part modules)

import build123d as bd

from .juno_lib import (
    ALU,
    SHELL,
    STRUCT,
    VISOR,
    part_compound,
    styled,
)

# Loft sections: (z, depth_x, width_y, corner_r, center_x).
# Front line bulges to x=+78 at the chest and pulls back at the top for a
# slightly forward-leaning athletic silhouette; width V-tapers 148 -> 222.
_OUTER = [
    (36.0, 104.0, 132.0, 22.0, 2.0),
    (90.0, 112.0, 150.0, 26.0, 5.0),
    (160.0, 122.0, 172.0, 30.0, 9.0),
    (225.0, 132.0, 196.0, 33.0, 12.0),
    (272.0, 138.0, 216.0, 35.0, 9.0),
    (300.0, 132.0, 222.0, 36.0, 6.0),
    (310.0, 124.0, 210.0, 34.0, 4.0),
]
_SHELL_T = 5.0
_INNER = [
    (z, d - 2 * _SHELL_T, w - 2 * _SHELL_T, r - _SHELL_T, cx)
    for (z, d, w, r, cx) in _OUTER
]


def _loft_solid(specs):
    sections = [
        bd.Plane.XY.offset(z) * bd.Pos(cx, 0, 0) * bd.RectangleRounded(d, w, r)
        for (z, d, w, r, cx) in specs
    ]
    return bd.loft(sections)


def _safe_fillet(solid, edges, radius):
    try:
        return bd.fillet(edges, radius)
    except Exception:
        return solid


def _safe_chamfer(solid, edges, length):
    try:
        return bd.chamfer(edges, length)
    except Exception:
        return solid


def _region(size, center, radius):
    """Clip volume with rounded Y/Z seam corners (edges along X filleted)."""
    box = bd.Pos(*center) * bd.Box(*size)
    try:
        box = bd.fillet(box.edges().filter_by(bd.Axis.X), radius)
    except Exception:
        pass
    return box


def _clip_panel(ring, region):
    piece = ring & region
    solids = piece.solids()
    if len(solids) > 1:
        piece = solids.sort_by(bd.SortBy.VOLUME)[-1]
    return _safe_fillet(piece, piece.edges(), 1.0)


def build_torso():
    children = []

    # --- graphite waist collar (locked: dia 100, z 2..36) ----------------
    collar = bd.Pos(0, 0, 19) * bd.Cylinder(radius=50, height=34)
    collar = _safe_chamfer(collar, collar.edges(), 2.0)
    for zc in (9.0, 27.0):
        groove = bd.Pos(0, 0, zc) * (
            bd.Cylinder(radius=52, height=2.4) - bd.Cylinder(radius=48, height=2.4)
        )
        collar = collar - groove
    children.append(styled(collar, "torso_waist_collar", STRUCT))

    # --- graphite core + shoulder gusset barrels --------------------------
    outer = _loft_solid(_OUTER)
    inner = _loft_solid(_INNER)
    ring = outer - inner

    core = inner
    for sgn in (1.0, -1.0):
        gusset = bd.Pos(0, sgn * 100.0, 290) * bd.Rot(-90, 0, 0) * bd.Cylinder(
            radius=40, height=24
        )
        gusset = _safe_chamfer(gusset, gusset.edges(), 1.5)
        core = core + gusset

    # side intake louvres: three slanted grooves cut into each flank
    for sgn in (1.0, -1.0):
        for xc in (-14.0, 4.0, 22.0):
            slot = bd.Pos(xc, sgn * 90.0, 205) * bd.Rot(0, -12, 0) * bd.Box(9, 14, 64)
            core = core - slot

    # upper-chest sensor pocket (flat floor at x = 59)
    pocket = bd.Pos(69.5, 0, 302) * bd.Box(21, 48, 11)
    core = core - pocket
    children.append(styled(core, "torso_core", STRUCT))

    # gloss-black sensor bar recessed in the pocket
    sensor = bd.Pos(61.5, 0, 301.5) * bd.Box(5, 44, 8)
    sensor = _safe_fillet(sensor, sensor.edges().filter_by(bd.Axis.X), 2.0)
    children.append(styled(sensor, "torso_chest_sensor", VISOR))

    # --- ice-gray armor panels (conformal ring pieces) --------------------
    # twin pectoral plates with a 10 mm center crease
    for sgn, tag in ((1.0, "l"), (-1.0, "r")):
        pec = _clip_panel(
            ring, _region((95, 68, 146), (47.5, sgn * 39.0, 223), 12)
        )
        children.append(styled(pec, f"torso_pec_panel_{tag}", SHELL))

    # abdomen plate below an 8 mm horizontal reveal
    abdomen = _clip_panel(ring, _region((95, 90, 92), (47.5, 0, 98), 10))
    children.append(styled(abdomen, "torso_abdomen_panel", SHELL))

    # thin backpack panels either side of the graphite spine column
    for sgn, tag in ((1.0, "l"), (-1.0, "r")):
        back = _clip_panel(
            ring, _region((65, 45, 220), (-62.5, sgn * 35.5, 180), 10)
        )
        children.append(styled(back, f"torso_back_panel_{tag}", SHELL))

    # slim graphite spine column, flush with the back panels
    spine = _clip_panel(ring, _region((65, 16, 258), (-62.5, 0, 173), 6))
    children.append(styled(spine, "torso_spine_column", STRUCT))

    # --- top deck + neck collar -------------------------------------------
    deck_specs = [
        (310.0, 110.0, 170.0, 30.0, 4.0),
        (318.0, 110.0, 170.0, 30.0, 4.0),
    ]
    deck = _loft_solid(deck_specs)
    deck = _safe_chamfer(deck, deck.edges().group_by(bd.Axis.Z)[-1], 2.5)
    children.append(styled(deck, "torso_top_deck", SHELL))

    neck = bd.Pos(0, 0, 321) * bd.Cylinder(radius=26, height=6)
    neck = _safe_chamfer(neck, neck.edges().group_by(bd.Axis.Z)[-1], 1.0)
    children.append(styled(neck, "torso_neck_collar", ALU))

    # --- aluminum shoulder bosses (locked: dia 76, |y| 112..132) ----------
    for sgn, tag in ((1.0, "l"), (-1.0, "r")):
        boss = bd.Pos(0, sgn * 122.0, 290) * bd.Rot(-90, 0, 0) * bd.Cylinder(
            radius=38, height=20
        )
        boss = _safe_chamfer(boss, boss.edges(), 2.0)
        groove = bd.Pos(0, sgn * 126.0, 290) * bd.Rot(-90, 0, 0) * (
            bd.Cylinder(radius=39, height=2.5) - bd.Cylinder(radius=36.5, height=2.5)
        )
        boss = boss - groove
        children.append(styled(boss, f"torso_shoulder_boss_{tag}", ALU))

    return part_compound("torso", children)
