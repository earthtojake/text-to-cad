"""Build-time kinematics resolution: refs -> numbers.

One job, against the freshly built tree, before the sidecar is written:
every mate's parent/child occurrence ref must name a real occurrence, and every
``axis={"ref": ...}`` selector becomes world-at-rest ``{"origin", "dir"}``
numbers via the same composed selector index inspect uses. The sidecar carries
only numbers — the viewer does arithmetic, never topology.

A mate's ends name occurrences, so they resolve in the tree's occurrence
namespace alone: its leaves, its group nodes and their labels, read from the
flattened tree. No component's topology is read for them. An axis ref names a
face or edge of one occurrence, and only that occurrence's component is read:
its selector rows come from its SURF, derived through the build pool when the
store has none.

Nothing here moves geometry. A kinematics declaration describes how the
written tree articulates; the tree itself is the model's return value and is
stored exactly as returned.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from cadgen.label_refs import TreeNames


def _fail(message: str) -> ValueError:
    return ValueError(f"kinematics: {message}")


def _occurrence_index(descriptor: Mapping[str, Any]):
    """The namespace a mate's parent and child resolve in: the tree's leaf
    occurrences, its group nodes and the label aliases of both. It is the
    composed selector index inspect uses
    (``assembly_lookup.index_with_assembly_occurrences``) without any
    component's topology, which a mate's end never names."""
    from cadgen.assembly_lookup import merge_assembly_occurrences
    from cadgen.label_refs import attach_label_aliases
    from cadgen.lookup import build_selector_index

    index = build_selector_index(dict(descriptor))
    return attach_label_aliases(merge_assembly_occurrences(index, descriptor, None))


_ENTITY_TYPES = frozenset({"shape", "face", "edge", "vertex"})


def _with_named_entities(index, descriptor: Mapping[str, Any], refs: list[str], *, tree_hash: str,
                         producer: dict | None):
    """``index`` plus the shapes, faces, edges and vertices of every leaf an
    axis ref in ``refs`` names, placed exactly as the composed index places
    them (``assembly_lookup.merge_assembly_entities``). Each row is a function
    of its occurrence's placement and its component's SURF alone, so an axis
    resolves to the same numbers as it would against every occurrence's rows.
    A ref that names no leaf's entity reads nothing, and fails as it would
    have: the composed index holds entities for leaves only."""
    import shutil

    from cadgen import cad_ref_syntax as syntax
    from cadgen.assembly_lookup import merge_assembly_entities
    from cadgen.lookup import canonicalize_selector
    from cadgen.store.view import export_view

    named: set[str] = set()
    for ref in refs:
        canonical = canonicalize_selector(ref.lstrip("#"), index)
        parsed = syntax.parse_selector(canonical) if canonical else None
        if parsed is not None and parsed.occurrence_id and parsed.selector_type in _ENTITY_TYPES:
            named.add(parsed.occurrence_id)
    rows = [row for row in descriptor.get("occurrences") or []
            if isinstance(row, Mapping) and str(row.get("id") or "").strip() in named
            and str(row.get("component") or "").strip()]
    if not rows:
        return index
    cids = list(dict.fromkeys(str(row["component"]).strip() for row in rows))
    view = export_view(tree_hash, producer=producer, cids=cids)
    try:
        return merge_assembly_entities(index, {**descriptor, "occurrences": rows}, view)
    finally:
        shutil.rmtree(view, ignore_errors=True)


def _lookup(index, selector_text: str):
    from cadgen import lookup

    return lookup.lookup_selector(selector_text, index)


def _axis_from_ref(index, ref: str, *, mate: str, source_ref: str) -> dict[str, list[float]]:
    from cadgen.analysis import positioning_facts_for_row
    from cadgen.lookup import label_resolution_error

    selector = ref.lstrip("#")
    resolved = _lookup(index, selector)
    if resolved is None:
        reason = label_resolution_error(selector, index)
        if reason is not None:
            raise _fail(f"{source_ref} mate {mate!r}: axis ref {ref!r}: {reason}")
        raise _fail(
            f"{source_ref} mate {mate!r}: axis ref {ref!r} does not resolve — "
            "use `read_scene(path).leaves()` and `occurrence.entities(kind)` to list saved selectors and labels"
        )
    selector_type, row = resolved
    if selector_type == "occurrence":
        raise _fail(
            f"{source_ref} mate {mate!r}: axis ref {ref!r} names a whole occurrence; "
            "an axis needs a face or edge (a cylindrical face or circular edge "
            "yields its axis, a planar face its normal) or literal origin=/direction="
        )
    facts = positioning_facts_for_row(selector_type, row, index)
    direction = facts.get("axisVector") or facts.get("normal") or facts.get("direction")
    origin = facts.get("origin") or facts.get("center") or facts.get("point")
    if not (isinstance(direction, list) and isinstance(origin, list)):
        kind = facts.get("kind") or selector_type
        raise _fail(
            f"{source_ref} mate {mate!r}: axis ref {ref!r} resolves to a {kind}, "
            "which defines no axis — pick a cylindrical face, circular edge, or "
            "planar face, or pass literal origin=/direction="
        )
    return {"origin": [float(v) for v in origin], "dir": [float(v) for v in direction]}


def _instance_tree_ids(descriptor: Mapping[str, Any]) -> tuple[dict[str, str], TreeNames]:
    """The INSTANCE TREE's node ids and names — subassemblies included.

    The flat selector index holds LEAF occurrences only, but mates target the
    instance-tree namespace: a mate on a group occurrence is how "rigid groups
    are free", and ``_subtree_ids`` already carries a group's whole subtree. So
    group nodes have to be resolvable, and ``assembly.json["assembly"]["root"]``
    is where they live. A name resolves as every ``#name`` does
    (:class:`cadgen.label_refs.TreeNames`).
    """
    from cadgen.label_refs import TreeNames

    by_id: dict[str, str] = {}
    by_name: dict[str, list[str]] = {}
    root = (descriptor.get("assembly") or {}).get("root") if isinstance(descriptor.get("assembly"), Mapping) else None
    stack = [root] if isinstance(root, Mapping) else []
    while stack:
        node = stack.pop()
        if not isinstance(node, Mapping):
            continue
        node_id = str(node.get("id") or "").strip()
        if node_id:
            by_id[node_id] = node_id
            name = str(node.get("name") or "").strip()
            if name:
                by_name.setdefault(name, []).append(node_id)
        stack.extend(node.get("children") or [])
    return by_id, TreeNames(by_name)


def _occurrence_id_for_ref(
    ref: str, *, what: str, mate: str, source_ref: str, tree: tuple[dict[str, str], TreeNames]
) -> str:
    from cadgen.label_refs import LabelResolutionError

    selector = ref.lstrip("#")
    by_id, names = tree
    if selector in by_id:
        return by_id[selector]
    try:
        node_id = names.resolve(selector)
    except LabelResolutionError as error:
        raise _fail(f"{source_ref} mate {mate!r}: {what} {ref!r}: {error}") from None
    if node_id is not None:
        return node_id
    raise _fail(
        f"{source_ref} mate {mate!r}: {what} {ref!r} does not name an occurrence — "
        "label the part or subassembly in the model (cadgen.label_shape, or a "
        "Compound label) or use its occurrence id; `read_scene(path).leaves()` "
        "lists the leaf occurrences"
    )


def remap_document_kinematics(
    block: Mapping[str, Any],
    occurrence_map: Mapping[str, list[str]],
    document_node_map: Mapping[str, str],
    document_tree: str,
) -> dict[str, Any]:
    """Bind resolved authored mates to their verified canonical product nodes.

    Axes are already world-space numbers. Structural correspondence supplies
    the exact written product; its canonical descendant set must still equal
    the independently recorded authored leaf set. This preserves nested
    single-child groups, which leaf sets alone cannot distinguish.
    """
    from cadgen.store.trees import flatten

    descriptor = flatten(document_tree)
    if descriptor is None:
        raise FileNotFoundError(f"document tree missing: {document_tree}")
    leaves = {str(item["id"]) for item in descriptor.get("occurrences") or []}
    node_leaves: dict[str, frozenset[str]] = {}

    def visit(node):
        node_id = str(node.get("id") or "")
        members = {node_id} if node_id in leaves else set()
        for child in node.get("children") or []:
            members.update(visit(child))
        if node_id:
            node_leaves[node_id] = frozenset(members)
        return members

    visit((descriptor.get("assembly") or {}).get("root") or {})
    resolved = copy.deepcopy(dict(block))
    for mate in resolved.get("mates") or []:
        for key in ("parentId", "childId"):
            authored_id = str(mate.get(key) or "")
            members = frozenset(occurrence_map.get(authored_id) or [])
            document_id = str(document_node_map.get(authored_id) or "")
            if not members or document_id not in node_leaves:
                raise ValueError(f"mate {mate.get('name')}: {key} {authored_id} has no exact document subtree")
            if node_leaves[document_id] != members:
                raise ValueError(
                    f"mate {mate.get('name')}: {key} {authored_id} document subtree does not match its exact leaves"
                )
            mate[key] = document_id
    return resolved


def resolve_kinematics_block(
    block: Mapping[str, Any], *, tree_hash: str, source_ref: str, producer: dict | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Validated declaration -> sidecar-ready block (axes as numbers), plus the
    mate-ref -> occurrence-id map, against the stored tree ``tree_hash``.

    ``producer`` is the display producer an axis ref's SURF is derived under;
    None resolves it through the build pool, and only when an axis ref needs it."""
    from cadgen.store.trees import flatten

    descriptor = flatten(tree_hash)
    if not isinstance(descriptor, dict):
        raise _fail(f"{source_ref}: tree {tree_hash} is missing from the store")
    tree = _instance_tree_ids(descriptor)
    resolved = copy.deepcopy(dict(block))
    occurrence_ids: dict[str, str] = {}
    axis_refs = [str((mate.get("axis") or {})["ref"]) for mate in resolved.get("mates", [])
                 if mate.get("kind") != "fastened" and "ref" in (mate.get("axis") or {})]
    # Only an axis ref reads the selector index.
    index = _occurrence_index(descriptor) if axis_refs else None
    entities = None
    for mate in resolved.get("mates", []):
        name = str(mate.get("name"))
        for what, key in (("parent", "parent"), ("child", "child")):
            ref = str(mate.get(key))
            if ref not in occurrence_ids:
                occurrence_ids[ref] = _occurrence_id_for_ref(
                    ref, what=what, mate=name, source_ref=source_ref, tree=tree
                )
            # The resolved instance-tree id rides the sidecar beside the
            # authored label, for the same reason axes ride it as numbers: the
            # viewer does arithmetic and id-prefix subtree matching, never
            # topology or label resolution of its own.
            mate[f"{key}Id"] = occurrence_ids[ref]
        axis = mate.get("axis") or {}
        if mate.get("kind") == "fastened":
            continue
        if "ref" in axis:
            if entities is None:
                entities = _with_named_entities(index, descriptor, axis_refs, tree_hash=tree_hash, producer=producer)
            mate["axis"] = _axis_from_ref(entities, str(axis["ref"]), mate=name, source_ref=source_ref)
    return resolved, occurrence_ids
