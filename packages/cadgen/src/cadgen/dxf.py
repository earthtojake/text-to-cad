"""The public ``dxf`` format namespace: the ``@dxf`` decorator and its verbs.

``@dxf`` DECLARES a drawing; ``dxf.snapshot(...)`` renders one. They are the
same object — this module is callable (see
:mod:`cadgen._internal.format_namespace`) — so the drawing family is one table
row like every other format (README law 6).

**There is no ``dxf.build``** (deleted, hard cutover). A ``.dxf`` has no derived
state a door must materialize: the file IS the product, and both the CAD Viewer
and snapshot draw it from the same server-side 2D payload
(:mod:`cadgen.drawing_payload`). Drawings are made the way every model is made —
by running the script: ``python drawing.py``.

Import discipline: nothing here may pull in ezdxf/OCP at module scope (see
:mod:`cadgen.step`).
"""

from __future__ import annotations

from pathlib import Path

from cadgen._internal.format_namespace import callable_namespace
from cadgen._internal.snapshot_door import drawing_snapshot_verb
from cadgen.results import ValidationResult

__all__ = ["snapshot", "validate"]

#: ``cadgen dxf snapshot``'s verb: draw a ``.dxf`` flat, as the viewer draws it.
snapshot = drawing_snapshot_verb("dxf")


def validate(
    target: Path,
    *,
    strict: bool = False,
    verbose: bool = False,
) -> ValidationResult:
    """Check one DXF drawing or cut layout for conformance.

    Verifies document units ($INSUNITS), detects open cut profiles, degenerate
    entities, duplicate geometry (double-cut risk), and classifies dimensioned
    drawings versus cut layouts. Errors always block; under ``strict`` warnings do too.

    target: the .dxf file to validate.
    strict: treat warnings as blocking.
    verbose: narrate the target on stderr.
    """
    import sys

    from cadgen._internal.validation_door import (
        blocks,
        display_path,
        failed,
        resolved_target,
        result_from_findings,
    )
    from cadgen.findings import FindingsReport

    dxf_path = resolved_target(target, label="dxf")
    if verbose:
        print(f"[dxf] validating {dxf_path}", file=sys.stderr)
    if dxf_path.suffix.lower() != ".dxf":
        return failed(dxf_path, "target must be a .dxf file")
    if not dxf_path.is_file():
        return failed(dxf_path, "file not found")
    if dxf_path.stat().st_size == 0:
        return failed(dxf_path, "file is empty", code="empty_file")

    try:
        import ezdxf
        from cadgen.drawing_checks import validate_drawing_document

        document = ezdxf.readfile(str(dxf_path))
    except Exception as exc:  # noqa: BLE001
        return failed(dxf_path, f"Could not parse DXF file: {exc}", code="unparsable_dxf")

    raw_findings = validate_drawing_document(document)
    findings = FindingsReport()
    for item in raw_findings:
        findings.add(
            item.severity,  # "error", "warning", or "info"
            item.code,
            item.message,
            path=str(dxf_path),
        )

    summary = ""
    if not blocks(findings, strict=strict):
        from cadgen.drawing_checks import document_is_drawing

        is_drawing, drawing_evidence = document_is_drawing(document)
        modelspace = document.modelspace()
        entity_count = len(list(modelspace))
        kind_str = f"drawing ({drawing_evidence})" if is_drawing else "cut layout"
        summary = f"OK {display_path(dxf_path)}: {kind_str}, {entity_count} entity/entities"

    return result_from_findings(dxf_path, findings, strict=strict, summary=summary)


def __getattr__(name: str):
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


callable_namespace(__name__, "dxf")
