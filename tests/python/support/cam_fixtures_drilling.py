"""Parts for the drilling suites (``tests/python/packages/cadgen/cam/test_cam_drilling_*.py``), built with build123d
in a temporary directory (never ``models/``).

The drill plate (:func:`drill_plate_step`, :data:`PLATE`): 60 x 40 x 12 mm standing on z = 0, centred in x and y,
with

* four Ø5 through holes at (±24, ±14);
* two Ø6 blind holes 8 mm deep with a drawn 118° drill point below their floor, at (-14, -8) and (-6, -8);
* one Ø8 blind hole 6 mm deep with a flat floor at (-14, 8);
* one Ø6.8 through hole (the M8 tap drill) at (-6, 8);
* a 16 x 16 pocket 4 mm deep (floor z = 8) centred at (12, 0), with two Ø4 through holes in its floor at (8, -4)
  and (16, 4);
* one Ø4 blind hole 10 mm deep drilled in from the +X side, its axis at y = 0, z = 4.

The hole block (:func:`hole_block_step`, :data:`BLOCK`): 80 x 40 x 20 mm standing on z = 0, centred in x and y,
with

* a Ø5 through hole under a Ø9 x 4 counterbore at (-30, 12);
* a Ø5 through hole under a Ø10, 90° countersink at (-15, 12);
* a Ø6 blind hole 8 mm deep with a drawn 140° point at (0, 12), and a Ø6 blind hole 6 mm deep with a flat floor at
  (15, 12);
* a Ø8 cross bore along X right through the block at y = -12, z = 8, and a Ø5 hole down from the top at (-20, -12)
  that ends in it;
* a cave open to the +X side (x 15..40, y -6..6, z 4..10, under a 10 mm roof) with a Ø5 blind hole 3 mm deep in its
  floor at (28, 0).

The counterbore plate (:func:`counterbore_plate_step`, :data:`CBORE`): 60 x 40 x 12 mm standing on z = 0, centred in
x and y, every hole Ø10 and every counterbore Ø14 x 3, with

* a through hole counterbored at the top at (-18, 8);
* two through holes counterbored at the bottom (back counterbores, for a back bore from the top) at (18, 8) and
  (18, -10);
* a blind hole 8 mm deep (counterbore included: its flat floor at z = 4) counterbored at the top at (0, -10);
* a plain through hole, no counterbore, at (-18, -10).
"""

from __future__ import annotations

import math
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

PLATE = {
    "size": (60.0, 40.0, 12.0),
    "through5": ((-24.0, -14.0), (24.0, -14.0), (-24.0, 14.0), (24.0, 14.0)),
    "blind6": {"centers": ((-14.0, -8.0), (-6.0, -8.0)), "depth": 8.0, "point_angle": 118.0},
    "blind8": {"center": (-14.0, 8.0), "depth": 6.0},
    "through68": (-6.0, 8.0),
    "pocket": {"center": (12.0, 0.0), "size": (16.0, 16.0), "floor_z": 8.0, "holes": ((8.0, -4.0), (16.0, 4.0))},
    "side": {"diameter": 4.0, "depth": 10.0, "y": 0.0, "z": 4.0},
}


def drill_plate_step(directory: Path, name: str = "drill_plate") -> Path:
    from build123d import Align, Box, Cone, Cylinder, Pos, Rot, export_step

    base = (Align.CENTER, Align.CENTER, Align.MIN)
    sx, sy, sz = PLATE["size"]
    part = Box(sx, sy, sz, align=base)
    for x, y in PLATE["through5"]:
        part -= Pos(x, y, 0) * Cylinder(2.5, sz, align=base)
    blind = PLATE["blind6"]
    point = 3.0 / math.tan(math.radians(blind["point_angle"] / 2.0))
    floor = sz - blind["depth"]
    for x, y in blind["centers"]:
        part -= Pos(x, y, floor) * Cylinder(3.0, blind["depth"], align=base)
        part -= Pos(x, y, floor - point) * Cone(0.0, 3.0, point, align=base)
    x, y = PLATE["blind8"]["center"]
    part -= Pos(x, y, sz - PLATE["blind8"]["depth"]) * Cylinder(4.0, PLATE["blind8"]["depth"], align=base)
    x, y = PLATE["through68"]
    part -= Pos(x, y, 0) * Cylinder(3.4, sz, align=base)
    pocket = PLATE["pocket"]
    part -= Pos(*pocket["center"], pocket["floor_z"]) * Box(*pocket["size"], sz - pocket["floor_z"], align=base)
    for x, y in pocket["holes"]:
        part -= Pos(x, y, 0) * Cylinder(2.0, pocket["floor_z"], align=base)
    side = PLATE["side"]
    part -= Pos(sx / 2 - side["depth"] / 2, side["y"], side["z"]) * Rot(0, 90, 0) * Cylinder(side["diameter"] / 2,
                                                                                               side["depth"])
    path = directory / f"{name}.step"
    export_step(part, str(path))
    return path


BLOCK = {
    "size": (80.0, 40.0, 20.0),
    "counterbore": {"center": (-30.0, 12.0), "diameter": 5.0, "bore": 9.0, "bore_depth": 4.0},
    "countersink": {"center": (-15.0, 12.0), "diameter": 5.0, "sink": 10.0, "angle": 90.0},
    "pointed": {"center": (0.0, 12.0), "diameter": 6.0, "depth": 8.0, "point_angle": 140.0},
    "flat": {"center": (15.0, 12.0), "diameter": 6.0, "depth": 6.0},
    "cross": {"y": -12.0, "z": 8.0, "diameter": 8.0, "down": (-20.0, -12.0), "down_diameter": 5.0},
    "cave": {"x": (15.0, 40.0), "y": (-6.0, 6.0), "z": (4.0, 10.0), "hole": (28.0, 0.0), "diameter": 5.0,
             "depth": 3.0},
}


def hole_block_step(directory: Path, name: str = "hole_block") -> Path:
    from build123d import Align, Box, Cone, Cylinder, Pos, Rot, export_step

    base = (Align.CENTER, Align.CENTER, Align.MIN)
    sx, sy, sz = BLOCK["size"]
    part = Box(sx, sy, sz, align=base)
    cb = BLOCK["counterbore"]
    part -= Pos(*cb["center"], 0) * Cylinder(cb["diameter"] / 2, sz, align=base)
    part -= Pos(*cb["center"], sz - cb["bore_depth"]) * Cylinder(cb["bore"] / 2, cb["bore_depth"], align=base)
    cs = BLOCK["countersink"]
    part -= Pos(*cs["center"], 0) * Cylinder(cs["diameter"] / 2, sz, align=base)
    sink = (cs["sink"] - cs["diameter"]) / 2 / math.tan(math.radians(cs["angle"] / 2))
    part -= Pos(*cs["center"], sz - sink) * Cone(cs["diameter"] / 2, cs["sink"] / 2, sink, align=base)
    pt = BLOCK["pointed"]
    point = pt["diameter"] / 2 / math.tan(math.radians(pt["point_angle"] / 2))
    part -= Pos(*pt["center"], sz - pt["depth"]) * Cylinder(pt["diameter"] / 2, pt["depth"], align=base)
    part -= Pos(*pt["center"], sz - pt["depth"] - point) * Cone(0.0, pt["diameter"] / 2, point, align=base)
    fl = BLOCK["flat"]
    part -= Pos(*fl["center"], sz - fl["depth"]) * Cylinder(fl["diameter"] / 2, fl["depth"], align=base)
    cr = BLOCK["cross"]
    part -= Pos(0, cr["y"], cr["z"]) * Rot(0, 90, 0) * Cylinder(cr["diameter"] / 2, sx)
    part -= Pos(*cr["down"], cr["z"]) * Cylinder(cr["down_diameter"] / 2, sz - cr["z"], align=base)
    cave = BLOCK["cave"]
    (x0, x1), (y0, y1), (z0, z1) = cave["x"], cave["y"], cave["z"]
    part -= Pos((x0 + x1) / 2, (y0 + y1) / 2, z0) * Box(x1 - x0, y1 - y0, z1 - z0, align=base)
    part -= Pos(*cave["hole"], z0 - cave["depth"]) * Cylinder(cave["diameter"] / 2, cave["depth"], align=base)
    path = directory / f"{name}.step"
    export_step(part, str(path))
    return path


CBORE = {
    "size": (60.0, 40.0, 12.0),
    "diameter": 10.0,
    "bore": 14.0,
    "bore_depth": 3.0,
    "top": (-18.0, 8.0),
    "back": ((18.0, 8.0), (18.0, -10.0)),
    "blind": {"center": (0.0, -10.0), "depth": 8.0},
    "plain": (-18.0, -10.0),
}


def counterbore_plate_step(directory: Path, name: str = "counterbore_plate") -> Path:
    from build123d import Align, Box, Cylinder, Pos, export_step

    base = (Align.CENTER, Align.CENTER, Align.MIN)
    sx, sy, sz = CBORE["size"]
    r, rb, depth = CBORE["diameter"] / 2, CBORE["bore"] / 2, CBORE["bore_depth"]
    part = Box(sx, sy, sz, align=base)
    for x, y in (CBORE["top"], *CBORE["back"], CBORE["plain"]):
        part -= Pos(x, y, 0) * Cylinder(r, sz, align=base)
    part -= Pos(*CBORE["top"], sz - depth) * Cylinder(rb, depth, align=base)
    for x, y in CBORE["back"]:
        part -= Pos(x, y, 0) * Cylinder(rb, depth, align=base)
    blind = CBORE["blind"]
    part -= Pos(*blind["center"], sz - blind["depth"]) * Cylinder(r, blind["depth"], align=base)
    part -= Pos(*blind["center"], sz - depth) * Cylinder(rb, depth, align=base)
    path = directory / f"{name}.step"
    export_step(part, str(path))
    return path


def drill_job(operations: list[dict], *, tools: list[dict] | None = None, post: str = "grbl",
              setups: list[dict] | None = None, material: str = "aluminum-6061", machine: dict | None = None) -> dict:
    """A 3-axis job: T1 a 5 mm drill, T2 a 6 mm drill, T3 an M6x1 tap, T4 a 6 mm spot drill, T5 a 6 mm reamer,
    T6 an 8 mm boring bar, T7 a 4 mm drill (stock 2 mm round, 1 mm over the top). ``machine`` adds machine keys."""
    return {
        "machine": {"kind": "mill", "post": post, "max_rpm": 24000, "travel_mm": [300, 200, 80], **(machine or {})},
        "material": material,
        "stock": {"kind": "box", "margin_mm": [2, 2, 1]},
        "tools": tools or [
            {"id": "T1", "type": "drill", "diameter_mm": 5},
            {"id": "T2", "type": "drill", "diameter_mm": 6},
            {"id": "T3", "type": "tap", "diameter_mm": 6, "pitch_mm": 1},
            {"id": "T4", "type": "spot", "diameter_mm": 6},
            {"id": "T5", "type": "reamer", "diameter_mm": 6},
            {"id": "T6", "type": "boring", "diameter_mm": 8},
            {"id": "T7", "type": "drill", "diameter_mm": 4},
        ],
        "setups": setups or [{"id": "top", "orientation": "+Z", "origin": "stock-top-center",
                              "operations": operations}],
    }


def hole_faces(features, diameter: float, *, axis: str = "+Z") -> list[str]:
    """One wall face of every hole of ``diameter`` along ``axis`` (a features() result)."""
    return [hole["faces"][0] for hole in features.holes
            if abs(hole["diameter_mm"] - diameter) < 1e-3 and hole["axis_word"] == axis]
