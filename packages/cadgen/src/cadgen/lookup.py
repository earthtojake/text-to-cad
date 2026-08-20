from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from cadgen import cad_ref_syntax as syntax


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


def _buffer_rows(buffers: Mapping[str, Any] | None, view_name: object) -> list[int]:
    if not isinstance(view_name, str) or buffers is None:
        return []
    values = buffers.get(view_name)
    if values is None:
        return []
    try:
        return [int(value) for value in values]
    except (TypeError, ValueError):
        return []


def _relations(manifest: dict[str, Any], buffers: Mapping[str, Any] | None = None) -> dict[str, list[int]]:
    relations = manifest.get("relations")
    if not isinstance(relations, dict):
        return {"faceEdgeRows": [], "edgeFaceRows": [], "edgeVertexRows": [], "vertexEdgeRows": []}

    def rows(name: str) -> list[int]:
        inline = relations.get(name)
        if isinstance(inline, list):
            try:
                return [int(value) for value in inline]
            except (TypeError, ValueError):
                return []
        return _buffer_rows(buffers, relations.get(f"{name}View"))

    return {
        "faceEdgeRows": rows("faceEdgeRows"),
        "edgeFaceRows": rows("edgeFaceRows"),
        "edgeVertexRows": rows("edgeVertexRows"),
        "vertexEdgeRows": rows("vertexEdgeRows"),
    }


@dataclass(frozen=True)
class SelectorIndex:
    manifest: dict[str, Any]
    occurrences: list[dict[str, Any]]
    shapes: list[dict[str, Any]]
    faces: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    vertices: list[dict[str, Any]]
    relations: dict[str, list[int]]
    occurrence_by_id: dict[str, dict[str, Any]]
    shape_by_id: dict[str, dict[str, Any]]
    face_by_id: dict[str, dict[str, Any]]
    edge_by_id: dict[str, dict[str, Any]]
    vertex_by_id: dict[str, dict[str, Any]]
    single_occurrence_id: str
    leaf_occurrence_ids: tuple[str, ...]
    # Label aliases for this index's occurrences, filled in by
    # cadgen.label_refs.attach_label_aliases once the row set is final. Empty until then, and
    # empty forever for inputs whose parts carry no usable labels -- those stay reachable by
    # their numeric ids, exactly as before labels existed.
    label_aliases: dict[str, Any] = field(default_factory=dict)


def build_selector_index(manifest: dict[str, Any], *, buffers: Mapping[str, Any] | None = None) -> SelectorIndex:
    occurrences = _table_rows(manifest, "occurrences", "occurrenceColumns")
    shapes = _table_rows(manifest, "shapes", "shapeColumns")
    faces = _table_rows(manifest, "faces", "faceColumns")
    edges = _table_rows(manifest, "edges", "edgeColumns")
    vertices = _table_rows(manifest, "vertices", "vertexColumns")
    relations = _relations(manifest, buffers=buffers)

    occurrence_by_id = {str(row.get("id")): row for row in occurrences if row.get("id")}
    shape_by_id = {str(row.get("id")): row for row in shapes if row.get("id")}
    face_by_id = {str(row.get("id")): row for row in faces if row.get("id")}
    edge_by_id = {str(row.get("id")): row for row in edges if row.get("id")}
    vertex_by_id = {str(row.get("id")): row for row in vertices if row.get("id")}

    leaf_occurrence_ids = tuple(
        sorted(
            {
                str(row.get("occurrenceId"))
                for row in shapes
                if isinstance(row.get("occurrenceId"), str) and row.get("occurrenceId")
            }
        )
    )
    single_occurrence_id = leaf_occurrence_ids[0] if len(leaf_occurrence_ids) == 1 else ""

    return SelectorIndex(
        manifest=manifest,
        occurrences=occurrences,
        shapes=shapes,
        faces=faces,
        edges=edges,
        vertices=vertices,
        relations=relations,
        occurrence_by_id=occurrence_by_id,
        shape_by_id=shape_by_id,
        face_by_id=face_by_id,
        edge_by_id=edge_by_id,
        vertex_by_id=vertex_by_id,
        single_occurrence_id=single_occurrence_id,
        leaf_occurrence_ids=leaf_occurrence_ids,
    )


def entry_summary(index: SelectorIndex) -> dict[str, Any]:
    stats = index.manifest.get("stats") if isinstance(index.manifest.get("stats"), dict) else {}
    bbox = index.manifest.get("bbox") if isinstance(index.manifest.get("bbox"), dict) else None
    return {
        "kind": "part",
        "occurrenceCount": int(stats.get("occurrenceCount") or len(index.occurrences)),
        "leafOccurrenceCount": int(stats.get("leafOccurrenceCount") or len(index.leaf_occurrence_ids)),
        "shapeCount": int(stats.get("shapeCount") or len(index.shapes)),
        "faceCount": int(stats.get("faceCount") or len(index.faces)),
        "edgeCount": int(stats.get("edgeCount") or len(index.edges)),
        "vertexCount": int(stats.get("vertexCount") or len(index.vertices)),
        "bounds": bbox,
    }


def canonicalize_selector(raw_selector: str, index: SelectorIndex) -> str | None:
    parsed = syntax.parse_selector(raw_selector)
    if parsed is None:
        return None
    if parsed.label:
        # A label names an occurrence; turn it into one before the numeric logic below runs, so
        # every caller downstream sees the same canonical form it always has.
        from cadgen.label_refs import LabelResolutionError, resolve_label_selectors

        try:
            resolved = resolve_label_selectors([raw_selector], getattr(index, "label_aliases", None))
        except LabelResolutionError:
            return None
        parsed = syntax.parse_selector(resolved[0]) if resolved else None
        if parsed is None:
            return None
    if parsed.selector_type == "opaque":
        return parsed.canonical
    if parsed.occurrence_id:
        return parsed.canonical
    if not index.single_occurrence_id:
        return None
    if parsed.selector_type == "shape":
        return f"{index.single_occurrence_id}.s{parsed.ordinal}"
    if parsed.selector_type == "face":
        return f"{index.single_occurrence_id}.f{parsed.ordinal}"
    if parsed.selector_type == "edge":
        return f"{index.single_occurrence_id}.e{parsed.ordinal}"
    if parsed.selector_type == "vertex":
        return f"{index.single_occurrence_id}.v{parsed.ordinal}"
    return parsed.canonical


def display_selector(selector: str, index: SelectorIndex) -> str:
    if not selector or not index.single_occurrence_id:
        return selector
    prefix = f"{index.single_occurrence_id}."
    if selector.startswith(prefix):
        tail = selector[len(prefix) :]
        if tail.startswith(("s", "f", "e", "v")):
            return tail
    return selector


def lookup_selector(selector: str, index: SelectorIndex) -> tuple[str, dict[str, Any]] | None:
    normalized = canonicalize_selector(selector, index)
    if not normalized:
        return None
    if normalized in index.occurrence_by_id:
        return "occurrence", index.occurrence_by_id[normalized]
    if normalized in index.shape_by_id:
        return "shape", index.shape_by_id[normalized]
    if normalized in index.face_by_id:
        return "face", index.face_by_id[normalized]
    if normalized in index.edge_by_id:
        return "edge", index.edge_by_id[normalized]
    if normalized in index.vertex_by_id:
        return "vertex", index.vertex_by_id[normalized]
    return None


def face_adjacent_edge_selectors(face_row: dict[str, Any], index: SelectorIndex) -> list[str]:
    start = int(face_row.get("edgeStart") or 0)
    count = int(face_row.get("edgeCount") or 0)
    selectors: list[str] = []
    for edge_row_index in index.relations.get("faceEdgeRows", [])[start : start + count]:
        if 0 <= int(edge_row_index) < len(index.edges):
            selectors.append(str(index.edges[int(edge_row_index)].get("id")))
    return selectors


def edge_adjacent_face_selectors(edge_row: dict[str, Any], index: SelectorIndex) -> list[str]:
    start = int(edge_row.get("faceStart") or 0)
    count = int(edge_row.get("faceCount") or 0)
    selectors: list[str] = []
    for face_row_index in index.relations.get("edgeFaceRows", [])[start : start + count]:
        if 0 <= int(face_row_index) < len(index.faces):
            selectors.append(str(index.faces[int(face_row_index)].get("id")))
    return selectors


def edge_adjacent_vertex_selectors(edge_row: dict[str, Any], index: SelectorIndex) -> list[str]:
    start = int(edge_row.get("vertexStart") or 0)
    count = int(edge_row.get("vertexCount") or 0)
    selectors: list[str] = []
    for vertex_row_index in index.relations.get("edgeVertexRows", [])[start : start + count]:
        if 0 <= int(vertex_row_index) < len(index.vertices):
            selectors.append(str(index.vertices[int(vertex_row_index)].get("id")))
    return selectors


def vertex_adjacent_edge_selectors(vertex_row: dict[str, Any], index: SelectorIndex) -> list[str]:
    start = int(vertex_row.get("edgeStart") or 0)
    count = int(vertex_row.get("edgeCount") or 0)
    selectors: list[str] = []
    for edge_row_index in index.relations.get("vertexEdgeRows", [])[start : start + count]:
        if 0 <= int(edge_row_index) < len(index.edges):
            selectors.append(str(index.edges[int(edge_row_index)].get("id")))
    return selectors


def vertex_adjacent_face_selectors(vertex_row: dict[str, Any], index: SelectorIndex) -> list[str]:
    selectors: list[str] = []
    seen: set[str] = set()
    for edge_selector in vertex_adjacent_edge_selectors(vertex_row, index):
        edge_row = index.edge_by_id.get(edge_selector)
        if edge_row is None:
            continue
        for face_selector in edge_adjacent_face_selectors(edge_row, index):
            if face_selector not in seen:
                seen.add(face_selector)
                selectors.append(face_selector)
    return selectors


def topology_payload(index: SelectorIndex) -> dict[str, list[str]]:
    return {
        "occurrences": [display_selector(str(row.get("id")), index) for row in index.occurrences if row.get("id")],
        "shapes": [display_selector(str(row.get("id")), index) for row in index.shapes if row.get("id")],
        "faces": [display_selector(str(row.get("id")), index) for row in index.faces if row.get("id")],
        "edges": [display_selector(str(row.get("id")), index) for row in index.edges if row.get("id")],
        "vertices": [display_selector(str(row.get("id")), index) for row in index.vertices if row.get("id")],
    }
