from __future__ import annotations

import contextlib
import time
from dataclasses import replace
from pathlib import Path
from typing import Iterator

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
)
from cadgen.catalog import build_scope, result_view_dir
from cadgen._internal.step_scene import LoadedStepScene, load_step_scene_cached
from cadgen.step_artifact_cli import infer_entry_kind
from cadgen.step_targets import (
    REGENERATE_STEP_COMMAND,
    REGENERATE_STEP_PROMPT,
    ResolvedStepTarget,
    StepTopologyArtifact,
    StepTopologyArtifactError,
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
        # report to the VIEWER only, so a terminal caller watched a silent
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
    resolved_artifact_path = artifact_path or result_view_dir(spec.entry_path)

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
                spec, require_selector=require_selector, debug=debug
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

    if debug is not None:
        debug["cacheHit"] = False

    try:
        # This rebuild REWRITES the render package, so it reports for the whole span --
        # generator run AND emit -- and a viewer polling during the emit sees a build.
        #
        # Progress keys by the MODEL PATH, never by the content-keyed package dir: a
        # rebuild changes the content key mid-build, so the package dir does not identify
        # the run, and readers (the viewer's progress poller, a peer CLI) derive the record
        # from the model path they hold and could not know the new key in advance.
        with artifact_build(
            STEP_PACKAGE, build_scope(spec.entry_path), sink=sink
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
                f"Failed to compile {spec.cad_ref}: {exc}.\n"
                f"{REGENERATE_STEP_PROMPT}"
            ),
        ) from exc
    # The build just produced the render package (the ONLY artifact form); return its
    # topology the same way the fast path above does — cheap descriptor for renders,
    # on-demand selector extraction otherwise.
    if not is_assembly_package(resolved_artifact_path):
        raise StepTopologyArtifactError(
            code="missing_glb",
            cad_path=spec.cad_ref,
            step_path=spec.step_path,
            artifact_path=resolved_artifact_path,
            regenerate_command=REGENERATE_STEP_COMMAND,
            message=(
                f"Build finished but no tree exists for {spec.cad_ref}.\n"
                f"{REGENERATE_STEP_PROMPT}"
            ),
        )
    return _assembly_topology_artifact(
        spec,
        require_selector=require_selector,
        debug=debug,
        )


def _entry_spec_for_target(
    target: ResolvedStepTarget,
    *,
    mesh_tolerance: float | None,
    mesh_angular_tolerance: float | None,
) -> EntrySpec:
    # DOCUMENTS-ONLY (design/pose-animation-split.md, CLI/doors follow-on): a
    # target is the document. The artifact resolver used to walk back to a
    # `.py` generator and re-run it here, which is how a render could contain a
    # build; a stale document is now refused at the door instead.
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
        mesh_tolerance=mesh_tolerance,
        mesh_angular_tolerance=mesh_angular_tolerance,
    )


def _assembly_topology_artifact(
    spec: EntrySpec,
    *,
    require_selector: bool,
    debug: dict[str, object] | None = None,
) -> StepTopologyArtifact:
    """The topology artifact for a component-GLB package, which carries no embedded
    whole-assembly topology.

    When the caller does not need selectors (a plain render reads the package's render
    meshes directly), return a cheap descriptor-only artifact. When selectors ARE needed
    (inspect, selection-based renders), return a COMPOSED artifact: the component GLBs
    already carry each part's complete topology and the index merge in
    ``assembly_lookup`` places them per occurrence, so no whole-model extraction or
    ``topology.glb`` sidecar is involved at all."""
    from cadgen._internal.component_package import read_package_descriptor

    descriptor = read_package_descriptor(result_view_dir(spec.entry_path))
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
                artifact_path=result_view_dir(spec.entry_path),
                manifest=descriptor,
                selector_bundle=None,
            )

    if descriptor is not None:
        # COMPOSED selector artifact (design/incremental-generation.md,
        # Phase 3): every ``components/<cid>.glb`` already embeds that part's
        # complete topology tables, and both selector consumers (inspect,
        # snapshot) funnel through
        # ``assembly_lookup.index_with_assembly_occurrences``, which merges
        # those tables into the index per occurrence. So the whole-model
        # ``topology.glb`` sidecar is redundant: return the descriptor as the
        # bundle manifest — its selector tables are empty, so the base index
        # is empty — and let composition supply every ref. This removes the
        # sidecar's entire lifecycle (the unconditional delete on package
        # rewrite and the lazy whole-model re-extraction, the ~29.5s class
        # noted above) along with the flat compound namespace (``o1.f19``),
        # which the instance-tree namespace supersedes. ``preloaded_scene``
        # is deliberately unused here: composition reads the component GLBs
        # the build just wrote, so no post-build extraction pass is needed.
        if debug is not None:
            debug["cacheHit"] = True
            debug["selectorReextracted"] = False
            debug["composed"] = True
        from cadgen.selector_types import SelectorBundle

        return StepTopologyArtifact(
            cad_path=spec.cad_ref,
            kind="assembly",
            source_path=spec.source_path,
            step_path=spec.step_path,
            artifact_path=result_view_dir(spec.entry_path),
            manifest=descriptor,
            selector_bundle=SelectorBundle(manifest=descriptor),
        )

    # No descriptor: the package is mid-write (the writer swaps assembly.json
    # atomically under the generation lock) or vanished between the
    # is_assembly_package() check and here. Wait for the writer instead of
    # re-extracting a whole-model selector bundle in memory — deleting that
    # pre-composition path removed the last caller of the OCP selector
    # extractor, leaving exactly two selector implementations (the Python surf
    # reader and its JS twin), fenced by their shared fixtures.
    if debug is not None:
        debug["cacheHit"] = False
        debug["descriptorRetried"] = True
    deadline = time.monotonic() + 5.0
    while descriptor is None and time.monotonic() < deadline:
        time.sleep(0.05)
        descriptor = read_package_descriptor(result_view_dir(spec.entry_path))
    if descriptor is None:
        raise StepTopologyArtifactError(
            code="missing_glb",
            cad_path=spec.cad_ref,
            step_path=spec.step_path,
            artifact_path=result_view_dir(spec.entry_path),
            regenerate_command=REGENERATE_STEP_COMMAND,
            message=(
                f"The tree for {spec.cad_ref} did not appear "
                f"(deleted mid-read?).\n{REGENERATE_STEP_PROMPT}"
            ),
        )
    from cadgen.selector_types import SelectorBundle

    return StepTopologyArtifact(
        cad_path=spec.cad_ref,
        kind="assembly",
        source_path=spec.source_path,
        step_path=spec.step_path,
        artifact_path=result_view_dir(spec.entry_path),
        manifest=descriptor,
        selector_bundle=SelectorBundle(manifest=descriptor) if require_selector else None,
    )


def _scene_for_regeneration(
    spec: EntrySpec,
    *,
    logger: CliLogger | None,
    force: bool,
    progress: object | None = None,
) -> tuple[EntrySpec, LoadedStepScene]:
    if spec.source == "generated":
        # A door never runs the script. The document on disk is what inspect
        # measures: its tree is made current from its BYTES (a compile job in the
        # pool when the store has none), then it is read like any import below.
        from cadgen._internal.doors import document_tree

        if not spec.step_path.is_file():
            raise FileNotFoundError(
                f"no document on disk for {spec.source_ref}: run python {spec.script_path or spec.source_path}"
            )
        document_tree(spec.step_path)

    resolve_progress(progress).phase(PHASE_GENERATE)
    with (logger.timed(f"load STEP {spec.cad_ref}") if logger is not None else _null_context()):
        scene = load_step_scene_cached(spec.step_path)
    inferred_kind = infer_entry_kind(spec.step_path, scene)
    if inferred_kind != spec.kind:
        spec = replace(spec, kind=inferred_kind)
    return spec, scene


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
