"""Reconstruct a loaded STEP scene from its render package.

The render package (store-primary, content-keyed) already stores everything a
scene holds: each unique prototype as an exact ``components/<cid>.brep`` blob
(the same BinTools serialization the old scene cache wrote), the occurrence
tree with names/transforms/colors in ``assembly.json``, and per-face colors in
each component's ``.surf`` index. So the package IS the warm-load cache —
there is no second geometry store. ``load_step_scene_cached`` keeps its name
and contract (warm loads skip the text-STEP parse) but now reads the package;
a STEP with no current package pays one full parse, and the package the entry
build then writes makes the next load warm.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from cadgen._internal.step_hash import step_file_hash
from cadgen._internal.step_scene_loader import (
    _location_from_transform_matrix,
    _shape_hash,
    load_step_scene,
)
from cadgen._internal.step_scene_types import ColorRGBA, LoadedStepScene, OccurrenceNode

_IDENTITY_TRANSFORM = (
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
)


def _shape_from_brep(path: Path) -> Any | None:
    from OCP.BinTools import BinTools
    from OCP.TopoDS import TopoDS_Shape

    try:
        payload = path.read_bytes()
    except OSError:
        return None
    shape = TopoDS_Shape()
    try:
        BinTools.Read_s(shape, io.BytesIO(payload))
    except Exception:  # noqa: BLE001 - unreadable blob -> reparse the STEP instead
        return None
    return None if shape.IsNull() else shape


def _face_colors_from_surf(surf_path: Path, shape: Any) -> dict[int, ColorRGBA]:
    """Hash-keyed per-face colors from the component's .surf index.

    The surf keys colors by face ORDINAL (TopExp.MapShapes order), which the
    BinTools round-trip preserves, so mapping ordinal -> loaded face -> hash
    reproduces the scene loader's hash-keyed dict for downstream consumers
    (3MF/GLB export materials)."""
    from cadgen._internal.surface_extract import read_surf

    try:
        index, _ = read_surf(surf_path.read_bytes())
    except Exception:  # noqa: BLE001 - a missing/old surf simply has no colors
        return {}
    colors_by_ordinal: dict[int, ColorRGBA] = {}
    for face in index.get("faces") or []:
        color = face.get("color")
        if isinstance(color, list) and len(color) == 4:
            colors_by_ordinal[int(face.get("ord", 0))] = tuple(float(c) for c in color)
    if not colors_by_ordinal:
        return {}
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape

    face_map = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_ShapeEnum.TopAbs_FACE, face_map)
    face_colors: dict[int, ColorRGBA] = {}
    for ordinal, color in colors_by_ordinal.items():
        if 1 <= ordinal <= face_map.Extent():
            face_colors[_shape_hash(face_map.FindKey(ordinal))] = color
    return face_colors


def _transform_tuple(raw: object) -> tuple[float, ...]:
    if isinstance(raw, list) and len(raw) == 16:
        return tuple(float(value) for value in raw)
    return _IDENTITY_TRANSFORM


def _path_from_occurrence_id(occurrence_id: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in occurrence_id.lstrip("o").split("."))
    except ValueError:
        return (1,)


def scene_from_render_package(step_path: Path, *, step_hash: str) -> LoadedStepScene | None:
    """A LoadedStepScene rebuilt from the entry's render package, or None when
    the package is absent or unreadable — every miss falls back to the
    text-STEP parse. Content keying answers schema and hash by construction:
    a package that resolves for these bytes is current-scheme and theirs."""
    from cadgen.catalog import result_descriptor_for
    from cadgen.store.objects import object_path

    descriptor = result_descriptor_for(step_path)
    if not isinstance(descriptor, dict) or descriptor.get("kind") != "assembly-package":
        return None
    components = descriptor.get("components")
    occurrences = descriptor.get("occurrences")
    if not isinstance(components, dict) or not isinstance(occurrences, list) or not occurrences:
        return None

    prototype_shapes: dict[int, Any] = {}
    prototype_names: dict[int, str | None] = {}
    prototype_colors: dict[int, ColorRGBA] = {}
    prototype_face_colors: dict[int, dict[int, ColorRGBA]] = {}
    key_by_cid: dict[str, int] = {}
    for cid, entry in components.items():
        if not isinstance(entry, dict):
            return None
        try:
            brep_path = object_path(str(entry.get("brep") or ""))
            surf_path = object_path(str(entry.get("surf") or ""))
        except ValueError:
            return None
        shape = _shape_from_brep(brep_path)
        if shape is None:
            return None
        key = _shape_hash(shape)
        key_by_cid[str(cid)] = key
        prototype_shapes[key] = shape
        color = entry.get("color")
        if isinstance(color, list) and len(color) == 4:
            prototype_colors[key] = tuple(float(c) for c in color)
        face_colors = _face_colors_from_surf(surf_path, shape)
        if face_colors:
            prototype_face_colors[key] = face_colors

    occurrence_by_id: dict[str, dict[str, Any]] = {
        str(occ.get("id")): occ for occ in occurrences if isinstance(occ, dict)
    }

    def leaf_node(occ: dict[str, Any]) -> OccurrenceNode | None:
        key = key_by_cid.get(str(occ.get("component")))
        if key is None:
            return None
        transform = _transform_tuple(occ.get("transform"))
        name = str(occ.get("name") or "") or None
        color = occ.get("color")
        node = OccurrenceNode(
            path=_path_from_occurrence_id(str(occ.get("id") or "o1")),
            name=name,
            source_name=name,
            transform=transform,
            prototype_key=key,
            local_transform=transform,
            color=tuple(float(c) for c in color) if isinstance(color, list) and len(color) == 4 else None,
            location=_location_from_transform_matrix(transform),
        )
        if name and prototype_names.get(key) is None:
            prototype_names[key] = name
        return node

    assembly = descriptor.get("assembly")
    roots: list[OccurrenceNode]
    if isinstance(assembly, dict) and isinstance(assembly.get("root"), dict):
        def build(tree_node: dict[str, Any]) -> OccurrenceNode | None:
            children_meta = tree_node.get("children") or []
            node_id = str(tree_node.get("id") or "o1")
            if not children_meta:
                occ = occurrence_by_id.get(node_id)
                return leaf_node(occ) if occ is not None else None
            children = [child for child in (build(c) for c in children_meta if isinstance(c, dict)) if child]
            if not children:
                return None
            name = str(tree_node.get("name") or "") or None
            return OccurrenceNode(
                path=_path_from_occurrence_id(node_id),
                name=name,
                source_name=name,
                transform=_IDENTITY_TRANSFORM,
                prototype_key=None,
                local_transform=_IDENTITY_TRANSFORM,
                color=None,
                location=None,
                children=children,
            )

        root = build(assembly["root"])
        if root is None:
            return None
        roots = [root]
    else:
        # Part-kind package: one occurrence holding the whole geometry.
        roots = [node for node in (leaf_node(occ) for occ in occurrences if isinstance(occ, dict)) if node]
        if not roots:
            return None

    scene = LoadedStepScene(
        step_path=step_path,
        roots=roots,
        prototype_shapes=prototype_shapes,
        prototype_names=prototype_names,
        prototype_colors=prototype_colors,
        prototype_face_colors=prototype_face_colors,
        step_hash=step_hash,
        source_kind="step",
    )
    return scene


def load_step_scene_cached(step_path: Path) -> LoadedStepScene:
    """Load a STEP scene, warm from its render package when one is current."""
    resolved_step_path = step_path.expanduser().resolve()
    if not resolved_step_path.exists():
        raise FileNotFoundError(f"STEP file does not exist: {resolved_step_path}")
    step_hash = step_file_hash(resolved_step_path)
    from_package = scene_from_render_package(resolved_step_path, step_hash=step_hash)
    if from_package is not None:
        return from_package
    scene = load_step_scene(resolved_step_path)
    scene.step_hash = step_hash
    return scene
