from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any

from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS
from OCP.TopoDS import TopoDS_Shape

from cadgen.catalog import CADGEN_DIRNAME
from cadgen.catalog import CADGEN_MODELS_DIRNAME

from cadgen._internal.step_scene_loader import _location_from_transform_matrix, _relative_path_from_directory, _shape_hash, _step_hash, load_step_scene
from cadgen._internal.step_scene_types import ColorRGBA, LoadedStepScene, OccurrenceNode, STEP_SCENE_CACHE_SCHEMA_VERSION, _STEP_SCENE_CACHE_BINTOOLS_VERSION, _identity_transform_matrix


_STEP_SCENE_CACHE_DIRNAME = CADGEN_DIRNAME
_STEP_SCENE_CACHE_MODELS_DIRNAME = CADGEN_MODELS_DIRNAME
# Subdir holding the content-hash scene leaves, isolated from the render package files.
_STEP_SCENE_CACHE_SUBDIR = "scene"


def _step_scene_cache_enabled() -> bool:
    value = os.environ.get("TEXT_TO_CAD_STEP_SCENE_CACHE", "1").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _path_is_skill_runtime(path: Path) -> bool:
    resolved = path.expanduser().resolve()
    return any((candidate / "SKILL.md").is_file() for candidate in (resolved, *resolved.parents))


def _step_scene_cache_dir(step_path: Path, step_hash: str) -> Path | None:
    """Inline binary-scene cache directory for a STEP file.

    Written under
    ``<base>/__cadgen__/models/<step-filename>/scene/v<schema>-<hash>`` so it sits
    inside the same per-model ``__cadgen__/models`` home as the component-GLB render
    package and generation lock (like ``__pycache__`` beside a ``.py``). Honors
    ``TEXT_TO_CAD_STEP_SCENE_CACHE=0`` (disabled) and
    ``TEXT_TO_CAD_STEP_SCENE_CACHE_DIR`` (central override); falls back to a temp store
    when the STEP lives inside a packaged skill runtime so the cache never pollutes
    shipped skill files.
    """
    if not _step_scene_cache_enabled():
        return None
    resolved = step_path.expanduser().resolve()
    configured = os.environ.get("TEXT_TO_CAD_STEP_SCENE_CACHE_DIR")
    if configured:
        base = Path(configured).expanduser().resolve()
    elif _path_is_skill_runtime(resolved.parent):
        base = Path(tempfile.gettempdir()).resolve() / "cadgen-step-scene-cache"
    else:
        base = resolved.parent
    leaf = f"v{STEP_SCENE_CACHE_SCHEMA_VERSION}-{step_hash}"
    return (
        base
        / _STEP_SCENE_CACHE_DIRNAME
        / _STEP_SCENE_CACHE_MODELS_DIRNAME
        / resolved.name
        / _STEP_SCENE_CACHE_SUBDIR
        / leaf
    )


def _rgba_to_cache_value(color: ColorRGBA | None) -> list[float] | None:
    return None if color is None else [float(component) for component in color]


def _rgba_from_cache_value(value: object) -> ColorRGBA | None:
    if not isinstance(value, list) or len(value) < 3:
        return None
    rgba = [float(component) for component in value[:4]]
    if len(rgba) == 3:
        rgba.append(1.0)
    return (rgba[0], rgba[1], rgba[2], rgba[3])


def _node_to_cache_payload(node: OccurrenceNode) -> dict[str, Any]:
    return {
        "path": [int(value) for value in node.path],
        "name": node.name,
        "sourceName": node.source_name,
        "transform": [float(value) for value in node.transform],
        "localTransform": [float(value) for value in node.local_transform],
        "prototypeKey": node.prototype_key,
        "color": _rgba_to_cache_value(node.color),
        "children": [_node_to_cache_payload(child) for child in node.children],
    }


def _node_from_cache_payload(payload: object) -> OccurrenceNode:
    if not isinstance(payload, dict):
        raise ValueError("cached occurrence node must be an object")
    transform = tuple(float(value) for value in payload.get("transform", _identity_transform_matrix()))
    local_transform = tuple(float(value) for value in payload.get("localTransform", _identity_transform_matrix()))
    if len(transform) != 16 or len(local_transform) != 16:
        raise ValueError("cached occurrence node has an invalid transform")
    prototype_key = payload.get("prototypeKey")
    return OccurrenceNode(
        path=tuple(int(value) for value in payload.get("path", ())),
        name=payload.get("name") if payload.get("name") is None else str(payload.get("name")),
        source_name=payload.get("sourceName") if payload.get("sourceName") is None else str(payload.get("sourceName")),
        transform=transform,
        local_transform=local_transform,
        prototype_key=None if prototype_key is None else int(prototype_key),
        color=_rgba_from_cache_value(payload.get("color")),
        location=_location_from_transform_matrix(transform),
        children=[_node_from_cache_payload(child) for child in payload.get("children", [])],
    )


def _face_index_color_payload(shape: object, face_colors: dict[int, ColorRGBA]) -> list[list[object]]:
    if not face_colors:
        return []
    payload: list[list[object]] = []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    face_index = 0
    while explorer.More():
        face_hash = _shape_hash(TopoDS.Face_s(explorer.Current()))
        color = face_colors.get(face_hash)
        if color is not None:
            payload.append([face_index, _rgba_to_cache_value(color)])
        face_index += 1
        explorer.Next()
    return payload


def _face_colors_from_index_payload(shape: object, payload: object) -> dict[int, ColorRGBA]:
    if not isinstance(payload, list) or not payload:
        return {}
    colors_by_index: dict[int, ColorRGBA] = {}
    for raw_item in payload:
        if not isinstance(raw_item, list) or len(raw_item) != 2:
            continue
        color = _rgba_from_cache_value(raw_item[1])
        if color is None:
            continue
        colors_by_index[int(raw_item[0])] = color
    face_colors: dict[int, ColorRGBA] = {}
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    face_index = 0
    while explorer.More():
        color = colors_by_index.get(face_index)
        if color is not None:
            face_colors[_shape_hash(TopoDS.Face_s(explorer.Current()))] = color
        face_index += 1
        explorer.Next()
    return face_colors


def _read_step_scene_cache(step_path: Path, *, step_hash: str) -> LoadedStepScene | None:
    from OCP.BinTools import BinTools

    started = time.perf_counter()
    cache_dir = _step_scene_cache_dir(step_path, step_hash)
    if cache_dir is None:
        return None
    meta_path = cache_dir / "scene.json"
    if not meta_path.is_file():
        return None
    try:
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        if metadata.get("schemaVersion") != STEP_SCENE_CACHE_SCHEMA_VERSION:
            return None
        if metadata.get("stepHash") != step_hash:
            return None
        prototypes = metadata.get("prototypes")
        if not isinstance(prototypes, list):
            return None
        prototype_shapes: dict[int, Any] = {}
        prototype_names: dict[int, str | None] = {}
        prototype_colors: dict[int, ColorRGBA] = {}
        prototype_face_colors: dict[int, dict[int, ColorRGBA]] = {}
        for index, prototype in enumerate(prototypes):
            if not isinstance(prototype, dict):
                return None
            prototype_key = int(prototype["key"])
            brep_file = str(prototype.get("file") or f"prototype-{index}.bin")
            if "/" in brep_file or "\\" in brep_file:
                return None
            brep_path = cache_dir / brep_file
            if not brep_path.is_file():
                return None
            shape = TopoDS_Shape()
            if not BinTools.Read_s(shape, os.fspath(brep_path)) or shape.IsNull():
                return None
            prototype_shapes[prototype_key] = shape
            name = prototype.get("name")
            prototype_names[prototype_key] = None if name is None else str(name)
            color = _rgba_from_cache_value(prototype.get("color"))
            if color is not None:
                prototype_colors[prototype_key] = color
            face_colors = _face_colors_from_index_payload(shape, prototype.get("faceIndexColors"))
            if face_colors:
                prototype_face_colors[prototype_key] = face_colors
        roots = [_node_from_cache_payload(node) for node in metadata.get("roots", [])]
        if not roots or not prototype_shapes:
            return None
        return LoadedStepScene(
            step_path=step_path,
            roots=roots,
            prototype_shapes=prototype_shapes,
            prototype_names=prototype_names,
            prototype_colors=prototype_colors,
            prototype_face_colors=prototype_face_colors,
            load_elapsed=time.perf_counter() - started,
            step_hash=step_hash,
        )
    except Exception:  # noqa: BLE001 - any load failure returns None; callers fall back to a direct load
        return None


def _write_step_scene_cache(scene: LoadedStepScene, *, step_hash: str) -> None:
    from OCP.BinTools import BinTools, BinTools_FormatVersion

    bintools_version = getattr(
        BinTools_FormatVersion,
        f"BinTools_FormatVersion_VERSION_{_STEP_SCENE_CACHE_BINTOOLS_VERSION}",
    )
    cache_dir = _step_scene_cache_dir(scene.step_path, step_hash)
    if cache_dir is None:
        return
    if (cache_dir / "scene.json").is_file():
        return
    temp_dir = cache_dir.parent / f".{cache_dir.name}.{os.getpid()}.tmp"
    try:
        cache_dir.parent.mkdir(parents=True, exist_ok=True)
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        temp_dir.mkdir(parents=True, exist_ok=False)
        prototypes: list[dict[str, Any]] = []
        for index, (prototype_key, shape) in enumerate(scene.prototype_shapes.items()):
            brep_file = f"prototype-{index}.bin"
            if not BinTools.Write_s(
                shape,
                os.fspath(temp_dir / brep_file),
                False,
                False,
                bintools_version,
            ):
                raise RuntimeError("failed to write cached BREP prototype")
            prototypes.append(
                {
                    "key": int(prototype_key),
                    "file": brep_file,
                    "name": scene.prototype_names.get(prototype_key),
                    "color": _rgba_to_cache_value(scene.prototype_colors.get(prototype_key)),
                    "faceIndexColors": _face_index_color_payload(
                        shape,
                        scene.prototype_face_colors.get(prototype_key, {}),
                    ),
                }
            )
        metadata = {
            "schemaVersion": STEP_SCENE_CACHE_SCHEMA_VERSION,
            "stepHash": step_hash,
            "sourcePath": _relative_path_from_directory(scene.step_path, temp_dir),
            "roots": [_node_to_cache_payload(root_node) for root_node in scene.roots],
            "prototypes": prototypes,
        }
        (temp_dir / "scene.json").write_text(
            json.dumps(metadata, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        try:
            temp_dir.rename(cache_dir)
            _prune_step_scene_cache_siblings(cache_dir)
        except FileExistsError:
            shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:  # noqa: BLE001 - a failed cache write must not fail the load; drop the temp dir
        shutil.rmtree(temp_dir, ignore_errors=True)


def _prune_step_scene_cache_siblings(cache_dir: Path) -> None:
    """Drop stale cache entries for this STEP (older hashes / schema versions),
    keeping only the just-written ``cache_dir`` so __cadgen__ does not accumulate."""
    try:
        for sibling in cache_dir.parent.iterdir():
            if sibling.name == cache_dir.name or sibling.name.endswith(".tmp"):
                continue
            shutil.rmtree(sibling, ignore_errors=True)
    except Exception:  # noqa: BLE001 - cache pruning is best-effort housekeeping
        pass


def load_step_scene_cached(step_path: Path) -> LoadedStepScene:
    resolved_step_path = step_path.expanduser().resolve()
    if not resolved_step_path.exists():
        raise FileNotFoundError(f"STEP file does not exist: {resolved_step_path}")
    step_hash = _step_hash(resolved_step_path)
    cached = _read_step_scene_cache(resolved_step_path, step_hash=step_hash)
    if cached is not None:
        return cached
    scene = load_step_scene(resolved_step_path)
    scene.step_hash = step_hash
    _write_step_scene_cache(scene, step_hash=step_hash)
    return scene


