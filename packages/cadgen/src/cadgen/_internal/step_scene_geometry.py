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
from OCP.GCPnts import GCPnts_QuasiUniformDeflection
from OCP.TopAbs import TopAbs_REVERSED
from OCP.TopAbs import TopAbs_VERTEX
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS

from cadgen._internal.glb_mesh_payload import transform_normal_from_occ as _transform_normal_from_occ
from cadgen._internal.glb_topology import STEP_EDGE_FLAGS
from cadgen._internal.glb_topology import STEP_EDGE_VISIBILITY_CLASSES
from cadgen._internal.glb_topology import STEP_TOPOLOGY_EDGE_ANGULAR_TOLERANCE_DEG
from cadgen._internal.glb_topology import STEP_TOPOLOGY_EDGE_SAMPLE_COUNT

from cadgen._internal.step_scene_types import _enum_name


def _round_value(value: float, digits: int | None) -> float:
    if digits is None:
        return float(value)
    return round(float(value), digits)


def _round_point(point: list[float] | tuple[float, float, float], digits: int | None) -> list[float]:
    if digits is None:
        return [float(point[0]), float(point[1]), float(point[2])]
    return [round(float(point[0]), digits), round(float(point[1]), digits), round(float(point[2]), digits)]


def _round_transform(matrix: tuple[float, ...], digits: int | None) -> list[float]:
    if digits is None:
        return [float(value) for value in matrix]
    return [round(float(value), digits) for value in matrix]


def _normalize(vector: tuple[float, float, float] | list[float]) -> list[float] | None:
    x, y, z = vector
    length = math.sqrt(x * x + y * y + z * z)
    if length <= 1e-12:
        return None
    return [x / length, y / length, z / length]


def _cross(a: list[float], b: list[float], c: list[float]) -> tuple[float, float, float]:
    abx = b[0] - a[0]
    aby = b[1] - a[1]
    abz = b[2] - a[2]
    acx = c[0] - a[0]
    acy = c[1] - a[1]
    acz = c[2] - a[2]
    return (
        aby * acz - abz * acy,
        abz * acx - abx * acz,
        abx * acy - aby * acx,
    )


def _distance(a: list[float], b: list[float]) -> float:
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    dz = a[2] - b[2]
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _triangle_side_key(left: int, right: int) -> tuple[int, int]:
    a = max(0, int(left))
    b = max(0, int(right))
    return (a, b) if a < b else (b, a)


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


def _compact_bbox(box: dict[str, Any], digits: int | None) -> dict[str, Any]:
    return {
        "min": _round_point(box["min"], digits),
        "max": _round_point(box["max"], digits),
    }


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


def _transform_point_from_occ(point: Any, location: TopLoc_Location) -> list[float]:
    transformed = point.Transformed(location.Transformation())
    return [transformed.X(), transformed.Y(), transformed.Z()]


def _point_from_occ(point: Any) -> list[float]:
    return [point.X(), point.Y(), point.Z()]


def _apply_transform_point(transform: tuple[float, ...], point: list[float]) -> list[float]:
    x, y, z = point
    return [
        (transform[0] * x) + (transform[1] * y) + (transform[2] * z) + transform[3],
        (transform[4] * x) + (transform[5] * y) + (transform[6] * z) + transform[7],
        (transform[8] * x) + (transform[9] * y) + (transform[10] * z) + transform[11],
    ]


def _apply_transform_vector(transform: tuple[float, ...], vector: list[float]) -> list[float] | None:
    x, y, z = vector
    return _normalize(
        (
            (transform[0] * x) + (transform[1] * y) + (transform[2] * z),
            (transform[4] * x) + (transform[5] * y) + (transform[6] * z),
            (transform[8] * x) + (transform[9] * y) + (transform[10] * z),
        )
    )


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


def _transform_param_dict(params: dict[str, Any], transform: tuple[float, ...], digits: int | None) -> dict[str, Any]:
    point_keys = {"origin", "center", "location"}
    vector_keys = {"axis", "direction", "normal"}
    transformed: dict[str, Any] = {}
    for key, value in params.items():
        if key in point_keys and isinstance(value, list) and len(value) == 3:
            transformed[key] = _round_point(_apply_transform_point(transform, value), digits)
        elif key in vector_keys and isinstance(value, list) and len(value) == 3:
            vector = _apply_transform_vector(transform, value)
            transformed[key] = _round_point(vector or value, digits)
        else:
            transformed[key] = value
    return transformed


def _dedupe_consecutive(points: list[list[float]], tolerance: float) -> list[list[float]]:
    if not points:
        return points
    deduped = [points[0]]
    for point in points[1:]:
        if _distance(deduped[-1], point) > tolerance:
            deduped.append(point)
    return deduped


def _decimate_polyline(points: list[list[float]], max_points: int) -> list[list[float]]:
    if max_points <= 1 or len(points) <= max_points:
        return points
    stride = (len(points) - 1) / float(max_points - 1)
    result = []
    last_index = -1
    for i in range(max_points):
        index = int(round(i * stride))
        if index >= len(points):
            index = len(points) - 1
        if index != last_index:
            result.append(points[index])
            last_index = index
    if result[-1] != points[-1]:
        result[-1] = points[-1]
    return result


def _polyline_length(points: list[list[float]], closed: bool) -> float:
    if len(points) < 2:
        return 0.0
    total = 0.0
    for left, right in zip(points, points[1:]):
        total += _distance(left, right)
    if closed and _distance(points[0], points[-1]) > 1e-9:
        total += _distance(points[-1], points[0])
    return total


def _polyline_center(points: list[list[float]]) -> list[float]:
    if not points:
        return [0.0, 0.0, 0.0]
    total = [0.0, 0.0, 0.0]
    for point in points:
        total[0] += point[0]
        total[1] += point[1]
        total[2] += point[2]
    inv = 1.0 / len(points)
    return [total[0] * inv, total[1] * inv, total[2] * inv]


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


def _extract_face_geometry(face: Any) -> dict[str, Any]:
    location = TopLoc_Location()
    triangulation = BRep_Tool.Triangulation_s(face, location)
    if triangulation is None:
        return {
            "nodes": [],
            "normals": [],
            "triangles": [],
            "triangleCount": 0,
            "area": 0.0,
            "center": [0.0, 0.0, 0.0],
            "normal": None,
            "bbox": _bbox_from_points([]),
            "triangulation": None,
            "location": location,
        }

    if not triangulation.HasNormals():
        triangulation.ComputeNormals()
    reversed_face = face.Orientation() == TopAbs_REVERSED
    nodes = [_transform_point_from_occ(triangulation.Node(index), location) for index in range(1, triangulation.NbNodes() + 1)]
    normals = [
        _transform_normal_from_occ(triangulation.Normal(index), location, reversed_face=reversed_face)
        for index in range(1, triangulation.NbNodes() + 1)
    ]
    triangles: list[tuple[int, int, int]] = []
    area_sum = 0.0
    centroid_sum = [0.0, 0.0, 0.0]
    normal_sum = [0.0, 0.0, 0.0]

    for index in range(1, triangulation.NbTriangles() + 1):
        node_a, node_b, node_c = triangulation.Triangle(index).Get()
        point_a = nodes[node_a - 1]
        point_b = nodes[node_b - 1]
        point_c = nodes[node_c - 1]
        normal_x, normal_y, normal_z = _cross(point_a, point_b, point_c)
        twice_area = math.sqrt((normal_x * normal_x) + (normal_y * normal_y) + (normal_z * normal_z))
        # GLB export filters in meters with a 1e-15 twice-area floor. Selector
        # extraction stores CAD units, so use the equivalent millimeter-scale
        # threshold to keep v3 face runs aligned with GLB primitive triangles.
        if twice_area <= 1e-9:
            continue
        area = twice_area * 0.5
        centroid_sum[0] += (point_a[0] + point_b[0] + point_c[0]) * area / 3.0
        centroid_sum[1] += (point_a[1] + point_b[1] + point_c[1]) * area / 3.0
        centroid_sum[2] += (point_a[2] + point_b[2] + point_c[2]) * area / 3.0
        normal_sum[0] += normal_x
        normal_sum[1] += normal_y
        normal_sum[2] += normal_z
        area_sum += area
        triangle = [node_a - 1, node_b - 1, node_c - 1]
        if reversed_face:
            triangle[1], triangle[2] = triangle[2], triangle[1]
        triangles.append((triangle[0], triangle[1], triangle[2]))

    if not nodes:
        center = [0.0, 0.0, 0.0]
    elif area_sum > 1e-12:
        center = [
            centroid_sum[0] / area_sum,
            centroid_sum[1] / area_sum,
            centroid_sum[2] / area_sum,
        ]
    else:
        center = _bbox_from_points(nodes)["center"]

    normal = _normalize((normal_sum[0], normal_sum[1], normal_sum[2]))
    if normal and reversed_face:
        normal = [-normal[0], -normal[1], -normal[2]]

    return {
        "nodes": nodes,
        "normals": normals,
        "triangles": triangles,
        "triangleCount": len(triangles),
        "area": area_sum,
        "center": center,
        "normal": normal,
        "bbox": _bbox_from_points(nodes),
        "triangulation": triangulation,
        "location": location,
    }


def _edge_polygon_node_indices_from_face_mesh(edge: Any, face_mesh: dict[str, Any]) -> list[int]:
    triangulation = face_mesh["triangulation"]
    if triangulation is None:
        return []
    polygon = BRep_Tool.PolygonOnTriangulation_s(edge, triangulation, face_mesh["location"])
    if polygon is None:
        return []
    return [int(polygon.Node(index)) - 1 for index in range(1, polygon.NbNodes() + 1)]


def _edge_points_from_face_polygon(face_mesh: dict[str, Any], node_indices: list[int], max_points: int) -> list[list[float]]:
    points = [
        face_mesh["nodes"][node_index]
        for node_index in node_indices
        if 0 <= node_index < len(face_mesh["nodes"])
    ]
    points = _dedupe_consecutive(points, 1e-9)
    if points and max_points > 1:
        points = _decimate_polyline(points, max_points)
    return points


def _extract_edge_points_from_curve(edge: Any, deflection: float, max_points: int) -> list[list[float]]:
    adaptor = BRepAdaptor_Curve(edge)
    curve_type = _enum_name(adaptor.GetType(), "GeomAbs_")
    if curve_type == "line":
        points = [
            _point_from_occ(adaptor.Value(adaptor.FirstParameter())),
            _point_from_occ(adaptor.Value(adaptor.LastParameter())),
        ]
        return _dedupe_consecutive(points, max(deflection * 0.25, 1e-9))

    points: list[list[float]] = []
    try:
        sampler = GCPnts_QuasiUniformDeflection(
            adaptor,
            deflection,
            adaptor.FirstParameter(),
            adaptor.LastParameter(),
        )
        if sampler.IsDone():
            points = [_point_from_occ(sampler.Value(index)) for index in range(1, sampler.NbPoints() + 1)]
    except Exception:  # noqa: BLE001 - OCP sampling can raise on degenerate curves; fall back to vertex points
        points = []

    if not points:
        vertex_points = []
        explorer = TopExp_Explorer(edge, TopAbs_VERTEX)
        while explorer.More():
            vertex = TopoDS.Vertex_s(explorer.Current())
            vertex_points.append(_point_from_occ(BRep_Tool.Pnt_s(vertex)))
            explorer.Next()
        points = vertex_points

    points = _dedupe_consecutive(points, max(deflection * 0.25, 1e-9))
    if points and max_points > 1:
        points = _decimate_polyline(points, max_points)
    return points


def _face_flags(face_data: dict[str, Any]) -> int:
    return 1 if not face_data.get("referenceable", True) else 0


def _edge_flags(edge_data: dict[str, Any]) -> int:
    flags = 0
    if edge_data.get("closed", False):
        flags |= 1
    if edge_data.get("degenerated", False):
        flags |= STEP_EDGE_FLAGS["DEGENERATE"]
    if edge_data.get("seam", False):
        flags |= STEP_EDGE_FLAGS["SEAM"]
    if not edge_data.get("referenceable", True):
        flags |= STEP_EDGE_FLAGS["NOT_REFERENCEABLE"]
    return flags


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


def _face_normal_at_edge_fraction(edge: Any, face: Any, fraction: float) -> list[float] | None:
    curve = BRepAdaptor_Curve2d(edge, face)
    first = float(curve.FirstParameter())
    last = float(curve.LastParameter())
    if not math.isfinite(first) or not math.isfinite(last) or abs(last - first) <= 1e-12:
        return None
    uv = curve.Value(first + ((last - first) * fraction))
    surface = BRepAdaptor_Surface(face, True)
    props = BRepLProp_SLProps(surface, 1, 1e-6)
    props.SetParameters(float(uv.X()), float(uv.Y()))
    if not props.IsNormalDefined():
        return None
    normal = _point_from_occ(props.Normal())
    if face.Orientation() == TopAbs_REVERSED:
        normal = [-normal[0], -normal[1], -normal[2]]
    return _normalize(normal)


def _sampled_edge_dihedral_deg(edge: Any, face_shapes: list[Any], fallback_normals: list[list[float] | None]) -> float | None:
    if len(face_shapes) != 2:
        return None
    max_angle: float | None = None
    denominator = STEP_TOPOLOGY_EDGE_SAMPLE_COUNT + 1
    for index in range(1, STEP_TOPOLOGY_EDGE_SAMPLE_COUNT + 1):
        fraction = index / denominator
        try:
            left_normal = _face_normal_at_edge_fraction(edge, face_shapes[0], fraction)
            right_normal = _face_normal_at_edge_fraction(edge, face_shapes[1], fraction)
        except Exception:  # noqa: BLE001 - OCP normal queries can raise; a skipped sample must not fail the edge read
            left_normal = None
            right_normal = None
        angle = _angle_between_vectors_deg(left_normal, right_normal)
        if angle is not None and math.isfinite(angle):
            max_angle = angle if max_angle is None else max(max_angle, angle)
    if max_angle is not None:
        return max_angle
    return _angle_between_vectors_deg(fallback_normals[0], fallback_normals[1]) if len(fallback_normals) == 2 else None


def _classify_edge(
    edge_data: dict[str, Any],
    *,
    edge: Any,
    face_shapes: list[Any],
    face_normals: list[list[float] | None],
    face_use_counts: dict[int, int],
) -> None:
    flags = _edge_flags(edge_data)
    adjacent_face_count = len(edge_data.get("faceOrdinals", ()))
    continuity = ""
    dihedral_deg: float | None = None
    visibility_class = STEP_EDGE_VISIBILITY_CLASSES["FEATURE"]

    if edge_data.get("degenerated", False) or len(edge_data.get("points", ())) < 2 or float(edge_data.get("length") or 0.0) <= 1e-9:
        flags |= STEP_EDGE_FLAGS["DEGENERATE"]
        visibility_class = STEP_EDGE_VISIBILITY_CLASSES["DEGENERATE"]
        continuity = "degenerate"
    elif edge_data.get("seam", False) or any(int(count) > 1 for count in face_use_counts.values()):
        flags |= STEP_EDGE_FLAGS["SEAM"]
        visibility_class = STEP_EDGE_VISIBILITY_CLASSES["SEAM"]
        continuity = "seam"
    elif adjacent_face_count <= 0:
        flags |= STEP_EDGE_FLAGS["NOT_REFERENCEABLE"] | STEP_EDGE_FLAGS["UNKNOWN_CONTINUITY"]
        continuity = "unknown"
    elif adjacent_face_count == 1:
        flags |= STEP_EDGE_FLAGS["BOUNDARY"]
        continuity = "boundary"
    elif adjacent_face_count > 2:
        flags |= STEP_EDGE_FLAGS["NON_MANIFOLD"]
        visibility_class = STEP_EDGE_VISIBILITY_CLASSES["NON_MANIFOLD"]
        continuity = "non_manifold"
    else:
        continuity = _edge_continuity_name(edge, face_shapes)
        if continuity == "c0":
            flags |= STEP_EDGE_FLAGS["HARD"]
            dihedral_deg = _angle_between_vectors_deg(face_normals[0], face_normals[1]) if len(face_normals) == 2 else None
        elif _is_smooth_continuity(continuity):
            flags |= STEP_EDGE_FLAGS["TANGENT"]
            visibility_class = STEP_EDGE_VISIBILITY_CLASSES["TANGENT"]
            dihedral_deg = _angle_between_vectors_deg(face_normals[0], face_normals[1]) if len(face_normals) == 2 else None
        else:
            dihedral_deg = _sampled_edge_dihedral_deg(edge, face_shapes, face_normals)
            if dihedral_deg is not None:
                if dihedral_deg > STEP_TOPOLOGY_EDGE_ANGULAR_TOLERANCE_DEG:
                    flags |= STEP_EDGE_FLAGS["HARD"]
                    continuity = "sampled_hard"
                else:
                    flags |= STEP_EDGE_FLAGS["TANGENT"]
                    visibility_class = STEP_EDGE_VISIBILITY_CLASSES["TANGENT"]
                    continuity = "sampled_tangent"
            else:
                flags |= STEP_EDGE_FLAGS["UNKNOWN_CONTINUITY"]
                visibility_class = STEP_EDGE_VISIBILITY_CLASSES["UNKNOWN"]
                continuity = "unknown"

    edge_data["flags"] = flags
    edge_data["adjacentFaceCount"] = adjacent_face_count
    edge_data["continuity"] = continuity
    edge_data["dihedralDeg"] = None if dihedral_deg is None else _round_value(dihedral_deg, 3)
    edge_data["visibilityClass"] = visibility_class


