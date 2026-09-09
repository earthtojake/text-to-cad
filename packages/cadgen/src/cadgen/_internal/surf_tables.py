"""Selector tables from a component ``.surf`` (design/surface-rendering.md R5).

The Python twin of ``@hardcore/core/src/lib/surf/surfSelectorBundle.js`` for the
consumers that compose topology server-side (``assembly_lookup`` behind
inspect and snapshot selector resolution). A ``.surf`` v2 stores the exact
metrics (GProps areas/centers/lengths, BndLib bboxes) the GLB tables used
to carry, so no tessellation happens here — this is a pure re-shaping of
the index into the STEP_TOPOLOGY selector-manifest schema.

Mesh-buffer columns (``triangleStart``/``segmentStart``/…) are zeroed: the
assembly merge drops them anyway (``_BUFFER_START_FIELDS``), and the only
mesh in this architecture lives client-side.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

STEP_TOPOLOGY_SCHEMA_VERSION = 2
_OCCURRENCE_ID = "o1"
_IDENTITY = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]

_OCCURRENCE_COLUMNS = [
    "id", "path", "name", "sourceName", "parentId", "transform", "bbox",
    "shapeStart", "shapeCount", "faceStart", "faceCount", "edgeStart", "edgeCount",
]
_SHAPE_COLUMNS = [
    "id", "occurrenceId", "ordinal", "kind", "name", "sourceName", "bbox",
    "center", "area", "volume", "faceStart", "faceCount", "edgeStart", "edgeCount",
]
_FACE_COLUMNS = [
    "id", "occurrenceId", "shapeId", "ordinal", "surfaceType", "area", "center",
    "normal", "bbox", "edgeStart", "edgeCount", "relevance", "flags", "params",
    "triangleStart", "triangleCount",
]
_EDGE_COLUMNS = [
    "id", "occurrenceId", "shapeId", "ordinal", "curveType", "length", "center",
    "bbox", "faceStart", "faceCount", "relevance", "flags", "params",
    "segmentStart", "segmentCount", "adjacentFaceCount", "continuity",
    "dihedralDeg", "visibilityClass", "surfaceHalfEdgeStart", "surfaceHalfEdgeCount",
]
_ANALYTIC_SURFACES = {"plane", "cylinder", "cone", "sphere", "torus"}
_ANALYTIC_CURVES = {"line", "circle", "ellipse"}


@dataclass
class SurfTopologyBundle:
    manifest: dict[str, Any]
    buffers: dict[str, Any] | None = None


def _box_dict(box: list[float] | None) -> dict[str, list[float]] | None:
    if not box or len(box) != 6:
        return None
    return {"min": box[:3], "max": box[3:]}


def _merge_box(target: dict[str, list[float]] | None,
               source: dict[str, list[float]] | None):
    if source is None:
        return target
    if target is None:
        return {"min": list(source["min"]), "max": list(source["max"])}
    for axis in range(3):
        target["min"][axis] = min(target["min"][axis], source["min"][axis])
        target["max"][axis] = max(target["max"][axis], source["max"][axis])
    return target


def read_component_topology_bundle(surf_path: Path) -> SurfTopologyBundle | None:
    """Load a ``.surf`` and shape its metadata into a selector bundle."""
    try:
        data = surf_path.read_bytes()
    except OSError:
        return None
    from cadgen._internal.surface_extract import read_surf

    try:
        index, _ = read_surf(data)
    except Exception:
        return None
    return selector_bundle_from_surf_index(index)


def selector_bundle_from_surf_index(index: Mapping[str, Any]) -> SurfTopologyBundle:
    faces = list(index.get("faces") or [])
    edges = list(index.get("edges") or [])
    shapes_meta = list(index.get("shapes") or [{"ord": 1, "kind": "shape", "volume": None}])
    face_row_by_ord = {int(face["ord"]): row for row, face in enumerate(faces)}
    edge_row_by_ord = {int(edge["ord"]): row for row, edge in enumerate(edges)}

    total_area = max(sum(float(face.get("area") or 0.0) for face in faces), 1e-12)
    overall = None
    for face in faces:
        overall = _merge_box(overall, _box_dict(face.get("bbox")))
    if overall is None:
        overall = {"min": [0, 0, 0], "max": [0, 0, 0]}
    diag = max(sum((overall["max"][i] - overall["min"][i]) ** 2 for i in range(3)) ** 0.5, 1e-9)
    size_floor = max(diag * diag * 1e-6, 1e-12)
    length_floor = max(diag * 1e-5, 1e-12)
    total_length = max(sum(float(edge.get("length") or 0.0) for edge in edges), 1e-12)

    face_edge_rows: list[int] = []
    face_ranges: dict[int, tuple[int, int]] = {}
    for face in faces:
        start = len(face_edge_rows)
        seen: set[int] = set()
        for loop in face.get("loops") or []:
            for pcurve in loop:
                row = edge_row_by_ord.get(int(pcurve.get("edgeOrd") or 0))
                if row is not None and row not in seen:
                    seen.add(row)
                    face_edge_rows.append(row)
        face_ranges[int(face["ord"])] = (start, len(face_edge_rows) - start)

    edge_face_rows: list[int] = []
    edge_ranges: dict[int, tuple[int, int]] = {}
    for edge in edges:
        start = len(edge_face_rows)
        for face_ord in edge.get("faceOrds") or []:
            row = face_row_by_ord.get(int(face_ord))
            if row is not None:
                edge_face_rows.append(row)
        edge_ranges[int(edge["ord"])] = (start, len(edge_face_rows) - start)

    shape_area: dict[int, float] = {}
    shape_box: dict[int, dict | None] = {}
    shape_faces: dict[int, int] = {}
    shape_edges: dict[int, int] = {}
    for face in faces:
        ordinal = int(face.get("shape") or 1)
        shape_area[ordinal] = shape_area.get(ordinal, 0.0) + float(face.get("area") or 0.0)
        shape_box[ordinal] = _merge_box(shape_box.get(ordinal), _box_dict(face.get("bbox")))
        shape_faces[ordinal] = shape_faces.get(ordinal, 0) + 1
    for edge in edges:
        ordinal = int(edge.get("shape") or 1)
        shape_edges[ordinal] = shape_edges.get(ordinal, 0) + 1

    shape_rows = []
    for shape in shapes_meta:
        ordinal = int(shape.get("ord") or 1)
        box = shape_box.get(ordinal) or {"min": [0, 0, 0], "max": [0, 0, 0]}
        shape_rows.append([
            f"{_OCCURRENCE_ID}.s{ordinal}",
            _OCCURRENCE_ID,
            ordinal,
            str(shape.get("kind") or "shape"),
            None,
            None,
            box,
            [(box["min"][i] + box["max"][i]) / 2 for i in range(3)],
            shape_area.get(ordinal, 0.0),
            shape.get("volume"),
            0,
            shape_faces.get(ordinal, 0),
            0,
            shape_edges.get(ordinal, 0),
        ])

    face_rows = []
    for face in faces:
        ordinal = int(face["ord"])
        area = float(face.get("area") or 0.0)
        relevance = 100.0 * (max(area, 0.0) / total_area) ** 0.5
        if str(face.get("surfaceType") or "") in _ANALYTIC_SURFACES:
            relevance += 8.0
        if area < size_floor:
            relevance -= 45.0
        start, count = face_ranges[ordinal]
        face_rows.append([
            f"{_OCCURRENCE_ID}.f{ordinal}",
            _OCCURRENCE_ID,
            f"{_OCCURRENCE_ID}.s{int(face.get('shape') or 1)}",
            ordinal,
            str(face.get("surfaceType") or ""),
            area,
            face.get("center") or [0, 0, 0],
            face.get("normal"),
            _box_dict(face.get("bbox")) or {"min": [0, 0, 0], "max": [0, 0, 0]},
            start,
            count,
            max(0, min(100, round(relevance))),
            0,
            face.get("params"),
            0,
            0,
        ])

    edge_rows = []
    visibility_counts: dict[str, int] = {}
    for edge in edges:
        ordinal = int(edge["ord"])
        length = float(edge.get("length") or 0.0)
        visibility = str(edge.get("class") or "feature")
        visibility_counts[visibility] = visibility_counts.get(visibility, 0) + 1
        relevance = 100.0 * (max(length, 0.0) / total_length) ** 0.5
        if str(edge.get("curveType") or "") in _ANALYTIC_CURVES:
            relevance += 8.0
        if length < length_floor:
            relevance -= 45.0
        start, count = edge_ranges[ordinal]
        edge_rows.append([
            f"{_OCCURRENCE_ID}.e{ordinal}",
            _OCCURRENCE_ID,
            f"{_OCCURRENCE_ID}.s{int(edge.get('shape') or 1)}",
            ordinal,
            str(edge.get("curveType") or ""),
            length,
            edge.get("center") or [0, 0, 0],
            _box_dict(edge.get("bbox")) or {"min": [0, 0, 0], "max": [0, 0, 0]},
            start,
            count,
            max(0, min(100, round(relevance))),
            int(edge.get("flags") or 0),
            edge.get("params"),
            0,
            0,
            int(edge.get("adjacentFaceCount") or len(edge.get("faceOrds") or [])),
            str(edge.get("continuity") or ""),
            edge.get("dihedralDeg"),
            visibility,
            0,
            0,
        ])

    manifest: dict[str, Any] = {
        "schemaVersion": STEP_TOPOLOGY_SCHEMA_VERSION,
        "profile": "artifact",
        "entryKind": "part",
        "bbox": overall,
        "stats": {
            "occurrenceCount": 1,
            "leafOccurrenceCount": 1,
            "shapeCount": len(shape_rows),
            "faceCount": len(face_rows),
            "edgeCount": len(edge_rows),
        },
        "edgeRendering": {
            "visibilityClasses": ["feature", "tangent", "seam", "degenerate"],
            "visibilityClassCounts": dict(sorted(visibility_counts.items())),
        },
        "tables": {
            "occurrenceColumns": _OCCURRENCE_COLUMNS,
            "shapeColumns": _SHAPE_COLUMNS,
            "faceColumns": _FACE_COLUMNS,
            "edgeColumns": _EDGE_COLUMNS,
        },
        "occurrences": [[
            _OCCURRENCE_ID, "1", None, None, None, list(_IDENTITY), overall,
            0, len(shape_rows), 0, len(face_rows), 0, len(edge_rows),
        ]],
        "shapes": shape_rows,
        "faces": face_rows,
        "edges": edge_rows,
        "relations": {
            "faceEdgeRows": face_edge_rows,
            "edgeFaceRows": edge_face_rows,
        },
    }
    return SurfTopologyBundle(manifest=manifest, buffers=None)
