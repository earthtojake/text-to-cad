from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterator, Sequence, TextIO

from cadgen.catalog import (
    CadSource,
    StepImportOptions,
    cad_ref_from_dxf_path,
    cad_ref_from_step_path,
    render_package_dir,
    find_source_by_path,
    iter_cad_sources,
    normalize_cad_ref,
    normalize_source_ref,
    source_from_path,
)
from cadgen.cli_logging import CliLogger
from cadgen._internal.cli_locking import contended_payload, deadline_ms, lock_wait_notice
from cadgen._internal.file_metadata import text_to_cad_identity_metadata, write_dxf_text_to_cad_metadata
from cadgen._internal.package_freshness import (
    STEP_PACKAGE_VERSION,
    bake_hash_matches,
    schema_version_matches,
)
from cadgen._internal.glb import build_step_topology_index_manifest
from cadgen._internal.glb import read_step_topology_manifest_from_glb
from cadgen._internal.glb_topology import (
    STEP_EDGE_VISIBILITY_CLASSES,
    normalize_step_edge_render_visibility_classes,
)
from cadgen.coordination import (
    DRAWING_PACKAGE,
    PHASE_GENERATE,
    STEP_PACKAGE,
    ProgressEvent,
    artifact_build,
    generator_busy,
    render_progress_bar,
    reporting_as,
    resolve as resolve_progress,
)
from cadgen.cli_progress import (
    InlineProgressLine,
    _finished_phase_text,
    _progress_status_text,
    cli_progress_line,
)
from cadgen.coordination.lock import exclusive
from cadgen.coordination.paths import write_lock_path
from cadgen.metadata import (
    DEFAULT_MESH_ANGULAR_TOLERANCE,
    DEFAULT_MESH_TOLERANCE,
    GeneratorMetadata,
    resolve_mesh_settings,
)
from cadgen.render import (
    relative_to_file,
    relative_to_cwd,
)
from cadgen._internal.source_hash import (
    PythonSourceClosure,
    PythonSourceHash,
    capture_runtime_closure,
    closure_hash_matches,
    evict_first_party_modules,
    python_source_hash,
    record_first_party_execution,
)
from cadgen.step_export import build_build123d_step_scene
from cadgen._internal.step_scene import (
    load_step_scene_cached,
    LoadedStepScene,
    SelectorBundle,
    SelectorOptions,
    adaptive_mesh_resolution_from_hints,
    adaptive_mesh_resolution_for_scene,
    step_file_hash,
)
from cadgen._internal.generation_runner import (
    GIT_LFS_POINTER_PREFIX,
    _ArtifactJob,
    _effective_step_spec_for_scene,
    _ensure_step_ready,
    _generator_progress_line,
    _is_git_lfs_pointer,
    _load_generator_module,
    _mark_scene_python_backed,
    _mark_scene_step_payload,
    _normalize_dxf_payload,
    _normalize_step_payload,
    _resolve_params_sidecar,
    _run_artifact_jobs,
    _run_script_generator_inner,
    _scene_entry_kind,
    _shape_has_explicit_children,
    _shape_is_multi_child_compound,
    _shape_payload_entry_kind,
    _spec_output_dir,
    _track_spec_generation,
    _write_dxf_payload,
    _write_lock_without_reporting,
    _write_shape_step_payload,
    run_script_generator,
)
from cadgen._internal.generation_spec import (
    EntrySpec,
    GeneratedStepResult,
    _CliTargetSpec,
    _TOLERANCE_WARN_RATIO,
    _apply_dxf_output_override,
    _apply_dxf_output_overrides,
    _apply_step_options_to_spec,
    _apply_step_output_overrides,
    _cli_progress_line,
    _display_name_for_path,
    _display_path,
    _edge_visibility_classes_for_resolution,
    _entry_spec_from_source,
    _hint_float,
    _hint_int,
    _mesh_angular_tolerance_is_explicit,
    _mesh_tolerance_is_explicit,
    _parse_cli_target_specs,
    _resolve_cli_output_path,
    _resolve_discovery_root,
    _selector_options_for_part,
    _spec_for_source_ref,
    _spec_output_paths,
    _spec_requests_extra_outputs,
    _validate_cli_output_override,
    _validate_duplicate_cli_output_overrides,
    _warn_if_tolerance_defeats_scale_floor,
    list_entry_specs,
    selected_entry_specs,
    targets_include_output_pairs,
)

def _mesh_values_match(
    mesh: Mapping[str, object],
    *,
    linear_deflection: float,
    angular_deflection: float,
    relative: bool,
) -> bool:
    try:
        artifact_linear = float(mesh.get("linearDeflection"))
        artifact_angular = float(mesh.get("angularDeflection"))
    except (TypeError, ValueError):
        return False
    return (
        math.isclose(artifact_linear, float(linear_deflection), rel_tol=1e-9, abs_tol=1e-12)
        and math.isclose(artifact_angular, float(angular_deflection), rel_tol=1e-9, abs_tol=1e-12)
        and bool(mesh.get("relative", True)) == bool(relative)
    )


def _selector_options_from_topology_manifest(spec: EntrySpec, manifest: Mapping[str, object]) -> SelectorOptions | None:
    mesh = manifest.get("mesh")
    if not isinstance(mesh, Mapping):
        return None

    defaults = SelectorOptions()
    linear_explicit = _mesh_tolerance_is_explicit(spec)
    angular_explicit = _mesh_angular_tolerance_is_explicit(spec)
    linear_deflection = spec.mesh_tolerance
    angular_deflection = spec.mesh_angular_tolerance

    if not linear_explicit or not angular_explicit:
        resolution = mesh.get("resolution")
        hints = resolution.get("hints") if isinstance(resolution, Mapping) else None
        if not isinstance(hints, dict):
            return None
        adaptive = adaptive_mesh_resolution_from_hints(hints)
        if not linear_explicit:
            linear_deflection = adaptive.settings.tolerance
        if not angular_explicit:
            angular_deflection = adaptive.settings.angular_tolerance

    return SelectorOptions(
        linear_deflection=linear_deflection,
        angular_deflection=angular_deflection,
        relative=bool(mesh.get("relative", defaults.relative)),
        edge_deflection=defaults.edge_deflection,
        edge_deflection_ratio=defaults.edge_deflection_ratio,
        max_edge_points=defaults.max_edge_points,
        digits=defaults.digits,
        mesh_resolution=mesh.get("resolution") if isinstance(mesh.get("resolution"), dict) else None,
        edge_visibility_classes=_edge_visibility_classes_from_topology_manifest(manifest),
    )


def _edge_visibility_classes_from_topology_manifest(manifest: Mapping[str, object]) -> tuple[str, ...]:
    edge_rendering = manifest.get("edgeRendering")
    if isinstance(edge_rendering, Mapping):
        classes = edge_rendering.get("visibilityClasses")
        if classes is not None:
            return normalize_step_edge_render_visibility_classes(classes)
    mesh = manifest.get("mesh")
    resolution = mesh.get("resolution") if isinstance(mesh, Mapping) else None
    hints = resolution.get("hints") if isinstance(resolution, Mapping) else None
    profile = resolution.get("profile") if isinstance(resolution, Mapping) else ""
    if isinstance(hints, Mapping):
        return _edge_visibility_classes_for_resolution(str(profile or ""), hints)
    return normalize_step_edge_render_visibility_classes(None)


def _edge_visibility_classes_match_manifest(
    manifest: Mapping[str, object],
    selector_options: SelectorOptions,
) -> bool:
    edge_rendering = manifest.get("edgeRendering")
    if not isinstance(edge_rendering, Mapping):
        return False
    return tuple(edge_rendering.get("visibilityClasses") or ()) == tuple(selector_options.edge_visibility_classes)


def _artifact_source_kind_matches_spec(spec: EntrySpec, manifest: Mapping[str, object]) -> bool:
    source_kind = str(manifest.get("sourceKind") or "step").strip().lower()
    if spec.source != "generated" and spec.step_path is not None and spec.step_path.is_file():
        if source_kind == "python":
            return bool(str(manifest.get("stepHash") or "").strip())
        return source_kind == "step"
    expected = "python" if spec.source == "generated" and spec.script_path is not None else "step"
    return source_kind == expected


def _artifact_step_hash_matches_spec(spec: EntrySpec, manifest: Mapping[str, object]) -> bool:
    if spec.step_path is None or not spec.step_path.is_file():
        return True
    expected_hash = step_file_hash(spec.step_path)
    return str(manifest.get("stepHash") or "").strip() == expected_hash


def _package_descriptor_matches_spec(
    spec: EntrySpec,
    selector_options: SelectorOptions | None = None,
) -> bool | None:
    """Descriptor-based freshness for a component-GLB package directory.

    Returns None when the entry's artifact is not a package (caller falls back
    to the monolith-GLB validator). Packages carry no embedded selector/edge
    views (selector topology is extracted on demand), so routing them through
    the monolith validator always failed and every build re-ran gen_step plus
    the full-scene mesh; validate against the package descriptor instead.

    The schema-version and bake gates below mirror the viewer's validator
    (``viewer/server_py/artifact.py``) exactly. A check on only one side is worse than
    no check at all: the viewer would report stale, this predicate would report current,
    the build would no-op, and the request would settle ``ready`` on the stale package.
    The imported-STEP digest gate is already fail-closed here
    (``_artifact_step_hash_matches_spec``: a descriptor recording no ``stepHash`` cannot
    equal the file's real hash), which is the behaviour the viewer now matches.
    """
    from cadgen._internal.component_package import is_assembly_package, read_package_descriptor

    package_dir = render_package_dir(spec.entry_path)
    if not is_assembly_package(package_dir):
        return None
    manifest = read_package_descriptor(package_dir)
    if not isinstance(manifest, dict):
        return False
    if not schema_version_matches(manifest, STEP_PACKAGE_VERSION):
        return False
    # The assembly package bakes no format settings into its payload (components are pure
    # geometry at recorded mesh tolerances, and those are compared below), so the expected
    # bake is None -- and a descriptor that records one did not come from this producer.
    if not bake_hash_matches(manifest, None):
        return False
    if not _artifact_source_kind_matches_spec(spec, manifest):
        return False
    if not _artifact_step_hash_matches_spec(spec, manifest):
        return False
    mesh = manifest.get("mesh")
    if not isinstance(mesh, Mapping):
        return False
    if selector_options is None:
        selector_options = _selector_options_from_topology_manifest(spec, manifest)
    if selector_options is None:
        return False
    return (
        _mesh_values_match(
            mesh,
            linear_deflection=selector_options.linear_deflection,
            angular_deflection=selector_options.angular_deflection,
            relative=selector_options.relative,
        )
        and _edge_visibility_classes_match_manifest(manifest, selector_options)
    )


def _existing_topology_artifact_matches_spec_without_scene(
    spec: EntrySpec,
    *,
    require_selector: bool = True,
) -> bool:
    if spec.step_path is None or spec.kind not in {"part", "assembly"}:
        return False
    package_match = _package_descriptor_matches_spec(spec)
    if package_match is not None:
        return package_match
    from cadgen.step_targets import (
        ResolvedStepTarget,
        StepTopologyArtifactError,
        validate_step_topology_artifact,
    )

    try:
        artifact = validate_step_topology_artifact(
            ResolvedStepTarget(
                cad_path=spec.cad_ref,
                kind=spec.kind,
                source_path=spec.source_path,
                step_path=spec.step_path,
            ),
            artifact_path=render_package_dir(spec.entry_path),
            require_selector=require_selector,
        )
    except StepTopologyArtifactError:
        return False
    if not _artifact_source_kind_matches_spec(spec, artifact.manifest):
        return False
    if not _artifact_step_hash_matches_spec(spec, artifact.manifest):
        return False
    mesh = artifact.manifest.get("mesh")
    if not isinstance(mesh, Mapping):
        return False
    selector_options = _selector_options_from_topology_manifest(spec, artifact.manifest)
    if selector_options is None:
        return False
    return (
        _mesh_values_match(
            mesh,
            linear_deflection=selector_options.linear_deflection,
            angular_deflection=selector_options.angular_deflection,
            relative=selector_options.relative,
        )
        and _edge_visibility_classes_match_manifest(artifact.manifest, selector_options)
    )


def _existing_topology_artifact_matches_options(spec: EntrySpec, selector_options: SelectorOptions) -> bool:
    if spec.step_path is None or spec.kind not in {"part", "assembly"}:
        return False
    package_match = _package_descriptor_matches_spec(spec, selector_options)
    if package_match is not None:
        return package_match
    from cadgen.step_targets import (
        ResolvedStepTarget,
        StepTopologyArtifactError,
        validate_step_topology_artifact,
    )

    try:
        artifact = validate_step_topology_artifact(
            ResolvedStepTarget(
                cad_path=spec.cad_ref,
                kind=spec.kind,
                source_path=spec.source_path,
                step_path=spec.step_path,
            ),
            artifact_path=render_package_dir(spec.entry_path),
            require_selector=False,
        )
    except StepTopologyArtifactError:
        return False
    if not _artifact_source_kind_matches_spec(spec, artifact.manifest):
        return False
    if not _artifact_step_hash_matches_spec(spec, artifact.manifest):
        return False
    mesh = artifact.manifest.get("mesh")
    if not isinstance(mesh, Mapping):
        return False
    return (
        _mesh_values_match(
            mesh,
            linear_deflection=selector_options.linear_deflection,
            angular_deflection=selector_options.angular_deflection,
            relative=selector_options.relative,
        )
        and _edge_visibility_classes_match_manifest(artifact.manifest, selector_options)
    )


def _assembly_provenance_manifest(
    scene: LoadedStepScene,
    *,
    selector_options: SelectorOptions,
    step_path: Path,
    entry_kind: str,
) -> dict[str, object]:
    """The index-manifest provenance an assembly package descriptor carries, mirroring
    the monolithic GLB's embedded STEP_topology index — but WITHOUT the expensive
    selector extraction. Sourced from the scene (sourceKind/closure), the mesh options,
    and the STEP hash, so the build freshness gates can read it from assembly.json
    exactly as they read the monolithic manifest.
    """
    import os
    from datetime import datetime, timezone

    from cadgen._internal.glb_topology import step_topology_capabilities

    source_kind = str(getattr(scene, "source_kind", "step") or "step").strip().lower()
    if source_kind not in {"step", "python"}:
        source_kind = "step"
    mesh: dict[str, object] = {
        "linearDeflection": float(selector_options.linear_deflection),
        "angularDeflection": float(selector_options.angular_deflection),
        "relative": bool(selector_options.relative),
    }
    if isinstance(getattr(selector_options, "mesh_resolution", None), dict):
        mesh["resolution"] = selector_options.mesh_resolution
    minimal: dict[str, object] = {
        "sourceKind": source_kind,
        "capabilities": step_topology_capabilities(selector_options.edge_visibility_classes),
        "edgeRendering": {"visibilityClasses": list(selector_options.edge_visibility_classes)},
        "mesh": mesh,
        "stepPath": os.path.relpath(step_path, step_path.parent),
    }
    source_path = str(getattr(scene, "source_path", "") or "")
    if source_path:
        minimal["sourcePath"] = source_path
    params_path = str(getattr(scene, "params_path", "") or "")
    if params_path:
        minimal["paramsPath"] = params_path
    if source_kind == "python":
        source_hash = str(getattr(scene, "source_hash", "") or "").strip()
        if source_hash:
            minimal["sourceHash"] = source_hash
        closure_hash = str(getattr(scene, "source_closure_hash", "") or "").strip()
        closure_files = getattr(scene, "source_closure_files", ()) or ()
        if closure_hash and closure_files:
            minimal["sourceClosureHash"] = closure_hash
            minimal["sourceClosureFiles"] = list(closure_files)
        minimal["generatedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    step_hash = (
        step_file_hash(step_path)
        if step_path.is_file()
        else str(getattr(scene, "step_hash", "") or "").strip()
    )
    if step_hash:
        minimal["stepHash"] = step_hash
    return build_step_topology_index_manifest(minimal, entry_kind=entry_kind)


def _generate_part_outputs(
    spec: EntrySpec,
    *,
    entries_by_step_path: dict[Path, EntrySpec],
    preloaded_scene: LoadedStepScene | None = None,
    require_step_file: bool = True,
    force: bool = False,
    logger: CliLogger | None = None,
    progress: object | None = None,
) -> GeneratedStepResult:
    logger = logger or CliLogger("cad")
    progress = resolve_progress(progress)
    if spec.kind not in {"part", "assembly"} or spec.step_path is None:
        return GeneratedStepResult(spec=spec, scene=None)
    if require_step_file:
        _ensure_step_ready(spec.step_path)
    if preloaded_scene is not None:
        if preloaded_scene.step_path != spec.step_path.expanduser().resolve():
            raise RuntimeError(
                f"Preloaded STEP scene path {preloaded_scene.step_path} does not match {_display_path(spec.step_path)}"
            )

    # Any on-demand output (mesh sidecar or --step export) must be produced even when the
    # render package is current, so its presence defeats the reuse fast paths.
    has_extra_outputs = _spec_requests_extra_outputs(spec)
    package_current = (
        spec.source != "generated"
        or _assembly_glb_package_current(spec)
    )
    if (
        preloaded_scene is None
        and not has_extra_outputs
        and not force
        and package_current
        and _existing_topology_artifact_matches_spec_without_scene(spec)
    ):
        logger.debug(f"reused current GLB/topology: {_display_path(render_package_dir(spec.entry_path))}")
        return GeneratedStepResult(spec=spec, scene=None)

    if preloaded_scene is not None:
        scene = preloaded_scene
    else:
        # An imported STEP's parse is this path's equivalent of running a generator:
        # opaque, and often seconds for a large vendor file.
        progress.phase(PHASE_GENERATE)
        with logger.timed(f"load STEP {spec.cad_ref}"):
            # Cross-run binary BREP scene cache: warm rebuilds of imported
            # STEP entries skip the text-STEP parse (seconds to ~10s+ for
            # large vendor files) and deserialize cached geometry instead.
            scene = load_step_scene_cached(spec.step_path)
        if spec.source == "generated" and spec.script_path is not None:
            _mark_scene_python_backed(
                scene,
                source_identity=python_source_hash(spec.script_path),
                source_path=spec.script_path,
            )
    spec = _effective_step_spec_for_scene(spec, scene)
    entries_by_step_path = {
        **entries_by_step_path,
        spec.step_path.resolve(): spec,
    }
    selector_options = _selector_options_for_part(spec, scene=scene)
    if (
        not has_extra_outputs
        and not force
        and package_current
        and _existing_topology_artifact_matches_options(spec, selector_options)
        and _generated_assembly_glb_closure_current(spec)
    ):
        logger.debug(f"reused current GLB/topology: {_display_path(render_package_dir(spec.entry_path))}")
        return GeneratedStepResult(spec=spec, scene=scene)

    jobs: list[_ArtifactJob] = []

    artifact_results: dict[str, object] = {}

    if spec.step_export_path is not None:
        def step_export_job() -> Path:
            # On-demand text STEP (--step). gen_step never writes a STEP, so serialize the
            # in-memory compound the generator produced; for an imported source the .step
            # already exists, so copy it to the requested path.
            from cadgen.step_export import export_build123d_step_file

            target = spec.step_export_path
            target.parent.mkdir(parents=True, exist_ok=True)
            source_compound = getattr(scene, "source_compound", None)
            if source_compound is not None:
                export_build123d_step_file(
                    source_compound,
                    target,
                    text_to_cad_entry_kind=spec.kind,
                    source_path=(str(getattr(scene, "source_path", "") or "") or None),
                    source_hash=(str(getattr(scene, "source_hash", "") or "") or None),
                )
            elif spec.step_path is not None and spec.step_path.is_file() and spec.step_path.resolve() != target.resolve():
                shutil.copyfile(spec.step_path, target)
            return target

        jobs.append(_ArtifactJob("STEP", step_export_job))

    # UNIFIED render artifact: every model — part or assembly, generated or imported — is
    # a component-GLB PACKAGE (a directory at __cadgen__/models/<entry>: assembly.json
    # descriptor + content-addressed components). An assembly introspects its
    # placed children as occurrences; a part is one occurrence/one component. The
    # part/assembly choice is the *authored* kind (spec.kind, from generator metadata or STEP
    # inference) — never guessed from geometry — and is recorded as entryKind on the
    # descriptor. There is no monolithic GLB and no file-vs-dir split.
    source_compound = getattr(scene, "source_compound", None)
    single_component = spec.kind != "assembly"
    package_provenance = _assembly_provenance_manifest(
        scene, selector_options=selector_options, step_path=spec.step_path, entry_kind=spec.kind
    )

    def component_package_job() -> dict[str, object]:
        # Lazy import: component_package imports from this module, so a top-level
        # import would cycle.
        from cadgen._internal.component_package import build_package_from_compound
        from cadgen._internal.legacy_artifacts import prune_legacy_artifacts

        shape = source_compound
        if shape is None:
            # Imported STEP (no generator compound): package its geometry directly. An
            # imported assembly re-imports to a compound of placed solids; a part is one.
            from build123d import import_step

            shape = import_step(spec.step_path)
        # An in-place 0.3.x -> 0.4.x upgrade leaves that release's artifacts beside the
        # source, where nothing reads them any more. Pruned here rather than on a
        # separate migration pass because this is already the once-per-entry moment
        # under the generation lock, and the schema bump that invalidates 0.3.x-era
        # packages routes every model through it on first open.
        pruned = prune_legacy_artifacts(spec.entry_path)
        if pruned["removed"]:
            reclaimed_mb = pruned["bytes"] / (1024 * 1024)
            print(
                f"Removed {len(pruned['removed'])} legacy 0.3.x artifact(s) "
                f"beside {spec.entry_path.name} ({reclaimed_mb:.1f} MB)"
            )
        for skipped in pruned["skipped"]:
            print(f"Left {skipped.name} in place: unrecognized contents for a 0.3.x artifact")
        return build_package_from_compound(
            shape,
            package_dir=render_package_dir(spec.entry_path),
            # The descriptor's rootName is a plain model name, not a repo path (which would leak
            # the arbitrary `models/` root into a bundle meant to be hosted/relocated anywhere).
            root_name=spec.step_path.stem,
            single_component=single_component,
            force=force,
            provenance=package_provenance,
            linear_deflection=selector_options.linear_deflection,
            angular_deflection=selector_options.angular_deflection,
            progress=progress,
        )

    jobs.append(_ArtifactJob("GLB package", component_package_job))

    artifact_results.update(_run_artifact_jobs(jobs, logger=logger))
    # The render artifact is the component-GLB package; whole-model selector topology is
    # extracted on demand by ensure_step_topology_artifact (inspect/selection renders), so
    # generation no longer returns a selector bundle.
    return GeneratedStepResult(spec=spec, scene=scene, selector_bundle=None)


def _generate_step_outputs(
    spec: EntrySpec,
    *,
    entries_by_step_path: dict[Path, EntrySpec],
    force: bool = False,
    logger: CliLogger | None = None,
    progress: object | None = None,
) -> GeneratedStepResult:
    preloaded_scene: LoadedStepScene | None = None
    # An on-demand output (mesh sidecar or --step export) must run even when the package is
    # current, so its presence defeats the reuse fast path.
    has_extra_outputs = _spec_requests_extra_outputs(spec)
    # Reuse fast path: skip the build when the component-GLB package is already present and
    # current and nothing forces a run. A generated model's freshness rides on its recorded
    # source closure; an imported/committed STEP's freshness rides on the STEP hash recorded in
    # the package (verified inside the artifact-matches gate), so it needs no closure check.
    if (
        not force
        and not has_extra_outputs
        and _assembly_glb_package_current(spec)
        and _existing_topology_artifact_matches_spec_without_scene(spec)
        and (spec.source != "generated" or _generated_assembly_glb_closure_current(spec))
    ):
        if logger is not None:
            logger.debug(f"reused current GLB/topology: {_display_path(render_package_dir(spec.entry_path))}")
        return GeneratedStepResult(spec=spec, scene=None)
    output_kwargs: dict[str, object] = {
        "entries_by_step_path": entries_by_step_path,
        "force": force,
        "progress": progress,
    }
    if logger is not None:
        output_kwargs["logger"] = logger
    if spec.source == "generated":
        preloaded_scene = run_script_generator(
            spec,
            "gen_step",
            logger=logger,
            force=force,
            progress=progress,
        )
        spec = _effective_step_spec_for_scene(spec, preloaded_scene)
        if spec.step_path is not None:
            output_kwargs["entries_by_step_path"] = {
                **entries_by_step_path,
                spec.step_path.resolve(): spec,
            }
        output_kwargs["preloaded_scene"] = preloaded_scene
        # gen_step never writes a STEP, so the artifact pipeline must not require one.
        output_kwargs["require_step_file"] = False
    else:
        # Imported/committed STEP target (kind supplied by the caller or inferred upstream):
        # _generate_part_outputs loads + meshes the on-disk STEP and emits the same flat
        # component-GLB package. Without this branch the function fell off the end and silently
        # returned None — no package written — while the CLI still reported success.
        output_kwargs["require_step_file"] = True
    return _generate_part_outputs(spec, **output_kwargs)


def _generate_step_outputs_for_cli(
    spec: EntrySpec,
    *,
    entries_by_step_path: dict[Path, EntrySpec],
    logger: CliLogger,
    force: bool = False,
    progress: object | None = None,
) -> GeneratedStepResult:
    kwargs: dict[str, object] = {
        "entries_by_step_path": entries_by_step_path,
        "progress": progress,
    }
    if force:
        kwargs["force"] = True
    if logger.verbose:
        kwargs["logger"] = logger
    return _generate_step_outputs(spec, **kwargs)


def _selected_specs_for_targets(
    targets: Sequence[str],
    *,
    step_options: StepImportOptions | None = None,
    expected_output_suffixes: tuple[str, ...] | None = None,
    tool_name: str = "CAD",
    include_output_paths: bool = False,
) -> tuple[list[EntrySpec], list[EntrySpec]] | tuple[list[EntrySpec], list[EntrySpec], list[Path | None]]:
    step_options = step_options or StepImportOptions()
    target_specs = (
        _parse_cli_target_specs(
            targets,
            expected_suffixes=expected_output_suffixes,
            tool_name=tool_name,
        )
        if expected_output_suffixes is not None
        else [_CliTargetSpec(target=str(target or "").strip()) for target in targets]
    )
    explicit_specs: list[EntrySpec] = []
    output_paths: list[Path | None] = []
    unresolved_targets: list[str] = []
    for target_spec in target_specs:
        target_text = target_spec.target
        target_path = Path(target_text)
        resolved = target_path.resolve() if target_path.is_absolute() else (Path.cwd() / target_path).resolve()
        source = (
            source_from_path(resolved, step_options=step_options)
            if resolved.exists()
            else None
        )
        if source is None:
            unresolved_targets.append(target_text)
            continue
        explicit_specs.append(_apply_step_options_to_spec(_entry_spec_from_source(source), step_options))
        output_paths.append(target_spec.output_path)

    if not unresolved_targets:
        expanded_specs = _expand_specs_with_file_dependencies(explicit_specs)
        if include_output_paths:
            return expanded_specs, explicit_specs, output_paths
        return expanded_specs, explicit_specs

    unresolved = ", ".join(unresolved_targets)
    raise FileNotFoundError(
        "CAD target path not found or not a supported source file: "
        f"{unresolved}. Pass a Python generator or STEP/STP file path."
    )


def _expand_specs_with_file_dependencies(specs: Sequence[EntrySpec]) -> list[EntrySpec]:
    # Shape-only generators don't expose a static recipe to walk for dependency
    # expansion. The Python source-closure capture in run_script_generator picks
    # up generator-side .py changes; child STEP changes require --force.
    return list(specs)


def _entries_by_step_path(specs: Sequence[EntrySpec]) -> dict[Path, EntrySpec]:
    return {
        spec.step_path.resolve(): spec
        for spec in specs
        if spec.step_path is not None
    }


def _validate_step_target(spec: EntrySpec, *, tool_name: str) -> None:
    if spec.step_path is None:
        raise ValueError(f"{tool_name} target has no STEP path: {spec.source_ref}")
    if spec.source == "generated":
        metadata = spec.generator_metadata
        if metadata is None or not metadata.has_gen_step:
            raise ValueError(f"{tool_name} target does not define gen_step(): {spec.source_ref}")
        return
    raise ValueError(
        f"{tool_name} builds gen_step() Python sources only: {spec.source_ref}. "
        "Imported STEP/STP files get render artifacts on demand (inspect, snapshot, CAD Viewer)."
    )


def _validate_dxf_target(spec: EntrySpec) -> None:
    metadata = spec.generator_metadata
    if spec.source != "generated" or spec.script_path is None or metadata is None:
        raise ValueError(f"dxf expected a generated Python source target: {spec.source_ref}")
    if not metadata.has_gen_dxf:
        raise ValueError(f"dxf target does not define gen_dxf(): {spec.source_ref}")
    if spec.dxf_path is None:
        raise ValueError(f"dxf target has no configured DXF output: {spec.source_ref}")


def _generated_output_summary(spec: EntrySpec) -> str:
    if spec.step_path is not None:
        return f"generated {spec.kind} STEP: {_display_path(spec.step_path)}"
    return f"processed: {spec.source_ref}"


def _generated_python_glb_summary(spec: EntrySpec) -> str:
    if spec.step_path is not None:
        return f"generated {spec.kind} GLB/topology artifact: {_display_path(render_package_dir(spec.entry_path))}"
    return f"processed: {spec.source_ref}"


def _generated_dxf_summary(spec: EntrySpec) -> str:
    if spec.dxf_export_path is not None:
        return f"generated DXF: {_display_path(spec.dxf_export_path)}"
    if spec.script_path is not None:
        return (
            "generated DXF drawing package: "
            f"{_display_path(render_package_dir(spec.script_path))}"
        )
    return f"processed: {spec.source_ref}"


class _SkippedGeneration:
    """Marker: the lock holder ahead of us had already produced a current package."""

    __slots__ = ("spec",)

    def __init__(self, spec: EntrySpec) -> None:
        self.spec = spec


class _ContendedGeneration:
    """Marker: a peer holds the lock and this run declined to wait for it.

    Deliberately NOT :class:`_SkippedGeneration`. That one means the package IS current --
    the peer finished and this run re-checked under the lock. This one means the build is
    still in flight somewhere else, so nothing can be claimed about the package yet."""

    __slots__ = ("spec",)

    def __init__(self, spec: EntrySpec) -> None:
        self.spec = spec


def _run_with_spec_generation_status(
    spec: EntrySpec,
    generator_name: str,
    action: Callable[..., object],
    *,
    skip_if_current: Callable[[EntrySpec], bool] | None = None,
    progress_sink: object | None = None,
    logger: CliLogger | None = None,
    lock_timeout_s: float = 0.0,
) -> object:
    """Run ``action`` while holding the model's build lock, reporting its progress.

    Delegates to :func:`cadgen.coordination.artifact_build`, which is the SAME primitive
    ``cadgen.step_artifact_cli`` uses. That shared implementation is the point: the lock, the
    status record and the post-lock currency re-check used to be assembled by hand at each
    producer, and the two producers had drifted -- this one re-checked under the lock,
    step_artifact_cli's did not, so a queued viewer build redid a peer's whole generator+mesh.

    ``skip_if_current`` is re-evaluated AFTER the lock is acquired. The pre-lock fast path
    cannot cover the concurrent case: it ran before the other build existed.

    ``action`` is called as ``action(spec, run)``; ``run`` is the progress reporter.

    ``lock_timeout_s`` bounds the wait for a peer's lock, exactly as it does in
    ``cadgen.step_artifact_cli``: 0 waits, and a positive value gives up and reports the peer
    instead. Same flag, same default, same meaning -- see :mod:`cadgen._internal.cli_locking`.
    """
    kind = DRAWING_PACKAGE if generator_name == "gen_dxf" else STEP_PACKAGE
    # No output dir means no lock, so there is nothing to wait on and no ref to name in a
    # notice -- and a spec that never reaches a lock is not required to have one.
    output_dir = _spec_output_dir(spec, generator_name)
    with artifact_build(
        kind,
        output_dir,
        is_current=(lambda: bool(skip_if_current(spec))) if skip_if_current is not None else None,
        deadline_ms=deadline_ms(lock_timeout_s),
        sink=progress_sink,
        on_wait=lock_wait_notice(logger, spec.source_ref) if output_dir is not None else None,
    ) as run:
        if run.contended:
            return _ContendedGeneration(spec)
        if run.skipped:
            return _SkippedGeneration(spec)
        return action(spec, run)


def _run_selected_specs(
    selected_specs: Sequence[EntrySpec],
    *,
    action_status: str = "Generating...",
    done_status: str = "Generated",
    action: Callable[..., object],
    logger: CliLogger,
    success_message: Callable[[EntrySpec], str] | None = _generated_output_summary,
) -> list[object]:
    """Run ``action`` for each spec, narrating to ``logger`` and painting one progress line.

    A generator's own prints go straight through to stdout: the CLIs reserve stdout for the
    result (``--json``) and put every log line on stderr, so there is nothing to protect it
    from. Progress is a transient tty line that erases itself — see
    :func:`_cli_progress_line`, which stays silent under ``--verbose`` where the logger is
    already narrating every stage. The sidecar is written either way, so an open CAD Viewer
    tracks the build regardless of what this prints.
    """
    results: list[object] = []
    for spec in selected_specs:
        logger.debug(f"{action_status} {spec.source_ref}")
        with _cli_progress_line(spec, logger=logger, fallback=action_status) as progress_sink:
            with logger.timed(f"{done_status.lower()} {spec.source_ref}"):
                result = action(spec, progress_sink)
        results.append(result)
        if isinstance(result, _ContendedGeneration):
            logger.info(f"another run is building {spec.cad_ref}; not waiting")
        elif isinstance(result, _SkippedGeneration):
            logger.info(f"{spec.cad_ref} was built by a concurrent run; skipped")
        elif success_message is not None:
            message_spec = result.spec if isinstance(result, GeneratedStepResult) else spec
            logger.info(success_message(message_spec))
    return results


def _manifest_source_closure_unchanged(manifest: Mapping[str, object], base: Path) -> bool:
    """Whether a topology manifest's recorded source closure re-hashes unchanged.

    The closure is the generator's Python import reach, so a changed generator or
    shared helper invalidates it — and so does a composed child when it is composed
    the documented way, by importing its ``.step.py``. A child read as a raw ``.step``
    file is data, not a closure input; ``_rebuild_stale_assembly_children`` keeps
    generated children current instead. ``base`` is the model folder the recorded
    closure paths are relative to. Returns False when no usable closure was recorded."""
    recorded_hash = str(manifest.get("sourceClosureHash") or "").strip()
    recorded_files = manifest.get("sourceClosureFiles")
    if not recorded_hash or not isinstance(recorded_files, list) or not recorded_files:
        return False
    return closure_hash_matches(recorded_hash, recorded_files, base=base)


def _assembly_is_current(spec: EntrySpec) -> bool:
    """Whether a generated model's render package is already up to date, so
    regeneration (gen_step + mesh + emit) can be skipped entirely.

    gen_step no longer writes a STEP, so freshness rides on the package
    descriptor's recorded source closure (the generator's Python import reach)
    re-hashing unchanged — not an on-disk STEP hash. Parts and assemblies are
    both packages and share this gate.
    """
    if spec.source != "generated" or spec.step_path is None:
        return False
    return _generated_assembly_glb_closure_current(spec)


def _generated_assembly_glb_closure_current(spec: EntrySpec) -> bool:
    """Whether a generated model's existing render package still matches its
    source closure (the generator's Python import reach). Imported models have no
    closure and are unaffected (return True; their stepHash gate handles freshness).

    Reads the closure from the package descriptor (assembly.json), which the
    dir-aware manifest reader returns. A changed generator or shared helper
    invalidates the closure; see :func:`_manifest_source_closure_unchanged` for how
    composed children are covered."""
    if spec.source != "generated":
        return True
    if spec.step_path is None:
        return False
    artifact_path = render_package_dir(spec.entry_path)
    if not artifact_path.exists():
        return False
    manifest = read_step_topology_manifest_from_glb(artifact_path)
    if not isinstance(manifest, dict):
        return False
    return _manifest_source_closure_unchanged(manifest, spec.step_path.parent)


def _assembly_glb_package_current(spec: EntrySpec) -> bool:
    """Whether the sibling component-GLB package exists with every referenced
    component present. Paired with the closure gate (which detects source
    changes), so this only guards the package's own existence — a missing/partial
    package forces the emit job to run. Every generated model is a package."""
    if spec.step_path is None:
        return False
    from cadgen._internal.component_package import assembly_package_current

    # The render package is keyed by the ENTRY filename (`<name>.step.py` for a
    # generated model), not the logical step path — keying by step_path checked
    # a directory that never exists and forced a rebuild on every run.
    return assembly_package_current(spec.entry_path)


def _generated_child_is_stale(child_spec: EntrySpec, *, force: bool) -> bool:
    """Whether a generated child part must be rebuilt before composing a parent.

    Detection order:
    1. force, or a missing/unhydrated STEP -> stale.
    2. Recorded import closure (sound, incl. transitive sys.path-loaded deps):
       re-hash the recorded closure files and compare. This is the precise path.
    3. Fallback when no closure was recorded (artifacts predating this feature,
       or minimal fixtures): compare the script's own-file source hash to the
       sourceHash recorded with the STEP. Catches own-file edits; transitive-dep
       detection resumes once the child is regenerated with a closure.
    4. If nothing was recorded, do not rebuild blindly (avoid mass rebuilds and
       false positives on artifacts that carry no provenance).
    """
    if child_spec.source != "generated" or child_spec.script_path is None or child_spec.step_path is None:
        return False
    if force:
        return True
    # gen_step writes no STEP — the render GLB/package is the artifact, so freshness keys
    # on it. A missing/unhydrated artifact (file GLB or package directory) is stale.
    artifact_path = render_package_dir(child_spec.entry_path)
    if not artifact_path.exists() or _is_git_lfs_pointer(artifact_path):
        return True
    manifest = read_step_topology_manifest_from_glb(artifact_path)
    if isinstance(manifest, dict):
        recorded_hash = str(manifest.get("sourceClosureHash") or "").strip()
        recorded_files = manifest.get("sourceClosureFiles")
        if recorded_hash and isinstance(recorded_files, list) and recorded_files:
            return not closure_hash_matches(
                recorded_hash, recorded_files, base=child_spec.step_path.parent
            )
        recorded_source_hash = str(manifest.get("sourceHash") or "").strip()
        if recorded_source_hash:
            return python_source_hash(child_spec.script_path).source_hash != recorded_source_hash
    return False


def _rebuild_child_in_subprocess(child_spec: EntrySpec) -> None:
    """Rebuild one stale child in a clean subprocess.

    A fresh interpreter is required so the child's runtime import closure is
    captured accurately: the current process has already imported the part
    modules (the parent generator imports them), which would make an in-process
    sys.modules delta miss shared dependencies."""
    bootstrap = (
        "import sys\n"
        "from cadgen._internal.generation import generate_step_targets\n"
        "sys.exit(generate_step_targets([sys.argv[1]], force=True))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", bootstrap, str(child_spec.script_path)],
        cwd=str(Path.cwd()),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(
            f"Failed to rebuild stale subcomponent {child_spec.source_ref}:\n{detail}"
        )


def _timed_rebuild(child: EntrySpec, *, logger: CliLogger | None) -> None:
    if logger is not None:
        with logger.timed(f"rebuild stale subcomponent {child.source_ref}"):
            _rebuild_child_in_subprocess(child)
    else:
        _rebuild_child_in_subprocess(child)


def _rebuild_children_parallel(
    children: Sequence[EntrySpec],
    *,
    logger: CliLogger | None,
) -> list[str]:
    """Rebuild independent leaf children concurrently in bounded subprocesses.

    Each rebuilds in its own clean interpreter (sound closure capture), so they
    share no in-process state and parallelize freely. Their build123d imports
    overlap, which is what removes the sequential per-child import overhead.
    Errors are collected so one failure doesn't mask the others. Returns the
    source refs in the input order (deterministic), regardless of finish order."""
    if len(children) <= 1:
        for child in children:
            _timed_rebuild(child, logger=logger)
        return [child.source_ref for child in children]

    max_workers = min(len(children), max(1, (os.cpu_count() or 2) - 1))
    if logger is not None:
        logger.debug(f"rebuilding {len(children)} stale subcomponents (up to {max_workers} parallel)")

    def run_one(child: EntrySpec) -> tuple[str, float, Exception | None]:
        started = time.perf_counter()
        try:
            _rebuild_child_in_subprocess(child)
            return child.source_ref, time.perf_counter() - started, None
        except Exception as exc:  # aggregated and re-raised below
            return child.source_ref, time.perf_counter() - started, exc

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(run_one, children))

    rebuilt: list[str] = []
    errors: list[tuple[str, Exception]] = []
    for source_ref, elapsed, exc in results:
        if exc is not None:
            errors.append((source_ref, exc))
            continue
        rebuilt.append(source_ref)
        if logger is not None:
            logger.debug(f"rebuilt subcomponent {source_ref} in {elapsed:.2f}s")
    if errors:
        joined = "\n".join(f"  {source_ref}: {exc}" for source_ref, exc in errors)
        raise RuntimeError(f"Failed to rebuild {len(errors)} stale subcomponent(s):\n{joined}")
    return rebuilt


def _rebuild_stale_assembly_children(
    all_specs: Sequence[EntrySpec],
    selected_specs: Sequence[EntrySpec],
    *,
    force: bool,
    logger: CliLogger | None,
) -> list[str]:
    """Rebuild generated child parts of selected assemblies whose source changed.

    Reuses the already-expanded ``all_specs`` (no extra source discovery).
    Independent leaf parts rebuild concurrently; sub-assembly children rebuild
    sequentially afterward in leaf-first (deepest-first) order, since each
    composes from its own children and its subprocess force-rebuilds that
    subtree. Returns the source refs that were rebuilt."""
    has_assembly_target = any(
        spec.kind == "assembly" and spec.source == "generated" for spec in selected_specs
    )
    if not has_assembly_target:
        return []
    selected_refs = {spec.source_ref for spec in selected_specs}
    seen: set[str] = set()
    stale_leaves: list[EntrySpec] = []
    stale_assemblies: list[EntrySpec] = []
    # all_specs lists parents before dependencies; reversing yields leaf-first.
    for child in reversed(list(all_specs)):
        if child.source_ref in selected_refs or child.source_ref in seen:
            continue
        seen.add(child.source_ref)
        if not _generated_child_is_stale(child, force=force):
            continue
        if child.kind == "assembly":
            stale_assemblies.append(child)
        else:
            stale_leaves.append(child)
    if not stale_leaves and not stale_assemblies:
        return []

    rebuilt = _rebuild_children_parallel(stale_leaves, logger=logger)
    for child in stale_assemblies:
        _timed_rebuild(child, logger=logger)
        rebuilt.append(child.source_ref)

    if rebuilt and logger is not None:
        logger.info(f"rebuilt {len(rebuilt)} stale subcomponent(s): {', '.join(rebuilt)}")
    return rebuilt


def generate_step_targets(
    targets: Sequence[str],
    *,
    step_options: StepImportOptions | None = None,
    force: bool = False,
    verbose: bool = False,
    json_output: bool = False,
    lock_timeout_s: float = 0.0,
) -> int:
    """Build render packages for ``targets``. Returns the process exit code.

    ``json_output`` additionally prints one JSON line per target to STDOUT. The exit code
    alone cannot say WHICH targets were rebuilt and which were already current, and the
    logger's prose goes to stderr by design -- so without this a caller reading the streams
    apart had no machine-readable result at all.

    ``lock_timeout_s`` bounds the wait for a concurrent build of the same model. 0 waits,
    which is what an agent that asked for a build wants; a positive value reports the peer
    as ``contended`` and moves on.
    """
    tool_name = "scripts/gen"
    logger = CliLogger("scripts/gen", verbose=verbose)
    reported: list[dict[str, object]] = []

    def _emit(spec: EntrySpec, outcome: str) -> None:
        reported.append(
            {
                "ok": True,
                "sourceRef": spec.source_ref,
                "cadPath": spec.cad_ref,
                "kind": spec.kind,
                "outcome": outcome,
                "packagePath": _display_path(render_package_dir(spec.entry_path)),
            }
        )

    def _emit_contended(spec: EntrySpec) -> None:
        # The SAME payload the artifact CLIs answer with when a peer holds the lock, so a
        # caller branching on `contended` does not have to learn a second spelling of it per
        # CLI. `outcome` rides alongside, because --json promises one line per target and a
        # reader should not have to special-case which key names the result.
        reported.append(
            {
                **contended_payload(
                    source_ref=spec.source_ref,
                    cad_ref=spec.cad_ref,
                    package_dir=render_package_dir(spec.entry_path),
                ),
                "kind": spec.kind,
                "outcome": "contended",
            }
        )

    def _flush() -> None:
        # STDOUT IS THE RESULT, on every CLI. `gen` used to print nothing there at all --
        # its only output was the logger's prose on stderr -- so a caller reading the two
        # streams apart got an exit code and nothing else, while export, snapshot, validate
        # and inspect all answered on stdout. One line per target, `outcome path`, upgraded
        # to JSON by --json.
        for entry in reported:
            if json_output:
                print(json.dumps(entry, separators=(",", ":")))
            else:
                print(f"{entry['outcome']} {entry['packagePath']}")
    all_specs, selected_specs, target_output_paths = _selected_specs_for_targets(
        targets,
        step_options=step_options,
        expected_output_suffixes=(".step",),
        tool_name=tool_name,
        include_output_paths=True,
    )
    for spec in selected_specs:
        _validate_step_target(spec, tool_name=tool_name)
    selected_specs = _apply_step_output_overrides(
        selected_specs,
        output_paths=target_output_paths,
        all_specs=all_specs,
        tool_name=tool_name,
    )
    if step_options is not None and step_options.has_metadata:
        selected_specs = [_apply_step_options_to_spec(spec, step_options) for spec in selected_specs]
    _rebuild_stale_assembly_children(all_specs, selected_specs, force=force, logger=logger)
    # No-op fast path: skip recomposing a generated assembly whose source closure
    # (the generator's Python import reach) is unchanged. Runs after the
    # child rebuild so a just-rebuilt child correctly invalidates the closure. Only
    # for plain in-place regeneration (no --force or output overrides).
    no_output_override = not any(path is not None for path in target_output_paths)
    if not force and no_output_override:
        current_specs = [
            spec
            for spec in selected_specs
            # An explicit STEP export (--write-step) must be written even when the
            # compose is current, so it keeps the spec in the run.
            if not _spec_requests_extra_outputs(spec)
            and _assembly_is_current(spec)
            and _assembly_glb_package_current(spec)
        ]
        if current_specs:
            for spec in current_specs:
                logger.info(f"{spec.cad_ref} is current; skipped recompose")
                _emit(spec, "current")
            current_refs = {spec.source_ref for spec in current_specs}
            selected_specs = [spec for spec in selected_specs if spec.source_ref not in current_refs]
            if not selected_specs:
                logger.total()
                _flush()
                return 0
    entries_by_step_path = _entries_by_step_path([*all_specs, *selected_specs])

    # Same condition as the pre-lock fast path above, re-checked once the lock is held
    # so a run that queued behind a concurrent build of this model no-ops instead of
    # rebuilding it. --force and explicit extra outputs always do the work.
    def _built_by_a_peer(spec: EntrySpec) -> bool:
        if force or not no_output_override or _spec_requests_extra_outputs(spec):
            return False
        return _assembly_is_current(spec) and _assembly_glb_package_current(spec)

    def generate_step(spec: EntrySpec, progress_sink: object | None = None) -> object:
        # The lock and the progress record are now one thing, keyed by the same package
        # dir, so a CAD Viewer polling this model's artifact status picks up exactly the
        # run that is holding the lock -- and cannot pick up a previous run's leftovers.
        def build(tracked_spec: EntrySpec, reporter: object) -> object:
            return _generate_step_outputs_for_cli(
                tracked_spec,
                entries_by_step_path=entries_by_step_path,
                logger=logger,
                force=force,
                progress=reporter,
            )

        return _run_with_spec_generation_status(
            spec,
            "gen_step",
            build,
            skip_if_current=_built_by_a_peer,
            progress_sink=progress_sink,
            logger=logger,
            lock_timeout_s=lock_timeout_s,
        )

    results = _run_selected_specs(
        selected_specs,
        action=generate_step,
        logger=logger,
        success_message=_generated_python_glb_summary,
    )
    for spec, result in zip(selected_specs, results):
        if isinstance(result, _ContendedGeneration):
            _emit_contended(spec)
            continue
        _emit(spec, "skipped-peer" if isinstance(result, _SkippedGeneration) else "built")
    logger.total()
    _flush()
    return 0


def generate_dxf_targets(
    targets: Sequence[str],
    *,
    output: str | Path | None = None,
    write_dxf: bool = False,
    force: bool = False,
    verbose: bool = False,
) -> int:
    from cadgen._internal.drawing_package import drawing_package_current

    tool_name = "dxf"
    logger = CliLogger("scripts/gen", verbose=verbose)
    if output is not None and targets_include_output_pairs(targets):
        raise ValueError(f"{tool_name} --output cannot be combined with SOURCE=OUTPUT targets")
    output_path = _resolve_cli_output_path(output, expected_suffixes=(".dxf",), tool_name=tool_name)
    all_specs, selected_specs, target_output_paths = _selected_specs_for_targets(
        targets,
        expected_output_suffixes=(".dxf",),
        tool_name=tool_name,
        include_output_paths=True,
    )
    for spec in selected_specs:
        _validate_dxf_target(spec)
    selected_specs = _apply_dxf_output_override(
        selected_specs,
        output_path=output_path,
        all_specs=all_specs,
        tool_name=tool_name,
    )
    selected_specs = _apply_dxf_output_overrides(
        selected_specs,
        output_paths=target_output_paths,
        all_specs=all_specs,
        tool_name=tool_name,
    )
    if write_dxf:
        # The sibling `<name>.dxf` is written on demand only (mirror of `--step`); the
        # default build product is the drawing package under __cadgen__/models/.
        selected_specs = [
            spec if spec.dxf_export_path is not None else replace(spec, dxf_export_path=spec.dxf_path)
            for spec in selected_specs
        ]
    # No-op fast path: skip regenerating a drawing whose source closure is unchanged.
    # An export request on a current package is satisfied from the cache (copy +
    # identity re-point) instead of re-running the generator.
    if not force:
        current_specs = [
            spec
            for spec in selected_specs
            if spec.script_path is not None and drawing_package_current(spec.script_path)
        ]
        if current_specs:
            from cadgen._internal.drawing_package import export_drawing_dxf

            for spec in current_specs:
                if spec.dxf_export_path is not None:
                    export_drawing_dxf(spec.script_path, spec.dxf_export_path)
                    logger.info(
                        f"{spec.cad_ref} is current; exported cached DXF: "
                        f"{_display_path(spec.dxf_export_path)}"
                    )
                else:
                    logger.info(f"{spec.cad_ref} is current; skipped regeneration")
            current_refs = {spec.source_ref for spec in current_specs}
            selected_specs = [spec for spec in selected_specs if spec.source_ref not in current_refs]
    if selected_specs:
        # Re-checked under the lock, like the STEP path: a run that queued behind a
        # concurrent build of this drawing must not regenerate it. An export request
        # still has to write its file, so it never skips.
        def _built_by_a_peer(spec: EntrySpec) -> bool:
            if force or spec.dxf_export_path is not None or spec.script_path is None:
                return False
            return drawing_package_current(spec.script_path)

        _run_selected_specs(
            selected_specs,
            # A drawing build DOES have countable stages -- DRAWING_PACKAGE declares
            # parse/mesh/write, reported by the Node child while this process holds the
            # lock -- so the sink is threaded through rather than dropped. It was dropped
            # on the belief that a drawing is "one opaque generator run", which was true
            # only of the Python half.
            action=lambda spec, progress_sink=None: _run_with_spec_generation_status(
                spec,
                "gen_dxf",
                lambda tracked_spec, reporter: run_script_generator(
                    tracked_spec, "gen_dxf", logger=logger, progress=reporter
                ),
                skip_if_current=_built_by_a_peer,
                progress_sink=progress_sink,
                logger=logger,
            ),
            logger=logger,
            success_message=_generated_dxf_summary,
        )
    logger.total()
    return 0


def run_tool_cli(
    argv: Sequence[str] | None,
    *,
    prog: str,
    description: str,
    action: Callable[..., int],
    target_help: str | None = None,
    output_help: str | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog=prog, description=description)
    parser.add_argument(
        "targets",
        nargs="+",
        help=target_help or "Explicit Python generator or STEP/STP file path to generate.",
    )
    if output_help is not None:
        parser.add_argument("-o", "--output", metavar="PATH", help=output_help)
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed progress and timing information.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    if output_help is not None:
        if args.output is not None:
            if targets_include_output_pairs(args.targets):
                parser.error("--output cannot be combined with SOURCE=OUTPUT targets")
            if len(args.targets) != 1:
                parser.error("--output can only be used with exactly one target")
        return action(args.targets, output=args.output, verbose=bool(args.verbose))
    return action(args.targets, verbose=bool(args.verbose))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CAD generation support library.")
    parser.parse_args(list(argv) if argv is not None else None)
    parser.error("cadgen.generation is a library module.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
