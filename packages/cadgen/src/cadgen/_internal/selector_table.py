"""The selector table of one component: every fact a ref is resolved by, minted once.

A ref someone copies (``#o1.2.f7``), the facts a tool reports for it and the
sets the viewer's connected selection grows it to (an edge's chain, a face's
tangent group) all come from this one table. It is derived from the exact
BREP and the component's ``.surf`` index -- the SURF already holds the exact
metrics, surface and curve types, parameters and edge classes; the BREP adds
what the SURF does not carry: the vertices, which edge ends where, and the
tangent directions the chains follow -- and stored beside the surface
(``cadgen.store.selectors``). The page joins its rows to the mesh's face and
edge tables by ordinal and composes ``occurrenceId + "." + localId``; it
mints nothing. The CLI reads the same table (``cadgen.assembly_lookup``).

Ordinals are the ``TopExp.MapShapes_s`` order the SURF and the mesh share, so
a face row, its triangles and its ref name one face.
"""

from __future__ import annotations

import json
import math
from typing import Any, Mapping

from cadgen._internal.glb_topology import (
    STEP_EDGE_FLAGS,
    STEP_EDGE_RENDER_VISIBILITY_CLASSES,
    STEP_EDGE_VISIBILITY_CLASSES,
    STEP_TOPOLOGY_EDGE_ANGULAR_TOLERANCE_DEG,
    STEP_TOPOLOGY_EDGE_CLASSIFICATION_ALGORITHM,
    STEP_TOPOLOGY_EDGE_SAMPLE_COUNT,
)

# The table's wire schema, read by the page (selectorTable.js) and the CLI: a
# column added, removed or given a new meaning bumps it. The stored entry's
# scheme (cadgen.store.selectors.SELECTOR_SCHEME) is bumped with it, and for
# any change in what the same columns hold.
SELECTOR_TABLE_SCHEMA_VERSION = 1
OCCURRENCE_ID = "o1"
_IDENTITY = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]

OCCURRENCE_COLUMNS = [
    "id", "path", "name", "sourceName", "parentId", "transform", "bbox",
    "shapeStart", "shapeCount", "faceStart", "faceCount", "edgeStart", "edgeCount",
    "vertexStart", "vertexCount",
]
SHAPE_COLUMNS = [
    "id", "localId", "occurrenceId", "ordinal", "kind", "name", "sourceName", "bbox",
    "center", "area", "volume", "faceStart", "faceCount", "edgeStart", "edgeCount",
]
FACE_COLUMNS = [
    "id", "localId", "occurrenceId", "shapeId", "ordinal", "surfaceType", "area",
    "center", "normal", "bbox", "edgeStart", "edgeCount", "relevance", "flags",
    "params", "tangentGroup",
]
EDGE_COLUMNS = [
    "id", "localId", "occurrenceId", "shapeId", "ordinal", "curveType", "length",
    "center", "bbox", "faceStart", "faceCount", "vertexStart", "vertexCount",
    "relevance", "flags", "params", "adjacentFaceCount", "continuity",
    "dihedralDeg", "visibilityClass", "chain",
]
VERTEX_COLUMNS = [
    "id", "localId", "occurrenceId", "shapeId", "ordinal", "center", "bbox",
    "edgeStart", "edgeCount",
]
# A face with no area is a ref nothing can pick or measure; the bit is the
# edge table's, so one vocabulary reads both.
FACE_FLAG_NOT_REFERENCEABLE = STEP_EDGE_FLAGS["NOT_REFERENCEABLE"]
_EDGE_UNREFERENCEABLE = STEP_EDGE_FLAGS["DEGENERATE"] | STEP_EDGE_FLAGS["NOT_REFERENCEABLE"]
_ANALYTIC_SURFACES = {"plane", "cylinder", "cone", "sphere", "torus"}
_ANALYTIC_CURVES = {"line", "circle", "ellipse"}
# Two edge ends meeting at a vertex continue one chain when their tangents are
# opposed within this angle: the one aligned continuation at a branch.
CHAIN_ALIGNMENT_DEG = 3.0
_CHAIN_ALIGNMENT_COS = -math.cos(math.radians(CHAIN_ALIGNMENT_DEG))


def _box(values: list[float] | None) -> dict[str, list[float]] | None:
    if not values or len(values) != 6:
        return None
    return {"min": [float(v) for v in values[:3]], "max": [float(v) for v in values[3:]]}


def _merge(target: dict[str, list[float]] | None, source: dict[str, list[float]] | None):
    if source is None:
        return target
    if target is None:
        return {"min": list(source["min"]), "max": list(source["max"])}
    for axis in range(3):
        target["min"][axis] = min(target["min"][axis], source["min"][axis])
        target["max"][axis] = max(target["max"][axis], source["max"][axis])
    return target


def _zero_box() -> dict[str, list[float]]:
    return {"min": [0.0, 0.0, 0.0], "max": [0.0, 0.0, 0.0]}


def _relevance(measure: float, total: float, analytic: bool, floor: float) -> int:
    value = 100.0 * (max(measure, 0.0) / total) ** 0.5
    if analytic:
        value += 8.0
    if measure < floor:
        value -= 45.0
    return max(0, min(100, round(value)))


class _Groups:
    """Union-find over ordinals; ``ids()`` numbers each group by its smallest member."""

    def __init__(self, ordinals: list[int]) -> None:
        self.parent = {ordinal: ordinal for ordinal in ordinals}

    def find(self, ordinal: int) -> int:
        root = ordinal
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[ordinal] != root:
            self.parent[ordinal], ordinal = root, self.parent[ordinal]
        return root

    def union(self, a: int, b: int) -> None:
        a, b = self.find(a), self.find(b)
        if a != b:
            self.parent[max(a, b)] = min(a, b)

    def ids(self) -> dict[int, int]:
        roots = sorted({self.find(ordinal) for ordinal in self.parent})
        number = {root: index + 1 for index, root in enumerate(roots)}
        return {ordinal: number[self.find(ordinal)] for ordinal in self.parent}


def _unit(vector: tuple[float, float, float]) -> tuple[float, float, float] | None:
    length = math.sqrt(sum(v * v for v in vector))
    if length <= 1e-12 or not math.isfinite(length):
        return None
    return (vector[0] / length, vector[1] / length, vector[2] / length)


def _vertex_facts(shape, edges: list[dict[str, Any]]):
    """The BREP's part of the table: vertex ordinals and positions, each edge's
    end vertices in curve-parameter order, and the unit tangent INTO each
    non-degenerate open edge at each of its ends."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_VERTEX
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Pnt, gp_Vec

    from cadgen._internal.entity_ordinals import shape_entities
    from cadgen._internal.step_scene_loader import _shape_hash

    vertex_map = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_VERTEX, vertex_map)
    edge_map = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_EDGE, edge_map)
    if edge_map.Extent() != len(edges):
        raise ValueError("the SURF index does not describe this shape: its edge count differs")
    vertex_ord = {_shape_hash(vertex_map.FindKey(i)): i for i in range(1, vertex_map.Extent() + 1)}

    # Solid membership, decided as the SURF decides a face's or edge's.
    shape_by_vertex: dict[int, int] = {}
    for ordinal, sub in enumerate(shape_entities(shape), start=1):
        sub_vertices = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(sub, TopAbs_VERTEX, sub_vertices)
        for i in range(1, sub_vertices.Extent() + 1):
            found = vertex_ord.get(_shape_hash(sub_vertices.FindKey(i)))
            if found is not None:
                shape_by_vertex.setdefault(found, ordinal)

    positions = {}
    for i in range(1, vertex_map.Extent() + 1):
        point = BRep_Tool.Pnt_s(TopoDS.Vertex_s(vertex_map.FindKey(i)))
        positions[i] = [point.X(), point.Y(), point.Z()]

    ends: dict[int, list[int]] = {}
    tangents: dict[int, tuple[tuple[float, float, float] | None, tuple[float, float, float] | None]] = {}
    for ordinal in range(1, edge_map.Extent() + 1):
        edge = TopoDS.Edge_s(edge_map.FindKey(ordinal))
        first = vertex_ord.get(_shape_hash(TopExp.FirstVertex_s(edge, False)))
        last = vertex_ord.get(_shape_hash(TopExp.LastVertex_s(edge, False)))
        ends[ordinal] = [v for v in (first, last) if v is not None]
        if BRep_Tool.Degenerated_s(edge) or first is None or last is None or first == last:
            continue
        try:
            curve = BRepAdaptor_Curve(edge)
            point, vector = gp_Pnt(), gp_Vec()
            curve.D1(curve.FirstParameter(), point, vector)
            into_first = _unit((vector.X(), vector.Y(), vector.Z()))
            curve.D1(curve.LastParameter(), point, vector)
            into_last = _unit((-vector.X(), -vector.Y(), -vector.Z()))
        except Exception:
            continue
        tangents[ordinal] = (into_first, into_last)
    return positions, shape_by_vertex, ends, tangents


def _edge_chains(edges: list[dict[str, Any]], ends: dict[int, list[int]], tangents) -> dict[int, int | None]:
    """Each edge's chain: the connected set a pick of one edge grows to.

    Two edges continue each other at a shared vertex when they bound a common
    face in the same solid and, where more than one edge could continue, when
    exactly one of them runs on through the vertex (tangents opposed within
    ``CHAIN_ALIGNMENT_DEG``) -- and only when each is the other's choice. A
    degenerate edge is in no chain; a closed edge is a chain of its own.
    """
    by_ord = {int(edge["ord"]): edge for edge in edges}
    faces_of = {ordinal: set(int(f) for f in (edge.get("faceOrds") or [])) for ordinal, edge in by_ord.items()}
    shape_of = {ordinal: int(edge.get("shape") or 1) for ordinal, edge in by_ord.items()}
    # (edge, end) -> vertex, and the ends at each vertex.
    at_vertex: dict[int, list[tuple[int, int]]] = {}
    for ordinal, pair in tangents.items():
        for end, vertex in enumerate(ends[ordinal]):
            if pair[end] is None:
                continue
            at_vertex.setdefault(vertex, []).append((ordinal, end))

    def dot(a, b) -> float:
        return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

    choice: dict[tuple[int, int], tuple[int, int]] = {}
    for vertex, here in at_vertex.items():
        for ordinal, end in here:
            candidates = [
                (other, other_end) for other, other_end in here
                if other != ordinal and shape_of[other] == shape_of[ordinal] and faces_of[other] & faces_of[ordinal]
            ]
            if len(candidates) > 1:
                direction = tangents[ordinal][end]
                candidates = [
                    (other, other_end) for other, other_end in candidates
                    if dot(direction, tangents[other][other_end]) < _CHAIN_ALIGNMENT_COS
                ]
            if len(candidates) == 1:
                choice[(ordinal, end)] = candidates[0]
    chained = [ordinal for ordinal, edge in by_ord.items() if not int(edge.get("flags") or 0) & STEP_EDGE_FLAGS["DEGENERATE"]]
    groups = _Groups(chained)
    for here, there in choice.items():
        if choice.get(there) == here and here[0] in groups.parent and there[0] in groups.parent:
            groups.union(here[0], there[0])
    ids = groups.ids()
    return {ordinal: ids.get(ordinal) for ordinal in by_ord}


def _tangent_groups(faces: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[int, int]:
    """Each face's tangent group: faces joined across tangent-class edges of one solid."""
    shape_of = {int(face["ord"]): int(face.get("shape") or 1) for face in faces}
    groups = _Groups(list(shape_of))
    for edge in edges:
        if str(edge.get("class") or "") != STEP_EDGE_VISIBILITY_CLASSES["TANGENT"]:
            continue
        adjacent = sorted({int(f) for f in (edge.get("faceOrds") or [])})
        if len(adjacent) != 2 or adjacent[0] not in shape_of or adjacent[1] not in shape_of:
            continue
        if shape_of[adjacent[0]] != shape_of[adjacent[1]]:
            continue
        groups.union(adjacent[0], adjacent[1])
    return groups.ids()


def capabilities() -> dict[str, Any]:
    return {
        "edgeClassification": {
            "algorithm": STEP_TOPOLOGY_EDGE_CLASSIFICATION_ALGORITHM,
            "angularToleranceDeg": STEP_TOPOLOGY_EDGE_ANGULAR_TOLERANCE_DEG,
            "samples": STEP_TOPOLOGY_EDGE_SAMPLE_COUNT,
        },
        # The mesh carries the CAD edge lines, so the page's own topology line pass stays off.
        "surfaceEdgeRendering": {
            "algorithm": "surf-edge-lines-v1",
            "visibilityClasses": list(STEP_EDGE_RENDER_VISIBILITY_CLASSES),
        },
        "connectedSelection": {"edgeChain": {"alignmentDeg": CHAIN_ALIGNMENT_DEG}, "tangentFaces": True},
    }


def build_selector_table(shape, index: Mapping[str, Any]) -> dict[str, Any]:
    """The table of one unlocated component: ``shape`` (a ``TopoDS_Shape``) and the
    SURF index extracted from it (``surface_extract.read_surf``)."""
    faces = list(index.get("faces") or [])
    edges = list(index.get("edges") or [])
    shapes_meta = list(index.get("shapes") or [{"ord": 1, "kind": "shape", "volume": None}])
    face_row = {int(face["ord"]): row for row, face in enumerate(faces)}
    edge_row = {int(edge["ord"]): row for row, edge in enumerate(edges)}
    positions, shape_by_vertex, ends, tangents = _vertex_facts(shape, edges)
    vertex_ordinals = sorted(positions)
    vertex_row = {ordinal: row for row, ordinal in enumerate(vertex_ordinals)}
    chains = _edge_chains(edges, ends, tangents)
    tangent_groups = _tangent_groups(faces, edges)

    overall = None
    for face in faces:
        overall = _merge(overall, _box(face.get("bbox")))
    for ordinal in vertex_ordinals:
        point = positions[ordinal]
        overall = _merge(overall, {"min": list(point), "max": list(point)})
    if overall is None:
        overall = _zero_box()
    diagonal = max(math.sqrt(sum((overall["max"][i] - overall["min"][i]) ** 2 for i in range(3))), 1e-9)
    size_floor = max(diagonal * diagonal * 1e-6, 1e-12)
    length_floor = max(diagonal * 1e-5, 1e-12)
    total_area = max(sum(float(face.get("area") or 0.0) for face in faces), 1e-12)
    total_length = max(sum(float(edge.get("length") or 0.0) for edge in edges), 1e-12)

    face_edge_rows: list[int] = []
    face_edges: dict[int, tuple[int, int]] = {}
    for face in faces:
        start = len(face_edge_rows)
        seen: set[int] = set()
        for loop in face.get("loops") or []:
            for pcurve in loop:
                row = edge_row.get(int(pcurve.get("edgeOrd") or 0))
                if row is not None and row not in seen:
                    seen.add(row)
                    face_edge_rows.append(row)
        face_edges[int(face["ord"])] = (start, len(face_edge_rows) - start)
    edge_face_rows: list[int] = []
    edge_faces: dict[int, tuple[int, int]] = {}
    edge_vertex_rows: list[int] = []
    edge_vertices: dict[int, tuple[int, int]] = {}
    edges_at_vertex: dict[int, list[int]] = {ordinal: [] for ordinal in vertex_ordinals}
    for edge in edges:
        ordinal = int(edge["ord"])
        start = len(edge_face_rows)
        for face_ord in edge.get("faceOrds") or []:
            row = face_row.get(int(face_ord))
            if row is not None:
                edge_face_rows.append(row)
        edge_faces[ordinal] = (start, len(edge_face_rows) - start)
        start = len(edge_vertex_rows)
        for vertex in dict.fromkeys(ends.get(ordinal, [])):
            edge_vertex_rows.append(vertex_row[vertex])
            edges_at_vertex[vertex].append(edge_row[ordinal])
        edge_vertices[ordinal] = (start, len(edge_vertex_rows) - start)
    vertex_edge_rows: list[int] = []
    vertex_edges: dict[int, tuple[int, int]] = {}
    for ordinal in vertex_ordinals:
        start = len(vertex_edge_rows)
        vertex_edge_rows.extend(sorted(edges_at_vertex[ordinal]))
        vertex_edges[ordinal] = (start, len(vertex_edge_rows) - start)

    shape_area: dict[int, float] = {}
    shape_box: dict[int, dict | None] = {}
    counts = {"face": {}, "edge": {}}
    for face in faces:
        ordinal = int(face.get("shape") or 1)
        shape_area[ordinal] = shape_area.get(ordinal, 0.0) + float(face.get("area") or 0.0)
        shape_box[ordinal] = _merge(shape_box.get(ordinal), _box(face.get("bbox")))
        counts["face"][ordinal] = counts["face"].get(ordinal, 0) + 1
    for edge in edges:
        ordinal = int(edge.get("shape") or 1)
        counts["edge"][ordinal] = counts["edge"].get(ordinal, 0) + 1
    shape_rows = []
    for shape_meta in shapes_meta:
        ordinal = int(shape_meta.get("ord") or 1)
        box = shape_box.get(ordinal) or _zero_box()
        shape_rows.append([
            f"{OCCURRENCE_ID}.s{ordinal}", f"s{ordinal}", OCCURRENCE_ID, ordinal,
            str(shape_meta.get("kind") or "shape"), None, None, box,
            [(box["min"][i] + box["max"][i]) / 2 for i in range(3)],
            shape_area.get(ordinal, 0.0), shape_meta.get("volume"),
            0, counts["face"].get(ordinal, 0), 0, counts["edge"].get(ordinal, 0),
        ])

    face_rows = []
    for face in faces:
        ordinal = int(face["ord"])
        area = float(face.get("area") or 0.0)
        referenceable = area > 1e-12
        surface_type = str(face.get("surfaceType") or "")
        start, count = face_edges[ordinal]
        face_rows.append([
            f"{OCCURRENCE_ID}.f{ordinal}", f"f{ordinal}", OCCURRENCE_ID,
            f"{OCCURRENCE_ID}.s{int(face.get('shape') or 1)}", ordinal, surface_type, area,
            face.get("center") or [0.0, 0.0, 0.0], face.get("normal"),
            _box(face.get("bbox")) or _zero_box(), start, count,
            _relevance(area, total_area, surface_type in _ANALYTIC_SURFACES, size_floor) if referenceable else 0,
            0 if referenceable else FACE_FLAG_NOT_REFERENCEABLE,
            face.get("params"), tangent_groups[ordinal],
        ])

    edge_rows = []
    visibility_counts: dict[str, int] = {}
    for edge in edges:
        ordinal = int(edge["ord"])
        length = float(edge.get("length") or 0.0)
        flags = int(edge.get("flags") or 0)
        referenceable = not flags & _EDGE_UNREFERENCEABLE
        visibility = str(edge.get("class") or STEP_EDGE_VISIBILITY_CLASSES["FEATURE"])
        visibility_counts[visibility] = visibility_counts.get(visibility, 0) + 1
        curve_type = str(edge.get("curveType") or "")
        face_start, face_count = edge_faces[ordinal]
        vertex_start, vertex_count = edge_vertices[ordinal]
        params = edge.get("params")
        curve = edge.get("curve") if isinstance(edge.get("curve"), Mapping) else None
        if curve is not None and curve.get("kind") == "circle":
            span = curve.get("range")
            if isinstance(span, list) and len(span) == 2 and all(isinstance(v, (int, float)) for v in span):
                params = {**(params or {}), "sweepRadians": abs(float(span[1]) - float(span[0]))}
        edge_rows.append([
            f"{OCCURRENCE_ID}.e{ordinal}", f"e{ordinal}", OCCURRENCE_ID,
            f"{OCCURRENCE_ID}.s{int(edge.get('shape') or 1)}", ordinal, curve_type, length,
            edge.get("center") or [0.0, 0.0, 0.0], _box(edge.get("bbox")) or _zero_box(),
            face_start, face_count, vertex_start, vertex_count,
            _relevance(length, total_length, curve_type in _ANALYTIC_CURVES, length_floor) if referenceable else 0,
            flags, params,
            int(edge.get("adjacentFaceCount") or len(edge.get("faceOrds") or [])),
            str(edge.get("continuity") or ""), edge.get("dihedralDeg"), visibility, chains[ordinal],
        ])

    vertex_rows = []
    for ordinal in vertex_ordinals:
        point = positions[ordinal]
        start, count = vertex_edges[ordinal]
        vertex_rows.append([
            f"{OCCURRENCE_ID}.v{ordinal}", f"v{ordinal}", OCCURRENCE_ID,
            f"{OCCURRENCE_ID}.s{shape_by_vertex.get(ordinal, 1)}", ordinal, list(point),
            {"min": list(point), "max": list(point)}, start, count,
        ])

    return {
        "schemaVersion": SELECTOR_TABLE_SCHEMA_VERSION,
        "profile": "artifact",
        "entryKind": "part",
        "capabilities": capabilities(),
        "bbox": overall,
        "stats": {
            "occurrenceCount": 1,
            "leafOccurrenceCount": 1,
            "shapeCount": len(shape_rows),
            "faceCount": len(face_rows),
            "edgeCount": len(edge_rows),
            "vertexCount": len(vertex_rows),
        },
        "edgeRendering": {
            "visibilityClasses": list(STEP_EDGE_RENDER_VISIBILITY_CLASSES),
            "visibilityClassCounts": dict(sorted(visibility_counts.items())),
        },
        "tables": {
            "occurrenceColumns": OCCURRENCE_COLUMNS,
            "shapeColumns": SHAPE_COLUMNS,
            "faceColumns": FACE_COLUMNS,
            "edgeColumns": EDGE_COLUMNS,
            "vertexColumns": VERTEX_COLUMNS,
        },
        "occurrences": [[
            OCCURRENCE_ID, "1", None, None, None, list(_IDENTITY), overall,
            0, len(shape_rows), 0, len(face_rows), 0, len(edge_rows), 0, len(vertex_rows),
        ]],
        "shapes": shape_rows,
        "faces": face_rows,
        "edges": edge_rows,
        "vertices": vertex_rows,
        "relations": {
            "faceEdgeRows": face_edge_rows,
            "edgeFaceRows": edge_face_rows,
            "edgeVertexRows": edge_vertex_rows,
            "vertexEdgeRows": vertex_edge_rows,
        },
    }


def selector_table_bytes(table: Mapping[str, Any]) -> bytes:
    """The table as the store holds and the page reads it: compact JSON, no NaN."""
    return json.dumps(table, separators=(",", ":"), allow_nan=False).encode("utf-8")


def read_selector_table(payload: bytes) -> dict[str, Any]:
    """A stored table, checked to be one of this schema with consistent tables.
    ValueError for anything else."""
    try:
        table = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError("invalid selector table JSON") from error
    if type(table) is not dict or table.get("schemaVersion") != SELECTOR_TABLE_SCHEMA_VERSION:
        raise ValueError("selector table is not this cadgen's schema")
    columns = table.get("tables")
    if type(columns) is not dict:
        raise ValueError("selector table lacks its columns")
    expected = {
        "occurrences": ("occurrenceColumns", OCCURRENCE_COLUMNS), "shapes": ("shapeColumns", SHAPE_COLUMNS),
        "faces": ("faceColumns", FACE_COLUMNS), "edges": ("edgeColumns", EDGE_COLUMNS),
        "vertices": ("vertexColumns", VERTEX_COLUMNS),
    }
    for name, (column_key, declared) in expected.items():
        rows = table.get(name)
        if columns.get(column_key) != declared or type(rows) is not list or any(
            type(row) is not list or len(row) != len(declared) for row in rows
        ):
            raise ValueError(f"selector table {name} rows do not match their columns")
    ordinal = {"shapes": 3, "faces": 4, "edges": 4, "vertices": 4}
    for name, column in ordinal.items():
        if name != "shapes" and [row[column] for row in table[name]] != list(range(1, len(table[name]) + 1)):
            raise ValueError(f"selector table {name} ordinals are not contiguous")
    stats = table.get("stats")
    if type(stats) is not dict or any(
        stats.get(f"{kind}Count") != len(table[name]) for kind, name in
        (("shape", "shapes"), ("face", "faces"), ("edge", "edges"), ("vertex", "vertices"))
    ):
        raise ValueError("selector table counts do not match its rows")
    relations = table.get("relations")
    if type(relations) is not dict or any(
        type(relations.get(name)) is not list or any(type(v) is not int or v < 0 or v >= len(table[target]) for v in relations[name])
        for name, target in (("faceEdgeRows", "edges"), ("edgeFaceRows", "faces"),
                             ("edgeVertexRows", "vertices"), ("vertexEdgeRows", "edges"))
    ):
        raise ValueError("selector table relations do not index its rows")
    return table
