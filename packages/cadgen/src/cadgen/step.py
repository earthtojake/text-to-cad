"""The public ``step`` format namespace: the ``@step`` decorator and its verbs.

``@step`` DECLARES a model; the verbs OPERATE on documents. They are the same
object — this module is callable (see
:mod:`cadgen._internal.format_namespace`) — so a format is one table row:
decorator, verbs, and generated CLI together (design/format-doors.md).

Two verbs make documents, and the difference is what lands on disk:

* ``compile`` is a CACHE action — a document in, its tree in the
  store, the document untouched. It is INTERNAL: every door and the viewer
  compile a missing package on demand, so no skill teaches the command.
* ``build`` writes a NEW document — ``IN.step OUT.step`` — re-emitted through
  cadgen's own pipeline (OCCT read -> package -> canonical XCAF writer), so the
  output's bytes are deterministic whichever kernel wrote the input, and
  optionally annotated with ``kinematics=``. OUT is REQUIRED,
  which is what tells the two verbs apart at the command line.

Model scripts are RUN, never passed here: ``python model.py`` is the one source
door (design/pose-animation-split.md, CLI/doors follow-on). Every verb takes a
DOCUMENT and refuses a ``.py`` by naming the run.

Import discipline: nothing here may pull in OCP/build123d at module scope. A
model script pays this import before its freshness gate runs, and the whole
point of the ~0.2s pre-gate budget is that a current model never wakes the CAD
kernel. Every heavy import lives inside a verb body.
"""

from __future__ import annotations

from pathlib import Path

from cadgen._internal.format_namespace import callable_namespace
from cadgen._internal.snapshot_door import step_snapshot_verb
from cadgen.results import BuildResult, CompileResult

__all__ = ["build", "compile", "snapshot"]

#: ``cadgen step snapshot``'s verb: render a STEP/STP document. Mesh inputs
#: belong to their own doors (``cadgen.stl.snapshot`` and friends).
snapshot = step_snapshot_verb("step")


def compile(  # noqa: A001 - the verb IS "compile"; the builtin is not used here
    target: Path,
    *,
    force: bool = False,
    verbose: bool = False,
) -> CompileResult:
    """Make TARGET's tree current; no-op when it already is.

    A cache action, not a build: the tree is keyed by the document's bytes, so
    nothing new appears beside the model and repeating it is free. Every door
    and the CAD Viewer compile a missing tree on demand — this command exists
    for tooling and CI, and no skill documentation teaches it.

    target: the STEP/STP document to compile.
    force: recompile even when the tree is already current.
    verbose: show detailed progress and timing on stderr.
    """
    from cadgen._internal.doors import document_target
    from cadgen.step_artifact_cli import build_step_artifact

    # The document's BYTES are compiled, generated or imported alike; whether its
    # source has moved on is its model's business, not this door's.
    document = document_target(target, suffixes=(".step", ".stp"))
    payload = build_step_artifact(
        repo_root=Path.cwd(),
        step=document,
        source_path=None,
        force=force,
        verbose=verbose,
    )

    def path_of(key: str) -> Path | None:
        value = payload.get(key)
        return Path(str(value)).resolve() if value else None

    return CompileResult(
        ok=bool(payload.get("ok", True)),
        document=path_of("document"),
        tree=str(payload.get("tree") or "") or None,
        skipped=bool(payload.get("skipped")),
    )


def build(
    target: Path,
    out: Path,
    *,
    kinematics: str | dict | None = None,
    materials: str | dict | None = None,
    animation: str | None = None,
    force: bool = False,
    verbose: bool = False,
) -> BuildResult:
    """Write OUT: TARGET re-emitted in cadgen's dialect, optionally annotated —
    compile caches a document, build writes a new one.

    TARGET is read with
    OCCT, packaged, and re-emitted by the canonical XCAF writer, so OUT's bytes
    are deterministic regardless of which kernel produced TARGET — the way to
    canonicalize a foreign STEP or to give one kinematics without wrapping it
    in a model script. Vendor metadata (PMI, GD&T) does not survive; a model
    that keeps evolving belongs in a script instead.

    Re-running is a no-op. Editing only declared materials, animation or
    kinematics refreshes OUT's sidecar without re-emitting STEP geometry.

    target: the STEP/STP document to read.
    out: the STEP/STP document to write. Required, and never TARGET itself.
    kinematics: the kinematics SPACE this document declares — inline JSON or a
        .json path, with the same {mates, couplings, poses} vocabulary the
        decorator takes.
    materials: named material definitions and component assignments, as inline
        JSON or a .json path, using the same vocabulary as @step materials=.
    animation: a JavaScript file path or self-contained ES module source exporting
        clips; embedded into OUT's JSON sidecar.
    force: re-emit even when the freshness gate says OUT is current.
    verbose: show detailed progress and timing on stderr.
    """
    from cadgen._internal.step_reemit import (
        load_kinematics_space,
        load_materials_config,
        load_animation_source,
        reemit_step_document,
        resolve_output,
    )
    from cadgen.cli_logging import CliLogger

    document, destination = resolve_output(target, out)
    where = "cadgen step build"
    kinematics_def = load_kinematics_space(kinematics, where=where)
    payload = reemit_step_document(
        document,
        destination,
        kinematics_def=kinematics_def,
        materials=load_materials_config(materials, where=where),
        animation=load_animation_source(animation, where=where),
        force=force,
        logger=CliLogger(where, verbose=verbose),
    )
    return BuildResult(
        ok=bool(payload.get("ok", True)),
        document=payload.get("document"),  # type: ignore[arg-type]
        tree=payload.get("tree"),  # type: ignore[arg-type]
        skipped=bool(payload.get("skipped")),
        sidecar_only=bool(payload.get("sidecarOnly")),
    )


def __getattr__(name: str):
    if name in {"inspect", "INSPECTIONS"}:
        raise ImportError("step.inspect has been removed; use cadgen.read_scene and cadgen.geometry in a Python script")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


callable_namespace(__name__, "step")
