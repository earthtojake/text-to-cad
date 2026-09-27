"""Compile one STEP/STP DOCUMENT into the store: its tree and components.

The engine behind ``cadgen step compile`` (:func:`cadgen.step.compile`) and the
compile job every door and the CAD Viewer submit for a document the store has no
tree for (``cadgen.daemon.executors.submit_compile``). One input, one behaviour:
the document's BYTES are read and their tree published. No model script is
accepted, parsed or run here -- a script is a program, and ``python <model>.py``
is its one door (README laws 1 and 7).

There is no command line in this module: the command is the generated
``cadgen step compile`` (``cadgen.cli.step_compile``).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cadgen.cli_logging import CliLogger
from cadgen.cli_progress import cli_progress_line
from cadgen._internal.generation import (
    EntrySpec,
    _generate_part_outputs,
    _manifest_records_edge_visibility_classes,
)
from cadgen.coordination import PHASE_GENERATE, STEP_PACKAGE, artifact_build
from cadgen._internal.doors import STEP_SUFFIXES
from cadgen.catalog import build_scope
from cadgen.render import relative_to_cwd
from cadgen._internal.step_scene import step_file_hash
from cadgen._internal.step_scene_package import load_step_scene_exact
from cadgen.step_targets import (
    StepTopologyArtifact,
)


@dataclass(frozen=True, kw_only=True)
class _ImportedArtifactSnapshot(StepTopologyArtifact):
    """One verified document selection, owned only by this currency check."""

    document_hash: str
    tree: str


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


def _build_entry_spec(repo_root: Path, step_path: Path) -> EntrySpec:
    """The spec of a DOCUMENT: keyed by its own path, with no script behind it.
    It carries no mesh tolerances -- a tree is tessellation-free."""
    return EntrySpec(
        source_ref=_relative_to_base(repo_root, step_path),
        cad_ref=_cad_ref_for_step(repo_root, step_path),
        source_path=step_path,
        display_name=step_path.stem,
        source="imported",
        step_path=step_path,
    )


def _compiled_result_payload(spec: EntrySpec, stats: dict[str, object] | None) -> dict[str, object]:
    from cadgen.catalog import result_tree_for
    from cadgen.store.trees import tree_kind_for

    tree = result_tree_for(spec.entry_path)
    return {
        "ok": True,
        "document": relative_to_cwd(spec.step_path),
        # The tree these bytes resolve to (index/document → tree): the result's
        # identity, never a directory — nothing of the sort exists in the store.
        "tree": tree,
        # Off the tree (store.trees.tree_kind) — the one place kind is decided.
        "entryKind": tree_kind_for(tree) or "part",
        "stats": stats or {},
    }


def _existing_result_payload(
    spec: EntrySpec, artifact: _ImportedArtifactSnapshot
) -> dict[str, object] | None:
    from cadgen._internal.source_sidecar import read_source_sidecar

    # Bind the answer to the bytes on disk NOW, not the snapshot's remembered
    # digest: the document may have been replaced after the lookup.
    step_hash = step_file_hash(spec.step_path)
    if step_hash != artifact.document_hash:
        return None
    # "Current" is said about the document AND the declarations beside it: a
    # sidecar bound to other bytes fails loudly here (SidecarBindingError) rather
    # than being reported current and then refused by the reader that follows.
    # Nothing is taken from it -- a compile's answer is the tree.
    read_source_sidecar(spec.step_path, document_hash=step_hash)
    stats = artifact.manifest.get("stats")
    # capture_tree already classified this exact root before flattening.
    # Do not select a newer document index or reopen the tree for its kind.
    return {
        "ok": True,
        "document": relative_to_cwd(spec.step_path),
        "tree": artifact.tree,
        "entryKind": artifact.kind,
        "stats": stats if isinstance(stats, dict) else {},
        "skipped": True,
    }


def _current_artifact_for_spec(spec: EntrySpec) -> _ImportedArtifactSnapshot | None:
    """The complete tree the store holds for this document's bytes, or None.

    A compile completes when its native geometry is available. Display
    derivations belong to their consumers and must never run in this gate."""
    from cadgen.catalog import result_snapshot_for
    from cadgen.store.objects import object_path
    from cadgen.store.trees import capture_tree

    if spec.step_path is None or not spec.step_path.is_file():
        return None
    snapshot = result_snapshot_for(spec.entry_path)
    if snapshot is None:
        return None
    try:
        manifest, _ = capture_tree(snapshot[1], retain_payloads=False)
    except (OSError, ValueError):
        return None
    if not _manifest_records_edge_visibility_classes(manifest):
        return None
    return _ImportedArtifactSnapshot(
        cad_path=spec.cad_ref,
        source_path=spec.source_path,
        step_path=spec.step_path,
        artifact_path=object_path(snapshot[1]),
        manifest=manifest,
        document_hash=snapshot[0],
        tree=snapshot[1],
    )


def build_step_artifact(
    *,
    repo_root: Path,
    step: Path,
    force: bool = False,
    verbose: bool = False,
    logger: CliLogger | None = None,
) -> dict[str, object]:
    """Compile the DOCUMENT ``step`` into the store and return the result payload
    (``ok``, ``document``, ``tree``, ``entryKind``, ``stats``; ``skipped`` when the
    tree for these bytes already existed). Raises on error.

    ``step`` must be an existing STEP/STP file. The document itself is never
    written, and nothing appears beside it: the tree is keyed by its bytes."""
    repo_root = Path(repo_root).expanduser().resolve()
    step_path = Path(step).expanduser().resolve()
    if not step_path.is_file():
        raise FileNotFoundError(f"STEP file does not exist: {step_path}")
    if step_path.suffix.lower() not in STEP_SUFFIXES:
        raise ValueError(f"Expected a STEP/STP file: {step_path}")

    if logger is None:
        logger = CliLogger("step-artifact", verbose=verbose)
    spec = _build_entry_spec(repo_root, step_path)
    # Cheap early exit for the overwhelmingly common "nothing to do" call. It is NOT
    # the real gate -- see the is_current= re-check below, which is the one that has
    # to be right.
    if not force:
        existing_artifact = _current_artifact_for_spec(spec)
        if existing_artifact is not None:
            payload = _existing_result_payload(spec, existing_artifact)
            if payload is not None:
                return payload

    # Progress is scoped to the document's path, which stays stable while a
    # recompile changes the result's tree.
    scope = build_scope(spec.entry_path) if spec.entry_path else None
    with cli_progress_line(
        spec.source_ref, logger=logger, fallback="Building..."
    ) as progress_sink, artifact_build(
        STEP_PACKAGE,
        scope,
        is_current=lambda: _current_artifact_for_spec(spec) is not None,
        force=force,
        sink=progress_sink,
    ) as progress:
        if progress.skipped:
            artifact = _current_artifact_for_spec(spec)
            if artifact is not None:
                payload = _existing_result_payload(spec, artifact)
                if payload is not None:
                    return payload
        from cadgen.daemon import broker

        # A document's compile is a JOB (STORE.md §9): its kernel work -- the read
        # and the component emit -- holds a job slot the way a model body does.
        with broker.held(spec.source_ref):
            # _generate_part_outputs reports this phase itself when it does the loading;
            # here the scene is preloaded, so the parse would otherwise go unreported.
            progress.phase(PHASE_GENERATE)
            with logger.timed(f"load STEP {relative_to_cwd(step_path)}"):
                scene = load_step_scene_exact(step_path)
            result = _generate_part_outputs(
                spec,
                # A document compile has no source dependencies to discover.
                entries_by_step_path={spec.step_path.resolve(): spec},
                preloaded_scene=scene,
                require_step_file=True,
                force=force,
                logger=logger,
                progress=progress,
            )
    stats = result.selector_bundle.manifest.get("stats") if result.selector_bundle is not None else {}
    return _compiled_result_payload(spec, stats if isinstance(stats, dict) else {})
