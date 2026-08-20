from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path

from cadgen.cli_logging import CliLogger
from cadgen._internal.cli_locking import (
    add_lock_timeout_argument,
    contended_payload,
    deadline_ms,
    lock_wait_notice,
)
from cadgen._internal.generation import (
    EntrySpec,
    cli_progress_line,
    _assembly_glb_package_current,
    _existing_topology_artifact_matches_spec_without_scene,
    _entry_spec_from_source,
    _generate_part_outputs,
    _generated_assembly_glb_closure_current,
    run_script_generator,
)
from cadgen.coordination import PHASE_GENERATE, STEP_PACKAGE, artifact_build
from cadgen.metadata import DEFAULT_MESH_ANGULAR_TOLERANCE, DEFAULT_MESH_TOLERANCE, normalize_mesh_numeric
from cadgen.catalog import render_package_dir
from cadgen.render import relative_to_cwd
from cadgen._internal.step_metadata import read_text_to_cad_step_metadata
from cadgen._internal.step_scene import LoadedStepScene, load_step_scene, step_file_hash
from cadgen.catalog import iter_cad_sources, source_from_path
from cadgen.step_targets import (
    ResolvedStepTarget,
    StepTopologyArtifact,
    StepTopologyArtifactError,
    validate_step_topology_artifact,
)


def _relative_to_base(repo_root: Path, path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(repo_root).as_posix()
    except ValueError:
        return resolved.as_posix()


def _cad_ref_for_step(repo_root: Path, step_path: Path) -> str:
    relative = _relative_to_base(repo_root, step_path)
    suffix = step_path.suffix
    return relative[: -len(suffix)] if suffix else relative


def _scene_has_assembly_structure(scene: LoadedStepScene) -> bool:
    """True if the scene's product hierarchy has child relationships.

    Multiple roots OR any root with children indicates assembly structure.
    The check is deliberately shallow: any descendant implies a child of the
    root, so a root with children already makes the model an assembly.
    """
    if len(scene.roots) > 1:
        return True
    return any(node.children for node in scene.roots)


def infer_entry_kind(step_path: Path, scene: LoadedStepScene) -> str:
    """Classify a STEP model as ``part`` or ``assembly`` without a caller-supplied kind.

    Embedded text-to-cad ``entryKind`` metadata wins when present (generated STEP);
    otherwise a STEP whose product hierarchy has child nodes reads as an assembly.
    """
    metadata_kind = None
    try:
        metadata_kind = read_text_to_cad_step_metadata(step_path).get("entryKind")
    except Exception:  # noqa: BLE001 - a STEP whose embedded metadata cannot be read has no entryKind to honor
        metadata_kind = None
    if metadata_kind in {"part", "assembly"}:
        return metadata_kind
    return "assembly" if _scene_has_assembly_structure(scene) else "part"


def _build_entry_spec(
    repo_root: Path,
    step_path: Path,
    scene: LoadedStepScene,
    *,
    kind: str,
    mesh_tolerance: float | None = None,
    mesh_angular_tolerance: float | None = None,
) -> EntrySpec:
    cad_ref = _cad_ref_for_step(repo_root, step_path)
    return EntrySpec(
        source_ref=_relative_to_base(repo_root, step_path),
        cad_ref=cad_ref,
        kind=kind,
        source_path=step_path,
        display_name=step_path.stem,
        source="imported",
        step_path=step_path,
        mesh_tolerance=mesh_tolerance if mesh_tolerance is not None else DEFAULT_MESH_TOLERANCE,
        mesh_angular_tolerance=(
            mesh_angular_tolerance
            if mesh_angular_tolerance is not None
            else DEFAULT_MESH_ANGULAR_TOLERANCE
        ),
        mesh_tolerance_explicit=mesh_tolerance is not None,
        mesh_angular_tolerance_explicit=mesh_angular_tolerance is not None,
    )


def _entries_by_step_path_for_repo(repo_root: Path, spec: EntrySpec) -> dict[Path, EntrySpec]:
    entries: dict[Path, EntrySpec] = {}
    try:
        for source in iter_cad_sources(repo_root):
            entry_spec = _entry_spec_from_source(source)
            if entry_spec.step_path is not None:
                entries[entry_spec.step_path.resolve()] = entry_spec
    except Exception:  # noqa: BLE001 - a repo scan failure degrades to only the requested spec
        entries = {}
    if spec.step_path is not None:
        entries[spec.step_path.resolve()] = spec
    return entries


def _result_payload(
    spec: EntrySpec,
    *,
    entry_kind: str,
    source_kind: str,
    artifact_path: Path,
    step_hash: str | None = None,
    source_hash: str | None = None,
    stats: dict[str, object] | None = None,
    load_elapsed_ms: float | None = None,
    skipped: bool = False,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "ok": True,
        "stepPath": relative_to_cwd(spec.step_path),
        "packagePath": relative_to_cwd(artifact_path),
        "entryKind": entry_kind,
        "sourceKind": source_kind,
        "stats": stats or {},
        "sourceRef": spec.source_ref,
        "cadPath": spec.cad_ref,
    }
    if step_hash:
        payload["stepHash"] = step_hash
    if source_hash:
        payload["sourceHash"] = source_hash
    if load_elapsed_ms is not None:
        payload["loadElapsedMs"] = round(load_elapsed_ms, 1)
    if skipped:
        payload["skipped"] = True
    return payload


def _generated_result_payload(spec: EntrySpec, scene: LoadedStepScene, stats: dict[str, object] | None = None) -> dict[str, object]:
    artifact_path = render_package_dir(spec.entry_path)
    source_kind = str(getattr(scene, "source_kind", "step") or "step").strip().lower()
    step_hash = str(getattr(scene, "step_hash", "") or "").strip()
    if not step_hash and spec.step_path is not None and spec.step_path.is_file():
        step_hash = step_file_hash(spec.step_path)
    return _result_payload(
        spec,
        entry_kind=spec.kind,
        source_kind=source_kind,
        step_hash=step_hash or None,
        source_hash=getattr(scene, "source_hash", None) if source_kind == "python" else None,
        artifact_path=artifact_path,
        stats=stats,
        load_elapsed_ms=scene.load_elapsed * 1000.0,
    )


def _existing_result_payload(spec: EntrySpec, artifact: StepTopologyArtifact) -> dict[str, object]:
    entry_kind = str(artifact.manifest.get("entryKind") or spec.kind)
    source_kind = str(artifact.manifest.get("sourceKind") or "step").strip().lower()
    step_hash = str(artifact.manifest.get("stepHash") or "")
    source_hash = str(artifact.manifest.get("sourceHash") or "")
    if source_kind != "python" and not step_hash:
        step_hash = step_file_hash(spec.step_path)
    stats = artifact.manifest.get("stats")
    return _result_payload(
        spec,
        entry_kind=entry_kind,
        source_kind=source_kind,
        step_hash=step_hash or None,
        source_hash=source_hash or None,
        artifact_path=artifact.artifact_path,
        stats=stats if isinstance(stats, dict) else {},
        skipped=True,
    )


def _current_artifact_for_spec(spec: EntrySpec) -> StepTopologyArtifact | None:
    if not _existing_topology_artifact_matches_spec_without_scene(spec):
        return None
    package_dir = render_package_dir(spec.entry_path)
    # A component-GLB package is a DIRECTORY, and validate_step_topology_artifact() gates on
    # `.is_file()` (step_targets.py) -- so routing a package through it always raised
    # missing_glb, this whole fast path returned None, and EVERY build re-ran gen_step().
    # The descriptor comparison above (_package_descriptor_matches_spec) IS the package's
    # freshness gate; there is nothing further to validate. Packages carry no whole-assembly
    # selector topology either -- it is extracted on demand -- so require_selector cannot be
    # satisfied from the package and must not be asked of it.
    from cadgen._internal.component_package import is_assembly_package, read_package_descriptor

    if is_assembly_package(package_dir):
        # _package_descriptor_matches_spec (above) compares kind/stepHash/mesh options but
        # NOT the generator's source closure, so it alone would serve a stale package after
        # an edited generator. These are the same two predicates the CLI's currency gate
        # uses (generation.py's "is current; skipped recompose" path), so the two entry
        # points cannot disagree about what "current" means:
        #   closure  -- generated models re-hash the recorded import reach; imported ones
        #               return True and rely on the stepHash gate above.
        #   package  -- the descriptor's referenced components are all present on disk.
        if not (
            _generated_assembly_glb_closure_current(spec) and _assembly_glb_package_current(spec)
        ):
            return None
        manifest = read_package_descriptor(package_dir)
        if not isinstance(manifest, dict):
            return None
        return StepTopologyArtifact(
            cad_path=spec.cad_ref,
            kind=spec.kind,
            source_path=spec.source_path,
            step_path=spec.step_path,
            artifact_path=package_dir,
            manifest=manifest,
        )
    try:
        return validate_step_topology_artifact(
            ResolvedStepTarget(
                cad_path=spec.cad_ref,
                kind=spec.kind,
                source_path=spec.source_path,
                step_path=spec.step_path,
            ),
            artifact_path=package_dir,
            require_selector=True,
        )
    except StepTopologyArtifactError:
        return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m cadgen.step_artifact_cli",
        description="Build the CAD Viewer render package for one STEP/STP file or gen_step() generator.",
    )
    parser.add_argument("--repo-root", required=True, help="Repository/workspace root for relative STEP metadata.")
    parser.add_argument("--step", required=True, help="STEP/STP source file to process.")
    parser.add_argument(
        "--source-path",
        help=(
            "Python gen_step() source for a generated model. Selects generator mode: the build "
            "runs the generator in-process and writes only the render package; the logical "
            "--step path need not exist on disk. Without it, --step must be an existing "
            "STEP/STP file (imported model)."
        ),
    )
    parser.add_argument("--kind", choices=("part", "assembly"), help="Override inferred STEP entry kind.")
    parser.add_argument("--force", action="store_true", help="Regenerate even if a current artifact exists.")
    parser.add_argument("--mesh-tolerance", type=float, help="Override automatic mesh linear deflection.")
    parser.add_argument("--mesh-angular-tolerance", type=float, help="Override automatic mesh angular deflection.")
    parser.add_argument("--verbose", action="store_true", help="Show detailed timing on stderr.")
    add_lock_timeout_argument(parser)
    return parser


def build_step_artifact(
    *,
    repo_root: Path,
    step: Path,
    source_path: Path | None = None,
    kind: str | None = None,
    force: bool = False,
    mesh_tolerance: float | None = None,
    mesh_angular_tolerance: float | None = None,
    reset_runtime_closure: bool = False,
    verbose: bool = False,
    logger: CliLogger | None = None,
    lock_timeout_s: float = 0.0,
) -> dict[str, object]:
    """Build the GLB/topology artifact for one STEP/.step.py and RETURN the result
    payload (the exact dict the CLI prints). This is the single source of truth,
    callable in-process by a long-lived warm-OCCT worker AND wrapped by main();
    it raises on error (the CLI shell owns argv parsing + JSON stdout).

    Passing ``source_path`` selects GENERATOR mode: the gen_step() source runs
    in-process and only the render package is written — the logical ``step``
    path never needs to exist on disk (STEP is exported on demand elsewhere).
    Without ``source_path``, ``step`` must be an existing imported STEP/STP file.

    ``reset_runtime_closure`` (default-off) is for warm worker processes: it makes
    the generator's recorded source closure deterministic across repeated in-process
    builds — see :func:`cadgen.generation.run_script_generator`.

    ``lock_timeout_s`` bounds the wait for a peer's generation lock. 0 waits (the CLI
    default: an agent asking for a build wants the build). A caller that must not block —
    the CAD Viewer's request path, which shares ONE serial warm worker across every model —
    passes a short one and gets ``{"ok": True, "contended": True}`` back, so it can report
    the peer's run instead of occupying the worker until the peer finishes."""
    repo_root = Path(repo_root).expanduser().resolve()
    step_path = Path(step).expanduser().resolve()
    from_generator = source_path is not None
    if from_generator:
        script_path = Path(source_path).expanduser().resolve()
        if not script_path.is_file():
            raise FileNotFoundError(f"Python generator does not exist for logical STEP path: {script_path}")
        source = source_from_path(script_path)
        if source is None:
            raise RuntimeError(f"Python generator is not a gen_step() CAD source: {script_path}")
        spec = _entry_spec_from_source(source)
        if spec.step_path is None or spec.step_path.resolve() != step_path:
            if spec.step_path is None:
                raise RuntimeError(f"Python generator does not map to logical STEP path: {step_path}")
            spec = replace(
                spec,
                cad_ref=_cad_ref_for_step(repo_root, step_path),
                display_name=step_path.stem,
                step_path=step_path,
            )
        if kind is not None and kind != spec.kind:
            raise ValueError(f"Requested --kind {kind!r} does not match generator kind {spec.kind!r}")
    elif not step_path.is_file():
        raise FileNotFoundError(f"STEP file does not exist: {step_path}")
    if step_path.suffix.lower() not in {".step", ".stp"}:
        raise ValueError(f"Expected a STEP/STP file: {step_path}")

    if logger is None:
        logger = CliLogger("step-artifact", verbose=verbose)
    mesh_tolerance = normalize_mesh_numeric(mesh_tolerance, field_name="mesh_tolerance")
    mesh_angular_tolerance = normalize_mesh_numeric(mesh_angular_tolerance, field_name="mesh_angular_tolerance")
    if from_generator:
        existing_spec = spec
        if mesh_tolerance is not None or mesh_angular_tolerance is not None:
            existing_spec = replace(
                existing_spec,
                mesh_tolerance=mesh_tolerance if mesh_tolerance is not None else existing_spec.mesh_tolerance,
                mesh_angular_tolerance=(
                    mesh_angular_tolerance
                    if mesh_angular_tolerance is not None
                    else existing_spec.mesh_angular_tolerance
                ),
                mesh_tolerance_explicit=mesh_tolerance is not None,
                mesh_angular_tolerance_explicit=mesh_angular_tolerance is not None,
            )
    else:
        existing_spec = EntrySpec(
            source_ref=_relative_to_base(repo_root, step_path),
            cad_ref=_cad_ref_for_step(repo_root, step_path),
            kind=kind or "part",
            source_path=step_path,
            display_name=step_path.stem,
            source="imported",
            step_path=step_path,
            mesh_tolerance=mesh_tolerance if mesh_tolerance is not None else DEFAULT_MESH_TOLERANCE,
            mesh_angular_tolerance=(
                mesh_angular_tolerance
                if mesh_angular_tolerance is not None
                else DEFAULT_MESH_ANGULAR_TOLERANCE
            ),
            mesh_tolerance_explicit=mesh_tolerance is not None,
            mesh_angular_tolerance_explicit=mesh_angular_tolerance is not None,
        )
    # Cheap pre-lock exit for the overwhelmingly common "nothing to do" call, so an
    # already-current model never pays for a lock acquisition. It is NOT the real gate --
    # see the is_current= re-check below, which is the one that has to be right.
    if not force:
        existing_artifact = _current_artifact_for_spec(existing_spec)
        if existing_artifact is not None:
            return _existing_result_payload(existing_spec, existing_artifact)

    # The lock covers the WHOLE build, not just the generator run. run_script_generator
    # takes this same lock internally (re-entrantly, so the nesting is a no-op), but it
    # releases on return — leaving the meshing, which is the long part, unlocked. A viewer
    # polling artifact status during that window would read "no build in flight", find the
    # package stale, and start a second one.
    #
    # is_current is re-evaluated UNDER the lock. The pre-lock check above cannot cover the
    # concurrent case: it ran before the peer's build existed, so a process that queued
    # behind one used to wake up and redo the full generator+mesh the holder had just
    # finished. Measured before this: two processes 0.3s apart on a cold package both ran
    # gen_step(), the second for a further 2.5s after waiting 2.67s for the lock.
    package_dir = render_package_dir(existing_spec.entry_path) if existing_spec.entry_path else None
    # This builds exactly what `scripts/gen` builds, and reported nothing while doing it:
    # the sidecar went to the viewer and a terminal caller watched a silent process.
    with cli_progress_line(
        existing_spec.source_ref, logger=logger, fallback="Building..."
    ) as progress_sink, artifact_build(
        STEP_PACKAGE,
        package_dir,
        is_current=lambda: _current_artifact_for_spec(existing_spec) is not None,
        force=force,
        deadline_ms=deadline_ms(lock_timeout_s),
        on_wait=lock_wait_notice(logger, existing_spec.source_ref),
        sink=progress_sink,
    ) as progress:
        if progress.contended:
            # A peer holds this model's lock and the caller asked not to wait it out. Not
            # an error: the model IS being built, just not by us.
            logger.info(f"another run is building {existing_spec.source_ref}; not waiting")
            return contended_payload(
                source_ref=existing_spec.source_ref,
                cad_ref=existing_spec.cad_ref,
                package_dir=package_dir,
                stepPath=relative_to_cwd(existing_spec.step_path),
            )
        if progress.skipped:
            artifact = _current_artifact_for_spec(existing_spec)
            if artifact is not None:
                return _existing_result_payload(existing_spec, artifact)
        if from_generator:
            scene = run_script_generator(
                existing_spec,
                "gen_step",
                logger=logger,
                force=force,
                reset_runtime_closure=reset_runtime_closure,
                progress=progress,
            )
            if scene is None:
                raise RuntimeError(f"Python generator did not produce a STEP scene: {existing_spec.source_ref}")
            spec = existing_spec
        else:
            # _generate_part_outputs reports this phase itself when it does the loading;
            # here the scene is preloaded, so the parse would otherwise go unreported.
            progress.phase(PHASE_GENERATE)
            with logger.timed(f"load STEP {relative_to_cwd(step_path)}"):
                scene = load_step_scene(step_path)
            kind_value = kind or infer_entry_kind(step_path, scene)
            spec = _build_entry_spec(
                repo_root,
                step_path,
                scene,
                kind=kind_value,
                mesh_tolerance=mesh_tolerance,
                mesh_angular_tolerance=mesh_angular_tolerance,
            )
        result = _generate_part_outputs(
            spec,
            entries_by_step_path=_entries_by_step_path_for_repo(repo_root, spec),
            preloaded_scene=scene,
            require_step_file=not from_generator,
            force=force,
            logger=logger,
            progress=progress,
        )
    stats = result.selector_bundle.manifest.get("stats") if result.selector_bundle is not None else {}
    return _generated_result_payload(spec, scene, stats if isinstance(stats, dict) else {})


def run_cli_payload(
    argv: list[str] | None = None,
    *,
    reset_runtime_closure: bool = False,
) -> dict[str, object]:
    """Parse CLI ``argv`` and run :func:`build_step_artifact`, RETURNING its payload
    (no printing, no logger.total()). The in-process primitive shared by ``main()``
    and the CAD Viewer's warm worker — the worker passes ``reset_runtime_closure=True``
    so repeated warm builds record the same closure a cold CLI does."""
    args = build_parser().parse_args(argv)
    logger = CliLogger("step-artifact", verbose=bool(args.verbose))
    payload = build_step_artifact(
        repo_root=Path(args.repo_root),
        step=Path(args.step),
        source_path=Path(args.source_path) if args.source_path else None,
        kind=args.kind,
        force=bool(args.force),
        mesh_tolerance=args.mesh_tolerance,
        mesh_angular_tolerance=args.mesh_angular_tolerance,
        reset_runtime_closure=reset_runtime_closure,
        logger=logger,
        lock_timeout_s=float(args.lock_timeout or 0.0),
    )
    logger.total()
    return payload


def main(argv: list[str] | None = None) -> int:
    payload = run_cli_payload(argv)
    print(json.dumps(payload, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
