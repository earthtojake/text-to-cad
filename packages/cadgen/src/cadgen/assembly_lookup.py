"""Selector resolution across a component package's INSTANCE TREE.

An assembly is described by two artifacts that answer different questions, and until this module
they disagreed about what an occurrence is:

* ``assembly.json`` -- the package descriptor. Knows the instance tree: 160 occurrences for
  ``tom_v2``, ids ``o1.1.1``/``o1.12``/``o1.11.7.1.1.1.2``, each naming a component and carrying
  its placement. This is what ``snapshot --mode list`` enumerates and what the CAD Viewer hands
  the user when they click a part.
* ``topology.glb`` -- the whole-assembly selector sidecar, extracted from the COMPOSED compound.
  A compound has no instance tree, so it flattens to ONE occurrence (``o1``) holding every solid:
  162 shapes, 13866 faces, in a single namespace ``o1.s1``/``o1.f19``.

``lookup.build_selector_index`` reads the second. So every ref the first hands out -- every ref a
user can actually pick -- resolved to an error, and ``inspect refs --facts`` reported
``occurrenceCount: 1`` for a 160-part assembly (issue 0b in tom-cad's FEEDBACK.md). The user's
workaround was to re-identify each face by area and position in the owning part's own namespace,
which is guesswork whenever a part appears at more than one occurrence.

The fix needs no new data. Each occurrence names a component, and each ``components/<hash>.glb``
already carries that part's own complete topology -- the yoke's component has its 66 faces sitting
there unused. So this module ADDS the instance-tree occurrences to the flat index rather than
replacing it: ``#o1.f19`` keeps resolving exactly as before, and ``#o1.12`` starts resolving.

Coordinates are WORLD AT REST: occurrence transforms applied, parameter-sidecar poses not.
That is the frame the viewer shows when the ref is picked and the frame ``snapshot --mode list``
already reports its bounds in, so the two tools now agree. Reporting component-local coordinates
instead would recreate the frame confusion that FEEDBACK.md P2 documents costing a wrong edit and
a full revert.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from cadgen.lookup import SelectorIndex

COMPONENTS_DIRNAME = "components"


def _identity() -> list[float]:
    return [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]


def _matrix(raw: object) -> list[float]:
    """A row-major 4x4 as 16 floats, or identity when the descriptor omits/mangles it."""
    if not isinstance(raw, (list, tuple)) or len(raw) < 16:
        return _identity()
    try:
        return [float(value) for value in raw[:16]]
    except (TypeError, ValueError):
        return _identity()


def transform_point(matrix: list[float], point: object) -> list[float] | None:
    if not isinstance(point, (list, tuple)) or len(point) < 3:
        return None
    try:
        x, y, z = (float(point[0]), float(point[1]), float(point[2]))
    except (TypeError, ValueError):
        return None
    return [
        matrix[0] * x + matrix[1] * y + matrix[2] * z + matrix[3],
        matrix[4] * x + matrix[5] * y + matrix[6] * z + matrix[7],
        matrix[8] * x + matrix[9] * y + matrix[10] * z + matrix[11],
    ]


def transform_bbox(matrix: list[float], bbox: object) -> dict[str, list[float]] | None:
    """Transform an axis-aligned box by transforming its eight CORNERS and re-deriving min/max.

    Transforming min and max alone is wrong under any rotation: it produces a box with the right
    diagonal and the wrong extent, and every occurrence in a posed assembly is rotated.
    """
    if not isinstance(bbox, Mapping):
        return None
    low = bbox.get("min")
    high = bbox.get("max")
    if not isinstance(low, (list, tuple)) or not isinstance(high, (list, tuple)):
        return None
    if len(low) < 3 or len(high) < 3:
        return None
    try:
        lows = [float(value) for value in low[:3]]
        highs = [float(value) for value in high[:3]]
    except (TypeError, ValueError):
        return None
    corners = [
        transform_point(matrix, [x, y, z])
        for x in (lows[0], highs[0])
        for y in (lows[1], highs[1])
        for z in (lows[2], highs[2])
    ]
    placed = [corner for corner in corners if corner is not None]
    if not placed:
        return None
    return {
        "min": [min(corner[axis] for corner in placed) for axis in range(3)],
        "max": [max(corner[axis] for corner in placed) for axis in range(3)],
    }


# How each entity field moves under a rigid placement. Classified by KEY, because the schema is
# uniform across surface and curve types: a plane and a cylinder both carry `origin`/`axis`, a
# line carries `origin`/`direction`, and a cylinder's `radius` is a length that a rigid transform
# does not change. Anything unlisted is carried through untouched, which is right for ordinals,
# counts, flags and areas -- and is why `params` is transformed key-by-key rather than wholesale.
_POINT_FIELDS = ("center",)
_POINT_PARAM_KEYS = ("origin",)
_DIRECTION_FIELDS = ("normal",)
_DIRECTION_PARAM_KEYS = ("axis", "direction")


def transform_direction(matrix: list[float], vector: object) -> list[float] | None:
    """Rotate a direction. The translation column must NOT apply -- a surface normal that picks
    up the occurrence's offset stops being a unit vector and starts pointing somewhere false."""
    if not isinstance(vector, (list, tuple)) or len(vector) < 3:
        return None
    try:
        x, y, z = (float(vector[0]), float(vector[1]), float(vector[2]))
    except (TypeError, ValueError):
        return None
    return [
        matrix[0] * x + matrix[1] * y + matrix[2] * z,
        matrix[4] * x + matrix[5] * y + matrix[6] * z,
        matrix[8] * x + matrix[9] * y + matrix[10] * z,
    ]


def _transform_params(matrix: list[float], params: object) -> object:
    """Place a face's or edge's surface/curve parameters.

    Leaving these in component-local coordinates while `center` and `bbox` are placed would be
    the worst of both: a cylinder whose centre is in the assembly and whose axis origin is in the
    part, with nothing in the payload saying so. That is the frame mismatch FEEDBACK.md P2 charges
    a wrong edit and a full revert to.
    """
    if not isinstance(params, Mapping):
        return params
    placed: dict[str, Any] = {}
    for key, value in params.items():
        name = str(key)
        if name in _POINT_PARAM_KEYS:
            placed[name] = transform_point(matrix, value) or value
        elif name in _DIRECTION_PARAM_KEYS:
            placed[name] = transform_direction(matrix, value) or value
        else:
            placed[name] = value
    return placed


def _place_entity_row(matrix: list[float], row: Mapping[str, Any]) -> dict[str, Any]:
    """Copy a component row into world coordinates.

    A geometry field that cannot be placed is REMOVED rather than left as it was. Keeping it
    would publish a component-local coordinate in a row whose every other number is in assembly
    space, with nothing marking which is which -- and it would be the same object shared by every
    occurrence of that component, so the two identical spacers would report one position. The
    frames must not mix silently; that is what FEEDBACK.md P2 cost a wrong edit and a revert.
    """
    placed = dict(row)
    for field in _POINT_FIELDS:
        if field in placed:
            moved = transform_point(matrix, placed[field])
            if moved is None:
                placed.pop(field, None)
            else:
                placed[field] = moved
    for field in _DIRECTION_FIELDS:
        if field in placed:
            moved = transform_direction(matrix, placed[field])
            if moved is None:
                placed.pop(field, None)
            else:
                placed[field] = moved
    if "bbox" in placed:
        moved_box = transform_bbox(matrix, placed["bbox"])
        if moved_box is None:
            placed.pop("bbox", None)
        else:
            placed["bbox"] = moved_box
    if "params" in placed:
        placed["params"] = _transform_params(matrix, placed["params"])
    return placed


def _component_bundle_reader():
    """Imported lazily: cadgen._internal.glb pulls in the GLB machinery, and a part entry
    never reaches this module."""
    from cadgen._internal.glb import read_step_topology_bundle_from_glb

    return read_step_topology_bundle_from_glb


def _component_occurrence_bbox(bundle: object) -> object:
    """The component's own root-occurrence bbox, in component-local coordinates."""
    manifest = getattr(bundle, "manifest", None)
    if not isinstance(manifest, Mapping):
        return None
    columns = manifest.get("tables")
    columns = columns.get("occurrenceColumns") if isinstance(columns, Mapping) else None
    rows = manifest.get("occurrences")
    if not isinstance(columns, list) or not isinstance(rows, list) or not rows:
        return None
    first = rows[0]
    if not isinstance(first, list):
        return None
    row = {str(columns[index]): first[index] for index in range(min(len(columns), len(first)))}
    return row.get("bbox")


def assembly_occurrence_rows(
    descriptor: Mapping[str, Any],
    package_dir: Path,
) -> list[dict[str, Any]]:
    """Instance-tree occurrences as selector-index rows, in world coordinates at rest.

    Column names mirror the topology sidecar's ``occurrenceColumns`` so that consumers written
    against that table (``entry_summary``, ``reporting``) need no special case for assemblies.
    """
    rows = descriptor.get("occurrences")
    if not isinstance(rows, list):
        return []
    read_bundle = None
    bbox_by_component: dict[str, object] = {}
    materialized: list[dict[str, Any]] = []
    for entry in rows:
        if not isinstance(entry, Mapping):
            continue
        occurrence_id = str(entry.get("id") or "").strip()
        if not occurrence_id:
            continue
        matrix = _matrix(entry.get("transform"))
        component = str(entry.get("component") or "").strip()
        local_bbox: object = None
        if component:
            if component not in bbox_by_component:
                # Deduped by content hash: tom_v2 has 160 occurrences over 65 components, and
                # the whole set reads in well under a second.
                if read_bundle is None:
                    read_bundle = _component_bundle_reader()
                path = package_dir / COMPONENTS_DIRNAME / f"{component}.glb"
                bundle = read_bundle(path) if path.is_file() else None
                bbox_by_component[component] = _component_occurrence_bbox(bundle)
            local_bbox = bbox_by_component[component]
        materialized.append(
            {
                "id": occurrence_id,
                "path": occurrence_id,
                "name": str(entry.get("name") or occurrence_id),
                "sourceName": str(entry.get("name") or occurrence_id),
                "parentId": occurrence_id.rpartition(".")[0] or None,
                "transform": matrix,
                "bbox": transform_bbox(matrix, local_bbox),
                "component": component or None,
                # Entity ranges belong to phase 2; a reader must not mistake 0 for "has none".
                "shapeStart": 0,
                "shapeCount": 0,
                "faceStart": 0,
                "faceCount": 0,
                "edgeStart": 0,
                "edgeCount": 0,
            }
        )
    return materialized


def _component_index(package_dir: Path, component: str, cache: dict[str, Any]) -> Any:
    """The component's own selector index, loaded once per content hash.

    tom_v2 places 160 occurrences over 65 distinct components, so the cache is most of the cost:
    the whole set reads in about 0.2 s.
    """
    if component in cache:
        return cache[component]
    from cadgen.lookup import build_selector_index

    read_bundle = _component_bundle_reader()
    path = package_dir / COMPONENTS_DIRNAME / f"{component}.glb"
    bundle = read_bundle(path) if path.is_file() else None
    manifest = getattr(bundle, "manifest", None)
    built = None
    if isinstance(manifest, Mapping):
        built = build_selector_index(dict(manifest), buffers=getattr(bundle, "buffers", None))
    cache[component] = built
    return built


def _entity_id(occurrence_id: str, local_id: object, kind: str, ordinal: object) -> str | None:
    """``o1.f19`` inside a component becomes ``o1.12.f19`` in the assembly.

    Prefers the row's own ordinal over re-parsing its id, so the assembly ref keeps the number
    the component's own namespace uses -- which is what makes a translated ref checkable by hand
    against the part file, the exact step users were doing manually.

    None when neither an ordinal nor a suffix is available. Naming it ``o1.12.f`` instead would
    be a selector that cannot be parsed AND that every unnamed row of that component would
    share, so the first would silently stand in for the rest.
    """
    if ordinal is not None:
        try:
            return f"{occurrence_id}.{kind}{int(ordinal)}"
        except (TypeError, ValueError):
            pass
    _, _, suffix = str(local_id or "").rpartition(".")
    return f"{occurrence_id}.{suffix}" if suffix else None


def _rebase(row: dict, field: str, offset: int) -> None:
    """Shift a range field that indexes a list we are concatenating into."""
    if field in row:
        try:
            row[field] = offset + int(row[field] or 0)
        except (TypeError, ValueError):
            row[field] = offset


# Offsets into the component's OWN proxy buffers (mesh triangles, edge polylines, surface
# half-edges). The merged index carries the flat assembly's buffers, not the component's, so a
# start copied across points into unrelated data. Dropped rather than rebased: there is nothing
# in this index for them to point AT. Absent raises a KeyError at the reader; stale silently
# returns the wrong triangles.
_BUFFER_START_FIELDS = ("triangleStart", "segmentStart", "surfaceHalfEdgeStart")


def merge_assembly_entities(
    index: SelectorIndex,
    descriptor: Mapping[str, Any],
    package_dir: Path,
) -> SelectorIndex:
    """Add each occurrence's shapes/faces/edges/vertices, placed into world coordinates.

    This is what makes a ref picked in the viewer measurable: `#o1.12.f19` is face 19 of that
    occurrence's component, and until now only the flat whole-assembly namespace resolved, whose
    numbering does not agree with the component's (FEEDBACK.md: "the assembly's f18 is the wall's
    face; the part's f18 is a 17.085 mm2 cylinder").

    Every id and every RANGE is re-based as the tables concatenate. A component's rows index its
    own tables: a face's `edgeStart` points into that component's faceEdgeRows, a shape's
    `faceStart` slices that component's face list, an edge's `shapeId` names that component's
    solid. Copied across unchanged they all still resolve -- against the wrong thing, which is
    worse than not resolving. `#o1.12.f19` reported `shapeId s1`, and `s1` in the merged index is
    a solid 40 mm away.
    """
    occurrences = descriptor.get("occurrences")
    if not isinstance(occurrences, list) or not occurrences:
        return index

    shapes = list(index.shapes)
    faces = list(index.faces)
    edges = list(index.edges)
    vertices = list(index.vertices)
    shape_by_id = dict(index.shape_by_id)
    face_by_id = dict(index.face_by_id)
    edge_by_id = dict(index.edge_by_id)
    vertex_by_id = dict(index.vertex_by_id)
    occurrence_by_id = dict(index.occurrence_by_id)
    occurrence_rows = list(index.occurrences)
    relations = {name: list(rows) for name, rows in index.relations.items()}
    for name in ("faceEdgeRows", "edgeFaceRows", "edgeVertexRows", "vertexEdgeRows"):
        relations.setdefault(name, [])
    cache: dict[str, Any] = {}
    added = 0

    for entry in occurrences:
        if not isinstance(entry, Mapping):
            continue
        occurrence_id = str(entry.get("id") or "").strip()
        component = str(entry.get("component") or "").strip()
        if not occurrence_id or not component:
            continue
        component_index = _component_index(package_dir, component, cache)
        if component_index is None:
            continue
        matrix = _matrix(entry.get("transform"))

        shape_offset = len(shapes)
        face_offset = len(faces)
        edge_offset = len(edges)
        vertex_offset = len(vertices)
        face_edge_offset = len(relations["faceEdgeRows"])
        edge_face_offset = len(relations["edgeFaceRows"])
        edge_vertex_offset = len(relations["edgeVertexRows"])
        vertex_edge_offset = len(relations["vertexEdgeRows"])

        # A face names its owning solid by id, so the rename has to be known before the faces
        # are written or `shapeId` keeps pointing at the flat namespace.
        shape_id_map: dict[str, str] = {}
        for row in component_index.shapes:
            new_id = _entity_id(occurrence_id, row.get("id"), "s", row.get("ordinal"))
            if new_id is not None:
                shape_id_map[str(row.get("id"))] = new_id

        for row in component_index.shapes:
            new_id = shape_id_map.get(str(row.get("id")))
            if new_id is None:
                continue
            placed = _place_entity_row(matrix, row)
            placed["id"] = new_id
            placed["occurrenceId"] = occurrence_id
            _rebase(placed, "faceStart", face_offset)
            _rebase(placed, "edgeStart", edge_offset)
            shapes.append(placed)
            shape_by_id.setdefault(str(placed["id"]), placed)
            added += 1
        for row in component_index.faces:
            new_id = _entity_id(occurrence_id, row.get("id"), "f", row.get("ordinal"))
            if new_id is None:
                continue
            placed = _place_entity_row(matrix, row)
            placed["id"] = new_id
            placed["occurrenceId"] = occurrence_id
            if placed.get("shapeId") is not None:
                placed["shapeId"] = shape_id_map.get(str(placed["shapeId"]), placed["shapeId"])
            _rebase(placed, "edgeStart", face_edge_offset)
            for field in _BUFFER_START_FIELDS:
                placed.pop(field, None)
            faces.append(placed)
            face_by_id.setdefault(str(placed["id"]), placed)
            added += 1
        for row in component_index.edges:
            new_id = _entity_id(occurrence_id, row.get("id"), "e", row.get("ordinal"))
            if new_id is None:
                continue
            placed = _place_entity_row(matrix, row)
            placed["id"] = new_id
            placed["occurrenceId"] = occurrence_id
            if placed.get("shapeId") is not None:
                placed["shapeId"] = shape_id_map.get(str(placed["shapeId"]), placed["shapeId"])
            _rebase(placed, "faceStart", edge_face_offset)
            _rebase(placed, "vertexStart", edge_vertex_offset)
            for field in _BUFFER_START_FIELDS:
                placed.pop(field, None)
            edges.append(placed)
            edge_by_id.setdefault(str(placed["id"]), placed)
            added += 1
        for row in component_index.vertices:
            new_id = _entity_id(occurrence_id, row.get("id"), "v", row.get("ordinal"))
            if new_id is None:
                continue
            placed = _place_entity_row(matrix, row)
            placed["id"] = new_id
            placed["occurrenceId"] = occurrence_id
            _rebase(placed, "edgeStart", vertex_edge_offset)
            vertices.append(placed)
            vertex_by_id.setdefault(str(placed["id"]), placed)
            added += 1

        component_relations = component_index.relations
        relations["faceEdgeRows"].extend(
            edge_offset + int(value) for value in component_relations.get("faceEdgeRows", [])
        )
        relations["edgeFaceRows"].extend(
            face_offset + int(value) for value in component_relations.get("edgeFaceRows", [])
        )
        relations["edgeVertexRows"].extend(
            vertex_offset + int(value) for value in component_relations.get("edgeVertexRows", [])
        )
        relations["vertexEdgeRows"].extend(
            edge_offset + int(value) for value in component_relations.get("vertexEdgeRows", [])
        )

        # The occurrence's own ranges, now that its rows exist. Phase 1 wrote zeros because it
        # had no entities to point at, and a zero range reads as "this occurrence has no faces".
        # A COPY. These row dicts are shared with the index we were handed, and
        # SelectorIndex is a frozen value: writing ranges into them in place would leave the
        # caller's index claiming slices of lists it does not have.
        occurrence_row = occurrence_by_id.get(occurrence_id)
        if isinstance(occurrence_row, dict):
            occurrence_row = dict(occurrence_row)
            occurrence_by_id[occurrence_id] = occurrence_row
            for position, existing in enumerate(occurrence_rows):
                if existing is not None and str(existing.get("id")) == occurrence_id:
                    occurrence_rows[position] = occurrence_row
                    break
            occurrence_row.update(
                {
                    "shapeStart": shape_offset,
                    "shapeCount": len(component_index.shapes),
                    "faceStart": face_offset,
                    "faceCount": len(component_index.faces),
                    "edgeStart": edge_offset,
                    "edgeCount": len(component_index.edges),
                }
            )

    if not added:
        return index
    return replace(
        index,
        occurrences=occurrence_rows,
        occurrence_by_id=occurrence_by_id,
        shapes=shapes,
        faces=faces,
        edges=edges,
        vertices=vertices,
        shape_by_id=shape_by_id,
        face_by_id=face_by_id,
        edge_by_id=edge_by_id,
        vertex_by_id=vertex_by_id,
        relations=relations,
    )


def merge_assembly_occurrences(
    index: SelectorIndex,
    descriptor: Mapping[str, Any],
    package_dir: Path,
) -> SelectorIndex:
    """Add the instance-tree occurrences to a flat whole-assembly index.

    ADDITIVE on purpose. The flat namespace (``#o1.f19``, ``#o1.s3``) is what every existing
    caller and test resolves against, and ``single_occurrence_id`` is what lets a bare ``#f19``
    canonicalize; replacing the index would break both to fix a third thing.
    """
    rows = assembly_occurrence_rows(descriptor, package_dir)
    if not rows:
        return index
    occurrences = list(index.occurrences)
    occurrence_by_id = dict(index.occurrence_by_id)
    added = 0
    for row in rows:
        occurrence_id = str(row.get("id") or "")
        if not occurrence_id or occurrence_id in occurrence_by_id:
            continue
        occurrences.append(row)
        occurrence_by_id[occurrence_id] = row
        added += 1
    if not added:
        return index
    # occurrenceCount came from the sidecar's stats and said 1 for a 160-part assembly, which is
    # what `inspect refs --facts` reported. It is a count of what this index can resolve.
    manifest = dict(index.manifest)
    stats = dict(manifest.get("stats")) if isinstance(manifest.get("stats"), Mapping) else {}
    stats["occurrenceCount"] = len(occurrences)
    manifest["stats"] = stats
    return replace(
        index,
        manifest=manifest,
        occurrences=occurrences,
        occurrence_by_id=occurrence_by_id,
    )


def _index_with_assembly_occurrences(index: SelectorIndex, artifact: object) -> SelectorIndex:
    if index is None or artifact is None:
        return index
    if str(getattr(artifact, "kind", "")) != "assembly":
        return index
    package_dir = getattr(artifact, "artifact_path", None)
    if not isinstance(package_dir, Path):
        return index
    from cadgen._internal.component_package import is_assembly_package, read_package_descriptor

    if not is_assembly_package(package_dir):
        return index
    descriptor = read_package_descriptor(package_dir)
    if not isinstance(descriptor, dict):
        return index
    merged = merge_assembly_occurrences(index, descriptor, package_dir)
    return merge_assembly_entities(merged, descriptor, package_dir)


def index_with_assembly_occurrences(index: SelectorIndex, artifact: object) -> SelectorIndex:
    """The whole instance tree -- occurrences AND their entities -- keyed off a
    ``StepTopologyArtifact``, plus the label aliases for whatever rows survive.

    Lives here rather than at either call site because there are TWO of them and they had already
    drifted: ``snapshot_cli.artifact_selector_index`` serves ``--focus``/``--hide``, while
    ``inspect refs`` builds its own index from the same bundle. Fixing one would have left the
    other reporting the bug, which is how 0b presented as three separate tool failures.

    Label aliases are attached on EVERY return path, including the early ones for part entries,
    for the same reason: this is the one function both call sites already funnel through, so
    attaching here is what keeps them from drifting again. Aliases must be computed after the
    assembly merge, because the merge is what decides the final row set.

    Anything that is not an assembly package keeps its own occurrence rows, so part entries are
    unaffected other than gaining aliases.
    """
    from cadgen.label_refs import attach_label_aliases

    return attach_label_aliases(_index_with_assembly_occurrences(index, artifact))
