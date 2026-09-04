"""Build-time kinematics resolution: refs -> numbers.

One job, against the freshly built tree, before the sidecar is written:
every mate's parent/child occurrence ref must name a real occurrence, and every
``axis={"ref": ...}`` selector becomes world-at-rest ``{"origin", "dir"}``
numbers via the same composed selector index inspect uses. The sidecar carries
only numbers — the viewer does arithmetic, never topology.

Nothing here moves geometry. A kinematics declaration describes how the
written tree articulates; the tree itself is the model's return value and is
stored exactly as returned.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping


def _fail(message: str) -> ValueError:
    return ValueError(f"kinematics: {message}")


def _composed_index(package_dir: Path, *, step_path: Path, source_ref: str):
    """The composed selector index for a view directory (staging or final):
    descriptor as the (empty-tabled) bundle manifest, component GLBs supplying
    every ref per occurrence — the same shape ``_assembly_topology_artifact``
    returns for require_selector consumers."""
    from cadgen._internal.component_package import read_package_descriptor
    from cadgen.assembly_lookup import index_with_assembly_occurrences
    from cadgen.lookup import build_selector_index
    from cadgen.selector_types import SelectorBundle
    from cadgen.step_topology_artifact import StepTopologyArtifact

    descriptor = read_package_descriptor(package_dir)
    if not isinstance(descriptor, dict):
        raise _fail(f"{source_ref}: materialized tree (assembly.json) missing under {package_dir}")
    artifact = StepTopologyArtifact(
        cad_path=source_ref,
        kind="assembly",
        source_path=step_path,
        step_path=step_path,
        artifact_path=package_dir,
        manifest=descriptor,
        selector_bundle=SelectorBundle(manifest=descriptor),
    )
    index = build_selector_index(descriptor)
    return index_with_assembly_occurrences(index, artifact), descriptor


def _lookup(index, selector_text: str):
    from cadgen import lookup

    return lookup.lookup_selector(selector_text, index)


def _axis_from_ref(index, ref: str, *, mate: str, source_ref: str) -> dict[str, list[float]]:
    from cadgen.analysis import positioning_facts_for_row

    selector = ref.lstrip("#")
    resolved = _lookup(index, selector)
    if resolved is None:
        raise _fail(
            f"{source_ref} mate {mate!r}: axis ref {ref!r} does not resolve — "
            "use `cadgen step inspect refs` to list this model's selectors and labels"
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


def _instance_tree_ids(descriptor: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, list[str]]]:
    """The INSTANCE TREE's node ids and names — subassemblies included.

    The flat selector index holds LEAF occurrences only, but mates target the
    instance-tree namespace: a mate on a group occurrence is how "rigid groups
    are free" (design/pose-animation-split.md), and ``_subtree_ids`` already
    carries a group's whole subtree. So group nodes have to be resolvable, and
    ``assembly.json["assembly"]["root"]`` is where they live.
    """
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
    return by_id, by_name


def _occurrence_id_for_ref(
    index, ref: str, *, what: str, mate: str, source_ref: str, tree: tuple[dict[str, str], dict[str, list[str]]]
) -> str:
    selector = ref.lstrip("#")
    resolved = _lookup(index, selector)
    if resolved is not None and resolved[0] == "occurrence":
        return str(resolved[1].get("id") or "")
    by_id, by_name = tree
    if selector in by_id:
        return by_id[selector]
    candidates = by_name.get(selector) or []
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        raise _fail(
            f"{source_ref} mate {mate!r}: {what} {ref!r} names {len(candidates)} occurrences "
            f"({', '.join(candidates)}) — mate one of them by occurrence id, or give the "
            "groups distinct labels"
        )
    raise _fail(
        f"{source_ref} mate {mate!r}: {what} {ref!r} does not name an occurrence — "
        "label the part or subassembly in the model (cadgen.label_shape, or a "
        "Compound label) or use its occurrence id; `cadgen step inspect refs` "
        "lists the leaf occurrences"
    )


def resolve_kinematics_block(
    block: Mapping[str, Any], *, package_dir: Path, step_path: Path, source_ref: str
) -> tuple[dict[str, Any], dict[str, str]]:
    """Validated declaration -> sidecar-ready block (axes as numbers), plus the
    mate-ref -> occurrence-id map."""
    index, descriptor = _composed_index(package_dir, step_path=step_path, source_ref=source_ref)
    tree = _instance_tree_ids(descriptor)
    resolved = copy.deepcopy(dict(block))
    occurrence_ids: dict[str, str] = {}
    for mate in resolved.get("mates", []):
        name = str(mate.get("name"))
        for what, key in (("parent", "parent"), ("child", "child")):
            ref = str(mate.get(key))
            if ref not in occurrence_ids:
                occurrence_ids[ref] = _occurrence_id_for_ref(
                    index, ref, what=what, mate=name, source_ref=source_ref, tree=tree
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
            mate["axis"] = _axis_from_ref(index, str(axis["ref"]), mate=name, source_ref=source_ref)
    return resolved, occurrence_ids
