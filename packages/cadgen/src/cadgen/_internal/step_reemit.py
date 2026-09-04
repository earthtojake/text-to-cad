"""``cadgen step build IN OUT``: one document in, a NEW document out.

The engine behind the STEP door's ``build`` verb. It re-emits an existing
document in cadgen's own dialect — OCCT read -> content-keyed tree ->
the canonical XCAF writer — so the OUTPUT's bytes are deterministic regardless
of which kernel wrote the input, and optionally ANNOTATES it with kinematics
and animation that land in ``OUT``'s sidecar.

This is deliberately the SAME pipeline a model script runs. The scene is loaded
from ``IN``, re-pathed to ``OUT``, and handed to ``_generate_part_outputs`` as a
preloaded scene; everything downstream — package build, axis-ref resolution,
bake, canonical emit, store publish, sidecar write — is the one implementation
(design/pose-animation-split.md, CLI/doors follow-on). Two scene fields mark the
re-emit so the sidecar writer records ``sourceKind: "step"`` with the INPUT's
content hash as its closure instead of a Python provenance block.

Freshness has two independent halves, which is what makes a kinematics-only
edit cheap:

* BYTES depend on the input's content hash and the bake point. Unchanged ->
  nothing is re-emitted.
* The ANNOTATION (the kinematics declaration and the animation text) is a
  sidecar digest. Changed alone, with no bake, the sidecar is refreshed in
  place against the tree already on disk.

Not for foreign metadata: PMI, GD&T and vendor extensions do not survive the
round trip. That is the documented price of speaking one dialect.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from cadgen.cli_logging import CliLogger

STEP_SUFFIXES = (".step", ".stp")


def _fail(message: str) -> ValueError:
    return ValueError(message)


def _display(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(Path.cwd().resolve()))
    except (OSError, ValueError):
        return str(path)


def load_kinematics_space(raw: object, *, where: str) -> Any | None:
    """``--kinematics`` on a DECLARING surface: the whole space, not a point.

    ``step build`` declares kinematics for a document that has no model script,
    so its ``--kinematics`` takes the same dict the decorator does —
    ``{mates, couplings, poses, at}`` — spelled as inline JSON or named as a
    ``.json`` file. Both go through :func:`cadgen.kinematics.normalize_kinematics`,
    the one validator, so the JSON and Python spellings cannot drift.
    """
    from cadgen.kinematics import normalize_kinematics

    if raw is None:
        return None
    if isinstance(raw, dict):
        return normalize_kinematics(raw, where=where)
    text = str(raw).strip()
    if not text:
        return None
    if text.startswith("{"):
        try:
            parsed = json.loads(text)
        except ValueError as exc:
            raise _fail(f"{where} --kinematics is not valid JSON: {exc}") from None
    else:
        path = Path(text).expanduser()
        if not path.is_file():
            raise _fail(
                f"{where} --kinematics takes the kinematics SPACE: inline JSON "
                f"({{'mates': [...]}}) or a path to a .json file; no such file: {text}"
            )
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise _fail(f"{where} --kinematics file is not valid JSON: {exc}") from None
    if not isinstance(parsed, dict):
        raise _fail(f"{where} --kinematics must be a JSON object, got {type(parsed).__name__}")
    return normalize_kinematics(parsed, where=where)


def load_animation_text(animation: Path | None, *, where: str) -> str | None:
    """The declared ``.js`` choreography module's TEXT, copied.

    Same contract as ``@step(animation=...)``: the file must exist (there is no
    convention discovery), and only its text travels — no generated file ever
    references the source tree.
    """
    if animation is None:
        return None
    path = Path(animation).expanduser()
    if path.suffix.lower() != ".js":
        raise _fail(f"{where} --animation must name a .js module, got {animation}")
    if not path.is_file():
        raise _fail(f"{where} --animation module not found: {animation}")
    return path.read_text(encoding="utf-8")


def annotation_digest(kinematics_def: Any | None, animation_source: str | None) -> str:
    """A stable digest of what the author DECLARED for this document.

    Digests the pre-resolution block (selector refs and all) plus the bake point
    and the animation text, so an annotation edit is detectable without
    re-resolving anything against geometry.
    """
    payload = {
        "kinematics": None if kinematics_def is None else kinematics_def.block,
        "at": None if kinematics_def is None else kinematics_def.at,
        "animation": animation_source,
    }
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _same_pose(left: object, right: object) -> bool:
    def norm(value: object) -> dict[str, float]:
        if not isinstance(value, dict) or not value:
            return {}
        return {str(k): float(v) for k, v in value.items()}

    return norm(left) == norm(right)


def resolve_output(target: Path, out: Path) -> tuple[Path, Path]:
    """The (input, output) pair, both validated as documents.

    OUT is REQUIRED and is what separates this verb from the cache action:
    ``cadgen step compile`` makes a document's package current, ``cadgen step
    build`` writes a new document. Writing onto the input is refused — a
    re-emit that clobbers its own source cannot be re-run.
    """
    from cadgen._internal.doors import document_target

    document = document_target(target, suffixes=STEP_SUFFIXES)
    destination = Path(out).expanduser()
    if destination.suffix.lower() not in STEP_SUFFIXES:
        raise _fail(f"OUT must be a .step/.stp document: {out}")
    destination = destination.resolve()
    if destination == document:
        raise _fail(
            f"OUT is the input document ({_display(document)}): `cadgen step build` "
            "writes a NEW document — give it a different path (to make an existing "
            "document's tree current instead, that is what compile does)"
        )
    return document, destination


def reemit_step_document(
    document: Path,
    out: Path,
    *,
    kinematics_def: Any | None,
    animation_source: str | None,
    force: bool,
    logger: CliLogger,
) -> dict[str, object]:
    """Do the work and RETURN ``{ok, document, package, skipped, sidecarOnly}``.

    The freshness gate is read first and answers three ways: current (nothing to
    do), annotation-only (rewrite the sidecar beside bytes that already match),
    or emit.
    """
    from cadgen.catalog import artifact_file_hash, result_tree_for
    from cadgen._internal.source_sidecar import read_source_provenance, write_source_sidecar
    from cadgen.store.records import update_record

    input_hash = artifact_file_hash(document)
    if not input_hash:
        raise _fail(f"could not read {_display(document)}")
    digest = annotation_digest(kinematics_def, animation_source)
    at = None if kinematics_def is None else kinematics_def.at

    sidecar = read_source_provenance(out) or {}
    tree = result_tree_for(out)
    bytes_current = (
        not force
        and out.is_file()
        and tree is not None
        and str(sidecar.get("sourceKind") or "") == "step"
        and str(sidecar.get("sourceHash") or "") == input_hash
        and _same_pose((sidecar.get("kinematics") or {}).get("bakedPose"), at)
    )
    if bytes_current and str(sidecar.get("annotationHash") or "") == digest:
        return {
            "ok": True,
            "document": out,
            "tree": tree,
            "skipped": True,
            "sidecarOnly": False,
        }
    if bytes_current and at is None:
        # The ANNOTATION changed but the bytes cannot have: no bake point, same
        # input. Re-resolve the declaration against a view of the tree already in
        # the store and rewrite the sidecar — no OCCT, no emit, no new tree.
        payload = dict(sidecar)
        payload["annotationHash"] = digest
        payload.pop("kinematics", None)
        payload.pop("animation", None)
        if kinematics_def is not None:
            import shutil

            from cadgen._internal.kinematics_resolve import resolve_kinematics_block
            from cadgen.store.view import export_view

            view_dir = export_view(tree)
            try:
                resolved, _ids = resolve_kinematics_block(
                    kinematics_def.block,
                    package_dir=view_dir,
                    step_path=out,
                    source_ref=_display(out),
                )
            finally:
                shutil.rmtree(view_dir, ignore_errors=True)
            payload["kinematics"] = resolved
        if animation_source:
            payload["animation"] = {"clips": animation_source}
        update_record(out, annotationHash=digest, kinematics=payload.get("kinematics"))
        write_source_sidecar(out, payload)
        return {
            "ok": True,
            "document": out,
            "tree": tree,
            "skipped": False,
            "sidecarOnly": True,
        }

    _emit(
        document,
        out,
        input_hash=input_hash,
        digest=digest,
        kinematics_def=kinematics_def,
        animation_source=animation_source,
        force=force,
        logger=logger,
    )
    return {
        "ok": out.is_file(),
        "document": out,
        "tree": result_tree_for(out),
        "skipped": False,
        "sidecarOnly": False,
    }


def _emit(
    document: Path,
    out: Path,
    *,
    input_hash: str,
    digest: str,
    kinematics_def: Any | None,
    animation_source: str | None,
    force: bool,
    logger: CliLogger,
) -> None:
    """Read IN, re-path the scene to OUT, and run the ONE build pipeline."""
    from cadgen._internal.generation import _generate_part_outputs
    from cadgen._internal.step_scene import load_step_scene
    from cadgen.step_artifact_cli import (
        _build_entry_spec,
        _entries_by_step_path_for_repo,
        infer_entry_kind,
    )

    with logger.timed(f"load STEP {_display(document)}"):
        scene = load_step_scene(document)
    kind = infer_entry_kind(document, scene)
    # The scene now DESCRIBES the output: the tree is keyed by the bytes we
    # are about to write, and the preloaded-scene contract pins the two paths
    # together. `step_hash` is the INPUT's and would misidentify the output.
    scene.step_path = out.expanduser().resolve()
    scene.step_hash = None
    scene.reemit_source_hash = input_hash
    scene.reemit_annotation_hash = digest
    scene.kinematics = None if kinematics_def is None else dict(kinematics_def.block)
    scene.bake_pose = None if kinematics_def is None else kinematics_def.at
    scene.animation_source = animation_source

    out.parent.mkdir(parents=True, exist_ok=True)
    spec = _build_entry_spec(Path.cwd().resolve(), scene.step_path, scene, kind=kind)
    from dataclasses import replace as _replace

    from cadgen.catalog import build_scope
    from cadgen.cli_progress import cli_progress_line
    from cadgen.coordination import STEP_PACKAGE, artifact_build

    # source="generated" selects the STAGE-then-publish path: a document whose
    # content key does not exist until after it is written. That is exactly the
    # shape of a re-emit, and it is why the writer here is the canonical one.
    spec = _replace(spec, source="generated", script_path=None, step_path=scene.step_path)
    # Progress keyed by the MODEL PATH, never by the content-keyed view directory: a
    # re-emit's content key does not exist until the document has been written, so a
    # package-keyed record would land where no reader (the viewer polls the model's
    # build scope) looks. Two concurrent re-emits of one output both proceed; every
    # store write is atomic and idempotent, so neither can tear the other.
    with cli_progress_line(
        spec.source_ref, logger=logger, fallback="Building..."
    ) as progress_sink, artifact_build(
        STEP_PACKAGE,
        build_scope(spec.entry_path) if spec.entry_path else None,
        force=True,
        sink=progress_sink,
    ):
        _generate_part_outputs(
            spec,
            entries_by_step_path=_entries_by_step_path_for_repo(Path.cwd().resolve(), spec),
            preloaded_scene=scene,
            require_step_file=False,
            force=force,
            logger=logger,
        )
