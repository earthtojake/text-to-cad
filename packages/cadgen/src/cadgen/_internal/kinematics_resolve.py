"""Build-time kinematics resolution: refs -> numbers, pose -> baked package.

Two jobs, both against the freshly built (staging) render package, before the
STEP is assembled from it:

1. RESOLVE: every mate's parent/child occurrence ref must name a real
   occurrence, and every ``axis={"ref": ...}`` selector becomes world-at-rest
   ``{"origin", "dir"}`` numbers via the same composed selector index inspect
   uses. The sidecar carries only numbers — the viewer does arithmetic, never
   topology.

2. BAKE (``pose=`` on the decorator): apply the FK deltas to the descriptor's
   absolute occurrence transforms so the artifact is WRITTEN at the pose and
   is therefore its own q=0. Mate axes ride their parent chain, and declared
   limits/defaults/presets shift by the baked values so the sidecar describes
   the artifact as written.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping

from cadgen._internal.atomic_replace import replace_atomic, temp_suffix
from cadgen._internal.kinematics_fk import (
    kinematics_deltas,
    matmul4,
    matrix_from_rows12,
    parent_chain_deltas,
    transform_point,
    transform_vector,
)


def _fail(message: str) -> ValueError:
    return ValueError(f"kinematics: {message}")


def _composed_index(package_dir: Path, *, step_path: Path, source_ref: str):
    """The composed selector index for a package directory (staging or final):
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
    ``descriptor["assembly"]["root"]`` is where they live.
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
    mate-ref -> occurrence-id map the bake step reuses."""
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


def _descriptor_nodes(descriptor: Mapping[str, Any]):
    # The descriptor's occurrence list is FLAT: leaves only, the instance tree
    # encoded in dotted ids (o1.2.3 is inside o1.2). Walk defensively through
    # any children arrays too, should a nested form ever appear.
    stack = list(descriptor.get("occurrences") or [])
    while stack:
        node = stack.pop()
        yield node
        stack.extend(node.get("children") or [])


def _subtree_ids(descriptor: Mapping[str, Any], occurrence_id: str) -> set[str]:
    """Every occurrence AT or BELOW an id — dotted-prefix containment, so a
    mate on a group occurrence carries all of its leaves."""
    prefix = f"{occurrence_id}."
    ids = {
        str(node.get("id"))
        for node in _descriptor_nodes(descriptor)
        if str(node.get("id")) == occurrence_id or str(node.get("id")).startswith(prefix)
    }
    if not ids:
        raise _fail(f"occurrence {occurrence_id} vanished from the tree during bake")
    return ids


def _premultiply_transform16(transform: list[float], delta: list[list[float]]) -> list[float]:
    matrix = [
        transform[0:4],
        transform[4:8],
        transform[8:12],
        transform[12:16],
    ]
    baked = matmul4(delta, matrix)
    return [value for row in baked for value in row]


def bake_pose_into_package(
    resolved_block: dict[str, Any],
    bake_pose: Mapping[str, float],
    *,
    package_dir: Path,
    occurrence_ids: Mapping[str, str],
) -> dict[str, Any]:
    """Write the pose into the package descriptor and re-zero the block.

    Descriptor occurrence transforms are ABSOLUTE, so a mate's world delta
    premultiplies every transform in its child's subtree (deeper mates carry
    their own composed delta and simply override within their subtree). The
    returned block describes the artifact AS WRITTEN: axes carried by their
    parent chains, limits/defaults/presets shifted by the baked values.
    """
    from cadgen._internal.component_package import read_package_descriptor
    from cadgen._internal.kinematics_fk import effective_dof_values

    descriptor = read_package_descriptor(package_dir)
    if not isinstance(descriptor, dict):
        raise _fail(f"materialized tree (assembly.json) missing under {package_dir} during bake")

    chains = parent_chain_deltas(resolved_block, bake_pose)
    delta_by_id_4x4 = _delta_by_occurrence(resolved_block, bake_pose, descriptor=descriptor, occurrence_ids=occurrence_ids)

    for node in _descriptor_nodes(descriptor):
        delta = delta_by_id_4x4.get(str(node.get("id")))
        transform = node.get("transform")
        if delta is None or not isinstance(transform, list) or len(transform) != 16:
            continue
        node["transform"] = _premultiply_transform16([float(v) for v in transform], delta)

    target = package_dir / "assembly.json"
    temp = target.with_name(f".{target.name}{temp_suffix()}")
    temp.write_text(json.dumps(descriptor, sort_keys=True), encoding="utf-8")
    replace_atomic(temp, target)

    # Re-zero the block: the artifact as written is q=0, so every declared
    # range and preset shifts by however far the bake moved each DOF.
    baked = copy.deepcopy(resolved_block)
    shift = effective_dof_values(resolved_block, bake_pose)
    for mate in baked.get("mates", []):
        chain = chains.get(str(mate["name"]))
        if chain is not None:
            axis = mate["axis"]
            axis["origin"] = transform_point(chain, tuple(axis["origin"]))
            axis["dir"] = transform_vector(chain, tuple(axis["dir"]))
        dofs = (
            [(f"{mate['name']}.{sub}", sub) for sub in ("turn", "travel")]
            if mate.get("kind") == "cylindrical"
            else [(str(mate["name"]), "value")]
        )
        limits = mate.get("limits") or {}
        for dof_id, key in dofs:
            moved = shift.get(dof_id, 0.0)
            if moved and key in limits:
                limits[key] = [limits[key][0] - moved, limits[key][1] - moved]
    for preset in (baked.get("poses") or {}).values():
        for dof in list(preset):
            preset[dof] = float(preset[dof]) - shift.get(dof, 0.0)
    baked["bakedPose"] = {dof: float(value) for dof, value in dict(bake_pose).items()}
    return baked


def _delta_by_occurrence(
    resolved_block: Mapping[str, Any],
    pose_values: Mapping[str, float],
    *,
    descriptor: Mapping[str, Any],
    occurrence_ids: Mapping[str, str],
) -> dict[str, list[list[float]]]:
    """Mate-tree deltas expanded to per-occurrence-id 4x4s, innermost mate
    winning within its subtree (tree order makes the deeper assignment last)."""
    deltas = kinematics_deltas(resolved_block, pose_values)
    delta_by_id: dict[str, list[list[float]]] = {}
    for ref, delta in deltas.items():
        for occurrence_id in _subtree_ids(descriptor, occurrence_ids[ref]):
            delta_by_id[occurrence_id] = delta
    return delta_by_id


def mesh_pose_deltas(
    kinematics_def: Any,
    pose_values: Mapping[str, float],
    *,
    package_dir: Path,
    step_path: Path,
    source_ref: str,
) -> dict[str, list[float]]:
    """Everything a posed MESH export needs, in one call against the FINAL
    package: resolve the declaration's refs, evaluate FK at the pose, and
    return {occurrence id: flat-16 row-major delta} for the Node exporter.
    Nothing is written — a mesh bake is transient (no sidecar, ever)."""
    from cadgen._internal.component_package import read_package_descriptor

    block = dict(getattr(kinematics_def, "block", kinematics_def))
    resolved_block, occurrence_ids = resolve_kinematics_block(
        block, package_dir=package_dir, step_path=step_path, source_ref=source_ref
    )
    descriptor = read_package_descriptor(package_dir)
    if not isinstance(descriptor, dict):
        raise _fail(f"{source_ref}: materialized tree (assembly.json) missing under {package_dir}")
    return {
        occurrence_id: [value for row in delta for value in row]
        for occurrence_id, delta in _delta_by_occurrence(
            resolved_block, pose_values, descriptor=descriptor, occurrence_ids=occurrence_ids
        ).items()
    }


def resolved_block_pose_deltas(
    block: Mapping[str, Any],
    pose_values: Mapping[str, float],
    *,
    package_dir: Path,
) -> dict[str, list[float]]:
    """FK deltas from an ALREADY-RESOLVED block — the sidecar's kinematics.

    The mesh DOORS' path. A sidecar block carries world-number axes and the
    ``parentId``/``childId`` this expansion needs, so a door evaluates forward
    kinematics with no selector index, no topology and no OCCT: it reads the
    package descriptor for the occurrence tree and folds. Nothing is written —
    a mesh bake is transient (no sidecar, ever).
    """
    from cadgen._internal.component_package import read_package_descriptor

    descriptor = read_package_descriptor(package_dir)
    if not isinstance(descriptor, dict):
        raise _fail(f"materialized tree (assembly.json) missing under {package_dir}")
    occurrence_ids: dict[str, str] = {}
    for mate in block.get("mates", []):
        for ref_key, id_key in (("parent", "parentId"), ("child", "childId")):
            ref = str(mate.get(ref_key) or "")
            occurrence_id = str(mate.get(id_key) or "")
            if not ref or not occurrence_id:
                raise _fail(
                    f"mate {mate.get('name')!r} in the sidecar carries no resolved "
                    f"{id_key}; rebuild the document by running its model script"
                )
            occurrence_ids[ref] = occurrence_id
    return {
        occurrence_id: [value for row in delta for value in row]
        for occurrence_id, delta in _delta_by_occurrence(
            block, pose_values, descriptor=descriptor, occurrence_ids=occurrence_ids
        ).items()
    }


def runtime_mesh_declarations(script_path: Path) -> dict[tuple[str, Path], tuple[Any, dict | None]]:
    """The RUNTIME mesh declarations' kinematics, keyed by (fmt, resolved out
    path). The AST metadata cannot evaluate a kinematics= dict, so posed mesh
    exports read the registry — importing the model module (registration only;
    import never builds) if this process has not loaded it yet."""
    from cadgen.authoring import registered_model
    from cadgen.metadata import resolve_model_output_path

    script = Path(script_path).resolve()
    model = registered_model(script)
    if model is None:
        from cadgen._internal.generation_runner import _load_generator_module
        from cadgen._internal.source_hash import evict_first_party_modules

        # Same clean first-party module space the generation path starts from.
        # This load happens when the STEP is already current and only declared
        # mesh exports need refreshing, so it is the ONE module load that skips
        # generation — and without the eviction it inherits whatever project a
        # warm worker built last. Every cad-project keeps shared code in
        # `src/lib/`, so a stale `lib` from another project makes this model's
        # own helpers unimportable (or, worse, importable and wrong).
        evict_first_party_modules()
        _load_generator_module(script)
        model = registered_model(script)
    if model is None:
        return {}
    declarations: dict[tuple[str, Path], tuple[Any, dict | None]] = {}
    for decl in model.mesh_exports:
        if decl.kinematics is None:
            continue
        if decl.out is not None:
            path = resolve_model_output_path(script, fmt=decl.fmt, explicit_out=decl.out)
        else:
            path = model.output_path.with_suffix(f".{decl.fmt}")
        declarations[(decl.fmt, path.expanduser().resolve())] = (decl.kinematics, decl.bake_pose)
    return declarations
