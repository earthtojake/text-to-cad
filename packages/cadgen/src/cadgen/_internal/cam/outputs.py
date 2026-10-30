"""The result GLB (``<stem>.cam.glb``): the part, the stock, the toolpaths, and the plan in its extras.

Written by hand (glTF 2.0 is a JSON chunk and one binary chunk), so CAM adds no dependency.
Coordinates are glTF's: metres, Y up (CAD ``(x, y, z)`` mm -> ``(x, z, -y) / 1000``), so the part shows upright at
its true size in any glTF viewer.

The scene has one root node ``cam`` whose children are:

* the part mesh (TRIANGLES; node extras ``{"kind": "part"}``);
* the stock box (TRIANGLES, translucent; ``{"kind": "stock"}``);
* per setup a ``feed`` node and a ``rapid`` node, each one LINES primitive (mode 1) of segment pairs in part
  coordinates, with float attributes ``_CAM_T`` (program time in seconds, cumulative across setups, the same clock
  as the operations' ``t0``/``t1`` and ``duration_s``) and ``_CAM_OP`` (the global operation index, the one the
  extras' ``operations[].index`` and every finding's ``items[].operation`` use); node extras
  ``{"generator": "cadgen cam", "setup": id, "kind": "feed" | "rapid"}``. Feed lines hold feed, plunge and arc
  moves (arcs sampled within :data:`toolpath.CHORD_MM`). Every vertex's tool axis is its setup's (the third row of
  ``matrix`` in the extras: WCS +Z in part coordinates).

``generator: "cadgen cam"`` and the whole plan (``cam``, schema 1, see :func:`write_glb`'s ``cam`` argument) are on
both ``scenes[0].extras`` and the root node's extras. glTF loaders may lowercase custom attribute names
(``_cam_t``); the names written are ``_CAM_T`` and ``_CAM_OP``.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

__all__ = ["GENERATOR", "gltf_space", "line_segments", "write_glb"]

GENERATOR = "cadgen cam"


def gltf_space(points_mm: "np.ndarray") -> "np.ndarray":
    """CAD (x, y, z) mm -> glTF (x, z, -y) metres, float32."""
    import numpy as np

    points_mm = np.asarray(points_mm, dtype=float).reshape(-1, 3)
    out = np.empty_like(points_mm, dtype=np.float32)
    out[:, 0] = points_mm[:, 0] / 1000.0
    out[:, 1] = points_mm[:, 2] / 1000.0
    out[:, 2] = -points_mm[:, 1] / 1000.0
    return out


def _vertex_normals(positions, triangles):
    import numpy as np

    a = positions[triangles[:, 1]] - positions[triangles[:, 0]]
    b = positions[triangles[:, 2]] - positions[triangles[:, 0]]
    face = np.cross(a, b)
    normals = np.zeros_like(positions)
    for corner in range(3):
        np.add.at(normals, triangles[:, corner], face)
    length = np.linalg.norm(normals, axis=1, keepdims=True)
    length[length == 0] = 1.0
    return (normals / length).astype(np.float32)


def write_glb(path: Path, *, part_mesh, stock_mesh, lines: list[dict], cam: dict, name: str) -> None:
    """Write the result GLB.

    ``part_mesh`` and ``stock_mesh`` are ``(vertices (V, 3) part mm, triangles (T, 3))``. ``lines`` has one dict per
    toolpath node: ``{"setup", "kind": "feed" | "rapid", "points": (2S, 3) part mm (segment pairs), "t": (2S,),
    "op": (2S,)}``. ``cam`` is the plan
    the viewer reads (``extras.cam``)."""
    import numpy as np

    blobs: list[bytes] = []
    views: list[dict] = []
    accessors: list[dict] = []

    def add(array, *, target: int, kind: str, component: int, bounds: bool = False) -> int:
        data = np.ascontiguousarray(array).tobytes()
        offset = sum(len(b) for b in blobs)
        blobs.append(data + b"\0" * (-len(data) % 4))
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(data), "target": target})
        accessor = {"bufferView": len(views) - 1, "componentType": component, "count": int(array.shape[0]),
                    "type": kind}
        if bounds and len(array):
            accessor["min"] = [float(x) for x in array.min(axis=0)]
            accessor["max"] = [float(x) for x in array.max(axis=0)]
        accessors.append(accessor)
        return len(accessors) - 1

    ARRAY, ELEMENT = 34962, 34963
    FLOAT, UINT = 5126, 5125
    meshes: list[dict] = []
    nodes: list[dict] = [{"name": "cam", "children": [], "extras": {"generator": GENERATOR, "cam": cam}}]
    materials = [
        {"name": "part", "doubleSided": True,
         "pbrMetallicRoughness": {"baseColorFactor": [0.72, 0.74, 0.78, 1.0], "metallicFactor": 0.1,
                                  "roughnessFactor": 0.6}},
        {"name": "stock", "doubleSided": True, "alphaMode": "BLEND",
         "pbrMetallicRoughness": {"baseColorFactor": [0.85, 0.62, 0.30, 0.35], "metallicFactor": 0.0,
                                  "roughnessFactor": 0.9}},
        {"name": "feed", "pbrMetallicRoughness": {"baseColorFactor": [0.10, 0.45, 0.95, 1.0], "metallicFactor": 0.0}},
        {"name": "rapid", "pbrMetallicRoughness": {"baseColorFactor": [0.90, 0.20, 0.15, 1.0], "metallicFactor": 0.0}},
    ]

    def triangles_node(mesh, label: str, material: int, extras: dict) -> None:
        vertices, triangles = mesh
        vertices = np.asarray(vertices, dtype=float)
        triangles = np.asarray(triangles, dtype=np.int64)
        if not len(triangles):
            return
        positions = gltf_space(vertices)
        normals = _vertex_normals(positions.astype(float), triangles)
        primitive = {"attributes": {"POSITION": add(positions, target=ARRAY, kind="VEC3", component=FLOAT, bounds=True),
                                    "NORMAL": add(normals, target=ARRAY, kind="VEC3", component=FLOAT)},
                     "indices": add(triangles.astype(np.uint32).reshape(-1, 1), target=ELEMENT, kind="SCALAR",
                                    component=UINT),
                     "material": material, "mode": 4}
        meshes.append({"name": label, "primitives": [primitive]})
        nodes.append({"name": label, "mesh": len(meshes) - 1, "extras": extras})
        nodes[0]["children"].append(len(nodes) - 1)

    triangles_node(part_mesh, "part", 0, {"kind": "part"})
    triangles_node(stock_mesh, "stock", 1, {"kind": "stock"})
    for entry in lines:
        points = np.asarray(entry["points"], dtype=float)
        if not len(points):
            continue
        attributes = {
            "POSITION": add(gltf_space(points), target=ARRAY, kind="VEC3", component=FLOAT, bounds=True),
            "_CAM_T": add(np.asarray(entry["t"], dtype=np.float32).reshape(-1, 1), target=ARRAY, kind="SCALAR",
                          component=FLOAT),
            "_CAM_OP": add(np.asarray(entry["op"], dtype=np.float32).reshape(-1, 1), target=ARRAY, kind="SCALAR",
                           component=FLOAT),
        }
        label = f"{entry['setup']} {entry['kind']}"
        meshes.append({"name": label, "primitives": [{"attributes": attributes, "mode": 1,
                                                      "material": 2 if entry["kind"] == "feed" else 3}]})
        nodes.append({"name": label, "mesh": len(meshes) - 1,
                      "extras": {"generator": GENERATOR, "setup": entry["setup"], "kind": entry["kind"]}})
        nodes[0]["children"].append(len(nodes) - 1)

    gltf = {
        "asset": {"version": "2.0", "generator": GENERATOR},
        "scene": 0,
        "scenes": [{"name": name, "nodes": [0], "extras": {"generator": GENERATOR, "cam": cam}}],
        "nodes": nodes,
        "meshes": meshes,
        "materials": materials,
        "buffers": [{"byteLength": sum(len(b) for b in blobs)}],
        "bufferViews": views,
        "accessors": accessors,
    }
    header = json.dumps(gltf, separators=(",", ":"), allow_nan=False).encode("utf-8")
    header += b" " * (-len(header) % 4)
    binary = b"".join(blobs)
    total = 12 + 8 + len(header) + 8 + len(binary)
    from cadgen._internal.primitive_mesh import GLB_BIN_CHUNK, GLB_JSON_CHUNK, GLB_MAGIC, GLB_VERSION

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(struct.pack("<III", GLB_MAGIC, GLB_VERSION, total))
        handle.write(struct.pack("<II", len(header), GLB_JSON_CHUNK))
        handle.write(header)
        handle.write(struct.pack("<II", len(binary), GLB_BIN_CHUNK))
        handle.write(binary)


def line_segments(moves, *, setup: str, t_offset: float, to_part) -> list[dict]:
    """The feed and rapid line entries of one setup's moves (:class:`toolpath.Moves`), as :func:`write_glb` takes
    them: segment pairs in part coordinates (``to_part`` turns setup points into them), times shifted by
    ``t_offset`` (the setup's start in program time)."""
    import numpy as np

    points = to_part(moves.points)
    a, b = np.arange(len(points) - 1), np.arange(1, len(points))
    moving = np.any(points[a] != points[b], axis=1)
    out = []
    for name, selected in (("feed", moving & ~moves.rapid[b]), ("rapid", moving & moves.rapid[b])):
        start, end = a[selected], b[selected]
        pairs = np.empty((2 * len(start), 3))
        pairs[0::2], pairs[1::2] = points[start], points[end]
        times = np.empty(2 * len(start))
        times[0::2], times[1::2] = moves.t[start] + t_offset, moves.t[end] + t_offset
        out.append({"setup": setup, "kind": name, "points": pairs, "t": times, "op": np.repeat(moves.op[end], 2)})
    return out
