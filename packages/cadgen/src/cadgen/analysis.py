from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from . import lookup


AXIS_NAMES = ("x", "y", "z")
AXIS_INDEX = {name: index for index, name in enumerate(AXIS_NAMES)}
AXIS_ALIGNMENT_THRESHOLD = 0.985


def _float_triplet(value: object) -> tuple[float, float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None
    try:
        return (float(value[0]), float(value[1]), float(value[2]))
    except (TypeError, ValueError):
        return None


def _normalize(vector: tuple[float, float, float] | None) -> tuple[float, float, float] | None:
    if vector is None:
        return None
    length = math.sqrt(sum(component * component for component in vector))
    if length <= 1e-12:
        return None
    return tuple(component / length for component in vector)


def dominant_axis(
    vector: object,
    *,
    aligned_threshold: float = AXIS_ALIGNMENT_THRESHOLD,
) -> dict[str, object] | None:
    normalized = _normalize(_float_triplet(vector))
    if normalized is None:
        return None
    magnitudes = [abs(component) for component in normalized]
    axis_index = max(range(3), key=lambda index: magnitudes[index])
    component = normalized[axis_index]
    return {
        "axis": AXIS_NAMES[axis_index],
        "index": axis_index,
        "sign": 1 if component >= 0.0 else -1,
        "component": component,
        "magnitude": magnitudes[axis_index],
        "aligned": magnitudes[axis_index] >= aligned_threshold,
    }


def bbox_size(bbox: object) -> list[float] | None:
    if not isinstance(bbox, dict):
        return None
    min_point = _float_triplet(bbox.get("min"))
    max_point = _float_triplet(bbox.get("max"))
    if min_point is None or max_point is None:
        return None
    return [
        float(max_point[0] - min_point[0]),
        float(max_point[1] - min_point[1]),
        float(max_point[2] - min_point[2]),
    ]


def bbox_center(bbox: object) -> list[float] | None:
    if not isinstance(bbox, dict):
        return None
    min_point = _float_triplet(bbox.get("min"))
    max_point = _float_triplet(bbox.get("max"))
    if min_point is None or max_point is None:
        return None
    return [
        float((min_point[0] + max_point[0]) * 0.5),
        float((min_point[1] + max_point[1]) * 0.5),
        float((min_point[2] + max_point[2]) * 0.5),
    ]


def bbox_diag(bbox: object) -> float | None:
    size = bbox_size(bbox)
    if size is None:
        return None
    return math.sqrt(sum(component * component for component in size))


def bbox_facts(bbox: object) -> dict[str, object]:
    facts: dict[str, object] = {}
    if not isinstance(bbox, dict):
        return facts
    size = bbox_size(bbox)
    center = bbox_center(bbox)
    diag = bbox_diag(bbox)
    if size is not None:
        facts["size"] = size
        extent_axis = dominant_axis(size, aligned_threshold=0.0)
        if extent_axis is not None:
            facts["extentAxis"] = extent_axis["axis"]
    if center is not None:
        facts["center"] = center
    if diag is not None:
        facts["diag"] = diag
    return facts


def _dot(left: tuple[float, float, float], right: tuple[float, float, float]) -> float:
    return (left[0] * right[0]) + (left[1] * right[1]) + (left[2] * right[2])


def _transform_tuple(value: object) -> tuple[float, ...] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 16:
        return None
    try:
        transform = tuple(float(item) for item in value)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(item) for item in transform):
        return None
    return transform


def _axis_alignment_payload(vector: object) -> dict[str, object] | None:
    alignment = dominant_axis(vector)
    if alignment is None:
        return None
    return {
        "axis": alignment["axis"],
        "sign": alignment["sign"],
        "aligned": alignment["aligned"],
        "magnitude": alignment["magnitude"],
    }


def transform_frame_facts(transform: object) -> dict[str, object] | None:
    matrix = _transform_tuple(transform)
    if matrix is None:
        return None
    local_x = _normalize((matrix[0], matrix[4], matrix[8]))
    local_y = _normalize((matrix[1], matrix[5], matrix[9]))
    local_z = _normalize((matrix[2], matrix[6], matrix[10]))
    return {
        "translation": [matrix[3], matrix[7], matrix[11]],
        "localAxes": {
            "x": list(local_x) if local_x is not None else [matrix[0], matrix[4], matrix[8]],
            "y": list(local_y) if local_y is not None else [matrix[1], matrix[5], matrix[9]],
            "z": list(local_z) if local_z is not None else [matrix[2], matrix[6], matrix[10]],
        },
        "transform": list(matrix),
    }


def positioning_facts_for_row(
    selector_type: str,
    row: dict[str, object],
    index: lookup.SelectorIndex | None = None,
) -> dict[str, object]:
    bbox = row.get("bbox")
    center = _float_triplet(row.get("center")) or _float_triplet(bbox_center(bbox))
    facts: dict[str, object] = {
        "selectorType": selector_type,
    }
    if index is not None and row.get("id"):
        facts["selector"] = lookup.display_selector(str(row["id"]), index)
    if isinstance(bbox, dict):
        facts["bbox"] = bbox
        bbox_fact_payload = bbox_facts(bbox)
        if bbox_fact_payload:
            facts["bboxFacts"] = bbox_fact_payload
    if center is not None:
        facts["center"] = list(center)

    if selector_type == "occurrence":
        facts["kind"] = "frame"
        name = str(row.get("name") or row.get("sourceName") or "").strip()
        if name:
            facts["name"] = name
        frame = transform_frame_facts(row.get("transform"))
        if frame is not None:
            facts.update(frame)
        return facts

    if selector_type == "shape":
        facts["kind"] = str(row.get("kind") or "shape")
        if index is not None and row.get("occurrenceId"):
            facts["occurrenceId"] = lookup.display_selector(str(row["occurrenceId"]), index)
        return facts

    if selector_type == "vertex":
        facts["kind"] = "point"
        if center is not None:
            facts["point"] = list(center)
        if index is not None and row.get("occurrenceId"):
            facts["occurrenceId"] = lookup.display_selector(str(row["occurrenceId"]), index)
        return facts

    params = row.get("params") if isinstance(row.get("params"), dict) else {}
    if index is not None and row.get("occurrenceId"):
        facts["occurrenceId"] = lookup.display_selector(str(row["occurrenceId"]), index)
    if index is not None and row.get("shapeId"):
        facts["shapeId"] = lookup.display_selector(str(row["shapeId"]), index)

    if selector_type == "face":
        surface_type = str(row.get("surfaceType") or "").lower()
        facts["kind"] = surface_type or "face"
        if row.get("area") not in {None, ""}:
            facts["area"] = float(row["area"])

        normal = _normalize(
            _float_triplet(row.get("normal"))
            or _float_triplet(params.get("normal"))
            or _float_triplet(params.get("axis"))
        )
        point = _float_triplet(params.get("origin")) or center
        if point is not None:
            facts["origin"] = list(point)
        if normal is not None:
            facts["normal"] = list(normal)
            alignment = _axis_alignment_payload(normal)
            if alignment is not None:
                facts["axisAlignment"] = alignment
                facts["normalAxis"] = {
                    "axis": alignment["axis"],
                    "sign": alignment["sign"],
                    "aligned": alignment["aligned"],
                }
                if bool(alignment["aligned"]) and point is not None:
                    axis = str(alignment["axis"])
                    facts["axis"] = axis
                    facts["coordinate"] = float(point[AXIS_INDEX[axis]])
            if point is not None:
                facts["planeOffset"] = _dot(normal, point)

        radius = params.get("radius")
        if radius not in {None, ""}:
            facts["radius"] = float(radius)
        if surface_type in {"cylinder", "cone", "torus"}:
            axis_vector = _normalize(_float_triplet(params.get("axis")))
            if axis_vector is not None:
                facts["axisVector"] = list(axis_vector)
                facts["axisAlignment"] = _axis_alignment_payload(axis_vector)
        if surface_type == "sphere":
            sphere_center = _float_triplet(params.get("center")) or center
            if sphere_center is not None:
                facts["center"] = list(sphere_center)
        return facts

    curve_type = str(row.get("curveType") or "").lower()
    facts["kind"] = curve_type or "edge"
    if row.get("length") not in {None, ""}:
        facts["length"] = float(row["length"])
    if curve_type == "line":
        origin = _float_triplet(params.get("origin")) or center
        direction = _normalize(_float_triplet(params.get("direction")))
        if origin is not None:
            facts["origin"] = list(origin)
        if direction is not None:
            facts["direction"] = list(direction)
            alignment = _axis_alignment_payload(direction)
            if alignment is not None:
                facts["axisAlignment"] = alignment
                if bool(alignment["aligned"]) and center is not None:
                    axis = str(alignment["axis"])
                    facts["axis"] = axis
                    facts["coordinate"] = float(center[AXIS_INDEX[axis]])
    elif curve_type in {"circle", "ellipse"}:
        circle_center = _float_triplet(params.get("center")) or center
        axis_vector = _normalize(_float_triplet(params.get("axis")))
        if circle_center is not None:
            facts["center"] = list(circle_center)
        if axis_vector is not None:
            facts["axisVector"] = list(axis_vector)
            facts["axisAlignment"] = _axis_alignment_payload(axis_vector)
        for radius_key in ("radius", "majorRadius", "minorRadius"):
            if params.get(radius_key) not in {None, ""}:
                facts[radius_key] = float(params[radius_key])
    return facts


def positioning_point(facts: dict[str, object]) -> list[float] | None:
    for key in ("point", "origin", "center", "translation"):
        point = _float_triplet(facts.get(key))
        if point is not None:
            return list(point)
    bbox = facts.get("bbox")
    center = bbox_center(bbox)
    return center if center is not None else None


def positioning_coordinate(
    facts: dict[str, object],
    axis: str,
) -> tuple[float, str] | None:
    normalized_axis = str(axis or "").strip().lower()
    if normalized_axis not in AXIS_INDEX:
        return None
    if str(facts.get("axis") or "") == normalized_axis and facts.get("coordinate") not in {None, ""}:
        return float(facts["coordinate"]), "coordinate"
    point = positioning_point(facts)
    if point is not None:
        return float(point[AXIS_INDEX[normalized_axis]]), "point"
    return None


def infer_positioning_axis(*fact_payloads: dict[str, object]) -> str | None:
    axes: list[str] = []
    for facts in fact_payloads:
        alignment = facts.get("axisAlignment")
        if not isinstance(alignment, dict) or not bool(alignment.get("aligned")):
            continue
        axis = str(alignment.get("axis") or "")
        if axis in AXIS_INDEX:
            axes.append(axis)
    if axes and all(axis == axes[0] for axis in axes):
        return axes[0]
    for facts in fact_payloads:
        axis = str(facts.get("axis") or "")
        if axis in AXIS_INDEX:
            return axis
    return None


def vector_relationship(
    left: object,
    right: object,
    *,
    aligned_threshold: float = AXIS_ALIGNMENT_THRESHOLD,
) -> dict[str, object] | None:
    left_vector = _normalize(_float_triplet(left))
    right_vector = _normalize(_float_triplet(right))
    if left_vector is None or right_vector is None:
        return None
    dot = _dot(left_vector, right_vector)
    abs_dot = abs(dot)
    if dot <= -aligned_threshold:
        relation = "opposed"
    elif dot >= aligned_threshold:
        relation = "parallel"
    elif abs_dot <= 1.0 - aligned_threshold:
        relation = "perpendicular"
    else:
        relation = "angled"
    return {
        "relation": relation,
        "dot": dot,
        "aligned": abs_dot >= aligned_threshold,
    }


def geometry_facts_for_row(
    selector_type: str,
    row: dict[str, object],
    index: lookup.SelectorIndex | None = None,
) -> dict[str, object]:
    facts = bbox_facts(row.get("bbox"))
    if selector_type in {"occurrence", "shape"}:
        return facts

    params = row.get("params") if isinstance(row.get("params"), dict) else {}
    center = _float_triplet(row.get("center"))
    if center is not None:
        facts.setdefault("center", list(center))

    if selector_type == "vertex":
        if row.get("edgeCount") not in {None, ""}:
            facts["edgeCount"] = int(row["edgeCount"])
        if index is not None and row.get("id"):
            facts["selector"] = lookup.display_selector(str(row["id"]), index)
        return facts

    axis_vector = _float_triplet(params.get("axis"))
    direction_vector = _float_triplet(params.get("direction"))
    normal_vector = _float_triplet(row.get("normal")) or _float_triplet(params.get("normal")) or axis_vector

    if selector_type == "face":
        surface_type = str(row.get("surfaceType") or "")
        if surface_type:
            facts["surfaceType"] = surface_type
        if row.get("area") not in {None, ""}:
            facts["area"] = float(row["area"])
        normal_axis = dominant_axis(normal_vector)
        if normal_axis is not None:
            facts["normalAxis"] = {
                "axis": normal_axis["axis"],
                "sign": normal_axis["sign"],
                "aligned": normal_axis["aligned"],
            }
            if center is not None and bool(normal_axis["aligned"]):
                facts["planeCoordinate"] = center[int(normal_axis["index"])]
        radius = params.get("radius")
        if radius not in {None, ""}:
            facts["radius"] = float(radius)
        if surface_type == "plane" and axis_vector is not None:
            facts["axis"] = list(axis_vector)
        if index is not None and row.get("id"):
            facts["selector"] = lookup.display_selector(str(row["id"]), index)
        return facts

    curve_type = str(row.get("curveType") or "")
    if curve_type:
        facts["curveType"] = curve_type
    if row.get("length") not in {None, ""}:
        facts["length"] = float(row["length"])
    direction_axis = dominant_axis(direction_vector or axis_vector or bbox_size(row.get("bbox")))
    if direction_axis is not None:
        facts["directionAxis"] = {
            "axis": direction_axis["axis"],
            "sign": direction_axis["sign"],
            "aligned": direction_axis["aligned"],
        }
    radius = params.get("radius")
    if radius not in {None, ""}:
        facts["radius"] = float(radius)
    if index is not None and row.get("id"):
        facts["selector"] = lookup.display_selector(str(row["id"]), index)
    return facts


def _merge_bboxes(boxes: list[dict[str, object]]) -> dict[str, object]:
    min_x = min(float(box["min"][0]) for box in boxes)
    min_y = min(float(box["min"][1]) for box in boxes)
    min_z = min(float(box["min"][2]) for box in boxes)
    max_x = max(float(box["max"][0]) for box in boxes)
    max_y = max(float(box["max"][1]) for box in boxes)
    max_z = max(float(box["max"][2]) for box in boxes)
    return {
        "min": [min_x, min_y, min_z],
        "max": [max_x, max_y, max_z],
    }


def major_planar_face_groups(
    index: lookup.SelectorIndex,
    *,
    coordinate_tolerance: float = 1e-3,
    min_area_ratio: float = 0.05,
    limit: int = 12,
) -> list[dict[str, object]]:
    planar_rows = [
        row for row in index.faces if str(row.get("surfaceType") or "").lower() == "plane"
    ]
    total_planar_area = sum(float(row.get("area") or 0.0) for row in planar_rows)
    grouped: dict[tuple[str, int], dict[str, object]] = {}

    for row in planar_rows:
        facts = geometry_facts_for_row("face", row, index)
        normal_axis = facts.get("normalAxis")
        plane_coordinate = facts.get("planeCoordinate")
        if not isinstance(normal_axis, dict) or plane_coordinate in {None, ""}:
            continue
        axis = str(normal_axis.get("axis") or "")
        if axis not in AXIS_INDEX:
            continue
        coordinate = float(plane_coordinate)
        bucket = int(round(coordinate / coordinate_tolerance)) if coordinate_tolerance > 0 else 0
        key = (axis, bucket)
        bbox = row.get("bbox")
        if not isinstance(bbox, dict):
            continue
        group = grouped.get(key)
        if group is None:
            group = {
                "axis": axis,
                "coordinate": 0.0,
                "normalSign": int(normal_axis.get("sign") or 1),
                "faceCount": 0,
                "totalArea": 0.0,
                "bboxParts": [],
                "selectors": [],
            }
            grouped[key] = group
        area = float(row.get("area") or 0.0)
        group["coordinate"] = float(group["coordinate"]) + (coordinate * max(area, 1e-9))
        group["faceCount"] = int(group["faceCount"]) + 1
        group["totalArea"] = float(group["totalArea"]) + area
        group["bboxParts"].append(bbox)
        selector = lookup.display_selector(str(row.get("id") or ""), index)
        if selector:
            group["selectors"].append(selector)

    result: list[dict[str, object]] = []
    for group in grouped.values():
        total_area = float(group["totalArea"])
        if total_planar_area > 0.0 and total_area / total_planar_area < min_area_ratio:
            continue
        weighted_coordinate = float(group["coordinate"]) / max(total_area, 1e-9)
        merged_bbox = _merge_bboxes(list(group["bboxParts"]))
        result.append(
            {
                "axis": group["axis"],
                "coordinate": weighted_coordinate,
                "normalSign": group["normalSign"],
                "faceCount": group["faceCount"],
                "totalArea": total_area,
                "bbox": merged_bbox,
                "selectors": sorted(set(str(selector) for selector in group["selectors"] if selector)),
            }
        )

    result.sort(key=lambda item: (-float(item["totalArea"]), str(item["axis"]), float(item["coordinate"])))
    return result[: max(int(limit), 0)]


def _table_rows(manifest: dict[str, Any], table_name: str, columns_name: str) -> list[dict[str, Any]]:
    columns = manifest.get("tables", {}).get(columns_name)
    rows = manifest.get(table_name)
    if not isinstance(columns, list) or not isinstance(rows, list):
        return []
    materialized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, list):
            continue
        materialized.append({str(columns[index]): row[index] for index in range(min(len(columns), len(row)))})
    return materialized


def _stable_hash(payload: object) -> str:
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def selector_manifest_diff(
    old_manifest: dict[str, Any] | None,
    new_manifest: dict[str, Any],
) -> dict[str, object]:
    if old_manifest is None:
        return {
            "hasPrevious": False,
            "topologyChanged": False,
            "geometryChanged": False,
            "bboxChanged": False,
            "countDelta": {},
        }

    old_faces = _table_rows(old_manifest, "faces", "faceColumns")
    new_faces = _table_rows(new_manifest, "faces", "faceColumns")
    old_edges = _table_rows(old_manifest, "edges", "edgeColumns")
    new_edges = _table_rows(new_manifest, "edges", "edgeColumns")
    old_vertices = _table_rows(old_manifest, "vertices", "vertexColumns")
    new_vertices = _table_rows(new_manifest, "vertices", "vertexColumns")

    old_topology = {
        "occurrences": [row.get("id") for row in _table_rows(old_manifest, "occurrences", "occurrenceColumns")],
        "shapes": [row.get("id") for row in _table_rows(old_manifest, "shapes", "shapeColumns")],
        "faces": [row.get("id") for row in old_faces],
        "edges": [row.get("id") for row in old_edges],
        "vertices": [row.get("id") for row in old_vertices],
        "faceCount": old_manifest.get("stats", {}).get("faceCount"),
        "edgeCount": old_manifest.get("stats", {}).get("edgeCount"),
        "vertexCount": old_manifest.get("stats", {}).get("vertexCount"),
    }
    new_topology = {
        "occurrences": [row.get("id") for row in _table_rows(new_manifest, "occurrences", "occurrenceColumns")],
        "shapes": [row.get("id") for row in _table_rows(new_manifest, "shapes", "shapeColumns")],
        "faces": [row.get("id") for row in new_faces],
        "edges": [row.get("id") for row in new_edges],
        "vertices": [row.get("id") for row in new_vertices],
        "faceCount": new_manifest.get("stats", {}).get("faceCount"),
        "edgeCount": new_manifest.get("stats", {}).get("edgeCount"),
        "vertexCount": new_manifest.get("stats", {}).get("vertexCount"),
    }
    old_geometry = {
        "bbox": old_manifest.get("bbox"),
        "faces": [
            {
                "id": row.get("id"),
                "surfaceType": row.get("surfaceType"),
                "center": row.get("center"),
                "normal": row.get("normal"),
                "bbox": row.get("bbox"),
                "area": row.get("area"),
            }
            for row in old_faces
        ],
        "edges": [
            {
                "id": row.get("id"),
                "curveType": row.get("curveType"),
                "center": row.get("center"),
                "bbox": row.get("bbox"),
                "length": row.get("length"),
            }
            for row in old_edges
        ],
        "vertices": [
            {
                "id": row.get("id"),
                "center": row.get("center"),
                "bbox": row.get("bbox"),
            }
            for row in old_vertices
        ],
    }
    new_geometry = {
        "bbox": new_manifest.get("bbox"),
        "faces": [
            {
                "id": row.get("id"),
                "surfaceType": row.get("surfaceType"),
                "center": row.get("center"),
                "normal": row.get("normal"),
                "bbox": row.get("bbox"),
                "area": row.get("area"),
            }
            for row in new_faces
        ],
        "edges": [
            {
                "id": row.get("id"),
                "curveType": row.get("curveType"),
                "center": row.get("center"),
                "bbox": row.get("bbox"),
                "length": row.get("length"),
            }
            for row in new_edges
        ],
        "vertices": [
            {
                "id": row.get("id"),
                "center": row.get("center"),
                "bbox": row.get("bbox"),
            }
            for row in new_vertices
        ],
    }

    count_delta = {
        "faceCount": int(new_manifest.get("stats", {}).get("faceCount") or 0)
        - int(old_manifest.get("stats", {}).get("faceCount") or 0),
        "edgeCount": int(new_manifest.get("stats", {}).get("edgeCount") or 0)
        - int(old_manifest.get("stats", {}).get("edgeCount") or 0),
        "vertexCount": int(new_manifest.get("stats", {}).get("vertexCount") or 0)
        - int(old_manifest.get("stats", {}).get("vertexCount") or 0),
        "shapeCount": int(new_manifest.get("stats", {}).get("shapeCount") or 0)
        - int(old_manifest.get("stats", {}).get("shapeCount") or 0),
    }

    return {
        "hasPrevious": True,
        "topologyChanged": _stable_hash(old_topology) != _stable_hash(new_topology),
        "geometryChanged": _stable_hash(old_geometry) != _stable_hash(new_geometry),
        "bboxChanged": old_manifest.get("bbox") != new_manifest.get("bbox"),
        "countDelta": count_delta,
    }


def view_name_for_axis(axis: str, sign: int) -> str:
    normalized_sign = 1 if sign >= 0 else -1
    if axis == "x":
        return "right" if normalized_sign > 0 else "left"
    if axis == "y":
        return "top" if normalized_sign > 0 else "bottom"
    return "front" if normalized_sign > 0 else "back"


def aligned_view_name_for_facts(
    selector_type: str,
    facts: dict[str, object],
) -> str | None:
    if selector_type == "face":
        normal_axis = facts.get("normalAxis")
        if isinstance(normal_axis, dict):
            axis = str(normal_axis.get("axis") or "")
            sign = int(normal_axis.get("sign") or 1)
            if axis in AXIS_INDEX:
                return view_name_for_axis(axis, sign)
        return None

    if selector_type != "edge":
        return None
    direction_axis = facts.get("directionAxis")
    if not isinstance(direction_axis, dict):
        return None
    axis = str(direction_axis.get("axis") or "")
    if axis == "x":
        return "front"
    if axis == "y":
        return "front"
    if axis == "z":
        return "top"
    return None
