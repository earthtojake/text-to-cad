"""A solid of planar faces from a polygon mesh: ``faceted_solid(vertices, faces)``.

A triangle mesh -- an STL's (``stl.read``), a field's (``cad.cadjoint.solid``) -- becomes a build123d
``Solid`` whose every face is one of its polygons, flat: one vertex per point the faces use, one edge per
pair of points two faces share (the same edge in both, walked one way by each), one closed wire and one
planar face per polygon, sewn by construction into one shell, with no tolerance search. The mesh is read
whole and refused, in one line naming the fix, before anything is built: a solid of a mesh that is open,
non-manifold or wound both ways would be a plausible wrong one (law 17).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

__all__ = ["faceted_solid"]

# Two points closer than this are one (OCCT's Precision::Confusion, in millimetres): an edge between them
# has no length, and a polygon's corners further than this from its plane do not lie in one.
_CONFUSION = 1e-7


def _points(vertices: Any) -> Any:
    import numpy as np

    try:
        points = np.asarray(vertices, dtype=np.float64)
    except (TypeError, ValueError):
        raise TypeError(f"faceted_solid takes vertices as an (n, 3) array of numbers in millimetres, "
                        f"not {type(vertices).__name__}") from None
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError(f"faceted_solid takes vertices as an (n, 3) array of points, not one of shape {points.shape}")
    if not np.isfinite(points).all():
        bad = int((~np.isfinite(points).all(axis=1)).sum())
        raise ValueError(f"{bad} of the {len(points)} vertices are not finite (NaN or infinite): pass finite points")
    return points


def _loops(faces: Any, count: int) -> list[list[int]]:
    import numpy as np

    if isinstance(faces, (str, bytes)) or not isinstance(faces, (Sequence, np.ndarray)):
        raise TypeError(f"faceted_solid takes faces as a (t, 3) array of triangle indices or a sequence of index "
                        f"loops, not {type(faces).__name__}")
    if isinstance(faces, np.ndarray) and faces.ndim == 2 and faces.dtype.kind in "iu" and faces.shape[1] >= 3:
        # An array of loops of one length, an (t, 3) array of triangles: checked whole.
        if not len(faces):
            raise ValueError("faceted_solid has no faces to make a solid of")
        ordered = np.sort(faces, axis=1)
        repeated = np.flatnonzero((ordered[:, 1:] == ordered[:, :-1]).any(axis=1))
        outside = np.flatnonzero(((faces < 0) | (faces >= count)).any(axis=1))
        if not repeated.size and not outside.size:
            return faces.tolist()
    rows = faces.tolist() if isinstance(faces, np.ndarray) else list(faces)
    if not rows:
        raise ValueError("faceted_solid has no faces to make a solid of")
    loops: list[list[int]] = []
    for index, row in enumerate(rows):
        loop = np.asarray(row)
        if loop.ndim != 1 or loop.dtype.kind not in "iu":
            raise TypeError(f"face {index} is {row!r}: a face is a sequence of integer indices into the vertices")
        indices = [int(value) for value in loop]
        if len(set(indices)) < 3:
            raise ValueError(f"face {index} is {indices}: a face is a loop of three or more distinct vertices -- drop "
                             "the faces that collapse to a line or a point")
        if len(set(indices)) != len(indices):
            raise ValueError(f"face {index} is {indices}: a loop visits each of its vertices once")
        out = [value for value in indices if not 0 <= value < count]
        if out:
            raise ValueError(f"face {index} names vertex {out[0]}, and there are {count} vertices (0 to {count - 1})")
        loops.append(indices)
    return loops


def _checked(points: Any, loops: list[list[int]]) -> list[Any]:
    """Each loop's outward normal (its corners counterclockwise seen from outside), once the mesh is known
    closed, manifold, wound one way, with no edge of no length and no polygon out of its plane."""
    import numpy as np

    walked = np.array([(a, b) for loop in loops for a, b in zip(loop, loop[1:] + loop[:1])], dtype=np.int64)
    undirected = np.sort(walked, axis=1)
    edges, uses = np.unique(undirected, axis=0, return_counts=True)
    wrong = int((uses != 2).sum())
    if wrong:
        open_ = int((uses == 1).sum())
        raise ValueError(f"{wrong} of the mesh's {len(edges)} edges are not shared by exactly two faces ({open_} by one, "
                         f"{wrong - open_} by more than two): the mesh is open or non-manifold, and a solid needs a "
                         "closed surface -- close its holes, or split the bodies that touch at an edge")
    _, directed = np.unique(walked, axis=0, return_counts=True)
    twice = int((directed > 1).sum())
    if twice:
        raise ValueError(f"{twice} edges are walked the same way by both their faces: the faces' winding is inconsistent "
                         "-- wind every face counterclockwise seen from outside")
    lengths = np.linalg.norm(points[edges[:, 0]] - points[edges[:, 1]], axis=1)
    short = int((lengths <= _CONFUSION).sum())
    if short:
        raise ValueError(f"{short} edges join two coincident points (closer than {_CONFUSION:g} mm): weld coincident "
                         "points into one vertex and drop the faces that collapse")
    normals = np.empty((len(loops), 3))
    lengths_of: dict[int, list[int]] = {}
    for index, loop in enumerate(loops):
        lengths_of.setdefault(len(loop), []).append(index)
    for length, rows in lengths_of.items():
        corners = points[np.array([loops[index] for index in rows])]  # (m, length, 3)
        corners = corners - corners[:, :1]
        # Newell's normal: twice the area, outward for corners counterclockwise seen from outside.
        normal = np.cross(corners, np.roll(corners, -1, axis=1)).sum(axis=1)
        size = np.linalg.norm(normal, axis=1)
        flat = np.flatnonzero(size <= _CONFUSION ** 2)
        if flat.size:
            index = rows[int(flat[0])]
            raise ValueError(f"face {index} has no area: its corners {loops[index]} lie on one line")
        normal = normal / size[:, None]
        if length > 3:
            off = np.abs(((corners - corners.mean(axis=1, keepdims=True)) * normal[:, None, :]).sum(axis=2)).max(axis=1)
            bent = np.flatnonzero(off > _CONFUSION)
            if bent.size:
                index = rows[int(bent[0])]
                raise ValueError(f"face {index}'s {length} corners are not in one plane (one lies "
                                 f"{float(off[bent[0]]):.3g} mm off it): split it into triangles")
        normals[rows] = normal
    return list(normals)


def faceted_solid(vertices: Any, faces: Any) -> Any:
    """The closed mesh ``vertices`` and ``faces`` as one build123d ``Solid`` of planar faces, one per face.

    ``vertices`` is an (n, 3) array-like of points in millimetres; ``faces`` an (t, 3) array of triangle
    indices into it, or a sequence of index loops of three or more vertices, each wound counterclockwise
    seen from outside -- a mesh read with ``stl.read`` is ``faceted_solid(mesh.vertices, mesh.triangles)``.
    Points no face uses are left out. The mesh must be closed and manifold (every edge shared by exactly
    two faces, walked one way by each), with no edge of no length and every polygon flat; anything else is
    a ``ValueError`` (a ``TypeError`` for arguments of the wrong kind) naming what to fix, before anything
    is built.

    The solid is faceted: it is exact to the mesh, and no more. No face is a cylinder, and none a plane a
    pick can select as one wall (a flat wall of many triangles is that many faces); a hole's radius reads
    as its chords. It measures (volume, bounds, mass properties), exports and draws as any solid does.
    Building costs a fraction of a millisecond a face: about 2.5 s for 10,000 triangles."""
    import numpy as np
    from build123d import Solid
    from OCP.BRep import BRep_Builder
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeSolid,
                                    BRepBuilderAPI_MakeVertex)
    from OCP.BRepLib import BRepLib
    from OCP.gp import gp_Pnt
    from OCP.TopoDS import TopoDS, TopoDS_Shell, TopoDS_Wire

    points = _points(vertices)
    loops = _loops(faces, len(points))
    normals = _checked(points, loops)

    builder = BRep_Builder()
    corners = {index: BRepBuilderAPI_MakeVertex(gp_Pnt(*(float(value) for value in points[index]))).Vertex()
               for index in sorted({index for loop in loops for index in loop})}
    edges: dict[tuple[int, int], Any] = {}

    def edge(start: int, end: int) -> Any:
        """The one edge between two points, oriented as a loop walks it from ``start`` to ``end``."""
        key = (start, end) if start < end else (end, start)
        found = edges.get(key)
        if found is None:
            made = BRepBuilderAPI_MakeEdge(corners[key[0]], corners[key[1]])
            if not made.IsDone():
                raise ValueError(f"the edge from vertex {key[0]} to vertex {key[1]} cannot be made")
            found = edges[key] = made.Edge()
        return found if key == (start, end) else TopoDS.Edge(found.Reversed())

    shell = TopoDS_Shell()
    builder.MakeShell(shell)
    for index, (loop, normal) in enumerate(zip(loops, normals)):
        wire = TopoDS_Wire()
        builder.MakeWire(wire)
        for start, end in zip(loop, loop[1:] + loop[:1]):
            builder.Add(wire, edge(start, end))
        wire.Closed(True)
        made = BRepBuilderAPI_MakeFace(wire, True)
        if not made.IsDone():
            raise ValueError(f"face {index} ({loop}) cannot be made a plane face: its corners are not in one plane")
        face = made.Face()
        direction = BRepAdaptor_Surface(face).Plane().Axis().Direction()
        if float(np.dot(normal, (direction.X(), direction.Y(), direction.Z()))) < 0:
            face.Reverse()
        builder.Add(shell, face)
    shell.Closed(True)
    made_solid = BRepBuilderAPI_MakeSolid(shell)
    if not made_solid.IsDone():
        raise ValueError("the mesh's faces make no solid")
    solid = made_solid.Solid()
    BRepLib.OrientClosedSolid_s(solid)
    return Solid(solid)
