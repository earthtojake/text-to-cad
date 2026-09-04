"""The public ``step`` format namespace: the ``@step`` decorator and its verbs.

``@step`` DECLARES a model; the verbs OPERATE on documents. They are the same
object — this module is callable (see
:mod:`cadgen._internal.format_namespace`) — so a format is one table row:
decorator, verbs, and generated CLI together (design/format-doors.md).

Two verbs make documents, and the difference is what lands on disk:

* ``compile`` is a CACHE action — a document in, its render package in the
  store, the document untouched. It is INTERNAL: every door and the viewer
  compile a missing package on demand, so no skill teaches the command.
* ``build`` writes a NEW document — ``IN.step OUT.step`` — re-emitted through
  cadgen's own pipeline (OCCT read -> package -> canonical XCAF writer), so the
  output's bytes are deterministic whichever kernel wrote the input, and
  optionally annotated with ``kinematics=``/``animation=``. OUT is REQUIRED,
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

from collections.abc import Sequence
from pathlib import Path

from cadgen._internal.format_namespace import callable_namespace
from cadgen._internal.snapshot_door import step_snapshot_verb
from cadgen.results import BuildResult, CompileResult, InspectResult

__all__ = ["build", "compile", "inspect", "snapshot"]

#: ``cadgen step snapshot``'s verb: render a STEP/STP document. Mesh inputs
#: belong to their own doors (``cadgen.stl.snapshot`` and friends).
snapshot = step_snapshot_verb("step")


def compile(  # noqa: A001 - the verb IS "compile"; the builtin is not used here
    target: Path,
    *,
    force: bool = False,
    verbose: bool = False,
) -> CompileResult:
    """Make TARGET's render package current; no-op when it already is.

    A cache action, not a build: the package is keyed by the document's bytes,
    so nothing new appears beside the model and repeating it is free. Every
    door and the CAD Viewer compile a missing package on demand — this command
    exists for tooling and CI, and no skill documentation teaches it.

    target: the STEP/STP document to compile.
    force: recompile even when the package is already current.
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
        document=path_of("stepPath"),
        tree=str(payload.get("tree") or "") or None,
        skipped=bool(payload.get("skipped")),
    )


def build(
    target: Path,
    out: Path,
    *,
    kinematics: str | dict | None = None,
    animation: Path | None = None,
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

    Re-running is a no-op. Editing only the kinematics or animation refreshes
    OUT's sidecar without re-emitting a byte.

    target: the STEP/STP document to read.
    out: the STEP/STP document to write. Required, and never TARGET itself.
    kinematics: the kinematics SPACE this document declares — inline JSON or a
        .json path, with the same {mates, couplings, poses, at} vocabulary the
        decorator takes.
    animation: a .js choreography module whose TEXT is copied into the sidecar.
    force: re-emit even when the freshness gate says OUT is current.
    verbose: show detailed progress and timing on stderr.
    """
    from cadgen._internal.step_reemit import (
        load_animation_text,
        load_kinematics_space,
        reemit_step_document,
        resolve_output,
    )
    from cadgen.cli_logging import CliLogger

    document, destination = resolve_output(target, out)
    where = "cadgen step build"
    kinematics_def = load_kinematics_space(kinematics, where=where)
    animation_source = load_animation_text(animation, where=where)
    payload = reemit_step_document(
        document,
        destination,
        kinematics_def=kinematics_def,
        animation_source=animation_source,
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


INSPECTIONS = ("refs", "diff", "frame", "measure", "align", "interfere", "validate")


def inspect(
    target: Path,
    refs: "Sequence[str] | None" = None,
    *,
    inspection: str = "refs",
    against: Path | None = None,
    moving: str = "",
    onto: str = "",
    align_mode: str = "flush",
    offset: float = 0.0,
    axis: str = "",
    detail: bool = False,
    facts: bool = False,
    positioning: bool = False,
    planes: bool = False,
    topology: bool = False,
    plane_coordinate_tolerance: float = 1e-3,
    plane_min_area_ratio: float = 0.05,
    plane_limit: int = 12,
    tolerance: float | None = None,
    max_pairs: int | None = None,
    allow_open: bool = False,
    skip_self_intersection: bool = False,
    every_placement: bool = False,
    out: Path | None = None,
) -> InspectResult:
    """Answer one geometry question about TARGET, without changing it.

    The parameters are a union across the inspections because the CLI's
    subcommands are: `cadgen step inspect <inspection>` is this function with
    the arguments that inspection reads, and the ones it does not read are
    ignored. Every inspection resolves refs the same way and builds the same
    package, so they are one verb with a mode rather than seven verbs.

    target: STEP/STP document, or a CAD entry target naming one.
    refs: selector refs such as `#o1.2` or `#f9`. refs/interfere/validate read
        the whole list; measure reads the first two as from/to; frame reads the
        first as the occurrence to report.
    inspection: refs (default), diff, frame, measure, align, interfere, or
        validate.
    against: the right-hand document, for `diff`.
    moving: the selector being placed, for `align`.
    onto: the selector it is placed against, for `align`.
    align_mode: flush, center, or contact — how `align` relates the two.
    offset: extra distance along the axis, for `align`.
    axis: x, y or z. Inferred from the selectors when omitted.
    detail: include full geometry facts for each resolved face/edge ref.
    facts: include compact geometry facts for whole entries and selectors.
    positioning: include placement-ready frame, point, plane and axis facts.
    planes: include grouped major planar faces.
    topology: include full face/edge selector lists. Expensive on large models.
    plane_coordinate_tolerance: merge planar groups within this coordinate
        distance.
    plane_min_area_ratio: drop planar groups below this fraction of total
        planar area.
    plane_limit: maximum number of plane groups to report.
    tolerance: minimum overlap volume in mm3 that counts, for `interfere`.
    max_pairs: stop after this many interfering pairs, for `interfere`.
    allow_open: treat surface/shell geometry as intended, for `validate`.
    skip_self_intersection: skip the boolean self-intersection test, which
        dominates runtime on large assemblies, for `validate`.
    every_placement: for `validate`, run the numeric self-intersection test
        on every placed copy of a part instead of once at its first placement.
        Topology, closure and volume are always checked once per unique shape.
    out: for `validate`, a path that receives the JSON report as it
        accumulates (`"partial": true` until the last part lands), so a killed
        run leaves a readable document.
    """
    # Every heavy import stays in the body: this module is on a model script's
    # pre-gate path (see the module docstring).
    from cadgen._internal.doors import script_target_message
    from cadgen.cli.step_inspect import inspect as inspection_api

    if str(target).strip().lower().endswith(".py"):
        # A CadRefError, not a bare ValueError: an unusable target is an ANSWER
        # here, so the refusal prints as this door's ordinary error report
        # rather than as a traceback.
        raise inspection_api.CadRefError(script_target_message(Path(str(target))))
    if inspection not in INSPECTIONS:
        raise ValueError(
            f"unknown inspection {inspection!r}; expected one of: {', '.join(INSPECTIONS)}"
        )
    entry = str(target)
    selectors = [str(ref) for ref in (refs or [])]
    plane_options = {
        "planes": planes,
        "plane_coordinate_tolerance": float(plane_coordinate_tolerance),
        "plane_min_area_ratio": float(plane_min_area_ratio),
        "plane_limit": int(plane_limit),
    }
    try:
        if inspection == "refs":
            report = inspection_api.inspect_cad_refs(
                entry,
                # One ref per line is the shape the token parser is fed
                # everywhere else, including `--input-file`.
                "\n".join(selectors),
                detail=detail,
                include_topology=topology,
                facts=facts,
                positioning=positioning,
                **plane_options,
            )
        elif inspection == "diff":
            if against is None:
                raise ValueError("diff needs a second document: pass against=")
            report = inspection_api.diff_entry_targets(entry, str(against), **plane_options)
        elif inspection == "frame":
            report = inspection_api.inspect_target_frame(entry, selectors[0] if selectors else "")
        elif inspection == "measure":
            if len(selectors) < 2:
                raise ValueError("measure needs two refs: pass refs=[from, to]")
            report = inspection_api.measure_targets(
                entry, selectors[0], selectors[1], axis=axis or None
            )
        elif inspection == "align":
            report = inspection_api.align_targets(
                entry, moving, onto, mode=align_mode, offset=float(offset), axis=axis or None
            )
        elif inspection == "interfere":
            from cadgen import interference

            report = interference.inspect_interference(
                entry,
                refs=selectors,
                tolerance=(
                    interference.DEFAULT_TOLERANCE_MM3 if tolerance is None else tolerance
                ),
                max_pairs=max_pairs,
            )
        else:
            from cadgen import validity

            report = validity.inspect_validity(
                entry,
                refs=selectors,
                allow_open=allow_open,
                check_self_intersection=not skip_self_intersection,
                every_placement=every_placement,
                out=out,
            )
    except inspection_api.CadRefError as exc:
        # A ref that does not resolve is an ANSWER, not a crash: the report says
        # which token failed and why, and the CLI prints it like any other.
        report = {"ok": False, "errors": [inspection_api.cad_ref_error_payload(exc)]}
    return InspectResult(
        ok=bool(report.get("ok")), command=inspection, report=dict(report)
    )


callable_namespace(__name__, "step")
