"""The result GLB (``<stem>.cam.glb``): the part, the simulated stock, the toolpaths, and the plan in its extras.

Written by hand (glTF 2.0 is a JSON chunk and one binary chunk, as FEA's result GLB is), so CAM adds no dependency.
Coordinates are glTF's: metres, Y up (CAD ``(x, y, z)`` mm -> ``(x, z, -y) / 1000``), so the part shows upright at
its true size in any glTF viewer.

The scene has one root node ``cam`` whose children are:

* the part mesh (TRIANGLES; node extras ``{"kind": "part"}``);
* the simulated stock after the job (TRIANGLES, translucent; ``{"kind": "stock"}``);
* per setup a ``feed`` node and a ``rapid`` node, each one LINES primitive (mode 1) of segment pairs in part
  coordinates, with float attributes ``_CAM_T`` (program time in seconds, cumulative across setups, the same clock
  as the operations' ``t0``/``t1`` and ``duration_s``) and ``_CAM_OP`` (the global operation index, the one the
  extras' ``operations[].index`` and every finding's ``items[].operation`` use); node extras
  ``{"generator": "cadgen cam", "setup": id, "kind": "feed" | "rapid"}``. Feed lines hold feed, plunge and arc
  moves (arcs sampled within the display chord). Where the tool's axis changes along a setup (a continuous rotary,
  swarf or 5-axis operation, or a tapered wire), its lines also carry ``_CAM_AXIS`` (VEC3 float, unit, glTF axes like
  ``POSITION``): the direction the tool comes from at each vertex, the wire's from its bottom to its top. Without it
  every vertex's axis is its setup's (the third row of ``matrix`` in the extras: WCS +Z in part coordinates).

``generator: "cadgen cam"`` and the whole plan (``cam``, schema 1, see :func:`write_glb`'s ``cam`` argument) are on
both ``scenes[0].extras`` and the root node's extras. glTF loaders may lowercase custom attribute names
(``_cam_t``); the names written are ``_CAM_T``, ``_CAM_OP`` and ``_CAM_AXIS``.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

__all__ = ["GENERATOR", "gltf_space", "line_segments", "sample_axes", "write_glb"]

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


def gltf_direction(vectors) -> "np.ndarray":
    """CAD (x, y, z) directions -> glTF (x, z, -y), float32 (unscaled)."""
    import numpy as np

    vectors = np.asarray(vectors, dtype=float).reshape(-1, 3)
    return np.column_stack([vectors[:, 0], vectors[:, 2], -vectors[:, 1]]).astype(np.float32)


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
    "op": (2S,)}`` and, where the tool's axis changes, ``"axis": (2S, 3)`` unit part directions. ``cam`` is the plan
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
        if entry.get("axis") is not None:
            attributes["_CAM_AXIS"] = add(gltf_direction(entry["axis"]), target=ARRAY, kind="VEC3", component=FLOAT)
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
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(struct.pack("<4sII", b"glTF", 2, total))
        handle.write(struct.pack("<II", len(header), 0x4E4F534A))
        handle.write(header)
        handle.write(struct.pack("<II", len(binary), 0x004E4942))
        handle.write(binary)


def sample_axes(toolpath, wcs, move, *, thickness_mm: float | None = None):
    """The tool's axis (N, 3), unit, part coordinates, at each sample of a setup's toolpath (``Samples.move``: the
    axis at the end of the move a sample ends), or None when it is the setup's own throughout. A continuous
    multi-axis operation's comes from each move's ``a b c`` (:func:`multiaxis.path_axes`); a wire EDM's
    (``thickness_mm`` given: the work's height) is the wire's lean, its ``a b`` columns being U V (top - bottom)."""
    import numpy as np

    moves = toolpath.moves
    if not len(moves):
        return None
    move = np.asarray(move, dtype=np.int64)
    rows = np.maximum(move, 0)
    if thickness_mm is not None:
        if not (np.any(moves["a"]) or np.any(moves["b"])) or not thickness_mm > 0:
            return None
        lean = np.column_stack([moves["a"][rows], moves["b"][rows], np.full(len(rows), float(thickness_mm))])
        lean[move < 0, :2] = 0.0
        axes = wcs.vectors_from_wcs(lean)
    else:
        if not toolpath.rotary:
            return None
        from cadgen._internal.cam.multiaxis import path_axes

        held = dict(wcs.rotary_deg)
        abc = np.column_stack([moves[k] for k in "abc"])
        if np.allclose(abc, [held.get(k, 0.0) for k in "abc"]):
            return None
        axes = path_axes(toolpath, wcs, move)
    return axes / np.linalg.norm(axes, axis=1, keepdims=True)


def line_segments(samples, *, setup: str, t_offset: float, stride: int = 1, axes=None) -> list[dict]:
    """The feed and rapid line entries of one setup's samples (:meth:`Toolpath.sample`), as :func:`write_glb`
    takes them. Times are shifted by ``t_offset`` (the setup's start in program time). ``axes`` (one per sample,
    :func:`sample_axes`) adds each vertex's tool axis."""
    import numpy as np

    from cadgen._internal.cam.ir import DWELL, RAPID

    points, t, op, kind = samples.points, samples.t + t_offset, samples.op, samples.kind
    keep = np.arange(len(points))
    if stride > 1:
        # Thin within each run of one kind and one op; a run's last point is always kept.
        change = np.concatenate([[True], (kind[1:] != kind[:-1]) | (op[1:] != op[:-1]), [True]])
        mask = (np.arange(len(points)) % stride == 0) | change[:-1] | change[1:]
        keep = keep[mask]
    out = []
    a, b = keep[:-1], keep[1:]
    moving = (kind[b] != DWELL) & np.any(points[a] != points[b], axis=1)
    for name, selected in (("feed", moving & (kind[b] != RAPID)), ("rapid", moving & (kind[b] == RAPID))):
        start, end = a[selected], b[selected]
        pairs = np.empty((2 * len(start), 3))
        pairs[0::2], pairs[1::2] = points[start], points[end]
        times = np.empty(2 * len(start))
        times[0::2], times[1::2] = t[start], t[end]
        ops = np.repeat(op[end], 2)
        entry = {"setup": setup, "kind": name, "points": pairs, "t": times, "op": ops}
        if axes is not None:
            axis = np.empty((2 * len(start), 3))
            axis[0::2], axis[1::2] = axes[start], axes[end]
            entry["axis"] = axis
        out.append(entry)
    return out
