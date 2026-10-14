"""Parts for the 3D milling suites (``test_cam_milling3d_*.py``), built with build123d into a temporary directory.

* :func:`dome_step` (:data:`DOME`): a 60 x 60 x 8 mm plate on z = 0 with a boss Ø36 standing on it, its wall up to
  z = 20 and a spherical dome over it (sphere R30 centred on the axis at z = -4), top at z = 26.
* :func:`fillet_block_step` (:data:`FILLET_BLOCK`): a 50 x 40 x 20 block on z = 0 with its four top edges rounded R5.
* :func:`mould_step` (:data:`MOULD`): a 60 x 50 x 25 block on z = 0 with a cavity 36 x 26 x 10 deep from the top, its
  vertical corners rounded R5 and its floor edges R3.

Every part is centred in x and y. The job helper is :func:`mill3d_job` (GRBL, aluminium, a 6 mm flat T1, a 6 mm ball
T2, a 6 mm R1 bull T3 and a 2 mm ball T4).
"""

from __future__ import annotations

from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

DOME = {"plate": (60.0, 60.0, 8.0), "boss_diameter": 36.0, "wall_top": 20.0, "sphere_radius": 30.0,
        "sphere_z": -4.0, "top": 26.0}
FILLET_BLOCK = {"size": (50.0, 40.0, 20.0), "fillet": 5.0}
MOULD = {"size": (60.0, 50.0, 25.0), "cavity": (36.0, 26.0, 10.0), "corner": 5.0, "floor_fillet": 3.0}


def dome_z(r):
    """The dome's height at radius ``r`` from the axis (inside the boss)."""
    import numpy as np

    return DOME["sphere_z"] + np.sqrt(DOME["sphere_radius"] ** 2 - np.asarray(r, dtype=float) ** 2)


def dome_step(directory: Path, name: str = "dome") -> Path:
    from build123d import Align, Box, Cylinder, Pos, Sphere, export_step

    base = (Align.CENTER, Align.CENTER, Align.MIN)
    sx, sy, sz = DOME["plate"]
    plate = Box(sx, sy, sz, align=base)
    radius = DOME["boss_diameter"] / 2
    boss = Pos(0, 0, sz) * Cylinder(radius, DOME["top"] - sz + 1, align=base)
    dome = Pos(0, 0, DOME["sphere_z"]) * Sphere(DOME["sphere_radius"])
    part = plate + (boss & dome)
    path = directory / f"{name}.step"
    export_step(part, str(path))
    return path


def fillet_block_step(directory: Path, name: str = "fillet_block") -> Path:
    from build123d import Align, Axis, Box, export_step, fillet

    sx, sy, sz = FILLET_BLOCK["size"]
    block = Box(sx, sy, sz, align=(Align.CENTER, Align.CENTER, Align.MIN))
    top_edges = block.edges().group_by(Axis.Z)[-1]
    part = fillet(top_edges, FILLET_BLOCK["fillet"])
    path = directory / f"{name}.step"
    export_step(part, str(path))
    return path


def mould_step(directory: Path, name: str = "mould") -> Path:
    from build123d import Align, Axis, Box, Pos, export_step, fillet

    sx, sy, sz = MOULD["size"]
    cx, cy, depth = MOULD["cavity"]
    block = Box(sx, sy, sz, align=(Align.CENTER, Align.CENTER, Align.MIN))
    tool = Pos(0, 0, sz - depth) * Box(cx, cy, depth + 5, align=(Align.CENTER, Align.CENTER, Align.MIN))
    tool = fillet(tool.edges().filter_by(Axis.Z), MOULD["corner"])
    tool = fillet(tool.edges().group_by(Axis.Z)[0], MOULD["floor_fillet"])
    part = block - tool
    path = directory / f"{name}.step"
    export_step(part, str(path))
    return path


def mill3d_job(operations: list[dict], *, tools: list[dict] | None = None, stock: dict | None = None,
               setups: list[dict] | None = None, tolerance_mm: float | None = None) -> dict:
    job = {
        "machine": {"kind": "mill", "post": "grbl", "max_rpm": 24000, "travel_mm": [400, 300, 150]},
        "material": "aluminum-6061",
        "stock": stock or {"kind": "box", "margin_mm": [2, 2, 1]},
        "tools": tools or [
            {"id": "T1", "type": "flat", "diameter_mm": 6, "flutes": 3, "flute_length_mm": 30, "stickout_mm": 40},
            {"id": "T2", "type": "ball", "diameter_mm": 6, "flutes": 2, "flute_length_mm": 30, "stickout_mm": 40},
            {"id": "T3", "type": "bull", "diameter_mm": 6, "corner_radius_mm": 1, "flute_length_mm": 30,
             "stickout_mm": 40},
            {"id": "T4", "type": "ball", "diameter_mm": 2, "flute_length_mm": 12, "stickout_mm": 40,
             "shank_diameter_mm": 6},
        ],
        "setups": setups or [{"id": "top", "orientation": "+Z", "origin": "stock-top-center", "operations": operations}],
    }
    if tolerance_mm is not None:
        job["tolerance_mm"] = tolerance_mm
    return job
