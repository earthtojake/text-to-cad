from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from cadpy_common.assembly_spec import REPO_ROOT
from cadpy_common.catalog import iter_cad_sources, source_from_path
from cadpy_common.cli_logging import CliLogger
from cadpy_common.generation import (
    EntrySpec,
    _entry_spec_from_source,
    _existing_topology_artifact_matches_spec_without_scene,
    _generate_part_outputs,
    run_script_generator,
)
from cadpy_common.metadata import DEFAULT_MESH_ANGULAR_TOLERANCE, DEFAULT_MESH_TOLERANCE
from cadpy_common.render import part_glb_path
from cadpy_common.step_metadata import read_text_to_cad_step_metadata
from cadpy_common.step_scene import LoadedStepScene, load_step_scene
from cadpy_common.step_targets import (
    REGENERATE_STEP_COMMAND,
    REGENERATE_STEP_PROMPT,
    ResolvedStepTarget,
    StepTopologyArtifact,
    StepTopologyArtifactError,
    validate_step_topology_artifact,
)


def cad_ref_for_step_path(repo_root: Path, step_path: Path) -> str:
    relative = _repo_relative(repo_root, step_path)
    suffix = step_path.suffix
    return relative[: -len(suffix)] if suffix else relative


def ensure_step_topology_artifact(
    target: ResolvedStepTarget,
    *,
    glb_path: Path | None = None,
    require_selector: bool = False,
    force: bool = False,
    logger: CliLogger | None = None,
    mesh_tolerance: float | None = None,
    mesh_angular_tolerance: float | None = None,
    owner: str = "cadpy-step-artifact",
) -> StepTopologyArtifact:
    spec = _entry_spec_for_target(
        target,
        mesh_tolerance=mesh_tolerance,
        mesh_angular_tolerance=mesh_angular_tolerance,
    )
    resolved_glb_path = glb_path or part_glb_path(spec.step_path)
    if not force:
        artifact = _current_artifact_for_spec(spec, glb_path=resolved_glb_path, require_selector=require_selector)
        if artifact is not None:
            return artifact

    try:
        spec, scene = _scene_for_regeneration(spec, logger=logger, force=force)
        _generate_part_outputs(
            spec,
            entries_by_step_path=_entries_by_step_path_for_repo(REPO_ROOT, spec),
            preloaded_scene=scene,
            require_step_file=(spec.source != "generated"),
            force=True,
            logger=logger,
        )
    except StepTopologyArtifactError:
        raise
    except Exception as exc:
        raise StepTopologyArtifactError(
            code="glb_regeneration_failed",
            cad_path=spec.cad_ref,
            step_path=spec.step_path,
            glb_path=resolved_glb_path,
            regenerate_command=REGENERATE_STEP_COMMAND,
            message=(
                f"Failed to regenerate GLB/topology artifact for {spec.cad_ref}: {exc}.\n"
                f"{REGENERATE_STEP_PROMPT}"
            ),
        ) from exc
    return validate_step_topology_artifact(
        ResolvedStepTarget(
            cad_path=spec.cad_ref,
            kind=spec.kind,
            source_path=spec.source_path,
            step_path=spec.step_path,
        ),
        glb_path=resolved_glb_path,
        require_selector=require_selector,
    )


def _entries_by_step_path_for_repo(repo_root: Path, spec: EntrySpec) -> dict[Path, EntrySpec]:
    entries: dict[Path, EntrySpec] = {}
    try:
        for source in iter_cad_sources(repo_root):
            entry_spec = _entry_spec_from_source(source)
            if entry_spec.step_path is not None:
                entries[entry_spec.step_path.resolve()] = entry_spec
    except Exception:
        entries = {}
    if spec.step_path is not None:
        entries[spec.step_path.resolve()] = spec
    return entries


def _entry_spec_for_target(
    target: ResolvedStepTarget,
    *,
    mesh_tolerance: float | None,
    mesh_angular_tolerance: float | None,
) -> EntrySpec:
    python_source = _python_source_for_target(target)
    if python_source is not None:
        source = source_from_path(python_source)
        if source is None:
            raise RuntimeError(f"Python generator is not a gen_step() CAD source: {python_source}")
        spec = _entry_spec_from_source(source)
        if spec.step_path is not None and spec.step_path.resolve() != target.step_path.resolve():
            spec = replace(
                spec,
                cad_ref=target.cad_path,
                display_name=target.step_path.stem,
                step_path=target.step_path,
            )
        return _with_mesh_overrides(spec, mesh_tolerance=mesh_tolerance, mesh_angular_tolerance=mesh_angular_tolerance)

    if not target.step_path.is_file():
        raise FileNotFoundError(f"STEP file does not exist: {target.step_path}")
    return EntrySpec(
        source_ref=_repo_relative(REPO_ROOT, target.step_path),
        cad_ref=target.cad_path,
        kind=target.kind if target.kind in {"part", "assembly"} else "part",
        source_path=target.step_path,
        display_name=target.step_path.stem,
        source="imported",
        step_path=target.step_path,
        mesh_tolerance=mesh_tolerance if mesh_tolerance is not None else DEFAULT_MESH_TOLERANCE,
        mesh_angular_tolerance=(
            mesh_angular_tolerance
            if mesh_angular_tolerance is not None
            else DEFAULT_MESH_ANGULAR_TOLERANCE
        ),
        mesh_tolerance_explicit=mesh_tolerance is not None,
        mesh_angular_tolerance_explicit=mesh_angular_tolerance is not None,
    )


def _scene_for_regeneration(
    spec: EntrySpec,
    *,
    logger: CliLogger | None,
    force: bool,
) -> tuple[EntrySpec, LoadedStepScene]:
    if spec.source == "generated":
        scene = run_script_generator(
            spec,
            "gen_step",
            logger=logger,
            force=force,
            load_current_scene=False,
            skip_step_write=True,
        )
        if scene is None:
            raise RuntimeError(f"Python generator did not produce a STEP scene: {spec.source_ref}")
        return spec, scene

    with (logger.timed(f"load STEP {spec.cad_ref}") if logger is not None else _null_context()):
        scene = load_step_scene(spec.step_path)
    inferred_kind = _infer_entry_kind(spec.step_path, scene)
    if inferred_kind != spec.kind:
        spec = replace(spec, kind=inferred_kind)
    return spec, scene


def _current_artifact_for_spec(
    spec: EntrySpec,
    *,
    glb_path: Path,
    require_selector: bool,
) -> StepTopologyArtifact | None:
    if not _existing_topology_artifact_matches_spec_without_scene(spec, require_selector=require_selector):
        return None
    try:
        return validate_step_topology_artifact(
            ResolvedStepTarget(
                cad_path=spec.cad_ref,
                kind=spec.kind,
                source_path=spec.source_path,
                step_path=spec.step_path,
            ),
            glb_path=glb_path,
            require_selector=require_selector,
        )
    except StepTopologyArtifactError:
        return None


def _python_source_for_target(target: ResolvedStepTarget) -> Path | None:
    if target.step_path.is_file():
        return None
    if target.source_path.suffix.lower() == ".py" and target.source_path.is_file():
        return target.source_path
    candidate = target.step_path.with_suffix(".py")
    return candidate if candidate.is_file() else None


def _with_mesh_overrides(
    spec: EntrySpec,
    *,
    mesh_tolerance: float | None,
    mesh_angular_tolerance: float | None,
) -> EntrySpec:
    if mesh_tolerance is None and mesh_angular_tolerance is None:
        return spec
    return replace(
        spec,
        mesh_tolerance=mesh_tolerance if mesh_tolerance is not None else spec.mesh_tolerance,
        mesh_angular_tolerance=(
            mesh_angular_tolerance
            if mesh_angular_tolerance is not None
            else spec.mesh_angular_tolerance
        ),
        mesh_tolerance_explicit=mesh_tolerance is not None,
        mesh_angular_tolerance_explicit=mesh_angular_tolerance is not None,
    )


def _scene_has_assembly_structure(scene: LoadedStepScene) -> bool:
    stack = list(scene.roots)
    if len(stack) > 1:
        return True
    while stack:
        node = stack.pop()
        if node.children:
            return True
        stack.extend(node.children)
    return False


def _infer_entry_kind(step_path: Path, scene: LoadedStepScene) -> str:
    metadata_kind = None
    try:
        metadata_kind = read_text_to_cad_step_metadata(step_path).get("entryKind")
    except Exception:
        metadata_kind = None
    if metadata_kind in {"part", "assembly"}:
        return metadata_kind
    return "assembly" if _scene_has_assembly_structure(scene) else "part"


def _repo_relative(repo_root: Path, path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


class _null_context:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_args: object) -> None:
        return None
