from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from common.assembly_spec import (
    IDENTITY_TRANSFORM,
    AssemblySpec,
    AssemblyNodeSpec,
    assembly_spec_children,
    multiply_transforms,
)
from common.render import (
    part_glb_path,
    part_selector_manifest_path,
    relative_to_repo,
    sha256_file,
)


ASSEMBLY_COMPOSITION_SCHEMA_VERSION = 1
TOPOLOGY_COUNT_KEYS = ("shapeCount", "faceCount", "edgeCount", "vertexCount")


class AssemblyCompositionError(ValueError):
    pass


def component_name(instance_path: Sequence[str]) -> str:
    return "__".join(str(part) for part in instance_path if str(part)) or "root"


def _relative_to_topology(topology_path: Path, target_path: Path) -> str:
    return os.path.relpath(target_path.resolve(), start=topology_path.resolve().parent).replace(os.sep, "/")


def _versioned_relative_url(topology_path: Path, target_path: Path, content_hash: str) -> str:
    suffix = f"?v={content_hash}" if content_hash else ""
    return f"{_relative_to_topology(topology_path, target_path)}{suffix}"


def build_linked_assembly_composition(
    *,
    cad_ref: str,
    topology_path: Path,
    topology_manifest: dict[str, Any],
    assembly_spec: AssemblySpec,
    entries_by_step_path: Mapping[Path, object],
    read_assembly_spec: Callable[[Path], AssemblySpec],
) -> dict[str, Any]:
    occurrences = _rows(topology_manifest, "occurrences", "occurrenceColumns")
    if not occurrences:
        raise AssemblyCompositionError(f"Assembly topology has no occurrences: {cad_ref}")
    component_occurrences = _component_occurrences(topology_manifest)
    root_occurrence = occurrences[0]
    children = [
        _linked_instance_node(
            cad_ref=cad_ref,
            topology_path=topology_path,
            instance=instance,
            instance_path=(instance.instance_id,),
            target_occurrence=None,
            parent_world_transform=IDENTITY_TRANSFORM,
            parent_use_source_colors=True,
            all_occurrences=occurrences,
            component_occurrences=component_occurrences,
            entries_by_step_path=entries_by_step_path,
            read_assembly_spec=read_assembly_spec,
            stack=(assembly_spec.assembly_path.resolve().as_posix(),),
        )
        for instance in assembly_spec_children(assembly_spec)
    ]
    if not children:
        raise AssemblyCompositionError(f"Assembly {cad_ref} has no component instances")
    return {
        "schemaVersion": ASSEMBLY_COMPOSITION_SCHEMA_VERSION,
        "mode": "linked",
        "root": _assembly_root_node(cad_ref, root_occurrence, children),
    }


def build_native_assembly_composition(
    *,
    cad_ref: str,
    topology_path: Path,
    topology_manifest: dict[str, Any],
    component_mesh_paths: Mapping[str, Path],
) -> dict[str, Any]:
    occurrences = _rows(topology_manifest, "occurrences", "occurrenceColumns")
    if not occurrences:
        raise AssemblyCompositionError(f"Assembly topology has no occurrences: {cad_ref}")
    by_id = {
        str(row.get("id") or "").strip(): row
        for row in occurrences
        if str(row.get("id") or "").strip()
    }
    children_by_parent: dict[str, list[dict[str, Any]]] = {}
    top_level: list[dict[str, Any]] = []
    for row in occurrences:
        parent_id = str(row.get("parentId") or "").strip()
        if parent_id:
            children_by_parent.setdefault(parent_id, []).append(row)
        else:
            top_level.append(row)

    root_occurrence = top_level[0] if len(top_level) == 1 else occurrences[0]
    root_children = top_level
    if len(top_level) == 1 and not children_by_parent.get(str(top_level[0].get("id") or "").strip()):
        root_children = top_level
    elif len(top_level) == 1:
        root_children = children_by_parent.get(str(top_level[0].get("id") or "").strip(), [])

    children = [
        _native_occurrence_node(
            row,
            children_by_parent=children_by_parent,
            component_mesh_paths=component_mesh_paths,
            topology_path=topology_path,
            parent_world_transform=IDENTITY_TRANSFORM,
        )
        for row in root_children
    ]
    if not children:
        row = root_occurrence
        children = [
            _native_part_node(
                row,
                component_mesh_paths=component_mesh_paths,
                topology_path=topology_path,
                parent_world_transform=IDENTITY_TRANSFORM,
            )
        ]
    return {
        "schemaVersion": ASSEMBLY_COMPOSITION_SCHEMA_VERSION,
        "mode": "native",
        "root": _assembly_root_node(cad_ref, root_occurrence, children),
    }


def _linked_instance_node(
    *,
    cad_ref: str,
    topology_path: Path,
    instance: object,
    instance_path: tuple[str, ...],
    target_occurrence: Mapping[str, Any] | None,
    parent_world_transform: tuple[float, ...],
    parent_use_source_colors: bool,
    all_occurrences: Sequence[dict[str, Any]],
    component_occurrences: Sequence[dict[str, Any]],
    entries_by_step_path: Mapping[Path, object],
    read_assembly_spec: Callable[[Path], AssemblySpec],
    stack: tuple[str, ...],
) -> dict[str, Any]:
    instance_source_path = Path(instance.source_path).resolve() if instance.source_path is not None else None
    source_spec = entries_by_step_path.get(instance_source_path) if instance_source_path is not None else None
    child_kind = str(getattr(source_spec, "kind", "") or "")
    instance_transform = tuple(float(value) for value in instance.transform)
    world_transform = multiply_transforms(parent_world_transform, instance_transform)
    source_step_path = getattr(source_spec, "step_path", None) if source_spec is not None else None
    source_path = _relative_to_topology(topology_path, Path(source_step_path)) if source_step_path is not None else (instance.path or "")
    # Prefer the user-supplied instance name (it is required by the generator
    # contract and intentionally chosen for display); fall back to the source
    # STEP filename stem only when no instance name is set, then to the
    # instance-path component as a last resort.
    display_name = str(
        instance.name
        or (
            Path(source_step_path).stem
            if source_step_path is not None
            else Path(instance.path or "").stem
        )
        or instance_path[-1]
    ).strip()
    use_source_colors = parent_use_source_colors and bool(instance.use_source_colors)

    if instance.children:
        occurrence = target_occurrence or _find_occurrence_by_component_name(
            component_name(instance_path),
            all_occurrences,
            cad_ref,
        )
        occurrence_id = str(occurrence.get("id") or component_name(instance_path)).strip() if occurrence else component_name(instance_path)
        occurrence_world_transform = (
            tuple(float(value) for value in occurrence.get("transform"))
            if occurrence and isinstance(occurrence.get("transform"), list) and len(occurrence.get("transform")) == 16
            else world_transform
        )
        target_children_by_parent = _children_by_parent(all_occurrences)
        target_children = target_children_by_parent.get(occurrence_id, [])
        children = [
            _linked_instance_node(
                cad_ref=cad_ref,
                topology_path=topology_path,
                instance=child_instance,
                instance_path=(*instance_path, child_instance.instance_id),
                target_occurrence=_match_occurrence_child_for_instance(
                    target_children,
                    child_instance,
                    index,
                    (*instance_path, child_instance.instance_id),
                ),
                parent_world_transform=occurrence_world_transform,
                parent_use_source_colors=use_source_colors,
                all_occurrences=all_occurrences,
                component_occurrences=component_occurrences,
                entries_by_step_path=entries_by_step_path,
                read_assembly_spec=read_assembly_spec,
                stack=stack,
            )
            for index, child_instance in enumerate(instance.children)
        ]
        return _assembly_node(
            id=occurrence_id,
            occurrence_id=occurrence_id,
            display_name=display_name,
            source_kind="catalog",
            source_path=source_path,
            instance_path=".".join(instance_path),
            use_source_colors=use_source_colors,
            local_transform=instance_transform,
            world_transform=occurrence_world_transform,
            bbox=(occurrence.get("bbox") if occurrence else None) or _merge_bbox([child.get("bbox") for child in children]),
            topology_counts=_sum_public_counts(children),
            children=children,
        )

    if source_spec is None or instance_source_path is None:
        raise AssemblyCompositionError(
            f"{cad_ref} assembly component {component_name(instance_path)} references missing CAD source {instance.path}"
        )

    if child_kind == "assembly":
        stack_key = instance_source_path.as_posix()
        if stack_key in stack:
            cycle = " -> ".join((*stack, stack_key))
            raise AssemblyCompositionError(f"Assembly cycle detected: {cycle}")
        source_source_path = getattr(source_spec, "source_path", None)
        script_path = getattr(source_spec, "script_path", None)
        if source_source_path is None or script_path is None:
            raise AssemblyCompositionError(
                f"{cad_ref} nested assembly {instance.path} must be a generated assembly source"
            )
        child_spec = read_assembly_spec(Path(source_source_path))
        occurrence = target_occurrence or _find_occurrence_by_component_name(
            component_name(instance_path),
            all_occurrences,
            cad_ref,
        )
        occurrence_id = str(occurrence.get("id") or component_name(instance_path)).strip() if occurrence else component_name(instance_path)
        occurrence_world_transform = (
            tuple(float(value) for value in occurrence.get("transform"))
            if occurrence and isinstance(occurrence.get("transform"), list) and len(occurrence.get("transform")) == 16
            else world_transform
        )
        target_children_by_parent = _children_by_parent(all_occurrences)
        target_children = target_children_by_parent.get(occurrence_id, [])
        children = [
            _linked_instance_node(
                cad_ref=cad_ref,
                topology_path=topology_path,
                instance=child_instance,
                instance_path=(*instance_path, child_instance.instance_id),
                target_occurrence=_match_occurrence_child_for_instance(
                    target_children,
                    child_instance,
                    index,
                    (*instance_path, child_instance.instance_id),
                ),
                parent_world_transform=occurrence_world_transform,
                parent_use_source_colors=use_source_colors,
                all_occurrences=all_occurrences,
                component_occurrences=component_occurrences,
                entries_by_step_path=entries_by_step_path,
                read_assembly_spec=read_assembly_spec,
                stack=(*stack, stack_key),
            )
            for index, child_instance in enumerate(assembly_spec_children(child_spec))
        ]
        return _assembly_node(
            id=occurrence_id,
            occurrence_id=occurrence_id,
            display_name=display_name,
            source_kind="catalog",
            source_path=_relative_to_topology(topology_path, Path(source_step_path)) if source_step_path is not None else (instance.path or ""),
            instance_path=".".join(instance_path),
            use_source_colors=use_source_colors,
            local_transform=instance_transform,
            world_transform=occurrence_world_transform,
            bbox=(occurrence.get("bbox") if occurrence else None) or _merge_bbox([child.get("bbox") for child in children]),
            topology_counts=_sum_public_counts(children),
            children=children,
        )

    native_source_assembly = _source_assembly_payload(Path(source_step_path)) if source_step_path is not None else None
    if native_source_assembly is not None:
        occurrence = target_occurrence or _find_occurrence_by_component_name(
            component_name(instance_path),
            all_occurrences,
            cad_ref,
        )
        if occurrence is None:
            raise AssemblyCompositionError(
                f"{cad_ref} assembly topology is missing occurrence {component_name(instance_path)!r}"
            )
        occurrence_id = str(occurrence.get("id") or "").strip()
        return _linked_native_assembly_node(
            topology_path=topology_path,
            source_topology_path=part_selector_manifest_path(Path(source_step_path)),
            source_assembly=native_source_assembly,
            source_path=source_path,
            occurrence=occurrence,
            occurrence_id=occurrence_id,
            all_occurrences=all_occurrences,
            display_name=display_name,
            instance_path=".".join(instance_path),
            use_source_colors=use_source_colors,
            local_transform=instance_transform,
            world_transform=tuple(float(value) for value in occurrence.get("transform") or world_transform),
        )

    if child_kind == "part":
        occurrence = target_occurrence or _find_occurrence_by_component_name(
            component_name(instance_path),
            component_occurrences,
            cad_ref,
        )
        if occurrence is None:
            raise AssemblyCompositionError(
                f"{cad_ref} assembly topology is missing occurrence {component_name(instance_path)!r}"
            )
        if source_step_path is None:
            raise AssemblyCompositionError(f"{cad_ref} component {component_name(instance_path)} is missing STEP source")
        source_counts = _source_topology_counts(part_selector_manifest_path(Path(source_step_path)))
        occurrence_counts = _occurrence_topology_counts(occurrence)
        if source_counts != occurrence_counts:
            raise AssemblyCompositionError(
                f"{cad_ref} assembly occurrence {occurrence.get('id')!r} count mismatch for "
                f"{source_path}: source={source_counts} assembly={occurrence_counts}"
            )
        occurrence_id = str(occurrence.get("id") or "").strip()
        glb_path = part_glb_path(Path(source_step_path))
        glb_hash = sha256_file(glb_path) if glb_path.exists() else ""
        return _part_node(
            id=occurrence_id,
            occurrence_id=occurrence_id,
            display_name=display_name,
            source_kind="catalog",
            source_path=source_path,
            instance_path=".".join(instance_path),
            use_source_colors=use_source_colors,
            local_transform=instance_transform,
            world_transform=tuple(float(value) for value in occurrence.get("transform") or world_transform),
            bbox=occurrence.get("bbox"),
            topology_counts=_public_topology_counts(occurrence_counts),
            asset_url=_versioned_relative_url(topology_path, glb_path, glb_hash) if glb_hash else "",
            asset_hash=glb_hash,
        )

    raise AssemblyCompositionError(
        f"{cad_ref} component {component_name(instance_path)} must resolve to a STEP part or assembly source"
    )


def _source_assembly_payload(step_path: Path) -> dict[str, Any] | None:
    topology_path = part_selector_manifest_path(step_path)
    try:
        payload = _read_json(topology_path)
    except AssemblyCompositionError:
        return None
    assembly = payload.get("assembly")
    root = assembly.get("root") if isinstance(assembly, dict) else None
    if not isinstance(root, dict) or not root.get("children"):
        return None
    return assembly


def _linked_native_assembly_node(
    *,
    topology_path: Path,
    source_topology_path: Path,
    source_assembly: Mapping[str, Any],
    source_path: str,
    occurrence: Mapping[str, Any],
    occurrence_id: str,
    all_occurrences: Sequence[dict[str, Any]],
    display_name: str,
    instance_path: str,
    use_source_colors: bool,
    local_transform: Sequence[float],
    world_transform: tuple[float, ...],
) -> dict[str, Any]:
    source_root = source_assembly.get("root")
    if not isinstance(source_root, Mapping):
        raise AssemblyCompositionError(f"Native source assembly is missing root: {relative_to_repo(source_topology_path)}")
    source_root_occurrence_id = str(source_root.get("occurrenceId") or source_root.get("id") or "").strip()
    source_children = source_root.get("children")
    if not isinstance(source_children, list) or not source_children:
        raise AssemblyCompositionError(f"Native source assembly has no children: {relative_to_repo(source_topology_path)}")
    target_children_by_parent = _children_by_parent(all_occurrences)
    target_children = target_children_by_parent.get(occurrence_id, [])
    child_nodes = [
        _clone_native_source_node(
            source_node=_source_node_for_native_target_child(
                source_root,
                source_children,
                target_children,
                target_children_by_parent,
                child,
                index,
            ),
            target_row=child,
            target_children_by_parent=target_children_by_parent,
            topology_path=topology_path,
            source_topology_path=source_topology_path,
            source_root_occurrence_id=source_root_occurrence_id,
            target_parent_occurrence_id=occurrence_id,
            parent_world_transform=world_transform,
            parent_instance_path=instance_path,
            parent_use_source_colors=use_source_colors,
        )
        for index, child in enumerate(target_children)
    ]
    if not child_nodes:
        child_nodes = [
            _clone_native_source_node(
                source_node=child,
                target_row=None,
                target_children_by_parent={},
                topology_path=topology_path,
                source_topology_path=source_topology_path,
                source_root_occurrence_id=source_root_occurrence_id,
                target_parent_occurrence_id=occurrence_id,
                parent_world_transform=world_transform,
                parent_instance_path=instance_path,
                parent_use_source_colors=use_source_colors,
            )
            for child in source_children
            if isinstance(child, Mapping)
        ]
    child_counts = _sum_public_counts(child_nodes)
    return _assembly_node(
        id=occurrence_id,
        occurrence_id=occurrence_id,
        display_name=display_name,
        source_kind="native",
        source_path=source_path,
        instance_path=instance_path,
        use_source_colors=use_source_colors,
        local_transform=local_transform,
        world_transform=world_transform,
        bbox=occurrence.get("bbox") or _merge_bbox([child.get("bbox") for child in child_nodes]),
        topology_counts=child_counts if _counts_have_values(child_counts) else _public_topology_counts(_occurrence_topology_counts(occurrence)),
        children=child_nodes,
    )


def _clone_native_source_node(
    *,
    source_node: Mapping[str, Any],
    target_row: Mapping[str, Any] | None,
    target_children_by_parent: Mapping[str, list[dict[str, Any]]],
    topology_path: Path,
    source_topology_path: Path,
    source_root_occurrence_id: str,
    target_parent_occurrence_id: str,
    parent_world_transform: tuple[float, ...],
    parent_instance_path: str,
    parent_use_source_colors: bool,
) -> dict[str, Any]:
    source_occurrence_id = str(source_node.get("occurrenceId") or source_node.get("id") or "").strip()
    occurrence_id = (
        str(target_row.get("id") or "").strip()
        if target_row is not None
        else _prefix_native_occurrence_id(
            source_occurrence_id,
            source_root_occurrence_id=source_root_occurrence_id,
            target_parent_occurrence_id=target_parent_occurrence_id,
        )
    )
    source_world_transform = _transform_tuple(source_node.get("worldTransform"), IDENTITY_TRANSFORM)
    source_local_transform = _transform_tuple(source_node.get("localTransform"), source_world_transform)
    world_transform = _row_transform(target_row) if target_row is not None else multiply_transforms(parent_world_transform, source_local_transform)
    local_transform = (
        _relative_transform(parent_world_transform, world_transform)
        if target_row is not None
        else source_local_transform
    )
    source_children = source_node.get("children")
    target_children = target_children_by_parent.get(occurrence_id, []) if occurrence_id else []
    if target_children and not _source_node_has_children(source_node) and _source_node_has_glb_asset(source_node):
        return _native_source_part_node(
            source_node=source_node,
            target_row=target_row,
            topology_path=topology_path,
            source_topology_path=source_topology_path,
            occurrence_id=occurrence_id,
            display_name=_occurrence_display_name(target_row) if target_row is not None else "",
            instance_path=".".join(
                part
                for part in (
                    parent_instance_path,
                    str(target_row.get("path") or "") if target_row is not None else str(source_node.get("instancePath") or source_occurrence_id),
                )
                if part
            ),
            use_source_colors=parent_use_source_colors and source_node.get("useSourceColors") is not False,
            local_transform=local_transform,
            world_transform=world_transform,
            bbox=target_row.get("bbox") if target_row is not None else _transform_bbox(parent_world_transform, source_node.get("bbox")),
        )
    node_children = [
        _clone_native_source_node(
            source_node=_match_source_child_for_target(source_children, child, index),
            target_row=child,
            target_children_by_parent=target_children_by_parent,
            topology_path=topology_path,
            source_topology_path=source_topology_path,
            source_root_occurrence_id=source_root_occurrence_id,
            target_parent_occurrence_id=target_parent_occurrence_id,
            parent_world_transform=world_transform,
            parent_instance_path=parent_instance_path,
            parent_use_source_colors=parent_use_source_colors,
        )
        for index, child in enumerate(target_children)
    ]
    if not node_children and isinstance(source_children, list) and source_children:
        node_children = [
            _clone_native_source_node(
                source_node=child,
                target_row=None,
                target_children_by_parent={},
                topology_path=topology_path,
                source_topology_path=source_topology_path,
                source_root_occurrence_id=source_root_occurrence_id,
                target_parent_occurrence_id=occurrence_id,
                parent_world_transform=world_transform,
                parent_instance_path=parent_instance_path,
                parent_use_source_colors=parent_use_source_colors,
            )
            for child in source_children
            if isinstance(child, Mapping)
        ]
    display_name = str(
        _occurrence_display_name(target_row)
        if target_row is not None
        else source_node.get("displayName") or source_node.get("name") or occurrence_id
    ).strip()
    instance_path = ".".join(
        part
        for part in (
            parent_instance_path,
            str(target_row.get("path") or "") if target_row is not None else str(source_node.get("instancePath") or source_occurrence_id),
        )
        if part
    )
    topology_counts = source_node.get("topologyCounts") if isinstance(source_node.get("topologyCounts"), Mapping) else {}
    bbox = target_row.get("bbox") if target_row is not None else _transform_bbox(parent_world_transform, source_node.get("bbox"))
    use_source_colors = parent_use_source_colors and source_node.get("useSourceColors") is not False
    if node_children:
        child_counts = _sum_public_counts(node_children)
        return _assembly_node(
            id=occurrence_id,
            occurrence_id=occurrence_id,
            display_name=display_name,
            source_kind="native",
            source_path="",
            instance_path=instance_path,
            use_source_colors=use_source_colors,
            local_transform=local_transform,
            world_transform=world_transform,
            bbox=bbox or _merge_bbox([child.get("bbox") for child in node_children]),
            topology_counts=child_counts if _counts_have_values(child_counts) else _public_topology_counts(topology_counts),
            children=node_children,
        )

    return _native_source_part_node(
        source_node=source_node,
        target_row=target_row,
        topology_path=topology_path,
        source_topology_path=source_topology_path,
        occurrence_id=occurrence_id,
        display_name=display_name,
        instance_path=instance_path,
        use_source_colors=use_source_colors,
        local_transform=local_transform,
        world_transform=world_transform,
        bbox=bbox,
    )


def _source_node_has_children(source_node: Mapping[str, Any]) -> bool:
    source_children = source_node.get("children")
    return isinstance(source_children, list) and bool(source_children)


def _source_node_glb_asset(source_node: Mapping[str, Any]) -> Mapping[str, Any]:
    glb_asset = source_node.get("assets", {}).get("glb") if isinstance(source_node.get("assets"), Mapping) else {}
    return glb_asset if isinstance(glb_asset, Mapping) else {}


def _source_node_has_glb_asset(source_node: Mapping[str, Any]) -> bool:
    return bool(str(_source_node_glb_asset(source_node).get("url") or "").strip())


def _native_source_part_node(
    *,
    source_node: Mapping[str, Any],
    target_row: Mapping[str, Any] | None,
    topology_path: Path,
    source_topology_path: Path,
    occurrence_id: str,
    display_name: str,
    instance_path: str,
    use_source_colors: bool,
    local_transform: Sequence[float],
    world_transform: Sequence[float],
    bbox: Any,
) -> dict[str, Any]:
    glb_asset = _source_node_glb_asset(source_node)
    asset_hash = str(glb_asset.get("hash") or "").strip() if isinstance(glb_asset, Mapping) else ""
    asset_url = _relocated_asset_url(topology_path, source_topology_path, str(glb_asset.get("url") or "")) if isinstance(glb_asset, Mapping) else ""
    topology_counts = (
        _occurrence_topology_counts(target_row)
        if target_row is not None
        else source_node.get("topologyCounts") if isinstance(source_node.get("topologyCounts"), Mapping) else {}
    )
    return _part_node(
        id=occurrence_id,
        occurrence_id=occurrence_id,
        display_name=display_name,
        source_kind="native",
        source_path="",
        instance_path=instance_path,
        use_source_colors=use_source_colors,
        local_transform=local_transform,
        world_transform=world_transform,
        bbox=bbox,
        topology_counts=_public_topology_counts(topology_counts),
        asset_url=asset_url,
        asset_hash=asset_hash,
    )


def _prefix_native_occurrence_id(
    source_occurrence_id: str,
    *,
    source_root_occurrence_id: str,
    target_parent_occurrence_id: str,
) -> str:
    if source_root_occurrence_id and source_occurrence_id == source_root_occurrence_id:
        return target_parent_occurrence_id
    prefix = f"{source_root_occurrence_id}."
    if source_root_occurrence_id and source_occurrence_id.startswith(prefix):
        return f"{target_parent_occurrence_id}.{source_occurrence_id[len(prefix):]}"
    suffix = source_occurrence_id[1:] if source_occurrence_id.startswith("o") else source_occurrence_id
    return f"{target_parent_occurrence_id}.{suffix}" if suffix else target_parent_occurrence_id


def _relocated_asset_url(topology_path: Path, source_topology_path: Path, raw_url: str) -> str:
    if not raw_url:
        return ""
    asset_path, separator, query = raw_url.partition("?")
    if not asset_path:
        return ""
    target_path = (source_topology_path.parent / asset_path).resolve()
    relocated = _relative_to_topology(topology_path, target_path)
    return f"{relocated}{separator}{query}" if separator else relocated


def _children_by_parent(occurrences: Sequence[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    children_by_parent: dict[str, list[dict[str, Any]]] = {}
    for row in occurrences:
        parent_id = str(row.get("parentId") or "").strip()
        if parent_id:
            children_by_parent.setdefault(parent_id, []).append(row)
    return children_by_parent


def _match_source_child_for_target(
    source_children: object,
    target_row: Mapping[str, Any],
    index: int,
) -> Mapping[str, Any]:
    candidates = [child for child in source_children if isinstance(child, Mapping)] if isinstance(source_children, list) else []
    if not candidates:
        return {}
    target_names = {
        str(target_row.get("name") or "").strip(),
        str(target_row.get("sourceName") or "").strip(),
        str(target_row.get("id") or "").strip(),
    }
    target_names.discard("")
    for candidate in candidates:
        candidate_names = {
            str(candidate.get("displayName") or "").strip(),
            str(candidate.get("name") or "").strip(),
            str(candidate.get("occurrenceId") or "").strip(),
            str(candidate.get("id") or "").strip(),
        }
        if target_names.intersection(candidate_names):
            return candidate
    if 0 <= index < len(candidates):
        return candidates[index]
    return candidates[-1]


def _source_node_for_native_target_child(
    source_root: Mapping[str, Any],
    source_children: object,
    target_siblings: Sequence[Mapping[str, Any]],
    target_children_by_parent: Mapping[str, list[dict[str, Any]]],
    target_row: Mapping[str, Any],
    index: int,
) -> Mapping[str, Any]:
    target_row_id = str(target_row.get("id") or "").strip()
    target_child_rows = target_children_by_parent.get(target_row_id, []) if target_row_id else []
    source_child_count = len(source_children) if isinstance(source_children, list) else 0
    if (
        len(target_siblings) == 1
        and len(target_child_rows) > 1
        and source_child_count > 1
        and isinstance(source_root, Mapping)
    ):
        return source_root
    return _match_source_child_for_target(source_children, target_row, index)


def _match_occurrence_child_for_instance(
    target_children: Sequence[Mapping[str, Any]],
    instance: object,
    index: int,
    instance_path: tuple[str, ...],
) -> Mapping[str, Any] | None:
    if not target_children:
        return None
    expected_names = {
        str(getattr(instance, "instance_id", "") or "").strip(),
        str(getattr(instance, "name", "") or "").strip(),
        component_name(instance_path),
    }
    expected_names.discard("")
    for child in target_children:
        child_names = {
            str(child.get("name") or "").strip(),
            str(child.get("sourceName") or "").strip(),
            str(child.get("id") or "").strip(),
        }
        if expected_names.intersection(child_names):
            return child
    if 0 <= index < len(target_children):
        return target_children[index]
    return target_children[-1]


def _native_occurrence_node(
    row: dict[str, Any],
    *,
    children_by_parent: Mapping[str, list[dict[str, Any]]],
    component_mesh_paths: Mapping[str, Path],
    topology_path: Path,
    parent_world_transform: tuple[float, ...],
) -> dict[str, Any]:
    row_id = str(row.get("id") or "").strip()
    children = children_by_parent.get(row_id, [])
    if not children:
        return _native_part_node(
            row,
            component_mesh_paths=component_mesh_paths,
            topology_path=topology_path,
            parent_world_transform=parent_world_transform,
        )
    world_transform = _row_transform(row)
    child_nodes = [
        _native_occurrence_node(
            child,
            children_by_parent=children_by_parent,
            component_mesh_paths=component_mesh_paths,
            topology_path=topology_path,
            parent_world_transform=world_transform,
        )
        for child in children
    ]
    return _assembly_node(
        id=row_id,
        occurrence_id=row_id,
        display_name=_occurrence_display_name(row),
        source_kind="native",
        source_path="",
        instance_path=str(row.get("path") or row_id),
        use_source_colors=True,
        local_transform=_relative_transform(parent_world_transform, world_transform),
        world_transform=world_transform,
        bbox=row.get("bbox") or _merge_bbox([child.get("bbox") for child in child_nodes]),
        topology_counts=_public_topology_counts(_occurrence_topology_counts(row)),
        children=child_nodes,
    )


def _native_part_node(
    row: dict[str, Any],
    *,
    component_mesh_paths: Mapping[str, Path],
    topology_path: Path,
    parent_world_transform: tuple[float, ...],
) -> dict[str, Any]:
    occurrence_id = str(row.get("id") or "").strip()
    if not occurrence_id:
        raise AssemblyCompositionError("Native assembly occurrence is missing an id")
    mesh_path = component_mesh_paths.get(occurrence_id)
    if mesh_path is None:
        raise AssemblyCompositionError(f"Native assembly component {occurrence_id} is missing a mesh asset")
    mesh_hash = sha256_file(mesh_path) if mesh_path.exists() else ""
    world_transform = _row_transform(row)
    return _part_node(
        id=occurrence_id,
        occurrence_id=occurrence_id,
        display_name=_occurrence_display_name(row),
        source_kind="native",
        source_path="",
        instance_path=str(row.get("path") or occurrence_id),
        use_source_colors=True,
        local_transform=_relative_transform(parent_world_transform, world_transform),
        world_transform=world_transform,
        bbox=row.get("bbox"),
        topology_counts=_public_topology_counts(_occurrence_topology_counts(row)),
        asset_url=_versioned_relative_url(topology_path, mesh_path, mesh_hash) if mesh_hash else "",
        asset_hash=mesh_hash,
    )


def _part_node(
    *,
    id: str,
    occurrence_id: str,
    display_name: str,
    source_kind: str,
    source_path: str,
    instance_path: str,
    use_source_colors: bool,
    local_transform: Sequence[float],
    world_transform: Sequence[float],
    bbox: Any,
    topology_counts: Mapping[str, int],
    asset_url: str,
    asset_hash: str,
) -> dict[str, Any]:
    return {
        "id": id,
        "occurrenceId": occurrence_id,
        "nodeType": "part",
        "displayName": display_name,
        "sourceKind": source_kind,
        "sourcePath": source_path,
        "instancePath": instance_path,
        "useSourceColors": use_source_colors,
        "localTransform": _transform_list(local_transform),
        "worldTransform": _transform_list(world_transform),
        "bbox": bbox,
        "topologyCounts": _public_topology_counts(topology_counts),
        "assets": {
            "glb": {
                "url": asset_url,
                "hash": asset_hash,
            }
        },
        "leafPartIds": [id],
        "children": [],
    }


def _assembly_node(
    *,
    id: str,
    occurrence_id: str,
    display_name: str,
    source_kind: str,
    source_path: str,
    instance_path: str,
    use_source_colors: bool,
    local_transform: Sequence[float],
    world_transform: Sequence[float],
    bbox: Any,
    topology_counts: Mapping[str, int],
    children: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    leaf_part_ids = _leaf_part_ids(children)
    return {
        "id": id,
        "occurrenceId": occurrence_id,
        "nodeType": "assembly",
        "displayName": display_name,
        "sourceKind": source_kind,
        "sourcePath": source_path,
        "instancePath": instance_path,
        "useSourceColors": use_source_colors,
        "localTransform": _transform_list(local_transform),
        "worldTransform": _transform_list(world_transform),
        "bbox": bbox,
        "topologyCounts": _public_topology_counts(topology_counts),
        "leafPartIds": leaf_part_ids,
        "children": list(children),
    }


def _leaf_part_ids(children: Sequence[Mapping[str, Any]]) -> list[str]:
    ids: list[str] = []
    for child in children:
        child_ids = child.get("leafPartIds")
        if isinstance(child_ids, list):
            ids.extend(str(value) for value in child_ids if str(value or "").strip())
            continue
        child_id = str(child.get("id") or "").strip()
        if child_id:
            ids.append(child_id)
    return ids


def _assembly_root_node(cad_ref: str, root_occurrence: dict[str, Any], children: Sequence[dict[str, Any]]) -> dict[str, Any]:
    counts = _sum_public_counts(children)
    if not _counts_have_values(counts):
        counts = _public_topology_counts(_occurrence_topology_counts(root_occurrence))
    return _assembly_node(
        id="root",
        occurrence_id=str(root_occurrence.get("id") or "root").strip() or "root",
        display_name=_root_display_name(cad_ref, root_occurrence),
        source_kind="catalog",
        source_path="",
        instance_path="",
        use_source_colors=True,
        local_transform=IDENTITY_TRANSFORM,
        world_transform=IDENTITY_TRANSFORM,
        bbox=root_occurrence.get("bbox") or _merge_bbox([child.get("bbox") for child in children]),
        topology_counts=counts,
        children=children,
    )


def _root_display_name(cad_ref: str, root_occurrence: Mapping[str, Any]) -> str:
    display_name = str(root_occurrence.get("name") or "").strip()
    if not display_name or display_name.lower() == "root":
        return cad_ref.rsplit("/", 1)[-1]
    return display_name


def _rows(manifest: dict[str, Any], row_key: str, columns_key: str) -> list[dict[str, Any]]:
    columns = manifest.get("tables", {}).get(columns_key)
    rows = manifest.get(row_key)
    if not isinstance(columns, list) or not isinstance(rows, list):
        return []
    output: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, list):
            output.append({str(column): row[index] if index < len(row) else None for index, column in enumerate(columns)})
    return output


def _component_occurrences(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    occurrences = _rows(manifest, "occurrences", "occurrenceColumns")
    parent_ids = {
        str(row.get("parentId") or "").strip()
        for row in occurrences
        if str(row.get("parentId") or "").strip()
    }
    candidate_occurrences = [
        row
        for row in occurrences
        if str(row.get("parentId") or "").strip() and int(row.get("shapeCount") or 0) > 0
    ]
    if candidate_occurrences:
        return candidate_occurrences

    leaf_occurrences = [
        row
        for row in occurrences
        if str(row.get("id") or "").strip() not in parent_ids and int(row.get("shapeCount") or 0) > 0
    ]
    if not leaf_occurrences:
        leaf_occurrences = [
            row
            for row in occurrences
            if int(row.get("shapeCount") or 0) > 0
        ]
    if not leaf_occurrences:
        raise AssemblyCompositionError("Assembly topology has no component occurrences")
    return leaf_occurrences


def _find_occurrence_by_component_name(
    component: str,
    occurrences: Sequence[dict[str, Any]],
    cad_ref: str,
) -> dict[str, Any] | None:
    matches = []
    for occurrence in occurrences:
        names = {
            str(occurrence.get("name") or "").strip(),
            str(occurrence.get("sourceName") or "").strip(),
        }
        if component in names:
            matches.append(occurrence)
    if len(matches) > 1:
        raise AssemblyCompositionError(
            f"Assembly topology has duplicate component occurrence name for {cad_ref}: {component}"
        )
    return matches[0] if matches else None


def _read_json(path: Path) -> dict[str, Any]:
    import json

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AssemblyCompositionError(f"Failed to read JSON: {relative_to_repo(path)}") from exc
    if not isinstance(payload, dict):
        raise AssemblyCompositionError(f"Expected JSON object: {relative_to_repo(path)}")
    return payload


def _source_topology_counts(topology_manifest_path: Path) -> dict[str, int]:
    manifest = _read_json(topology_manifest_path)
    stats = manifest.get("stats")
    if not isinstance(stats, dict):
        raise AssemblyCompositionError(
            f"Source topology is missing stats: {relative_to_repo(topology_manifest_path)}"
        )
    counts = {
        "shapes": int(stats.get("shapeCount") or 0),
        "faces": int(stats.get("faceCount") or 0),
        "edges": int(stats.get("edgeCount") or 0),
        "vertices": int(stats.get("vertexCount") or 0),
    }
    if any(value <= 0 for value in counts.values()):
        raise AssemblyCompositionError(
            f"Source topology has invalid counts in {relative_to_repo(topology_manifest_path)}: {counts}"
        )
    return counts


def _occurrence_topology_counts(occurrence: Mapping[str, Any]) -> dict[str, int]:
    return {
        "shapes": int(occurrence.get("shapeCount") or 0),
        "faces": int(occurrence.get("faceCount") or 0),
        "edges": int(occurrence.get("edgeCount") or 0),
        "vertices": int(occurrence.get("vertexCount") or 0),
    }


def _public_topology_counts(counts: Mapping[str, int]) -> dict[str, int]:
    return {
        "shapes": int(counts.get("shapes") or 0),
        "faces": int(counts.get("faces") or 0),
        "edges": int(counts.get("edges") or 0),
        "vertices": int(counts.get("vertices") or 0),
    }


def _sum_public_counts(children: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    total = {"shapes": 0, "faces": 0, "edges": 0, "vertices": 0}
    for child in children:
        counts = child.get("topologyCounts")
        if not isinstance(counts, Mapping):
            continue
        for key in total:
            total[key] += int(counts.get(key) or 0)
    return total


def _counts_have_values(counts: Mapping[str, int]) -> bool:
    return any(int(counts.get(key) or 0) > 0 for key in ("shapes", "faces", "edges", "vertices"))


def _occurrence_display_name(row: Mapping[str, Any]) -> str:
    name = str(row.get("name") or "").strip()
    source_name = str(row.get("sourceName") or "").strip()
    if name and not (name.startswith("=>[") and name.endswith("]")):
        return name
    return source_name or name or str(row.get("path") or row.get("id") or "component").strip()


def _row_transform(row: Mapping[str, Any]) -> tuple[float, ...]:
    raw_transform = row.get("transform")
    if not isinstance(raw_transform, list) or len(raw_transform) != 16:
        return IDENTITY_TRANSFORM
    return tuple(float(value) for value in raw_transform)


def _transform_tuple(raw_transform: Any, fallback: Sequence[float]) -> tuple[float, ...]:
    if not isinstance(raw_transform, list) or len(raw_transform) != 16:
        return tuple(float(value) for value in fallback)
    return tuple(float(value) for value in raw_transform)


def _transform_list(transform: Sequence[float]) -> list[float]:
    return [float(value) for value in transform]


def _transform_point(transform: Sequence[float], point: Sequence[float]) -> list[float]:
    x = float(point[0])
    y = float(point[1])
    z = float(point[2])
    return [
        (float(transform[0]) * x) + (float(transform[1]) * y) + (float(transform[2]) * z) + float(transform[3]),
        (float(transform[4]) * x) + (float(transform[5]) * y) + (float(transform[6]) * z) + float(transform[7]),
        (float(transform[8]) * x) + (float(transform[9]) * y) + (float(transform[10]) * z) + float(transform[11]),
    ]


def _transform_bbox(transform: Sequence[float], bbox: Any) -> dict[str, Any] | None:
    if not isinstance(bbox, Mapping) or not isinstance(bbox.get("min"), list) or not isinstance(bbox.get("max"), list):
        return None
    mins = bbox["min"]
    maxs = bbox["max"]
    corners = [
        [mins[0], mins[1], mins[2]],
        [mins[0], mins[1], maxs[2]],
        [mins[0], maxs[1], mins[2]],
        [mins[0], maxs[1], maxs[2]],
        [maxs[0], mins[1], mins[2]],
        [maxs[0], mins[1], maxs[2]],
        [maxs[0], maxs[1], mins[2]],
        [maxs[0], maxs[1], maxs[2]],
    ]
    transformed = [_transform_point(transform, corner) for corner in corners]
    return {
        "min": [min(point[index] for point in transformed) for index in range(3)],
        "max": [max(point[index] for point in transformed) for index in range(3)],
    }


def _merge_bbox(boxes: Sequence[Any]) -> dict[str, Any]:
    valid_boxes = [
        box
        for box in boxes
        if isinstance(box, Mapping) and isinstance(box.get("min"), list) and isinstance(box.get("max"), list)
    ]
    if not valid_boxes:
        return {"min": [0.0, 0.0, 0.0], "max": [0.0, 0.0, 0.0]}
    mins = [list(box["min"]) for box in valid_boxes]
    maxs = [list(box["max"]) for box in valid_boxes]
    return {
        "min": [min(float(point[index]) for point in mins) for index in range(3)],
        "max": [max(float(point[index]) for point in maxs) for index in range(3)],
    }


def _relative_transform(parent_world_transform: tuple[float, ...], world_transform: tuple[float, ...]) -> tuple[float, ...]:
    return multiply_transforms(_invert_affine_transform(parent_world_transform), world_transform)


def _invert_affine_transform(transform: tuple[float, ...]) -> tuple[float, ...]:
    a, b, c, tx, d, e, f, ty, g, h, i, tz = transform[:12]
    det = (
        a * (e * i - f * h)
        - b * (d * i - f * g)
        + c * (d * h - e * g)
    )
    if abs(det) <= 1e-12:
        return IDENTITY_TRANSFORM
    inv_det = 1.0 / det
    r00 = (e * i - f * h) * inv_det
    r01 = (c * h - b * i) * inv_det
    r02 = (b * f - c * e) * inv_det
    r10 = (f * g - d * i) * inv_det
    r11 = (a * i - c * g) * inv_det
    r12 = (c * d - a * f) * inv_det
    r20 = (d * h - e * g) * inv_det
    r21 = (b * g - a * h) * inv_det
    r22 = (a * e - b * d) * inv_det
    return (
        r00,
        r01,
        r02,
        -((r00 * tx) + (r01 * ty) + (r02 * tz)),
        r10,
        r11,
        r12,
        -((r10 * tx) + (r11 * ty) + (r12 * tz)),
        r20,
        r21,
        r22,
        -((r20 * tx) + (r21 * ty) + (r22 * tz)),
        0.0,
        0.0,
        0.0,
        1.0,
    )
