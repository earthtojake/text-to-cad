"""Multi-axis fixtures for the CAM suites (``test_cam_multiaxis_*``): parts built with build123d in a temp directory.

* :func:`angled_block_step` (:data:`ANGLED`): a block 60 x 40 x 30 standing on z = 0, its top's +Y edge cut away by a
  face tilted 30° about X (normal ``(0, sin 30°, cos 30°)``), with a 16 x 8 pocket 3 mm deep sunk square into that
  face: a 3+2 job at ``a_deg`` 30.
* :func:`wrapped_cylinder_step` (:data:`CYLINDER`): a bar Ø30 along X from x = -30 to 30 with a ring groove 6 mm wide
  down to Ø22 at x = 0 and a flat 3 mm deep (z <= 12) from x = 8 to 24: a 4th-axis wrap.
* :func:`tapered_boss_step` (:data:`TAPER`): a plate 60 x 40 x 5 with a boss whose four walls lean in 15° from
  vertical, from 30 x 20 at z = 5 to the top at z = 17: swarf on its ruled walls.
* :func:`dome_step` (:data:`DOME`): a block 50 x 50 x 10 with a spherical cap R30 rising 8 mm over its top: a 5-axis
  finish along the surface normal.

Face refs come from ``cadgen.cam.features`` (:func:`face_ref`). Job helpers build the multi-axis machines.
"""

from __future__ import annotations

import math
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

ANGLED = {"size": (60.0, 40.0, 30.0), "tilt_deg": 30.0, "hinge": (5.0, 30.0), "pocket": (16.0, 8.0, 3.0),
          "pocket_y": 12.5}
CYLINDER = {"radius": 15.0, "length": 60.0, "groove": {"x": (-3.0, 3.0), "radius": 11.0},
            "flat": {"x": (8.0, 24.0), "z": 12.0}}
TAPER = {"plate": (60.0, 40.0, 5.0), "bottom": (30.0, 20.0), "height": 12.0, "lean_deg": 15.0}
DOME = {"block": (50.0, 50.0, 10.0), "radius": 30.0, "rise": 8.0}


def angled_normal() -> tuple[float, float, float]:
    t = math.radians(ANGLED["tilt_deg"])
    return (0.0, math.sin(t), math.cos(t))


def angled_pocket_centre() -> tuple[float, float, float]:
    """The pocket's mouth centre on the angled face (part mm)."""
    t = math.radians(ANGLED["tilt_deg"])
    y0, z0 = ANGLED["hinge"]
    y = ANGLED["pocket_y"]
    return (0.0, y, z0 - math.tan(t) * (y - y0))


def angled_block_step(directory: Path, name: str = "angled") -> Path:
    from build123d import Align, Box, Keep, Plane, export_step, split

    sx, sy, sz = ANGLED["size"]
    normal = angled_normal()
    y0, z0 = ANGLED["hinge"]
    block = Box(sx, sy, sz, align=(Align.CENTER, Align.CENTER, Align.MIN))
    part = split(block, bisect_by=Plane(origin=(0, y0, z0), z_dir=normal), keep=Keep.BOTTOM)
    px, py, depth = ANGLED["pocket"]
    mouth = Plane(origin=angled_pocket_centre(), x_dir=(1, 0, 0), z_dir=normal)
    part -= mouth * Box(px, py, 2 * depth, align=(Align.CENTER, Align.CENTER, Align.CENTER))
    path = directory / f"{name}.step"
    export_step(part, str(path))
    return path


def wrapped_cylinder_step(directory: Path, name: str = "bar") -> Path:
    from build123d import Align, Box, Cylinder, Pos, Rot, export_step

    r, length = CYLINDER["radius"], CYLINDER["length"]
    along_x = Rot(0, 90, 0)
    part = along_x * Cylinder(r, length)
    g0, g1 = CYLINDER["groove"]["x"]
    ring = along_x * (Cylinder(r + 2, g1 - g0) - Cylinder(CYLINDER["groove"]["radius"], g1 - g0))
    part -= Pos((g0 + g1) / 2, 0, 0) * ring
    f0, f1 = CYLINDER["flat"]["x"]
    flat_z = CYLINDER["flat"]["z"]
    part -= Pos((f0 + f1) / 2, 0, flat_z) * Box(f1 - f0, 2 * r + 4, r, align=(Align.CENTER, Align.CENTER, Align.MIN))
    path = directory / f"{name}.step"
    export_step(part, str(path))
    return path


def tapered_boss_step(directory: Path, name: str = "taper") -> Path:
    from build123d import Align, Box, Plane, Pos, Rectangle, export_step, loft

    px, py, pz = TAPER["plate"]
    bx, by = TAPER["bottom"]
    height = TAPER["height"]
    inset = math.tan(math.radians(TAPER["lean_deg"])) * height
    plate = Box(px, py, pz, align=(Align.CENTER, Align.CENTER, Align.MIN))
    boss = loft([Plane.XY.offset(pz) * Rectangle(bx, by), Plane.XY.offset(pz + height) * Rectangle(bx - 2 * inset,
                                                                                                    by - 2 * inset)])
    part = plate + boss
    path = directory / f"{name}.step"
    export_step(part, str(path))
    return path


def dome_step(directory: Path, name: str = "dome") -> Path:
    from build123d import Align, Box, Pos, Sphere, export_step

    bx, by, bz = DOME["block"]
    radius, rise = DOME["radius"], DOME["rise"]
    block = Box(bx, by, bz, align=(Align.CENTER, Align.CENTER, Align.MIN))
    cap = Pos(0, 0, bz + rise - radius) * Sphere(radius)
    cap &= Pos(0, 0, bz) * Box(bx, by, rise + 1, align=(Align.CENTER, Align.CENTER, Align.MIN))
    part = block + cap
    path = directory / f"{name}.step"
    export_step(part, str(path))
    return path


def face_ref(features, *, surface: str, near, normal=None, tolerance: float = 1.0) -> str:
    """The face of ``surface`` type whose centre is within ``tolerance`` mm of ``near`` (and whose plane normal is
    ``normal``, when given)."""
    import numpy as np

    best = None
    for face in features.faces:
        if face["surface"] != surface:
            continue
        if normal is not None and np.linalg.norm(np.asarray(face.get("normal", (9, 9, 9))) - normal) > 1e-3:
            continue
        distance = float(np.linalg.norm(np.asarray(face["center_mm"]) - np.asarray(near)))
        if distance <= tolerance and (best is None or distance < best[0]):
            best = (distance, face["ref"])
    if best is None:
        raise AssertionError(f"no {surface} face near {near}: "
                             f"{[(f['ref'], f['surface'], f['center_mm']) for f in features.faces]}")
    return best[1]


def multiaxis_job(operations: list[dict], *, kind: str = "mill4", orientation="+Z", tools: list[dict] | None = None,
                  stock: dict | None = None, machine: dict | None = None, post: str = "linuxcnc",
                  setups: list[dict] | None = None) -> dict:
    """A job on a mill4 (or mill5) with a 6 mm flat (T1) and a 4 mm ball (T2) by default."""
    return {
        "machine": {"kind": kind, "post": post, "max_rpm": 18000, **(machine or {})},
        "material": "aluminum-6061",
        "stock": stock or {"kind": "box", "margin_mm": [2, 2, 1]},
        "tools": tools or [
            {"id": "T1", "type": "flat", "diameter_mm": 6, "flutes": 3, "flute_length_mm": 20, "stickout_mm": 35},
            {"id": "T2", "type": "ball", "diameter_mm": 4, "flutes": 2, "flute_length_mm": 12, "stickout_mm": 30},
        ],
        "setups": setups or [{"id": "s1", "orientation": orientation, "origin": "stock-top-center",
                              "operations": operations}],
    }
