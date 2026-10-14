"""Shared fixtures for the CAM suites (``tests/python/packages/cadgen/cam/``).

Parts are built with build123d into a temporary directory per test class (never ``models/``), and the job helpers
build the dicts the suites plan. Heavy imports stay inside the helpers. A track that needs its own parts adds a
``cam_fixtures_<track>.py`` beside this one rather than editing it.

The block (:func:`block_step`, :data:`BLOCK`): 80 x 60 x 25 mm standing on z = 0, centred in x and y, with a stepped
pocket (an upper step 50 x 40 down to z = 17, a lower step 24 x 20 centred at x = -10 down to z = 11), a round
island Ø8 at (14, 0) rising from the upper floor to the top, and four Ø5 through holes at (±33, ±23).
"""

from __future__ import annotations

import io
import json
import struct
import tempfile
from contextlib import contextmanager, redirect_stderr
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

#: The block's numbers, for assertions.
BLOCK = {
    "size": (80.0, 60.0, 25.0),
    "upper": {"size": (50.0, 40.0), "center": (0.0, 0.0), "floor_z": 17.0},
    "lower": {"size": (24.0, 20.0), "center": (-10.0, 0.0), "floor_z": 11.0},
    "island": {"center": (14.0, 0.0), "diameter": 8.0},
    "holes": {"diameter": 5.0, "centers": ((-33.0, -23.0), (33.0, -23.0), (-33.0, 23.0), (33.0, 23.0))},
}
PLATE = {"size": (60.0, 40.0, 6.0)}


def class_directory(cls) -> Path:
    """A temporary directory for a TestCase class's fixtures, removed after its last test."""
    tmp = tempfile.TemporaryDirectory(prefix="cam-")
    cls.addClassCleanup(tmp.cleanup)
    return Path(tmp.name)


@contextmanager
def quiet():
    with redirect_stderr(io.StringIO()):
        yield


def block_step(directory: Path, name: str = "block") -> Path:
    from build123d import Align, Box, Cylinder, Pos, export_step

    base = (Align.CENTER, Align.CENTER, Align.MIN)
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


def plate_step(directory: Path, name: str = "plate") -> Path:
    from build123d import Align, Box, export_step

    path = directory / f"{name}.step"
    export_step(Box(*PLATE["size"], align=(Align.CENTER, Align.CENTER, Align.MIN)), str(path))
    return path


def mill_job(operations: list[dict], *, tools: list[dict] | None = None, stock: dict | None = None,
             machine: dict | None = None, material: str = "aluminum-6061", setups: list[dict] | None = None) -> dict:
    """A 3-axis job on GRBL with a 6 mm three-flute flat (T1) and a 5 mm drill (T2) by default."""
    return {
        "machine": machine or {"kind": "mill", "post": "grbl", "max_rpm": 24000, "travel_mm": [300, 200, 80]},
        "material": material,
        "stock": stock or {"kind": "box", "margin_mm": [2, 2, 1]},
        "tools": tools or [
            {"id": "T1", "type": "flat", "diameter_mm": 6, "flutes": 3, "flute_length_mm": 20, "stickout_mm": 30},
            {"id": "T2", "type": "drill", "diameter_mm": 5},
        ],
        "setups": setups or [{"id": "top", "orientation": "+Z", "origin": "stock-top-center", "operations": operations}],
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


def accessor_array(document: dict, blob: bytes, index: int):
    """One accessor's data as a numpy array (float32/uint32, shaped by its type)."""
    import numpy as np

    accessor = document["accessors"][index]
    view = document["bufferViews"][accessor["bufferView"]]
    dtype = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8}[accessor["componentType"]]
    width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[accessor["type"]]
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    array = np.frombuffer(blob, dtype=dtype, count=accessor["count"] * width, offset=start)
    return array.reshape(accessor["count"], width) if width > 1 else array
