"""A part's engine mesh (an XBM buffer, ``mesh.Mesh``) as OCCT shapes, without a Python loop
per node, per triangle or per edge: the triangulations and polylines are written with numpy
straight into the kernel's binary shape format (``BinTools``, format 4) -- triangulation-only
faces and ``Poly_Polygon3D`` edges in one compound -- and read back in one kernel call.

So OCCT draws the very triangles and polylines the engine meshed (FreeCAD's deflection, the
viewer's buffer), and never meshes anything itself: a face with a triangulation and no surface
is drawn as it is, an edge with a 3D polygon likewise.

A part becomes one face per colour group (its faces of one colour merged into one
triangulation) and one compound of edges per edge class (``feature``: feature, boundary and
non-manifold edges, as the viewer groups them; ``tangent``; ``seam``), each edge one polyline.
A mesh file's part may bring texture coordinates (a GLB's, ``formats/glb.py``): its faces' nodes
carry them, and ``textures`` holds the texture each colour group is drawn with.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from cadgen.engine.mesh import BOUNDARY, FEATURE, NONMANIFOLD, SEAM, TANGENT, Mesh

LINES = ("feature", "tangent", "seam")
_LINE_OF = {FEATURE: "feature", BOUNDARY: "feature", NONMANIFOLD: "feature", TANGENT: "tangent", SEAM: "seam"}

_HEAD = b"\nOpen CASCADE Topology V4, (c) Open Cascade\nLocations 0\nCurve2ds 0\nCurves 0\n"
_FLAGS = (0, 1, 0, 1, 0, 0, 0)  # Free, Modified, Checked, Orientable, Closed, Infinite, Convex
_TOL = 1e-7

_EDGE = np.dtype([("type", "u1"), ("tol", "<f8"), ("same", "u1", 3), ("rep", "u1"), ("poly", "<i4"),
                  ("loc", "<i4"), ("end", "u1"), ("flags", "u1", 7), ("star", "u1")])
_FACE = np.dtype([("type", "u1"), ("natural", "u1"), ("tol", "<f8"), ("surface", "<i4"), ("loc", "<i4"),
                  ("mark", "u1"), ("tri", "<i4"), ("flags", "u1", 7), ("star", "u1")])
_CHILD = np.dtype([("orient", "u1"), ("index", "<i4"), ("loc", "<i4")])
_POLY = np.dtype([("n", "<i4"), ("params", "u1"), ("deflection", "<f8")])
assert _EDGE.itemsize == 30 and _FACE.itemsize == 31 and _CHILD.itemsize == 9 and _POLY.itemsize == 13


@dataclass
class PartShapes:
    """A part's faces by colour group and its edges by class, in the part's own frame."""

    faces: dict[Any, Any] = field(default_factory=dict)  # group: TopoDS_Face (triangulation only)
    edges: dict[str, Any] = field(default_factory=dict)  # line class: TopoDS_Compound of polygon edges
    triangles: int = 0
    edge_count: int = 0
    textures: dict[Any, Any] = field(default_factory=dict)  # group: its texture set (a GLB's)


def _compound(children: np.ndarray) -> bytes:
    rows = np.zeros(len(children), _CHILD)
    rows["index"] = children
    return bytes([0, 1, 1, 0, 0, 0, 0, 0]) + rows.tobytes() + b"*"


def _polygons(points: np.ndarray, counts: np.ndarray) -> bytes:
    """``Poly_Polygon3D`` records, one per run of ``counts`` points, each a 13-byte head and its
    nodes as doubles, interleaved with numpy alone."""
    heads = np.zeros(len(counts), _POLY)
    heads["n"] = counts
    head_bytes = heads.view(np.uint8).reshape(-1, 13)
    nodes = np.ascontiguousarray(points, "<f8").view(np.uint8).reshape(-1)
    sizes = 13 + 24 * counts
    total = int(sizes.sum())
    out = np.empty(total, np.uint8)
    starts = np.concatenate(([0], np.cumsum(sizes)[:-1]))
    is_head = np.zeros(total, bool)
    head_at = (starts[:, None] + np.arange(13)).reshape(-1)
    is_head[head_at] = True
    out[head_at] = head_bytes.reshape(-1)
    out[~is_head] = nodes
    return out.tobytes()


def craft(groups: list[tuple], lines: dict[str, tuple[np.ndarray, np.ndarray]]) -> bytes:
    """The BinTools bytes of a compound: one triangulation-only face per ``groups`` entry
    (nodes (n, 3), 0-based triangles (m, 3), normals (n, 3) or None, and optionally texture
    coordinates (n, 2)), then one compound per line class of ``lines`` (points (P, 3), counts per
    edge), each edge a ``Poly_Polygon3D``."""
    chunks = [_HEAD]
    classes = [name for name in LINES if name in lines and len(lines[name][1])]
    counts = np.concatenate([lines[name][1] for name in classes]) if classes else np.zeros(0, np.int64)
    points = np.concatenate([lines[name][0] for name in classes]) if classes else np.zeros((0, 3))
    chunks.append(b"Polygon3D %d\n" % len(counts))
    if len(counts):
        chunks.append(_polygons(points, counts.astype(np.int64)))
    chunks.append(b"PolygonOnTriangulations 0\nSurfaces 0\n")
    chunks.append(b"Triangulations %d\n" % len(groups))
    for group in groups:
        nodes, triangles, normals = group[:3]
        uvs = group[3] if len(group) > 3 else None
        has_normals = normals is not None
        chunks.append(np.array([len(nodes), len(triangles)], "<i4").tobytes())
        chunks.append(bytes([0 if uvs is None else 1, 1 if has_normals else 0]))
        chunks.append(np.array([0.0], "<f8").tobytes())
        chunks.append(np.ascontiguousarray(nodes, "<f8").tobytes())
        if uvs is not None:
            chunks.append(np.ascontiguousarray(uvs, "<f8").tobytes())
        chunks.append(np.ascontiguousarray(triangles + 1, "<i4").tobytes())
        if has_normals:
            chunks.append(np.ascontiguousarray(normals, "<f4").tobytes())
    # TShapes: written N..1, so the k-th record written has index N - k + 1; the root is last (1).
    faces, edges = len(groups), len(counts)
    total = faces + edges + len(classes) + 1
    chunks.append(b"\nTShapes %d\n" % total)
    face_rows = np.zeros(faces, _FACE)
    face_rows["type"], face_rows["tol"], face_rows["mark"], face_rows["star"] = 4, _TOL, 2, 42
    face_rows["tri"] = np.arange(1, faces + 1)
    face_rows["flags"] = _FLAGS
    chunks.append(face_rows.tobytes())
    edge_rows = np.zeros(edges, _EDGE)
    edge_rows["type"], edge_rows["tol"], edge_rows["rep"], edge_rows["star"] = 6, _TOL, 5, 42
    edge_rows["same"] = (1, 1, 0)
    edge_rows["poly"] = np.arange(1, edges + 1)
    edge_rows["flags"] = _FLAGS
    chunks.append(edge_rows.tobytes())
    position = faces + edges
    compound_indices = []
    at = faces
    for name in classes:
        count = len(lines[name][1])
        positions = np.arange(at + 1, at + count + 1)
        chunks.append(_compound(total - positions + 1))
        at += count
        position += 1
        compound_indices.append(total - position + 1)
    root_children = np.concatenate([total - np.arange(1, faces + 1) + 1, np.asarray(compound_indices, np.int64)])
    chunks.append(_compound(root_children))
    chunks.append(bytes([0]) + np.array([1, 0], "<i4").tobytes())
    return b"".join(chunks)


def read(data: bytes) -> Any:
    from OCP.BinTools import BinTools
    from OCP.TopoDS import TopoDS_Shape

    shape = TopoDS_Shape()
    BinTools.Read_s(shape, io.BytesIO(data))
    return shape


def part_shapes(mesh: Mesh, group_of: dict[int, Any] | None = None, default: Any = None,
                uvs: np.ndarray | None = None) -> PartShapes:
    """The part's faces, one per colour group (``group_of``: face ordinal -> group; every
    other face is ``default``'s), and its edges by class, as triangulation-only and polygon
    shapes read from one crafted BinTools buffer; ``uvs`` (each vertex's texture coordinates)
    on its faces' nodes."""
    from OCP.TopoDS import TopoDS_Iterator

    group_of = group_of or {}
    faces = np.asarray(mesh.faces, np.int64).reshape(-1, 3)
    triangles = np.asarray(mesh.indices, np.int64).reshape(-1, 3)
    positions, normals = mesh.positions, mesh.normals
    groups: list[tuple[np.ndarray, np.ndarray, np.ndarray | None]] = []
    keys: list[Any] = []
    painted = {ordinal: group for ordinal, group in group_of.items() if group != default}
    if not painted:
        if len(triangles):
            groups.append((positions, triangles, normals) if uvs is None else (positions, triangles, normals, uvs))
            keys.append(default)
    else:
        # Each group by a number of its own: a group is a colour (an RGBA tuple), which numpy
        # would compare element by element against an array of them.
        order = [default, *sorted({*painted.values()} - {default}, key=str)]
        number = {key: at for at, key in enumerate(order)}
        per_triangle = np.repeat(np.array([number[painted.get(int(o), default)] for o in faces[:, 0]], np.int64),
                                 faces[:, 2] // 3)
        for key in order:
            chosen = triangles[per_triangle == number[key]]
            if not len(chosen):
                continue
            used, inverse = np.unique(chosen, return_inverse=True)
            groups.append((positions[used], inverse.reshape(-1, 3), normals[used])
                          + (() if uvs is None else (uvs[used],)))
            keys.append(key)
    edges = np.asarray(mesh.edges, np.int64).reshape(-1, 4)
    edges = edges[edges[:, 2] >= 2]
    lines: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    points = np.asarray(mesh.edge_points)
    for name in LINES:
        rows = edges[np.isin(edges[:, 3], [c for c, n in _LINE_OF.items() if n == name])]
        if not len(rows):
            continue
        take = np.concatenate([np.arange(first, first + count) for first, count in rows[:, 1:3]]) if len(rows) < 64 \
            else _ranges(rows[:, 1], rows[:, 2])
        lines[name] = (points[take], rows[:, 2])
    shape = read(craft(groups, lines))
    found = PartShapes(triangles=len(triangles), edge_count=len(edges))
    children = TopoDS_Iterator(shape)
    at = 0
    names = [name for name in LINES if name in lines]
    while children.More():
        child = children.Value()
        if at < len(keys):
            found.faces[keys[at]] = child
        else:
            found.edges[names[at - len(keys)]] = child
        at += 1
        children.Next()
    return found


def _ranges(starts: np.ndarray, counts: np.ndarray) -> np.ndarray:
    """``concatenate(arange(s, s + c))`` for every pair, vectorized."""
    total = int(counts.sum())
    bases = np.repeat(starts - np.concatenate(([0], np.cumsum(counts)[:-1])), counts)
    return bases + np.arange(total)
