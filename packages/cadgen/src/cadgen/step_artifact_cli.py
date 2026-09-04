from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
from typing import Callable

from cadgen.cli_logging import CliLogger
from cadgen._internal.generation import (
    EntrySpec,
    cli_progress_line,
    _assembly_glb_package_current,
    _existing_topology_artifact_matches_spec_without_scene,
    _entry_spec_from_source,
    _generate_part_outputs,
    _generated_assembly_glb_closure_current,
    _produce_declared_mesh_exports,
    run_script_generator,
)
from cadgen.coordination import PHASE_GENERATE, STEP_PACKAGE, ProgressEvent, artifact_build
from cadgen.metadata import normalize_mesh_numeric
from cadgen.catalog import build_scope, result_view_dir
from cadgen.render import relative_to_cwd
from cadgen._internal.step_scene import LoadedStepScene, load_step_scene, step_file_hash
from cadgen.catalog import iter_cad_sources, source_from_path
from cadgen.step_targets import (
    ResolvedStepTarget,
    StepTopologyArtifact,
    StepTopologyArtifactError,
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
    """Classify a STEP model as ``part`` or ``assembly``: a STEP whose product
    hierarchy has child nodes reads as an assembly. Purely structural — a STEP
    file carries no cadgen metadata of any kind."""
    del step_path  # classification is structural; the file's bytes carry no metadata
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
        mesh_tolerance=mesh_tolerance,
        mesh_angular_tolerance=mesh_angular_tolerance,
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
    step_hash: str | None = None,
    source_hash: str | None = None,
    stats: dict[str, object] | None = None,
    load_elapsed_ms: float | None = None,
    skipped: bool = False,
) -> dict[str, object]:
    from cadgen.catalog import result_tree_for

    payload: dict[str, object] = {
        "ok": True,
        "stepPath": relative_to_cwd(spec.step_path),
        # The tree these bytes resolve to (index/document → tree): the result's
        # identity, never a directory — nothing of the sort exists in the store.
        "tree": result_tree_for(spec.entry_path),
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
        stats=stats,
        load_elapsed_ms=scene.load_elapsed * 1000.0,
    )


def _existing_result_payload(spec: EntrySpec, artifact: StepTopologyArtifact) -> dict[str, object]:
    entry_kind = str(artifact.manifest.get("entryKind") or spec.kind)
    from cadgen._internal.source_sidecar import read_source_sidecar

    sidecar = read_source_sidecar(spec.entry_path) or {}
    source_kind = "python" if sidecar else "step"
    step_hash = str(artifact.manifest.get("stepHash") or "")
    source_hash = str(sidecar.get("sourceHash") or "")
    if source_kind != "python" and not step_hash:
        step_hash = step_file_hash(spec.step_path)
    stats = artifact.manifest.get("stats")
    return _result_payload(
        spec,
        entry_kind=entry_kind,
        source_kind=source_kind,
        step_hash=step_hash or None,
        source_hash=source_hash or None,
        stats=stats if isinstance(stats, dict) else {},
        skipped=True,
    )


def _current_artifact_for_spec(spec: EntrySpec) -> StepTopologyArtifact | None:
    if not _existing_topology_artifact_matches_spec_without_scene(spec):
        return None
    package_dir = result_view_dir(spec.entry_path)
    # A component-GLB package is a DIRECTORY, and validate_step_topology_artifact() gates on
    # `.is_file()` (step_targets.py) -- so routing a package through it always raised
    # missing_glb, this whole fast path returned None, and EVERY build re-ran the generator.
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
    # No package directory -> nothing current (the package IS the only artifact form).
    return None


def _with_declared_exports(
    payload: dict[str, object], spec: EntrySpec, *, logger: CliLogger | None
) -> dict[str, object]:
    """Produce the model's declared mesh exports and list what this run wrote.

    Declared `@stl`/`@glb`/`@threemf` outputs are CONTENT-gated, not
    build-gated: a current model whose STL was deleted heals it here from the
    store package without a rebuild — the same thing a model-script run does on
    its own no-op path, so the two front doors cannot disagree about what a
    finished build leaves on disk.
    """
    written = _produce_declared_mesh_exports(spec, logger=logger, announce=False)
    if written:
        payload["exports"] = [relative_to_cwd(path) for path in written]
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m cadgen.step_artifact_cli",
        description="Build the CAD Viewer render package for one STEP/STP file or @step model script.",
    )
    parser.add_argument("--repo-root", required=True, help="Repository/workspace root for relative STEP metadata.")
    parser.add_argument("--step", required=True, help="STEP/STP source file to process.")
    parser.add_argument(
        "--source-path",
        help=(
            "Python @step source for a generated model. Selects generator mode: the build "
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
    return parser


def _fan_out_sink(
    cli_sink: Callable[[ProgressEvent], None],
    extra: Callable[[ProgressEvent], None] | None,
) -> Callable[[ProgressEvent], None]:
    """Deliver each event to the CLI line and to an in-process listener.

    The listener is isolated: a caller whose sink raises (a viewer whose client
    socket has gone away mid-build, say) must lose its progress, not the build.
    """
    if extra is None:
        return cli_sink

    def fan_out(event: ProgressEvent) -> None:
        cli_sink(event)
        try:
            extra(event)
        except Exception:  # noqa: BLE001 - reporting must never fail a build
            pass

    return fan_out


def build_step_artifact(
    *,
    repo_root: Path,
    step: Path,
    source_path: Path | None = None,
    kind: str | None = None,
    force: bool = False,
    mesh_tolerance: float | None = None,
    mesh_angular_tolerance: float | None = None,
    verbose: bool = False,
    logger: CliLogger | None = None,
    sink: Callable[[ProgressEvent], None] | None = None,
) -> dict[str, object]:
    """Build the GLB/topology artifact for one STEP/.step.py and RETURN the result
    payload (the exact dict the CLI prints). This is the single source of truth,
    callable in-process by a long-lived warm-OCCT worker AND wrapped by main();
    it raises on error (the CLI shell owns argv parsing + JSON stdout).

    Passing ``source_path`` selects GENERATOR mode: the @step source runs
    in-process and only the render package is written — the logical ``step``
    path never needs to exist on disk (STEP is exported on demand elsewhere).
    Without ``source_path``, ``step`` must be an existing imported STEP/STP file.

    ``sink`` receives every :class:`ProgressEvent` alongside the CLI's own line, so an
    in-process caller can watch the build as DATA rather than reading back the status
    record the run happens to publish. The CAD Viewer's compile worker uses this: it is
    what lets an import report its phase and counts live, instead of the viewer scraping
    a file whose location depends on which producer wrote it."""
    repo_root = Path(repo_root).expanduser().resolve()
    step_path = Path(step).expanduser().resolve()
    from_generator = source_path is not None
    if from_generator:
        script_path = Path(source_path).expanduser().resolve()
        if not script_path.is_file():
            raise FileNotFoundError(f"Python generator does not exist for logical STEP path: {script_path}")
        source = source_from_path(script_path)
        if source is None:
            raise RuntimeError(f"Python generator is not a @step CAD source: {script_path}")
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
            mesh_tolerance=mesh_tolerance,
            mesh_angular_tolerance=mesh_angular_tolerance,
        )
    # Cheap early exit for the overwhelmingly common "nothing to do" call. It is NOT
    # the real gate -- see the is_current= re-check below, which is the one that has
    # to be right.
    if not force:
        existing_artifact = _current_artifact_for_spec(existing_spec)
        if existing_artifact is not None:
            return _with_declared_exports(
                _existing_result_payload(existing_spec, existing_artifact),
                existing_spec,
                logger=logger,
            )

    # The progress record covers the WHOLE build, not just the generator run: the
    # meshing is the long part, and a viewer polling during it must see a build.
    #
    # Progress keys by the MODEL PATH, never by the content-keyed package dir. A rebuild
    # changes the document's content key mid-build, and no reader could know the new key
    # in advance: the viewer's progress reader derives its record from the model path it
    # is polling (cadgen.viewer.store_paths.build_scope). `package_dir` stays because the
    # RESULT payloads name the package; only the progress identity is path-keyed.
    package_dir = result_view_dir(existing_spec.entry_path) if existing_spec.entry_path else None
    scope = build_scope(existing_spec.entry_path) if existing_spec.entry_path else None
    # This builds exactly what a model-script run builds, and reported nothing while doing it:
    # the sidecar went to the viewer and a terminal caller watched a silent process.
    with cli_progress_line(
        existing_spec.source_ref, logger=logger, fallback="Building..."
    ) as progress_sink, artifact_build(
        STEP_PACKAGE,
        scope,
        is_current=lambda: _current_artifact_for_spec(existing_spec) is not None,
        force=force,
        # The caller's sink runs ALONGSIDE the CLI line, never instead of it: a
        # terminal watching this build still gets its bar when the viewer is
        # also listening. A caller's sink must not be able to fail the build, so
        # it is guarded here rather than trusted.
        sink=_fan_out_sink(progress_sink, sink),
    ) as progress:
        if progress.skipped:
            artifact = _current_artifact_for_spec(existing_spec)
            if artifact is not None:
                return _with_declared_exports(
                    _existing_result_payload(existing_spec, artifact),
                    existing_spec,
                    logger=logger,
                )
        import contextlib

        with contextlib.ExitStack() as slot:
            if from_generator:
                from cadgen._internal.doors import announce_rebuild
                from cadgen.store.gate import stale

                document = existing_spec.step_path
                verdict = stale(existing_spec.script_path) if existing_spec.script_path else None
                announce_rebuild(
                    "step compile",
                    document,
                    reason=(
                        "--force" if force
                        else "no document on disk" if not document.is_file()
                        else verdict.reason() if verdict is not None and verdict.stale
                        else "its render package is missing or stale"
                    ),
                    source=existing_spec.script_path or existing_spec.source_path,
                    verb="compiling its render package",
                )
                scene = run_script_generator(
                    existing_spec,
                    "step",
                    logger=logger,
                    force=force,
                    progress=progress,
                )
                if scene is None:
                    raise RuntimeError(f"Python generator did not produce a STEP scene: {existing_spec.source_ref}")
                # The generation pipeline's contract: a generated model's build
                # ALWAYS produces its STEP file (assembled from the package —
                # design/step-document-architecture.md), no matter which front
                # door asked (a model-script run, `cadgen step build`, inspect).
                import dataclasses

                spec = existing_spec
                if spec.step_export_path is None and spec.step_path is not None:
                    spec = dataclasses.replace(spec, step_export_path=spec.step_path)
            else:
                from cadgen.daemon import broker

                # An imported document's compile is a JOB (STORE.md §9): its kernel
                # work -- the read and the component emit -- holds a job slot the way
                # a model body does. (A generated document's run takes its own slot
                # inside run_script_generator.)
                slot.enter_context(broker.held(existing_spec.source_ref))
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
    return _with_declared_exports(
        _generated_result_payload(spec, scene, stats if isinstance(stats, dict) else {}),
        spec,
        logger=logger,
    )


def run_cli_payload(argv: list[str] | None = None) -> dict[str, object]:
    """Parse CLI ``argv`` and run :func:`build_step_artifact`, RETURNING its payload
    (no printing, no logger.total()). The in-process primitive shared by ``main()``
    and the CAD Viewer's warm worker."""
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
        logger=logger,
    )
    logger.total()
    return payload


def main(argv: list[str] | None = None) -> int:
    payload = run_cli_payload(argv)
    print(json.dumps(payload, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
