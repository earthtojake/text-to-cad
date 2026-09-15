"""Build a model's TREE from its returned geometry.

Walks the compound a model returned. Every leaf becomes a content-addressed
**component** (encoded ``.brep`` plus an intrinsic face-color recipe); every
subtree that is a child model's materialized geometry, found intact, becomes a
**link** to that child's tree. The decision is mechanical (§Tree in STORE.md):

- a materialized child with its original native partner, geometry and
  descendant occurrence metadata → link at its world location; root label
  and color overrides are still intact;
- anything else — geometry the model made, an extracted sub-shape, a modified
  child (``housing() - holes``: a new TShape), a mirrored child (a new TShape)
  → the model's own components. No error path.

Each native component is privately decoded and validated before publication.
Surface extraction is a separate artifact derivation and never delays native
geometry readiness. A component without an admitted native codec explicitly
pins its eager surface; no later producer receives the original live shape.

A model's final result contains its authored source geometry, reconstructed
from canonical BREP bytes, whether it declares STEP or only meshes. A STEP
writer (``build_tree_through_step``) publishes that complete immutable tree
before persistence, then assembles the document from those exact pins.
OCCT's STEP translation is not lossless for every surface, so a separate
document tree comes entirely from that STEP's
read-back, through the same builder a cold import uses. Only the latter belongs
under the document byte digest. Resolved appearance and the occurrence mapping
are returned as private publication data, never inserted into that tree.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import struct
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from cadgen.coordination import PHASE_COMPONENTS, PHASE_FINALIZE, PHASE_PACKAGE
from cadgen.coordination import resolve as resolve_progress
from cadgen.store.index import read_entry, write_entry
from cadgen.store.materialize import (
    PARTNER_TAG,
    ROOT_LOC_TAG,
    TREE_TAG,
    _ComponentIdentity,
    _location_from_matrix,
    materialized_children,
)
from cadgen.store.objects import has_object, put_object, read_verified_object
from cadgen.store.trees import put_tree


def _tagged_intact(node: Any) -> str | None:
    """The tree hash when ``node`` is a materialized child still carrying the
    geometry it was materialized with (placement may differ), else None."""
    tag = getattr(node, TREE_TAG, None)
    if not tag:
        return None
    holder = getattr(node, PARTNER_TAG, None)
    intact = getattr(holder, "intact", None)
    if intact is None:
        return None
    try:
        return str(tag) if intact(node) else None
    except Exception:  # noqa: BLE001 - an odd wrapper is not intact
        return None


def compound_has_children(shape: Any) -> bool:
    """Whether ``shape`` is a Compound placing children — the ONE fact packaging
    turns on. A Compound with children becomes occurrences (one per child, links
    where a child is an intact model result); anything else is one component.
    Nothing but the shape itself decides this: no declaration, no inference from
    source."""
    try:
        if tuple(getattr(shape, "children", ()) or ()):
            return True
    except TypeError:
        pass
    wrapped = getattr(shape, "wrapped", None)
    if wrapped is None:
        return False
    try:
        from OCP.TopAbs import TopAbs_COMPOUND
        from OCP.TopoDS import TopoDS_Iterator

        if wrapped.ShapeType() != TopAbs_COMPOUND:
            return False
        iterator = TopoDS_Iterator(wrapped)
        count = 0
        while iterator.More():
            count += 1
            if count > 1:
                return True
            iterator.Next()
    except Exception:  # noqa: BLE001 - an odd wrapper packages as one component
        return False
    return False


@dataclass
class _Walk:
    """A compound walked into tree parts, before anything is published: own
    occurrences (placing ``components`` by cid), links to children's trees, the
    grouping root, and per cid the shape that owns the geometry plus the
    location-stripped BREP bytes its cid digests."""

    occurrences: list[dict[str, Any]] = field(default_factory=list)
    links: list[dict[str, Any]] = field(default_factory=list)
    components: dict[str, dict[str, Any]] = field(default_factory=dict)
    shapes: dict[str, Any] = field(default_factory=dict)
    brep_bytes_by_cid: dict[str, bytes] = field(default_factory=dict)
    prepared: dict[str, dict[str, Any]] = field(default_factory=dict)
    native_locations: dict[str, Any] = field(default_factory=dict)
    root: dict[str, Any] = field(default_factory=dict)

    def draft_tree(self, *, root_name: str) -> dict[str, Any]:
        """The tree these parts describe, minus the object hashes publishing adds."""
        return {
            "label": root_name,
            "units": "mm",
            "components": self.components,
            "occurrences": self.occurrences,
            "links": self.links,
            "assembly": {"root": self.root},
        }


def build_tree_from_compound(
    compound: Any,
    *,
    root_name: str,
    force: bool = False,
    progress: Any | None = None,
    extra: dict[str, Any] | None = None,
    materials: object = None,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Return ``(tree_hash, tree, stats)``. ``extra`` are content-pure fields
    recorded on the tree (capabilities, edgeRendering) — never paths or times.

    Packaging follows the RETURN VALUE: a Compound with children is walked into
    occurrences; a single shape is one component (``compound_has_children``).
    The tree's ``entryKind`` is then read off the tree (``tree_kind``).

    The components are the shapes as returned. This is the tree of a model that
    writes no STEP (mesh-only outputs) and of an imported document, whose
    compound IS the document's geometry; a model that writes a STEP builds
    through it (:func:`build_tree_through_step`)."""
    progress = resolve_progress(progress)
    walk = _walk_compound(compound, root_name=root_name, progress=progress)
    from cadgen._internal.source_sidecar import resolve_materials
    from cadgen.store.trees import flatten_tree

    descriptor = flatten_tree(walk.draft_tree(root_name=root_name))
    inherited_appearance = descriptor.get("appearance")
    appearance = resolve_materials(descriptor, materials, inherited=inherited_appearance)
    return _publish_tree(
        walk, bbox_shape=compound, root_name=root_name, force=force, progress=progress,
        extra=extra, appearance=appearance, base_appearance=inherited_appearance,
    )


def _document_walk(
    scene: Any, *, progress: Any,
) -> tuple[_Walk, Any, dict[str, list[str]], dict[str, str]]:
    """Walk parsed STEP products, with no filename or authored-result input.

    A product holding a native compound remains that product, rather than
    acquiring another grouping from a reconstructed Python wrapper. Canonical
    IDs follow product order; the maps relate the parser's paths to their
    canonical node and descendant leaf IDs, including synthetic wrapping when
    a STEP has several free roots.
    """
    from build123d import Compound

    from cadgen._internal.component_package import (
        _build123d_shape_from_topods, _component_id, prepare_geometry_component, _normalized_face_colors,
    )
    from cadgen._internal.step_scene_loader import _selector_id
    from cadgen._internal.step_scene_mesh import _face_colors_by_ordinal, scene_occurrence_shape

    walk = _Walk()
    prototype_cids: dict[Any, str] = {}
    occurrence_map: dict[str, list[str]] = {}
    node_map: dict[str, str] = {}
    located_shapes: list[Any] = []

    def node_name(node: Any, occurrence_id: str) -> str:
        return str(node.name or node.source_name or occurrence_id)

    def collect(node: Any, occurrence_id: str) -> dict[str, Any]:
        parsed_id = _selector_id(node.path)
        if parsed_id in occurrence_map:
            raise RuntimeError(f"STEP has duplicate product path {parsed_id}")
        occurrence_map[parsed_id] = []
        node_map[parsed_id] = occurrence_id
        name = node_name(node, occurrence_id)
        if node.children:
            children = [collect(child, f"{occurrence_id}.{index}")
                        for index, child in enumerate(node.children, start=1)]
            leaves = [leaf for child in children for leaf in child["leafPartIds"]]
            occurrence_map[parsed_id] = leaves
            return {"id": occurrence_id, "name": name, "nodeType": "subassembly",
                    "leafPartIds": leaves, "children": children}
        key = node.prototype_key
        if key is None or key not in scene.prototype_shapes:
            raise RuntimeError(f"STEP product {parsed_id} has no geometry")
        cid = prototype_cids.get(key)
        if cid is None:
            prototype = scene.prototype_shapes[key]
            raw_colors = scene.prototype_face_colors.get(key)
            face_colors = _normalized_face_colors(
                _face_colors_by_ordinal(prototype, raw_colors) if raw_colors else None
            )
            prepared = prepare_geometry_component(prototype, face_colors=face_colors)
            content_hash = prepared["entry"]["contentHash"]
            cid = _component_id(content_hash)
            prototype_cids[key] = cid
            if cid not in walk.shapes:
                shape = _build123d_shape_from_topods(prototype)
                if face_colors:
                    shape.cad_face_ordinal_colors = face_colors
                walk.shapes[cid] = shape
                walk.prepared[cid] = prepared
                walk.brep_bytes_by_cid[cid] = prepared["payload"]
                meta: dict[str, Any] = dict(prepared["entry"])
                color = scene.prototype_colors.get(key)
                if color is not None:
                    meta["color"] = [float(c) for c in color]
                walk.components[cid] = meta
        occurrence = {"id": occurrence_id, "name": name, "component": cid,
                      "transform": [float(value) for value in node.transform]}
        color = node.color if node.color is not None else scene.prototype_colors.get(key)
        if color is not None:
            occurrence["color"] = [float(c) for c in color]
        walk.occurrences.append(occurrence)
        # Publication-only native placement. Canonical bounds use this exact
        # location rather than reconstructing one from the serialized matrix,
        # which can re-orthogonalize rotations by a few ulps.
        walk.native_locations[occurrence_id] = node.location
        located_shapes.append(_build123d_shape_from_topods(scene_occurrence_shape(scene, node)))
        occurrence_map[parsed_id] = [occurrence_id]
        progress.advance(detail=name)
        return {"id": occurrence_id, "name": name, "nodeType": "part",
                "leafPartIds": [occurrence_id], "children": []}

    progress.phase(PHASE_PACKAGE)
    roots = list(scene.roots)
    if not roots:
        raise RuntimeError("STEP has no product roots")
    if len(roots) == 1:
        walk.root = collect(roots[0], "o1")
        if walk.root["children"]:
            walk.root["nodeType"] = "assembly"
    else:
        children = [collect(node, f"o1.{index}") for index, node in enumerate(roots, start=1)]
        walk.root = {"id": "o1", "name": "model", "nodeType": "assembly", "children": children,
                     "leafPartIds": [leaf for child in children for leaf in child["leafPartIds"]]}
    if not walk.occurrences:
        raise RuntimeError("STEP has no leaf geometry")
    return walk, Compound(children=located_shapes), occurrence_map, node_map


def _publish_document_scene(
    scene: Any, *, force: bool, progress: Any, repair_objects: bool = False,
) -> tuple[str, dict[str, Any], dict[str, Any], dict[str, list[str]], dict[str, str]]:
    from cadgen._internal.glb_topology import (
        STEP_EDGE_DEFAULT_RENDER_VISIBILITY_CLASSES, step_topology_capabilities,
    )

    walk, artifact, occurrence_map, node_map = _document_walk(scene, progress=progress)
    digest, tree, stats = _publish_tree(
        walk, bbox_shape=artifact, root_name=walk.root["name"], force=force, progress=progress,
        extra={"capabilities": step_topology_capabilities(),
               "edgeRendering": {"visibilityClasses": list(STEP_EDGE_DEFAULT_RENDER_VISIBILITY_CLASSES)}},
        repair_objects=repair_objects,
        prepared_occurrence_bounds=True,
    )
    return digest, tree, stats, occurrence_map, node_map


def build_document_tree(
    scene: Any, *, force: bool = False, progress: Any | None = None,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Canonical ``(digest, tree, stats)`` from a parsed STEP scene.

    The scene must describe the saved bytes. No source name, filename, model
    record, appearance annotation or author options enter this tree. Both cold
    compilation and generated STEP read-back use this exact packaging path.
    This writes immutable objects and component indexes, never document indexes.
    A compile miss can follow an unreadable indexed object, so canonical
    publication verifies reuse and atomically repairs damaged derived bytes.
    """
    digest, tree, stats, _, _ = _publish_document_scene(
        scene, force=force, progress=resolve_progress(progress), repair_objects=True,
    )
    return digest, tree, stats


def _walk_compound(compound: Any, *, root_name: str, progress: Any) -> _Walk:
    from build123d import Location

    single_component = not compound_has_children(compound)

    from cadgen._internal.component_package import (
        _component_id,
        prepare_geometry_component,
        _normalized_face_colors,
        _occurrence_color,
        _occurrence_material,
        _transform_from_location,
    )

    walk = _Walk()
    from cadgen.store._references import links as reference_links

    references = reference_links(compound)
    if references is not None:
        progress.phase(PHASE_PACKAGE)
        walk.links = references
        walk.root = {
            "id": "o1", "name": str(getattr(compound, "label", "") or "o1"),
            "nodeType": "assembly", "leafPartIds": [row["id"] for row in references],
            "children": [{"id": row["id"], "name": row["name"], "nodeType": "link",
                          "tree": row["tree"], "children": []} for row in references],
        }
        for row in references:
            progress.advance(detail=row["name"])
        return walk
    occurrences = walk.occurrences
    links = walk.links
    components = walk.components
    shapes = walk.shapes
    hash_memo: dict[Any, str] = {}
    brep_bytes_by_cid = walk.brep_bytes_by_cid

    def _add_leaf(
        node: Any,
        world_loc: Any,
        occ_id: str,
        name: str | None = None,
        identity: _ComponentIdentity | None = None,
    ) -> dict[str, Any]:
        face_colors = _normalized_face_colors(getattr(node, "cad_face_ordinal_colors", None))
        if identity is not None:
            try:
                from cadgen._internal.component_package import validate_geometry_component
                validate_geometry_component(identity.entry(), read_verified_object(identity.brep), cid=identity.cid)
            except (OSError, ValueError, TypeError):
                # A lost or damaged pin cannot certify newly serialized geometry.
                identity = None
        if identity is not None:
            cid = identity.cid
            entry_meta = identity.entry()
        else:
            try:
                memo_key = (node.wrapped.TShape(), int(node.wrapped.Orientation()), tuple(face_colors.items()))
                cid = hash_memo.get(memo_key)
            except TypeError:
                memo_key, cid = None, None
            if cid is None:
                prepared = prepare_geometry_component(node, face_colors=face_colors)
                entry_meta = dict(prepared["entry"])
                cid = _component_id(entry_meta["contentHash"])
                previous = walk.prepared.setdefault(cid, prepared)
                if previous["entry"]["contentHash"] != entry_meta["contentHash"]:
                    raise ValueError("short component ID collision")
                brep_bytes_by_cid.setdefault(cid, prepared["payload"])
                if memo_key is not None:
                    hash_memo[memo_key] = cid
            else:
                entry_meta = dict(walk.prepared[cid]["entry"])
        shapes.setdefault(cid, node)
        node_color = getattr(node, "color", None)
        if node_color is not None:
            try:
                entry_meta["color"] = [float(c) for c in node_color.to_tuple()]
            except Exception:  # noqa: BLE001
                pass
        components.setdefault(cid, entry_meta)
        if name is None:
            name = str(getattr(node, "label", "") or f"part_{occ_id}")
        occurrence: dict[str, Any] = {
            "id": occ_id,
            "name": name,
            "component": cid,
            "transform": _transform_from_location(world_loc),
        }
        color = _occurrence_color(node)
        if color is not None:
            occurrence["color"] = color
        material = _occurrence_material(node)
        if material is not None:
            occurrence["material"] = material
            material_id = getattr(node, "_cadgen_material_id", None)
            if isinstance(material_id, str) and material_id:
                occurrence["materialId"] = material_id
        occurrences.append(occurrence)
        progress.advance(detail=name)
        return {"id": occ_id, "name": name, "nodeType": "part", "leafPartIds": [occ_id], "children": []}

    def _add_link(node: Any, world_loc: Any, occ_id: str, tree_hash: str) -> dict[str, Any]:
        name = str(getattr(node, "label", "") or occ_id)
        # The link places the child's TREE FRAME. The node's location is
        # ``placement * root`` when the child's own root occurrence is placed
        # (a part returned as ``Pos(...) * body``), and the tree re-applies that
        # root on expansion, so divide it out here or it lands twice.
        root_matrix = getattr(node, ROOT_LOC_TAG, None)
        if root_matrix is not None:
            world_loc = world_loc * _location_from_matrix(list(root_matrix)).inverse()
        link: dict[str, Any] = {
            "id": occ_id,
            "name": name,
            "tree": tree_hash,
            "transform": _transform_from_location(world_loc),
        }
        color = _occurrence_color(node)
        if color is not None:
            link["color"] = color
        links.append(link)
        progress.advance(detail=name)
        return {"id": occ_id, "name": name, "nodeType": "link", "tree": tree_hash, "children": []}

    def _consume_spliced(node: dict[str, Any], parent_world_loc: Any, path: str) -> dict[str, Any]:
        if node.get("leaf"):
            return _add_leaf(node["shape"], parent_world_loc * node["world_loc"], path, name=node["name"])
        child_nodes = [
            _consume_spliced(child, parent_world_loc, f"{path}.{index}")
            for index, child in enumerate(node["children"], start=1)
        ]
        return {
            "id": path,
            "name": node["name"],
            "nodeType": "subassembly",
            "leafPartIds": [leaf for cn in child_nodes for leaf in cn.get("leafPartIds", [cn["id"]])],
            "children": child_nodes,
        }

    def _walk(
        node: Any,
        parent_world_loc: Any,
        path: str,
        baseline: Any = None,
        *,
        identities_verified: bool = False,
    ) -> dict[str, Any]:
        node_loc = getattr(node, "location", None)
        world_loc = (parent_world_loc * node_loc) if node_loc is not None else parent_world_loc
        if baseline is None:
            baseline = getattr(getattr(node, PARTNER_TAG, None), "baseline", None)
        if path != "o1":
            tagged = _tagged_intact(node)
            if tagged is not None:
                return _add_link(node, world_loc, path, tagged)
        nested_tree = getattr(node, "_occurrence_tree", None)
        if nested_tree is not None:
            spliced = _consume_spliced(dict(nested_tree, leaf=False), world_loc, path)
            spliced["name"] = str(getattr(node, "label", "") or nested_tree.get("name") or path)
            return spliced
        child_shapes = materialized_children(node, baseline)
        if not child_shapes:
            identity = baseline.component if identities_verified and baseline is not None else None
            return _add_leaf(node, world_loc, path, identity=identity)
        child_nodes = [
            _walk(
                child,
                world_loc,
                f"{path}.{index}",
                child_baseline,
                identities_verified=identities_verified,
            )
            for index, (child, child_baseline) in enumerate(child_shapes, start=1)
        ]
        return {
            "id": path,
            "name": str(getattr(node, "label", "") or path),
            "nodeType": "subassembly",
            "leafPartIds": [leaf for cn in child_nodes for leaf in cn.get("leafPartIds", [cn["id"]])],
            "children": child_nodes,
        }

    progress.phase(PHASE_PACKAGE)
    holder = getattr(compound, PARTNER_TAG, None)
    baseline = getattr(holder, "baseline", None)
    verified_baseline = None
    verify = getattr(holder, "verified_baseline", None)
    if verify is not None:
        try:
            verified_baseline = verify(compound)
        except Exception:  # noqa: BLE001 - unverifiable geometry takes the canonical slow path
            verified_baseline = None
    if single_component:
        identity = verified_baseline.component if verified_baseline is not None else None
        root = _add_leaf(
            compound,
            getattr(compound, "location", None) or Location(),
            "o1",
            identity=identity,
        )
        root["nodeType"] = "part"
    else:
        occurrence_tree = getattr(compound, "_occurrence_tree", None)
        if occurrence_tree is not None:
            root = _consume_spliced(dict(occurrence_tree, leaf=False), Location(), "o1")
        else:
            root = _walk(
                compound,
                Location(),
                "o1",
                baseline,
                identities_verified=verified_baseline is not None,
            )
        # A native compound with no wrapper children (a fuse whose pieces do not
        # all touch) walks to one leaf: it is that part, not a childless assembly.
        root["nodeType"] = "assembly" if root.get("children") else "part"
    if not occurrences and not links:
        raise RuntimeError(f"model {root_name!r} has no geometry")
    walk.root = root
    return walk


def _publish_tree(
    walk: _Walk,
    *,
    bbox_shape: Any,
    root_name: str,
    force: bool,
    progress: Any,
    extra: dict[str, Any] | None,
    repair_objects: bool = False,
    descriptor_bounds: bool = False,
    prepared_occurrence_bounds: bool = False,
    bbox_override: dict[str, list[float]] | None = None,
    appearance: dict[str, Any] | None = None,
    base_appearance: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Publish verified geometry inputs before any disposable surface work."""
    from cadgen._internal.component_package import _bbox_from_shape, validate_geometry_component

    occurrences, links = walk.occurrences, walk.links
    components, root = walk.components, walk.root
    built, reused = [], []
    progress.phase(PHASE_COMPONENTS, total=len(components))
    for cid, entry in components.items():
        prepared = walk.prepared.get(cid)
        payload = prepared["payload"] if prepared is not None else read_verified_object(entry["brep"])
        validate_geometry_component(entry, payload, cid=cid)
        ready = not force
        for field in ("brep", "eagerSurface"):
            if not entry.get(field):
                continue
            try:
                read_verified_object(entry[field])
            except (OSError, ValueError):
                ready = False
        if ready:
            reused.append(cid)
        else:
            # Capture owns these exact bytes; repair does not ask the live
            # authored shape or a newer child result to replace this input.
            put_object(payload, repair=True)
            if entry.get("eagerSurface"):
                surface = prepared["surface"] if prepared is not None else read_verified_object(entry["eagerSurface"])
                put_object(surface, repair=True)
            built.append(cid)
        write_entry("component", cid, {"schemaVersion": 1, **entry})
        progress.advance(detail=cid)

    progress.phase(PHASE_FINALIZE)
    # Resolved intrinsic appearance has one home in schema-2 trees. Transient
    # materialized wrappers may have supplied inline private metadata while a
    # child became parent-owned geometry; flattening above already folded it
    # into the named library and assignments.
    for occurrence in occurrences:
        occurrence.pop("material", None)
        occurrence.pop("materialId", None)
    tree: dict[str, Any] = dict(extra or {})
    tree.update(
        {
            "label": root_name,
            "units": "mm",
            "components": components,
            "occurrences": occurrences,
            "links": links,
            "assembly": {"root": root},
        }
    )
    if appearance is not None:
        tree["appearance"] = appearance
    from cadgen.store.trees import tree_kind

    from cadgen.store.trees import TREE_KIND, TREE_SCHEMA, _validate_structure
    tree["kind"] = TREE_KIND
    tree["schemaVersion"] = TREE_SCHEMA
    tree["entryKind"] = tree_kind(tree)
    _validate_structure(tree, native=True)
    bbox = bbox_override
    if bbox is None and descriptor_bounds and not force:
        from cadgen.store._descriptor_bounds import try_bounds
        bbox = try_bounds(walk.draft_tree(root_name=root_name))
    if bbox is None and prepared_occurrence_bounds and not force:
        bbox = _bbox_from_prepared_occurrences(walk)
    if bbox is None:
        bbox = _bbox_from_shape(bbox_shape)
    if bbox is not None:
        tree["bbox"] = bbox
    tree["stats"] = {"occurrenceCount": len(occurrences), "linkCount": len(links)}
    # The metadata-only refresh baseline: identical source geometry and child
    # pins with local @step materials removed, while inherited child appearance
    # remains. Publishing it is content-only and performs no kernel work.
    unannotated = dict(tree)
    if base_appearance is not None:
        unannotated["appearance"] = base_appearance
    else:
        unannotated.pop("appearance", None)
    unannotated_hash = put_tree(unannotated, repair=repair_objects)
    tree_hash = put_tree(tree, repair=repair_objects)
    stats = {
        "occurrences": len(occurrences),
        "links": len(links),
        "unique_components": len(components),
        "components_built": len(built),
        "components_reused": len(reused),
        "unannotatedTree": unannotated_hash,
    }
    return tree_hash, tree, stats


_PREPARED_OCCURRENCE_BOUNDS_OP = "component_bbox.canonical_native_rotation.algorithm1"


def _bbox_from_prepared_occurrences(walk: _Walk) -> dict[str, list[float]] | None:
    """Exact canonical bounds without serializing every placed occurrence.

    ``_document_walk`` already owns one privately decoded shape per canonical
    component and the exact native location of each parsed STEP occurrence.
    Use the component's verified BREP identity, native-leaf ordinal and exact
    leaf rotation as the memo input, measure that leaf tightly on a miss, and
    apply only its removed final translation. No transformed local AABB is used.

    Any incomplete private input falls back to the ordinary composed-shape
    path in ``_publish_tree``. Store component and draft-structure validation
    have already run before this helper is called.
    """
    try:
        from OCP.TopLoc import TopLoc_Location
        from OCP.gp import gp_Vec

        from cadgen._internal import op_memo
        from cadgen._internal.component_package import _world_leaves, optimal_box

        boxes: list[list[float]] = []
        for occurrence in walk.occurrences:
            occurrence_id = str(occurrence["id"])
            cid = str(occurrence["component"])
            entry = walk.components[cid]
            prepared = walk.prepared[cid]
            prototype = prepared.get("shape")
            location = walk.native_locations[occurrence_id]
            if prototype is None or location is None:
                return None

            placed = prototype.wrapped.Located(location)
            for leaf_ordinal, leaf in enumerate(_world_leaves(placed), start=1):
                transform = leaf.Location().Transformation()
                translation = tuple(float(value) for value in transform.TranslationPart().Coord())
                transform.SetTranslationPart(gp_Vec(0.0, 0.0, 0.0))
                linear = tuple(float(transform.Value(row, column))
                               for row in range(1, 4) for column in range(1, 5))
                untranslated = leaf.Located(TopLoc_Location(transform))

                box = op_memo.memoized_value(
                    _PREPARED_OCCURRENCE_BOUNDS_OP,
                    (str(entry["codec"]), str(entry["brep"]), leaf_ordinal,
                     struct.pack("<12d", *linear)),
                    lambda untranslated=untranslated: optimal_box(untranslated),
                )
                if box is not None:
                    if (type(box) not in (list, tuple) or len(box) != 6 or
                            any(type(value) not in (float, int) or not math.isfinite(value)
                                for value in box)):
                        return None
                    boxes.append([
                        float(value) + translation[index % 3]
                        for index, value in enumerate(box)
                    ])
        if not boxes:
            return None
        return {
            "min": [min(box[axis] for box in boxes) for axis in range(3)],
            "max": [max(box[axis] for box in boxes) for axis in range(3, 6)],
        }
    except Exception:  # noqa: BLE001 - ordinary native bounds remain the exact fallback
        return None


def _transforms_agree(written: list[float], read: tuple[float, ...]) -> bool:
    if len(written) != 16 or len(read) != 16:
        return False
    return all(abs(a - b) <= 1e-6 * max(1.0, abs(a), abs(b)) for a, b in zip(written, read))


def _document_correspondence(
    descriptor: dict[str, Any], scene: Any, parsed_leaves: dict[str, list[str]],
    parsed_nodes: dict[str, str],
    *, root_name: str, step_name: str,
) -> tuple[dict[str, list[str]], dict[str, dict[str, float]], dict[str, str]]:
    """Match the complete exported hierarchy, including pinned child leaves.

    The STEP writer places each prepared child in order. A written leaf may
    acquire native product children (notably a located solid root), so its
    appearance applies to that exact descendant set. No geometry/name search
    guesses a different product when hierarchy, placement or coverage disagree.
    """
    from cadgen._internal.step_scene_loader import _normalize_label_name, _selector_id

    occurrences: dict[str, dict[str, Any]] = {}
    for occurrence in descriptor.get("occurrences") or []:
        occurrence_id = str(occurrence["id"])
        if occurrence_id in occurrences:
            raise RuntimeError(f"{step_name}: duplicate authored occurrence {occurrence_id}")
        occurrences[occurrence_id] = occurrence
    occurrence_map: dict[str, list[str]] = {}
    appearance: dict[str, dict[str, float]] = {}
    node_map: dict[str, str] = {}
    claimed: set[str] = set()
    matched: set[str] = set()

    def fail(occurrence_id: str, detail: str) -> None:
        raise RuntimeError(f"{step_name}: STEP correspondence for {occurrence_id}: {detail}")

    def match(authored: dict[str, Any], written: Any, *, root: bool = False) -> list[str]:
        occurrence_id = str(authored["id"])
        if occurrence_id in occurrence_map:
            fail(occurrence_id, "duplicate authored product path")
        occurrence_map[occurrence_id] = []
        parsed_id = _selector_id(written.path)
        leaves = parsed_leaves.get(parsed_id)
        if not leaves:
            fail(occurrence_id, f"written product {parsed_id} has no canonical leaves")
        canonical_node = parsed_nodes.get(parsed_id)
        if not canonical_node:
            fail(occurrence_id, f"written product {parsed_id} has no canonical node")
        node_map[occurrence_id] = canonical_node
        occurrence = occurrences.get(occurrence_id)
        # Single-shape XCAF export may replace its root name with a reference
        # wrapper. Within an explicitly authored assembly, names are written
        # directly and help verify that the product order survived the export.
        if not (root and occurrence is not None):
            expected_name = _normalize_label_name(root_name if root else authored.get("name"))
            if expected_name is not None and expected_name != (written.name or written.source_name):
                fail(occurrence_id, f"written product name changed from {expected_name!r} "
                     f"to {(written.name or written.source_name)!r}")
        children = authored.get("children") or []
        if occurrence is not None:
            if children:
                fail(occurrence_id, "an authored leaf also claims product children")
            if not written.children and not _transforms_agree(occurrence["transform"], tuple(written.transform)):
                fail(occurrence_id, "written leaf placement changed")
            if claimed.intersection(leaves):
                fail(occurrence_id, "canonical leaves are claimed by more than one authored occurrence")
            claimed.update(leaves)
            matched.add(occurrence_id)
            material = occurrence.get("material")
            if material:
                for leaf_id in leaves:
                    appearance[leaf_id] = dict(material)
        else:
            if len(children) != len(written.children) or not children:
                fail(occurrence_id, "written product children do not match the authored hierarchy")
            mapped = [leaf for child, written_child in zip(children, written.children)
                      for leaf in match(child, written_child)]
            if mapped != leaves:
                fail(occurrence_id, "written descendant order differs from the authored hierarchy")
        occurrence_map[occurrence_id] = list(leaves)
        return leaves

    root = (descriptor.get("assembly") or {}).get("root")
    if not isinstance(root, dict) or len(scene.roots) != 1:
        raise RuntimeError(f"{step_name}: STEP correspondence requires the one exported product root")
    all_leaves = match(root, scene.roots[0], root=True)
    if matched != set(occurrences) or claimed != set(all_leaves):
        raise RuntimeError(f"{step_name}: STEP correspondence does not cover every authored and written leaf")
    return occurrence_map, appearance, node_map


def _reread_component(
    scene: Any, node: Any, occurrence: dict[str, Any], step_name: str, *, written: Any
) -> tuple[Any, dict[int, tuple] | None]:
    """The component an own occurrence reads back as: ``(unlocated TopoDS_Shape,
    face colours by MapShapes ordinal or None)``.

    A leaf node IS the prototype. A node with children is what XCAF makes of a
    written ``TopoDS_Compound`` (and of the located root of a single-shape
    document, whose placement the reader hangs on the child): its leaves,
    re-placed relative to the occurrence's own placement, are the component —
    so the occurrence's transform still places exactly what the document
    shows. The component keeps the WRITTEN shape's kind: a compound that was
    written (a ``Part``, build123d's boolean result, is a compound of one
    solid) comes back a compound, so ``materialize`` hands a parent the type
    the model returned; a located solid root comes back the bare solid, which
    keeps XCAF's own de-duplication (one product, one cid) across
    occurrences."""
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.BRep import BRep_Builder
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS_Compound

    from cadgen._internal.step_scene_loader import _location_from_transform_matrix, _selector_id
    from cadgen._internal.step_scene_mesh import _face_colors_by_ordinal, _iter_leaf_occurrences

    occ_id = str(occurrence["id"])
    label = f"{step_name}: occurrence {occ_id} ({occurrence.get('name')})"
    if not node.children:
        if node.prototype_key is None or node.prototype_key not in scene.prototype_shapes:
            raise RuntimeError(f"{label} reads back with no shape")
        if not _transforms_agree(occurrence["transform"], tuple(node.transform)):
            raise RuntimeError(
                f"{label} reads back at a different placement: wrote {occurrence['transform']}, "
                f"read {list(node.transform)}"
            )
        prototype = scene.prototype_shapes[node.prototype_key]
        face_colors = scene.prototype_face_colors.get(node.prototype_key)
        return prototype, (_face_colors_by_ordinal(prototype, face_colors) if face_colors else None)

    leaves = _iter_leaf_occurrences([node])
    if not leaves:
        raise RuntimeError(f"{label} reads back with no shape")
    inverse = _location_from_transform_matrix(tuple(occurrence["transform"])).Inverted()
    placed: list[tuple[Any, Any]] = []
    for leaf in leaves:
        if leaf.prototype_key is None or leaf.prototype_key not in scene.prototype_shapes:
            raise RuntimeError(f"{label}: member {_selector_id(leaf.path)} reads back with no shape")
        relative = inverse.Multiplied(leaf.location) if leaf.location is not None else inverse
        if relative.IsIdentity() or _transforms_agree(list(_identity16()), tuple(_matrix16(relative))):
            relative = TopLoc_Location()
        placed.append((leaf, relative))
    written_compound = written is not None and written.ShapeType() == TopAbs_ShapeEnum.TopAbs_COMPOUND
    if len(placed) == 1 and placed[0][1].IsIdentity() and not written_compound:
        leaf = placed[0][0]
        prototype = scene.prototype_shapes[leaf.prototype_key]
        face_colors = scene.prototype_face_colors.get(leaf.prototype_key)
        return prototype, (_face_colors_by_ordinal(prototype, face_colors) if face_colors else None)

    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    merged_face_colors: dict[int, tuple] = {}
    for leaf, relative in placed:
        prototype = scene.prototype_shapes[leaf.prototype_key]
        builder.Add(compound, prototype.Located(relative))
        merged_face_colors.update(scene.prototype_face_colors.get(leaf.prototype_key) or {})
    if not merged_face_colors:
        return compound, None
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape

    from cadgen._internal.step_scene_loader import _shape_hash

    face_map = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(compound, TopAbs_ShapeEnum.TopAbs_FACE, face_map)
    by_ordinal: dict[int, tuple] = {}
    for ordinal in range(1, face_map.Extent() + 1):
        # Face colours are keyed by the PROTOTYPE's faces; a member's faces are
        # those faces under the member's location, so strip it to look them up.
        color = merged_face_colors.get(_shape_hash(face_map.FindKey(ordinal).Located(TopLoc_Location())))
        if color is not None:
            by_ordinal[ordinal] = tuple(float(c) for c in color)
    return compound, (by_ordinal or None)


def _identity16() -> list[float]:
    return [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]


def _matrix16(location: Any) -> list[float]:
    trsf = location.Transformation()
    rows = [trsf.Value(r, c) for r in range(1, 4) for c in range(1, 5)]
    return [*rows, 0.0, 0.0, 0.0, 1.0]


def build_tree_through_step(
    compound: Any,
    step_path: Path,
    *,
    root_name: str,
    force: bool = False,
    progress: Any | None = None,
    extra: dict[str, Any] | None = None,
    logger: Any | None = None,
    on_preview: Callable[[str, dict[str, Any]], None] | None = None,
    _internal_source_publication: bool = False,
    materials: object = None,
) -> tuple[str, dict[str, Any], dict[str, Any], str]:
    """Write STEP and return ``(result_hash, result_tree, stats, step_hash)``.

    The result preserves authored source geometry, grouping/appearance and child pins.
    ``stats['documentTree']`` names the separate byte-derived document tree;
    ``documentAppearance`` maps its leaf IDs to authored PBR numbers, and
    ``documentOccurrenceMap`` maps all authored flattened leaf/group IDs to
    canonical leaf-ID lists. ``documentNodeMap`` maps those same authored IDs
    to their exact written product nodes, preserving one-child group boundaries.
    These private publication fields are not tree content. The caller owns
    document indexes, annotations and final filenames.

    1. Walk the compound (:func:`_walk_compound`): own occurrences, links,
       grouping — and, for each own component, the returned shape.
    2. Prepare the document exactly as :func:`cadgen.store.materialize.materialize`
       would from the published tree (the in-memory draft flattened, links
       resolved from the store, own components read back from their BREP
       bytes). A bounded all-link result under the internal source publisher
       may capture and validate its private inputs here, then assemble ordinary
       occurrences and groups after the callback. Publish the final source
       result and notify the callback, which may await dependent saves, before
       writing the STEP. Direct callbacks retain complete preparation first.
    3. Re-read the STEP with the scene loader, reusing only a complete verified
       canonical document of the exact emitted bytes unless forced. Map every
       own occurrence to its
       node by id (``o1.2.3`` is the XCAF path, because the document's product
       tree mirrors the flattened grouping). Validate own occurrence placement
       and face-color survival without modifying the published source tree.
    4. Verify complete authored-to-written correspondence. A privately retained
       canonical readback keeps its exact selected component/tree identities;
       a raw parse goes through the canonical cold-import builder.

    Any own occurrence the re-read does not account for — no node at its id, a
    member without a shape, a placement that moved — is a hard error (law 10).
    Source and translated component identities may differ; a saved-file reader
    always resolves the canonical document tree by the file's actual bytes.
    """
    from contextlib import nullcontext

    from cadgen._internal.component_package import (
        decode_geometry_component,
        _normalized_face_colors,
    )
    from cadgen._internal.step_scene_loader import _selector_id, load_step_scene
    from cadgen._internal.step_scene_package import _lookup_document_readback
    from cadgen.step_export import export_build123d_step_file
    from cadgen.store.materialize import materialize_descriptor
    from cadgen.store.trees import flatten_tree

    def timed(label: str):
        return logger.timed(label) if logger is not None else nullcontext()

    progress = resolve_progress(progress)
    walk = _walk_compound(compound, root_name=root_name, progress=progress)

    # Only cadgen's own source-publication callback opts in. Arbitrary direct
    # on_preview callers retain their original construction/error ordering.
    snapshot = None
    prepared_document = None
    captured_bbox = None
    if _internal_source_publication and not force and not walk.shapes:
        from cadgen.store._descriptor_bounds import capture_links
        try:
            snapshot = capture_links(walk.draft_tree(root_name=root_name)).capture_appearance()
            # A scalar cache hit is not a native validity certificate. Preserve
            # pre-callback rejection of malformed BREP/placements on every path.
            prepared_document = snapshot.prepare_document()
            captured_bbox = snapshot.bounds(shapes=prepared_document._shapes)
        except (OSError, ValueError, TypeError, KeyError, RuntimeError, OverflowError):
            snapshot = None
            prepared_document = None
            captured_bbox = None

    # The document, assembled the way materialize() assembles a published tree
    # so the bytes do not depend on whether the tree existed yet.
    own_shapes: dict[str, Any] = {}
    for cid, prepared in walk.prepared.items():
        shape = prepared["shape"]
        if shape is None:
            # Authored pins have no saved-document substitute. The explicit
            # eager-only exception is handled only at saved-file reader doors.
            shape = decode_geometry_component(prepared["entry"], prepared["payload"])
        own_shapes[cid] = shape
    descriptor = snapshot.descriptor() if snapshot is not None else flatten_tree(walk.draft_tree(root_name=root_name))
    from cadgen._internal.source_sidecar import apply_appearance, resolve_materials

    inherited_appearance = descriptor.get("appearance")
    appearance = resolve_materials(descriptor, materials, inherited=inherited_appearance)
    if appearance is not None:
        descriptor = apply_appearance(descriptor, appearance)
    document = None
    if snapshot is None:
        with timed("tree: prepare document"):
            document = materialize_descriptor(descriptor, shapes=own_shapes, label=root_name)
    from cadgen.store.trees import tree_complete

    # This is the FINAL authored result, whether or not a UI is attached.
    # Persistence never substitutes STEP-translated prototypes into this tree.
    with timed("tree: source result"):
        tree_hash, tree, stats = _publish_tree(
            walk, bbox_shape=document, root_name=root_name,
            force=force, progress=progress, extra=extra,
            descriptor_bounds=snapshot is None,
            bbox_override=captured_bbox if snapshot is not None else None,
            appearance=appearance,
            base_appearance=inherited_appearance,
        )
        if not tree_complete(tree_hash):
            raise RuntimeError("source result components disappeared before publication")
        if on_preview is not None:
            on_preview(tree_hash, tree)
    if snapshot is not None:
        # Like today's already-constructed private document, these owned bytes
        # survive direct-callback store deletion. Existing wait_children and
        # pre-callback tree_complete checks still decide their normal failures.
        # Never resolve a newer pin or consult the authored shapes here.
        with timed("tree: prepare document"):
            document = prepared_document.materialize(root_name)
    with timed(f"tree: assemble STEP {step_path.name}"):
        step_path.parent.mkdir(parents=True, exist_ok=True)
        step_hash = export_build123d_step_file(document, step_path, logger=logger)

    with timed(f"tree: re-read STEP {step_path.name}"):
        readback, damaged_document = (None, False) if force else _lookup_document_readback(step_path, step_hash=step_hash)
        scene = readback.scene if readback is not None else None
        if scene is None:
            scene = load_step_scene(step_path, record_read=False)
    nodes: dict[str, Any] = {}
    stack = list(scene.roots)
    while stack:
        node = stack.pop()
        nodes[_selector_id(node.path)] = node
        stack.extend(node.children)

    with timed("tree: re-read components"):
        for occurrence in walk.occurrences:
            occ_id = str(occurrence["id"])
            node = nodes.get(occ_id)
            if node is None:
                raise RuntimeError(
                    f"{step_path.name}: occurrence {occ_id} ({occurrence.get('name')}) has no "
                    "product at that path in the STEP just written"
                )
            own_shape = walk.shapes.get(str(occurrence["component"]))
            _prototype, face_colors = _reread_component(
                scene, node, occurrence, step_path.name, written=getattr(own_shape, "wrapped", None)
            )
            if not _normalized_face_colors(face_colors) and getattr(own_shape, "cad_face_ordinal_colors", None):
                raise RuntimeError(
                    f"{step_path.name}: occurrence {occ_id} ({occurrence.get('name')}) was "
                    "written with per-face colours the STEP does not carry back"
                )
    with timed("tree: canonical document"):
        if readback is not None and readback.tree_hash is not None:
            # Only this internal call owns the verified closure and the scene
            # decoded from it. Public mutable scenes never acquire authority
            # to reuse a tree through an attribute, digest, or document index.
            parsed_leaves, parsed_nodes = readback.canonical_maps()
        else:
            document_hash, _document_tree, _document_stats, parsed_leaves, parsed_nodes = _publish_document_scene(
                scene, force=force or damaged_document, progress=progress,
                repair_objects=True,
            )
        occurrence_map, appearance, node_map = _document_correspondence(
            descriptor, scene, parsed_leaves, parsed_nodes,
            root_name=root_name, step_name=step_path.name,
        )
        if readback is not None and readback.tree_hash is not None:
            # Keep the snapshot until correspondence succeeds. Restore exact
            # bytes if GC/damage raced the read, without re-encoding native
            # shapes (a decode/encode need not be a byte fixed point).
            document_hash = readback.restore()
    stats["documentTree"] = document_hash
    stats["documentAppearance"] = appearance
    stats["documentOccurrenceMap"] = occurrence_map
    stats["documentNodeMap"] = node_map
    return tree_hash, tree, stats, step_hash
