"""A Wavefront OBJ read as one triangle mesh: its vertices and its faces, each face fanned into
triangles. numpy alone, as the STL reader is.

MuJoCo's models name their link meshes as OBJ as often as STL (the menagerie's do), so an MJCF's
visuals need one read: the stills draw it as a part (``robot.py``) and the robot payload serves it
to the page as a GLB (``cad_server.robot_payload``). Only the geometry is read -- ``v`` and ``f``
lines; a face's ``v/vt/vn`` indices keep the vertex, and a negative index counts from the end, as
the format says -- and nothing of the materials (``mtllib``, ``usemtl``), groups, normals or texture
coordinates: a robot's description colours its visuals itself. The numbers are as the file has
them, in whatever unit the description's mesh scale makes metres.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

__all__ = ["ObjError", "read_obj"]


class ObjError(ValueError):
    """An OBJ that is no triangle mesh, said by name."""


def read_obj(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """``(points, triangles)``: the vertices as an ``(n, 3)`` float64 array and the faces as an ``(m, 3)``
    int64 array of indices into them. ``ObjError`` for a file with no face, a face with fewer than three
    vertices or an index outside its vertices."""
    points: list[tuple[float, float, float]] = []
    triangles: list[tuple[int, int, int]] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for number, raw in enumerate(handle, start=1):
                line = raw.strip()
                if not line or line[0] == "#":
                    continue
                while line.endswith("\\"):  # a continued line
                    line = line[:-1] + next(handle, "").strip()
                pieces = line.split()
                if pieces[0] == "v" and len(pieces) >= 4:
                    try:
                        points.append((float(pieces[1]), float(pieces[2]), float(pieces[3])))
                    except ValueError:
                        raise ObjError(f"{path.name} line {number}: a vertex that is not three numbers") from None
                elif pieces[0] == "f":
                    corners = []
                    for piece in pieces[1:]:
                        index_text = piece.split("/", 1)[0]
                        try:
                            index = int(index_text)
                        except ValueError:
                            raise ObjError(f"{path.name} line {number}: a face index that is not a number") from None
                        if index == 0:
                            raise ObjError(f"{path.name} line {number}: a face index of 0 (OBJ counts from 1)")
                        corners.append(index - 1 if index > 0 else len(points) + index)
                    if len(corners) < 3:
                        raise ObjError(f"{path.name} line {number}: a face with fewer than three vertices")
                    for second, third in zip(corners[1:-1], corners[2:], strict=True):
                        triangles.append((corners[0], second, third))
    except OSError as error:
        raise ObjError(f"{path.name} could not be read: {error.strerror or error}") from None
    if not triangles:
        raise ObjError(f"{path.name} has no faces")
    faces = np.asarray(triangles, dtype=np.int64)
    if faces.min() < 0 or faces.max() >= len(points):
        raise ObjError(f"{path.name} names a vertex it does not have")
    return np.asarray(points, dtype=np.float64), faces
