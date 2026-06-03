from __future__ import annotations
import copy
from contextlib import nullcontext
import hashlib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Sequence

from cadpy.assembly_flatten import AssemblyResolutionError, CatalogEntry
from cadpy.assembly_spec import (
    REPO_ROOT,
    AssemblySpec,
    AssemblySpecError,
    AssemblyNodeSpec,
    IDENTITY_TRANSFORM,
    assembly_spec_from_payload,
    assembly_spec_children,
    read_assembly_spec,
)
from cadpy.catalog import (
    CadSource,
    cad_ref_from_step_path,
    iter_cad_sources,
    normalize_cad_ref,
    source_from_path,
)
from cadpy.glb import read_step_topology_manifest_from_glb
from cadpy.render import existing_part_glb_path, part_glb_path
from cadpy.step_export import create_bin_xcaf_doc, export_xcaf_doc_step_scene
from cadpy.step_scene import (
    LoadedStepScene,
    _shape_hash,
    load_step_scene,
    load_step_scene_cached,
    load_step_scene_from_xcaf_doc,
    occurrence_selector_id,
)


GIT_LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1\n"


@dataclass
class _AssemblyBuildCache:
    resolver: "_AssemblyCatalogResolver"
    step_shapes: dict[tuple[Path, bool, tuple[float, float, float, float] | None], object] = field(default_factory=dict)
    step_has_assembly: dict[Path, bool] = field(default_factory=dict)
    step_scenes: dict[Path, LoadedStepScene] = field(default_factory=dict)
    source_colors: dict[str, tuple[float, float, float, float] | None] = field(default_factory=dict)


@dataclass
class _AssemblyCatalogResolver:
    sources: tuple[CadSource, ...] | None = None
    by_path: dict[Path, CadSource] = field(default_factory=dict)
    by_cad_ref: dict[str, CadSource] = field(default_factory=dict)
    entries: dict[Path, CatalogEntry | None] = field(default_factory=dict)
    assembly_specs: dict[Path, AssemblySpec] = field(default_factory=dict)

    def _ensure_index(self) -> None:
        if self.sources is not None:
            return
        self.sources = iter_cad_sources()
        for source in self.sources:
            self.by_cad_ref[source.cad_ref] = source
            for path in (
                source.source_path,
                source.step_path,
                source.script_path,
                source.dxf_path,
                source.urdf_path,
                *source.generated_paths,
            ):
                if path is not None:
                    self.by_path[path.resolve()] = source

    def source_for_path(self, source_path: Path) -> CadSource | None:
        self._ensure_index()
        resolved = source_path.resolve()
        source = self.by_path.get(resolved)
        if source is not None:
            return source
        return source_from_path(resolved) if resolved.exists() else None

    def source_color_for_cad_ref(self, cad_ref: str):
        self._ensure_index()
        normalized = normalize_cad_ref(cad_ref)
        source = self.by_cad_ref.get(normalized or "")
        return source.color if source is not None else None

    def entry_for_path(self, source_path: Path) -> CatalogEntry | None:
        resolved = source_path.resolve()
        if resolved in self.entries:
            return self.entries[resolved]
        entry = self._entry_for_resolved_path(resolved)
        self.entries[resolved] = entry
        return entry

    def _entry_for_resolved_path(self, resolved: Path) -> CatalogEntry | None:
        source = self.source_for_path(resolved)
        if source is None:
            if not resolved.is_file() or resolved.suffix.lower() not in {".step", ".stp"}:
                return None
            cad_ref = cad_ref_from_step_path(resolved)
            return CatalogEntry(
                cad_ref=cad_ref,
                source_ref=_relative_to_repo(resolved),
                kind="part",
                source_path=resolved,
                step_path=resolved,
                glb_path=existing_part_glb_path(resolved) or part_glb_path(resolved),
            )
        if source.kind == "assembly" and source.script_path is not None:
            try:
                assembly_spec = self._assembly_spec_for_source(source)
            except AssemblySpecError as exc:
                raise AssemblyResolutionError(str(exc)) from exc
            return CatalogEntry(
                cad_ref=source.cad_ref,
                source_ref=source.source_ref,
                kind="assembly",
                source_path=source.source_path,
                step_path=source.step_path,
                assembly_spec=assembly_spec,
            )
        if source.step_path is None:
            return None
        return CatalogEntry(
            cad_ref=source.cad_ref,
            source_ref=source.source_ref,
            kind="part",
            source_path=source.source_path,
            step_path=source.step_path,
            stl_path=source.stl_path,
            glb_path=existing_part_glb_path(source.step_path) or part_glb_path(source.step_path),
        )

    def _assembly_spec_for_source(self, source: CadSource) -> AssemblySpec:
        resolved = source.source_path.resolve()
        cached = self.assembly_specs.get(resolved)
        if cached is None:
            cached = read_assembly_spec(resolved)
            self.assembly_specs[resolved] = cached
        return cached


def _relative_to_repo(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.expanduser().resolve().open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_git_lfs_pointer(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(len(GIT_LFS_POINTER_PREFIX)) == GIT_LFS_POINTER_PREFIX
    except OSError:
        return False


def _location_from_transform(transform: tuple[float, ...]):
    import build123d
    from OCP.gp import gp_Trsf

    trsf = gp_Trsf()
    trsf.SetValues(
        transform[0],
        transform[1],
        transform[2],
        transform[3],
        transform[4],
        transform[5],
        transform[6],
        transform[7],
        transform[8],
        transform[9],
        transform[10],
        transform[11],
    )
    return build123d.Location(trsf)


@lru_cache(maxsize=4096)
def _toploc_from_transform(transform: tuple[float, ...]):
    from OCP.gp import gp_Trsf
    from OCP.TopLoc import TopLoc_Location

    trsf = gp_Trsf()
    trsf.SetValues(
        transform[0],
        transform[1],
        transform[2],
        transform[3],
        transform[4],
        transform[5],
        transform[6],
        transform[7],
        transform[8],
        transform[9],
        transform[10],
        transform[11],
    )
    return TopLoc_Location(trsf)


def _topods_shape_without_location(shape: object) -> object:
    from OCP.TopLoc import TopLoc_Location

    located = getattr(shape, "Located", None)
    if not callable(located):
        return shape
    try:
        return located(TopLoc_Location())
    except Exception:
        return shape


def _component_name(instance_path: tuple[str, ...]) -> str:
    return "__".join(instance_path) or "root"


def _load_step_shape(step_path: Path):
    if not step_path.exists():
        raise FileNotFoundError(f"Referenced STEP file is missing: {_relative_to_repo(step_path)}")
    if _is_git_lfs_pointer(step_path):
        raise RuntimeError(f"Referenced STEP file is a Git LFS pointer: {_relative_to_repo(step_path)}")

    import build123d

    try:
        return build123d.import_step(step_path)
    except Exception as exc:
        raise RuntimeError(f"Failed to load referenced STEP file: {_relative_to_repo(step_path)}") from exc


def _step_has_assembly_artifact(step_path: Path) -> bool | None:
    payload = read_step_topology_manifest_from_glb(existing_part_glb_path(step_path) or part_glb_path(step_path))
    if payload is None:
        return None
    step_hash = str(payload.get("stepHash") or "").strip()
    if not step_hash or step_hash != _file_sha256(step_path):
        return None
    root = payload.get("assembly", {}).get("root") if isinstance(payload.get("assembly"), dict) else None
    return isinstance(root, dict) and bool(root.get("children"))


def _scene_has_assembly_structure(scene: LoadedStepScene) -> bool:
    roots = list(getattr(scene, "roots", []) or [])
    if len(roots) > 1:
        return True
    stack = roots[:]
    while stack:
        node = stack.pop()
        children = list(getattr(node, "children", []) or [])
        if children:
            return True
        stack.extend(children)
    return False


def _cached_step_has_assembly_artifact(step_path: Path, *, cache: _AssemblyBuildCache) -> bool:
    resolved = step_path.resolve()
    cached = cache.step_has_assembly.get(resolved)
    if cached is None:
        artifact_has_assembly = _step_has_assembly_artifact(resolved)
        if artifact_has_assembly is None:
            try:
                artifact_has_assembly = _scene_has_assembly_structure(_cached_step_scene(resolved, cache=cache))
            except Exception:
                artifact_has_assembly = False
        cached = artifact_has_assembly
        cache.step_has_assembly[resolved] = cached
    return cached


def _cached_step_scene(step_path: Path, *, cache: _AssemblyBuildCache) -> LoadedStepScene:
    resolved = step_path.resolve()
    cached = cache.step_scenes.get(resolved)
    if cached is None:
        cached = load_step_scene_cached(resolved)
        cache.step_scenes[resolved] = cached
    return cached


def _load_step_assembly_shape(step_path: Path, *, label: str):
    import build123d

    from cadpy.step_scene import scene_occurrence_shape

    scene = load_step_scene(step_path)

    def node_label(node: object) -> str:
        return str(getattr(node, "name", None) or getattr(node, "source_name", None) or occurrence_selector_id(node)).strip()

    def build_node(node: object):
        children = list(getattr(node, "children", []) or [])
        if children:
            child_shapes = [build_node(child) for child in children]
            return build123d.Compound(
                children=child_shapes,
                label=node_label(node),
            )
        shape = build123d.Shape(obj=scene_occurrence_shape(scene, node))
        shape.label = node_label(node)
        return shape

    roots = [build_node(root) for root in scene.roots]
    if not roots:
        return _load_step_shape(step_path)
    return build123d.Compound(children=roots, label=label)


def _cached_source_color_for_cad_ref(cad_ref: str, *, cache: _AssemblyBuildCache) -> tuple[float, float, float, float] | None:
    if cad_ref not in cache.source_colors:
        color = cache.resolver.source_color_for_cad_ref(cad_ref)
        cache.source_colors[cad_ref] = None if color is None else tuple(float(value) for value in color)
    return cache.source_colors[cad_ref]


def _clear_shape_colors(shape: object) -> None:
    if hasattr(shape, "color"):
        shape.color = None
    for child in getattr(shape, "children", []) or []:
        _clear_shape_colors(child)


def _apply_source_color(shape: object, cad_ref: str, *, use_source_colors: bool, cache: _AssemblyBuildCache) -> None:
    import build123d

    source_color = _cached_source_color_for_cad_ref(cad_ref, cache=cache)
    if not use_source_colors:
        _clear_shape_colors(shape)
    elif source_color is not None:
        shape.color = build123d.Color(*source_color)


def _copy_cached_shape_tree(shape: object):
    import build123d
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy

    if getattr(shape, "children", None):
        copied = copy.copy(shape)
        copied.label = getattr(shape, "label", None)
    else:
        copier = BRepBuilderAPI_Copy(shape.wrapped, True, True)
        copied_shape = copier.Shape()
        copied = build123d.Shape(obj=copied_shape)
        copied.label = getattr(shape, "label", None)
    if hasattr(copied, "color"):
        copied.color = getattr(shape, "color", None)
    return copied


def _shape_for_part_entry(entry: CatalogEntry, *, use_source_colors: bool, cache: _AssemblyBuildCache):
    step_path = entry.step_path.resolve() if entry.step_path is not None else None
    if step_path is None:
        raise RuntimeError(f"Part source {entry.source_ref} is missing STEP source path")
    source_color = _cached_source_color_for_cad_ref(entry.cad_ref, cache=cache) if use_source_colors else None
    key = (step_path, bool(use_source_colors), source_color)
    cached = cache.step_shapes.get(key)
    if cached is not None:
        return cached
    shape = (
        _load_step_assembly_shape(step_path, label=Path(step_path).stem)
        if _cached_step_has_assembly_artifact(step_path, cache=cache)
        else _load_step_shape(step_path)
    )
    _apply_source_color(shape, entry.cad_ref, use_source_colors=use_source_colors, cache=cache)
    cache.step_shapes[key] = shape
    return shape


def _build_node_shape(
    node: AssemblyNodeSpec,
    *,
    resolve_entry,
    instance_path: tuple[str, ...],
    parent_use_source_colors: bool,
    stack: tuple[str, ...],
    cache: _AssemblyBuildCache,
):
    import build123d

    component_path = (*instance_path, node.instance_id) if instance_path else (node.instance_id,)
    label = _component_name(component_path)
    use_source_colors = parent_use_source_colors and node.use_source_colors
    copy_before_move = False

    if node.children:
        child_shapes = [
            _build_node_shape(
                child,
                resolve_entry=resolve_entry,
                instance_path=component_path,
                parent_use_source_colors=use_source_colors,
                stack=stack,
                cache=cache,
            )
            for child in node.children
        ]
        shape = build123d.Compound(children=child_shapes, label=label)
    else:
        if node.source_path is None or node.path is None:
            raise RuntimeError(f"Assembly node {label} is missing a STEP source path")
        child_entry = resolve_entry(node.source_path)
        if child_entry is None:
            raise RuntimeError(f"Assembly node {label} references missing CAD source {node.path}")
        if child_entry.kind == "assembly":
            if child_entry.assembly_spec is None:
                raise RuntimeError(f"Assembly source {child_entry.source_ref} is missing assembly spec data")
            stack_key = child_entry.source_ref
            if stack_key in stack:
                cycle = " -> ".join((*stack, stack_key))
                raise RuntimeError(f"Assembly cycle detected: {cycle}")
            shape = _compound_from_nodes(
                assembly_spec_children(child_entry.assembly_spec),
                label=label,
                resolve_entry=resolve_entry,
                instance_path=component_path,
                parent_use_source_colors=use_source_colors,
                stack=(*stack, stack_key),
                cache=cache,
            )
        elif child_entry.kind == "part":
            shape = _shape_for_part_entry(child_entry, use_source_colors=use_source_colors, cache=cache)
            copy_before_move = True
        else:
            raise RuntimeError(f"Assembly node {label} resolved to unsupported CAD source kind: {child_entry.kind}")

    if copy_before_move:
        shape = _copy_cached_shape_tree(shape)
    moved = shape.moved(_location_from_transform(node.transform))
    moved.label = label
    if not use_source_colors:
        _clear_shape_colors(moved)
    return moved


def _compound_from_nodes(
    nodes: Sequence[AssemblyNodeSpec],
    *,
    label: str,
    resolve_entry,
    instance_path: tuple[str, ...] = (),
    parent_use_source_colors: bool,
    stack: tuple[str, ...],
    cache: _AssemblyBuildCache,
):
    import build123d

    children = [
        _build_node_shape(
            node,
            resolve_entry=resolve_entry,
            instance_path=instance_path,
            parent_use_source_colors=parent_use_source_colors,
            stack=stack,
            cache=cache,
        )
        for node in nodes
    ]
    if not children:
        raise RuntimeError(f"Assembly {label} has no resolved STEP instances")
    return build123d.Compound(
        children=children,
        label=label,
    )


class _DirectXcafAssemblyWriter:
    def __init__(
        self,
        assembly_spec: AssemblySpec,
        *,
        label: str,
        resolver: _AssemblyCatalogResolver | None = None,
    ) -> None:
        from OCP.XCAFDoc import XCAFDoc_DocumentTool

        self.assembly_spec = assembly_spec
        self.label = label
        self.doc = create_bin_xcaf_doc()
        self.shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(self.doc.Main())
        self.color_tool = XCAFDoc_DocumentTool.ColorTool_s(self.doc.Main())
        self.resolver = resolver or _AssemblyCatalogResolver()
        self.cache = _AssemblyBuildCache(resolver=self.resolver)
        self.shape_definitions: dict[int, object] = {}
        self.step_scene_definitions: dict[tuple[Path, bool, tuple[float, float, float, float] | None], object] = {}
        self.step_scene_node_definitions: dict[
            tuple[Path, tuple[int, ...], bool, tuple[float, float, float, float] | None],
            object,
        ] = {}
        self.step_scene_prototype_definitions: dict[
            tuple[Path, int, bool, tuple[float, float, float, float] | None],
            object,
        ] = {}
        self.colors_by_rgba: dict[tuple[float, float, float, float], object] = {}

    def build_doc(self):
        root_label = self.shape_tool.NewShape()
        self._set_label_name(root_label, self.label)
        root_source = self.resolver.source_for_path(self.assembly_spec.assembly_path)
        root_source_ref = (
            root_source.source_ref
            if root_source is not None
            else _relative_to_repo(self.assembly_spec.assembly_path)
        )
        self._add_nodes_to_assembly(
            root_label,
            assembly_spec_children(self.assembly_spec),
            instance_path=(),
            parent_use_source_colors=True,
            stack=(root_source_ref,),
        )
        self.shape_tool.UpdateAssemblies()
        return self.doc

    def _set_label_name(self, label: object, name: str | None) -> None:
        if not name:
            return
        from OCP.TCollection import TCollection_ExtendedString
        from OCP.TDataStd import TDataStd_Name

        TDataStd_Name.Set_s(label, TCollection_ExtendedString(str(name)))

    def _set_label_color(self, label: object, color: object | None) -> None:
        if color is None:
            return
        from OCP.XCAFDoc import XCAFDoc_ColorType

        if isinstance(color, tuple):
            wrapped = self._quantity_color_rgba(color)
        else:
            wrapped = getattr(color, "wrapped", None)
            if wrapped is None:
                return
        self.color_tool.SetColor(label, wrapped, XCAFDoc_ColorType.XCAFDoc_ColorSurf)

    def _set_shape_face_colors(
        self,
        shape_label: object,
        shape: object,
        face_colors: dict[int, tuple[float, float, float, float]],
    ) -> None:
        if not face_colors:
            return
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS

        explorer = TopExp_Explorer(shape, TopAbs_FACE)
        while explorer.More():
            face = TopoDS.Face_s(explorer.Current())
            color = face_colors.get(_shape_hash(face))
            if color is not None:
                face_label = self.shape_tool.AddSubShape(shape_label, face)
                self._set_label_color(face_label, color)
            explorer.Next()

    def _quantity_color_rgba(self, color: tuple[float, ...]) -> object:
        from OCP.Quantity import Quantity_ColorRGBA

        values = tuple(max(0.0, min(1.0, float(component))) for component in color)
        if len(values) == 3:
            rgba = (values[0], values[1], values[2], 1.0)
        elif len(values) >= 4:
            rgba = (values[0], values[1], values[2], values[3])
        else:
            rgba = (0.72, 0.72, 0.72, 1.0)
        cached = self.colors_by_rgba.get(rgba)
        if cached is None:
            cached = Quantity_ColorRGBA(*rgba)
            self.colors_by_rgba[rgba] = cached
        return cached

    def _part_definition_for_entry(self, entry: CatalogEntry, *, use_source_colors: bool) -> object:
        step_path = entry.step_path.resolve() if entry.step_path is not None else None
        if step_path is None:
            raise RuntimeError(f"Part source {entry.source_ref} is missing STEP source path")
        if _cached_step_has_assembly_artifact(step_path, cache=self.cache):
            return self._step_scene_definition_for_entry(
                entry,
                step_path=step_path,
                use_source_colors=use_source_colors,
            )
        shape = _shape_for_part_entry(entry, use_source_colors=use_source_colors, cache=self.cache)
        return self._shape_definition_for_tree(shape)

    def _step_scene_definition_for_entry(
        self,
        entry: CatalogEntry,
        *,
        step_path: Path,
        use_source_colors: bool,
    ) -> object:
        source_color = _cached_source_color_for_cad_ref(entry.cad_ref, cache=self.cache) if use_source_colors else None
        key = (step_path, bool(use_source_colors), source_color)
        cached = self.step_scene_definitions.get(key)
        if cached is not None:
            return cached

        scene = _cached_step_scene(step_path, cache=self.cache)
        definition_label = self._new_assembly_definition(Path(step_path).stem)
        self.step_scene_definitions[key] = definition_label
        if source_color is not None:
            self._set_label_color(definition_label, source_color)

        for root in scene.roots:
            root_definition = self._step_scene_node_definition(
                scene,
                root,
                use_source_colors=use_source_colors,
                source_color=source_color,
            )
            root_component = self.shape_tool.AddComponent(
                definition_label,
                root_definition,
                _toploc_from_transform(root.local_transform),
            )
            self._set_label_name(root_component, self._step_scene_node_name(root))
            if use_source_colors:
                self._set_label_color(root_component, source_color or root.color)
        return definition_label

    def _step_scene_node_definition(
        self,
        scene: LoadedStepScene,
        node: object,
        *,
        use_source_colors: bool,
        source_color: tuple[float, float, float, float] | None,
    ) -> object:
        key = (
            scene.step_path.resolve(),
            tuple(getattr(node, "path", ())),
            bool(use_source_colors),
            source_color,
        )
        cached = self.step_scene_node_definitions.get(key)
        if cached is not None:
            return cached

        children = list(getattr(node, "children", []) or [])
        if children:
            definition_label = self._new_assembly_definition(self._step_scene_node_name(node))
            self.step_scene_node_definitions[key] = definition_label
            if use_source_colors:
                self._set_label_color(definition_label, source_color or getattr(node, "color", None))
            for child in children:
                child_definition = self._step_scene_node_definition(
                    scene,
                    child,
                    use_source_colors=use_source_colors,
                    source_color=source_color,
                )
                child_component = self.shape_tool.AddComponent(
                    definition_label,
                    child_definition,
                    _toploc_from_transform(getattr(child, "local_transform", IDENTITY_TRANSFORM)),
                )
                self._set_label_name(child_component, self._step_scene_node_name(child))
                if use_source_colors:
                    self._set_label_color(child_component, source_color or getattr(child, "color", None))
            return definition_label

        prototype_key = getattr(node, "prototype_key", None)
        if prototype_key is None or prototype_key not in scene.prototype_shapes:
            raise RuntimeError(f"Imported STEP occurrence {occurrence_selector_id(node)} has no prototype shape")
        definition_label = self._step_scene_prototype_definition(
            scene,
            int(prototype_key),
            use_source_colors=use_source_colors,
            source_color=source_color,
        )
        self.step_scene_node_definitions[key] = definition_label
        return definition_label

    def _step_scene_prototype_definition(
        self,
        scene: LoadedStepScene,
        prototype_key: int,
        *,
        use_source_colors: bool,
        source_color: tuple[float, float, float, float] | None,
    ) -> object:
        key = (scene.step_path.resolve(), int(prototype_key), bool(use_source_colors), source_color)
        cached = self.step_scene_prototype_definitions.get(key)
        if cached is not None:
            return cached
        definition_shape = _topods_shape_without_location(scene.prototype_shapes[prototype_key])
        definition_label = self.shape_tool.AddShape(definition_shape, False)
        self.step_scene_prototype_definitions[key] = definition_label
        self._set_label_name(definition_label, scene.prototype_names.get(prototype_key))
        if use_source_colors:
            self._set_label_color(definition_label, source_color or scene.prototype_colors.get(prototype_key))
            if source_color is None:
                self._set_shape_face_colors(
                    definition_label,
                    definition_shape,
                    scene.prototype_face_colors.get(prototype_key, {}),
                )
        return definition_label

    def _step_scene_node_name(self, node: object) -> str:
        return str(
            getattr(node, "name", None)
            or getattr(node, "source_name", None)
            or occurrence_selector_id(node)
        ).strip()

    def _add_nodes_to_assembly(
        self,
        assembly_label: object,
        nodes: Sequence[AssemblyNodeSpec],
        *,
        instance_path: tuple[str, ...],
        parent_use_source_colors: bool,
        stack: tuple[str, ...],
    ) -> None:
        for node in nodes:
            self._add_node_to_assembly(
                assembly_label,
                node,
                instance_path=instance_path,
                parent_use_source_colors=parent_use_source_colors,
                stack=stack,
            )

    def _add_node_to_assembly(
        self,
        assembly_label: object,
        node: AssemblyNodeSpec,
        *,
        instance_path: tuple[str, ...],
        parent_use_source_colors: bool,
        stack: tuple[str, ...],
    ) -> object:
        component_path = (*instance_path, node.instance_id) if instance_path else (node.instance_id,)
        label = _component_name(component_path)
        use_source_colors = parent_use_source_colors and node.use_source_colors

        if node.children:
            definition_label = self._new_assembly_definition(label)
            self._add_nodes_to_assembly(
                definition_label,
                node.children,
                instance_path=component_path,
                parent_use_source_colors=use_source_colors,
                stack=stack,
            )
        else:
            if node.source_path is None or node.path is None:
                raise RuntimeError(f"Assembly node {label} is missing a STEP source path")
            child_entry = self.resolver.entry_for_path(node.source_path)
            if child_entry is None:
                raise RuntimeError(f"Assembly node {label} references missing CAD source {node.path}")
            if child_entry.kind == "assembly":
                definition_label = self._assembly_definition_for_entry(
                    child_entry,
                    instance_path=component_path,
                    parent_use_source_colors=use_source_colors,
                    stack=stack,
                )
            elif child_entry.kind == "part":
                definition_label = self._part_definition_for_entry(
                    child_entry,
                    use_source_colors=use_source_colors,
                )
            else:
                raise RuntimeError(f"Assembly node {label} resolved to unsupported CAD source kind: {child_entry.kind}")

        component_label = self.shape_tool.AddComponent(
            assembly_label,
            definition_label,
            _toploc_from_transform(node.transform),
        )
        self._set_label_name(component_label, label)
        return component_label

    def _assembly_definition_for_entry(
        self,
        entry: CatalogEntry,
        *,
        instance_path: tuple[str, ...],
        parent_use_source_colors: bool,
        stack: tuple[str, ...],
    ) -> object:
        assembly_spec = entry.assembly_spec
        if assembly_spec is None:
            raise RuntimeError(f"Assembly source {entry.source_ref} is missing assembly spec data")
        stack_key = entry.source_ref
        if stack_key in stack:
            cycle = " -> ".join((*stack, stack_key))
            raise RuntimeError(f"Assembly cycle detected: {cycle}")
        definition_label = self._new_assembly_definition(_component_name(instance_path))
        self._add_nodes_to_assembly(
            definition_label,
            assembly_spec_children(assembly_spec),
            instance_path=instance_path,
            parent_use_source_colors=parent_use_source_colors,
            stack=(*stack, stack_key),
        )
        return definition_label

    def _new_assembly_definition(self, name: str | None = None) -> object:
        definition_label = self.shape_tool.NewShape()
        self._set_label_name(definition_label, name)
        return definition_label

    def _shape_definition_for_tree(self, shape: object) -> object:
        key = id(shape)
        cached = self.shape_definitions.get(key)
        if cached is not None:
            return cached
        children = list(getattr(shape, "children", []) or [])
        if children:
            definition_label = self._new_assembly_definition(getattr(shape, "label", None))
            self.shape_definitions[key] = definition_label
            self._set_label_color(definition_label, getattr(shape, "color", None))
            for child in children:
                child_definition = self._shape_definition_for_tree(child)
                child_component = self.shape_tool.AddComponent(
                    definition_label,
                    child_definition,
                    self._shape_location(child),
                )
                self._set_label_name(child_component, getattr(child, "label", None))
                self._set_label_color(child_component, getattr(child, "color", None))
            return definition_label
        definition_label = self.shape_tool.AddShape(_topods_shape_without_location(shape.wrapped), False)
        self.shape_definitions[key] = definition_label
        self._set_label_name(definition_label, getattr(shape, "label", None))
        self._set_label_color(definition_label, getattr(shape, "color", None))
        return definition_label

    def _shape_location(self, shape: object) -> object:
        location = getattr(getattr(shape, "wrapped", None), "Location", None)
        if not callable(location):
            return _toploc_from_transform(IDENTITY_TRANSFORM)
        try:
            return location()
        except Exception:
            return _toploc_from_transform(IDENTITY_TRANSFORM)


def export_direct_assembly_step_scene(
    assembly_spec: AssemblySpec,
    output_path: Path,
    *,
    text_to_cad_entry_kind: str | None = "assembly",
    source_path: str | None = None,
    source_hash: str | None = None,
    resolver: _AssemblyCatalogResolver | None = None,
    logger: object | None = None,
) -> LoadedStepScene:
    output_path = output_path.expanduser().resolve()
    writer = _DirectXcafAssemblyWriter(assembly_spec, label=output_path.stem, resolver=resolver)
    with (logger.timed(f"build assembly XCAF {output_path.name}") if logger is not None else nullcontext()):
        doc = writer.build_doc()
    with (logger.timed(f"export assembly STEP {output_path.name}") if logger is not None else nullcontext()):
        scene = export_xcaf_doc_step_scene(
            doc,
            output_path,
            label=output_path.stem,
            originating_system="tom-cad direct XCAF assembly",
            text_to_cad_entry_kind=text_to_cad_entry_kind,
            source_path=source_path,
            source_hash=source_hash,
            logger=logger,
        )
    return scene


def build_direct_assembly_step_scene(
    assembly_spec: AssemblySpec,
    output_path: Path,
    *,
    source_kind: str = "step",
    source_hash: str | None = None,
    resolver: _AssemblyCatalogResolver | None = None,
    logger: object | None = None,
) -> LoadedStepScene:
    output_path = output_path.expanduser().resolve()
    writer = _DirectXcafAssemblyWriter(assembly_spec, label=output_path.stem, resolver=resolver)
    with (logger.timed(f"build assembly XCAF {output_path.name}") if logger is not None else nullcontext()):
        doc = writer.build_doc()
    with (logger.timed(f"load assembly scene from XCAF {output_path.name}") if logger is not None else nullcontext()):
        return load_step_scene_from_xcaf_doc(
            output_path,
            doc,
            source_kind=source_kind,
            source_hash=source_hash,
        )


def build_assembly_compound(assembly_spec: AssemblySpec, *, label: str | None = None):
    resolver = _AssemblyCatalogResolver()
    root_source = resolver.source_for_path(assembly_spec.assembly_path)
    root_source_ref = root_source.source_ref if root_source is not None else _relative_to_repo(assembly_spec.assembly_path)
    cache = _AssemblyBuildCache(resolver=resolver)
    return _compound_from_nodes(
        assembly_spec_children(assembly_spec),
        label=label or Path(assembly_spec.assembly_path).stem,
        resolve_entry=resolver.entry_for_path,
        parent_use_source_colors=True,
        stack=(root_source_ref,),
        cache=cache,
    )


def export_assembly_step_scene(
    assembly_spec: AssemblySpec,
    output_path: Path,
    *,
    text_to_cad_entry_kind: str | None = "assembly",
    source_path: str | None = None,
    source_hash: str | None = None,
    resolver: _AssemblyCatalogResolver | None = None,
    logger: object | None = None,
) -> LoadedStepScene:
    try:
        scene = export_direct_assembly_step_scene(
            assembly_spec,
            output_path,
            text_to_cad_entry_kind=text_to_cad_entry_kind,
            source_path=source_path,
            source_hash=source_hash,
            resolver=resolver,
            logger=logger,
        )
    except Exception as exc:
        raise RuntimeError(f"Failed to write assembly STEP file: {_relative_to_repo(output_path)}") from exc
    return scene


def export_assembly_step(assembly_spec: AssemblySpec, output_path: Path) -> Path:
    export_assembly_step_scene(assembly_spec, output_path)
    return output_path


def export_assembly_step_from_payload(
    payload: object,
    *,
    assembly_path: Path,
    output_path: Path,
) -> Path:
    return export_assembly_step(
        assembly_spec_from_payload(assembly_path, payload),
        output_path,
    )


def export_assembly_step_scene_from_payload(
    payload: object,
    *,
    assembly_path: Path,
    output_path: Path,
    text_to_cad_entry_kind: str | None = "assembly",
) -> LoadedStepScene:
    return export_assembly_step_scene(
        assembly_spec_from_payload(assembly_path, payload),
        output_path,
        text_to_cad_entry_kind=text_to_cad_entry_kind,
    )
