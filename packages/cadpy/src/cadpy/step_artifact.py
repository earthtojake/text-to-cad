from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path

from cadpy.cli_logging import CliLogger
from cadpy.generation import (
    EntrySpec,
    _existing_topology_artifact_matches_spec_without_scene,
    _entry_spec_from_source,
    _generate_part_outputs,
    run_script_generator,
)
from cadpy.metadata import DEFAULT_MESH_ANGULAR_TOLERANCE, DEFAULT_MESH_TOLERANCE, normalize_mesh_numeric
from cadpy.render import part_glb_path, relative_to_repo
from cadpy.step_export import write_xcaf_doc_step_file
from cadpy.step_metadata import read_text_to_cad_step_metadata
from cadpy.step_scene import LoadedStepScene, load_step_scene, step_file_hash
from cadpy.catalog import iter_cad_sources, source_from_path
from cadpy.step_targets import (
    ResolvedStepTarget,
    StepTopologyArtifact,
    StepTopologyArtifactError,
    validate_step_topology_artifact,
)


def _repo_relative(repo_root: Path, path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(repo_root).as_posix()
    except ValueError:
        return resolved.as_posix()


def _cad_ref_for_step(repo_root: Path, step_path: Path) -> str:
    relative = _repo_relative(repo_root, step_path)
    suffix = step_path.suffix
    return relative[: -len(suffix)] if suffix else relative


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
        source_ref=_repo_relative(repo_root, step_path),
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
    except Exception:
        entries = {}
    if spec.step_path is not None:
        entries[spec.step_path.resolve()] = spec
    return entries


def _result_payload(
    spec: EntrySpec,
    *,
    entry_kind: str,
    source_kind: str,
    glb_path: Path,
    step_hash: str | None = None,
    source_hash: str | None = None,
    stats: dict[str, object] | None = None,
    load_elapsed_ms: float | None = None,
    skipped: bool = False,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "ok": True,
        "stepPath": relative_to_repo(spec.step_path),
        "glbPath": relative_to_repo(glb_path),
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
    glb_path = part_glb_path(spec.step_path)
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
        glb_path=glb_path,
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
        glb_path=artifact.glb_path,
        stats=stats if isinstance(stats, dict) else {},
        skipped=True,
    )


def _write_step_after_artifact(spec: EntrySpec, scene: LoadedStepScene, *, logger: CliLogger) -> str:
    if scene.doc is None:
        raise RuntimeError(f"Cannot write STEP after GLB artifact; scene has no XCAF document: {spec.step_path}")
    source_hash = (
        str(getattr(scene, "source_hash", "") or "").strip()
        if str(getattr(scene, "source_kind", "") or "").strip().lower() == "python"
        else ""
    )
    source_path = (
        str(getattr(scene, "source_path", "") or "").strip()
        if str(getattr(scene, "source_kind", "") or "").strip().lower() == "python"
        else ""
    )
    return write_xcaf_doc_step_file(
        scene.doc,
        spec.step_path,
        label=spec.step_path.stem,
        originating_system="tom-cad direct XCAF assembly" if spec.kind == "assembly" else "build123d",
        text_to_cad_entry_kind=spec.kind,
        source_path=source_path or None,
        source_hash=source_hash or None,
        logger=logger,
    )


def _current_artifact_for_spec(spec: EntrySpec) -> StepTopologyArtifact | None:
    if not _existing_topology_artifact_matches_spec_without_scene(spec):
        return None
    try:
        return validate_step_topology_artifact(
            ResolvedStepTarget(
                cad_path=spec.cad_ref,
                kind=spec.kind,
                source_path=spec.source_path,
                step_path=spec.step_path,
            ),
            glb_path=part_glb_path(spec.step_path),
            require_selector=True,
        )
    except StepTopologyArtifactError:
        return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m cadpy.step_artifact",
        description="Generate the hidden CAD Viewer GLB/topology artifact for one STEP/STP file.",
    )
    parser.add_argument("--repo-root", required=True, help="Repository/workspace root for relative STEP metadata.")
    parser.add_argument("--step", required=True, help="STEP/STP source file to process.")
    parser.add_argument("--source-path", help="Python gen_step() source path for a logical STEP output.")
    parser.add_argument("--kind", choices=("part", "assembly"), help="Override inferred STEP entry kind.")
    parser.add_argument("--skip-step-write", action="store_true", help="Generate from same-stem Python generator without writing STEP.")
    parser.add_argument("--write-step-after-artifact", action="store_true", help="With --skip-step-write, write/update the STEP file after the GLB artifact is ready.")
    parser.add_argument("--force", action="store_true", help="Regenerate even if a current artifact exists.")
    parser.add_argument("--mesh-tolerance", type=float, help="Override automatic mesh linear deflection.")
    parser.add_argument("--mesh-angular-tolerance", type=float, help="Override automatic mesh angular deflection.")
    parser.add_argument("--verbose", action="store_true", help="Show detailed timing on stderr.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if bool(args.write_step_after_artifact) and not bool(args.skip_step_write):
        raise ValueError("--write-step-after-artifact requires --skip-step-write")
    repo_root = Path(args.repo_root).expanduser().resolve()
    step_path = Path(args.step).expanduser().resolve()
    if bool(args.skip_step_write):
        script_path = (
            Path(args.source_path).expanduser().resolve()
            if args.source_path
            else step_path.with_suffix(".py")
        )
        if not script_path.is_file():
            raise FileNotFoundError(f"Python generator does not exist for logical STEP path: {script_path}")
        source = source_from_path(script_path)
        if source is None:
            raise RuntimeError(f"Python generator is not a gen_step() CAD source: {script_path}")
        spec = _entry_spec_from_source(source)
        if spec.step_path is None or spec.step_path.resolve() != step_path:
            if not args.source_path or spec.step_path is None:
                raise RuntimeError(f"Python generator does not map to logical STEP path: {step_path}")
            spec = replace(
                spec,
                cad_ref=_cad_ref_for_step(repo_root, step_path),
                display_name=step_path.stem,
                step_path=step_path,
            )
        if args.kind is not None and args.kind != spec.kind:
            raise ValueError(f"Requested --kind {args.kind!r} does not match generator kind {spec.kind!r}")
    elif not step_path.is_file():
        raise FileNotFoundError(f"STEP file does not exist: {step_path}")
    if step_path.suffix.lower() not in {".step", ".stp"}:
        raise ValueError(f"Expected a STEP/STP file: {step_path}")

    logger = CliLogger("step-artifact", verbose=bool(args.verbose))
    mesh_tolerance = normalize_mesh_numeric(args.mesh_tolerance, field_name="mesh_tolerance")
    mesh_angular_tolerance = normalize_mesh_numeric(
        args.mesh_angular_tolerance,
        field_name="mesh_angular_tolerance",
    )
    if bool(args.skip_step_write):
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
            source_ref=_repo_relative(repo_root, step_path),
            cad_ref=_cad_ref_for_step(repo_root, step_path),
            kind=args.kind or "part",
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
    if not args.force:
        existing_artifact = _current_artifact_for_spec(existing_spec)
        if existing_artifact is not None:
            print(json.dumps(_existing_result_payload(existing_spec, existing_artifact), separators=(",", ":")))
            return 0

    glb_path = part_glb_path(step_path)
    if bool(args.skip_step_write):
        scene = run_script_generator(
            existing_spec,
            "gen_step",
            logger=logger,
            force=bool(args.force),
            load_current_scene=False,
            skip_step_write=True,
        )
        if scene is None:
            raise RuntimeError(f"Python generator did not produce a STEP scene: {existing_spec.source_ref}")
        spec = existing_spec
        if bool(args.write_step_after_artifact):
            step_hash = _write_step_after_artifact(spec, scene, logger=logger)
            scene.step_hash = step_hash
    else:
        with logger.timed(f"load STEP {relative_to_repo(step_path)}"):
            scene = load_step_scene(step_path)
        kind = args.kind or _infer_entry_kind(step_path, scene)
        spec = _build_entry_spec(
            repo_root,
            step_path,
            scene,
            kind=kind,
            mesh_tolerance=mesh_tolerance,
            mesh_angular_tolerance=mesh_angular_tolerance,
        )
    result = _generate_part_outputs(
        spec,
        entries_by_step_path=_entries_by_step_path_for_repo(repo_root, spec),
        preloaded_scene=scene,
        require_step_file=not bool(args.skip_step_write),
        force=bool(args.force),
        logger=logger,
    )
    stats = result.selector_bundle.manifest.get("stats") if result.selector_bundle is not None else {}
    payload = _generated_result_payload(spec, scene, stats if isinstance(stats, dict) else {})
    if bool(args.write_step_after_artifact):
        print(json.dumps({**payload, "stepWrite": {"status": "complete", "stepHash": payload.get("stepHash", "")}}, separators=(",", ":")))
    else:
        print(json.dumps(payload, separators=(",", ":")))
    logger.total()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
