"""Build-time kinematics resolution: refs -> numbers.

One job, against the freshly built tree, before the sidecar is written:
every mate's parent/child occurrence ref must name a real occurrence, and every
``axis={"ref": ...}`` selector becomes world-at-rest ``{"origin", "dir"}``
numbers via the same composed selector index inspect uses. The sidecar carries
only numbers — the viewer does arithmetic, never topology.

Every ref resolves through the one resolver (``cadgen.refs``). A mate's ends
name occurrences, so they resolve in the tree's occurrence namespace alone: its
leaves, its group nodes and their names, read from the flattened tree. No
component's topology is read for them. An axis ref names a face or edge of one
occurrence, and only that occurrence's component is read: its selector rows
come from its part's selector table, derived through the build pool when the
store has none, and a ref by geometry is matched against the component. An
axis through a face whose parameters give no origin of its own -- a torus's,
which give its centre -- passes through the face's exact centroid, which no
selector row carries: it is measured on the stored component then, and only
then (``store.parts.measure_face``).

Nothing here moves geometry. A kinematics declaration describes how the
written tree articulates; the tree itself is the model's return value and is
stored exactly as returned.
"""

from __future__ import annotations

import copy
from typing import Any, Callable, Mapping


def _fail(message: str) -> ValueError:
    return ValueError(f"kinematics: {message}")


def _occurrence_index(descriptor: Mapping[str, Any]):
    """The selector index an axis ref resolves in, before any component is read: the
    tree's leaf occurrences and its group nodes, the composed selector index inspect uses
    (``assembly_lookup.index_with_assembly_occurrences``) without any component's
    topology, which :func:`_with_named_entities` adds for the leaves axis refs name."""
    from cadgen.assembly_lookup import merge_assembly_occurrences
    from cadgen.lookup import build_selector_index

    return merge_assembly_occurrences(build_selector_index(dict(descriptor)), descriptor, None)


def _with_named_entities(index, descriptor: Mapping[str, Any], refs: list[str], *, tree_hash: str,
                         producer: dict | None, ready: Callable[[], None] | None):
    """``index`` plus the shapes, faces, edges and vertices of every leaf an
    axis ref in ``refs`` names, placed exactly as the composed index places
    them (``assembly_lookup.merge_assembly_entities``). Each row is a function
    of its occurrence's placement and its part's selector table alone, so an axis
    resolves to the same numbers as it would against every occurrence's rows.
    A ref that names no leaf's entity reads nothing, and fails as it would
    have: the composed index holds entities for leaves only. ``ready`` is called
    before any table is read (the build's display job, done)."""
    import shutil

    from cadgen.assembly_lookup import merge_assembly_entities
    from cadgen.lookup import index_space
    from cadgen.refs import locate
    from cadgen.store.parts import producer_identity
    from cadgen.store.view import export_view

    named: set[str] = set()
    space = index_space(index)
    for ref in refs:
        try:
            occurrence, element = locate(ref, space)
        except ValueError:
            continue
        if element is not None:
            named.add(occurrence)
    rows = [row for row in descriptor.get("occurrences") or []
            if isinstance(row, Mapping) and str(row.get("id") or "").strip() in named
            and str(row.get("component") or "").strip()]
    if not rows:
        return index
    cids = list(dict.fromkeys(str(row["component"]).strip() for row in rows))
    # The tables are the parts' display data: the build's display job derives its own,
    # and the view asks the build pool for any the store still lacks, never this process.
    if ready is not None:
        ready()
    view = export_view(tree_hash, producer=producer or producer_identity(), cids=cids)
    try:
        return merge_assembly_entities(index, {**descriptor, "occurrences": rows}, view)
    finally:
        shutil.rmtree(view, ignore_errors=True)


def _face_centroid(row: Mapping[str, Any], descriptor: Mapping[str, Any], tree_hash: str) -> list[float] | None:
    """The face row's exact centroid, where its occurrence places it: measured on the stored
    component the occurrence places (``store.parts.measure_face``, remembered by its BREP), and
    placed as the composed index places the row (``assembly_lookup``)."""
    from cadgen.assembly_lookup import _matrix, transform_point
    from cadgen.store.parts import measure_face

    owner = str(row.get("occurrenceId") or "")
    occurrence = next((entry for entry in descriptor.get("occurrences") or []
                       if isinstance(entry, Mapping) and str(entry.get("id") or "") == owner), None)
    if occurrence is None or not isinstance(row.get("ordinal"), int):
        return None
    measured = measure_face(tree_hash, str(occurrence.get("component") or ""), row["ordinal"])
    return transform_point(_matrix(occurrence.get("transform")), measured["center"])


def _axis_from_ref(index, ref: str, *, mate: str, source_ref: str,
                   centroid: Callable[[Mapping[str, Any]], list[float] | None]) -> dict[str, list[float]]:
    """The world-at-rest axis ``ref`` names in ``index``. ``centroid(row)`` is a face row's exact
    centroid, asked for only by an axis whose face's parameters give no origin."""
    from cadgen.analysis import positioning_facts_for_row
    from cadgen.lookup import find

    try:
        selector_type, row = find(ref, index)
    except ValueError as error:
        raise _fail(
            f"{source_ref} mate {mate!r}: axis ref {ref!r} does not resolve ({error}) — "
            "use `read_scene(path).leaves()` and `occurrence.entities(kind)` to list saved selectors and labels"
        ) from None
    if row is None:
        raise _fail(f"{source_ref} mate {mate!r}: axis ref {ref!r} names a group; an axis needs a face or edge")
    if selector_type == "occurrence":
        raise _fail(
            f"{source_ref} mate {mate!r}: axis ref {ref!r} names a whole occurrence; "
            "an axis needs a face or edge (a cylindrical face or circular edge "
            "yields its axis, a planar face its normal) or literal origin=/direction="
        )
    facts = positioning_facts_for_row(selector_type, row, index)
    direction = facts.get("axisVector") or facts.get("normal") or facts.get("direction")
    if selector_type == "face" and direction is not None and "origin" not in (row.get("params") or {}):
        facts = positioning_facts_for_row(selector_type, {**row, "center": centroid(row)}, index)
    origin = facts.get("origin") or facts.get("center") or facts.get("point")
    if not (isinstance(direction, list) and isinstance(origin, list)):
        kind = facts.get("kind") or selector_type
        raise _fail(
            f"{source_ref} mate {mate!r}: axis ref {ref!r} resolves to a {kind}, "
            "which defines no axis — pick a cylindrical face, circular edge, or "
            "planar face, or pass literal origin=/direction="
        )
    return {"origin": [float(v) for v in origin], "dir": [float(v) for v in direction]}


def _occurrence_id_for_ref(ref: str, *, what: str, mate: str, source_ref: str, space: Any) -> str:
    """The instance tree node a mate's end names, groups included: a mate on a group is
    how "rigid groups are free" (``cadgen.refs``, over the tree's nodes)."""
    from cadgen.label_refs import LabelResolutionError
    from cadgen.refs import resolve

    try:
        found = resolve(ref, space)
    except LabelResolutionError as error:
        raise _fail(f"{source_ref} mate {mate!r}: {what} {ref!r}: {error}") from None
    except ValueError:
        found = None
    if found is not None and found.kind == "occurrence":
        return found.occurrence
    raise _fail(
        f"{source_ref} mate {mate!r}: {what} {ref!r} does not name an occurrence — "
        "label the part or subassembly in the model (cadgen.label_shape, or a "
        "Compound label) or use its occurrence token; `read_scene(path).leaves()` "
        "lists the leaf occurrences"
    )


def resolve_kinematics_block(
    block: Mapping[str, Any], *, tree_hash: str, source_ref: str, producer: dict | None = None,
    ready: Callable[[], None] | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Validated declaration -> sidecar-ready block (axes as numbers), plus the
    mate-ref -> occurrence-id map, against the stored tree ``tree_hash``.

    ``producer`` is the display producer an axis ref's part is derived under;
    None resolves it through the build pool, and only when an axis ref needs it.
    ``ready``, when given, is called before an axis ref reads a part's selector
    table: a build waits there for its display job, which derives its parts."""
    from cadgen.refs import descriptor_space
    from cadgen.store.trees import flatten

    descriptor = flatten(tree_hash)
    if not isinstance(descriptor, dict):
        raise _fail(f"{source_ref}: tree {tree_hash} is missing from the store")
    tree = descriptor_space(descriptor)
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
                    ref, what=what, mate=name, source_ref=source_ref, space=tree
                )
            # The resolved instance-tree token rides the sidecar beside the
            # authored label, for the same reason axes ride it as numbers: the
            # viewer does arithmetic and reads the tree for a node's leaves,
            # never topology or label resolution of its own.
            mate[f"{key}Id"] = occurrence_ids[ref]
        axis = mate.get("axis") or {}
        if mate.get("kind") == "fastened":
            continue
        if "ref" in axis:
            if entities is None:
                entities = _with_named_entities(index, descriptor, axis_refs, tree_hash=tree_hash, producer=producer,
                                                ready=ready)
            mate["axis"] = _axis_from_ref(entities, str(axis["ref"]), mate=name, source_ref=source_ref,
                                          centroid=lambda row: _face_centroid(row, descriptor, tree_hash))
    return resolved, occurrence_ids
