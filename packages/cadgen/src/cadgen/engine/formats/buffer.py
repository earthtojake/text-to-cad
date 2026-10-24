"""A mesh file's triangles as the engine's part buffer (``mesh.Mesh``, XBM2), so the stills draw
an STL, a 3MF, a GLB or a robot's link mesh as they draw a document's part.

``buffer(positions, triangles)`` is that buffer: the triangles, their normals, one face (or one
per ``faces`` id), and the viewer's feature edges -- three's ``EdgesGeometry`` at 16 degrees,
which the viewer draws over every mesh it has no CAD edges for (``cadScene.js``). Its rule, in
numpy: points weld where they round alike (three's ``Math.round(x * 1e4)`` in the mesh's own
units: ``weld`` is that step in the buffer's millimetres); an edge two triangles share in
opposite directions is drawn where their normals part by more than ``edge_angle``; any other
edge -- one triangle's, a pair wound alike, three or more -- is drawn once. A triangle whose
points weld together draws no edge, and a sliver (three points in a line: no normal) folds
nowhere (three would draw its every edge: a mesher's sliver is no fold of the surface).

Normals are the viewer's for a mesh that brings none (``meshNormals.js``): up to 10,000
triangles, creased at 30 degrees (three's ``toCreasedNormals``: a corner's normal the sum of the
unit normals of the triangles at its point, rounded at 1e-2 of the mesh's units, that meet its
own within the crease); above that, each triangle flat. Either way the corners are drawn apart,
three to a triangle. Normals given (a GLB's) are kept, the triangles indexed as given, a normal
of no length made its vertex's triangles' own.

A triangle of no area is not drawn (it covers nothing): its normal would be no direction, and one
normal of no length is enough for OCCT to draw none of the face it is in (measured: a 31,000
triangle link mesh with one such triangle drew as a lattice of slivers).
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from cadgen.engine.mesh_format import BOUNDARY, FEATURE, NONMANIFOLD, Mesh

__all__ = ["CREASE", "CREASED_MAX", "EDGE_ANGLE", "buffer", "creased_normals", "feature_edges"]

EDGE_ANGLE = 16.0  # degrees: the viewer's CAD_EDGE_THRESHOLD_DEG
CREASE = 30.0  # degrees: the viewer's MESH_NORMAL_CREASE_ANGLE
CREASED_MAX = 10_000  # triangles: above, flat normals (CREASED_NORMAL_MAX_TRIANGLES)
CREASE_PAIRS_MAX = 4_000_000  # corner pairs a crease compares: above, flat normals


def _unit_normals(corners: np.ndarray) -> np.ndarray:
    """Each triangle's unit normal (zero for a degenerate one), from its three corners (M, 3, 3),
    as three computes it: (c - b) x (a - b)."""
    a, b, c = corners[:, 0], corners[:, 1], corners[:, 2]
    normal = np.cross(c - b, a - b)
    length = np.linalg.norm(normal, axis=1, keepdims=True)
    return np.where(length > 0, normal / np.where(length > 0, length, 1), 0.0)


def _keys(points: np.ndarray, step: float, *, truncate: bool = False) -> np.ndarray:
    """An integer id per point: equal for points that round alike at ``step`` (three's
    ``Math.round``, or its ``~~`` truncation for the creased normals' hash)."""
    scaled = np.asarray(points, np.float64) / step
    cells = np.trunc(scaled) if truncate else np.floor(scaled + 0.5)
    _unique, inverse = np.unique(cells.astype(np.int64), axis=0, return_inverse=True)
    return inverse.reshape(-1)


def creased_normals(corners: np.ndarray, crease: float = CREASE, hashed: float = 1e-2) -> np.ndarray:
    """three's ``toCreasedNormals`` on a triangle soup (M, 3, 3): (M * 3, 3) unit normals."""
    faces = _unit_normals(corners)
    count = len(corners)
    point = _keys(corners.reshape(-1, 3), hashed, truncate=True)
    face_of = np.repeat(np.arange(count), 3)
    order = np.argsort(point, kind="stable")
    sorted_points = point[order]
    starts = np.flatnonzero(np.r_[True, sorted_points[1:] != sorted_points[:-1]])
    sizes = np.diff(np.r_[starts, len(order)])
    # Every pair of corners at one point: each corner against every corner of its group, so the
    # work is sum(group size squared), not the corner count. A mesh whose corners pile into a few
    # cells would blow that up far past its triangle count, so past a fixed budget the crease is
    # dropped for flat (per-face) normals, as the >CREASED_MAX path does.
    if int((sizes.astype(np.int64) ** 2).sum()) > CREASE_PAIRS_MAX:
        return np.repeat(faces, 3, axis=0)
    group_of = np.repeat(np.arange(len(starts)), sizes)
    pairs = sizes[group_of]
    left = np.repeat(order, pairs)
    offsets = np.arange(pairs.sum()) - np.repeat(np.cumsum(pairs) - pairs, pairs)
    right = order[np.repeat(starts[group_of], pairs) + offsets]
    own, other = faces[face_of[left]], faces[face_of[right]]
    keep = np.einsum("ij,ij->i", own, other) > math.cos(math.radians(crease))
    summed = np.zeros((count * 3, 3))
    np.add.at(summed, left[keep], other[keep])
    length = np.linalg.norm(summed, axis=1, keepdims=True)
    return np.where(length > 0, summed / np.where(length > 0, length, 1), 0.0)


def feature_edges(positions: np.ndarray, triangles: np.ndarray, *, edge_angle: float = EDGE_ANGLE,
                  weld: float = 1e-4) -> tuple[np.ndarray, np.ndarray]:
    """The viewer's edges of a mesh: (E, 2, 3) segments and each one's class (``FEATURE`` a fold,
    ``BOUNDARY`` one triangle's, ``NONMANIFOLD`` any other)."""
    positions = np.asarray(positions, np.float64)
    triangles = np.asarray(triangles, np.int64).reshape(-1, 3)
    if not len(triangles):
        return np.zeros((0, 2, 3)), np.zeros(0, np.uint32)
    ids = _keys(positions, weld)[triangles]
    keep = (ids[:, 0] != ids[:, 1]) & (ids[:, 1] != ids[:, 2]) & (ids[:, 0] != ids[:, 2])
    ids, kept = ids[keep], triangles[keep]
    normals = _unit_normals(positions[kept])
    start = ids.reshape(-1)
    end = ids[:, [1, 2, 0]].reshape(-1)
    owner = np.repeat(np.arange(len(ids)), 3)
    low, high = np.minimum(start, end), np.maximum(start, end)
    order = np.lexsort((high, low))
    low, high, start, owner = low[order], high[order], start[order], owner[order]
    first = np.flatnonzero(np.r_[True, (low[1:] != low[:-1]) | (high[1:] != high[:-1])])
    sizes = np.diff(np.r_[first, len(low)])
    forward = np.add.reduceat((start == low).astype(np.int64), first)
    paired = (sizes == 2) & (forward == 1)
    one, two = normals[owner[first]], normals[owner[np.minimum(first + 1, len(owner) - 1)]]
    dots = np.einsum("ij,ij->i", one, two)
    # A sliver (a triangle of no area: no normal) folds nowhere: its pair is drawn only where it folds.
    sliver = (np.abs(one).sum(1) == 0) | (np.abs(two).sum(1) == 0)
    drawn = ~paired | ((dots <= math.cos(math.radians(edge_angle))) & ~sliver)
    kind = np.where(paired, FEATURE, np.where(sizes == 1, BOUNDARY, NONMANIFOLD)).astype(np.uint32)
    # Each end at the first point that welded there, as three draws it.
    corner_of = np.full(int(ids.max()) + 1, -1, np.int64)
    flat = kept.reshape(-1)
    welded = ids.reshape(-1)
    corner_of[welded[::-1]] = flat[::-1]
    segments = np.stack([positions[corner_of[low[first]]], positions[corner_of[high[first]]]], 1)
    return segments[drawn], kind[drawn]


def buffer(positions: Any, triangles: Any, *, faces: Any = None, normals: Any = None, uvs: Any = None,
           edge_angle: float = EDGE_ANGLE, weld: float = 1e-4, hashed: float = 1e-2) -> tuple[Mesh, Any]:
    """The part buffer of a mesh: ``positions`` (V, 3) in millimetres, ``triangles`` (M, 3)
    indices into them, ``faces`` each triangle's face ordinal (from 1; all 1 when None),
    ``normals`` (V, 3) to keep (else the viewer's, the corners drawn apart), ``uvs`` (V, 2)
    carried beside. ``weld`` and ``hashed`` are three's rounding steps in the buffer's
    millimetres (``1e-4`` and ``1e-2`` of the mesh's own units). Returns the buffer and the
    UVs in its vertex order (None without)."""
    positions = np.asarray(positions, np.float64).reshape(-1, 3)
    triangles = np.asarray(triangles, np.int64).reshape(-1, 3)
    ordinals = np.ones(len(triangles), np.int64) if faces is None else np.asarray(faces, np.int64).reshape(-1)
    order = np.argsort(ordinals, kind="stable")
    triangles, ordinals = triangles[order], ordinals[order]
    segments, kinds = feature_edges(positions, triangles, edge_angle=edge_angle, weld=weld)
    covering = np.abs(_unit_normals(positions[triangles])).sum(1) > 0
    triangles, ordinals = triangles[covering], ordinals[covering]
    if normals is None:
        corners = positions[triangles]
        shading = creased_normals(corners, hashed=hashed) if len(triangles) <= CREASED_MAX \
            else np.repeat(_unit_normals(corners), 3, axis=0)
        drawn = corners.reshape(-1, 3)
        uv = None if uvs is None else np.asarray(uvs, np.float64).reshape(-1, 2)[triangles].reshape(-1, 2)
        indices = np.arange(len(drawn), dtype=np.uint32)
    else:
        drawn, shading = positions, np.asarray(normals, np.float64).reshape(-1, 3).copy()
        lost = ~(np.linalg.norm(shading, axis=1) > 1e-12)
        if lost.any():  # a normal of no length: its triangles' own, summed by area
            summed = np.zeros_like(positions)
            a, b, c = (positions[triangles[:, at]] for at in range(3))
            for column in range(3):
                np.add.at(summed, triangles[:, column], np.cross(c - b, a - b))
            length = np.linalg.norm(summed, axis=1, keepdims=True)
            shading[lost] = np.where(length > 0, summed / np.where(length > 0, length, 1), (0.0, 0.0, 1.0))[lost]
        uv = None if uvs is None else np.asarray(uvs, np.float64).reshape(-1, 2)
        indices = triangles.astype(np.uint32).reshape(-1)
    present, first, counts = np.unique(ordinals, return_index=True, return_counts=True)
    table = np.stack([present, first * 3, counts * 3], 1).astype(np.uint32) if len(present) \
        else np.array([[1, 0, 0]], np.uint32)
    edges = np.zeros((len(segments), 4), np.uint32)
    edges[:, 0] = np.arange(1, len(segments) + 1)
    edges[:, 1] = np.arange(len(segments)) * 2
    edges[:, 2] = 2
    edges[:, 3] = kinds
    mesh = Mesh(drawn.astype(np.float32), shading.astype(np.float32), indices, table, edges,
                segments.reshape(-1, 3).astype(np.float32), np.zeros((0, 4), np.float32))
    return mesh, uv
