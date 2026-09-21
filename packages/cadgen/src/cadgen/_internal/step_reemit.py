"""``cadgen step build IN OUT``: one document in, a NEW document out.

The engine behind the STEP door's ``build`` verb. It re-emits an existing
document in cadgen's own dialect — OCCT read -> content-keyed tree ->
the canonical XCAF writer — so the OUTPUT's bytes are deterministic regardless
of which kernel wrote the input, and optionally ANNOTATES it with kinematics
that land in ``OUT``'s sidecar.

This is deliberately the SAME pipeline a model script runs. The scene is loaded
from ``IN``, re-pathed to ``OUT``, and handed to ``_generate_part_outputs`` as a
preloaded scene; everything downstream — package build, axis-ref resolution,
bake, canonical emit, store publish, sidecar write — is the one implementation
(design/pose-animation-split.md, CLI/doors follow-on). Two scene fields mark the
re-emit so the sidecar writer records ``sourceKind: "step"`` with the INPUT's
content hash as its closure instead of a Python provenance block.

Freshness has two independent halves, which is what makes a kinematics-only
edit cheap:

* BYTES depend on the input's content hash alone. Unchanged -> nothing is
  re-emitted. An annotation never moves geometry.
* The ANNOTATION (the kinematics declaration) is a sidecar digest. Changed
  alone, the sidecar is refreshed in place against the tree already on disk.

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
    ``{mates, couplings, poses}`` — spelled as inline JSON or named as a
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


def load_materials_config(raw: object, *, where: str) -> dict | None:
    """Load the same material definitions/assignments accepted by @step."""
    from cadgen._internal.source_sidecar import normalize_materials

    if raw is None:
        return None
    if isinstance(raw, str):
        text = raw.strip()
        if not text.startswith("{"):
            text = Path(text).expanduser().read_text(encoding="utf-8")
        try:
            raw = json.loads(text)
        except ValueError as error:
            raise _fail(f"{where} --materials is not valid JSON: {error}") from None
    return normalize_materials(raw, where=f"{where} --materials")


def load_animation_source(raw: object, *, where: str) -> dict | None:
    """Embed a JS input file or inline module source, never its source path."""
    from cadgen._internal.source_sidecar import normalize_animation

    if raw is None:
        return None
    if not isinstance(raw, str):
        raise _fail(f"{where} --animation must be a JavaScript file or module source")
    text = raw.strip()
    if "\n" not in text and not text.startswith(("export ", "//", "/*", "const ", "let ", "var ", "class ", "async ", "function ")):
        text = Path(text).expanduser().read_text(encoding="utf-8")
    return normalize_animation(text, where=f"{where} --animation")


def annotation_digest(kinematics_def: Any | None, appearance: object = None, materials: object = None, animation: object = None) -> str:
    """A stable digest of what the author DECLARED for this document.

    Digests the pre-resolution block (selector refs and all), so an annotation
    edit is detectable without re-resolving anything against geometry.
    """
    payload = {
        "kinematics": None if kinematics_def is None else kinematics_def.block,
        "materials": materials,
        "animation": animation,
        "appearance": appearance,
    }
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _file_hash(path: Path) -> str | None:
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _recorded_outputs_current(record: dict[str, Any], out: Path) -> bool:
    """Whether the record still describes every named output byte-for-byte."""
    from cadgen._internal.source_sidecar import source_sidecar_path

    outputs = record.get("outputs") or {}
    primary = str(out.expanduser().resolve())
    if not isinstance(outputs, dict) or primary not in outputs:
        return False
    sidecar = source_sidecar_path(out).resolve()
    if sidecar.exists() != (str(sidecar) in outputs):
        return False
    for path, meta in outputs.items():
        expected = str((meta or {}).get("sha256") or "") if isinstance(meta, dict) else ""
        if not expected or _file_hash(Path(path)) != expected:
            return False
    return True


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
    materials: dict | None = None,
    animation: dict | None = None,
    force: bool,
    logger: CliLogger,
) -> dict[str, object]:
    """Do the work and RETURN ``{ok, document, package, skipped, sidecarOnly}``.

    The freshness gate is read first and answers three ways: current (nothing to
    do), annotation-only (rewrite the sidecar beside bytes that already match),
    or emit.
    """
    from cadgen.catalog import artifact_file_hash, result_tree_for
    from cadgen._internal.source_sidecar import appearance_digest, read_source_provenance, read_source_sidecar, write_source_sidecar
    from cadgen.store.records import read_record, write_record

    input_hash = artifact_file_hash(document)
    if not input_hash:
        raise _fail(f"could not read {_display(document)}")
    appearance = (read_source_sidecar(document, document_hash=input_hash) or {}).get("appearance")
    appearance_key = appearance_digest(appearance)
    digest = annotation_digest(kinematics_def, appearance, materials, animation)

    sidecar = read_source_provenance(out) or {}
    tree = result_tree_for(out)
    record = read_record(out) or {}
    bytes_current = (
        not force
        and out.is_file()
        and tree is not None
        and _recorded_outputs_current(record, out)
        and str(sidecar.get("sourceKind") or "") == "step"
        and str(sidecar.get("sourceHash") or "") == input_hash
        and record.get("inputAppearance") == appearance_key
    )
    if bytes_current and str(sidecar.get("annotationHash") or "") == digest:
        return {
            "ok": True,
            "document": out,
            "tree": tree,
            "skipped": True,
            "sidecarOnly": False,
        }
    if bytes_current:
        # The ANNOTATION changed but the bytes cannot have: same input, and an
        # annotation never moves geometry. Re-resolve the declaration against a view of the tree already in
        # the store and rewrite the sidecar — no OCCT, no emit, no new tree.
        payload = dict(sidecar)
        from cadgen._internal.source_sidecar import resolve_materials
        from cadgen.store.trees import flatten

        # Reuse the saved geometry and resolve only the new declarations.
        # Re-emitted intrinsic materials are the baseline; root assignments
        # are applied afresh so removing an override restores that baseline.
        inherited = record.get("intrinsicAppearance")
        if inherited is None:
            inherited = appearance
        resolved_appearance = resolve_materials(flatten(tree), materials, inherited=inherited)
        payload.pop("appearance", None)
        if resolved_appearance is not None:
            payload["appearance"] = resolved_appearance
        payload.pop("animation", None)
        if animation is not None:
            payload["animation"] = animation
        payload["annotationHash"] = digest
        payload.pop("kinematics", None)
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
        if read_record(out) != record or not _recorded_outputs_current(record, out):
            raise RuntimeError(f"{_display(out)} changed while its annotations were being resolved")
        write_source_sidecar(out, payload)
        from cadgen._internal.source_sidecar import source_sidecar_path
        from cadgen.store.records import forget_output, note_output

        sidecar_path = source_sidecar_path(out).resolve()
        outputs = dict(record.get("outputs") or {})
        sidecar_hash = _file_hash(sidecar_path)
        if sidecar_hash is None:
            outputs.pop(str(sidecar_path), None)
            forget_output(sidecar_path)
        else:
            outputs[str(sidecar_path)] = {"sha256": sidecar_hash}
            note_output(sidecar_path, str(record.get("model") or out))
        if read_record(out) != record:
            raise RuntimeError(f"{_display(out)} record changed while its annotations were being written")
        updated_record = dict(record)
        updated_record.update(
            annotationHash=digest,
            kinematics=payload.get("kinematics"),
            appearance=payload.get("appearance"),
            animation=payload.get("animation"),
            outputs=outputs,
        )
        write_record(out, updated_record)
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
        materials=materials,
        animation=animation,
        appearance=appearance,
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
    materials: dict | None = None,
    animation: dict | None = None,
    appearance: object = None,
    force: bool,
    logger: CliLogger,
) -> None:
    """Read IN, re-path the scene to OUT, and run the ONE build pipeline."""
    from cadgen._internal.generation import _generate_part_outputs
    from cadgen._internal.step_scene_package import load_step_scene_exact
    from cadgen.step_artifact_cli import _build_entry_spec

    with logger.timed(f"load STEP {_display(document)}"):
        scene = load_step_scene_exact(document)
    if scene.step_hash != input_hash:
        raise RuntimeError(
            f"{_display(document)} changed while it was being read; retry the build"
        )
    if appearance is not None:
        from cadgen.store.build import build_document_tree
        from cadgen.store.materialize import materialize_descriptor
        from cadgen.store.trees import flatten
        from cadgen._internal.source_sidecar import apply_appearance

        canonical_hash, _tree, _stats = build_document_tree(scene)
        scene.source_compound = materialize_descriptor(apply_appearance(flatten(canonical_hash), appearance))
    # The scene now DESCRIBES the output: the tree is keyed by the bytes we
    # are about to write, and the preloaded-scene contract pins the two paths
    # together. `step_hash` is the INPUT's and would misidentify the output.
    scene.step_path = out.expanduser().resolve()
    scene.step_hash = None
    scene.reemit_source_hash = input_hash
    scene.reemit_annotation_hash = digest
    from cadgen._internal.source_sidecar import appearance_digest

    scene.reemit_appearance_hash = appearance_digest(appearance)
    scene.kinematics = None if kinematics_def is None else dict(kinematics_def.block)
    scene.materials = materials
    scene.animation = animation

    out.parent.mkdir(parents=True, exist_ok=True)
    spec = _build_entry_spec(Path.cwd().resolve(), scene.step_path, scene)
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
            entries_by_step_path={spec.step_path: spec},
            preloaded_scene=scene,
            require_step_file=False,
            force=force,
            logger=logger,
        )
