"""The kernel-free half of tessellation: the part buffer a renderer reads without parsing
(``Mesh``, its wire form ``XBM2``, which ``mesh.py`` describes) and the classes its edge table
names. Producers, the HTTP server and the mesh files' readers share it; the kernel's mesher
(``mesh.py``) makes one from a shape, a mesh file's reader from its triangles."""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field

import numpy as np

# The tessellation (``mesh.py`` says why): a deviation of 0.25 (per cent of the box's mean side,
# its summed sides /300 as FreeCAD writes its own default of 0.5) and FreeCAD's angular deflection
# of 28.5 degrees.
DEVIATION = 0.25
ANGULAR = math.radians(28.5)
# The pair, by name: what a served part's URL carries (the structure's ``tessellation``).
TESSELLATION = f"{DEVIATION:g}-{math.degrees(ANGULAR):g}"

MAGIC = b"XBM2"
VERSION = 2
HEADER = struct.Struct("<4sI6I7I2f3I")
assert HEADER.size == 80

FEATURE, TANGENT, SEAM, BOUNDARY, NONMANIFOLD = 1, 2, 3, 5, 6
CLASS_NAMES = {FEATURE: "feature", TANGENT: "tangent", SEAM: "seam", BOUNDARY: "boundary",
               NONMANIFOLD: "non-manifold"}


@dataclass
class Mesh:
    positions: np.ndarray  # (V, 3) float32
    normals: np.ndarray  # (V, 3) float32; None for a mesh file of a format with none (``export/mesh_file.py``), never sent
    indices: np.ndarray  # (I,) uint32
    faces: np.ndarray  # (F, 3) uint32: ordinal, first index, index count
    edges: np.ndarray  # (E, 4) uint32: ordinal, first point, point count, class
    edge_points: np.ndarray  # (P, 3) float32
    vertices: np.ndarray  # (X, 4) float32: ordinal, x, y, z
    linear: float = 0.0
    angular: float = 0.0
    unmeshed: dict[int, str] = field(default_factory=dict)  # face ordinal: its BRepCheck verdict

    @property
    def triangles(self) -> int:
        return len(self.indices) // 3

    @property
    def nbytes(self) -> int:
        return sum(array.nbytes for array in (self.positions, self.normals, self.indices, self.faces, self.edges,
                                              self.edge_points, self.vertices))

    def to_bytes(self) -> bytes:
        arrays = [np.ascontiguousarray(self.positions, "<f4"), np.ascontiguousarray(self.normals, "<f4"),
                  np.ascontiguousarray(self.indices, "<u4"), np.ascontiguousarray(self.faces, "<u4"),
                  np.ascontiguousarray(self.edges, "<u4"), np.ascontiguousarray(self.edge_points, "<f4"),
                  np.ascontiguousarray(self.vertices, "<f4")]
        offsets = []
        at = HEADER.size
        for array in arrays:
            offsets.append(at)
            at += array.nbytes  # every element is 4 bytes: every offset stays aligned
        header = HEADER.pack(MAGIC, VERSION, len(self.positions), len(self.indices), len(self.faces),
                             len(self.edges), len(self.edge_points), len(self.vertices), *offsets,
                             self.linear, self.angular, 0, 0, 0)
        return b"".join([header, *(array.tobytes() for array in arrays)])

    @staticmethod
    def from_bytes(data: bytes) -> "Mesh":
        (magic, version, *rest) = HEADER.unpack_from(data)
        if magic != MAGIC or version != VERSION:
            raise ValueError("not a mesh buffer")
        counts, offsets, (linear, angular) = rest[:6], rest[6:13], rest[13:15]
        nodes, indices, faces, edges, points, vertices = counts

        def view(at: int, dtype: str, count: int, width: int) -> np.ndarray:
            array = np.frombuffer(data, dtype, count * width, offsets[at])
            return array.reshape(-1, width) if width > 1 else array

        found = Mesh(view(0, "<f4", nodes, 3), view(1, "<f4", nodes, 3), view(2, "<u4", indices, 1),
                     view(3, "<u4", faces, 3), view(4, "<u4", edges, 4), view(5, "<f4", points, 3),
                     view(6, "<f4", vertices, 4), linear, angular)
        found.unmeshed = {int(ordinal): "" for ordinal, _first, count in found.faces if count == 0}
        return found
