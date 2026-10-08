"""The meshes of a robot description's primitive shapes: box, cylinder, sphere, capsule.

A URDF or SDF visual may be a shape rather than a mesh file. cadgen meshes it, as it
meshes every other display mesh, at the standard rung of the display ladder
(``cadgen.tessellation_policy.DEFAULT_TESSELLATION``): a round shape takes as many
segments as the chord criterion (relative to the shape's bounding diagonal, as a STEP
component's is) and the angle criterion between them allow, which is what OCCT's
mesher decides for the same solid. A box is twelve triangles whatever the rung.

Each mesh is one glTF binary: positions and normals in glTF's Y-up metres, one triangle
primitive, no material (the robot's visual paints it: the description's colour, else the
viewer's surface), and the ``cadUpAxis`` declaration every cadgen GLB carries. It is a
store object addressed by its bytes (``cadgen.store.objects``), so one shape at one size
is meshed once for every robot that draws it. The page draws a GLB in millimetres, so a
primitive's placement carries the same ``0.001`` a ``<mesh scale>`` on a cadgen-written
link mesh does (``cadgen.robot_payload``).
"""

from __future__ import annotations

import json
import math
import struct

import numpy as np

from cadgen.tessellation_policy import DEFAULT_TESSELLATION

__all__ = ["PRIMITIVE_SHAPES", "primitive_glb", "primitive_segments"]

#: The shapes meshed here, by the name URDF and SDF give them.
PRIMITIVE_SHAPES = ("box", "cylinder", "sphere", "capsule")

# A circle is never coarser than an octagon nor finer than this, whatever the tolerances
# and the radius say: the ladder is a display policy, not a licence for a million triangles.
_MIN_SEGMENTS = 8
_MAX_SEGMENTS = 512

_GLB_MAGIC, _GLB_VERSION, _JSON_CHUNK, _BIN_CHUNK = 0x46546C67, 2, 0x4E4F534A, 0x004E4942
_FLOAT, _UNSIGNED_INT, _ARRAY_BUFFER, _ELEMENT_ARRAY_BUFFER, _TRIANGLES = 5126, 5125, 34962, 34963, 4


def primitive_segments(radius: float, diagonal: float) -> int:
    """How many segments a circle of ``radius`` takes on a shape of bounding ``diagonal``.

    The chord criterion bounds the sagitta of one segment by the rung's chord tolerance
    times the diagonal; the angle criterion bounds the turn between two segments' normals.
    The tighter of the two decides, within the floor and the cap above.
    """
    chord = float(DEFAULT_TESSELLATION["chordTolerance"]) * float(diagonal)
    angle = float(DEFAULT_TESSELLATION["angleTolerance"])
    theta = angle
    if 0.0 < chord < radius:
        theta = min(theta, 2.0 * math.acos(1.0 - chord / radius))
    return max(_MIN_SEGMENTS, min(_MAX_SEGMENTS, int(math.ceil(2.0 * math.pi / theta))))


class _Mesh:
    """Positions, outward normals and triangles, in Z-up metres, wound counter-clockwise
    seen from outside."""

    def __init__(self) -> None:
        self.positions: list = []
        self.normals: list = []
        self.indices: list[int] = []

    def vertex(self, position, normal) -> int:
        self.positions.append(np.asarray(position, dtype=np.float64))
        self.normals.append(np.asarray(normal, dtype=np.float64))
        return len(self.positions) - 1

    def ring(self, segments: int, radius: float, latitude: float, centre_z: float) -> int:
        """``segments`` vertices round a circle of a sphere of ``radius`` at ``latitude``,
        centred on ``(0, 0, centre_z)``, their normals the sphere's; returns the first index."""
        angles = np.arange(segments, dtype=np.float64) * (2.0 * math.pi / segments)
        c, s = math.cos(latitude), math.sin(latitude)
        direction = np.stack([np.cos(angles) * c, np.sin(angles) * c, np.full(segments, s)], axis=1)
        start = len(self.positions)
        self.positions.extend(direction * radius + np.array([0.0, 0.0, centre_z]))
        self.normals.extend(direction)
        return start

    def join(self, upper: int, lower: int, segments: int) -> None:
        """The wall between two rings, the upper ring above the lower."""
        for index in range(segments):
            following = (index + 1) % segments
            a, b = upper + index, upper + following
            c, d = lower + index, lower + following
            self.indices.extend((a, c, d, a, d, b))

    def fan(self, ring: int, pole: int, segments: int, *, top: bool) -> None:
        """Triangles from a ring to a pole vertex above (``top``) or below it."""
        for index in range(segments):
            following = (index + 1) % segments
            if top:
                self.indices.extend((ring + index, ring + following, pole))
            else:
                self.indices.extend((ring + following, ring + index, pole))

    def disc(self, ring: int, segments: int, centre_z: float, *, top: bool) -> None:
        """A flat cap over a ring: its own vertices with the cap's normal, fanned from the centre."""
        normal = (0.0, 0.0, 1.0 if top else -1.0)
        centre = self.vertex((0.0, 0.0, centre_z), normal)
        rim = len(self.positions)
        for index in range(segments):
            self.vertex(self.positions[ring + index], normal)
        self.fan(rim, centre, segments, top=top)

    def arrays(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return (np.array(self.positions, dtype=np.float64), np.array(self.normals, dtype=np.float64),
                np.array(self.indices, dtype=np.uint32))


def _box(size: tuple[float, float, float]) -> _Mesh:
    hx, hy, hz = (float(value) / 2.0 for value in size)
    faces = (
        ((1, 0, 0), ((hx, -hy, -hz), (hx, hy, -hz), (hx, hy, hz), (hx, -hy, hz))),
        ((-1, 0, 0), ((-hx, hy, -hz), (-hx, -hy, -hz), (-hx, -hy, hz), (-hx, hy, hz))),
        ((0, 1, 0), ((hx, hy, -hz), (-hx, hy, -hz), (-hx, hy, hz), (hx, hy, hz))),
        ((0, -1, 0), ((-hx, -hy, -hz), (hx, -hy, -hz), (hx, -hy, hz), (-hx, -hy, hz))),
        ((0, 0, 1), ((-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz))),
        ((0, 0, -1), ((-hx, hy, -hz), (hx, hy, -hz), (hx, -hy, -hz), (-hx, -hy, -hz))),
    )
    mesh = _Mesh()
    for normal, corners in faces:
        base = len(mesh.positions)
        for corner in corners:
            mesh.vertex(corner, normal)
        mesh.indices.extend((base, base + 1, base + 2, base, base + 2, base + 3))
    return mesh


def _cylinder(radius: float, length: float) -> _Mesh:
    half = length / 2.0
    segments = primitive_segments(radius, math.sqrt(2 * (2 * radius) ** 2 + length**2))
    mesh = _Mesh()
    top = mesh.ring(segments, radius, 0.0, half)
    bottom = mesh.ring(segments, radius, 0.0, -half)
    mesh.join(top, bottom, segments)
    mesh.disc(top, segments, half, top=True)
    mesh.disc(bottom, segments, -half, top=False)
    return mesh


def _sphere(radius: float) -> _Mesh:
    segments = primitive_segments(radius, 2.0 * radius * math.sqrt(3.0))
    rings = max(2, int(math.ceil(segments / 2)))
    mesh = _Mesh()
    north = mesh.vertex((0.0, 0.0, radius), (0.0, 0.0, 1.0))
    south = mesh.vertex((0.0, 0.0, -radius), (0.0, 0.0, -1.0))
    starts = [mesh.ring(segments, radius, math.pi / 2.0 - math.pi * ring / rings, 0.0) for ring in range(1, rings)]
    mesh.fan(starts[0], north, segments, top=True)
    for upper, lower in zip(starts, starts[1:]):
        mesh.join(upper, lower, segments)
    mesh.fan(starts[-1], south, segments, top=False)
    return mesh


def _capsule(radius: float, length: float) -> _Mesh:
    half = length / 2.0
    segments = primitive_segments(radius, math.sqrt(2 * (2 * radius) ** 2 + (length + 2 * radius) ** 2))
    rings = max(2, int(math.ceil(segments / 4)))
    mesh = _Mesh()
    north = mesh.vertex((0.0, 0.0, half + radius), (0.0, 0.0, 1.0))
    south = mesh.vertex((0.0, 0.0, -half - radius), (0.0, 0.0, -1.0))
    # The top dome from just under its pole down to the equator at +half, the bottom dome
    # from the equator at -half down to just above its pole; the wall joins the equators.
    upper = [mesh.ring(segments, radius, (math.pi / 2.0) * (1.0 - ring / rings), half) for ring in range(1, rings + 1)]
    lower = [mesh.ring(segments, radius, -(math.pi / 2.0) * (ring / rings), -half) for ring in range(0, rings)]
    mesh.fan(upper[0], north, segments, top=True)
    for above, below in zip(upper + lower, (upper + lower)[1:]):
        mesh.join(above, below, segments)
    mesh.fan(lower[-1], south, segments, top=False)
    return mesh


def _build(shape: str, dimensions: dict) -> _Mesh:
    if shape == "box":
        size = dimensions["size"]
        return _box((float(size[0]), float(size[1]), float(size[2])))
    if shape == "cylinder":
        return _cylinder(float(dimensions["radius"]), float(dimensions["length"]))
    if shape == "sphere":
        return _sphere(float(dimensions["radius"]))
    if shape == "capsule":
        return _capsule(float(dimensions["radius"]), float(dimensions["length"]))
    raise ValueError(f"not a primitive shape this meshes: {shape!r} (one of {', '.join(PRIMITIVE_SHAPES)})")


def _y_up(values: np.ndarray) -> np.ndarray:
    """(x, y, z) Z-up -> (x, z, -y) glTF Y-up, float32."""
    return np.stack([values[:, 0], values[:, 2], -values[:, 1]], axis=1).astype("<f4")


def primitive_glb(shape: str, dimensions: dict) -> bytes:
    """The GLB of one primitive at its metres: ``box`` (``size``), ``cylinder`` and
    ``capsule`` (``radius``, ``length``, along Z), ``sphere`` (``radius``), each centred on
    its own origin as URDF and SDF place them."""
    positions, normals, indices = _build(shape, dimensions).arrays()
    y_up = _y_up(positions)
    position_bytes = y_up.tobytes()
    normal_bytes = _y_up(normals / np.linalg.norm(normals, axis=1, keepdims=True)).tobytes()
    index_bytes = indices.astype("<u4").tobytes()
    views: list[dict] = []
    chunks: list[bytes] = []
    size = 0

    def view(payload: bytes, target: int) -> int:
        nonlocal size
        padding = -size % 4
        if padding:
            chunks.append(b"\0" * padding)
            size += padding
        views.append({"buffer": 0, "byteOffset": size, "byteLength": len(payload), "target": target})
        chunks.append(payload)
        size += len(payload)
        return len(views) - 1

    document = {
        "asset": {"version": "2.0", "generator": "cadgen"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        # No node or mesh name: a primitive is a shape, not an authored object, and the page lists a
        # named object of a link's mesh as a part of its own (its visual already says "box").
        "nodes": [{"mesh": 0, "extras": {"cadSourceKind": "robot", "cadUnits": "m", "cadUpAxis": "y"}}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1}, "indices": 2, "mode": _TRIANGLES}]}],
        "accessors": [
            {"bufferView": view(position_bytes, _ARRAY_BUFFER), "componentType": _FLOAT, "count": len(positions), "type": "VEC3",
             "min": [float(value) for value in y_up.min(axis=0)], "max": [float(value) for value in y_up.max(axis=0)]},
            {"bufferView": view(normal_bytes, _ARRAY_BUFFER), "componentType": _FLOAT, "count": len(normals), "type": "VEC3"},
            {"bufferView": view(index_bytes, _ELEMENT_ARRAY_BUFFER), "componentType": _UNSIGNED_INT, "count": len(indices),
             "type": "SCALAR"},
        ],
        "bufferViews": views,
    }
    body = b"".join(chunks)
    body += b"\0" * (-len(body) % 4)
    document["buffers"] = [{"byteLength": len(body)}]
    encoded = json.dumps(document, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded += b" " * (-len(encoded) % 4)
    total = 12 + 8 + len(encoded) + 8 + len(body)
    return (struct.pack("<III", _GLB_MAGIC, _GLB_VERSION, total) + struct.pack("<II", len(encoded), _JSON_CHUNK) + encoded
            + struct.pack("<II", len(body), _BIN_CHUNK) + body)
