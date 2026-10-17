"""Selector resolution across a tree's INSTANCE TREE.

An assembly is described by two artifacts that answer different questions:

* ``assembly.json`` -- the flattened tree. Knows the instance tree: 160 occurrences for
  ``tom_v2``, each named by its token (``o:…``), each naming a component and carrying its
  placement. This is what ``snapshot --mode list`` enumerates and what the CAD Viewer hands
  the user when they click a part.
* each component's selector table -- ``components/<cid>.selectors.json``, one of its part's
  two objects (``_internal/selector_table``, ``store.parts``) and the same table the CAD Viewer
  reads. It knows the component's own topology: every face, edge and vertex with its name
  (``f:…``, ``e:…``, ``v:…``), its facts and its adjacency, placed nowhere.

This module composes the two: for each occurrence, its component's rows placed into world
coordinates and keyed by ``<occurrence token>/<element name>`` -- the one composition rule,
which the page applies to the same table (``selectors/runtime.js``). So a ref the viewer shows
resolves here to the entity it names there, and a ref copied from a build's preview resolves
against the saved document: the saved document's components are the preview's (README law 20).

Coordinates are WORLD AT REST: occurrence transforms applied, parameter-sidecar poses not.
That is the frame the viewer shows when the ref is picked and the frame ``snapshot --mode list``
already reports its bounds in, so the two tools agree. Reporting component-local coordinates
instead would recreate a frame confusion that has cost a wrong edit and a full revert.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from cadgen.cad_ref_syntax import element_ref
from cadgen.lookup import SelectorIndex

COMPONENTS_DIRNAME = "components"


def _identity() -> list[float]:
    return [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]


def _matrix(raw: object) -> list[float]:
    """A row-major 4x4 as 16 floats, or identity when the assembly.json omits/mangles it."""
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
# counts, flags and lengths -- and is why `params` is transformed key-by-key rather than wholesale.
#
# The param key sets are the COMPLETE vocabulary of `step_scene_geometry._curve_params` and
# `_surface_params`, which is what writes the `params` this places. A point is spelled `origin`
# (plane/cylinder/cone/line) or `center` (circle/ellipse/hyperbola/parabola/sphere/torus),
# never both, so a list that knows only one spelling silently leaves half the analytic types
# in component-local coordinates -- which is what once measured a circular edge and a line
# 37 mm apart on an axis where they touch (tom-cad FEEDBACK issue 2). Any new
# analytic type must land in one of these lists or be a scalar; that is the review question.
_POINT_FIELDS = ("center",)
_POINT_PARAM_KEYS = ("origin", "center", "location")
_DIRECTION_FIELDS = ("normal",)
_DIRECTION_PARAM_KEYS = ("axis", "direction", "normal")


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
    part, with nothing in the payload saying so: a frame mismatch that has cost a wrong edit and
    a full revert.
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
    frames must not mix silently; mixing them has cost a wrong edit and a revert.
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


def _read_component_table(package_dir: Path, component: str) -> dict[str, Any] | None:
    """A component's selector table, as the view carries it (``store.view``): the
    one table the page reads too, so a ref resolves here to the entity it names
    there. None when the view holds none or it does not read."""
    from cadgen._internal.selector_table import read_selector_table
    from cadgen.store.view import SELECTOR_TABLE_SUFFIX

    path = package_dir / COMPONENTS_DIRNAME / f"{component}{SELECTOR_TABLE_SUFFIX}"
    try:
        return read_selector_table(path.read_bytes())
    except (OSError, ValueError):
        return None


def _component_occurrence_bbox(manifest: object) -> object:
    """The component's own root-occurrence bbox, in component-local coordinates."""
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


def _tree_nodes(descriptor: Mapping[str, Any]) -> list[tuple[Mapping[str, Any], str | None]]:
    """Every node of the descriptor's assembly tree with its parent's id, in tree order."""
    root = descriptor.get("assembly")
    root = root.get("root") if isinstance(root, Mapping) else None
    if not isinstance(root, Mapping):
        return []
    found: list[tuple[Mapping[str, Any], str | None]] = []
    stack: list[tuple[Mapping[str, Any], str | None]] = [(root, None)]
    while stack:
        node, parent = stack.pop()
        found.append((node, parent))
        node_id = str(node.get("id") or "").strip() or None
        children = node.get("children")
        children = [child for child in children if isinstance(child, Mapping)] if isinstance(children, list) else []
        stack.extend((child, node_id) for child in reversed(children))
    return found


def assembly_group_members(descriptor: Mapping[str, Any]) -> dict[str, list[str]]:
    """Every tree node's leaf occurrences by token, in tree order, the root first (a leaf's
    are itself): what a group ref covers. The tree's ``leafPartIds`` where the node carries
    them, its leaves walked otherwise."""
    members: dict[str, list[str]] = {}

    def visit(node: Mapping[str, Any]) -> list[str]:
        node_id = str(node.get("id") or "").strip()
        if node_id:
            members[node_id] = []  # entered now, so the mapping is in tree order, a node before its children
        children = [child for child in node.get("children") or [] if isinstance(child, Mapping)]
        declared = node.get("leafPartIds")
        if children:
            found: list[str] = []
            for child in children:
                found.extend(visit(child))
            leaves = [str(leaf) for leaf in declared] if isinstance(declared, list) and declared else found
        else:
            leaves = [node_id] if node_id else []
        if node_id:
            members[node_id] = leaves
        return leaves

    root = descriptor.get("assembly")
    root = root.get("root") if isinstance(root, Mapping) else None
    if isinstance(root, Mapping):
        visit(root)
    return members


def assembly_occurrence_rows(
    descriptor: Mapping[str, Any],
    package_dir: Path | None,
) -> list[dict[str, Any]]:
    """Instance-tree occurrences as selector-index rows, in world coordinates at rest, in the
    descriptor's order: each leaf's token (``id``), name, the token of the node above it
    (``parentId``, None for a root leaf), placement, placed box and component.

    With ``package_dir`` None no component's table is read and no row has a ``bbox``: the
    rows are the occurrence namespace alone, what a kinematics mate's ends resolve in.
    """
    rows = descriptor.get("occurrences")
    if not isinstance(rows, list):
        return []
    parents = {str(node.get("id") or ""): parent for node, parent in _tree_nodes(descriptor)}
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
                table = _read_component_table(package_dir, component) if package_dir is not None else None
                bbox_by_component[component] = _component_occurrence_bbox(table)
            local_bbox = bbox_by_component[component]
        materialized.append(
            {
                "id": occurrence_id,
                "name": str(entry.get("name") or occurrence_id),
                "sourceName": str(entry.get("name") or occurrence_id),
                "parentId": parents.get(occurrence_id),
                "transform": matrix,
                "bbox": transform_bbox(matrix, local_bbox),
                "component": component or None,
            }
        )
    return materialized


def _component_rows(package_dir: Path, component: str, cache: dict[str, Any]) -> dict[str, list[dict[str, Any]]] | None:
    """The component's own table rows by kind, loaded once per content hash.

    tom_v2 places 160 occurrences over 65 distinct components, so the cache is most of the cost:
    the whole set reads in about 0.2 s.
    """
    if component in cache:
        return cache[component]
    from cadgen.lookup import _table_rows

    table = _read_component_table(package_dir, component)
    rows = None
    if table is not None:
        rows = {
            "shapes": _table_rows(table, "shapes", "shapeColumns"),
            "faces": _table_rows(table, "faces", "faceColumns"),
            "edges": _table_rows(table, "edges", "edgeColumns"),
            "vertices": _table_rows(table, "vertices", "vertexColumns"),
        }
    cache[component] = rows
    return rows


def merge_assembly_entities(
    index: SelectorIndex,
    descriptor: Mapping[str, Any],
    package_dir: Path,
) -> SelectorIndex:
    """Add each occurrence's faces, edges and vertices, placed into world coordinates.

    This is what makes a ref picked in the viewer measurable: ``#o:…/f:…`` is the face of that
    occurrence's component whose name that is. The components themselves are kept, as a tree
    lists them, for a ref by geometry (``lookup.index_space``). Every element row is keyed by
    ``<occurrence token>/<element name>`` and carries ``occurrenceId`` (the occurrence that
    places it) and ``shapeId`` (the occurrence's solid, by the component's own ordinal);
    its range columns (``faceStart``, ``edgeCount``, ...) are copied as the component's table
    wrote them: they index that table, and nothing here reads them. The shapes of every
    occurrence are listed too, placed, for the facts a solid gives (its box); they carry no
    ref of their own: the occurrence names a body.
    """
    occurrences = descriptor.get("occurrences")
    if not isinstance(occurrences, list) or not occurrences:
        return index

    shapes = list(index.shapes)
    faces = list(index.faces)
    edges = list(index.edges)
    vertices = list(index.vertices)
    face_by_id = dict(index.face_by_id)
    edge_by_id = dict(index.edge_by_id)
    vertex_by_id = dict(index.vertex_by_id)
    cache: dict[str, Any] = {}
    added = 0

    for entry in occurrences:
        if not isinstance(entry, Mapping):
            continue
        occurrence_id = str(entry.get("id") or "").strip()
        component = str(entry.get("component") or "").strip()
        if not occurrence_id or not component:
            continue
        component_rows = _component_rows(package_dir, component, cache)
        if component_rows is None:
            continue
        matrix = _matrix(entry.get("transform"))

        for row in component_rows["shapes"]:
            placed = _place_entity_row(matrix, row)
            placed["occurrenceId"] = occurrence_id
            placed["shapeId"] = f"{occurrence_id}#{row.get('ordinal')}"
            shapes.append(placed)
            added += 1
        for kind, rows, by_id in (("faces", faces, face_by_id), ("edges", edges, edge_by_id),
                                  ("vertices", vertices, vertex_by_id)):
            for row in component_rows[kind]:
                name = str(row.get("name") or "").strip()
                if not name:
                    continue
                placed = _place_entity_row(matrix, row)
                placed["id"] = element_ref(occurrence_id, name)
                placed["occurrenceId"] = occurrence_id
                placed["shapeId"] = f"{occurrence_id}#{row.get('shape')}"
                rows.append(placed)
                by_id.setdefault(placed["id"], placed)
                added += 1

    if not added:
        return index
    from cadgen.store.parts import geometry_entry

    # A view lists a component with its BREP as ``brepObject``, a flattened tree as ``brep``.
    components = dict(index.components)
    for cid, entry in (descriptor.get("components") or {}).items():
        if isinstance(entry, Mapping) and (entry.get("brepObject") or entry.get("brep")):
            components.setdefault(str(cid), geometry_entry(dict(entry)) if entry.get("brepObject") else dict(entry))
    return replace(
        index,
        shapes=shapes,
        faces=faces,
        edges=edges,
        vertices=vertices,
        face_by_id=face_by_id,
        edge_by_id=edge_by_id,
        vertex_by_id=vertex_by_id,
        components=components,
    )


def assembly_group_nodes(descriptor: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """The instance tree's INTERIOR nodes, keyed by token, in tree order.

    The assembly.json's ``occurrences`` table is leaves only (a leaf is what owns geometry),
    so a subassembly node appears nowhere a selector row can find it. Its identity --
    the name a person recognises the branch by -- lives in the ``assembly`` tree, which
    is what this reads.

    ``transform`` is carried through when the node has one and simply absent otherwise.
    Group placement is baked into each leaf's absolute transform today, so no node here
    carries its own; a synthesised value would be a guess presented as a measurement, and
    a caller can tell "no stored frame" from a wrong one only if we decline to invent it.
    """
    nodes: dict[str, dict[str, Any]] = {}
    for node, _parent in _tree_nodes(descriptor):
        children = node.get("children")
        children = [child for child in children if isinstance(child, Mapping)] if isinstance(children, list) else []
        node_id = str(node.get("id") or "").strip()
        if not node_id or not children:
            continue  # a leaf; its row is in the occurrences table
        entry: dict[str, Any] = {
            "id": node_id,
            "name": str(node.get("name") or node_id),
            "nodeType": str(node.get("nodeType") or "subassembly"),
            "childCount": len(children),
        }
        transform = node.get("transform")
        if isinstance(transform, list) and len(transform) == 16:
            entry["transform"] = [float(value) for value in transform]
        nodes[node_id] = entry
    return nodes


def merge_assembly_occurrences(
    index: SelectorIndex,
    descriptor: Mapping[str, Any],
    package_dir: Path | None,
) -> SelectorIndex:
    """Add the instance-tree occurrences, its group nodes, every node's members and every
    node's names to an index.

    ADDITIVE: rows the index already holds under an id stay as they are.
    """
    from cadgen.refs import descriptor_nodes

    rows = assembly_occurrence_rows(descriptor, package_dir)
    group_nodes = assembly_group_nodes(descriptor)
    members = assembly_group_members(descriptor)
    names = descriptor_nodes(descriptor)[1]
    if not rows:
        return replace(index, group_nodes=group_nodes, members=members, names=names) if members else index
    occurrences = list(index.occurrences)
    occurrence_by_id = dict(index.occurrence_by_id)
    for row in rows:
        occurrence_id = str(row.get("id") or "")
        if not occurrence_id or occurrence_id in occurrence_by_id:
            continue
        occurrences.append(row)
        occurrence_by_id[occurrence_id] = row
    return replace(
        index,
        occurrences=occurrences,
        occurrence_by_id=occurrence_by_id,
        group_nodes=group_nodes,
        members=members,
        names=names,
    )


def index_with_assembly_occurrences(index: SelectorIndex, artifact: object) -> SelectorIndex:
    """The whole instance tree -- occurrences AND their entities -- keyed off a
    ``StepArtifact``: what a snapshot's ``--focus`` and ``--hide`` resolve their refs in
    (``snapshot_cli.artifact_selector_index``). It lives here, beside the composition a
    build's mate axes use (:func:`merge_assembly_occurrences`, :func:`merge_assembly_entities`),
    so that no reader of a ref builds an index of its own that can drift from the others.
    """
    if index is None or artifact is None:
        return index
    # Every tree's selector tables live in its components and are composed here per
    # occurrence -- a part's single component included.
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
