"""juno humanoid - arm segment builders (bicep, forearm).

Local frames (units mm, robot faces +X, +Y robot-left, +Z up):
- bicep:   origin = shoulder-yaw joint center at the TOP of the bicep,
           segment extends down -Z; elbow axis = Y through (0, 0, -156).
- forearm: origin = elbow joint center; wrist-roll seam at z = -150.

Styling: graphite structural core with ice-gray clamshell panels split
front/back (graphite reveal strips on the +-Y sides), machined-aluminum
joint rims, exposed cylindrical elbow actuator.
"""

from __future__ import annotations

import math  # noqa: F401  (kept per module convention)

import build123d as bd

from .juno_lib import (
    ALU,
    SHELL,
    STRUCT,
    actuator_solids,
    part_compound,
    styled,
)


# ---------------------------------------------------------------- helpers


def _loft(specs):
    """Loft elliptical sections; specs = [(z, half_x, half_y), ...]."""
    return bd.loft([bd.Plane.XY.offset(z) * bd.Ellipse(rx, ry) for z, rx, ry in specs])


def _try_fillet(solid, edges, radius):
    try:
        return bd.fillet(edges, radius)
    except Exception:
        return solid


def _try_chamfer(solid, edges, length):
    try:
        return bd.chamfer(edges, length)
    except Exception:
        return solid


def _soften_reveal(solid, seam_x, radius=0.8):
    """Break every edge of a clamshell panel with a small fillet.

    (Historical note: this used to fillet only the reveal-face edges,
    because filleting across the elliptical loft's parametric seam left the
    outer face's UV ~1e-8 outside its knot domain and the surface
    extractor's 1e-9 UV guard rejected the part. That guard is 1e-6 now, so
    the blanket fillet extracts fine.)
    """
    del seam_x
    return _try_fillet(solid, solid.edges(), radius)


def _ring_groove(solid, z, r_out, depth=0.9, width=1.5):
    """Shallow machined groove around a Z-axis ring at height z."""
    try:
        g = bd.Pos(0, 0, z) * (
            bd.Cylinder(radius=r_out + 1.0, height=width)
            - bd.Cylinder(radius=r_out - depth, height=width)
        )
        return solid - g
    except Exception:
        return solid


def _y_cyl(y_center, z_center, radius, height):
    """Cylinder whose axis is Y, centered at (0, y_center, z_center)."""
    return bd.Pos(0, y_center, z_center) * bd.Rot(-90, 0, 0) * bd.Cylinder(
        radius=radius, height=height
    )


# ---------------------------------------------------------------- bicep


def build_bicep(side: str):
    s = 1.0 if side == "left" else -1.0
    p = f"bicep_{side}"
    solids = []

    # -- shoulder-yaw rotation ring (LOCKED: dia 56, z 0..-10) --
    ring = bd.Pos(0, 0, -5.0) * bd.Cylinder(radius=28.0, height=10.0)
    ring = _try_chamfer(ring, ring.edges(), 0.8)
    solids.append(styled(ring, f"{p}_yaw_ring", ALU))

    # -- upper-arm capsule: graphite core + clamshell panels (dia ~54 -> 46) --
    outer_specs = [
        (-10.0, 26.5, 26.5),
        (-44.0, 27.4, 27.4),
        (-78.0, 25.2, 25.2),
        (-106.0, 23.0, 23.0),
    ]
    core_specs = [(z, rx - 2.5, ry - 2.5) for z, rx, ry in outer_specs]
    core = _loft(core_specs)
    outer = _loft(outer_specs)
    blank = outer - core
    seam = 3.2  # graphite reveal half-width on each side
    front = blank & (bd.Pos(45.0 + seam, 0, -58.0) * bd.Box(90, 90, 130))
    rear = blank & (bd.Pos(-45.0 - seam, 0, -58.0) * bd.Box(90, 90, 130))
    front = _try_fillet(front, front.edges(), 0.8)
    rear = _try_fillet(rear, rear.edges(), 0.8)
    solids.append(styled(core, f"{p}_core", STRUCT))
    solids.append(styled(front, f"{p}_shell_front", SHELL))
    solids.append(styled(rear, f"{p}_shell_rear", SHELL))

    # -- distal elbow fork (LOCKED: axis Y @ (0,0,-156), plates |y| 28..36,
    #    bosses dia 44 @ (0,+-32,-156), blends in by z -110) --
    trans = bd.loft(
        [
            bd.Plane.XY.offset(-108.0) * bd.Circle(22.9),
            bd.Plane.XY.offset(-120.0) * bd.RectangleRounded(44.0, 54.0, 14.0),
            bd.Plane.XY.offset(-132.0) * bd.RectangleRounded(50.0, 72.0, 10.0),
        ]
    )
    fork = trans
    for ys in (1.0, -1.0):
        slab = bd.Pos(0, ys * 32.0, -144.0) * bd.Box(50.0, 8.0, 24.0)
        # soften plate edges on the primitives (post-boolean chamfers on this
        # shape hang OCC, so detail is applied before fusing)
        slab = _try_fillet(slab, slab.edges().filter_by(bd.Axis.Y), 2.0)
        tip = _y_cyl(ys * 32.0, -156.0, 25.0, 8.0)
        tip = _try_chamfer(tip, tip.edges(), 1.0)
        fork = fork + slab + tip
    # clearance arch for the forearm elbow can (dia 62 + margin, |y|<=27.2)
    fork = fork - _y_cyl(0.0, -156.0, 34.0, 54.4)
    # through-bores for the aluminum joint bosses
    for ys in (1.0, -1.0):
        fork = fork - _y_cyl(ys * 32.0, -156.0, 22.05, 8.4)
    solids.append(styled(fork, f"{p}_fork", STRUCT))

    # -- aluminum elbow bosses (LOCKED dia 44 at (0,+-32,-156)) --
    for ys in (1.0, -1.0):
        tag = "outboard" if ys * s > 0 else "inboard"
        body = _y_cyl(ys * 32.0, -156.0, 21.9, 8.0)
        lip = _y_cyl(ys * 37.0, -156.0, 16.0, 2.0)
        boss = body + lip
        boss = _try_chamfer(boss, boss.edges(), 0.8)
        solids.append(styled(boss, f"{p}_elbow_boss_{tag}", ALU))

    return part_compound(p, solids)


# ---------------------------------------------------------------- forearm


def build_forearm(side: str):
    s = 1.0 if side == "left" else -1.0
    p = f"forearm_{side}"
    solids = []

    # -- exposed elbow actuator (LOCKED: dia 62, len 50, axis Y) --
    # output hub faces outboard (+y on left, -y on right)
    act = actuator_solids(f"{p}_elbow", 62.0, 50.0, center=(0, 0, 0), axis=(0, s, 0))
    can, rest = act[0], act[1:]
    solids.extend(rest)

    # -- graphite chassis: yoke wrapping the can, tapering to a wrist flare --
    core_specs = [
        (-4.0, 24.0, 16.0),
        (-26.0, 26.0, 18.0),
        (-72.0, 19.0, 14.5),
        (-112.0, 15.5, 12.5),
        (-126.0, 15.2, 12.4),
    ]
    flare = bd.loft(
        [
            bd.Plane.XY.offset(-126.0) * bd.Ellipse(15.2, 12.4),
            bd.Plane.XY.offset(-140.0) * bd.Ellipse(19.0, 19.0),
        ]
    )
    chassis = can + _loft(core_specs) + flare
    solids.append(styled(chassis, f"{p}_chassis", STRUCT))

    # -- ice-gray clamshell panels over the chassis --
    outer_specs = [
        (-26.0, 28.5, 20.5),
        (-72.0, 21.5, 17.0),
        (-112.0, 18.0, 15.0),
        (-124.0, 17.6, 14.7),
    ]
    blank = _loft(outer_specs) - chassis
    # wrap the panel tops around the actuator with a 2.5mm reveal
    blank = blank - _y_cyl(0.0, 0.0, 33.5, 80.0)
    seam = 3.0
    front = blank & (bd.Pos(45.0 + seam, 0, -76.0) * bd.Box(90, 80, 110))
    rear = blank & (bd.Pos(-45.0 - seam, 0, -76.0) * bd.Box(90, 80, 110))
    front = _soften_reveal(front, seam)
    rear = _soften_reveal(rear, -seam)
    solids.append(styled(front, f"{p}_shell_front", SHELL))
    solids.append(styled(rear, f"{p}_shell_rear", SHELL))

    # -- wrist-roll collar (LOCKED: dia 44, z -140..-150) --
    collar = bd.Pos(0, 0, -145.0) * bd.Cylinder(radius=22.0, height=10.0)
    collar = _try_chamfer(collar, collar.edges(), 0.8)
    solids.append(styled(collar, f"{p}_wrist_collar", ALU))

    return part_compound(p, solids)
