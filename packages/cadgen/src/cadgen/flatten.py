"""Flat patterns from 3D topology: exact 2D geometry for ``@dxf`` drawings.

A drawing generator returns build123d 2D geometry and the engine writes the DXF
(cadgen._internal.dxf_emit). This module is the bridge from a solid to that
geometry: pick the planar faces that make up the flat pattern, lay each one into
the XY plane, fuse them, and — where the cutting process needs it — offset for
kerf. Everything it hands back is build123d geometry, ready to return from a
``@dxf`` function.

**Exact, not sampled.** The union and the offset are OCC boolean and OCC offset
operations on the real faces, so an arc stays an arc: a filleted corner exports
as a DXF ``ARC``, a hole as a ``CIRCLE``, and kerf compensation preserves both.
The previous pipeline sampled every wire into a point list, unioned polygons in
shapely, and emitted polylines — which turned every curve into a run of chords
before it ever reached the file, at a resolution nobody chose. Shapely survives
here only as an internal fallback for the unions OCC refuses (see
:func:`union_faces`), and even then only its topology is borrowed.

A worked example lives in ``skills/dxf/references/generator-templates.md``.
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

# The lazy proxy, not the kernel: `from cadgen import flatten` sits in a drawing
# script's module body, and every use below is attribute-style (`build123d.Plane`),
# so the real ~2.5s import happens on the first call, never on import.
import cadgen.build123d as build123d


# A projected contour smaller than this is sampling debris, not a cut path.
MIN_CUT_CONTOUR_AREA_MM2 = 0.05
# Merge tolerance for the shapely fallback's rebuilt polygons. Far below any
# fabrication tolerance; it exists to keep duplicate points out of a contour.
POINT_MERGE_TOLERANCE_MM = 0.01


def axis_value(vector: build123d.Vector, axis: str) -> float:
    return {"x": vector.X, "y": vector.Y, "z": vector.Z}[axis]


def snap(value: float, source: float, target: float, *, tolerance: float = 1e-3) -> float:
    return target if abs(value - source) <= tolerance else value


def planar_faces(
    shape: build123d.Shape,
    *,
    normal_axis: str,
    normal_sign: float,
    coordinate_axis: str,
    coordinate: float,
    tolerance: float = 0.02,
    min_area: float = 1e-5,
) -> tuple[build123d.Face, ...]:
    """The planar faces of ``shape`` facing one way at one height.

    This is the selection step of a flat pattern: "every upward face of the top
    surface", "every outward face of the left flange". Raises rather than
    returning nothing — an empty selection means the plane or the sign is wrong,
    and a drawing generated from no faces is an empty file nobody notices.
    """
    matches: list[build123d.Face] = []
    for face in shape.faces():
        if face.geom_type != build123d.GeomType.PLANE:
            continue
        normal = face.normal_at()
        center = face.center()
        if abs(axis_value(normal, normal_axis) - normal_sign) > 0.02:
            continue
        if abs(axis_value(center, coordinate_axis) - coordinate) > tolerance:
            continue
        if face.area <= min_area:
            continue
        matches.append(face)
    if not matches:
        raise RuntimeError(
            "Could not find planar topology faces for DXF projection: "
            f"normal {normal_sign:+.0f}{normal_axis}, {coordinate_axis}={coordinate:.3f}"
        )
    return tuple(matches)


def flatten_face(face: build123d.Face) -> build123d.Face:
    """Lay one planar face into the XY plane, exactly.

    The face is moved by the rigid transform that takes its own plane to XY — no
    sampling, no projection error, and every curve survives as itself. A DXF is
    2D and the engine refuses geometry off the XY plane, so this (or an explicit
    ``bd.Location((0, 0, -z)) * face``) is how a derived face becomes drawable.

    A face whose normal points away from +Z comes back mirrored, because that is
    what looking at it from its own side means. Flip the source face first if you
    want the other handedness.
    """
    plane = build123d.Plane(face)
    return plane.to_local_coords(face)


def flatten_faces(faces: Iterable[build123d.Face]) -> tuple[build123d.Face, ...]:
    """:func:`flatten_face` over a selection."""
    return tuple(flatten_face(face) for face in faces)


def union_faces(faces: Sequence[build123d.Shape]) -> build123d.Shape:
    """Fuse coplanar XY faces into one profile, exactly.

    OCC's boolean is the primary path: overlapping faces merge, shared edges
    disappear, holes survive as inner wires, and arcs stay arcs. Disjoint faces
    come back as a multi-face result, which is a perfectly good nested cut
    layout.

    Shapely is the fallback, and only that. OCC refuses some genuinely
    degenerate inputs — faces that touch along a zero-width sliver, self-
    intersecting projections of a fold — where a tolerant polygon union still
    gives a usable contour. Taking that route costs curvature (the rebuilt
    profile is polygonal), so it is never the default and never silent.
    """
    shapes = [face for face in faces if face is not None]
    if not shapes:
        raise RuntimeError("No faces were given to union into a DXF profile")
    if len(shapes) == 1:
        return shapes[0]
    try:
        fused = shapes[0].fuse(*shapes[1:]).clean()
    except Exception as exact_error:  # noqa: BLE001 - OCC raises many types; the fallback is the point
        return _shapely_union_fallback(shapes, cause=exact_error)
    if not fused.faces():
        return _shapely_union_fallback(shapes, cause=RuntimeError("the exact union was empty"))
    return fused


def offset_profile(shape: build123d.Shape, amount: float) -> build123d.Shape:
    """Kerf / tool-radius compensation, exactly.

    Positive grows the profile (cut outside the line), negative shrinks it (cut
    inside). The offset is OCC's, so a filleted corner offsets to a concentric
    arc rather than to a fan of chords — the single biggest reason this module
    stopped going through shapely.
    """
    if amount == 0.0:
        return shape
    try:
        offset = build123d.offset(shape, amount=amount)
    except Exception as error:  # noqa: BLE001 - OCC/build123d report a consumed profile several ways
        offset = None
        failure: BaseException | None = error
    else:
        failure = None
    if offset is None or not offset.faces():
        raise RuntimeError(
            f"Kerf offset of {amount:+.3f} mm produced no profile. A negative offset "
            "at or beyond half the narrowest feature consumes it entirely — check the "
            "sign (positive grows the cut, negative shrinks it) and the magnitude."
        ) from failure
    return offset


def flat_pattern(
    shape: build123d.Shape,
    *,
    normal_axis: str = "z",
    normal_sign: float = 1.0,
    coordinate_axis: str = "z",
    coordinate: float,
    tolerance: float = 0.02,
    kerf: float = 0.0,
) -> build123d.Shape:
    """Select, flatten, fuse, and optionally kerf-offset — the usual whole job.

    The three steps are separately available above for drawings that need them
    apart (a multi-plane bracket flattens each flange with its own selection
    before one union)."""
    faces = planar_faces(
        shape,
        normal_axis=normal_axis,
        normal_sign=normal_sign,
        coordinate_axis=coordinate_axis,
        coordinate=coordinate,
        tolerance=tolerance,
    )
    profile = union_faces(flatten_faces(faces))
    return offset_profile(profile, kerf) if kerf else profile


# --- the fallback ---------------------------------------------------------------------
# Kept small and internal on purpose. It exists for the unions OCC will not do, and
# it converts curves to chords on the way, so nothing above reaches for it by choice.


def _shapely_union_fallback(shapes: Sequence[build123d.Shape], *, cause: BaseException):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    polygons = []
    for shape in shapes:
        for face in shape.faces():
            polygon = Polygon(
                _wire_points(face.outer_wire()),
                [_wire_points(wire) for wire in face.inner_wires() if wire.length > 1e-6],
            )
            if not polygon.is_valid:
                polygon = polygon.buffer(0)
            if not polygon.is_empty:
                polygons.append(polygon)
    if not polygons:
        raise RuntimeError(f"Could not union these faces into a DXF profile: {cause}") from cause
    geometry = unary_union(polygons).buffer(0)
    if geometry.is_empty:
        raise RuntimeError(f"Could not union these faces into a DXF profile: {cause}") from cause
    faces = [
        face
        for polygon in (geometry.geoms if geometry.geom_type != "Polygon" else [geometry])
        if polygon.area >= MIN_CUT_CONTOUR_AREA_MM2
        for face in [_face_from_polygon(polygon)]
        if face is not None
    ]
    if not faces:
        raise RuntimeError(f"Could not union these faces into a DXF profile: {cause}") from cause
    return faces[0] if len(faces) == 1 else build123d.Sketch(children=faces)


def _wire_points(wire: build123d.Wire, *, max_segment_mm: float = 0.25) -> list[tuple[float, float]]:
    sample_count = max(16, int(math.ceil(wire.length / max_segment_mm)))
    points: list[tuple[float, float]] = []
    for index in range(sample_count):
        position = wire.position_at(index / sample_count)
        point = (float(position.X), float(position.Y))
        if not points or math.dist(points[-1], point) > POINT_MERGE_TOLERANCE_MM:
            points.append(point)
    while len(points) >= 2 and math.dist(points[0], points[-1]) <= POINT_MERGE_TOLERANCE_MM:
        points.pop()
    return points


def _face_from_polygon(polygon) -> build123d.Face | None:
    outer = _face_from_ring(polygon.exterior)
    if outer is None:
        return None
    for interior in polygon.interiors:
        hole = _face_from_ring(interior)
        if hole is not None:
            outer = outer.cut(hole)
    faces = outer.faces()
    return faces[0] if faces else None


def _face_from_ring(ring) -> build123d.Face | None:
    points = [(float(x), float(y)) for x, y in ring.coords]
    while len(points) >= 2 and math.dist(points[0], points[-1]) <= POINT_MERGE_TOLERANCE_MM:
        points.pop()
    if len(points) < 3:
        return None
    wire = build123d.Polyline(*[(x, y, 0.0) for x, y in points], close=True)
    return build123d.make_face(wire)
