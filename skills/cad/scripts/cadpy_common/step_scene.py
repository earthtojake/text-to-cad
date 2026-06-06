from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import os
import shutil
import tempfile
import time
from array import array
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from OCP.BinXCAFDrivers import BinXCAFDrivers
from OCP.Bnd import Bnd_Box
from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Curve2d, BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.BRepLProp import BRepLProp_SLProps
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.GCPnts import GCPnts_QuasiUniformDeflection
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.STEPControl import STEPControl_Reader
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.Quantity import Quantity_ColorRGBA
from OCP.TDF import TDF_ChildIterator, TDF_Label, TDF_LabelSequence
from OCP.TDocStd import TDocStd_Document
from OCP.TopAbs import (
    TopAbs_EDGE,
    TopAbs_FACE,
    TopAbs_REVERSED,
    TopAbs_SHELL,
    TopAbs_SOLID,
    TopAbs_VERTEX,
)
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopTools import TopTools_FormatVersion, TopTools_IndexedMapOfShape
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Shape
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import (
    XCAFDoc_ColorCurv,
    XCAFDoc_ColorGen,
    XCAFDoc_ColorSurf,
    XCAFDoc_ColorTool,
    XCAFDoc_DocumentTool,
    XCAFDoc_ShapeTool,
)

from cadpy_common.glb_mesh_payload import (
    DEFAULT_MATERIAL as DEFAULT_TOPOLOGY_MATERIAL,
    normalize_rgba as _normalize_rgba,
    occurrence_color_for_id as _occurrence_color_for_id,
    scene_glb_mesh_payload,
    transform_normal_from_occ as _transform_normal_from_occ,
)
from cadpy_common.glb_topology import (
    STEP_EDGE_DEFAULT_RENDER_VISIBILITY_CLASSES,
    STEP_EDGE_FLAGS,
    STEP_EDGE_VISIBILITY_CLASSES,
    STEP_TOPOLOGY_EDGE_ANGULAR_TOLERANCE_DEG,
    STEP_TOPOLOGY_EDGE_SAMPLE_COUNT,
    STEP_TOPOLOGY_SCHEMA_VERSION,
    is_displayable_step_edge_surface_class_code,
    normalize_step_edge_render_visibility_classes,
    step_edge_surface_class_code,
    step_topology_capabilities,
)
from cadpy_common.metadata import DEFAULT_MESH_ANGULAR_TOLERANCE, DEFAULT_MESH_TOLERANCE, MeshSettings
from cadpy_common.selector_types import SelectorBundle, SelectorProfile
from cadpy_common.step_hash import step_file_hash


REPO_ROOT = Path.cwd().resolve()
ColorRGBA = tuple[float, float, float, float]
STEP_SCENE_CACHE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class SelectorOptions:
    linear_deflection: float = DEFAULT_MESH_TOLERANCE
    angular_deflection: float = DEFAULT_MESH_ANGULAR_TOLERANCE
    relative: bool = True
    edge_deflection: float | None = None
    edge_deflection_ratio: float = 0.00075
    max_edge_points: int = 96
    digits: int | None = 6
    mesh_resolution: dict[str, Any] | None = None
    edge_visibility_classes: tuple[str, ...] = STEP_EDGE_DEFAULT_RENDER_VISIBILITY_CLASSES


@dataclass
class LoadedStepScene:
    step_path: Path
    roots: list["OccurrenceNode"]
    prototype_shapes: dict[int, Any]
    prototype_names: dict[int, str | None] = field(default_factory=dict)
    prototype_colors: dict[int, ColorRGBA] = field(default_factory=dict)
    prototype_face_colors: dict[int, dict[int, ColorRGBA]] = field(default_factory=dict)
    load_elapsed: float = 0.0
    step_hash: str | None = None
    source_kind: str = "step"
    source_path: str | None = None
    source_hash: str | None = None
    mesh_signature: tuple[float, float, bool] | None = None
    glb_mesh_payloads: dict[tuple[object, ...], Any] = field(default_factory=dict)
    export_shape: Any | None = None
    doc: Any | None = None


@dataclass(frozen=True)
class AdaptiveMeshResolution:
    settings: MeshSettings
    profile: str
    hints: dict[str, Any]


@dataclass
class OccurrenceNode:
    path: tuple[int, ...]
    name: str | None
    source_name: str | None
    transform: tuple[float, ...]
    prototype_key: int | None
    local_transform: tuple[float, ...] = field(default_factory=lambda: _identity_transform_matrix())
    color: ColorRGBA | None = None
    location: object | None = None
    children: list["OccurrenceNode"] = field(default_factory=list)
    row_index: int = -1


@lru_cache(maxsize=512)
def _enum_name_from_text(text: str, prefix: str) -> str:
    name = text.split(".")[-1]
    if name.startswith(prefix):
        return name[len(prefix) :].lower()
    return name.lower()


def _enum_name(value: Any, prefix: str) -> str:
    return _enum_name_from_text(str(value), prefix)


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


def _bbox_from_shape(shape: Any) -> dict[str, Any]:
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
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
    except Exception:
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
    except Exception:
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
        except Exception:
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


def _shape_hash(shape: Any) -> int:
    return hash(shape)


def _shape_location(topods_shape: object) -> object | None:
    location = getattr(topods_shape, "Location", None)
    if not callable(location):
        return None
    try:
        return location()
    except Exception:
        return None


def _compose_locations(parent_location: object | None, child_location: object | None) -> object | None:
    if parent_location is None:
        return child_location
    if child_location is None:
        return parent_location
    try:
        return parent_location.Multiplied(child_location)
    except Exception:
        return child_location


def _located_shape(topods_shape: object, location: object | None) -> object:
    if location is None:
        return topods_shape
    located = getattr(topods_shape, "Located", None)
    if not callable(located):
        return topods_shape
    try:
        return located(location)
    except Exception:
        return topods_shape


def _unlocated_shape(topods_shape: object) -> object:
    located = getattr(topods_shape, "Located", None)
    if not callable(located):
        return topods_shape
    try:
        return located(TopLoc_Location())
    except Exception:
        return topods_shape


def _identity_transform_matrix() -> tuple[float, ...]:
    return (
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
    )


def _location_transform_matrix(location: object | None) -> tuple[float, ...]:
    if location is None:
        return _identity_transform_matrix()
    transformation = getattr(location, "Transformation", None)
    if not callable(transformation):
        return _identity_transform_matrix()
    try:
        trsf = transformation()
    except Exception:
        return _identity_transform_matrix()
    rows: list[float] = []
    try:
        for row in range(1, 4):
            rows.extend(float(trsf.Value(row, column)) for column in range(1, 5))
    except Exception:
        return _identity_transform_matrix()
    rows.extend((0.0, 0.0, 0.0, 1.0))
    return tuple(rows)


@lru_cache(maxsize=8192)
def _location_from_transform_matrix(transform: tuple[float, ...]) -> TopLoc_Location:
    from OCP.gp import gp_Trsf

    if len(transform) != 16:
        return TopLoc_Location()
    trsf = gp_Trsf()
    trsf.SetValues(
        transform[0],
        transform[1],
        transform[2],
        transform[3],
        transform[4],
        transform[5],
        transform[6],
        transform[7],
        transform[8],
        transform[9],
        transform[10],
        transform[11],
    )
    return TopLoc_Location(trsf)


def _normalize_label_name(raw_name: object) -> str | None:
    if raw_name is None:
        return None
    text = " ".join(str(raw_name).split())
    if not text:
        return None
    lowered = text.lower()
    if lowered.startswith("open cascade step translator"):
        return None
    if lowered in {"assembly", "solid", "compound", "compsolid", "shell", "face", "wire", "edge", "vertex"}:
        return None
    if text.isdigit():
        return None
    return text


def _label_name(label: object) -> str | None:
    name = TDataStd_Name()
    if not label.FindAttribute(TDataStd_Name.GetID_s(), name):
        return None
    return _normalize_label_name(name.Get().ToExtString())


def _resolve_referred_label(shape_tool: Any, label: object) -> object:
    if not shape_tool.IsReference_s(label):
        return label
    referred = TDF_Label()
    if shape_tool.GetReferredShape_s(label, referred):
        return referred
    return label


def _color_tuple(color: Quantity_ColorRGBA) -> ColorRGBA:
    rgb = color.GetRGB()
    return (
        float(rgb.Red()),
        float(rgb.Green()),
        float(rgb.Blue()),
        float(color.Alpha()),
    )


def _color_from_label(color_tool: Any, label: object) -> ColorRGBA | None:
    color = Quantity_ColorRGBA()
    for color_type in (XCAFDoc_ColorSurf, XCAFDoc_ColorGen, XCAFDoc_ColorCurv):
        try:
            if XCAFDoc_ColorTool.GetColor_s(label, color_type, color):
                return _color_tuple(color)
        except Exception:
            continue
    return None


def _color_from_shape(color_tool: Any, shape: object) -> ColorRGBA | None:
    if getattr(shape, "IsNull", lambda: True)():
        return None
    color = Quantity_ColorRGBA()
    for color_type in (XCAFDoc_ColorSurf, XCAFDoc_ColorGen, XCAFDoc_ColorCurv):
        try:
            if color_tool.GetColor(shape, color_type, color):
                return _color_tuple(color)
        except Exception:
            pass
        try:
            if color_tool.GetInstanceColor(shape, color_type, color):
                return _color_tuple(color)
        except Exception:
            pass
    return None


def _face_color_map_from_label(shape_tool: Any, color_tool: Any, label: object) -> dict[int, ColorRGBA]:
    face_colors: dict[int, ColorRGBA] = {}

    def collect(colored_label: object) -> None:
        label_color = _color_from_label(color_tool, colored_label)
        if label_color is not None:
            try:
                shape = shape_tool.GetShape_s(colored_label)
            except Exception:
                shape = None
            if shape is not None and not shape.IsNull():
                explorer = TopExp_Explorer(shape, TopAbs_FACE)
                while explorer.More():
                    face_colors[_shape_hash(TopoDS.Face_s(explorer.Current()))] = label_color
                    explorer.Next()
        iterator = TDF_ChildIterator(colored_label, False)
        while iterator.More():
            collect(iterator.Value())
            iterator.Next()

    collect(label)
    return face_colors


def _xcaf_children(shape_tool: Any, label: object, resolved_label: object) -> list[object]:
    children = TDF_LabelSequence()
    has_children = XCAFDoc_ShapeTool.GetComponents_s(label, children, False)
    if (not has_children or children.Length() <= 0) and resolved_label != label:
        children = TDF_LabelSequence()
        has_children = XCAFDoc_ShapeTool.GetComponents_s(resolved_label, children, False)
    if not has_children or children.Length() <= 0:
        return []
    return [children.Value(index) for index in range(1, children.Length() + 1)]


def _load_occurrence_tree(
    step_path: Path,
) -> tuple[
    list[OccurrenceNode],
    dict[int, Any],
    dict[int, str | None],
    dict[int, ColorRGBA],
    dict[int, dict[int, ColorRGBA]],
    Any | None,
]:
    app = XCAFApp_Application.GetApplication_s()
    BinXCAFDrivers.DefineFormat_s(app)
    doc = TDocStd_Document(TCollection_ExtendedString("BinXCAF"))
    app.NewDocument(TCollection_ExtendedString("BinXCAF"), doc)

    reader = STEPCAFControl_Reader()
    reader.SetColorMode(True)
    reader.SetNameMode(True)
    for mode_name in ("SetMatMode", "SetLayerMode", "SetSHUOMode"):
        mode = getattr(reader, mode_name, None)
        if callable(mode):
            mode(True)
    read_status = reader.ReadFile(str(step_path))
    if int(read_status) != int(IFSelect_RetDone):
        return (*_load_fallback_occurrence_tree(step_path), None)
    if not reader.Transfer(doc):
        return (*_load_fallback_occurrence_tree(step_path), None)

    loaded = _load_occurrence_tree_from_xcaf_doc(step_path, doc)
    if loaded is None:
        return (*_load_fallback_occurrence_tree(step_path), None)
    return (*loaded, doc)


def _load_occurrence_tree_from_xcaf_doc(
    step_path: Path,
    doc: Any,
) -> tuple[
    list[OccurrenceNode],
    dict[int, Any],
    dict[int, str | None],
    dict[int, ColorRGBA],
    dict[int, dict[int, ColorRGBA]],
] | None:

    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    color_tool = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    free_labels = TDF_LabelSequence()
    shape_tool.GetFreeShapes(free_labels)
    if free_labels.Length() <= 0:
        return None

    prototypes: dict[int, Any] = {}
    prototype_names: dict[int, str | None] = {}
    prototype_colors: dict[int, ColorRGBA] = {}
    prototype_face_colors: dict[int, dict[int, ColorRGBA]] = {}

    def collect(label: object, *, path: tuple[int, ...], parent_location: object | None = None) -> OccurrenceNode | None:
        resolved_label = _resolve_referred_label(shape_tool, label)
        instance_shape = shape_tool.GetShape_s(label)
        resolved_shape = shape_tool.GetShape_s(resolved_label)
        base_shape = instance_shape if not instance_shape.IsNull() else resolved_shape
        local_location = _shape_location(base_shape)
        current_location = _compose_locations(parent_location, local_location)
        children = _xcaf_children(shape_tool, label, resolved_label)
        name = _label_name(label) or _label_name(resolved_label)
        source_name = _label_name(resolved_label) or name
        occurrence_color = (
            _color_from_label(color_tool, label)
            or _color_from_shape(color_tool, instance_shape)
            or _color_from_label(color_tool, resolved_label)
            or _color_from_shape(color_tool, resolved_shape)
        )
        prototype_key: int | None = None
        if not children and not resolved_shape.IsNull():
            prototype_shape = _unlocated_shape(resolved_shape)
            prototype_key = _shape_hash(prototype_shape)
            prototypes.setdefault(prototype_key, prototype_shape)
        elif not children and not base_shape.IsNull():
            prototype_shape = _unlocated_shape(base_shape)
            prototype_key = _shape_hash(prototype_shape)
            prototypes.setdefault(prototype_key, prototype_shape)
        if prototype_key is not None:
            prototype_names.setdefault(prototype_key, source_name or name)
            prototype_color = _color_from_label(color_tool, resolved_label) or _color_from_shape(color_tool, resolved_shape)
            if prototype_color is not None:
                prototype_colors.setdefault(prototype_key, prototype_color)
            face_colors = _face_color_map_from_label(shape_tool, color_tool, resolved_label)
            if label != resolved_label:
                face_colors.update(_face_color_map_from_label(shape_tool, color_tool, label))
            if face_colors:
                prototype_face_colors.setdefault(prototype_key, {}).update(face_colors)
        child_nodes = [
            child_node
            for index, child in enumerate(children, start=1)
            if (child_node := collect(child, path=(*path, index), parent_location=current_location)) is not None
        ]
        if prototype_key is None and not child_nodes:
            return None
        return OccurrenceNode(
            path=path,
            name=name,
            source_name=source_name,
            transform=_location_transform_matrix(current_location),
            prototype_key=prototype_key,
            local_transform=_location_transform_matrix(local_location),
            color=occurrence_color,
            location=current_location,
            children=child_nodes,
        )

    roots = [
        node
        for index in range(1, free_labels.Length() + 1)
        if (node := collect(free_labels.Value(index), path=(index,))) is not None
    ]
    if not roots:
        return None
    return roots, prototypes, prototype_names, prototype_colors, prototype_face_colors


def load_step_scene_from_xcaf_doc(
    step_path: Path,
    doc: Any,
    *,
    step_hash: str | None = None,
    source_kind: str = "step",
    source_hash: str | None = None,
    load_elapsed: float | None = None,
) -> LoadedStepScene:
    resolved_step_path = step_path.expanduser().resolve()
    load_started = time.perf_counter()
    loaded = _load_occurrence_tree_from_xcaf_doc(resolved_step_path, doc)
    if loaded is None:
        raise RuntimeError(f"XCAF document contains no STEP geometry: {resolved_step_path}")
    (
        roots,
        prototype_shapes,
        prototype_names,
        prototype_colors,
        prototype_face_colors,
    ) = loaded
    return LoadedStepScene(
        step_path=resolved_step_path,
        roots=roots,
        prototype_shapes=prototype_shapes,
        prototype_names=prototype_names,
        prototype_colors=prototype_colors,
        prototype_face_colors=prototype_face_colors,
        load_elapsed=time.perf_counter() - load_started if load_elapsed is None else load_elapsed,
        step_hash=step_hash,
        source_kind=source_kind,
        source_hash=source_hash,
        doc=doc,
    )


def _load_fallback_occurrence_tree(
    step_path: Path,
) -> tuple[list[OccurrenceNode], dict[int, Any], dict[int, str | None], dict[int, ColorRGBA], dict[int, dict[int, ColorRGBA]]]:
    reader = STEPControl_Reader()
    status = reader.ReadFile(str(step_path))
    if status != IFSelect_RetDone:
        raise RuntimeError(f"failed to read STEP file: {step_path}")
    reader.TransferRoots()
    shape = reader.OneShape()
    if shape.IsNull():
        raise RuntimeError(f"STEP file produced no shape: {step_path}")
    prototype_key = _shape_hash(shape)
    return (
        [
            OccurrenceNode(
                path=(1,),
                name=step_path.stem,
                source_name=step_path.stem,
                transform=_identity_transform_matrix(),
                prototype_key=prototype_key,
                local_transform=_identity_transform_matrix(),
                location=None,
            )
        ],
        {prototype_key: shape},
        {prototype_key: step_path.stem},
        {},
        {},
    )


def load_step_scene(step_path: Path) -> LoadedStepScene:
    resolved_step_path = step_path.expanduser().resolve()
    if not resolved_step_path.exists():
        raise FileNotFoundError(f"STEP file does not exist: {resolved_step_path}")
    load_started = time.perf_counter()
    (
        roots,
        prototype_shapes,
        prototype_names,
        prototype_colors,
        prototype_face_colors,
        doc,
    ) = _load_occurrence_tree(resolved_step_path)
    return LoadedStepScene(
        step_path=resolved_step_path,
        roots=roots,
        prototype_shapes=prototype_shapes,
        prototype_names=prototype_names,
        prototype_colors=prototype_colors,
        prototype_face_colors=prototype_face_colors,
        load_elapsed=time.perf_counter() - load_started,
        doc=doc,
    )


def _step_scene_cache_root() -> Path | None:
    enabled = os.environ.get("TEXT_TO_CAD_STEP_SCENE_CACHE", "1").strip().lower()
    if enabled in {"0", "false", "no", "off"}:
        return None
    configured = os.environ.get("TEXT_TO_CAD_STEP_SCENE_CACHE_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    init_cwd = str(os.environ.get("INIT_CWD") or "").strip()
    cache_root = Path(init_cwd).expanduser().resolve() if init_cwd else REPO_ROOT
    if _path_is_skill_runtime(cache_root):
        return Path(tempfile.gettempdir()).resolve() / "cadpy-step-scene-cache"
    return cache_root / "tmp" / "step-scene-cache"


def _path_is_skill_runtime(path: Path) -> bool:
    resolved = path.expanduser().resolve()
    return any((candidate / "SKILL.md").is_file() for candidate in (resolved, *resolved.parents))


def _step_scene_cache_dir(root: Path, step_hash: str) -> Path:
    return root / f"v{STEP_SCENE_CACHE_SCHEMA_VERSION}" / step_hash[:2] / step_hash


def _rgba_to_cache_value(color: ColorRGBA | None) -> list[float] | None:
    return None if color is None else [float(component) for component in color]


def _rgba_from_cache_value(value: object) -> ColorRGBA | None:
    if not isinstance(value, list) or len(value) < 3:
        return None
    rgba = [float(component) for component in value[:4]]
    if len(rgba) == 3:
        rgba.append(1.0)
    return (rgba[0], rgba[1], rgba[2], rgba[3])


def _node_to_cache_payload(node: OccurrenceNode) -> dict[str, Any]:
    return {
        "path": [int(value) for value in node.path],
        "name": node.name,
        "sourceName": node.source_name,
        "transform": [float(value) for value in node.transform],
        "localTransform": [float(value) for value in node.local_transform],
        "prototypeKey": node.prototype_key,
        "color": _rgba_to_cache_value(node.color),
        "children": [_node_to_cache_payload(child) for child in node.children],
    }


def _node_from_cache_payload(payload: object) -> OccurrenceNode:
    if not isinstance(payload, dict):
        raise ValueError("cached occurrence node must be an object")
    transform = tuple(float(value) for value in payload.get("transform", _identity_transform_matrix()))
    local_transform = tuple(float(value) for value in payload.get("localTransform", _identity_transform_matrix()))
    if len(transform) != 16 or len(local_transform) != 16:
        raise ValueError("cached occurrence node has an invalid transform")
    prototype_key = payload.get("prototypeKey")
    return OccurrenceNode(
        path=tuple(int(value) for value in payload.get("path", ())),
        name=payload.get("name") if payload.get("name") is None else str(payload.get("name")),
        source_name=payload.get("sourceName") if payload.get("sourceName") is None else str(payload.get("sourceName")),
        transform=transform,
        local_transform=local_transform,
        prototype_key=None if prototype_key is None else int(prototype_key),
        color=_rgba_from_cache_value(payload.get("color")),
        location=_location_from_transform_matrix(transform),
        children=[_node_from_cache_payload(child) for child in payload.get("children", [])],
    )


def _face_index_color_payload(shape: object, face_colors: dict[int, ColorRGBA]) -> list[list[object]]:
    if not face_colors:
        return []
    payload: list[list[object]] = []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    face_index = 0
    while explorer.More():
        face_hash = _shape_hash(TopoDS.Face_s(explorer.Current()))
        color = face_colors.get(face_hash)
        if color is not None:
            payload.append([face_index, _rgba_to_cache_value(color)])
        face_index += 1
        explorer.Next()
    return payload


def _face_colors_from_index_payload(shape: object, payload: object) -> dict[int, ColorRGBA]:
    if not isinstance(payload, list) or not payload:
        return {}
    colors_by_index: dict[int, ColorRGBA] = {}
    for raw_item in payload:
        if not isinstance(raw_item, list) or len(raw_item) != 2:
            continue
        color = _rgba_from_cache_value(raw_item[1])
        if color is None:
            continue
        colors_by_index[int(raw_item[0])] = color
    face_colors: dict[int, ColorRGBA] = {}
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    face_index = 0
    while explorer.More():
        color = colors_by_index.get(face_index)
        if color is not None:
            face_colors[_shape_hash(TopoDS.Face_s(explorer.Current()))] = color
        face_index += 1
        explorer.Next()
    return face_colors


def _read_step_scene_cache(step_path: Path, *, step_hash: str, root: Path) -> LoadedStepScene | None:
    from OCP.BRepTools import BRepTools

    started = time.perf_counter()
    cache_dir = _step_scene_cache_dir(root, step_hash)
    meta_path = cache_dir / "scene.json"
    if not meta_path.is_file():
        return None
    try:
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        if metadata.get("schemaVersion") != STEP_SCENE_CACHE_SCHEMA_VERSION:
            return None
        if metadata.get("stepHash") != step_hash:
            return None
        prototypes = metadata.get("prototypes")
        if not isinstance(prototypes, list):
            return None
        prototype_shapes: dict[int, Any] = {}
        prototype_names: dict[int, str | None] = {}
        prototype_colors: dict[int, ColorRGBA] = {}
        prototype_face_colors: dict[int, dict[int, ColorRGBA]] = {}
        for index, prototype in enumerate(prototypes):
            if not isinstance(prototype, dict):
                return None
            prototype_key = int(prototype["key"])
            brep_file = str(prototype.get("file") or f"prototype-{index}.brep")
            if "/" in brep_file or "\\" in brep_file:
                return None
            brep_path = cache_dir / brep_file
            if not brep_path.is_file():
                return None
            shape = TopoDS_Shape()
            if not BRepTools.Read_s(shape, os.fspath(brep_path), BRep_Builder()) or shape.IsNull():
                return None
            prototype_shapes[prototype_key] = shape
            name = prototype.get("name")
            prototype_names[prototype_key] = None if name is None else str(name)
            color = _rgba_from_cache_value(prototype.get("color"))
            if color is not None:
                prototype_colors[prototype_key] = color
            face_colors = _face_colors_from_index_payload(shape, prototype.get("faceIndexColors"))
            if face_colors:
                prototype_face_colors[prototype_key] = face_colors
        roots = [_node_from_cache_payload(node) for node in metadata.get("roots", [])]
        if not roots or not prototype_shapes:
            return None
        return LoadedStepScene(
            step_path=step_path,
            roots=roots,
            prototype_shapes=prototype_shapes,
            prototype_names=prototype_names,
            prototype_colors=prototype_colors,
            prototype_face_colors=prototype_face_colors,
            load_elapsed=time.perf_counter() - started,
            step_hash=step_hash,
        )
    except Exception:
        return None


def _write_step_scene_cache(scene: LoadedStepScene, *, step_hash: str, root: Path) -> None:
    from OCP.BRepTools import BRepTools

    cache_dir = _step_scene_cache_dir(root, step_hash)
    if (cache_dir / "scene.json").is_file():
        return
    temp_dir = cache_dir.parent / f".{cache_dir.name}.{os.getpid()}.tmp"
    try:
        cache_dir.parent.mkdir(parents=True, exist_ok=True)
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        temp_dir.mkdir(parents=True, exist_ok=False)
        prototypes: list[dict[str, Any]] = []
        for index, (prototype_key, shape) in enumerate(scene.prototype_shapes.items()):
            brep_file = f"prototype-{index}.brep"
            if not BRepTools.Write_s(
                shape,
                os.fspath(temp_dir / brep_file),
                False,
                False,
                TopTools_FormatVersion.TopTools_FormatVersion_VERSION_1,
            ):
                raise RuntimeError("failed to write cached BREP prototype")
            prototypes.append(
                {
                    "key": int(prototype_key),
                    "file": brep_file,
                    "name": scene.prototype_names.get(prototype_key),
                    "color": _rgba_to_cache_value(scene.prototype_colors.get(prototype_key)),
                    "faceIndexColors": _face_index_color_payload(
                        shape,
                        scene.prototype_face_colors.get(prototype_key, {}),
                    ),
                }
            )
        metadata = {
            "schemaVersion": STEP_SCENE_CACHE_SCHEMA_VERSION,
            "stepHash": step_hash,
            "sourcePath": os.fspath(scene.step_path),
            "roots": [_node_to_cache_payload(root_node) for root_node in scene.roots],
            "prototypes": prototypes,
        }
        (temp_dir / "scene.json").write_text(
            json.dumps(metadata, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        try:
            temp_dir.rename(cache_dir)
        except FileExistsError:
            shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)


def load_step_scene_cached(step_path: Path) -> LoadedStepScene:
    resolved_step_path = step_path.expanduser().resolve()
    if not resolved_step_path.exists():
        raise FileNotFoundError(f"STEP file does not exist: {resolved_step_path}")
    step_hash = _step_hash(resolved_step_path)
    cache_root = _step_scene_cache_root()
    if cache_root is not None:
        cached = _read_step_scene_cache(resolved_step_path, step_hash=step_hash, root=cache_root)
        if cached is not None:
            return cached
    scene = load_step_scene(resolved_step_path)
    scene.step_hash = step_hash
    if cache_root is not None:
        _write_step_scene_cache(scene, step_hash=step_hash, root=cache_root)
    return scene


def _scene_step_hash(scene: LoadedStepScene) -> str:
    if scene.step_hash is None:
        scene.step_hash = _step_hash(scene.step_path)
    return scene.step_hash


def mesh_step_scene(
    scene: LoadedStepScene,
    *,
    linear_deflection: float,
    angular_deflection: float,
    relative: bool,
) -> None:
    signature = (float(linear_deflection), float(angular_deflection), bool(relative))
    if scene.mesh_signature == signature:
        return
    for shape in scene.prototype_shapes.values():
        BRepMesh_IncrementalMesh(
            shape,
            signature[0],
            signature[2],
            signature[1],
            True,
        )
    scene.mesh_signature = signature


def _iter_leaf_occurrences(nodes: list[OccurrenceNode]) -> list[OccurrenceNode]:
    leaves: list[OccurrenceNode] = []
    stack = list(reversed(nodes))
    while stack:
        node = stack.pop()
        if node.prototype_key is not None:
            leaves.append(node)
        if node.children:
            stack.extend(reversed(node.children))
    return leaves


def occurrence_selector_id(node: OccurrenceNode) -> str:
    return _selector_id(node.path)


def scene_leaf_occurrences(scene: LoadedStepScene) -> list[OccurrenceNode]:
    return _iter_leaf_occurrences(scene.roots)


def scene_occurrence_shape(scene: LoadedStepScene, node: OccurrenceNode) -> Any:
    if node.prototype_key is None or node.prototype_key not in scene.prototype_shapes:
        raise RuntimeError(f"Occurrence {occurrence_selector_id(node)} has no prototype shape")
    return _located_shape(scene.prototype_shapes[node.prototype_key], node.location)


def scene_occurrence_prototype_shape(scene: LoadedStepScene, node: OccurrenceNode) -> Any:
    if node.prototype_key is None or node.prototype_key not in scene.prototype_shapes:
        raise RuntimeError(f"Occurrence {occurrence_selector_id(node)} has no prototype shape")
    return scene.prototype_shapes[node.prototype_key]


def scene_export_shape(scene: LoadedStepScene) -> Any:
    if scene.export_shape is not None:
        return scene.export_shape
    leaf_shapes = [
        scene_occurrence_shape(scene, node)
        for node in _iter_leaf_occurrences(scene.roots)
        if node.prototype_key is not None and node.prototype_key in scene.prototype_shapes
    ]
    if not leaf_shapes:
        raise RuntimeError(f"No CAD geometry available for STL export: {scene.step_path}")
    if len(leaf_shapes) == 1:
        scene.export_shape = leaf_shapes[0]
        return scene.export_shape
    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for shape in leaf_shapes:
        builder.Add(compound, shape)
    scene.export_shape = compound
    return scene.export_shape


def _scene_mesh_resolution_hints(scene: LoadedStepScene) -> dict[str, Any]:
    prototype_face_counts: dict[int, int] = {}
    prototype_edge_counts: dict[int, int] = {}
    prototype_curved_face_counts: dict[int, int] = {}
    prototype_curved_edge_counts: dict[int, int] = {}
    for key, shape in scene.prototype_shapes.items():
        face_map = TopTools_IndexedMapOfShape()
        edge_map = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(shape, TopAbs_FACE, face_map)
        TopExp.MapShapes_s(shape, TopAbs_EDGE, edge_map)
        prototype_face_counts[key] = int(face_map.Extent())
        prototype_edge_counts[key] = int(edge_map.Extent())
        curved_faces = 0
        for face_index in range(1, face_map.Extent() + 1):
            try:
                surface = BRepAdaptor_Surface(TopoDS.Face_s(face_map.FindKey(face_index)))
                if _enum_name(surface.GetType(), "GeomAbs_") != "plane":
                    curved_faces += 1
            except Exception:
                curved_faces += 1
        curved_edges = 0
        for edge_index in range(1, edge_map.Extent() + 1):
            try:
                curve = BRepAdaptor_Curve(TopoDS.Edge_s(edge_map.FindKey(edge_index)))
                if _enum_name(curve.GetType(), "GeomAbs_") != "line":
                    curved_edges += 1
            except Exception:
                curved_edges += 1
        prototype_curved_face_counts[key] = curved_faces
        prototype_curved_edge_counts[key] = curved_edges

    leaves = scene_leaf_occurrences(scene)
    occurrence_face_count = sum(
        prototype_face_counts.get(int(node.prototype_key), 0)
        for node in leaves
        if node.prototype_key is not None
    )
    occurrence_edge_count = sum(
        prototype_edge_counts.get(int(node.prototype_key), 0)
        for node in leaves
        if node.prototype_key is not None
    )
    occurrence_curved_face_count = sum(
        prototype_curved_face_counts.get(int(node.prototype_key), 0)
        for node in leaves
        if node.prototype_key is not None
    )
    occurrence_curved_edge_count = sum(
        prototype_curved_edge_counts.get(int(node.prototype_key), 0)
        for node in leaves
        if node.prototype_key is not None
    )
    prototype_face_count = sum(prototype_face_counts.values())
    prototype_edge_count = sum(prototype_edge_counts.values())
    prototype_curved_face_count = sum(prototype_curved_face_counts.values())
    prototype_curved_edge_count = sum(prototype_curved_edge_counts.values())
    complexity_score = (
        float(occurrence_face_count)
        + (float(occurrence_edge_count) * 0.35)
        + (float(prototype_face_count) * 0.5)
        + (float(len(leaves)) * 24.0)
    )
    curvature_pressure_score = (
        (float(occurrence_curved_face_count) * 1.6)
        + (float(occurrence_curved_edge_count) * 0.9)
        + (float(prototype_curved_face_count) * 0.8)
        + (float(prototype_curved_edge_count) * 0.4)
    )
    high_complexity = occurrence_face_count >= 8000 or occurrence_edge_count >= 22000
    diagonal: float | None = None
    scale_factor = 1.0
    if not high_complexity:
        prototype_boxes = {
            key: _bbox_from_shape(shape)
            for key, shape in scene.prototype_shapes.items()
        }
        occurrence_boxes = [
            _transform_bbox(prototype_boxes[int(node.prototype_key)], node.transform)
            for node in leaves
            if node.prototype_key is not None and int(node.prototype_key) in prototype_boxes
        ]
        bbox = _merge_bbox(occurrence_boxes) if occurrence_boxes else _bbox_from_points([])
        diagonal = float(bbox.get("diag") or 0.0)
        if diagonal <= 50.0:
            scale_factor = 0.65
        elif diagonal <= 150.0:
            scale_factor = 0.8
        elif diagonal <= 500.0:
            scale_factor = 1.0
        elif diagonal <= 1500.0:
            scale_factor = 1.18
        else:
            scale_factor = 1.35
    return {
        "bboxDiag": None if diagonal is None else round(diagonal, 3),
        "prototypeFaceCount": prototype_face_count,
        "prototypeEdgeCount": prototype_edge_count,
        "prototypeCurvedFaceCount": prototype_curved_face_count,
        "prototypeCurvedEdgeCount": prototype_curved_edge_count,
        "occurrenceFaceCount": occurrence_face_count,
        "occurrenceEdgeCount": occurrence_edge_count,
        "occurrenceCurvedFaceCount": occurrence_curved_face_count,
        "occurrenceCurvedEdgeCount": occurrence_curved_edge_count,
        "leafOccurrenceCount": len(leaves),
        "complexityScore": round(complexity_score, 3),
        "effectiveComplexityScore": round(complexity_score * scale_factor, 3),
        "curvaturePressureScore": round(curvature_pressure_score * scale_factor, 3),
    }


def adaptive_mesh_resolution_from_hints(hints: dict[str, Any]) -> AdaptiveMeshResolution:
    effective_score = float(hints["effectiveComplexityScore"])
    curvature_pressure = float(hints["curvaturePressureScore"])
    leaf_count = int(hints["leafOccurrenceCount"])
    face_count = int(hints["occurrenceFaceCount"])
    edge_count = int(hints["occurrenceEdgeCount"])

    if face_count >= 20000 or edge_count >= 55000 or effective_score >= 45000 or curvature_pressure >= 45000:
        profile = "large-topology"
        settings = MeshSettings(tolerance=0.025, angular_tolerance=0.75)
    elif (
        face_count >= 8000
        or edge_count >= 22000
        or effective_score >= 28000
        or curvature_pressure >= 18000
        or (leaf_count >= 80 and effective_score >= 22000)
    ):
        profile = "coarse-assembly"
        settings = MeshSettings(tolerance=0.02, angular_tolerance=0.6)
    elif (
        face_count >= 2500
        or edge_count >= 8000
        or effective_score >= 6000
        or curvature_pressure >= 9000
        or (leaf_count >= 80 and effective_score >= 6000)
        or (leaf_count >= 24 and effective_score >= 3500)
    ):
        profile = "balanced-assembly"
        settings = MeshSettings(tolerance=0.016, angular_tolerance=0.5)
    elif face_count >= 800 or edge_count >= 2500 or effective_score >= 1800 or curvature_pressure >= 3500:
        profile = "medium"
        settings = MeshSettings(tolerance=0.014, angular_tolerance=0.45)
    elif face_count >= 180 or edge_count >= 600 or effective_score >= 450 or curvature_pressure >= 900:
        profile = "fine"
        settings = MeshSettings(tolerance=0.008, angular_tolerance=0.3)
    else:
        profile = "extra-fine"
        settings = MeshSettings(tolerance=0.006, angular_tolerance=0.2)

    hints = dict(hints)
    hints["profile"] = profile
    return AdaptiveMeshResolution(settings=settings, profile=profile, hints=hints)


def adaptive_mesh_resolution_for_scene(scene: LoadedStepScene) -> AdaptiveMeshResolution:
    return adaptive_mesh_resolution_from_hints(_scene_mesh_resolution_hints(scene))


def _face_ordinals_from_shape(shape: Any, face_ord_by_hash: dict[int, int]) -> list[int]:
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    ordinals: list[int] = []
    seen: set[int] = set()
    while explorer.More():
        ordinal = face_ord_by_hash.get(_shape_hash(explorer.Current()))
        if ordinal is not None and ordinal not in seen:
            ordinals.append(ordinal)
            seen.add(ordinal)
        explorer.Next()
    return ordinals


def _edge_ordinals_from_shape(shape: Any, edge_ord_by_hash: dict[int, int]) -> list[int]:
    explorer = TopExp_Explorer(shape, TopAbs_EDGE)
    ordinals: list[int] = []
    seen: set[int] = set()
    while explorer.More():
        ordinal = edge_ord_by_hash.get(_shape_hash(explorer.Current()))
        if ordinal is not None and ordinal not in seen:
            ordinals.append(ordinal)
            seen.add(ordinal)
        explorer.Next()
    return ordinals


def _prototype_shape_entries(root_shape: Any) -> tuple[str, list[dict[str, Any]], dict[int, int], dict[int, int]]:
    solid_map = TopTools_IndexedMapOfShape()
    shell_map = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(root_shape, TopAbs_SOLID, solid_map)
    TopExp.MapShapes_s(root_shape, TopAbs_SHELL, shell_map)

    entries: list[dict[str, Any]] = []
    face_to_shape: dict[int, int] = {}
    edge_to_shape: dict[int, int] = {}

    if solid_map.Extent() > 0:
        kind = "solid"
        map_source = solid_map
    elif shell_map.Extent() > 0:
        kind = "shell"
        map_source = shell_map
    else:
        kind = "compound"
        map_source = None

    if map_source is None:
        entries.append({"ordinal": 1, "shape": root_shape, "kind": kind})
        return kind, entries, face_to_shape, edge_to_shape

    for ordinal in range(1, map_source.Extent() + 1):
        entries.append({"ordinal": ordinal, "shape": map_source.FindKey(ordinal), "kind": kind})
    return kind, entries, face_to_shape, edge_to_shape


def _extract_summary_prototype(root_shape: Any, options: SelectorOptions) -> dict[str, Any]:
    face_map = TopTools_IndexedMapOfShape()
    edge_map = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(root_shape, TopAbs_FACE, face_map)
    TopExp.MapShapes_s(root_shape, TopAbs_EDGE, edge_map)
    kind, shape_entries, _face_to_shape, _edge_to_shape = _prototype_shape_entries(root_shape)
    return {
        "kind": kind,
        "bbox": _bbox_from_shape(root_shape),
        "shapeCount": len(shape_entries) if shape_entries else 0,
        "faceCount": face_map.Extent(),
        "edgeCount": edge_map.Extent(),
    }


def _extract_refs_prototype(
    root_shape: Any,
    options: SelectorOptions,
    *,
    include_buffers: bool,
    already_meshed: bool,
) -> dict[str, Any]:
    if not already_meshed:
        BRepMesh_IncrementalMesh(
            root_shape,
            options.linear_deflection,
            options.relative,
            options.angular_deflection,
            True,
        )

    face_map = TopTools_IndexedMapOfShape()
    edge_map = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(root_shape, TopAbs_FACE, face_map)
    TopExp.MapShapes_s(root_shape, TopAbs_EDGE, edge_map)
    face_ord_by_hash = {_shape_hash(face_map.FindKey(index)): index for index in range(1, face_map.Extent() + 1)}
    edge_ord_by_hash = {_shape_hash(edge_map.FindKey(index)): index for index in range(1, edge_map.Extent() + 1)}

    kind, shape_entries, _face_to_shape, _edge_to_shape = _prototype_shape_entries(root_shape)
    if not shape_entries and (face_map.Extent() > 0 or edge_map.Extent() > 0):
        shape_entries = [{"ordinal": 1, "shape": root_shape, "kind": "compound"}]

    shape_local_by_face: dict[int, int] = {}
    shape_local_by_edge: dict[int, int] = {}
    for shape_entry in shape_entries:
        face_ordinals = _face_ordinals_from_shape(shape_entry["shape"], face_ord_by_hash)
        edge_ordinals = _edge_ordinals_from_shape(shape_entry["shape"], edge_ord_by_hash)
        shape_entry["faceOrdinals"] = face_ordinals
        shape_entry["edgeOrdinals"] = edge_ordinals
        for ordinal in face_ordinals:
            shape_local_by_face.setdefault(ordinal, shape_entry["ordinal"])
        for ordinal in edge_ordinals:
            shape_local_by_edge.setdefault(ordinal, shape_entry["ordinal"])

    face_edge_ordinals: dict[int, list[int]] = {}
    edge_face_ordinals: dict[int, list[int]] = {}
    edge_face_use_counts: dict[int, dict[int, int]] = {}
    face_edge_polygon_nodes: dict[int, dict[int, list[int]]] = {}

    face_boxes: dict[int, dict[str, Any]] = {}
    face_meshes: dict[int, dict[str, Any]] = {}
    total_face_area = 0.0
    faces: list[dict[str, Any]] = []
    for face_ordinal in range(1, face_map.Extent() + 1):
        face = TopoDS.Face_s(face_map.FindKey(face_ordinal))
        surface = BRepAdaptor_Surface(face)
        geometry = _extract_face_geometry(face)
        raw_edge_ordinals: list[int] = []
        edge_polygons: dict[int, list[int]] = {}
        edge_side_ordinals: dict[str, int] = {}
        edge_explorer = TopExp_Explorer(face, TopAbs_EDGE)
        while edge_explorer.More():
            edge = TopoDS.Edge_s(edge_explorer.Current())
            edge_ordinal = edge_ord_by_hash.get(_shape_hash(edge))
            if edge_ordinal is not None:
                raw_edge_ordinals.append(edge_ordinal)
                use_counts = edge_face_use_counts.setdefault(edge_ordinal, {})
                use_counts[face_ordinal] = use_counts.get(face_ordinal, 0) + 1
                polygon_nodes = _edge_polygon_node_indices_from_face_mesh(edge, geometry)
                if polygon_nodes:
                    edge_polygons.setdefault(edge_ordinal, polygon_nodes)
                    for left, right in zip(polygon_nodes, polygon_nodes[1:]):
                        edge_side_ordinals[_triangle_side_key(left, right)] = edge_ordinal
            edge_explorer.Next()
        edge_ordinals = list(dict.fromkeys(raw_edge_ordinals))
        face_edge_ordinals[face_ordinal] = edge_ordinals
        for edge_ordinal in edge_ordinals:
            edge_face_ordinals.setdefault(edge_ordinal, []).append(face_ordinal)
        face_edge_polygon_nodes[face_ordinal] = edge_polygons
        face_boxes[face_ordinal] = geometry["bbox"]
        face_meshes[face_ordinal] = geometry
        total_face_area += geometry["area"]
        face_data = {
            "ordinal": face_ordinal,
            "shapeOrdinal": shape_local_by_face.get(face_ordinal, 1),
            "shapeHash": _shape_hash(face),
            "surfaceType": _enum_name(surface.GetType(), "GeomAbs_"),
            "area": geometry["area"],
            "center": geometry["center"],
            "normal": geometry["normal"],
            "bbox": geometry["bbox"],
            "edgeOrdinals": tuple(face_edge_ordinals.get(face_ordinal, [])),
            "edgeSideOrdinals": edge_side_ordinals,
            "triangleNodes": geometry["nodes"],
            "triangleNormals": geometry["normals"],
            "triangles": geometry["triangles"],
        }
        if not (geometry["triangleCount"] > 0 and geometry["area"] > 1e-12):
            face_data["referenceable"] = False
        params = _surface_params(surface, options.digits)
        if params:
            face_data["params"] = params
        faces.append(face_data)

    global_box = _merge_bbox(list(face_boxes.values())) if face_boxes else _bbox_from_shape(root_shape)
    diag = max(global_box["diag"], 1e-9)
    edge_deflection = options.edge_deflection if options.edge_deflection is not None else diag * options.edge_deflection_ratio
    edge_deflection = max(edge_deflection, 1e-7)

    total_edge_length = 0.0
    edge_boxes: dict[int, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    for edge_ordinal in range(1, edge_map.Extent() + 1):
        edge = TopoDS.Edge_s(edge_map.FindKey(edge_ordinal))
        curve = BRepAdaptor_Curve(edge)
        points: list[list[float]] = []
        for face_ordinal in edge_face_ordinals.get(edge_ordinal, []):
            polygon_nodes = face_edge_polygon_nodes.get(face_ordinal, {}).get(edge_ordinal, [])
            points = _edge_points_from_face_polygon(face_meshes[face_ordinal], polygon_nodes, options.max_edge_points)
            if points:
                break
        if not points:
            points = _extract_edge_points_from_curve(edge, edge_deflection, options.max_edge_points)
        closed = bool(BRep_Tool.IsClosed_s(edge))
        length = _polyline_length(points, closed)
        total_edge_length += length
        bbox = _bbox_from_points(points)
        edge_boxes[edge_ordinal] = bbox
        seam = any(BRep_Tool.IsClosed_s(edge, TopoDS.Face_s(face_map.FindKey(face_ordinal))) for face_ordinal in edge_face_ordinals.get(edge_ordinal, []))
        degenerated = bool(BRep_Tool.Degenerated_s(edge))
        edge_data = {
            "ordinal": edge_ordinal,
            "shapeOrdinal": shape_local_by_edge.get(edge_ordinal, 1),
            "curveType": _enum_name(curve.GetType(), "GeomAbs_"),
            "length": length,
            "center": _polyline_center(points),
            "bbox": bbox,
            "faceOrdinals": tuple(edge_face_ordinals.get(edge_ordinal, [])),
            "points": points,
        }
        if closed:
            edge_data["closed"] = True
        if degenerated:
            edge_data["degenerated"] = True
        if seam:
            edge_data["seam"] = True
        if degenerated or len(points) < 2:
            edge_data["referenceable"] = False
        params = _curve_params(curve, options.digits)
        if params:
            edge_data["params"] = params
        face_shapes = [
            TopoDS.Face_s(face_map.FindKey(face_ordinal))
            for face_ordinal in edge_face_ordinals.get(edge_ordinal, [])
            if 1 <= face_ordinal <= face_map.Extent()
        ]
        face_normals = [
            face_meshes.get(face_ordinal, {}).get("normal")
            for face_ordinal in edge_face_ordinals.get(edge_ordinal, [])
        ]
        _classify_edge(
            edge_data,
            edge=edge,
            face_shapes=face_shapes,
            face_normals=face_normals,
            face_use_counts=edge_face_use_counts.get(edge_ordinal, {}),
        )
        edge_data["surfaceClassCode"] = step_edge_surface_class_code(
            edge_data,
            enabled_visibility_classes=options.edge_visibility_classes,
        )
        edges.append(edge_data)

    total_area = max(total_face_area, 1e-12)
    total_length = max(total_edge_length, 1e-12)
    size_floor = max(diag * diag * 1e-6, 1e-12)
    length_floor = max(diag * 1e-5, 1e-12)

    for face_data in faces:
        area = float(face_data["area"])
        score = 100.0 * math.sqrt(max(area, 0.0) / total_area)
        if face_data["surfaceType"] in {"plane", "cylinder", "cone", "sphere", "torus"}:
            score += 8.0
        if area < size_floor:
            score -= 45.0
        if not face_data.get("referenceable", True):
            score = 0.0
        face_data["relevance"] = max(0, min(100, int(round(score))))
        face_data["flags"] = _face_flags(face_data)

    for edge_data in edges:
        length = float(edge_data["length"])
        score = 100.0 * math.sqrt(max(length, 0.0) / total_length)
        if edge_data["curveType"] in {"line", "circle", "ellipse"}:
            score += 10.0
        if edge_data.get("seam", False):
            score -= 30.0
        if edge_data.get("degenerated", False):
            score -= 80.0
        if length < length_floor:
            score -= 35.0
        if not edge_data.get("referenceable", True):
            score = 0.0
        edge_data["relevance"] = max(0, min(100, int(round(score))))

    for shape_entry in shape_entries:
        shape = shape_entry["shape"]
        face_ordinals = shape_entry.get("faceOrdinals", [])
        boxes = [face_boxes[ordinal] for ordinal in face_ordinals if ordinal in face_boxes]
        bbox = _merge_bbox(boxes) if boxes else _bbox_from_shape(shape)
        shape_entry["bbox"] = bbox
        shape_entry["area"] = sum(faces[ordinal - 1]["area"] for ordinal in face_ordinals)
        if shape_entry["kind"] == "solid":
            props = GProp_GProps()
            BRepGProp.VolumeProperties_s(shape, props, False, False, True)
            shape_entry["volume"] = props.Mass()
            shape_entry["center"] = _point_from_occ(props.CentreOfMass())
        else:
            shape_entry["center"] = bbox["center"]

    return {
        "kind": kind,
        "bbox": global_box,
        "shapeCount": len(shape_entries),
        "faceCount": len(faces),
        "edgeCount": len(edges),
        "shapes": shape_entries,
        "faces": faces,
        "edges": edges,
        "includeBuffers": include_buffers,
    }


def _selector_id(path: tuple[int, ...]) -> str:
    return "o" + ".".join(str(segment) for segment in path)


def _relative_step_path(step_path: Path) -> str:
    resolved = step_path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _step_hash(step_path: Path) -> str:
    return step_file_hash(step_path)


def _normalize_selector_options(options: SelectorOptions | None) -> SelectorOptions:
    normalized_options = options or SelectorOptions()
    if normalized_options.digits is not None and normalized_options.digits < 0:
        return SelectorOptions(
            linear_deflection=normalized_options.linear_deflection,
            angular_deflection=normalized_options.angular_deflection,
            relative=normalized_options.relative,
            edge_deflection=normalized_options.edge_deflection,
            edge_deflection_ratio=normalized_options.edge_deflection_ratio,
            max_edge_points=normalized_options.max_edge_points,
            digits=None,
            mesh_resolution=normalized_options.mesh_resolution,
            edge_visibility_classes=normalize_step_edge_render_visibility_classes(
                normalized_options.edge_visibility_classes
            ),
        )
    return SelectorOptions(
        linear_deflection=normalized_options.linear_deflection,
        angular_deflection=normalized_options.angular_deflection,
        relative=normalized_options.relative,
        edge_deflection=normalized_options.edge_deflection,
        edge_deflection_ratio=normalized_options.edge_deflection_ratio,
        max_edge_points=normalized_options.max_edge_points,
        digits=normalized_options.digits,
        mesh_resolution=normalized_options.mesh_resolution,
        edge_visibility_classes=normalize_step_edge_render_visibility_classes(
            normalized_options.edge_visibility_classes
        ),
    )


def _extract_prototype(
    shape: Any,
    profile: SelectorProfile,
    options: SelectorOptions,
    *,
    already_meshed: bool = False,
) -> dict[str, Any]:
    if profile == SelectorProfile.SUMMARY:
        return _extract_summary_prototype(shape, options)
    return _extract_refs_prototype(
        shape,
        options,
        include_buffers=(profile == SelectorProfile.ARTIFACT),
        already_meshed=already_meshed,
    )


def extract_selectors_from_scene(
    scene: LoadedStepScene,
    *,
    cad_ref: str | None = None,
    profile: SelectorProfile = SelectorProfile.ARTIFACT,
    options: SelectorOptions | None = None,
    color: ColorRGBA | tuple[float, ...] | None = None,
    occurrence_colors: dict[str, ColorRGBA] | None = None,
) -> SelectorBundle:
    started = time.perf_counter()
    resolved_step_path = scene.step_path
    # Retain the argument for existing callers, but topology artifacts are
    # identified by their colocated STEP file plus stepHash, not by a stored
    # repo-relative CAD target.
    _ = cad_ref

    normalized_options = _normalize_selector_options(options)
    if profile != SelectorProfile.SUMMARY:
        mesh_step_scene(
            scene,
            linear_deflection=normalized_options.linear_deflection,
            angular_deflection=normalized_options.angular_deflection,
            relative=normalized_options.relative,
        )

    prototype_started = time.perf_counter()
    prototypes = {
        key: _extract_prototype(
            shape,
            profile,
            normalized_options,
            already_meshed=(profile != SelectorProfile.SUMMARY),
        )
        for key, shape in scene.prototype_shapes.items()
    }
    prototype_elapsed = time.perf_counter() - prototype_started
    load_elapsed = scene.load_elapsed

    roots = scene.roots
    override_color = None if color is None else _normalize_rgba(color)
    normalized_occurrence_colors = {
        str(key): _normalize_rgba(value)
        for key, value in (occurrence_colors or {}).items()
    }

    occurrence_columns = [
        "id",
        "path",
        "name",
        "sourceName",
        "parentId",
        "transform",
        "bbox",
        "shapeStart",
        "shapeCount",
        "faceStart",
        "faceCount",
        "edgeStart",
        "edgeCount",
    ]
    shape_columns = [
        "id",
        "occurrenceId",
        "ordinal",
        "kind",
        "name",
        "sourceName",
        "bbox",
        "center",
        "area",
        "volume",
        "faceStart",
        "faceCount",
        "edgeStart",
        "edgeCount",
    ]
    shape_face_start_column = shape_columns.index("faceStart")
    shape_edge_start_column = shape_columns.index("edgeStart")
    face_columns = [
        "id",
        "occurrenceId",
        "shapeId",
        "ordinal",
        "surfaceType",
        "area",
        "center",
        "normal",
        "bbox",
        "edgeStart",
        "edgeCount",
        "relevance",
        "flags",
        "params",
        "triangleStart",
        "triangleCount",
    ]
    edge_columns = [
        "id",
        "occurrenceId",
        "shapeId",
        "ordinal",
        "curveType",
        "length",
        "center",
        "bbox",
        "faceStart",
        "faceCount",
        "relevance",
        "flags",
        "params",
        "segmentStart",
        "segmentCount",
        "adjacentFaceCount",
        "continuity",
        "dihedralDeg",
        "visibilityClass",
        "surfaceHalfEdgeStart",
        "surfaceHalfEdgeCount",
    ]

    occurrence_rows: list[list[Any]] = []
    shape_rows: list[list[Any]] = []
    face_rows: list[list[Any]] = []
    edge_rows: list[list[Any]] = []

    face_edge_rows = array("I")
    edge_face_rows = array("I")
    face_proxy_runs = array("I")
    edge_proxy_positions = array("f")
    edge_proxy_indices = array("I")
    edge_proxy_ids = array("I")
    surface_half_edges = array("I")

    entry_bbox_boxes: list[dict[str, Any]] = []
    leaf_occurrence_count = 0
    summary_shape_count = 0
    summary_face_count = 0
    summary_edge_count = 0
    unmapped_surface_edges: list[str] = []
    edge_visibility_class_counts: dict[str, int] = {}
    generated_edge_visibility_class_counts: dict[str, int] = {}

    def append_occurrence_row(node: OccurrenceNode) -> str:
        occurrence_id = _selector_id(node.path)
        parent_id = _selector_id(node.path[:-1]) if len(node.path) > 1 else None
        node.row_index = len(occurrence_rows)
        occurrence_rows.append(
            [
                occurrence_id,
                ".".join(str(segment) for segment in node.path),
                node.name,
                node.source_name,
                parent_id,
                _round_transform(node.transform, normalized_options.digits),
                None,
                0,
                0,
                0,
                0,
                0,
                0,
            ]
        )
        return occurrence_id

    def finalize_occurrence_row(node: OccurrenceNode, bbox: dict[str, Any], ranges: dict[str, int]) -> None:
        occurrence_rows[node.row_index][6] = _compact_bbox(bbox, normalized_options.digits)
        occurrence_rows[node.row_index][7] = ranges["shapeStart"]
        occurrence_rows[node.row_index][8] = ranges["shapeCount"]
        occurrence_rows[node.row_index][9] = ranges["faceStart"]
        occurrence_rows[node.row_index][10] = ranges["faceCount"]
        occurrence_rows[node.row_index][11] = ranges["edgeStart"]
        occurrence_rows[node.row_index][12] = ranges["edgeCount"]

    def glb_default_color_for_node(node: OccurrenceNode, occurrence_id: str) -> tuple[ColorRGBA, bool]:
        if override_color is not None:
            return override_color, True
        occurrence_color = _occurrence_color_for_id(occurrence_id, normalized_occurrence_colors)
        if occurrence_color is not None:
            return occurrence_color, True
        if node.color is not None:
            return _normalize_rgba(node.color), False
        if node.prototype_key is not None and node.prototype_key in scene.prototype_colors:
            return _normalize_rgba(scene.prototype_colors[node.prototype_key]), False
        return DEFAULT_TOPOLOGY_MATERIAL, False

    def glb_face_runs_for_node(
        node: OccurrenceNode,
        occurrence_id: str,
        prototype: dict[str, Any],
    ) -> tuple[dict[int, tuple[int, int, int]], Any | None]:
        if node.prototype_key is None:
            return {}, None
        default_color, suppress_face_colors = glb_default_color_for_node(node, occurrence_id)
        payload = scene_glb_mesh_payload(
            scene,
            node.prototype_key,
            default_color=default_color,
            suppress_face_colors=suppress_face_colors,
            prototype=prototype,
            include_surface_edges=(profile == SelectorProfile.ARTIFACT),
            surface_edge_class_signature=normalized_options.edge_visibility_classes,
        )
        runs: dict[int, tuple[int, int, int]] = {}
        for face_entry in prototype.get("faces", []):
            face_hash = int(face_entry.get("shapeHash") or 0)
            runs[int(face_entry["ordinal"])] = payload.face_runs_by_hash.get(face_hash, (0, 0, 0))
        return runs, payload

    def emit_leaf(node: OccurrenceNode, occurrence_id: str, prototype: dict[str, Any]) -> dict[str, Any]:
        nonlocal leaf_occurrence_count, summary_shape_count, summary_face_count, summary_edge_count
        leaf_occurrence_count += 1

        start_shape = len(shape_rows)
        start_face = len(face_rows)
        start_edge = len(edge_rows)
        shape_count = len(prototype.get("shapes", []))
        prototype_name = (
            scene.prototype_names.get(node.prototype_key)
            if node.prototype_key is not None
            else None
        )
        occurrence_shape_name = node.name or node.source_name or prototype_name

        def scoped_shape_name(base: str | None, ordinal: int) -> str | None:
            text = str(base or "").strip()
            if not text:
                return None
            if shape_count <= 1:
                return text
            return f"{text}:s{ordinal}"

        if profile == SelectorProfile.SUMMARY:
            summary_shape_count += int(prototype.get("shapeCount") or 0)
            summary_face_count += int(prototype.get("faceCount") or 0)
            summary_edge_count += int(prototype.get("edgeCount") or 0)
            bbox = _transform_bbox(prototype["bbox"], node.transform)
            entry_bbox_boxes.append(bbox)
            return {
                "bbox": bbox,
                "shapeStart": 0,
                "shapeCount": int(prototype.get("shapeCount") or 0),
                "faceStart": 0,
                "faceCount": int(prototype.get("faceCount") or 0),
                "edgeStart": 0,
                "edgeCount": int(prototype.get("edgeCount") or 0),
            }

        local_shape_index_to_global_row: dict[int, int] = {}
        for shape_entry in prototype.get("shapes", []):
            shape_ordinal = int(shape_entry["ordinal"])
            local_shape_index_to_global_row[shape_ordinal] = len(shape_rows)
            shape_rows.append(
                [
                    f"{occurrence_id}.s{shape_ordinal}",
                    occurrence_id,
                    shape_ordinal,
                    shape_entry["kind"],
                    scoped_shape_name(occurrence_shape_name, shape_ordinal),
                    scoped_shape_name(prototype_name or node.source_name, shape_ordinal),
                    _compact_bbox(_transform_bbox(shape_entry["bbox"], node.transform), normalized_options.digits),
                    _round_point(_apply_transform_point(node.transform, shape_entry["center"]), normalized_options.digits),
                    _round_value(shape_entry.get("area", 0.0), normalized_options.digits),
                    None if shape_entry.get("volume") is None else _round_value(shape_entry["volume"], normalized_options.digits),
                    0,
                    len(shape_entry.get("faceOrdinals", [])),
                    0,
                    len(shape_entry.get("edgeOrdinals", [])),
                ]
            )

        local_face_index_to_global_row: dict[int, int] = {}
        for face_entry in prototype.get("faces", []):
            local_face_index_to_global_row[int(face_entry["ordinal"])] = len(face_rows)
            edge_start = len(face_edge_rows)
            face_rows.append(
                [
                    f"{occurrence_id}.f{face_entry['ordinal']}",
                    occurrence_id,
                    f"{occurrence_id}.s{face_entry['shapeOrdinal']}",
                    int(face_entry["ordinal"]),
                    face_entry["surfaceType"],
                    _round_value(face_entry["area"], normalized_options.digits),
                    _round_point(_apply_transform_point(node.transform, face_entry["center"]), normalized_options.digits),
                    None
                    if face_entry.get("normal") is None
                    else _round_point(_apply_transform_vector(node.transform, face_entry["normal"]) or face_entry["normal"], normalized_options.digits),
                    _compact_bbox(_transform_bbox(face_entry["bbox"], node.transform), normalized_options.digits),
                    edge_start,
                    len(face_entry["edgeOrdinals"]),
                    int(face_entry.get("relevance", 0)),
                    int(face_entry.get("flags", 0)),
                    None
                    if face_entry.get("params") is None
                    else _transform_param_dict(face_entry["params"], node.transform, normalized_options.digits),
                    0,
                    0,
                ]
            )

        local_edge_index_to_global_row: dict[int, int] = {}
        for edge_entry in prototype.get("edges", []):
            local_edge_index_to_global_row[int(edge_entry["ordinal"])] = len(edge_rows)
            visibility_class = str(edge_entry.get("visibilityClass") or STEP_EDGE_VISIBILITY_CLASSES["FEATURE"])
            edge_visibility_class_counts[visibility_class] = edge_visibility_class_counts.get(visibility_class, 0) + 1
            if int(edge_entry.get("surfaceClassCode") or 0) > 0:
                generated_edge_visibility_class_counts[visibility_class] = (
                    generated_edge_visibility_class_counts.get(visibility_class, 0) + 1
                )
            face_start = len(edge_face_rows)
            edge_rows.append(
                [
                    f"{occurrence_id}.e{edge_entry['ordinal']}",
                    occurrence_id,
                    f"{occurrence_id}.s{edge_entry['shapeOrdinal']}",
                    int(edge_entry["ordinal"]),
                    edge_entry["curveType"],
                    _round_value(edge_entry["length"], normalized_options.digits),
                    _round_point(_apply_transform_point(node.transform, edge_entry["center"]), normalized_options.digits),
                    _compact_bbox(_transform_bbox(edge_entry["bbox"], node.transform), normalized_options.digits),
                    face_start,
                    len(edge_entry["faceOrdinals"]),
                    int(edge_entry.get("relevance", 0)),
                    int(edge_entry.get("flags", 0)),
                    None
                    if edge_entry.get("params") is None
                    else _transform_param_dict(edge_entry["params"], node.transform, normalized_options.digits),
                    0,
                    0,
                    int(edge_entry.get("adjacentFaceCount") or 0),
                    str(edge_entry.get("continuity") or ""),
                    edge_entry.get("dihedralDeg"),
                    visibility_class,
                    0,
                    0,
                ]
            )

        for shape_entry in prototype.get("shapes", []):
            global_shape_row = local_shape_index_to_global_row[int(shape_entry["ordinal"])]
            if shape_entry.get("faceOrdinals"):
                first_face_global = local_face_index_to_global_row[shape_entry["faceOrdinals"][0]]
            else:
                first_face_global = len(face_rows)
            if shape_entry.get("edgeOrdinals"):
                first_edge_global = local_edge_index_to_global_row[shape_entry["edgeOrdinals"][0]]
            else:
                first_edge_global = len(edge_rows)
            shape_rows[global_shape_row][shape_face_start_column] = first_face_global
            shape_rows[global_shape_row][shape_edge_start_column] = first_edge_global

        for face_entry in prototype.get("faces", []):
            global_face_row = local_face_index_to_global_row[int(face_entry["ordinal"])]
            edge_start = len(face_edge_rows)
            face_rows[global_face_row][9] = edge_start
            for edge_ordinal in face_entry["edgeOrdinals"]:
                face_edge_rows.append(local_edge_index_to_global_row[int(edge_ordinal)])

        for edge_entry in prototype.get("edges", []):
            global_edge_row = local_edge_index_to_global_row[int(edge_entry["ordinal"])]
            face_start = len(edge_face_rows)
            edge_rows[global_edge_row][8] = face_start
            for face_ordinal in edge_entry["faceOrdinals"]:
                edge_face_rows.append(local_face_index_to_global_row[int(face_ordinal)])

        if profile == SelectorProfile.ARTIFACT:
            face_runs, glb_payload = glb_face_runs_for_node(node, occurrence_id, prototype)
            for face_entry in prototype.get("faces", []):
                global_face_row = local_face_index_to_global_row[int(face_entry["ordinal"])]
                primitive_index, triangle_start, triangle_count = face_runs.get(int(face_entry["ordinal"]), (0, 0, 0))
                face_rows[global_face_row][14] = triangle_start
                face_rows[global_face_row][15] = triangle_count
                if triangle_count > 0:
                    face_proxy_runs.extend([
                        int(node.row_index),
                        int(primitive_index),
                        int(triangle_start),
                        int(triangle_count),
                        int(global_face_row),
                    ])

            for face_ordinal, half_edges in (getattr(glb_payload, "surface_half_edges_by_face_ordinal", {}) or {}).items():
                global_face_row = local_face_index_to_global_row.get(int(face_ordinal))
                if not isinstance(global_face_row, int):
                    continue
                for edge_ordinal, primitive_index, triangle_index, side, class_code in half_edges:
                    global_edge_row = local_edge_index_to_global_row.get(int(edge_ordinal))
                    if not isinstance(global_edge_row, int):
                        continue
                    current_count = int(edge_rows[global_edge_row][20] or 0)
                    if current_count == 0:
                        edge_rows[global_edge_row][19] = len(surface_half_edges) // 7
                    edge_rows[global_edge_row][20] = current_count + 1
                    surface_half_edges.extend(
                        [
                            int(global_edge_row),
                            int(global_face_row),
                            int(node.row_index),
                            int(primitive_index),
                            int(triangle_index),
                            int(side),
                            int(class_code),
                        ]
                    )

            unmapped_edges = []
            for edge_entry in prototype.get("edges", []):
                class_code = int(edge_entry.get("surfaceClassCode") or 0)
                if not is_displayable_step_edge_surface_class_code(class_code):
                    continue
                global_edge_row = local_edge_index_to_global_row.get(int(edge_entry["ordinal"]))
                if isinstance(global_edge_row, int) and int(edge_rows[global_edge_row][20] or 0) <= 0:
                    unmapped_edges.append(f"{occurrence_id}.e{edge_entry['ordinal']}")
            if unmapped_edges:
                unmapped_surface_edges.extend(unmapped_edges)

            for edge_entry in prototype.get("edges", []):
                global_edge_row = local_edge_index_to_global_row[int(edge_entry["ordinal"])]
                points = edge_entry["points"]
                if len(points) < 2:
                    continue
                vertex_offset = len(edge_proxy_positions) // 3
                segment_start = len(edge_proxy_ids)
                for point in points:
                    transformed = _apply_transform_point(node.transform, point)
                    edge_proxy_positions.extend(_round_point(transformed, normalized_options.digits))
                for local_index in range(len(points) - 1):
                    edge_proxy_indices.extend([vertex_offset + local_index, vertex_offset + local_index + 1])
                    edge_proxy_ids.append(global_edge_row)
                if edge_entry.get("closed", False) and _distance(points[0], points[-1]) > 1e-9:
                    edge_proxy_indices.extend([vertex_offset + len(points) - 1, vertex_offset])
                    edge_proxy_ids.append(global_edge_row)
                edge_rows[global_edge_row][13] = segment_start
                edge_rows[global_edge_row][14] = len(edge_proxy_ids) - segment_start

        bbox = _transform_bbox(prototype["bbox"], node.transform)
        entry_bbox_boxes.append(bbox)
        return {
            "bbox": bbox,
            "shapeStart": start_shape,
            "shapeCount": len(shape_rows) - start_shape,
            "faceStart": start_face,
            "faceCount": len(face_rows) - start_face,
            "edgeStart": start_edge,
            "edgeCount": len(edge_rows) - start_edge,
        }

    def emit_node(node: OccurrenceNode) -> dict[str, Any]:
        occurrence_id = append_occurrence_row(node)
        shape_start = len(shape_rows)
        face_start = len(face_rows)
        edge_start = len(edge_rows)
        child_boxes: list[dict[str, Any]] = []
        aggregated_shape_count = 0
        aggregated_face_count = 0
        aggregated_edge_count = 0

        if node.prototype_key is not None:
            leaf_result = emit_leaf(node, occurrence_id, prototypes[node.prototype_key])
            child_boxes.append(leaf_result["bbox"])
            aggregated_shape_count += int(leaf_result["shapeCount"])
            aggregated_face_count += int(leaf_result["faceCount"])
            aggregated_edge_count += int(leaf_result["edgeCount"])

        for child in node.children:
            child_result = emit_node(child)
            child_boxes.append(child_result["bbox"])
            aggregated_shape_count += int(child_result["shapeCount"])
            aggregated_face_count += int(child_result["faceCount"])
            aggregated_edge_count += int(child_result["edgeCount"])

        bbox = _merge_bbox(child_boxes) if child_boxes else _bbox_from_points([])
        ranges = {
            "shapeStart": shape_start if profile != SelectorProfile.SUMMARY else 0,
            "shapeCount": aggregated_shape_count if profile == SelectorProfile.SUMMARY else len(shape_rows) - shape_start,
            "faceStart": face_start if profile != SelectorProfile.SUMMARY else 0,
            "faceCount": aggregated_face_count if profile == SelectorProfile.SUMMARY else len(face_rows) - face_start,
            "edgeStart": edge_start if profile != SelectorProfile.SUMMARY else 0,
            "edgeCount": aggregated_edge_count if profile == SelectorProfile.SUMMARY else len(edge_rows) - edge_start,
        }
        finalize_occurrence_row(node, bbox, ranges)
        return {"bbox": bbox, **ranges}

    for root in roots:
        emit_node(root)

    overall_bbox = _merge_bbox(entry_bbox_boxes) if entry_bbox_boxes else _bbox_from_points([])
    elapsed = load_elapsed + (time.perf_counter() - started)

    stats = {
        "occurrenceCount": len(occurrence_rows),
        "leafOccurrenceCount": leaf_occurrence_count,
        "shapeCount": summary_shape_count if profile == SelectorProfile.SUMMARY else len(shape_rows),
        "faceCount": summary_face_count if profile == SelectorProfile.SUMMARY else len(face_rows),
        "edgeCount": summary_edge_count if profile == SelectorProfile.SUMMARY else len(edge_rows),
        "faceProxyRunCount": len(face_proxy_runs) // 5 if profile == SelectorProfile.ARTIFACT else 0,
        "edgeProxyPointCount": len(edge_proxy_positions) // 3 if profile == SelectorProfile.ARTIFACT else 0,
        "edgeProxySegmentCount": len(edge_proxy_ids) if profile == SelectorProfile.ARTIFACT else 0,
        "surfaceHalfEdgeCount": len(surface_half_edges) // 7 if profile == SelectorProfile.ARTIFACT else 0,
        "unmappedSurfaceEdgeCount": (
            len(unmapped_surface_edges) if profile == SelectorProfile.ARTIFACT else 0
        ),
        "timingMs": {
            "load": round(load_elapsed * 1000.0, 1),
            "extract": round(prototype_elapsed * 1000.0, 1),
            "total": round(elapsed * 1000.0, 1),
        },
    }
    if unmapped_surface_edges and profile == SelectorProfile.ARTIFACT:
        stats["unmappedSurfaceEdgePreview"] = unmapped_surface_edges[:20]
    edge_rendering_manifest: dict[str, Any] = {
        "visibilityClasses": list(normalized_options.edge_visibility_classes),
        "generatedVisibilityClasses": [
            class_id
            for class_id in normalized_options.edge_visibility_classes
            if generated_edge_visibility_class_counts.get(class_id, 0) > 0
        ],
        "visibilityClassCounts": dict(sorted(edge_visibility_class_counts.items())),
        "generatedVisibilityClassCounts": dict(sorted(generated_edge_visibility_class_counts.items())),
    }
    mesh_manifest: dict[str, Any] = {
        "linearDeflection": float(normalized_options.linear_deflection),
        "angularDeflection": float(normalized_options.angular_deflection),
        "relative": bool(normalized_options.relative),
    }
    if isinstance(normalized_options.mesh_resolution, dict):
        mesh_manifest["resolution"] = normalized_options.mesh_resolution

    source_kind = str(getattr(scene, "source_kind", "step") or "step").strip().lower()
    if source_kind not in {"step", "python"}:
        source_kind = "step"
    source_path = str(getattr(scene, "source_path", "") or "").strip()
    if not source_path and source_kind != "python":
        source_path = _relative_step_path(resolved_step_path)
    if not source_path:
        raise RuntimeError(f"STEP_topology artifact sourcePath is required for {resolved_step_path}")

    manifest: dict[str, Any] = {
        "schemaVersion": STEP_TOPOLOGY_SCHEMA_VERSION,
        "profile": profile.value,
        "capabilities": step_topology_capabilities(normalized_options.edge_visibility_classes),
        "sourceKind": source_kind,
        "sourcePath": source_path,
        "stepPath": _relative_step_path(resolved_step_path),
        "bbox": _compact_bbox(overall_bbox, normalized_options.digits),
        "stats": stats,
        "edgeRendering": edge_rendering_manifest,
        "mesh": mesh_manifest,
        "tables": {
            "occurrenceColumns": occurrence_columns,
            "shapeColumns": shape_columns,
            "faceColumns": face_columns,
            "edgeColumns": edge_columns,
        },
        "occurrences": occurrence_rows,
        "shapes": shape_rows,
        "faces": face_rows,
        "edges": edge_rows,
    }
    if source_kind == "python":
        source_hash = str(getattr(scene, "source_hash", "") or "").strip()
        if source_hash:
            manifest["sourceHash"] = source_hash
        manifest["generatedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if scene.step_path.is_file():
        manifest["stepHash"] = _scene_step_hash(scene)

    if profile != SelectorProfile.SUMMARY:
        if profile == SelectorProfile.ARTIFACT:
            manifest["faceProxy"] = {
                "source": f".{scene.step_path.name}.glb",
                "runsView": "faceRuns",
                "runColumns": ["occurrenceRow", "primitiveIndex", "triangleStart", "triangleCount", "faceRow"],
            }
            manifest["edgeProxy"] = {
                "positionsView": "edgePositions",
                "indicesView": "edgeIndices",
                "edgeIdsView": "edgeIds",
            }
            manifest["relations"] = {
                "faceEdgeRowsView": "faceEdgeRows",
                "edgeFaceRowsView": "edgeFaceRows",
            }
            buffers = {
                "faceRuns": face_proxy_runs,
                "edgePositions": edge_proxy_positions,
                "edgeIndices": edge_proxy_indices,
                "edgeIds": edge_proxy_ids,
                "faceEdgeRows": face_edge_rows,
                "edgeFaceRows": edge_face_rows,
                "surfaceHalfEdges": surface_half_edges,
            }
            return SelectorBundle(manifest=manifest, buffers=buffers)

        manifest["relations"] = {
            "faceEdgeRows": list(face_edge_rows),
            "edgeFaceRows": list(edge_face_rows),
        }

    return SelectorBundle(manifest=manifest)
