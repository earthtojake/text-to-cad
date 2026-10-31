"""Shared fixtures for the CAM suites (``tests/python/packages/cadgen/cam/``).

Parts are built with build123d into a temporary directory per test class (never ``models/``), and :func:`mill_job`
builds the dicts the suites plan. Heavy imports stay inside the helpers. :data:`needs_freecad` skips a test where
no FreeCAD is installed (``CADGEN_FREECAD`` names one that is not on PATH).

The block (:func:`block_step`, :data:`BLOCK`): 80 x 60 x 25 mm standing on z = 0, centred in x and y, with a stepped
pocket (an upper step 50 x 40 down to z = 17, a lower step 24 x 20 centred at x = -10 down to z = 11), a round
island Ø8 at (14, 0) rising from the upper floor to the top, and four Ø5 through holes at (±33, ±23).

The hole block (:func:`hole_block_step`, :data:`HOLE_BLOCK`): 80 x 40 x 20 mm, a counterbored, a countersunk, a
pointed and a flat-floored hole, a cross bore with a hole down into it, and a hole in the floor of a cave open to +X.

The bridge (:func:`bridge_step`, :data:`BRIDGE`): 60 x 40 x 20 mm with a 30 x 20 pocket down to z = 8 and a bar 8 mm
wide across it from z = 15 to the top: a quarter of the pocket's floor is under the bar.

The plate (:func:`plate_step`, :data:`PLATE`): 80 x 60 x 8 mm with a Ø22.2 bore and a 5.5 mm slot through it (too
wide to drill: an inside profile cuts them), a 20 x 12 pocket down to z = 4 and a flat-floored Ø6 hole down to z = 4.

The T-slot (:func:`tslot_step`, :data:`TSLOT`): 60 x 40 x 20 mm with a slot 6 mm wide down from the top to z = 10 and
under it one 14 mm wide from z = 4 to 10, both along X: the wide slot's walls are under the narrow one's lips.
"""

from __future__ import annotations

import io
import json
import math
import struct
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal.cam.freecad import FreecadMissingError, find_freecad  # noqa: E402

try:
    find_freecad()
    HAVE_FREECAD = True
except FreecadMissingError:
    HAVE_FREECAD = False

needs_freecad = unittest.skipUnless(HAVE_FREECAD, "FreeCAD 1.1 (freecadcmd) is not installed")

#: The block's numbers, for assertions.
BLOCK = {
    "size": (80.0, 60.0, 25.0),
    "upper": {"size": (50.0, 40.0), "center": (0.0, 0.0), "floor_z": 17.0},
    "lower": {"size": (24.0, 20.0), "center": (-10.0, 0.0), "floor_z": 11.0},
    "island": {"center": (14.0, 0.0), "diameter": 8.0},
    "holes": {"diameter": 5.0, "centers": ((-33.0, -23.0), (33.0, -23.0), (-33.0, 23.0), (33.0, 23.0))},
}
HOLE_BLOCK = {
    "size": (80.0, 40.0, 20.0),
    "counterbore": {"center": (-30.0, 12.0), "diameter": 5.0, "bore": 9.0, "bore_depth": 4.0},
    "countersink": {"center": (-15.0, 12.0), "diameter": 5.0, "sink": 10.0, "angle": 90.0},
    "pointed": {"center": (0.0, 12.0), "diameter": 6.0, "depth": 8.0, "point_angle": 140.0},
    "flat": {"center": (15.0, 12.0), "diameter": 6.0, "depth": 6.0},
    "cross": {"y": -12.0, "z": 8.0, "diameter": 8.0, "down": (-20.0, -12.0), "down_diameter": 5.0},
    "cave": {"x": (15.0, 40.0), "y": (-6.0, 6.0), "z": (4.0, 10.0), "hole": (28.0, 0.0), "diameter": 5.0,
             "depth": 3.0},
}
BRIDGE = {"size": (60.0, 40.0, 20.0), "pocket": (30.0, 20.0), "floor_z": 8.0, "bar": 8.0, "bar_z": 15.0}
PLATE = {"size": (80.0, 60.0, 8.0), "bore": {"center": (0.0, 0.0), "diameter": 22.2},
         "slot": {"center": (25.0, 15.0), "length": 12.0, "width": 5.5},
         "pocket": {"center": (-25.0, 15.0), "size": (20.0, 12.0), "floor_z": 4.0},
         "blind": {"center": (-25.0, -18.0), "diameter": 6.0, "floor_z": 4.0}}
TSLOT = {"size": (60.0, 40.0, 20.0), "neck": {"width": 6.0, "z": (10.0, 20.0)}, "head": {"width": 14.0, "z": (4.0, 10.0)}}


def class_directory(cls) -> Path:
    """A temporary directory for a TestCase class's fixtures, removed after its last test."""
    tmp = tempfile.TemporaryDirectory(prefix="cam-")
    cls.addClassCleanup(tmp.cleanup)
    return Path(tmp.name)


@contextmanager
def quiet():
    with redirect_stderr(io.StringIO()):
        yield


def _base():
    from build123d import Align

    return (Align.CENTER, Align.CENTER, Align.MIN)


def block_step(directory: Path, name: str = "block") -> Path:
    from build123d import Box, Cylinder, Pos, export_step

    base = _base()
    sx, sy, sz = BLOCK["size"]
    part = Box(sx, sy, sz, align=base)
    upper, lower, island = BLOCK["upper"], BLOCK["lower"], BLOCK["island"]
    part -= Pos(*upper["center"], upper["floor_z"]) * Box(*upper["size"], sz - upper["floor_z"], align=base)
    part -= Pos(*lower["center"], lower["floor_z"]) * Box(*lower["size"], upper["floor_z"] - lower["floor_z"], align=base)
    part += Pos(*island["center"], upper["floor_z"]) * Cylinder(island["diameter"] / 2, sz - upper["floor_z"], align=base)
    for x, y in BLOCK["holes"]["centers"]:
        part -= Pos(x, y, 0) * Cylinder(BLOCK["holes"]["diameter"] / 2, sz, align=base)
    path = directory / f"{name}.step"
    export_step(part, str(path))
    return path


def hole_block_step(directory: Path, name: str = "hole_block") -> Path:
    from build123d import Box, Cone, Cylinder, Pos, Rot, export_step

    base = _base()
    sx, sy, sz = HOLE_BLOCK["size"]
    part = Box(sx, sy, sz, align=base)
    cb = HOLE_BLOCK["counterbore"]
    part -= Pos(*cb["center"], 0) * Cylinder(cb["diameter"] / 2, sz, align=base)
    part -= Pos(*cb["center"], sz - cb["bore_depth"]) * Cylinder(cb["bore"] / 2, cb["bore_depth"], align=base)
    cs = HOLE_BLOCK["countersink"]
    part -= Pos(*cs["center"], 0) * Cylinder(cs["diameter"] / 2, sz, align=base)
    sink = (cs["sink"] - cs["diameter"]) / 2 / math.tan(math.radians(cs["angle"] / 2))
    part -= Pos(*cs["center"], sz - sink) * Cone(cs["diameter"] / 2, cs["sink"] / 2, sink, align=base)
    pt = HOLE_BLOCK["pointed"]
    point = pt["diameter"] / 2 / math.tan(math.radians(pt["point_angle"] / 2))
    part -= Pos(*pt["center"], sz - pt["depth"]) * Cylinder(pt["diameter"] / 2, pt["depth"], align=base)
    part -= Pos(*pt["center"], sz - pt["depth"] - point) * Cone(0.0, pt["diameter"] / 2, point, align=base)
    fl = HOLE_BLOCK["flat"]
    part -= Pos(*fl["center"], sz - fl["depth"]) * Cylinder(fl["diameter"] / 2, fl["depth"], align=base)
    cr = HOLE_BLOCK["cross"]
    part -= Pos(0, cr["y"], cr["z"]) * Rot(0, 90, 0) * Cylinder(cr["diameter"] / 2, sx)
    part -= Pos(*cr["down"], cr["z"]) * Cylinder(cr["down_diameter"] / 2, sz - cr["z"], align=base)
    cave = HOLE_BLOCK["cave"]
    (x0, x1), (y0, y1), (z0, z1) = cave["x"], cave["y"], cave["z"]
    part -= Pos((x0 + x1) / 2, (y0 + y1) / 2, z0) * Box(x1 - x0, y1 - y0, z1 - z0, align=base)
    part -= Pos(*cave["hole"], z0 - cave["depth"]) * Cylinder(cave["diameter"] / 2, cave["depth"], align=base)
    path = directory / f"{name}.step"
    export_step(part, str(path))
    return path


def bridge_step(directory: Path, name: str = "bridge") -> Path:
    from build123d import Box, Pos, export_step

    base = _base()
    sx, sy, sz = BRIDGE["size"]
    part = Box(sx, sy, sz, align=base)
    part -= Pos(0, 0, BRIDGE["floor_z"]) * Box(*BRIDGE["pocket"], sz - BRIDGE["floor_z"], align=base)
    part += Pos(0, 0, BRIDGE["bar_z"]) * Box(BRIDGE["bar"], sy, sz - BRIDGE["bar_z"], align=base)
    path = directory / f"{name}.step"
    export_step(part, str(path))
    return path


def plate_step(directory: Path, name: str = "plate") -> Path:
    from build123d import Box, Cylinder, Pos, SlotCenterToCenter, export_step, extrude

    base = _base()
    sx, sy, sz = PLATE["size"]
    part = Box(sx, sy, sz, align=base)
    part -= Pos(*PLATE["bore"]["center"], 0) * Cylinder(PLATE["bore"]["diameter"] / 2, sz, align=base)
    slot = PLATE["slot"]
    part -= Pos(*slot["center"], 0) * extrude(SlotCenterToCenter(slot["length"], slot["width"]), sz)
    pocket = PLATE["pocket"]
    part -= Pos(*pocket["center"], pocket["floor_z"]) * Box(*pocket["size"], sz - pocket["floor_z"], align=base)
    blind = PLATE["blind"]
    part -= Pos(*blind["center"], blind["floor_z"]) * Cylinder(blind["diameter"] / 2, sz - blind["floor_z"], align=base)
    path = directory / f"{name}.step"
    export_step(part, str(path))
    return path


def tslot_step(directory: Path, name: str = "tslot") -> Path:
    from build123d import Box, Pos, export_step

    base = _base()
    sx, sy, sz = TSLOT["size"]
    part = Box(sx, sy, sz, align=base)
    for key in ("neck", "head"):
        low, high = TSLOT[key]["z"]
        part -= Pos(0, 0, low) * Box(sx, TSLOT[key]["width"], high - low, align=base)
    path = directory / f"{name}.step"
    export_step(part, str(path))
    return path


def mill_job(operations: list[dict], *, tools: list[dict] | None = None, stock: dict | None = None,
             machine: dict | None = None, material: str = "aluminum-6061", setups: list[dict] | None = None) -> dict:
    """A 3-axis job on LinuxCNC with a 6 mm three-flute flat (T1) and a 5 mm drill (T2) by default."""
    return {
        "machine": machine or {"post": "linuxcnc", "max_rpm": 24000, "travel_mm": [300, 200, 80]},
        "material": material,
        "stock": stock or {"margin_mm": [2, 2, 1]},
        "tools": tools or [
            {"id": "T1", "type": "flat", "number": 1, "diameter_mm": 6, "flutes": 3, "flute_length_mm": 20,
             "stickout_mm": 30, "shank_diameter_mm": 6},
            {"id": "T2", "type": "drill", "number": 2, "diameter_mm": 5, "flute_length_mm": 50, "stickout_mm": 60,
             "point_angle": 118},
        ],
        "setups": setups or [{"id": "top", "operations": operations}],
    }


def floor_ref(features, z: float) -> str:
    """The +Z floor at height ``z`` (a features() result)."""
    return next(f["ref"] for f in features.floors if f["normal"] == "+Z" and abs(f["z_mm"] - z) < 1e-6)


def read_glb(path: Path) -> tuple[dict, bytes]:
    """A GLB's JSON chunk and binary chunk, checked against the container's own lengths."""
    data = Path(path).read_bytes()
    magic, version, total = struct.unpack_from("<4sII", data, 0)
    assert magic == b"glTF" and version == 2 and total == len(data), (magic, version, total, len(data))
    length, kind = struct.unpack_from("<II", data, 12)
    assert kind == 0x4E4F534A
    document = json.loads(data[20:20 + length])
    offset = 20 + length
    blob = b""
    if offset < len(data):
        blob_length, blob_kind = struct.unpack_from("<II", data, offset)
        assert blob_kind == 0x004E4942
        blob = data[offset + 8:offset + 8 + blob_length]
    return document, blob


def glb_cam(path: Path) -> dict:
    """The plan a result GLB carries (``scenes[0].extras.cam``)."""
    return read_glb(path)[0]["scenes"][0]["extras"]["cam"]
