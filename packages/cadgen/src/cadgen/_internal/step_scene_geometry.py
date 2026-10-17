from __future__ import annotations

import math
from typing import Any

from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepAdaptor import BRepAdaptor_Curve2d
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepLProp import BRepLProp_SLProps
from OCP.Bnd import Bnd_Box
from OCP.TopAbs import TopAbs_REVERSED

from cadgen._internal.glb_topology import STEP_EDGE_SAMPLE_COUNT

from cadgen._internal.step_scene_types import _enum_name


def _round_value(value: float, digits: int | None) -> float:
    if digits is None:
        return float(value)
    return round(float(value), digits)


def _round_point(point: list[float] | tuple[float, float, float], digits: int | None) -> list[float]:
    if digits is None:
        return [float(point[0]), float(point[1]), float(point[2])]
    return [round(float(point[0]), digits), round(float(point[1]), digits), round(float(point[2]), digits)]


def _normalize(vector: tuple[float, float, float] | list[float]) -> list[float] | None:
    x, y, z = vector
    length = math.sqrt(x * x + y * y + z * z)
    if length <= 1e-12:
        return None
    return [x / length, y / length, z / length]


def _angle_between_vectors_deg(left: list[float] | tuple[float, ...] | None, right: list[float] | tuple[float, ...] | None) -> float | None:
    left_normal = _normalize(left or (0.0, 0.0, 0.0))
    right_normal = _normalize(right or (0.0, 0.0, 0.0))
    if left_normal is None or right_normal is None:
        return None
    dot = max(-1.0, min(1.0, sum(left_normal[index] * right_normal[index] for index in range(3))))
    return math.degrees(math.acos(dot))


def _bbox_from_points(points: list[list[float]]) -> dict[str, Any]:
    if not points:
        zero = [0.0, 0.0, 0.0]
        return {"min": zero[:], "max": zero[:], "center": zero[:], "size": zero[:], "diag": 0.0}
    min_x = max_x = points[0][0]
    min_y = max_y = points[0][1]
    min_z = max_z = points[0][2]
    for x, y, z in points[1:]:
        if x < min_x:
            min_x = x
        if x > max_x:
            max_x = x
        if y < min_y:
            min_y = y
        if y > max_y:
            max_y = y
        if z < min_z:
            min_z = z
        if z > max_z:
            max_z = z
    size = [max_x - min_x, max_y - min_y, max_z - min_z]
    center = [min_x + size[0] * 0.5, min_y + size[1] * 0.5, min_z + size[2] * 0.5]
    return {
        "min": [min_x, min_y, min_z],
        "max": [max_x, max_y, max_z],
        "center": center,
        "size": size,
        "diag": math.sqrt(size[0] * size[0] + size[1] * size[1] + size[2] * size[2]),
    }


def _merge_bbox(boxes: list[dict[str, Any]]) -> dict[str, Any]:
    points: list[list[float]] = []
    for box in boxes:
        points.append(list(box["min"]))
        points.append(list(box["max"]))
    return _bbox_from_points(points)


def _bbox_from_shape(shape: Any, *, tight: bool = True) -> dict[str, Any]:
    box = Bnd_Box()
    if tight:
        BRepBndLib.AddOptimal_s(shape, box, False, False)
    else:
        # Loose geometric bounds (control-point based for splines). ~40% of a
        # forced heavy-assembly rebuild was AddOptimal tightening boxes whose
        # only consumer is the adaptive-mesh scale heuristic, which needs the
        # diagonal's magnitude, not tight extents.
        BRepBndLib.Add_s(shape, box, False)
    if box.IsVoid():
        return _bbox_from_points([])
    min_x, min_y, min_z, max_x, max_y, max_z = box.Get()
    return _bbox_from_points(
        [
            [min_x, min_y, min_z],
            [max_x, max_y, max_z],
        ]
    )


def _point_from_occ(point: Any) -> list[float]:
    return [point.X(), point.Y(), point.Z()]


def _apply_transform_point(transform: tuple[float, ...], point: list[float]) -> list[float]:
    x, y, z = point
    return [
        (transform[0] * x) + (transform[1] * y) + (transform[2] * z) + transform[3],
        (transform[4] * x) + (transform[5] * y) + (transform[6] * z) + transform[7],
        (transform[8] * x) + (transform[9] * y) + (transform[10] * z) + transform[11],
    ]


def _transform_bbox(box: dict[str, Any], transform: tuple[float, ...]) -> dict[str, Any]:
    min_x, min_y, min_z = box["min"]
    max_x, max_y, max_z = box["max"]
    corners = [
        [min_x, min_y, min_z],
        [min_x, min_y, max_z],
        [min_x, max_y, min_z],
        [min_x, max_y, max_z],
        [max_x, min_y, min_z],
        [max_x, min_y, max_z],
        [max_x, max_y, min_z],
        [max_x, max_y, max_z],
    ]
    return _bbox_from_points([_apply_transform_point(transform, corner) for corner in corners])


def _curve_params(adaptor: BRepAdaptor_Curve, digits: int | None) -> dict[str, Any]:
    curve_type = _enum_name(adaptor.GetType(), "GeomAbs_")
    params: dict[str, Any] = {}
    if curve_type == "line":
        line = adaptor.Line()
        params["origin"] = _round_point(_point_from_occ(line.Location()), digits)
        params["direction"] = _round_point(_point_from_occ(line.Direction()), digits)
    elif curve_type == "circle":
        circle = adaptor.Circle()
        params["center"] = _round_point(_point_from_occ(circle.Location()), digits)
        params["axis"] = _round_point(_point_from_occ(circle.Axis().Direction()), digits)
        params["radius"] = _round_value(circle.Radius(), digits)
    elif curve_type == "ellipse":
        ellipse = adaptor.Ellipse()
        params["center"] = _round_point(_point_from_occ(ellipse.Location()), digits)
        params["axis"] = _round_point(_point_from_occ(ellipse.Axis().Direction()), digits)
        params["majorRadius"] = _round_value(ellipse.MajorRadius(), digits)
        params["minorRadius"] = _round_value(ellipse.MinorRadius(), digits)
    elif curve_type == "hyperbola":
        hyperbola = adaptor.Hyperbola()
        params["center"] = _round_point(_point_from_occ(hyperbola.Location()), digits)
        params["axis"] = _round_point(_point_from_occ(hyperbola.Axis().Direction()), digits)
        params["majorRadius"] = _round_value(hyperbola.MajorRadius(), digits)
        params["minorRadius"] = _round_value(hyperbola.MinorRadius(), digits)
    elif curve_type == "parabola":
        parabola = adaptor.Parabola()
        params["center"] = _round_point(_point_from_occ(parabola.Location()), digits)
        params["axis"] = _round_point(_point_from_occ(parabola.Axis().Direction()), digits)
        params["focal"] = _round_value(parabola.Focal(), digits)
    elif curve_type in {"beziercurve", "bsplinecurve"}:
        params["degree"] = int(adaptor.Degree())
        params["periodic"] = bool(adaptor.IsPeriodic())
        params["rational"] = bool(adaptor.IsRational())
    return params


def _surface_params(adaptor: BRepAdaptor_Surface, digits: int | None) -> dict[str, Any]:
    surface_type = _enum_name(adaptor.GetType(), "GeomAbs_")
    params: dict[str, Any] = {}
    if surface_type == "plane":
        plane = adaptor.Plane()
        params["origin"] = _round_point(_point_from_occ(plane.Location()), digits)
        params["axis"] = _round_point(_point_from_occ(plane.Axis().Direction()), digits)
    elif surface_type == "cylinder":
        cylinder = adaptor.Cylinder()
        params["origin"] = _round_point(_point_from_occ(cylinder.Location()), digits)
        params["axis"] = _round_point(_point_from_occ(cylinder.Axis().Direction()), digits)
        params["radius"] = _round_value(cylinder.Radius(), digits)
    elif surface_type == "cone":
        cone = adaptor.Cone()
        params["origin"] = _round_point(_point_from_occ(cone.Location()), digits)
        params["axis"] = _round_point(_point_from_occ(cone.Axis().Direction()), digits)
        params["semiAngleRad"] = _round_value(cone.SemiAngle(), digits)
    elif surface_type == "sphere":
        sphere = adaptor.Sphere()
        params["center"] = _round_point(_point_from_occ(sphere.Location()), digits)
        params["radius"] = _round_value(sphere.Radius(), digits)
    elif surface_type == "torus":
        torus = adaptor.Torus()
        params["center"] = _round_point(_point_from_occ(torus.Location()), digits)
        params["axis"] = _round_point(_point_from_occ(torus.Axis().Direction()), digits)
        params["majorRadius"] = _round_value(torus.MajorRadius(), digits)
        params["minorRadius"] = _round_value(torus.MinorRadius(), digits)
    elif surface_type in {"beziersurface", "bsplinesurface"}:
        params["uClosed"] = bool(adaptor.IsUPeriodic())
        params["vClosed"] = bool(adaptor.IsVPeriodic())
    return params


def _is_smooth_continuity(value: object) -> bool:
    return str(value or "").lower() in {"g1", "c1", "g2", "c2", "c3", "cn"}


def _edge_continuity_name(edge: Any, face_shapes: list[Any]) -> str:
    if len(face_shapes) != 2:
        return ""
    try:
        if not BRep_Tool.HasContinuity_s(edge, face_shapes[0], face_shapes[1]):
            return ""
        return _enum_name(BRep_Tool.Continuity_s(edge, face_shapes[0], face_shapes[1]), "GeomAbs_")
    except Exception:  # noqa: BLE001 - OCP continuity queries can raise on odd edges; unknown continuity is an empty string
        return ""


def face_surface(face: Any) -> Any:
    """The face's surface adaptor restricted to the face's parameter bounds -- what an edge's
    dihedral angle reads the face's normal from. Restricting runs over every edge of the
    face, so the caller makes it once per face, however many of its edges ask."""
    return BRepAdaptor_Surface(face, True)


def _face_normal_at_edge_fraction(curve: Any, face: Any, props: Any, fraction: float) -> list[float] | None:
    """The face's oriented unit normal where the edge is at ``fraction`` of its parameter
    range: ``curve`` is the edge's parameter curve on the face, ``props`` the face's surface
    properties (``BRepLProp_SLProps`` over :func:`face_surface`)."""
    first = float(curve.FirstParameter())
    last = float(curve.LastParameter())
    if not math.isfinite(first) or not math.isfinite(last) or abs(last - first) <= 1e-12:
        return None
    uv = curve.Value(first + ((last - first) * fraction))
    props.SetParameters(float(uv.X()), float(uv.Y()))
    if not props.IsNormalDefined():
        return None
    normal = _point_from_occ(props.Normal())
    if face.Orientation() == TopAbs_REVERSED:
        normal = [-normal[0], -normal[1], -normal[2]]
    return _normalize(normal)


def _sampled_edge_dihedral_deg(edge: Any, face_shapes: list[Any], surfaces: list[Any]) -> float | None:
    """The largest angle between the two faces' normals at the edge's sample points;
    ``surfaces`` holds each face's :func:`face_surface`, None where it could not be made."""
    if len(face_shapes) != 2:
        return None
    try:
        curves = [BRepAdaptor_Curve2d(edge, face) for face in face_shapes]
        props = [BRepLProp_SLProps(surface, 1, 1e-6) for surface in surfaces]
    except Exception:  # noqa: BLE001 - an edge with no curve on a face, or a face with no surface, has no angle
        return None
    max_angle: float | None = None
    denominator = STEP_EDGE_SAMPLE_COUNT + 1
    for index in range(1, STEP_EDGE_SAMPLE_COUNT + 1):
        fraction = index / denominator
        try:
            left_normal = _face_normal_at_edge_fraction(curves[0], face_shapes[0], props[0], fraction)
            right_normal = _face_normal_at_edge_fraction(curves[1], face_shapes[1], props[1], fraction)
        except Exception:  # noqa: BLE001 - OCP normal queries can raise; a skipped sample must not fail the edge read
            left_normal = None
            right_normal = None
        angle = _angle_between_vectors_deg(left_normal, right_normal)
        if angle is not None and math.isfinite(angle):
            max_angle = angle if max_angle is None else max(max_angle, angle)
    return max_angle
