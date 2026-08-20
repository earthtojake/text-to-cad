from __future__ import annotations

import contextlib
import time
from dataclasses import replace
from pathlib import Path
from typing import Iterator

from cadgen._internal.atomic_replace import replace_atomic, temp_suffix
from cadgen.catalog import source_from_path
from cadgen.cli_logging import CliLogger
from cadgen.coordination import (
    PHASE_GENERATE,
    STEP_PACKAGE,
    artifact_build,
    resolve as resolve_progress,
)
from cadgen._internal.generation import (
    EntrySpec,
    _entry_spec_from_source,
    _existing_topology_artifact_matches_spec_without_scene,
    _generate_part_outputs,
    cli_progress_line,
    relative_to_cwd,
    run_script_generator,
)
from cadgen.metadata import DEFAULT_MESH_ANGULAR_TOLERANCE, DEFAULT_MESH_TOLERANCE
from cadgen.catalog import render_package_dir
from cadgen._internal.step_scene import LoadedStepScene, load_step_scene_cached
from cadgen.step_artifact_cli import infer_entry_kind
from cadgen.step_targets import (
    REGENERATE_STEP_COMMAND,
    REGENERATE_STEP_PROMPT,
    ResolvedStepTarget,
    StepTopologyArtifact,
    StepTopologyArtifactError,
    validate_step_topology_artifact,
)


def cad_ref_for_step_path(repo_root: Path, step_path: Path) -> str:
    relative = _relative_to_base(repo_root, step_path)
    suffix = step_path.suffix
    return relative[: -len(suffix)] if suffix else relative


def ensure_step_topology_artifact(
    target: ResolvedStepTarget,
    *,
    artifact_path: Path | None = None,
    require_selector: bool = False,
    force: bool = False,
    logger: CliLogger | None = None,
    mesh_tolerance: float | None = None,
    mesh_angular_tolerance: float | None = None,
    debug: dict[str, object] | None = None,
) -> StepTopologyArtifact:
    """Resolve (building/regenerating if needed) the render/topology artifact for `target`.

    `debug`, when passed a dict, is filled in-place with which build strategy this call
    took (generated vs. imported source, assembly vs. part, cache hit vs. regeneration,
    whether assembly selectors were re-extracted, and wall-clock time) so callers can
    surface it as opt-in diagnostics without adding overhead when `debug` is None."""
    started = time.perf_counter() if debug is not None else None
    try:
        # Every CLI that needs a STEP package comes through here -- inspect, snapshot -- and
        # the rebuild below can be the same multi-minute generator `cad gen` runs. It used to
        # take the lock and report to the VIEWER only, so a terminal caller watched a silent
        # process while an open viewer showed the phases. The progress line is built here, at
        # the one shared entry point, rather than asked of every caller.
        with _topology_progress_line(target, logger=logger) as sink:
            return _ensure_step_topology_artifact(
                target,
                artifact_path=artifact_path,
                require_selector=require_selector,
                force=force,
                logger=logger,
                mesh_tolerance=mesh_tolerance,
                mesh_angular_tolerance=mesh_angular_tolerance,
                debug=debug,
                sink=sink,
            )
    finally:
        if debug is not None and started is not None:
            debug["tookMs"] = (time.perf_counter() - started) * 1000


@contextlib.contextmanager
def _topology_progress_line(
    target: ResolvedStepTarget, *, logger: CliLogger | None
) -> "Iterator[object | None]":
    """The shared build progress line for every caller of this entry point.

    Deliberately defaulted rather than required. `inspect` reaches this through four layers
    that carry no logger, and threading one down each of them to earn a progress bar is the
    kind of plumbing that simply does not get done -- which is why inspect's rebuilds were
    silent. Painting is already gated on the stream being a tty, so the callers that must
    stay quiet stay quiet on their own: the viewer's warm worker writes to a pipe, and so
    does anything capturing output.
    """
    with cli_progress_line(
        relative_to_cwd(target.step_path),
        logger=logger or CliLogger("cad"),
        fallback="Building...",
    ) as sink:
        yield sink


def _ensure_step_topology_artifact(
    target: ResolvedStepTarget,
    *,
    artifact_path: Path | None,
    require_selector: bool,
    force: bool,
    logger: CliLogger | None,
    mesh_tolerance: float | None,
    mesh_angular_tolerance: float | None,
    debug: dict[str, object] | None,
    sink: object | None = None,
) -> StepTopologyArtifact:
    spec = _entry_spec_for_target(
        target,
        mesh_tolerance=mesh_tolerance,
        mesh_angular_tolerance=mesh_angular_tolerance,
    )
    if debug is not None:
        debug["source"] = spec.source
    resolved_artifact_path = artifact_path or render_package_dir(spec.entry_path)

    # The canonical render artifact for a generated assembly is a component-GLB package
    # directory, which carries no whole-assembly selector topology (faces/edges). inspect
    # needs that full manifest, so extract it on demand from the scene (the build-time
    # win is precisely that this 29.5s extraction is no longer in the build path).
    from cadgen._internal.component_package import is_assembly_package

    is_assembly = artifact_path is None and is_assembly_package(resolved_artifact_path)
    if debug is not None:
        debug["assembly"] = is_assembly

    if is_assembly:
        try:
            return _assembly_topology_artifact(
                spec, require_selector=require_selector, logger=logger, force=force, debug=debug
            )
        except StepTopologyArtifactError:
            raise
        except Exception as exc:
            raise StepTopologyArtifactError(
                code="glb_regeneration_failed",
                cad_path=spec.cad_ref,
                step_path=spec.step_path,
                artifact_path=resolved_artifact_path,
                regenerate_command=REGENERATE_STEP_COMMAND,
                message=(
                    f"Failed to extract assembly topology for {spec.cad_ref}: {exc}.\n"
                    f"{REGENERATE_STEP_PROMPT}"
                ),
            ) from exc

    if not force:
        artifact = _current_artifact_for_spec(spec, artifact_path=resolved_artifact_path, require_selector=require_selector)
        if artifact is not None:
            if debug is not None:
                debug["cacheHit"] = True
            return artifact

    if debug is not None:
        debug["cacheHit"] = False

    try:
        # This rebuild REWRITES the render package, so it must hold the package's write
        # lock for the whole span -- generator run AND emit. It previously held none: the
        # generator took the lock internally and released it on return, and the package
        # write that followed was completely uncoordinated. A viewer polling during that
        # window read "no build in flight", found the package stale, and started a SECOND
        # full build into the same directory.
        with artifact_build(
            STEP_PACKAGE, render_package_dir(spec.entry_path), sink=sink
        ) as run:
            spec, scene = _scene_for_regeneration(
                spec, logger=logger, force=force, progress=run
            )
            _generate_part_outputs(
                spec,
                entries_by_step_path={spec.step_path: spec},
                preloaded_scene=scene,
                require_step_file=(spec.source != "generated"),
                force=True,
                logger=logger,
                progress=run,
            )
    except StepTopologyArtifactError:
        raise
    except Exception as exc:
        raise StepTopologyArtifactError(
            code="glb_regeneration_failed",
            cad_path=spec.cad_ref,
            step_path=spec.step_path,
            artifact_path=resolved_artifact_path,
            regenerate_command=REGENERATE_STEP_COMMAND,
            message=(
                f"Failed to regenerate GLB/topology artifact for {spec.cad_ref}: {exc}.\n"
                f"{REGENERATE_STEP_PROMPT}"
            ),
        ) from exc
    # The build just produced a component-GLB package directory. Return its topology the
    # same way the fast path above does (cheap descriptor for renders, on-demand selector
    # extraction otherwise) rather than the monolith file-validator, which requires a GLB
    # *file* and would report the package directory as missing.
    if artifact_path is None and is_assembly_package(resolved_artifact_path):
        return _assembly_topology_artifact(
            spec,
            require_selector=require_selector,
            logger=logger,
            force=False,
            preloaded_scene=scene,
            debug=debug,
        )
    return validate_step_topology_artifact(
        ResolvedStepTarget(
            cad_path=spec.cad_ref,
            kind=spec.kind,
            source_path=spec.source_path,
            step_path=spec.step_path,
        ),
        artifact_path=resolved_artifact_path,
        require_selector=require_selector,
    )


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
        return _with_mesh_overrides(spec, mesh_tolerance=mesh_tolerance, mesh_angular_tolerance=mesh_angular_tolerance)

    if not target.step_path.is_file():
        raise FileNotFoundError(f"STEP file does not exist: {target.step_path}")
    return EntrySpec(
        source_ref=_relative_to_base(Path.cwd().resolve(), target.step_path),
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


def _assembly_topology_artifact(
    spec: EntrySpec,
    *,
    require_selector: bool,
    logger: CliLogger | None,
    force: bool,
    preloaded_scene: LoadedStepScene | None = None,
    debug: dict[str, object] | None = None,
) -> StepTopologyArtifact:
    """The topology artifact for a component-GLB package, which carries no embedded
    whole-assembly topology.

    When the caller does not need selectors (a plain render reads the package's render
    meshes directly), return a cheap descriptor-only artifact. When selectors ARE needed
    (inspect, selection-based renders), re-mesh + re-extract the full manifest on demand
    and return the bundle in memory — the build-time win is precisely that this ~29.5s
    extraction is no longer in the build path. Repeat selector queries read the
    ``topology.glb`` sidecar cached inside the package (validated against the
    descriptor's provenance) instead of re-running the generator + extraction."""
    from cadgen._internal.component_package import (
        assembly_topology_glb_path,
        read_package_descriptor,
    )

    descriptor = read_package_descriptor(render_package_dir(spec.entry_path))
    if not require_selector:
        if descriptor is not None:
            if debug is not None:
                debug["cacheHit"] = True
                debug["selectorReextracted"] = False
            return StepTopologyArtifact(
                cad_path=spec.cad_ref,
                kind="assembly",
                source_path=spec.source_path,
                step_path=spec.step_path,
                artifact_path=render_package_dir(spec.entry_path),
                manifest=descriptor,
                selector_bundle=None,
            )

    topology_glb = assembly_topology_glb_path(spec.entry_path)
    if (
        preloaded_scene is None
        and not force
        and descriptor is not None
        and topology_glb.is_file()
    ):
        from cadgen._internal.glb_topology import (
            read_step_topology_bundle_from_glb,
            read_step_topology_manifest_from_glb,
        )

        cached_manifest = read_step_topology_manifest_from_glb(topology_glb)
        if _topology_sidecar_matches_descriptor(cached_manifest, descriptor):
            bundle = read_step_topology_bundle_from_glb(topology_glb)
            if bundle is not None:
                if debug is not None:
                    debug["cacheHit"] = True
                    debug["selectorReextracted"] = False
                return StepTopologyArtifact(
                    cad_path=spec.cad_ref,
                    kind="assembly",
                    source_path=spec.source_path,
                    step_path=spec.step_path,
                    artifact_path=render_package_dir(spec.entry_path),
                    manifest=bundle.manifest,
                    selector_bundle=bundle,
                )

    from cadgen._internal.generation import (
        _effective_step_spec_for_scene,
        _selector_options_for_part,
    )
    from cadgen._internal.step_scene import (
        SelectorProfile,
        extract_selectors_from_scene,
        mesh_step_scene,
    )

    # Reached whenever selectors must be (re)extracted this call: neither the cached
    # descriptor (no-selector path) nor the topology.glb sidecar could serve it.
    if debug is not None:
        debug["cacheHit"] = False
        debug["selectorReextracted"] = True

    if preloaded_scene is not None:
        # The caller just ran gen_step for the package build; extracting
        # selectors from that scene avoids a second full generator run (this
        # halved cold/stale selector-query latency on generated assemblies).
        scene = preloaded_scene
    else:
        spec, scene = _scene_for_regeneration(spec, logger=logger, force=force)
    spec = _effective_step_spec_for_scene(spec, scene)
    options = _selector_options_for_part(spec, scene=scene)
    mesh_step_scene(
        scene,
        linear_deflection=options.linear_deflection,
        angular_deflection=options.angular_deflection,
        relative=options.relative,
    )
    bundle = extract_selectors_from_scene(
        scene,
        cad_ref=spec.cad_ref,
        profile=SelectorProfile.ARTIFACT,
        options=options,
        color=spec.color,
    )
    _write_topology_sidecar(spec, scene, options, bundle, logger=logger)
    return StepTopologyArtifact(
        cad_path=spec.cad_ref,
        kind="assembly",
        source_path=spec.source_path,
        step_path=spec.step_path,
        artifact_path=render_package_dir(spec.entry_path),
        manifest=bundle.manifest,
        selector_bundle=bundle,
    )


def _topology_sidecar_matches_descriptor(
    manifest: object,
    descriptor: dict[str, object],
) -> bool:
    """Whether a cached topology.glb sidecar's embedded provenance matches the
    package descriptor it sits beside. The descriptor is the freshness source of
    truth (its closure gate already ran); the sidecar must carry the SAME source
    closure / step hash and mesh settings or it predates a rebuild."""
    if not isinstance(manifest, dict):
        return False
    # Provenance-only gate: selector topology (occurrence/face/edge refs) is a
    # function of the B-rep sources, not of mesh resolution, so the sidecar is
    # valid whenever it was extracted from the same sources the descriptor
    # records. Comparing mesh settings here would permanently miss after any
    # adaptive-resolution tuning until the package itself rebuilds.
    closure_match = str(descriptor.get("sourceClosureHash") or "").strip() == str(
        manifest.get("sourceClosureHash") or ""
    ).strip()
    step_match = str(descriptor.get("stepHash") or "").strip() == str(
        manifest.get("stepHash") or ""
    ).strip()
    has_any = bool(
        str(descriptor.get("sourceClosureHash") or "").strip()
        or str(descriptor.get("stepHash") or "").strip()
    )
    return has_any and closure_match and step_match


def _write_topology_sidecar(
    spec: EntrySpec,
    scene: LoadedStepScene,
    options: object,
    bundle: object,
    *,
    logger: CliLogger | None,
) -> None:
    """Best-effort write-through of the on-demand selector extraction to the
    package's topology.glb sidecar (atomic rename). A failed cache write must
    never fail the selector query itself."""
    import os

    from cadgen._internal.component_package import assembly_topology_glb_path, is_assembly_package

    package_dir = render_package_dir(spec.entry_path)
    if not is_assembly_package(package_dir):
        return
    target = assembly_topology_glb_path(spec.entry_path)
    temp_path = target.with_name(f"{target.name}{temp_suffix()}")
    try:
        from cadgen._internal.glb import export_assembly_glb_from_scene

        export_assembly_glb_from_scene(
            spec.step_path,
            scene,
            target_path=temp_path,
            linear_deflection=options.linear_deflection,
            angular_deflection=options.angular_deflection,
            selector_bundle=bundle,
        )
        replace_atomic(temp_path, target)
    except Exception as exc:  # noqa: BLE001 - cache write is advisory
        if logger is not None:
            logger.debug(f"topology.glb cache write skipped for {spec.cad_ref}: {exc}")
    finally:
        # The handle that blocks a rename blocks the delete too; letting that escape would
        # replace the real failure with a cleanup error.
        with contextlib.suppress(OSError):
            temp_path.unlink(missing_ok=True)


def _scene_for_regeneration(
    spec: EntrySpec,
    *,
    logger: CliLogger | None,
    force: bool,
    progress: object | None = None,
) -> tuple[EntrySpec, LoadedStepScene]:
    if spec.source == "generated":
        # The run holding the lock, so the generator reports its phase (and whatever the
        # generator itself reports through cadgen.progress). Without it this call -- which
        # for a large assembly is the longest thing inspect does -- opened the build with no
        # `generate` phase at all: the bar jumped straight to `collecting parts`.
        scene = run_script_generator(
            spec,
            "gen_step",
            logger=logger,
            force=force,
            progress=progress,
        )
        if scene is None:
            raise RuntimeError(f"Python generator did not produce a STEP scene: {spec.source_ref}")
        return spec, scene

    resolve_progress(progress).phase(PHASE_GENERATE)
    with (logger.timed(f"load STEP {spec.cad_ref}") if logger is not None else _null_context()):
        scene = load_step_scene_cached(spec.step_path)
    inferred_kind = infer_entry_kind(spec.step_path, scene)
    if inferred_kind != spec.kind:
        spec = replace(spec, kind=inferred_kind)
    return spec, scene


def _current_artifact_for_spec(
    spec: EntrySpec,
    *,
    artifact_path: Path,
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
            artifact_path=artifact_path,
            require_selector=require_selector,
        )
    except StepTopologyArtifactError:
        return None


def _python_source_for_target(target: ResolvedStepTarget) -> Path | None:
    source_is_generator = (
        target.source_path.suffix.lower() == ".py" and target.source_path.is_file()
    )
    # An explicitly-targeted `.py` generator keeps resolving to the generator
    # entry even when its same-stem exported `.step` exists beside it — the
    # `.step.py` and `.step` files are distinct entry-keyed models, and only an
    # explicit `.step`/`.stp` target means "treat as imported STEP".
    if target.explicit_python and source_is_generator:
        return target.source_path
    if target.step_path.is_file():
        return None
    if source_is_generator:
        return target.source_path
    # The generator for `<name>.step` is `<name>.step.py` (append `.py` to the
    # full filename) under the entry convention.
    candidate = target.step_path.with_name(target.step_path.name + ".py")
    if candidate.is_file():
        return candidate
    return None


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


def _relative_to_base(repo_root: Path, path: Path) -> str:
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
