from __future__ import annotations

import copy
import json
import sys
import threading
import time

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from cadgen.catalog import source_from_path
from cadgen.cli_logging import CliLogger
from cadgen.coordination import (
    DRAWING_PACKAGE,
    PHASE_GENERATE,
    PHASE_MESH,
    STEP_PACKAGE,
    ProgressEvent,
    artifact_build,
    resolve as resolve_progress,
)
from cadgen._internal.source_hash import (
    python_source_hash,
)
from cadgen._internal.step_scene import (
    load_step_scene_cached,
    LoadedStepScene,
    SelectorOptions,
    step_file_hash,
)
from cadgen._internal.generation_runner import (
    _ArtifactJob,
    _ensure_step_ready,
    _mark_scene_python_backed,
    _run_artifact_jobs,
    _spec_output_dir,
    run_script_generator,
)
from cadgen._internal.generation_spec import (
    EntrySpec,
    GeneratedStepResult,
    _cli_progress_line,
    _display_path,
    _entry_spec_from_source,
    _selector_options_for_part,
)

def _stage(spec: EntrySpec, cleanup: object) -> Path:
    """A folder beside the saved STEP for the export to write into, removed with ``cleanup``.
    A build killed while it saved (its caller left) left its staging folder, a full copy
    of its document, beside its output: gone before this one stages. The file takes its
    final basename there, so its labels and bytes do not depend on the folder. The export
    job writes into it from another process (a daemon worker's), which may still hold the
    staged file when an interrupt unwinds the build: a removal Windows then refuses never
    replaces the interrupt, and the next build's sweep removes what is left."""
    from tempfile import TemporaryDirectory

    from cadgen._internal.filetrace import paused
    from cadgen._internal.temp_leftovers import stage_prefix, sweep_stages

    spec.step_path.parent.mkdir(parents=True, exist_ok=True)
    with paused():
        sweep_stages(spec.step_path.parent)
    return Path(cleanup.enter_context(TemporaryDirectory(prefix=stage_prefix(spec.step_path.stem),
                                                         dir=spec.step_path.parent, ignore_cleanup_errors=True)))


def _sha256_of(path: Path) -> str:
    import hashlib

    from cadgen._internal.atomic_replace import open_with_ladder

    # Through the ladder: a peer build publishing the same model may be renaming
    # over this very file, which Windows refuses an open for (STORE.md §7).
    digest = hashlib.sha256()
    with open_with_ladder(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_or_none(path: Path) -> str | None:
    try:
        return _sha256_of(path)
    except FileNotFoundError:
        return None


def _document_pair_state(step_path: Path) -> tuple[str | None, str | None]:
    """The saved STEP's and its sidecar's sha256, None for a file that is absent.

    Through the gate's digest memo (``store.gate._sha256_file``), which one job
    already consults for these very files: a file whose settled identity has
    not moved since this process hashed it, or since it renamed its own written
    copy into place, is not read again (STORE.md §4). A label edit keeps a STEP
    of hundreds of megabytes, and used to read it once per call."""
    from cadgen._internal.source_sidecar import source_sidecar_path
    from cadgen.store.gate import _sha256_file

    step = Path(step_path).expanduser().resolve()
    return _sha256_file(step), _sha256_file(source_sidecar_path(step))


def _publish_sidecar(staged_step: Path, entry_path: Path) -> None:
    """Move the build's staged sidecar beside the saved STEP, or remove the saved
    one when the build staged none. A saved sidecar that already has the staged
    bytes stays in place, as a kept document does: a viewer versions the sidecar
    by its file stamp, and a new stamp would reload the model for an edit that
    changed nothing on screen, such as a label or a comment."""
    from cadgen._internal.atomic_replace import replace_atomic
    from cadgen._internal.source_sidecar import remove_source_sidecar, source_sidecar_path

    staged, saved = source_sidecar_path(staged_step), source_sidecar_path(entry_path)
    if not staged.is_file():
        remove_source_sidecar(entry_path)
    elif _sha256_or_none(saved) != _sha256_of(staged):
        replace_atomic(staged, saved)


@dataclass(frozen=True)
class _ExportPlan:
    """What a build does about its STEP (STORE.md §3, *Exports*): keep the file on disk,
    whose recorded output entry is ``kept``, or export the result -- ``plain``, without
    names, where the file the same result was last written to did not hold it. ``why`` says
    why a file the same result was last written to, still on disk, is written again (a
    current model's re-export, :func:`_hit`); empty otherwise."""

    kept: dict | None
    plain: bool
    why: str = ""

    @property
    def kept_sha256(self) -> str:
        return str(self.kept["sha256"]) if self.kept is not None else ""

    def output(self) -> dict:
        """The record's entry for the STEP until it is saved: a kept file's own, else
        pending (an empty sha256, which the gate reads as never written)."""
        from cadgen.step_export import STEP_WRITER_SCHEME

        if self.kept is not None:
            return dict(self.kept)
        return {"sha256": "", "writer": STEP_WRITER_SCHEME, **({"plain": True} if self.plain else {})}


def _export_plan(previous: Mapping[str, object], step_key: str, tree: str, *, force: bool,
                 on_disk: str | None) -> _ExportPlan:
    """The kept rule: a build keeps its STEP, writing and verifying nothing, when its
    record's last build had this very tree, wrote the file with this writer, the file on
    disk when the build started still has the bytes it recorded, the store maps those
    bytes to a tree (their document entry), and they held the result or were written
    plain (the same result is written plain to the same bytes again) -- unless forced.
    Otherwise it exports, plain where the same result's last file from this writer did
    not hold it (its document entry lists what differs) or was itself written plain; a
    forced build, or another writer, writes the names again, and a file whose entry the
    store lost is written again (to the same bytes) and verified again."""
    from cadgen.step_export import STEP_WRITER_SCHEME
    from cadgen.store.records import document_entry_for_hash

    prior = (previous.get("outputs") or {}).get(step_key)
    prior = prior if isinstance(prior, dict) else {}
    same = previous.get("tree") == tree
    sha = str(prior.get("sha256") or "")
    entry = document_entry_for_hash(sha) if sha else None
    marked = bool(entry and entry.get("differ"))
    this_writer = prior.get("writer") == STEP_WRITER_SCHEME
    if (not force and same and sha and this_writer and on_disk == sha and entry is not None
            and (not marked or prior.get("plain"))):
        return _ExportPlan(kept={key: prior[key] for key in ("sha256", "writer", "plain") if key in prior},
                           plain=bool(prior.get("plain")))
    why = ""
    if not force and same and sha and on_disk == sha:
        why = ("did not hold its result" if marked and not prior.get("plain")
               else "was written by another writer" if not this_writer
               else "has no entry in the store" if entry is None else "")
    elif not force and same:
        why = ("was never written" if not sha else "is missing" if on_disk is None
               else "is not the file the record names")
    return _ExportPlan(kept=None, plain=not force and same and this_writer and (marked or bool(prior.get("plain"))),
                       why=why)


def _submit_export(tree: str, staged: Path, *, names: bool, live: Mapping[str, object]) -> object:
    """The export job writing ``tree`` to ``staged`` (``store/exports.py``), started now:
    the build pool's, or, for a result holding a component only this process's live shape
    stands for, this process's own, done here and now. Its ``result()`` is the job's answer."""
    if live:
        from concurrent.futures import Future

        from cadgen.store.exports import export_step

        done: Future = Future()
        done.set_result(export_step(tree, staged, names=names, shapes=live))
        return done
    from cadgen.daemon.artifacts import submit_artifact

    return submit_artifact({"kind": "export", "tree": tree, "out": str(staged), "names": names})


class _Export:
    """What a model's build owes beside its record, finished after it (STORE.md §3,
    *Exports*; §9a).

    Queued by the one pipeline the moment the model's result is recorded, root or child
    alike: the export job writing its STEP from the stored tree is submitted to the build
    pool then, so a child's file is written while its parent's body goes on, and the run
    that owns the command finishes every export it queued once its own body has returned,
    in the order queued -- children before the parent that called them
    (``cadgen.authoring.build_run``). Finishing one publishes the written file (the file
    and its sidecar into place, the expected pair checked first, §7; the bytes mapped to
    the tree pending their verify; the record's output entry; the ``STEP saved`` event,
    its ``elapsed`` read from the clock the model's ``done`` event reads),
    has it verified (a build with no daemon waits for the answer and warns; a daemon's
    verify finishes on the pool), then cuts the model's declared meshes from that file's
    bytes. A kept STEP submits nothing and publishes only its sidecar; a current model has
    its display data derived here too, after the STEP its file's bytes then map to; a
    mesh-only model has only its meshes. An export that fails fails the command, and the
    file on disk stays as it was.

    ``step`` is what the STEP needs, or None for a model that writes none: the plan
    (:func:`_export_plan`), the record to fill, the sidecar payload, the document pair
    expected on disk, the build's live shapes (``live``) and the publish rule to ask
    again (``still_saves``). The document entry a written file gets names the producer
    the export wrote with.
    """

    def __init__(self, spec: EntrySpec, tree: str, *, logger: CliLogger, step: dict | None = None,
                 display: bool = False, announce: str | None = None) -> None:
        from contextlib import ExitStack

        from cadgen._internal import build_timing
        from cadgen.authoring import current_run

        run = current_run()
        if run is None:
            raise RuntimeError(f"{spec.cad_ref}: an export was queued outside a build run")
        self.spec, self.tree, self.logger = spec, tree, logger
        self.step, self.display, self.announce = step, display, announce
        # The clock the model's ``done`` event reads, so its ``STEP saved`` event is on it
        # too. A model restored rather than built has no build clock: its export's queueing.
        clock = build_timing.current()
        self.started = clock.started if clock is not None else time.perf_counter()
        # The summary line is the command's, in its logger's voice; the job's spans and
        # warnings are the build's (``logger``, verbose or not as the build was given it).
        self.command_logger = run.logger if run.logger is not None else logger
        self.stage = ExitStack()
        self.job: object | None = None
        if step is not None:
            step["staged"] = _stage(spec, self.stage) / spec.step_path.name
            plan: _ExportPlan = step["plan"]
            if plan.kept is None:
                self.job = _submit_export(tree, step["staged"], names=not plan.plain, live=step["live"])
        run.exports.append(self)

    def finish(self) -> None:
        """Publish what the model owes, in order (the class docstring), and say so."""
        from cadgen.daemon.telemetry import job_reused

        try:
            written = self._publish_step() if self.step is not None else False
            if self.display:
                _ensure_reused_display(self.spec, self.tree, logger=self.logger)
            written = bool(_produce_declared_mesh_exports(self.spec, logger=self.logger, source_tree=self.tree)) or written
            if self.announce:
                self.command_logger.info(self.announce)
            if written:
                job_reused(False)  # a file written now: not all of it was the store's
        finally:
            self.stage.close()

    def abandon(self) -> None:
        """Leave the file as it is: the staged copy goes, and the next run exports again."""
        self.stage.close()

    def _publish_step(self) -> bool:
        """The STEP in place from the export's answer, or kept (STORE.md §3, *Exports*; §5,
        publish order), then its verify. True when the file was written."""
        from cadgen._internal.atomic_replace import replace_atomic
        from cadgen._internal.source_sidecar import source_sidecar_path, write_source_sidecar
        from cadgen.catalog import seed_artifact_hash
        from cadgen.daemon import executors
        from cadgen.store.gate import file_stamp, remember_renamed_digest
        from cadgen.store.records import forget_output, note_document_tree, write_record

        spec, tree, logger, step = self.spec, self.tree, self.logger, self.step
        plan: _ExportPlan = step["plan"]
        record: dict = step["record"]
        staged: Path = step["staged"]
        step_path = spec.step_path.expanduser().resolve()
        model_path = _model_for_spec(spec)
        export = None
        plain = plan.plain
        if self.job is not None:
            export = self.job.result()
            for label, seconds in export["spans"]:
                logger.timing(label, seconds)
            for warning in export["warnings"]:
                logger.warning(warning)
            digest = str(export["sha256"])
            # As written, not as planned: a worker that cannot name its producer writes plain.
            plain = plain or export["producer"] is None
        else:
            digest = plan.kept_sha256
        if step["sidecar_payload"] is not None:
            write_source_sidecar(staged, step["sidecar_payload"], document_hash=digest)
        staged_sidecar = source_sidecar_path(staged)
        sidecar = _sha256_of(staged_sidecar) if staged_sidecar.is_file() else None
        expected_document_pair = step["expected_document_pair"]
        if expected_document_pair is not None:
            current = _document_pair_state(spec.step_path)
            if current != expected_document_pair and current != (digest, sidecar):
                raise RuntimeError(f"{spec.cad_ref}: result was not saved: the STEP file or its annotations changed "
                                   "during the build")
        step["still_saves"]()
        if _document_pair_state(spec.step_path)[0] != digest:
            # Separate atomic writes, not a multi-file transaction. Equal bytes stay in place,
            # with their stamp. The written copy's identity survives the rename, so its digest
            # needs no second read of the saved document.
            staged_identity = file_stamp(staged)
            replace_atomic(staged, spec.step_path)
            remember_renamed_digest(step_path, digest, staged_identity)
        _publish_sidecar(staged, spec.entry_path)
        if _document_pair_state(spec.step_path) != (digest, sidecar):
            raise RuntimeError(f"{spec.cad_ref}: saved files changed during publication; the build record was not updated")
        seed_artifact_hash(spec.step_path, digest)
        if export is not None:
            # The bytes, mapped to the tree they were written from before any parse of them:
            # pending until the verify answers.
            note_document_tree(digest, tree, producer=export["producer"], verified=False, plain=plain)
        outputs = record["outputs"]
        outputs[str(step_path)] = {**plan.output(), "sha256": digest, **({"plain": True} if plain else {})}
        sidecar_key = str(source_sidecar_path(spec.entry_path).resolve())
        if sidecar is not None:
            outputs[sidecar_key] = {"sha256": sidecar}
        else:
            outputs.pop(sidecar_key, None)
            forget_output(sidecar_key)
        write_record(model_path, record)
        saved_at = time.perf_counter() - self.started
        executors.emit_event(executors.model_event(
            model_path, "building", phase="STEP saved", elapsed=saved_at,
            saved={"output": str(step_path), "tree": tree, "documentHash": digest},
        ))
        # The build tree drops an event that follows its model's done, so a person (or a
        # benchmark) reading --verbose finds the moment here, as for any stage.
        logger.timing(f"STEP saved {step_path.name}", saved_at)
        if export is not None:
            _verify_saved(tree, step_path, digest, producer=export["producer"])
        return export is not None


def _verify_saved(tree: str, step_path: Path, digest: str, *, producer: dict | None) -> None:
    """Have the build pool verify the saved STEP against the result it was written from
    (``store/exports.py``) and hear its answer (``exports.verify_warnings``): a file that
    does not hold the result, or a verify that could not answer, is a warning. With no
    daemon the build waits for it and warns here; on the daemon the build returns first,
    the answer reaches the daemon's log, and a mismatch the next touch of the file: a door,
    ``store why``, the next run."""
    from cadgen.daemon.artifacts import submit_artifact
    from cadgen.daemon.executors import use_daemon
    from cadgen.store.exports import verify_warnings

    job = submit_artifact({"kind": "verify", "tree": tree, "document": str(step_path), "sha256": digest,
                           "producer": producer})

    def heard(done: object) -> None:
        _note_warnings(verify_warnings(done, step_path, plain=producer is None))

    if use_daemon():
        job.add_done_callback(heard)
    else:
        heard(job)


def _edge_visibility_classes_match_manifest(
    manifest: Mapping[str, object],
    selector_options: SelectorOptions,
) -> bool:
    edge_rendering = manifest.get("edgeRendering")
    if not isinstance(edge_rendering, Mapping):
        return False
    return tuple(edge_rendering.get("visibilityClasses") or ()) == tuple(selector_options.edge_visibility_classes)


def _manifest_records_edge_visibility_classes(manifest: Mapping[str, object]) -> bool:
    """Well-formedness, not agreement: does this assembly.json say what it was built with?

    Every assembly.json written by a current build does. One that does not is
    truncated or foreign, and reusing it would serve components whose edge
    classes nothing can name.
    """
    edge_rendering = manifest.get("edgeRendering")
    if not isinstance(edge_rendering, Mapping):
        return False
    return bool(edge_rendering.get("visibilityClasses"))


def _manifest_source_sidecar(manifest: Mapping[str, object]) -> Mapping[str, object]:
    sidecar = manifest.get("_sourceSidecar")
    return sidecar if isinstance(sidecar, Mapping) else {}


def _artifact_source_kind_matches_spec(spec: EntrySpec, manifest: Mapping[str, object]) -> bool:
    # The generated-marker is the PROVENANCE RECORD every generated build writes
    # (source_sidecar.py records tier): the assembly.json itself is STEP-pure and
    # carries no sourceKind. An imported spec whose bytes resolve to a generated
    # model's tree is fine — content keying already guarantees the tree IS
    # these bytes' render.
    generated = bool(_manifest_source_sidecar(manifest))
    if spec.source != "generated" and spec.step_path is not None and spec.step_path.is_file():
        return True
    expected = spec.source == "generated" and spec.script_path is not None
    return generated == expected


def _package_descriptor_matches_spec(
    spec: EntrySpec,
    selector_options: SelectorOptions | None = None,
) -> bool | None:
    """Geometry-only currency, with source provenance for explicit builds.

    The saved byte digest selects a complete native tree. Display derivatives
    do not participate. Generated builds additionally check their provenance
    and source closure; artifact readers never do. Edge visibility policy, when
    explicitly requested, remains descriptor metadata rather than a mesh job.
    """
    from cadgen.catalog import result_descriptor_for, result_snapshot_for

    if spec.source != "generated" and spec.entry_path is not None and spec.entry_path.is_file():
        # A compile's current-check is a door's: an export's pending entry, confirmed first;
        # one whose verify could not answer is compiled again from the bytes.
        from cadgen.store.exports import confirm_document

        snapshot = result_snapshot_for(spec.entry_path)
        if snapshot is None or confirm_document(spec.entry_path, *snapshot) is None:
            return False
    manifest = result_descriptor_for(spec.entry_path)
    if not isinstance(manifest, dict):
        return None
    if spec.source == "generated":
        # Only a SCRIPT run asks whether this tree is its own model's (the
        # provenance record). A document at a door asks nothing of records:
        # a tree for its bytes is its render (STORE.md §2, the law).
        from cadgen._internal.source_sidecar import read_source_provenance

        provenance = read_source_provenance(spec.entry_path)
        if provenance is not None:
            if provenance.get("kinematics"):
                from cadgen._internal.source_sidecar import source_sidecar_matches_document

                if not source_sidecar_matches_document(spec.entry_path):
                    return False
            manifest["_sourceSidecar"] = provenance
    if not _artifact_source_kind_matches_spec(spec, manifest):
        return False
    if selector_options is None:
        return _manifest_records_edge_visibility_classes(manifest)
    return _edge_visibility_classes_match_manifest(manifest, selector_options)


def _existing_topology_artifact_matches_spec_without_scene(spec: EntrySpec) -> bool:
    """True when the entry's tree is current (no scene needed).

    The assembly.json is the ONLY artifact form, so this is a thin guard
    around :func:`_package_descriptor_matches_spec` (None -> no package -> not
    current). The pre-package monolith-GLB fallback that used to live here was
    unreachable — its validator gated on ``.is_file()`` and every artifact is a
    directory — and is deleted."""
    if spec.step_path is None:
        return False
    return bool(_package_descriptor_matches_spec(spec))


def _existing_topology_artifact_matches_options(spec: EntrySpec, selector_options: SelectorOptions) -> bool:
    """As above, but against explicitly supplied selector options."""
    if spec.step_path is None:
        return False
    return bool(_package_descriptor_matches_spec(spec, selector_options))


def _source_sidecar_payload(scene: LoadedStepScene) -> dict[str, object] | None:
    """The sidecar payload for a GENERATED build, or None for an import.

    Everything source-derived lands here: provenance (the no-op gate's
    closure) and the build timestamp — the one
    volatile field, which moving here keeps the assembly.json byte-stable across
    identical rebuilds. The KINEMATICS section is injected later, once the
    staging package exists to resolve axis refs against.
    """
    from datetime import datetime, timezone

    source_kind = str(getattr(scene, "source_kind", "step") or "step").strip().lower()
    reemit_hash = str(getattr(scene, "reemit_source_hash", "") or "").strip()
    if source_kind != "python" and not reemit_hash:
        return None
    payload: dict[str, object]
    if reemit_hash:
        # `cadgen step build IN OUT`: no Python behind the document, so the
        # freshness closure is the INPUT's content hash and the annotation
        # digest. No path to anything is recorded — the pair is self-describing.
        payload = {"sourceKind": "step", "sourceHash": reemit_hash}
        annotation = str(getattr(scene, "reemit_annotation_hash", "") or "").strip()
        if annotation:
            payload["annotationHash"] = annotation
    else:
        payload = {"sourceKind": "python"}
        source_path = str(getattr(scene, "source_path", "") or "")
        if source_path:
            payload["sourcePath"] = source_path
        source_hash = str(getattr(scene, "source_hash", "") or "").strip()
        if source_hash:
            payload["sourceHash"] = source_hash
        closure_hash = str(getattr(scene, "source_closure_hash", "") or "").strip()
        closure_files = getattr(scene, "source_closure_files", ()) or ()
        if closure_hash and closure_files:
            payload["sourceClosureHash"] = closure_hash
            from cadgen.store.closure import source_files

            payload["sourceClosureFiles"] = source_files(closure_files)
    payload["generatedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return payload


def _generate_part_outputs(
    spec: EntrySpec,
    *,
    preloaded_scene: LoadedStepScene | None = None,
    require_step_file: bool = True,
    force: bool = False,
    logger: CliLogger | None = None,
    progress: object | None = None,
    expected_document_pair: tuple[str | None, str | None] | None = None,
) -> GeneratedStepResult:
    logger = logger or CliLogger("cad")
    progress = resolve_progress(progress)
    if spec.step_path is None:
        return GeneratedStepResult(spec=spec, scene=None)
    if expected_document_pair is None and spec.source == "generated":
        expected_document_pair = _document_pair_state(spec.step_path)
    if require_step_file:
        _ensure_step_ready(spec.step_path)
    if preloaded_scene is not None:
        if preloaded_scene.step_path != spec.step_path.expanduser().resolve():
            raise RuntimeError(
                f"Preloaded STEP scene path {preloaded_scene.step_path} does not match {_display_path(spec.step_path)}"
            )

    if (
        preloaded_scene is None
        and spec.source != "generated"
        and not force
        and _existing_topology_artifact_matches_spec_without_scene(spec)
    ):
        logger.debug(f"reused current tree: {_display_path(spec.step_path)}")
        from cadgen.catalog import result_tree_for

        return GeneratedStepResult(spec=spec, scene=None, tree=result_tree_for(spec.step_path))

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
    # Raw document compilation publishes the byte-derived canonical tree,
    # whose edge classes are fixed by build_document_tree. Re-emits and
    # Python-backed scenes are walked as compounds, whose trees classify their
    # own edges from the topology they are built from.
    raw_document = (
        spec.source != "generated"
        and str(getattr(scene, "source_kind", "step") or "step").strip().lower() != "python"
        and not str(getattr(scene, "reemit_source_hash", "") or "").strip()
    )
    selector_options = _selector_options_for_part(spec)
    if (
        spec.source != "generated"
        and not force
        and _existing_topology_artifact_matches_options(spec, selector_options)
        and _generated_assembly_glb_closure_current(spec)
    ):
        logger.debug(f"reused current tree: {_display_path(spec.step_path)}")
        from cadgen.catalog import result_tree_for

        return GeneratedStepResult(spec=spec, scene=scene, tree=result_tree_for(spec.step_path))

    jobs: list[_ArtifactJob] = []

    artifact_results: dict[str, object] = {}
    # The build pool's job deriving this build's parts (``_request_display``), running while
    # the build saves its STEP; waited for before the build reports done.
    display_jobs: list = []

    # UNIFIED render artifact: every model — part or assembly, generated or imported — is
    # a TREE (a store object keyed by content hash: assembly.json plus content-addressed
    # components). Packaging follows the shape itself: a Compound placing children
    # becomes occurrences (links where a child is an intact model result); anything
    # else is one component. No declaration steers it and nothing is inferred from
    # source — the tree's entryKind is read off the tree once built.
    source_compound = getattr(scene, "source_compound", None)

    def component_package_job() -> dict[str, object]:
        from pathlib import Path

        shape = source_compound
        if shape is None and not raw_document:
            # Generated/re-emitted scenes without an authored compound need
            # this wrapper. Raw documents go directly to build_document_tree;
            # constructing the same hierarchy here would be discarded.
            from cadgen._internal.step_scene_mesh import scene_to_build123d_compound

            shape = scene_to_build123d_compound(scene)
        from cadgen._internal.source_sidecar import remove_source_sidecar
        from cadgen.store.build import build_tree_from_compound
        from cadgen.store.records import read_record, write_record

        with logger.timed("tree: sidecar payload"):
            sidecar_payload = _source_sidecar_payload(scene)
        generated = sidecar_payload is not None

        from cadgen.daemon import executors
        from cadgen.store.parts import producer_identity

        # The worker can attest its actual display producer without deriving
        # display data. Unknown display capability never prevents native publication.
        try:
            producer = producer_identity()
        except ValueError:
            producer = None

        def tree_kinematics(result_hash: str, display=None):
            declaration = getattr(scene, "kinematics", None)
            if not declaration:
                return None
            from cadgen._internal.kinematics_resolve import resolve_kinematics_block

            # Mates resolve against the result's occurrences and labels; only an
            # axis ref reads a component's topology, and only its own: once ``display``,
            # the job deriving this build's parts, is done.
            with logger.timed("tree: kinematics"):
                resolved, _ = resolve_kinematics_block(
                    declaration, tree_hash=result_hash, source_ref=str(spec.source_ref),
                    producer=producer, ready=display.settle if display is not None else None,
                )
            return resolved

        # What the preview resolved against the result tree; the sidecar carries the same.
        resolved: dict[str, object] = {}

        def publish_preview(result_hash: str, result_tree: dict):
            """The preview revision (STORE.md §9b), the moment the result exists: its tree and
            parts announced, the parts the store lacks derived by the build pool meanwhile,
            then its annotations as one object. The role, output path and progress belong to
            this request, never in the content-addressed tree or the saved document's index:
            a build's status names objects, and its readers take neither geometry nor
            annotations from it."""
            from cadgen._internal.preview_revision import annotations_object
            from cadgen.store.parts import part_keys, stored_keys

            if spec.source == "generated":
                executors.emit_source_result(_model_for_spec(spec), result_hash)
            output = str(spec.step_path.expanduser().resolve())
            announce = writes_step and executors.sink_installed()
            keys, selected, stored = {}, None, {}
            # The display job announces its parts from the thread that finishes it.
            announcing = threading.Lock()

            def preview_event(*, phase: str | None = None) -> None:
                if not announce:
                    return
                with announcing:
                    stored.update(stored_keys(keys))
                    executors.emit_event(executors.model_event(
                        _model_for_spec(spec), "building", phase=phase,
                        preview={"output": output, "tree": result_hash, "producer": selected,
                                 "parts": dict(stored), "complete": bool(keys) and len(stored) == len(keys)}))

            display = None
            if producer is not None:
                # The parts the store holds first, so a viewer draws them at once; this
                # build's own others the moment the pool's one job for them is done. A
                # child's parts are its own build's.
                keys, selected = part_keys(result_hash, producer=producer)
                preview_event()
                display = _request_display(result_hash, producer=producer,
                                           cids=list(result_tree.get("components") or {}))
                if display is not None:
                    display_jobs.append(display)
                    display.when_done(lambda _job: preview_event())
            else:
                # No display producer here: the parts are a view's to find, as for a saved file.
                preview_event()
            preview_event(phase="Saving STEP" if writes_step else None)
            # The declarations, resolved against the result tree: for the sidecar below,
            # and for the preview as the one annotations object a viewer binds to. An axis
            # ref reads its component's selector table once the display job is done. The
            # clips are baked once: the file is written from this tree, so its sidecar
            # carries these very keyframes.
            resolved["kinematics"] = tree_kinematics(result_hash, display=display)
            clips = getattr(scene, "animation", None)
            if writes_step and clips is not None:
                from cadgen._internal.animation_bake import bake_document_animation

                resolved["animation"] = bake_document_animation(clips, result_hash)
            if announce:
                annotations = annotations_object(
                    result_hash, kinematics=resolved["kinematics"],
                    appearance=result_tree.get("appearance"), animation=resolved.get("animation"))
                if annotations is not None:
                    executors.emit_event(executors.model_event(
                        _model_for_spec(spec), "building",
                        annotations={"output": output, "tree": result_hash, "object": annotations}))
        # Objects first: components + tree. Harmless if this build ends up not
        # publishing its record (publish rule below) — content-addressed and GC'd.
        writes_step = generated and bool(spec.step_output)
        # The model's run, which names each component it made by its construction key
        # and its lineage (README law 20); a document compiled from its bytes has none.
        kernel_run = getattr(scene, "kernel_run", None) if generated else None
        namer = kernel_run
        # The build's own live shapes for the components the store cannot decode, which
        # its STEP is written from in this process (store/exports.py).
        live: dict[str, object] = {}
        with logger.timed("tree: components"):
            if not generated:
                from cadgen.store.build import build_document_tree

                tree_hash, tree, stats = build_document_tree(scene, force=force, progress=progress)
            else:
                tree_hash, tree, stats = build_tree_from_compound(
                    shape, root_name=_document_root_name(shape, spec.step_path), force=force,
                    progress=progress, materials=getattr(scene, "materials", None), namer=namer, live=live,
                )
                # The preview, before any export work: the result is what the file is
                # written from.
                publish_preview(tree_hash, tree)
        stats["tree"] = tree_hash
        if producer is not None and not generated:
            # A document compiled from its bytes: every part of it, before its tree is
            # mapped to them, so a view only reads.
            _await_display(_request_display(tree_hash, producer=producer), progress=progress, logger=logger)
        # The build's account of its code (STORE.md §3): the features its run called,
        # where each ran, the components it made, each with the feature every name of
        # its lineage stands for, and each occurrence of one with the feature whose call
        # made the shape it places; written beside the record, after it, for a model
        # whose saved document `store where` can be asked about.
        provenance = None
        if kernel_run is not None and writes_step:
            provenance = {"features": kernel_run.trace.feature_rows(), **stats["account"]}

        model_path = _model_for_spec(spec)
        outputs: dict[str, object] = {}
        step_key = str(spec.step_path.expanduser().resolve())
        from cadgen._internal.source_sidecar import source_sidecar_path

        sidecar_key = str(source_sidecar_path(spec.entry_path).resolve())
        previous = (read_record(model_path) or {}) if generated else {}
        export_plan = _export_plan(previous, step_key, tree_hash, force=force,
                                   on_disk=(expected_document_pair or (None, None))[0]) if writes_step else None
        if writes_step:
            # The record is written at the source result, its STEP pending until the
            # export lands (an empty sha256 the gate reads as never written).
            outputs[step_key] = export_plan.output()
        # An imported document and anything beside it are authored inputs. Cache
        # publication must not add, rewrite, or remove either one.

        # The record. Publish rule: never replace a current record with a stale one.
        closure_hash = str(getattr(scene, "source_closure_hash", "") or "")
        closure_files = list(getattr(scene, "source_closure_files", ()) or ())
        closure_shas = dict(getattr(scene, "source_closure_file_hashes", None) or {})
        closure_names = {rel: list(names) for rel, names in (getattr(scene, "source_closure_names", None) or {}).items()}
        closure_wholes = dict(getattr(scene, "source_closure_wholes", None) or {})
        closure_own = {rel: list(names) for rel, names in (getattr(scene, "source_closure_own", None) or {}).items()}
        closure_static = False
        reemit_source_hash = getattr(scene, "reemit_source_hash", None)
        if not generated:
            # An imported document's closure is the document itself.
            from cadgen.store.closure import closure_hash as _closure_hash

            step_hash = str(getattr(scene, "step_hash", "") or "") or step_file_hash(spec.step_path)
            closure_files = [spec.step_path.name]
            closure_shas = {spec.step_path.name: step_hash}
            closure_names, closure_wholes, closure_own = {}, {}, {}
            closure_hash = _closure_hash([(spec.step_path.name, step_hash)])
        elif reemit_source_hash and not closure_hash:
            # A re-emitted document (`cadgen step build IN OUT`): its source is
            # another document's bytes plus the author's annotation, both compared
            # by that door — no files for the gate to re-hash.
            from cadgen.store.closure import closure_hash as _closure_hash

            closure_files = []
            closure_names, closure_wholes, closure_own = {}, {}, {}
            closure_hash = _closure_hash(
                [("reemit", str(reemit_source_hash)), ("annotation", str(getattr(scene, "reemit_annotation_hash", "") or ""))]
            )
            closure_static = True
        # Declared mesh exports recorded by earlier runs stay listed: each one
        # carries the document hash it was cut from, so the mesh gate re-checks
        # it against THIS document and re-exports only what no longer matches.
        # A foreign compile derives its result from document bytes alone.
        # Only generated jobs retain declarations from an earlier model run.
        for output_path, entry in (previous.get("outputs") or {}).items():
            if isinstance(entry, dict) and entry.get("declared") and output_path not in outputs:
                outputs[output_path] = entry
        # Every declared mesh output is listed from the first publish, sha-less
        # until its export writes it (record_mesh_export fills the entry), so a
        # declaration the exporter failed to honour reads as STALE at the next
        # gate ("never written") instead of as a current model missing an output.
        if generated:
            for declared in spec.mesh_exports or ():
                key = str(Path(declared.path).expanduser().resolve())
                outputs.setdefault(key, {"sha256": "", "declared": declared.fmt})
        from cadgen.store.trees import tree_kind

        record = {
            "entryKind": tree_kind(tree),
            "sourceKind": "step" if (not generated or reemit_source_hash) else "python",
            "tree": tree_hash,
            "unannotatedTree": str(stats.get("unannotatedTree") or tree_hash),
            "closure": {"hash": closure_hash, "files": closure_files, "shas": closure_shas, "names": closure_names,
                        "wholes": closure_wholes, "own": closure_own, "static": closure_static},
            # Literals imported from model files, tracked by VALUE (gate clause 2).
            "constants": dict(getattr(scene, "source_closure_constants", None) or {}) if generated else {},
            # Every child the body called, by the key it composed (store/results.py).
            "children": _children_by_key(getattr(scene, "store_children", None)),
            "outputs": outputs,
        }
        from cadgen.store.results import producer_versions
        from cadgen.store.trees import get_tree

        record["producer"] = producer_versions()

        unannotated = get_tree(str(record["unannotatedTree"]))
        intrinsic_appearance = (unannotated or {}).get("appearance")
        if intrinsic_appearance is not None:
            record["intrinsicAppearance"] = copy.deepcopy(intrinsic_appearance)
        if reemit_source_hash:
            record["sourceHash"] = str(reemit_source_hash)
            record["annotationHash"] = str(getattr(scene, "reemit_annotation_hash", "") or "")
            record["inputAppearance"] = str(getattr(scene, "reemit_appearance_hash", "") or "")
        if generated:
            kinematics_block = getattr(scene, "kinematics", None)
            if kinematics_block:
                # Bound to the result's tokens, which the file's are.
                sidecar_payload["kinematics"] = (
                    resolved["kinematics"] if "kinematics" in resolved else tree_kinematics(tree_hash))
            if writes_step:
                appearance = tree.get("appearance")
                if appearance is not None:
                    sidecar_payload["appearance"] = appearance
                if resolved.get("animation") is not None:
                    sidecar_payload["animation"] = resolved["animation"]
            if sidecar_payload is not None and sidecar_payload.get("kinematics") is not None:
                record["kinematics"] = sidecar_payload.get("kinematics")
            if getattr(scene, "materials", None) is not None:
                record["materials"] = copy.deepcopy(scene.materials)
            if sidecar_payload is not None and sidecar_payload.get("animation") is not None:
                # The keyframes, not the clips: an annotation refresh rewrites the
                # sidecar from the record without running the model.
                record["animation"] = sidecar_payload["animation"]
            if sidecar_payload is not None and sidecar_payload.get("appearance") is not None:
                record["appearance"] = copy.deepcopy(sidecar_payload["appearance"])
            if writes_step:
                from cadgen._internal.source_sidecar import sidecar_is_warranted, sidecar_sections

                # A sidecar this build will write is pending with the STEP until the export
                # lands; a missing one is then a run's to write again (gate clause 5). A
                # model that declares nothing lists none.
                if sidecar_is_warranted(sidecar_sections(sidecar_payload)):
                    outputs[sidecar_key] = {"sha256": ""}
        if record["sourceKind"] == "python" and spec.script_path is not None:
            from cadgen._internal.annotation_refresh import capture_geometry_closure

            entry_name = getattr(spec.generator_metadata, "entry_function", None)
            if entry_name:
                geometry_closure = capture_geometry_closure(
                    spec.script_path, record["closure"], entry_name=entry_name
                )
                if geometry_closure is not None:
                    record["geometryClosure"] = geometry_closure
        if generated:
            from cadgen._internal.build_timing import record_fields
            from cadgen.store.trees import claim_tree

            # The model-code time the next build compares itself against.
            record.update(record_fields())

            # Claimed, not just checked: the record below names this closure, so no
            # sweep may take any part of it from here on (STORE.md §8).
            if not claim_tree(tree_hash):
                raise RuntimeError(f"{spec.cad_ref}: result was not saved: the result's geometry disappeared from the cache during the build")
            # A re-emitted STEP has an immutable byte/annotation input closure,
            # not a Python source closure that current_closure_hash can read
            # (still_saves below).
        def still_saves() -> None:
            """The publish rule (``store.publish.decide``), asked again before the saved
            STEP replaces the record's pending one: a newer build of the model may have
            published since."""
            if not generated or closure_static:
                return
            from cadgen.store.publish import decide

            decision = decide(model_path, ran_closure_hash=closure_hash, ran_files=closure_files, ran_names=closure_names,
                              ran_shas=closure_shas, ran_wholes=closure_wholes, ran_own=closure_own)
            if not decision.publish_outputs:
                raise RuntimeError(f"{spec.cad_ref}: result was not saved: {decision.reason}")

        if generated:
            still_saves()
        from cadgen.store.records import note_document_tree, note_output

        if not generated:
            # Artifact side: the bytes of the document this tree describes → the tree
            # (a reader's one lookup; STORE.md §2).
            note_document_tree(step_hash, tree_hash, producer=producer)
        if generated:
            if not writes_step:
                # Mesh-only models have no STEP or kinematics sidecar.
                remove_source_sidecar(spec.entry_path)
            # Code side: which model writes each output path (the badge's question,
            # never a reader's).
            for output_path in outputs:
                note_output(output_path, model_path)
        # Keyed, and stored under its key, as it is written (store/results.py): what
        # a later build of these inputs restores.
        key = write_record(model_path, record)
        if provenance is not None:
            from cadgen.store.provenance import write_provenance

            # Beside the record and after it: code side, read by `store where`
            # and by nothing on a render path; kept with the result.
            write_provenance(model_path, provenance, tree=tree_hash)
        if kernel_run is not None:
            # The run's trace was this job's: nothing after it reads the run.
            scene.kernel_run = None
        if generated:
            # What the build still owes, queued: its STEP's export job starts now and the
            # file is published, verified and its meshes cut when the run finishes its
            # exports (_Export) -- after this build's done, while a parent's body goes on.
            kept = writes_step and export_plan.kept is not None
            summary = (f"kept STEP: {_display_path(spec.step_path)} (its bytes would not change)" if kept
                       else _generated_python_glb_summary(spec))
            _Export(spec, tree_hash, logger=logger, announce=None if reemit_source_hash else summary,
                    step={"plan": export_plan, "record": record, "sidecar_payload": sidecar_payload,
                          "expected_document_pair": expected_document_pair, "live": live,
                          "still_saves": still_saves} if writes_step else None)
        # Every part of the result is stored before the build reports done (the pool's
        # job for them runs while the record is written), so a view of what it built only
        # reads.
        while display_jobs:
            _await_display(display_jobs.pop(0), progress=progress, logger=logger)
        stats["published"] = True
        stats["key"] = key
        return stats

    jobs.append(_ArtifactJob("tree", component_package_job))

    try:
        artifact_results.update(_run_artifact_jobs(jobs, logger=logger))
    except Exception:
        # A build that failed after its preview leaves the preview standing under the
        # failure, its parts announced as the pool derives them.
        for display in display_jobs:
            display.settle()
        raise
    except BaseException:
        for display in display_jobs:
            display.abandon()
        raise
    tree_result = artifact_results.get("tree") or {}
    return GeneratedStepResult(spec=spec, scene=scene, tree=str(tree_result.get("tree") or "") or None,
                               key=tree_result.get("key"))


def _children_by_key(called: object) -> list[dict[str, str]]:
    """The record's ``children``: each model the body called, once, by the key of the
    result the call composed (``cadgen.authoring``), in the order first called."""
    children: dict[str, str] = {}
    for child in called or ():
        model, key = str((child or {}).get("model") or ""), str((child or {}).get("key") or "")
        if model and model not in children:
            children[model] = key
    return [{"model": model, "key": key} for model, key in children.items()]


def _generate_step_outputs(
    spec: EntrySpec,
    *,
    generator: Callable[[], object] | None = None,
    force: bool = False,
    logger: CliLogger | None = None,
    progress: object | None = None,
    verdict: object | None = None,
) -> GeneratedStepResult:
    """``verdict`` is the gate's verdict this job already took for ``spec``
    (:func:`build_model`); without one the gate is asked here. ``generator`` is
    the model's function when its module is loaded already (a child), else None
    (``run_script_generator``)."""
    preloaded_scene: LoadedStepScene | None = None
    if not force and spec.source == "generated" and verdict is None:
        verdict = _gate_verdict(spec)
    if not force and spec.source == "generated":
        from cadgen._internal.annotation_refresh import refresh_annotations

        refreshed_tree = refresh_annotations(spec, verdict=verdict)
        if refreshed_tree is not None:
            from cadgen.store.records import read_record

            _hit(spec, refreshed_tree, logger=logger or CliLogger("cadgen"), verdict=verdict)
            refreshed = read_record(_model_for_spec(spec)) or {}  # the record the refresh just wrote
            return GeneratedStepResult(spec=spec, scene=None, tree=refreshed_tree, key=refreshed.get("key"))
    reuse_tree = _checked_source_tree(spec, verdict) if not force else None
    # Reuse fast path: skip the build when the tree is already present and
    # current and nothing forces a run. A generated model's freshness rides on its recorded
    # source closure; an imported/committed STEP's freshness rides on the STEP hash recorded in
    # the tree (verified inside the artifact-matches gate), so it needs no closure check.
    # A stale verdict settles it before the descriptor check, which hashes the saved
    # document (and, for a model with kinematics, its sidecar's binding to it).
    if not force and (
        (reuse_tree is not None and _existing_topology_artifact_matches_spec_without_scene(spec))
        if spec.source == "generated"
        else (_existing_topology_artifact_matches_spec_without_scene(spec) and _assembly_glb_package_current(spec))
    ):
        if logger is not None:
            logger.debug(f"reused current tree: {_display_path(spec.step_path)}")
        if spec.source == "generated":
            # A peer published the model while this run waited for its slot: what it may
            # still owe is queued as for any current model.
            _hit(spec, reuse_tree, logger=logger or CliLogger("cadgen"), verdict=verdict)
        else:
            from cadgen.catalog import result_tree_for

            reuse_tree = result_tree_for(spec.step_path)
            _ensure_reused_display(spec, reuse_tree, progress=progress, logger=logger)
        return GeneratedStepResult(spec=spec, scene=None, tree=reuse_tree,
                                   key=verdict.key if verdict is not None else None)
    output_kwargs: dict[str, object] = {
        "force": force,
        "progress": progress,
    }
    if logger is not None:
        output_kwargs["logger"] = logger
    if spec.source == "generated":
        if spec.step_path is not None:
            output_kwargs["expected_document_pair"] = _document_pair_state(spec.step_path)
        preloaded_scene = run_script_generator(
            spec,
            "step",
            generator=generator,
            logger=logger,
            force=force,
            progress=progress,
            # The direct build flow: the model's own prints are the user's
            # stdout channel here (and pinned by test).
            model_prints_to_stdout=True,
        )
        output_kwargs["preloaded_scene"] = preloaded_scene
        # A @step entry never writes a STEP, so the artifact pipeline must not require one.
        output_kwargs["require_step_file"] = False
    else:
        # Imported/committed STEP target (kind supplied by the caller or inferred upstream):
        # _generate_part_outputs loads + meshes the on-disk STEP and emits the same flat
        # tree. Without this branch the function fell off the end and silently
        # returned None — no package written — while the CLI still reported success.
        output_kwargs["require_step_file"] = True
    return _generate_part_outputs(spec, **output_kwargs)


def _request_display(tree: str, *, producer: dict | None = None, cids: list[str] | None = None):
    """The build pool's job deriving the display data -- each part's mesh and selector
    table -- of every part of ``tree`` the store lacks (``store.parts.request_display``):
    submitted the moment the build's result exists, it runs while the build saves its
    STEP, on the pool, never on the build's thread, and the build waits for it before it
    reports done
    (:func:`_await_display`), so its preview and every view of what it built only read.
    ``cids`` restricts it to the build's own components: the parts of a child the build
    composed are there already, the child's build having had them derived before it
    reported done. None when nothing is missing, or when the job could not be asked for
    (a warning: the first view derives the parts)."""
    if not tree:
        return None
    from cadgen.store.parts import request_display

    try:
        return request_display(tree, producer=producer, cids=cids)
    except Exception as error:  # noqa: BLE001 - the build's result stands; its display data waits for a view
        _note_warnings([f"display data not derived ({type(error).__name__}: {error}); the first view derives it"])
        return None


def _await_display(job, *, progress: object | None = None, logger: CliLogger | None = None) -> None:
    """Wait for the display ``job`` (:func:`_request_display`), when there is one. A part it
    could not derive is a warning on the build, never its failure: a view, a snapshot and
    a list leave that part out and name it."""
    if job is None:
        return
    from contextlib import nullcontext

    progress = resolve_progress(progress)
    progress.phase(PHASE_MESH, total=len(job.keys))
    try:
        with logger.timed("display data") if logger is not None else nullcontext():
            texts = [f"{failure}; views leave it out" for failure in job.wait()]
    except Exception as error:  # noqa: BLE001 - the build's result stands; its display data waits for a view
        texts = [f"display data not derived ({type(error).__name__}: {error}); the first view derives it"]
    progress.advance(len(job.keys))
    _note_warnings(texts)


def _note_warnings(texts: list[str]) -> None:
    from cadgen._internal.build_timing import note_warning

    for text in texts:
        # On the done event, which reaches the root from a child whose own output is
        # dropped; outside a build, stderr (stdout is the result channel).
        if not note_warning(text):
            print(f"[cadgen] warning: {text}", file=sys.stderr)


def _ensure_reused_display(spec: EntrySpec, tree: str | None, *, progress: object | None = None,
                           logger: CliLogger | None = None) -> None:
    """The display data of a build that reuses its tree, derived by the pool where the store
    lacks it (:func:`_request_display`) before the command returns (``_Export``): the tree
    its saved document selects, under the producer that document names -- what a view of
    it reads -- or a mesh-only model's own tree."""
    producer = None
    if spec.step_output and spec.entry_path is not None:
        from cadgen.catalog import result_snapshot_for
        from cadgen.store.records import document_entry_for_hash

        snapshot = result_snapshot_for(spec.entry_path)
        if snapshot is None:
            return
        document_hash, tree = snapshot
        producer = _reused_display_producer(document_hash, tree, document_entry_for_hash(document_hash) or {})
    _await_display(_request_display(tree or "", producer=producer), progress=progress, logger=logger)


def _reused_display_producer(document_hash: str, tree: str, entry: Mapping[str, object]) -> object:
    """The producer a reused build derives its document's display data under.

    The document ``entry``'s hint while this runtime implements it, or while the store
    holds every part under it (a view reads those). Otherwise -- the kernel was upgraded,
    or another cadgen wrote the hint -- this runtime's, and the document is re-attested
    with it, keeping what else the entry says (whether its verify is pending, what
    differs), so neither this build nor a view asks again for parts no worker can make.
    Re-attesting is best effort: a store this process cannot write keeps the hint it has."""
    import contextlib

    from cadgen.store import parts

    hint = entry.get("producer")
    try:
        current = parts.producer_identity()
        hinted = parts.producer_fields(hint) if hint is not None else None
    except (ValueError, TypeError):
        return hint
    if hinted is None or hinted == current or parts.all_stored(tree, hinted):
        return hint
    from cadgen.store.paths import StoreUnwritableError
    from cadgen.store.records import note_document_tree

    with contextlib.suppress(OSError, StoreUnwritableError):
        note_document_tree(document_hash, tree, kind=str(entry.get("kind") or "step"), producer=current,
                           verified=entry.get("verified") is not False, plain=bool(entry.get("plain")),
                           differ=entry.get("differ"))
    return current


def _produce_declared_mesh_exports(
    spec: EntrySpec, *, logger: CliLogger | None, source_tree: str | None = None
) -> "tuple[Path, ...]":
    """Produce the model's declared ``@stl``/``@glb``/``@threemf`` outputs and
    RETURN the ones this call actually wrote (outputs the ledger already found
    current are not listed).

    Runs through the ONE mesh engine the `cadgen stl|3mf|glb build` doors use — same
    meshes, same writers, same records — so the two front doors cannot drift. Each
    output is gated by its content-keyed record (document hash + the tolerance
    pair the file on disk was ACTUALLY written at): current outputs cost a stat +
    record read; stale or missing ones are written from the store's meshes.
    Content-gated deliberately even under --force: a byte-identical rebuild
    leaves exports byte-identical by determinism, so rewriting them is pure waste.

    A declaration's own tolerances are the only ones: one that names none is
    written at the display tolerance, from the very meshes the viewer draws.

    A STEP model's meshes are keyed on its STEP's bytes as its record names them -- the
    build's own knowledge of the file it just wrote, or its current record's -- and cut
    from the tree those bytes map to (`index/document`): the result they were written
    from, pending their verify, or, after a verify found the file its own content or an
    annotation refresh re-keyed the record, the tree the entry names, which the bare mesh
    doors cut from too. No door's lookup of the file, so no wait on its verify (STORE.md
    §3, *Exports*). A mesh-only model writes no document: its result, ``source_tree``
    (else its record's), IS the geometry the meshes are cut from, so the ledger keys on
    that.
    """
    if not spec.mesh_exports or spec.entry_path is None or spec.step_path is None:
        return ()
    from cadgen._internal.mesh_export import (
        MeshExportJob,
        MeshSource,
        mesh_export_current,
        record_mesh_export,
        run_mesh_exporter,
    )
    from cadgen.store.records import read_record, tree_for_document_hash

    model = _model_for_spec(spec)
    record = (read_record(model) if model is not None else None) or {}
    if spec.step_output:
        output = (record.get("outputs") or {}).get(str(spec.step_path.expanduser().resolve())) or {}
        document_hash = str(output.get("sha256") or "") or None
        tree_hash = tree_for_document_hash(document_hash) if document_hash else None
    else:
        tree_hash = source_tree or str(record.get("tree") or "") or None
        document_hash = tree_hash
    if document_hash is None or tree_hash is None or model is None:
        return ()
    from cadgen._internal.source_sidecar import appearance_digest, read_source_sidecar

    sidecar = read_source_sidecar(spec.entry_path, document_hash=document_hash) if spec.step_output else None
    appearance = (sidecar or {}).get("appearance")
    appearance_key = appearance_digest(appearance)
    pending: list[MeshExportJob] = []
    for declared in spec.mesh_exports:
        if mesh_export_current(
            declared.path,
            model=model,
            document_hash=document_hash,
            mesh_tolerance=declared.mesh_tolerance,
            mesh_angular_tolerance=declared.mesh_angular_tolerance,
            appearance_key=appearance_key,
        ):
            continue
        declared.path.parent.mkdir(parents=True, exist_ok=True)
        pending.append(
            MeshExportJob(
                fmt=declared.fmt,
                out=declared.path,
                mesh_tolerance=declared.mesh_tolerance,
                mesh_angular_tolerance=declared.mesh_angular_tolerance,
            )
        )
    if not pending:
        return ()
    jobs = list(pending)
    exported = run_mesh_exporter(
        # A mesh-only model's tree is its own geometry, selected by no document.
        MeshSource(tree_hash, document_hash if spec.step_output else None),
        jobs,
        name=spec.step_path.stem,
        logger=logger if logger is not None else CliLogger("cadgen", verbose=False),
        appearance=appearance,
    )
    for job in jobs:
        record_mesh_export(
            job.out,
            model=model,
            document_hash=document_hash,
            fmt=job.fmt,
            mesh_tolerance=job.mesh_tolerance,
            mesh_angular_tolerance=job.mesh_angular_tolerance,
            appearance_key=appearance_key,
        )
        # stderr: stdout is the result channel (`outcome document`), and a
        # `[cadgen]`-prefixed line is the logger's voice, not a result.
        print(f"[cadgen] wrote {job.fmt.upper()}: {_display_path(job.out)}", file=sys.stderr)
    for entry in exported.get("files") or []:
        # A file open where no mesher could cover a face says so beside the line that wrote it.
        for warning in (entry or {}).get("warnings") or ():
            print(f"[cadgen] warning: {warning}", file=sys.stderr)
    return tuple(job.out for job in jobs)


def _selected_specs_for_targets(targets: Sequence[str]) -> tuple[list[EntrySpec], list[EntrySpec]]:
    """``(all specs the targets reach, the targets' own specs)``. A target is a
    model script or a document — its outputs are what it declares (``out=``);
    nothing on the command line renames them."""
    explicit_specs: list[EntrySpec] = []
    unresolved_targets: list[str] = []
    from cadgen.store.index import MODEL_REF_SEP

    for target in targets:
        target_text = str(target or "").strip()
        # ``script.py::fn`` names one model of a file holding several.
        function: str | None = None
        if MODEL_REF_SEP in target_text:
            target_text, _, function = target_text.rpartition(MODEL_REF_SEP)
        target_path = Path(target_text)
        resolved = target_path.resolve() if target_path.is_absolute() else (Path.cwd() / target_path).resolve()
        source = (
            source_from_path(resolved, function=function or None)
            if resolved.exists()
            else None
        )
        if source is None:
            unresolved_targets.append(target_text)
            continue
        explicit_specs.append(_entry_spec_from_source(source))

    if not unresolved_targets:
        return list(explicit_specs), explicit_specs

    unresolved = ", ".join(unresolved_targets)
    raise FileNotFoundError(
        f"not a model script cadgen can build: {unresolved}. A model is a Python script that "
        "decorates a function with @step, @dxf or a mesh decorator (@stl/@glb/@threemf); "
        "run it with `python <model>.py`."
    )


def _validate_step_target(spec: EntrySpec, *, tool_name: str) -> None:
    if spec.step_path is None:
        raise ValueError(f"{tool_name} target has no STEP path: {spec.source_ref}")
    if spec.source == "generated":
        metadata = spec.generator_metadata
        if metadata is None or metadata.format != "step":
            raise ValueError(f"{tool_name} target is not a @step model: {spec.source_ref}")
        return
    raise ValueError(
        f"{tool_name} builds model scripts only: {spec.source_ref} is a document. A STEP/STP "
        "file needs no build -- every command that reads one (snapshot, the mesh doors, the "
        "CAD Viewer) compiles its tree on demand; `cadgen step build IN OUT` re-emits one."
    )


def _validate_dxf_target(spec: EntrySpec) -> None:
    metadata = spec.generator_metadata
    if spec.source != "generated" or spec.script_path is None or metadata is None:
        raise ValueError(f"dxf expected a generated Python source target: {spec.source_ref}")
    if metadata.format != "dxf":
        raise ValueError(f"dxf target is not a @dxf model: {spec.source_ref}")
    if spec.dxf_path is None:
        raise ValueError(f"dxf target has no configured DXF output: {spec.source_ref}")


def _generated_python_glb_summary(spec: EntrySpec) -> str:
    if spec.step_path is not None and not getattr(spec, "step_output", True):
        # A mesh-only model: step_path is the logical document the store keys by,
        # never a file it wrote. Each mesh was already named by the line that
        # wrote it (`wrote STL: …`), so the summary names the model once.
        count = len(spec.mesh_exports or ())
        return f"built {spec.source_ref} ({count} mesh output{'s' if count != 1 else ''})"
    if spec.step_path is not None:
        return f"wrote STEP: {_display_path(spec.step_path)}"
    return f"processed: {spec.source_ref}"


def _generated_dxf_summary(spec: EntrySpec) -> str:
    output = spec.dxf_path
    if output is not None:
        return f"wrote DXF: {_display_path(output)}"
    return f"processed: {spec.source_ref}"


def _tree_event(spec: EntrySpec, state: str, **extra: object) -> None:
    """One model transition for the build tree (cadgen.cli_tree), with the model whose
    body called this one as its ``parent``. Generated models only: an imported document
    has no body and no children to show."""
    model = _model_for_spec(spec)
    if model is None:
        return
    from cadgen.daemon.executors import emit_event, model_event

    emit_event(model_event(model, state, parent=_event_parent(model), **extra))


def _event_parent(model: str) -> str | None:
    """The model whose body called ``model``, for its events: the body in flight on this
    thread (a child's build runs inside its caller's body), or, while ``model``'s own
    body runs, the frame it was entered from. None for the root."""
    from cadgen.authoring import current_frame

    frame = current_frame()
    if frame is None or frame.model is None:
        return None
    return frame.parent if frame.model == model else frame.model


def _current_source_result(spec: EntrySpec, tree: str | None) -> None:
    """Capture the current source result now; consumers never reread the record."""
    if spec.source != "generated" or spec.dxf_path is not None:
        return
    from cadgen.daemon.executors import emit_source_result
    model = _model_for_spec(spec)
    emit_source_result(model, tree)


def _tree_progress_sink(spec: EntrySpec, inner: object | None) -> Callable[[ProgressEvent], None]:
    """Fan a run's phase events out to the caller's sink AND the build tree."""

    def sink(event: ProgressEvent) -> None:
        if inner is not None:
            inner(event)  # type: ignore[operator]
        if event.phase == "done":
            return
        _tree_event(
            spec, "building", phase=event.label or event.phase,
            done=event.done if event.determinate else None,
            total=event.total if event.determinate else None,
            # Empty, not absent: a new phase's job must not keep the last one's detail.
            detail=event.detail or "",
        )

    return sink


class _SkippedGeneration:
    """Marker: a concurrent run ahead of us had already produced a current result."""

    __slots__ = ("spec", "tree")

    def __init__(self, spec: EntrySpec, tree: str | None = None) -> None:
        self.spec = spec
        self.tree = tree


def _run_with_spec_generation_status(
    spec: EntrySpec,
    model_format: str,
    action: Callable[..., object],
    *,
    skip_if_current: Callable[[EntrySpec], bool | str | None] | None = None,
    progress_sink: object | None = None,
    logger: CliLogger | None = None,
    on_queued: Callable[[], None] | None = None,
    profile: bool = False,
    on_timed: Callable[[dict[str, float]], None] | None = None,
) -> object:
    """Run ``action`` under the model's progress record.

    ``on_queued`` is told when the job had to wait for a slot before its body.

    The build is measured (cadgen._internal.build_timing): its ``done`` event carries
    the time split the root prints, and ``on_timed`` receives the same numbers for
    the run's result. ``profile`` profiles the model body and the ``done`` event
    carries the report, and the programs the model's code started.

    Delegates to :func:`cadgen.coordination.artifact_build`, the SAME primitive
    ``cadgen.step_artifact_cli`` uses, so every producer reports the same way.

    ``skip_if_current`` is re-evaluated when the run opens: a run that started behind a
    concurrent build of this model no-ops once that build has published.

    ``action`` is called as ``action(spec, run)``; ``run`` is the progress reporter.
    """
    del logger
    kind = DRAWING_PACKAGE if model_format == "dxf" else STEP_PACKAGE
    started = time.perf_counter()
    checked_tree = None

    def is_current():
        nonlocal checked_tree
        verdict = skip_if_current(spec)
        checked_tree = verdict if isinstance(verdict, str) else None
        return bool(verdict)

    from cadgen._internal import build_timing

    with artifact_build(
        kind,
        _spec_output_dir(spec, model_format),
        is_current=is_current if skip_if_current is not None else None,
        sink=_tree_progress_sink(spec, progress_sink),
    ) as run, build_timing.measuring(
        model_ref=_model_for_spec(spec),
        last_model_seconds=_last_model_seconds(spec),
        profile=profile,
    ) as clock:
        clock.started = started
        if run.skipped:
            if model_format == "step":
                _current_source_result(spec, checked_tree)
            _tree_event(spec, "current")
            return _SkippedGeneration(spec, checked_tree)
        from cadgen.daemon import broker

        # One running build per core: the body and its emit hold a job slot, and a
        # child's build inside the body runs in the slot its parent holds. `queued`
        # shows in the tree only when the slot did not come at once.
        def queued() -> None:
            _tree_event(spec, "queued")
            if on_queued is not None:
                on_queued()

        waiting_from = time.perf_counter()
        with broker.held(spec.source_ref, on_queued=queued):
            clock.queued = time.perf_counter() - waiting_from
            _tree_event(spec, "building", phase="generate")
            try:
                result = action(spec, run)
            except BaseException:
                _tree_event(spec, "failed", elapsed=time.perf_counter() - started)
                raise
        measured = clock.timings().payload()
        profile_report = clock.profile_report
    if on_timed is not None:
        on_timed(measured)
    timings = {
        **measured,
        "document": _timed_document(spec, model_format),
        # A profiled body is slowed by the profiler: no slowdown to compare.
        "lastModelSeconds": None if profile else clock.last_model_seconds,
    }
    # The programs its code started and its warnings ride the done event as its timings
    # do: the root's build tree prints them once per model (cadgen.cli_tree).
    _tree_event(
        spec, "done", elapsed=time.perf_counter() - started, stale=_stale_after_build(spec),
        timings=timings, profile=profile_report, started=list(clock.programs) or None,
        warnings=list(clock.warnings) or None,
    )
    return result


def _last_model_seconds(spec: EntrySpec) -> float | None:
    """The model-code time the model's record kept from its last build, if any."""
    model = _model_for_spec(spec)
    if model is None or spec.source != "generated":
        return None
    from cadgen.store.records import read_record

    try:
        value = (read_record(model) or {}).get("modelSeconds")
    except Exception:  # noqa: BLE001 - a missing comparison never fails a build
        return None
    return float(value) if isinstance(value, (int, float)) and value > 0 else None


def _timed_document(spec: EntrySpec, model_format: str) -> str | None:
    """The document a time line names: the one the run's result line names."""
    if model_format == "dxf":
        return str(spec.dxf_path.expanduser().resolve()) if spec.dxf_path is not None else None
    return _reported_document(spec)


def _document_root_name(shape: object, step_path: Path) -> str:
    """What a saved document's root is called: the label its author gave it (a
    re-emit's source document named its own root, so OUT keeps IN's name).

    Names are what an author wrote. Unlabelled, an assembly's root is ``model``,
    as a document with no root name is read: a name taken from the file
    would sit among its parts' labels and answer for one of them. An
    unlabelled single part takes its file's name, which nothing else in its
    document can share. A label the STEP round trip does not keep (a blank, a
    shape kind) is no label."""
    from cadgen._internal.step_scene_loader import _normalize_label_name
    from cadgen.store.build import compound_has_children

    authored = _normalize_label_name(getattr(shape, "label", None))
    if authored:
        return authored
    return "model" if compound_has_children(shape) else step_path.stem


def _stale_after_build(spec: EntrySpec) -> str | None:
    """The already-stale-on-completion notice: after publishing, the gate runs once
    more. A child edited during the build leaves the parent stale the moment it is done
    -- the parent built against the child it composed -- and the tree says so instead of
    letting the next run be the first to notice."""
    model = _model_for_spec(spec)
    if model is None or spec.source != "generated":
        return None
    try:
        from cadgen.store.gate import Verdict, stale

        verdict = stale(model)
    except Exception:  # noqa: BLE001 - a notice never fails a build
        return None
    # The sources: an output the run still owes (its STEP, exported once the run finishes
    # its exports) is no change.
    moved = [clause for clause in verdict.clauses if clause.get("stale") and clause.get("clause") != 5]
    if not moved:
        return None
    reason = Verdict(model=verdict.model, stale=True, clauses=moved).reason()
    return f"{reason}; changed during the build" if reason else "changed during the build"


def _reported_document(spec: EntrySpec) -> str | None:
    """The document a model run names on stdout, as an ABSOLUTE path: the STEP it
    declares, or -- for a mesh-only model (`@stl`/`@glb`/`@threemf` with no `@step`)
    -- the first mesh it declares. A STEP model that also declares meshes still
    names its STEP: the line names the model's primary document, not everything
    the build wrote."""
    if spec.step_output:
        return str(spec.step_path.expanduser().resolve()) if spec.step_path is not None else None
    for export in spec.mesh_exports:
        return str(export.path.expanduser().resolve())
    return None


def _model_for_spec(spec: EntrySpec) -> str | None:
    """The store identity of a spec: ``script::fn`` (generated) or its document's
    path (imported) -- cadgen.store.index.model_ref."""
    from cadgen.store.index import model_ref

    if spec.source == "generated" and spec.script_path is not None:
        function = getattr(spec.generator_metadata, "entry_function", None)
        return model_ref(spec.script_path, function)
    return str(spec.entry_path) if spec.entry_path is not None else None


def _assembly_is_current(spec: EntrySpec) -> bool:
    """Whether a generated model is current — THE gate (``cadgen.store.gate``):
    record present, closure unchanged, children standing at the keys it recorded,
    tree complete, outputs verify. Parts and assemblies share it."""
    if spec.source != "generated" or spec.step_path is None:
        return False
    from cadgen.store.gate import stale

    model = _model_for_spec(spec)
    return model is not None and not stale(model).stale


def _gate_verdict(spec: EntrySpec):
    """The gate's verdict on a generated model (``store.gate.stale``), or None."""
    if spec.source != "generated" or spec.step_path is None:
        return None
    from cadgen.store.gate import stale

    return stale(_model_for_spec(spec))


def _checked_source_tree(spec: EntrySpec, verdict: object | None = None) -> str | None:
    """The exact source result ``verdict`` checked, while it stands (``Verdict.key``:
    the gate's clauses 1-4 and 6 hold, and the files owe at most an export); without
    a verdict the gate is asked now."""
    if spec.source != "generated" or spec.step_path is None:
        return None
    if verdict is None:
        verdict = _gate_verdict(spec)
    return verdict.tree if verdict.key is not None else None


def _generated_assembly_glb_closure_current(spec: EntrySpec) -> bool:
    """Whether a generated model's record is current (imported models: True —
    their document IS their source and the store keys them by its bytes)."""
    if spec.source != "generated":
        return True
    return _assembly_is_current(spec)


def _assembly_glb_package_current(spec: EntrySpec) -> bool:
    """Whether the spec's current tree exists with every object present (gate
    clause 4). A document at a door is answered from objects alone: the tree
    for its bytes, complete — no record is consulted (STORE.md §2, the law)."""
    if spec.step_path is None:
        return False
    if spec.source != "generated":
        from cadgen.catalog import result_tree_for
        from cadgen.store.trees import tree_complete

        tree = result_tree_for(spec.entry_path) if spec.entry_path is not None else None
        return bool(tree) and tree_complete(tree)
    from cadgen.store.gate import stale

    model = _model_for_spec(spec)
    return model is not None and not stale(model).stale


@dataclass(frozen=True)
class _Built:
    """What :func:`build_model` answers: the model's result tree, how it came about
    (``current``: the stored result; ``built``: its body ran; ``skipped-peer``: a
    concurrent run published it first), and where a built model's time went."""

    tree: str | None
    outcome: str
    timings: dict[str, float] | None = None
    #: The key the result is stored under (store/results.py); a parent records the
    #: child by it.
    key: str | None = None


def build_model(
    spec: EntrySpec,
    *,
    generator: Callable[[], object] | None,
    force: bool,
    profile: bool,
    logger: CliLogger,
    progress_sink: object | None = None,
) -> _Built:
    """The one pipeline every decorated function goes through, root or child (STORE.md
    §9a): the gate, then either the stored result -- its parts' display data, its STEP
    (where the file does not hold the result or another writer wrote it) and its
    declared meshes owed without running its body -- or a run of the body, under a job
    slot and the run's scopes, publishing its record. Either way the files it owes are
    queued (``_Export``) and finished when the run that owns the command ends.

    ``generator`` is the model's function when its module is loaded already (a child a
    parent's body called); None loads the script. ``force`` and ``profile`` are the
    root's flags: they never reach a child.
    """
    # One gate verdict per model per build: taken here, re-taken only once the run
    # waited for a slot, which can change the answer. The already-stale notice after
    # publishing asks anew.
    verdicts: dict[str, object] = {}

    def verdict() -> object:
        if "verdict" not in verdicts:
            verdicts["verdict"] = _gate_verdict(spec)
        return verdicts["verdict"]

    if not force:
        tree = _checked_source_tree(spec, verdict())
        if tree is None:
            tree = _restore_result(spec, verdict(), logger=logger)
        if tree is not None:
            _hit(spec, tree, logger=logger, verdict=verdict())
            _tree_event(spec, "current")
            return _Built(tree, "current", key=verdict().key)

    # The same question, asked again when the run opens, so a run that started behind
    # a concurrent build of this model no-ops instead of rebuilding it. --force always
    # does the work.
    def built_by_a_peer(peer_spec: EntrySpec) -> str | None:
        return None if force else _checked_source_tree(peer_spec, verdict())

    def build(tracked_spec: EntrySpec, reporter: object) -> object:
        return _generate_step_outputs(
            tracked_spec,
            generator=generator,
            logger=logger if logger.verbose else None,
            force=force,
            progress=reporter,
            verdict=None if force else verdict(),
        )

    from cadgen.daemon.executors import capture_source_result

    timed: dict[str, dict[str, float]] = {}
    with capture_source_result(_model_for_spec(spec)) as captured:
        result = _run_with_spec_generation_status(
            spec,
            "step",
            build,
            skip_if_current=built_by_a_peer,
            progress_sink=progress_sink,
            logger=logger,
            on_queued=verdicts.clear,
            profile=profile,
            on_timed=lambda measured: timed.__setitem__("timings", measured),
        )
        captured._finish(0)
        if isinstance(result, _SkippedGeneration):
            return _Built(result.tree, "skipped-peer", key=verdict().key)
        if spec.source == "generated":
            result.tree = captured.wait_result()
    return _Built(result.tree, "built", timings=timed.get("timings"), key=result.key)


def _restore_result(spec: EntrySpec, verdict: object, *, logger: CliLogger) -> str | None:
    """A stored result for the source as it is NOW (``Verdict.candidate``, STORE.md
    §4): a source reverted to a state already built. Its record and provenance are
    restored from the result (``store.results``), and the model takes it as a
    current one, exporting what the files owe. None when there is none to restore,
    or its tree is gone; the verdict then names the restored key."""
    candidate = getattr(verdict, "candidate", None)
    if spec.source != "generated" or spec.step_path is None or not candidate or verdict.stored is not None:
        # A record whose stored result stands is the candidate itself: what it owes
        # beyond an export (a drawing) is a run's, not a restore's.
        return None
    from cadgen.store.provenance import write_provenance
    from cadgen.store.records import note_output, write_record
    from cadgen.store.results import read_result
    from cadgen.store.trees import claim_tree, tree_complete

    result = read_result(candidate)
    tree = str((result or {}).get("tree") or "")
    if not result or not tree or not tree_complete(tree) or not claim_tree(tree):
        return None
    record = dict(result["record"])
    model = _model_for_spec(spec)
    verdict.key = write_record(model, record)
    if result.get("provenance"):
        write_provenance(model, result["provenance"], tree=tree)
    for output_path in record.get("outputs") or {}:
        note_output(output_path, model)
    verdict.tree = tree
    logger.info(f"{spec.cad_ref}: an earlier build's result answers for the source as it is now; restored")
    return tree


def _recorded_sidecar(record: Mapping[str, object]) -> dict[str, object]:
    """The sidecar a model's result carries, from its record -- the kinematics, appearance
    and animation its build resolved, in the build's order -- so a file written again from
    the stored result gets the result's annotations, never the file's own
    (``annotation_refresh`` writes the same). Empty where the record holds none, which
    ``write_source_sidecar`` reads as: no sidecar."""
    return {section: copy.deepcopy(record[section]) for section in ("kinematics", "appearance", "animation")
            if record.get(section) is not None}


def _hit(spec: EntrySpec, tree: str, *, logger: CliLogger, verdict: object | None = None,
         healed: set[str] | None = None, display: bool = True) -> None:
    """A model whose stored result ``tree`` is current: its source result announced, what
    its children owe healed, then what it may still owe itself queued (``_Export``) --
    none of it by running its body. Its STEP (a file that did not hold its result,
    written plain this time; one another writer wrote; one whose entry the store lost;
    one missing, or never written because its export failed) and, with it or alone, its
    sidecar, written from the record (:func:`_recorded_sidecar`): a sidecar is a function
    of the result, so one on disk that is not the record's -- deleted, foreign, the other
    state's after a restore -- is written again even beside a kept STEP. Then its parts'
    display data (a cleared store) and its declared mesh exports (a deleted file, a
    changed declaration). The STEP first, so the display data derived is that of the
    result its bytes then map to, never of a marked file's own content.

    The children: a current model's body does not run, so it calls no child, yet its gate
    asked each one (``verdict``, clause 3). Every child whose result stands is healed the
    same way, by this path, its own children with it and before the parent, as a build
    queues them, so one run of the root leaves no file of the tree owed. A child whose
    record its source has moved on from, while a stored result answers for the source as
    it is now, is restored first (:func:`_restore_result`): the parent's hit leaves the
    child's record and files in the state the parent stands on. A child that owes a run
    does not stand, and the parent's run would have called it.

    ``display``: whether the model's parts' display data is asked for. A root's request
    covers its whole tree, links expanded, so the children it heals ask for none."""
    from cadgen.store.gate import stale
    from cadgen.store.index import split_model_ref
    from cadgen.store.records import read_record

    model = _model_for_spec(spec)
    healed = healed if healed is not None else set()
    healed.add(model)
    _current_source_result(spec, tree)
    record = read_record(model) or {}
    asked = getattr(verdict, "descendants", None) or {}
    for child in record.get("children") or []:
        child_model = str((child or {}).get("model") or "")
        if not child_model or child_model in healed:
            continue
        script, function = split_model_ref(child_model)
        source = source_from_path(script, function=function)
        if source is None:
            continue
        child_spec = _entry_spec_from_source(source)
        child_verdict = asked.get(child_model) or stale(child_model)
        if child_verdict.key is None and _restore_result(child_spec, child_verdict, logger=logger) is None:
            continue
        _hit(child_spec, child_verdict.tree, logger=logger, verdict=child_verdict, healed=healed, display=False)
        _tree_event(child_spec, "current")
    step = None
    if spec.source == "generated" and spec.step_output and spec.step_path is not None:
        from cadgen._internal.source_sidecar import source_sidecar_path

        pair = _document_pair_state(spec.step_path)
        plan = _export_plan(record, str(spec.step_path.expanduser().resolve()), tree, force=False, on_disk=pair[0])
        recorded = (record.get("outputs") or {}).get(str(source_sidecar_path(spec.entry_path).resolve())) or {}
        sidecar_owed = pair[1] != (str(recorded.get("sha256") or "") or None)
        if plan.kept is None:
            logger.info(f"{_display_path(spec.step_path)} {plan.why}; writing it again"
                        + (" without names" if plan.plain else ""))
        elif sidecar_owed:
            logger.info(f"{_display_path(source_sidecar_path(spec.step_path))} is not the record's; writing it again")
        if plan.kept is None or sidecar_owed:
            step = {"plan": plan, "record": copy.deepcopy(record), "sidecar_payload": _recorded_sidecar(record),
                    "expected_document_pair": pair, "live": {}, "still_saves": lambda: None}
    _Export(spec, tree, logger=logger, step=step, display=display)


def build_child(defn: object) -> tuple[str, str]:
    """A child model a parent's body called (``cadgen.authoring``): ``(key, tree)`` of
    its stored result, or of the result of running it now, in this process, as a build
    of its own -- once per run, however often it is called."""
    from cadgen.authoring import current_run

    run = current_run()
    if run is None:
        raise RuntimeError(f"{defn.ref} was called inside a body with no build run to belong to")
    result = run.results.get(defn.ref)
    if result is None:
        spec = _entry_spec_from_source(source_from_path(defn.script_path, function=defn.name))
        logger = run.logger if run.logger is not None else CliLogger("cadgen")
        built = build_model(spec, generator=defn.func, force=False, profile=False, logger=logger)
        if not built.tree or not built.key:
            raise RuntimeError(f"{defn.ref}: build supplied no source result")
        result = run.results[defn.ref] = (built.key, built.tree)
    return result


def generate_step_targets(
    targets: Sequence[str],
    *,
    force: bool = False,
    verbose: bool = False,
    json_output: bool = False,
    profile: bool = False,
    wait: bool = True,
) -> int:
    """Build trees for ``targets``. Returns the process exit code.

    ``json_output`` additionally prints one JSON line per target to STDOUT. The exit code
    alone cannot say WHICH targets were rebuilt and which were already current, and the
    logger's prose goes to stderr by design -- so without this a caller reading the streams
    apart had no machine-readable result at all.

    ``wait`` False (``--no-wait``) prints the result once every model's result is
    recorded and releases whoever asked (``executors.release_caller``: a daemon worker's
    client returns then), before the run finishes the files it queued; the files are
    written all the same, and a failure of theirs is this process's exit code and the
    build feed's, not the released caller's.
    """
    tool_name = "cadgen"
    logger = CliLogger("cadgen", verbose=verbose)
    reported: list[dict[str, object]] = []

    def _emit(spec: EntrySpec, built: _Built) -> None:
        from cadgen.daemon.telemetry import job_reused
        from cadgen.store.trees import tree_kind_for

        job_reused(built.outcome in ("current", "skipped-peer"))  # in a build worker: telemetry's cache hit, or not
        reported.append(
            {
                "ok": True,
                # Read off the tree (store.trees.tree_kind): part or assembly is
                # what the returned shape was, never something a model declares.
                "kind": tree_kind_for(built.tree) or "part",
                "outcome": built.outcome,
                # The document the run wrote, and the hash of the result tree it came
                # from. A mesh-only model declares no STEP, so it answers with the mesh
                # it wrote -- a path the caller can open, never the tree hash, which
                # names nothing on disk. ABSOLUTE in the JSON result, as every door's
                # is (a machine reader may not share this cwd); the human line below
                # shows it relative to the cwd.
                "document": _reported_document(spec),
                "tree": built.tree,
                # Where a built model's time went (cadgen._internal.build_timing); a
                # model that was current has none.
                "timings": built.timings if built.outcome == "built" else None,
            }
        )

    def _flush() -> None:
        # STDOUT IS THE RESULT, on every CLI: the logger's prose goes to stderr, so a
        # caller reading the two streams apart finds its answer here, as it does for a
        # door or a validator. One line per target, `outcome document`, upgraded to
        # JSON by --json. Every model has a document to name -- a mesh-only one names
        # its mesh -- so the tree hash is the last resort it never reaches.
        for entry in reported:
            if json_output:
                print(json.dumps(entry, separators=(",", ":")))
            else:
                document = entry["document"]
                print(f"{entry['outcome']} {_display_path(Path(document)) if document else entry['tree']}")

    _all_specs, selected_specs = _selected_specs_for_targets(targets)
    for spec in selected_specs:
        _validate_step_target(spec, tool_name=tool_name)
    from cadgen.authoring import build_run

    # The targets are the roots of the run: a child is built when its parent's body
    # calls it (cadgen.authoring), by the same pipeline, in this process. The run
    # finishes every export its calls queued -- each model's STEP, meshes and summary
    # line -- as it ends, children first, before the results are printed; with
    # ``wait`` False the results are printed, and the caller released, before that.
    with build_run(logger):
        for spec in selected_specs:
            logger.debug(f"Generating... {spec.source_ref}")
            with _cli_progress_line(spec, logger=logger, fallback="Generating...") as progress_sink:
                with logger.timed(f"generated {spec.source_ref}"):
                    built = build_model(spec, generator=None, force=force, profile=profile, logger=logger,
                                        progress_sink=progress_sink)
            document = _reported_document(spec)
            if built.outcome == "current":
                logger.info(f"{_display_path(Path(document)) if document else spec.cad_ref} is current; not rebuilt")
            elif built.outcome == "skipped-peer":
                logger.info(f"{spec.cad_ref} was built by a concurrent run; skipped")
            _emit(spec, built)
        if not wait:
            _answer(logger, _flush, release=True)
    if wait:
        _answer(logger, _flush)
    return 0


def _answer(logger: CliLogger, flush: Callable[[], None], *, release: bool = False) -> None:
    """The command's answer: its total and the result lines -- after its exports, whose
    end is the command's; or, with ``--no-wait`` (``release``), once every model's
    result is recorded, whoever asked released then (``executors.release_caller``) and
    the exports finishing after."""
    logger.total()
    flush()
    if release:
        from cadgen.daemon.executors import release_caller

        release_caller(0)


def generate_dxf_targets(
    targets: Sequence[str],
    *,
    force: bool = False,
    verbose: bool = False,
    json_output: bool = False,
    profile: bool = False,
    wait: bool = True,
) -> int:
    """Build drawings. A drawing is a model (STORE.md §3), so its run answers on
    stdout exactly as a STEP model's does: one `outcome document` line per
    target, upgraded to JSON by ``json_output`` (``tree`` is null — a drawing
    has no geometry tree). ``wait`` as :func:`generate_step_targets`'s: the
    drawing writes its own file in its run; what its children owe is queued."""
    from cadgen.store.gate import stale

    reported: list[dict[str, object]] = []
    timed: dict[str, dict[str, float]] = {}

    def _emit(spec: EntrySpec, outcome: str) -> None:
        from cadgen.daemon.telemetry import job_reused

        job_reused(outcome in ("current", "skipped-peer"))  # in a build worker: telemetry's cache hit, or not
        reported.append(
            {
                "ok": True,
                "kind": "drawing",
                "outcome": outcome,
                # Absolute in the JSON result, like every door's; the human line
                # shows it relative to the cwd.
                "document": str(spec.dxf_path.expanduser().resolve()) if spec.dxf_path is not None else None,
                "tree": None,
                "timings": timed.get(spec.source_ref) if outcome == "built" else None,
            }
        )

    def _flush() -> None:
        for entry in reported:
            if json_output:
                print(json.dumps(entry, separators=(",", ":")))
            else:
                document = entry["document"]
                print(f"{entry['outcome']} {_display_path(Path(document)) if document else None}")

    def dxf_output_current(spec: EntrySpec, output_path: Path | None) -> bool:
        # The ONE gate every model answers to (STORE.md §4): the drawing's record,
        # its closure, its children by key and its .dxf output.
        #
        # Ask it by the model's IDENTITY (``script::fn``), never by the bare script
        # path: a file may hold several models, and a bare path is ambiguous there --
        # cadgen.store.index.resolve_model_ref refuses it rather than guessing, which
        # would fail the drawing before it ever reached its own gate.
        if output_path is None:
            return False
        model = _model_for_spec(spec)
        if model is None:
            return False
        verdict = stale(model)
        return not verdict.stale

    logger = CliLogger("cadgen", verbose=verbose)
    all_specs, selected_specs = _selected_specs_for_targets(targets)
    for spec in selected_specs:
        _validate_dxf_target(spec)

    # The .dxf IS the product: every drawing writes the `.dxf` its decorator
    # declares (`out=`, else the sibling `<name>.dxf`). The viewer parses that
    # file directly; there is no drawing package.
    def _effective_output(spec: EntrySpec) -> Path | None:
        return spec.dxf_path

    # No-op fast path: skip regenerating a drawing whose source closure is
    # unchanged and whose recorded output still verifies byte-for-byte.
    if not force:
        current_specs = [
            spec
            for spec in selected_specs
            if spec.script_path is not None
            and dxf_output_current(spec, _effective_output(spec))
        ]
        for spec in current_specs:
            logger.info(
                f"{_display_path(spec.dxf_path) if spec.dxf_path is not None else spec.cad_ref} "
                "is current; not rebuilt"
            )
            _emit(spec, "current")
        current_refs = {spec.source_ref for spec in current_specs}
        selected_specs = [spec for spec in selected_specs if spec.source_ref not in current_refs]
    if selected_specs:
        # Re-checked when the run opens, like the STEP path: a run that started behind
        # a concurrent build of this drawing must not regenerate it.
        def _built_by_a_peer(spec: EntrySpec) -> bool:
            if force or spec.script_path is None:
                return False
            return dxf_output_current(spec, _effective_output(spec))

        from cadgen.authoring import build_run

        # The drawing's body calls models, each built by the same pipeline, in this
        # process, as a child of the drawing's run.
        with build_run(logger):
            for spec in selected_specs:
                logger.debug(f"Generating... {spec.source_ref}")
                with _cli_progress_line(spec, logger=logger, fallback="Generating...") as progress_sink:
                    with logger.timed(f"generated {spec.source_ref}"):
                        result = _run_with_spec_generation_status(
                            spec,
                            "dxf",
                            lambda tracked_spec, reporter: run_script_generator(
                                tracked_spec,
                                "dxf",
                                logger=logger,
                                progress=reporter,
                                model_prints_to_stdout=True,
                            ),
                            skip_if_current=_built_by_a_peer,
                            progress_sink=progress_sink,
                            logger=logger,
                            profile=profile,
                            on_timed=lambda measured, ref=spec.source_ref: timed.__setitem__(ref, measured),
                        )
                if isinstance(result, _SkippedGeneration):
                    logger.info(f"{spec.cad_ref} was built by a concurrent run; skipped")
                    _emit(spec, "skipped-peer")
                else:
                    logger.info(_generated_dxf_summary(spec))
                    _emit(spec, "built")
            if not wait:
                _answer(logger, _flush, release=True)
        if wait:
            _answer(logger, _flush)
    else:
        _answer(logger, _flush)
    return 0
