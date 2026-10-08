"""Compose an all-link parent's saved-document tree from its children's.

A parent that returns only placed children writes a STEP whose products are
the children's documents again: ``materialize_descriptor`` places every leaf
at its flattened world transform and every group at the identity, and the
writer emits each child's prototypes from the same bytes the child's own save
emitted. A child's read-back is therefore context-free: the components,
hierarchy, names, colours and the linear part of every leaf placement read
back from the parent's STEP are exactly those in the child's own document
tree, and only each leaf's translation is new. That translation is the one
number the parent's descriptor hands the writer, ``fl(child + link)``, and
what the reader gives back for it is its STEP text round trip
(:func:`written_real`). So the parent's canonical document tree can be
composed, bit for bit, without parsing the STEP the build just wrote.

Eligibility is exact and every other case takes the ordinary read-back:

- the parent result is links only (no own geometry);
- every link placement is a pure translation (its linear part is exactly the
  identity) with no link colour, and every link and group name survives
  ``_normalize_label_name``;
- every child's document tree is pinned by its record for the tree the parent
  used, is complete, has an assembly root, holds only native components, and
  names every node by a name that survives ``_normalize_label_name``;
- every leaf box the canonical bounds path would take is already in
  ``index/bounds`` under the child's publication, with a leaf layout whose
  leaves all sit at the prototype's placement;
- the writer emulation reproduces every translation in each child's own
  document from that child's descriptor (checked here, every time).

Nothing here consults a record or a source file: the caller resolves child
pins to document trees, and composition reads objects and the bounds index.
"""
from __future__ import annotations

import copy
import math
import struct
from typing import Any, Callable, Mapping

from cadgen.store.trees import _rebase_id

STEP_REAL_RANGE = (0.1, 1000.0)
STEP_REAL_RANGE_WIDTH = 15


class Ineligible(ValueError):
    """The ordinary STEP read-back must build this document tree."""


def written_text(value: float) -> str:
    """The text cadgen's writer prints for the finite real ``value``.

    A real within ``[0.1, 1000)`` in magnitude takes twelve decimals cut to
    fifteen characters (sign included), and any other real thirteen
    significant digits in exponent form; trailing zeros are dropped and zero of
    either sign is written ``0.``. A test pins this against the real writer.
    """
    if value == 0.0:
        return "0."
    if STEP_REAL_RANGE[0] <= abs(value) < STEP_REAL_RANGE[1]:
        return ("%.12f" % value)[:STEP_REAL_RANGE_WIDTH].rstrip("0")
    mantissa, exponent = ("%.12E" % value).split("E")
    return mantissa.rstrip("0") + "E" + exponent


def written_real(value: float) -> float:
    """The number OCCT's STEP reader returns for ``value`` after cadgen's writer
    printed it (:func:`written_text`): the nearest double to that text.
    :func:`compose_document_tree` checks this against every child's own
    document before trusting it for the parent's.
    """
    value = float(value)
    if not math.isfinite(value):
        raise Ineligible("non-finite placement")
    return float(written_text(value)) + 0.0


def _same_bits(a: float, b: float) -> bool:
    return a == b and math.copysign(1.0, a) == math.copysign(1.0, b)


def pure_translation(transform: Any) -> bool:
    """Whether ``transform`` (16 numbers, row-major) only translates."""
    if type(transform) is not list or len(transform) != 16:
        return False
    if any(type(value) not in (float, int) or not math.isfinite(value) for value in transform):
        return False
    linear = [transform[i] for i in (0, 1, 2, 4, 5, 6, 8, 9, 10)]
    return linear == [1, 0, 0, 0, 1, 0, 0, 0, 1] and transform[12:] == [0, 0, 0, 1]


def _named(node: Mapping[str, Any]) -> str:
    from cadgen._internal.step_scene_loader import _normalize_label_name

    name = node.get("name")
    if type(name) is not str or not name or name == node.get("id"):
        raise Ineligible(f"child document node {node.get('id')!r} has no name of its own")
    # A child's document tree compiled under an older name rule (one that kept an
    # XCAF label entry as a name) is not what the parent's bytes read back as now.
    if _normalize_label_name(name) != name:
        raise Ineligible(f"child document node {node.get('id')!r} has a name the read-back does not keep")
    return name


def compose_document_tree(
    *,
    walk: Any,
    descriptor: Mapping[str, Any],
    root_name: str,
    child_documents: Mapping[str, str],
) -> dict[str, Any]:
    """The canonical document tree the read-back of ``walk``'s STEP would
    publish, from the children's document trees. Raises :class:`Ineligible`.

    ``walk`` is the parent's packaged result, ``descriptor`` the flattened
    authored tree the STEP was assembled from, ``child_documents`` maps each
    pinned child tree hash to that child's document tree hash.
    """
    from cadgen._internal.glb_topology import (
        STEP_EDGE_DEFAULT_RENDER_VISIBILITY_CLASSES, step_topology_capabilities,
    )
    from cadgen._internal.step_scene_loader import _normalize_label_name
    from cadgen.store.trees import TREE_KIND, TREE_SCHEMA, _validate_structure, flatten, get_tree, tree_kind

    if walk.occurrences or walk.components or not walk.links:
        raise Ineligible("the parent has geometry of its own")
    root_label = _normalize_label_name(root_name)
    if root_label is None:
        raise Ineligible("the root name does not survive the STEP round trip")
    links_by_id = {str(link["id"]): link for link in walk.links}
    written = {}
    for occurrence in descriptor.get("occurrences") or ():
        if type(occurrence) is not dict or type(occurrence.get("id")) is not str:
            raise Ineligible("malformed descriptor occurrence")
        written[occurrence["id"]] = occurrence.get("transform")

    components: dict[str, dict[str, Any]] = {}
    occurrences: list[dict[str, Any]] = []
    documents: dict[str, dict[str, Any]] = {}

    def child_document(link: Mapping[str, Any]) -> dict[str, Any]:
        tree_hash = str(link["tree"])
        cached = documents.get(tree_hash)
        if cached is not None:
            return cached
        document_hash = child_documents.get(tree_hash)
        if not document_hash:
            raise Ineligible(f"no pinned document tree for child {link.get('name')!r}")
        document = get_tree(str(document_hash))
        if document is None:
            raise Ineligible(f"document tree {document_hash} of child {link.get('name')!r} is unreadable")
        if document.get("links") or document.get("entryKind") != "assembly":
            raise Ineligible(f"child {link.get('name')!r} is not a saved assembly")
        root = document["assembly"]["root"]
        if root.get("nodeType") != "assembly" or not root.get("children"):
            raise Ineligible(f"child {link.get('name')!r} has no assembly root")
        for entry in document["components"].values():
            if entry.get("kind") != "native":
                raise Ineligible(f"child {link.get('name')!r} holds a component without native geometry")
        # The writer emulation must reproduce what this child's own save read
        # back from this child's own descriptor, translation by translation.
        source = flatten(tree_hash)
        if source is None:
            raise Ineligible(f"source tree of child {link.get('name')!r} is unreadable")
        authored = {str(row.get("id")): row.get("transform") for row in source.get("occurrences") or ()}
        for row in document["occurrences"]:
            transform = authored.get(str(row["id"]))
            if type(transform) is not list or len(transform) != 16:
                raise Ineligible(f"child {link.get('name')!r} reads back leaves its result does not place")
            for index in (3, 7, 11):
                if not _same_bits(written_real(transform[index]), float(row["transform"][index])):
                    raise Ineligible(f"the writer emulation does not reproduce child {link.get('name')!r}")
        documents[tree_hash] = document
        return document

    def link_subtree(link: Mapping[str, Any]) -> dict[str, Any]:
        link_id = str(link["id"])
        if link.get("color") is not None:
            raise Ineligible(f"link {link.get('name')!r} carries a colour")
        if not pure_translation(link.get("transform")):
            raise Ineligible(f"link {link.get('name')!r} is not a pure translation")
        name = _normalize_label_name(link.get("name"))
        if name is None:
            raise Ineligible(f"link {link.get('name')!r} has no name that survives the STEP round trip")
        document = child_document(link)
        rows = {str(row["id"]): row for row in document["occurrences"]}
        for cid, entry in document["components"].items():
            components.setdefault(cid, copy.deepcopy(entry))

        def convert(node: Mapping[str, Any]) -> dict[str, Any]:
            node_id = _rebase_id(link_id, str(node["id"]))
            node_name = _named(node)
            children = node.get("children") or []
            if children:
                converted = [convert(child) for child in children]
                return {"id": node_id, "name": node_name, "nodeType": "subassembly",
                        "leafPartIds": [leaf for child in converted for leaf in child["leafPartIds"]],
                        "children": converted}
            row = rows.get(str(node["id"]))
            if row is None:
                raise Ineligible(f"child {link.get('name')!r} leaf {node['id']} has no geometry row")
            placement = written.get(node_id)
            if type(placement) is not list or len(placement) != 16:
                raise Ineligible(f"the parent's descriptor does not place {node_id}")
            occurrence = copy.deepcopy(row)
            occurrence["id"] = node_id
            occurrence["name"] = node_name
            transform = [float(value) for value in row["transform"]]
            for index in (3, 7, 11):
                transform[index] = written_real(placement[index])
            occurrence["transform"] = transform
            occurrences.append(occurrence)
            return {"id": node_id, "name": node_name, "nodeType": "part",
                    "leafPartIds": [node_id], "children": []}

        subtree = convert(document["assembly"]["root"])
        subtree["name"] = name
        subtree["nodeType"] = "subassembly"
        return subtree

    def convert_authored(node: Mapping[str, Any], *, root: bool = False) -> dict[str, Any]:
        node_id = str(node.get("id") or "")
        node_type = node.get("nodeType")
        if node_type == "link":
            link = links_by_id.get(node_id)
            if link is None:
                raise Ineligible(f"authored link {node_id} has no link row")
            return link_subtree(link)
        if node_type != ("assembly" if root else "subassembly"):
            raise Ineligible(f"authored node {node_id} is not a group of links")
        if root:
            name = root_label
        else:
            name = _normalize_label_name(node.get("name"))
            if name is None:
                raise Ineligible(f"group {node.get('name')!r} has no name that survives the STEP round trip")
        children = [convert_authored(child) for child in node.get("children") or []]
        if not children:
            raise Ineligible(f"authored group {node_id} places nothing")
        return {"id": node_id, "name": name, "nodeType": node_type,
                "leafPartIds": [leaf for child in children for leaf in child["leafPartIds"]],
                "children": children}

    root = convert_authored(walk.root, root=True)
    if not occurrences:
        raise Ineligible("the composed document places nothing")
    tree: dict[str, Any] = {
        "capabilities": step_topology_capabilities(),
        "edgeRendering": {"visibilityClasses": list(STEP_EDGE_DEFAULT_RENDER_VISIBILITY_CLASSES)},
        "label": root_label,
        "units": "mm",
        "components": components,
        "occurrences": occurrences,
        "links": [],
        "assembly": {"root": root},
        "kind": TREE_KIND,
        "schemaVersion": TREE_SCHEMA,
    }
    tree["entryKind"] = tree_kind(tree)
    tree["bbox"] = composed_bounds(occurrences, components)
    tree["stats"] = {"occurrenceCount": len(occurrences), "linkCount": 0}
    _validate_structure(tree, native=True)
    return tree


def composed_bounds(occurrences: list[dict[str, Any]], components: Mapping[str, Mapping[str, Any]]) -> dict[str, list[float]]:
    """The box canonical publication measures for these occurrences, from the
    per-leaf boxes it already remembered in ``index/bounds``.

    Each leaf's key is its component's codec and BREP object, its ordinal and
    the placement's rotation; a leaf layout whose leaves all sit at the
    prototype's placement makes that rotation the occurrence's own. A layout
    the index does not hold is measured from the component's bytes and
    remembered. A box it does not hold is :class:`Ineligible`: measuring one
    here would place the prototype from serialized numbers, which can differ
    from the native placement by ulps.
    """
    from cadgen._internal.component_package import component_leaf_layout, decode_geometry_component
    from cadgen.store.bounds import cached_leaf_layout, remembered_box
    from cadgen.store.build import _PREPARED_OCCURRENCE_BOUNDS_ALGORITHM
    from cadgen.store.objects import read_verified_object

    layouts: dict[str, dict[str, Any]] = {}
    boxes: list[list[float]] = []
    for occurrence in occurrences:
        cid = str(occurrence["component"])
        entry = components[cid]
        codec, brep = str(entry["codec"]), str(entry["brep"])
        layout = layouts.get(cid)
        if layout is None:
            # A child published before layouts were recorded decodes once here;
            # the layout is a pure function of the bytes and is remembered.
            layout = cached_leaf_layout(codec, brep, lambda entry=entry: component_leaf_layout(
                decode_geometry_component(entry, read_verified_object(entry["brep"])).wrapped))
            layouts[cid] = layout
        if not layout["placed"]:
            raise Ineligible(f"component {cid} places a leaf of its own")
        transform = occurrence["transform"]
        linear = struct.pack("<12d", transform[0], transform[1], transform[2], 0.0,
                             transform[4], transform[5], transform[6], 0.0,
                             transform[8], transform[9], transform[10], 0.0)
        translation = (transform[3], transform[7], transform[11])
        for leaf_ordinal in range(1, layout["leaves"] + 1):
            found, box = remembered_box(_PREPARED_OCCURRENCE_BOUNDS_ALGORITHM, (codec, brep, leaf_ordinal, linear))
            if not found:
                raise Ineligible(f"leaf {leaf_ordinal} of component {cid} has no remembered box in this placement")
            if box is not None:
                boxes.append([float(value) + translation[index % 3] for index, value in enumerate(box)])
    if not boxes:
        raise Ineligible("no leaf has bounds")
    return {
        "min": [min(box[axis] for box in boxes) for axis in range(3)],
        "max": [max(box[axis] for box in boxes) for axis in range(3, 6)],
    }


def compose_document_readback(
    *,
    walk: Any,
    descriptor: Mapping[str, Any],
    step_path: Any,
    step_hash: str,
    root_name: str,
    child_documents: Callable[[], Mapping[str, str]],
    logger: Any | None = None,
) -> Any | None:
    """A private canonical read-back of the STEP at ``step_path`` composed from
    the children's document trees, or None when the ordinary parse must run.

    The composed tree is published as an object first, then captured and
    verified exactly as an indexed read-back of already-seen bytes is
    (``_readback_from_document_tree``), so everything downstream — the
    correspondence check, the canonical maps, the restore — is the same code.
    """
    from OCP.Standard import Standard_Failure

    from cadgen._internal.component_package import NativeUnavailable
    from cadgen._internal.step_scene_package import _readback_from_document_tree
    from cadgen.store.trees import put_tree

    try:
        tree = compose_document_tree(
            walk=walk, descriptor=descriptor, root_name=root_name, child_documents=child_documents(),
        )
        tree_hash = put_tree(tree, repair=True)
        readback = _readback_from_document_tree(step_path, step_hash=step_hash, tree_hash=tree_hash, lazy=True)
    except Ineligible as reason:
        if logger is not None:
            logger.debug(f"document composed from children: no ({reason})")
        return None
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError, NativeUnavailable,
            Standard_Failure) as error:
        if logger is not None:
            logger.debug(f"document composed from children: no ({type(error).__name__}: {error})")
        return None
    if readback is None:
        return None
    if logger is not None:
        logger.debug(f"document composed from children: {len(walk.links)} links, {len(tree['occurrences'])} occurrences")
    return readback
