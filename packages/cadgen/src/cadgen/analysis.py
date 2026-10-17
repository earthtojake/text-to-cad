from __future__ import annotations

import math

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
    if row.get("id"):
        facts["selector"] = str(row["id"])
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

    if selector_type == "vertex":
        facts["kind"] = "point"
        if center is not None:
            facts["point"] = list(center)
        if row.get("occurrenceId"):
            facts["occurrenceId"] = str(row["occurrenceId"])
        return facts

    params = row.get("params") if isinstance(row.get("params"), dict) else {}
    if row.get("occurrenceId"):
        facts["occurrenceId"] = str(row["occurrenceId"])
    if row.get("shapeId"):
        facts["shapeId"] = str(row["shapeId"])

    if selector_type == "face":
        surface_type = str(row.get("surfaceType") or "").lower()
        facts["kind"] = surface_type or "face"

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
